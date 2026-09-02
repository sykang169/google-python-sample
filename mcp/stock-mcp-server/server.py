"""Stock MCP Server — 금융위원회 주식시세정보 OpenAPI를 MCP 도구로 노출한다.

data.go.kr의 GetStockSecuritiesInfoService 4개 오퍼레이션을 다룬다.
DART/ECOS 서버와 달리 API 표면이 작아서(4개) 카탈로그 검색 없이 직접 도구로 낸다.

Gemini Enterprise의 Custom MCP Server 데이터 스토어가 소비할 수 있도록
StreamableHTTP 전송을 쓴다. (Gemini Enterprise는 레거시 SSE를 지원하지 않는다.)

주의: 이 저장소의 기존 stock_analytics 코드는 `verify=False`로 TLS 검증을 껐지만,
실제로 확인해 보면 apis.data.go.kr는 정상 인증서를 제공한다. 여기서는 검증을 켠다.
"""

from __future__ import annotations

import logging
import os
import random
import time
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

BASE = "https://apis.data.go.kr/1160100/service/GetStockSecuritiesInfoService"
TIMEOUT = httpx.Timeout(30.0, connect=10.0)

# Cloud Run에서는 Secret Manager 값이 환경변수로 주입된다.
# data.go.kr 키는 '+', '/', '=' 를 포함하는 디코딩 형태다. httpx가 알아서
# 퍼센트 인코딩하므로 미리 인코딩해서 넣으면 이중 인코딩이 되어 실패한다.
API_KEY = os.environ.get("STOCK_API_KEY", "")

# httpx의 INFO 로그는 쿼리스트링을 포함한 전체 URL을 남긴다. 거기에 serviceKey가
# 들어 있어 Cloud Logging에 인증키가 적재된다. WARNING으로 올려 막는다.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True}

# data.go.kr 공통 결과 코드 중 자주 보는 것들.
RESULT_CODES = {
    "00": None,
    "01": "애플리케이션 에러",
    "02": "데이터베이스 에러",
    "03": "데이터 없음",
    "04": "HTTP 에러",
    "05": "서비스 연결 실패",
    "10": "잘못된 요청 파라미터",
    "11": "필수 요청 파라미터 누락",
    "12": "해당 오픈API 서비스가 없거나 폐기됨",
    "20": "서비스 접근 거부",
    "22": "서비스 요청 제한 횟수 초과",
    "30": "등록되지 않은 서비스키",
    "31": "활용기간 만료된 서비스키",
    "32": "등록되지 않은 IP",
    "33": "서명되지 않은 호출",
}

# 재시도 정책. apis.data.go.kr은 앞단에서 TCP 연결을 끊는 구간이 실제로
# 관측된다(약 20분간 연결 거부 후 조치 없이 자체 복구). 지수 백오프 + 지터로
# 짧은 장애 구간을 넘긴다. 긴 구간은 넘기지 못하므로 오류를 그대로 올린다.
MAX_ATTEMPTS = 3
BACKOFF_BASE = 1.0
BACKOFF_CAP = 6.0

# 재시도할 가치가 있는 resultCode. 03(데이터 없음), 10/11(잘못된 파라미터),
# 30/31/32(키 문제)처럼 다시 호출해도 같은 결과인 것은 넣지 않는다.
RETRYABLE_CODES = {
    "01",  # 애플리케이션 에러
    "02",  # 데이터베이스 에러
    "04",  # HTTP 에러
    "05",  # 서비스 연결 실패
    "22",  # 서비스 요청 제한 횟수 초과
}

mcp = FastMCP("stock-mcp")


class StockError(RuntimeError):
    """data.go.kr가 resultCode로 돌려주는 오류."""


def _backoff(attempt: int) -> None:
    """attempt(0부터)에 따라 지터를 섞어 대기한다."""
    delay = min(BACKOFF_BASE * (2 ** attempt), BACKOFF_CAP)
    time.sleep(delay * (0.5 + random.random()))


def _call(operation: str, params: dict[str, Any]) -> dict:
    """data.go.kr API를 호출한다.

    네트워크 오류, HTTP 5xx/429, RETRYABLE_CODES 응답은 최대 MAX_ATTEMPTS회까지
    지수 백오프로 재시도한다.
    """
    if not API_KEY:
        raise StockError(
            "STOCK_API_KEY가 설정되지 않았습니다. Cloud Run에서는 "
            "--set-secrets=STOCK_API_KEY=STOCK_API_KEY:latest 로 주입하세요."
        )

    query = {k: str(v) for k, v in params.items() if v not in (None, "")}
    query.update({"serviceKey": API_KEY, "resultType": "json"})

    last_error: str | None = None
    payload = None
    for attempt in range(MAX_ATTEMPTS):
        if attempt:
            _backoff(attempt - 1)
        try:
            with httpx.Client(timeout=TIMEOUT) as client:
                resp = client.get(f"{BASE}/{operation}", params=query)
        except httpx.TransportError as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            continue

        if resp.status_code == 429 or resp.status_code >= 500:
            last_error = f"HTTP {resp.status_code}"
            continue
        resp.raise_for_status()

        try:
            payload = resp.json()
        except ValueError as exc:
            # 키가 잘못되면 XML 에러 문서가 온다.
            raise StockError(f"JSON이 아닌 응답: {resp.text[:200]}") from exc

        header = (payload.get("response") or {}).get("header") or {}
        code = str(header.get("resultCode", ""))
        if code and code != "00":
            known = RESULT_CODES.get(code)
            message = f"data.go.kr {code}: {known or header.get('resultMsg', '')}"
            if code in RETRYABLE_CODES:
                last_error = message
                continue
            raise StockError(message)
        break
    else:
        raise StockError(
            f"data.go.kr 호출이 {MAX_ATTEMPTS}회 모두 실패했습니다. 마지막 오류 — {last_error}"
        )

    body = (payload.get("response") or {}).get("body") or {}
    items = (body.get("items") or {}).get("item") or []
    if isinstance(items, dict):  # 결과가 1건이면 리스트가 아니라 객체로 온다
        items = [items]
    return {
        "total_count": body.get("totalCount"),
        "page_no": body.get("pageNo"),
        "num_of_rows": body.get("numOfRows"),
        "rows": items,
    }


def _price_args(
    item_name: str, item_name_like: str, isin_cd: str, short_code: str,
    base_date: str, begin_date: str, end_date: str, rows: int, page: int,
) -> dict:
    return {
        "itmsNm": item_name,
        "likeItmsNm": item_name_like,
        "isinCd": isin_cd,
        "likeSrtnCd": short_code,
        "basDt": base_date,
        "beginBasDt": begin_date,
        "endBasDt": end_date,
        "numOfRows": rows,
        "pageNo": page,
    }


@mcp.tool(annotations=READ_ONLY)
def get_stock_price(
    item_name: str = "",
    item_name_like: str = "",
    isin_cd: str = "",
    short_code: str = "",
    market: str = "",
    base_date: str = "",
    begin_date: str = "",
    end_date: str = "",
    rows: int = 20,
    page: int = 1,
) -> dict:
    """주식(주권) 시세를 조회한다. 이 서버의 핵심 도구다.

    KOSPI/KOSDAQ/KONEX 상장 주식의 일자별 종가·등락·거래량을 제공한다.
    조건을 하나도 주지 않으면 최신 일자부터 전체를 훑으므로, 종목이나 기간을
    반드시 지정하는 편이 좋다.

    종목명은 정확히 일치(item_name)와 부분 일치(item_name_like)가 다르다.
    "삼성전자"를 item_name_like로 주면 "삼성전자우"도 함께 나온다.

    Args:
        item_name: 종목명 정확 일치 (예: "삼성전자").
        item_name_like: 종목명 부분 일치 (예: "삼성" -> 삼성 계열 전부).
        isin_cd: ISIN 코드 12자리 (예: "KR7005930003").
        short_code: 단축코드 부분 일치 (예: "005930").
        market: 시장 구분 — "KOSPI", "KOSDAQ", "KONEX" 중 하나.
            주의: 상위 API가 알 수 없는 값을 **조용히 무시**한다. "NASDAQ" 같은
            값을 주면 오류 없이 필터가 적용되지 않은 결과가 돌아오므로,
            반환된 rows의 mrktCtg를 확인할 것.
        base_date: 기준일자 YYYYMMDD. 특정 하루만 볼 때.
        begin_date: 기간 조회 시작일 YYYYMMDD.
        end_date: 기간 조회 종료일 YYYYMMDD.
        rows: 페이지당 건수 (최대 권장 100).
        page: 페이지 번호.

    Returns:
        rows의 각 항목 — basDt(기준일), srtnCd(단축코드), isinCd, itmsNm(종목명),
        mrktCtg(시장), clpr(종가), vs(전일대비), fltRt(등락률), mkp(시가),
        hipr(고가), lopr(저가), trqu(거래량), trPrc(거래대금),
        lstgStCnt(상장주식수), mrktTotAmt(시가총액).
    """
    args = _price_args(item_name, item_name_like, isin_cd, short_code,
                       base_date, begin_date, end_date, rows, page)
    args["mrktCtg"] = market
    return _call("getStockPriceInfo", args)


@mcp.tool(annotations=READ_ONLY)
def get_fund_price(
    item_name: str = "",
    item_name_like: str = "",
    isin_cd: str = "",
    short_code: str = "",
    base_date: str = "",
    begin_date: str = "",
    end_date: str = "",
    rows: int = 20,
    page: int = 1,
) -> dict:
    """수익증권(공모펀드) 시세를 조회한다.

    실제 수록 종목은 자산운용사의 공모펀드 수익증권이다
    (예: "한투한미핵심성장포커스1(A)"). 일자당 100건 미만으로 적다.

    **ETF는 이 서비스에 없다.** KODEX/TIGER 같은 ETF는 get_stock_price에도
    get_fund_price에도 수록되지 않으므로, 요청받아도 여기서 찾지 말 것.

    파라미터 의미는 get_stock_price와 같고 시장구분(market)만 없다.

    Args:
        item_name: 종목명 정확 일치.
        item_name_like: 종목명 부분 일치 (예: "한투").
        isin_cd: ISIN 코드 12자리.
        short_code: 단축코드 부분 일치.
        base_date: 기준일자 YYYYMMDD.
        begin_date: 기간 조회 시작일 YYYYMMDD.
        end_date: 기간 조회 종료일 YYYYMMDD.
        rows: 페이지당 건수.
        page: 페이지 번호.
    """
    return _call("getSecuritiesPriceInfo",
                 _price_args(item_name, item_name_like, isin_cd, short_code,
                             base_date, begin_date, end_date, rows, page))


@mcp.tool(annotations=READ_ONLY)
def get_warrant_price(
    item_name: str = "",
    item_name_like: str = "",
    isin_cd: str = "",
    short_code: str = "",
    base_date: str = "",
    begin_date: str = "",
    end_date: str = "",
    rows: int = 20,
    page: int = 1,
) -> dict:
    """신주인수권증권 시세를 조회한다.

    신주인수권'증서'(get_subscription_right_price)와 다른 상품이다.
    증권은 워런트, 증서는 유상증자 시 배정되는 단기 청약권이다.

    Args:
        item_name: 종목명 정확 일치.
        item_name_like: 종목명 부분 일치.
        isin_cd: ISIN 코드 12자리.
        short_code: 단축코드 부분 일치.
        base_date: 기준일자 YYYYMMDD.
        begin_date: 기간 조회 시작일 YYYYMMDD.
        end_date: 기간 조회 종료일 YYYYMMDD.
        rows: 페이지당 건수.
        page: 페이지 번호.
    """
    return _call("getPreemptiveRightSecuritiesPriceInfo",
                 _price_args(item_name, item_name_like, isin_cd, short_code,
                             base_date, begin_date, end_date, rows, page))


@mcp.tool(annotations=READ_ONLY)
def get_subscription_right_price(
    item_name: str = "",
    item_name_like: str = "",
    isin_cd: str = "",
    short_code: str = "",
    base_date: str = "",
    begin_date: str = "",
    end_date: str = "",
    rows: int = 20,
    page: int = 1,
) -> dict:
    """신주인수권증서 시세를 조회한다.

    유상증자 시 기존 주주에게 배정되는 청약권으로, 상장 기간이 짧다.
    워런트(get_warrant_price)와 혼동하지 않는다.

    Args:
        item_name: 종목명 정확 일치.
        item_name_like: 종목명 부분 일치.
        isin_cd: ISIN 코드 12자리.
        short_code: 단축코드 부분 일치.
        base_date: 기준일자 YYYYMMDD.
        begin_date: 기간 조회 시작일 YYYYMMDD.
        end_date: 기간 조회 종료일 YYYYMMDD.
        rows: 페이지당 건수.
        page: 페이지 번호.
    """
    return _call("getPreemptiveRightCertificatePriceInfo",
                 _price_args(item_name, item_name_like, isin_cd, short_code,
                             base_date, begin_date, end_date, rows, page))


def _configure_transport_security() -> None:
    """DNS 리바인딩 보호 설정.

    MCP SDK는 기본적으로 Host 헤더를 localhost 계열로만 허용한다. Cloud Run에
    올리면 Host가 `<service>-<projectnumber>.<region>.run.app`이 되어
    `421 Invalid Host header`로 전부 거부되고, Gemini Enterprise 쪽에서는
    "도구 0개"로만 보여 원인을 찾기 어렵다.
    """
    hosts = [h.strip() for h in os.environ.get("MCP_ALLOWED_HOSTS", "").split(",") if h.strip()]
    if hosts:
        mcp.settings.transport_security = TransportSecuritySettings(
            allowed_hosts=hosts,
            allowed_origins=[f"https://{h}" for h in hosts],
        )
    elif os.environ.get("K_SERVICE"):  # Cloud Run이 주입하는 변수
        mcp.settings.transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=False
        )


if __name__ == "__main__":
    mcp.settings.host = "0.0.0.0"
    mcp.settings.port = int(os.environ.get("PORT", 8080))

    # Cloud Run은 요청을 여러 인스턴스에 분산하고 세션 어피니티가 기본 off다.
    # MCP StreamableHTTP는 기본이 stateful이라 initialize로 만든 세션이 특정
    # 인스턴스 메모리에만 존재하고, 다음 요청이 다른 인스턴스로 가면 세션을
    # 찾지 못한다. 그러면 클라이언트(Gemini Enterprise)는 도구를 호출하려다
    # 계속 실패·재시도하고, 로그에는 "Created new transport"가 반복되며
    # "Truncated response body" 타임아웃이 남는다.
    #
    # stateless 모드에서는 요청이 각자 완결되므로 인스턴스가 몇 개든 안전하다.
    mcp.settings.stateless_http = True

    _configure_transport_security()
    # Gemini Enterprise는 StreamableHTTP만 지원한다. SSE로 바꾸지 말 것.
    mcp.run(transport="streamable-http")
