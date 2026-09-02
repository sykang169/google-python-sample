"""ECOS MCP Server — 한국은행 경제통계시스템(ECOS) OpenAPI를 MCP 도구로 노출한다.

Gemini Enterprise의 Custom MCP Server 데이터 스토어가 소비할 수 있도록
StreamableHTTP 전송을 사용한다. (Gemini Enterprise는 레거시 SSE 전송을 지원하지 않는다.)

모든 도구는 조회 전용이므로 readOnlyHint를 달아 Gemini Enterprise에서
사용자 확인 프롬프트 없이 호출되게 한다.
"""

import os
import random
import time
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

ECOS_BASE = "https://ecos.bok.or.kr/api"
TIMEOUT = httpx.Timeout(30.0, connect=10.0)

# Cloud Run에서는 Secret Manager 값이 환경변수로 주입된다.
API_KEY = os.environ.get("ECOS_API_KEY", "")

# 조회 전용 도구에 공통으로 붙이는 annotation.
# readOnlyHint=True 이면 Gemini Enterprise가 호출 전 확인 단계를 건너뛴다.
READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True}

# 서버 단위 전제. MCP initialize 응답으로 나간다.
INSTRUCTIONS = """한국은행 ECOS 거시경제 시계열 — 기준금리·환율·물가·GDP·국고채 금리.

통계표가 약 840종이라 코드를 기억으로 지어내면 조용히 틀린 표를 읽는다.
search_statistic_tables로 먼저 코드를 확정한다. 개별 금융회사가 파는 예금·대출
금리는 이 서버가 아니라 FINLIFE에 있다."""

mcp = FastMCP("ecos-mcp", instructions=INSTRUCTIONS)


class EcosError(RuntimeError):
    """ECOS가 RESULT 블록으로 돌려주는 오류."""


# 재시도 정책. 한국 공공 API는 앞단에서 연결을 끊거나 일시적으로 스로틀하는
# 구간이 실제로 관측된다(주식 API에서 약 20분간 TCP 연결 거부 후 자체 복구).
# 지수 백오프 + 지터로 짧은 장애 구간을 넘긴다.
MAX_ATTEMPTS = 3
BACKOFF_BASE = 1.0
BACKOFF_CAP = 6.0

# ECOS 공식 명세의 오류 코드 중 재시도할 가치가 있는 것.
# INFO-200(데이터 없음)이나 ERROR-100(필수값 누락)처럼 재시도해도 같은 결과가
# 나오는 것은 넣지 않는다.
RETRYABLE_CODES = {
    "ERROR-500",  # 서버 오류
    "ERROR-600",  # DB Connection 오류
    "ERROR-601",  # SQL 오류
    "ERROR-602",  # 과도한 호출로 이용 제한
}


def _backoff(attempt: int) -> None:
    """attempt(0부터)에 따라 지터를 섞어 대기한다."""
    delay = min(BACKOFF_BASE * (2 ** attempt), BACKOFF_CAP)
    time.sleep(delay * (0.5 + random.random()))


def _call(*segments: str) -> Any:
    """ECOS API를 호출하고 payload를 반환한다.

    ECOS는 인증키를 쿼리스트링이 아니라 경로 세그먼트로 받는다.
    HTTP 200과 함께 {"RESULT": {"CODE": ..., "MESSAGE": ...}} 형태로
    오류를 돌려주므로 상태 코드만 보면 안 된다.

    네트워크 오류, HTTP 5xx/429, 그리고 RETRYABLE_CODES에 해당하는 응답은
    최대 MAX_ATTEMPTS회까지 지수 백오프로 재시도한다.
    """
    if not API_KEY:
        raise EcosError(
            "ECOS_API_KEY가 설정되지 않았습니다. "
            "Cloud Run에서는 --set-secrets=ECOS_API_KEY=ECOS_API_KEY:latest 로 주입하세요."
        )

    url = "/".join([ECOS_BASE, *(str(s) for s in segments)])

    last_error: str | None = None
    for attempt in range(MAX_ATTEMPTS):
        if attempt:
            _backoff(attempt - 1)
        try:
            with httpx.Client(timeout=TIMEOUT) as client:
                resp = client.get(url)
        except httpx.TransportError as exc:
            # 연결 실패/타임아웃 등. 다음 시도로 넘어간다.
            last_error = f"{type(exc).__name__}: {exc}"
            continue

        if resp.status_code == 429 or resp.status_code >= 500:
            last_error = f"HTTP {resp.status_code}"
            continue
        resp.raise_for_status()

        try:
            data = resp.json()
        except ValueError as exc:
            raise EcosError(
                f"ECOS가 JSON이 아닌 응답을 반환했습니다: {resp.text[:200]}") from exc

        # 오류는 200과 함께 RESULT 블록으로 온다.
        if isinstance(data, dict) and "RESULT" in data:
            result = data["RESULT"]
            code = str(result.get("CODE") or "")
            msg = result.get("MESSAGE")
            if code in RETRYABLE_CODES:
                last_error = f"ECOS {code}: {msg}"
                continue
            # 공식 명세의 오류 코드 중 호출자가 대응을 달리해야 하는 것들.
            hint = {
                "INFO-200": " (조건에 맞는 데이터 없음 — 기간/코드를 넓혀 다시 시도)",
                "ERROR-400": " (검색범위 초과로 60초 타임아웃 — 기간을 좁힐 것)",
            }.get(code, "")
            raise EcosError(f"ECOS {code}: {msg}{hint}")
        break
    else:
        raise EcosError(
            f"ECOS 호출이 {MAX_ATTEMPTS}회 모두 실패했습니다. 마지막 오류 — {last_error}"
        )

    # 정상 응답은 {"<서비스명>": {"list_total_count": N, "row": [...]}} 형태다.
    if isinstance(data, dict) and len(data) == 1:
        body = next(iter(data.values()))
        if isinstance(body, dict):
            return {
                "total_count": body.get("list_total_count"),
                "rows": body.get("row", []),
            }
    return data


@mcp.tool(annotations=READ_ONLY)
def list_key_statistics(start: int = 1, end: int = 100) -> dict:
    """한국은행이 선정한 100대 주요 경제지표의 최신값을 조회한다.

    환율, 기준금리, 소비자물가, GDP 등 대표 지표를 한 번에 훑을 때 쓴다.
    특정 지표의 시계열이 필요하면 search_statistic_tables로 통계표를 찾은 뒤
    get_statistic_series를 사용한다.

    Args:
        start: 조회 시작 순번 (1부터).
        end: 조회 종료 순번. start와의 차이가 곧 반환 건수다.
    """
    return _call("KeyStatisticList", API_KEY, "json", "kr", start, end)


@mcp.tool(annotations=READ_ONLY)
def search_statistic_tables(
    stat_name: str = "", stat_code: str = "", searchable_only: bool = True, limit: int = 50
) -> dict:
    """통계표를 이름으로 검색한다. 통계표 코드(stat_code)를 찾는 첫 단계다.

    ECOS의 StatisticTableList가 받는 마지막 경로 인자는 **통계표코드 정확 일치
    필터**이며 이름 검색이 아니다 (이름을 넣으면 INFO-200). 따라서 이름 검색은
    전체 목록 840건을 받아 이 서버에서 부분 문자열로 필터링한다.

    Args:
        stat_name: 통계표 이름에 포함된 검색어 (예: "예금금리", "환율").
            비우면 목록의 앞부분을 그대로 반환한다.
        stat_code: 통계표 코드를 정확히 알 때 그 한 건만 조회한다
            (예: "102Y004"). 지정하면 stat_name/searchable_only는 무시된다.
        searchable_only: True면 실제 시계열 조회가 가능한 통계표(SRCH_YN="Y")만
            반환한다. 상위 분류 항목까지 보려면 False로 준다.
        limit: 반환할 최대 건수.
    """
    if stat_code:
        return _call("StatisticTableList", API_KEY, "json", "kr", 1, 10, stat_code)

    # ECOS 통계표는 840건 남짓이라 한 번에 받아 필터링하는 편이 안전하다.
    data = _call("StatisticTableList", API_KEY, "json", "kr", 1, 1000)
    rows = data.get("rows", [])

    if searchable_only:
        rows = [r for r in rows if (r.get("SRCH_YN") or "").upper() == "Y"]
    if stat_name:
        rows = [r for r in rows if stat_name in (r.get("STAT_NAME") or "")]

    return {"total_count": len(rows), "rows": rows[:limit]}


@mcp.tool(annotations=READ_ONLY)
def list_statistic_items(stat_code: str, start: int = 1, end: int = 100) -> dict:
    """특정 통계표의 세부항목(item_code) 목록을 조회한다.

    get_statistic_series에 넘길 item_code1 후보를 여기서 얻는다. 응답의
    START_TIME / END_TIME / DATA_CNT로 각 항목의 수록 기간을 미리 알 수 있으므로,
    시계열을 조회하기 전에 기간을 맞추는 데 쓴다.

    Args:
        stat_code: 통계표 코드 (search_statistic_tables로 확인한 값, 예: "722Y001").
        start: 조회 시작 순번 (1부터).
        end: 조회 종료 순번.
    """
    return _call("StatisticItemList", API_KEY, "json", "kr", start, end, stat_code)


@mcp.tool(annotations=READ_ONLY)
def get_statistic_series(
    stat_code: str,
    cycle: str,
    start_period: str,
    end_period: str,
    item_code1: str = "",
    item_code2: str = "",
    item_code3: str = "",
    item_code4: str = "",
    start: int = 1,
    end: int = 100,
) -> dict:
    """통계 시계열 데이터를 조회한다. 이 서버의 핵심 도구다.

    stat_code는 search_statistic_tables로 먼저 확인한다.

    item_code1을 생략하면 그 통계표의 **모든 세부항목**을 반환한다
    (예: 722Y001 기준금리 표는 6건 -> 54건). 특정 항목만 원하면
    list_statistic_items로 코드를 확인해 지정한다.

    Args:
        stat_code: 통계표 코드 (예: "722Y001").
        cycle: 주기. "A"=연, "S"=반년, "Q"=분기, "M"=월, "SM"=반월, "D"=일.
        start_period: 조회 시작 시점. 주기에 맞춘 형식 —
            연 "2020", 반년 "2020S1", 분기 "2020Q1", 월 "202001",
            반월 "202001S1", 일 "20200101".
        end_period: 조회 종료 시점. start_period와 같은 형식.
        item_code1: 통계 세부항목 코드. **생략하면 전체 항목을 반환한다.**
        item_code2: 2차 세부항목 코드 (선택).
        item_code3: 3차 세부항목 코드 (선택).
        item_code4: 4차 세부항목 코드 (선택).
        start: 조회 시작 순번 (1부터).
        end: 조회 종료 순번.
    """
    segments = [
        "StatisticSearch", API_KEY, "json", "kr", start, end,
        stat_code, cycle, start_period, end_period,
    ]
    # ECOS는 순수 경로 기반이라 중간을 건너뛸 수 없다. 공식 명세의 테스트 URL은
    # 빈 자리에 "?"를 쓴다. 연속된 값만 덧붙이고, 중간이 비면 거기서 끊는다.
    for code in (item_code1, item_code2, item_code3, item_code4):
        if not code:
            break
        segments.append(code)
    return _call(*segments)


@mcp.tool(annotations=READ_ONLY)
def search_statistic_glossary(word: str, start: int = 1, end: int = 100) -> dict:
    """통계용어사전에서 용어의 정의를 조회한다.

    Args:
        word: 검색할 통계 용어 (예: "본원통화").
        start: 조회 시작 순번 (1부터).
        end: 조회 종료 순번.
    """
    return _call("StatisticWord", API_KEY, "json", "kr", start, end, word)


@mcp.tool(annotations=READ_ONLY)
def get_statistic_metadata(data_name: str, start: int = 1, end: int = 100) -> dict:
    """통계메타DB에서 통계의 작성 기준·출처 등 메타정보를 조회한다.

    Args:
        data_name: 메타DB 항목명 (예: "경제심리지수").
        start: 조회 시작 순번 (1부터).
        end: 조회 종료 순번.
    """
    return _call("StatisticMeta", API_KEY, "json", "kr", start, end, data_name)


def _configure_transport_security() -> None:
    """DNS 리바인딩 보호 설정.

    MCP SDK는 기본적으로 Host 헤더를 localhost 계열로만 허용한다. Cloud Run에
    올리면 Host가 `<service>-<projectnumber>.<region>.run.app`이 되어
    `421 Invalid Host header`로 전부 거부되고, Gemini Enterprise 쪽에서는
    "도구 0개"로만 보여 원인을 찾기 어렵다.

    - MCP_ALLOWED_HOSTS가 있으면 그 목록만 허용한다 (권장).
    - Cloud Run이면서 목록이 없으면 보호를 끈다. 이 보호는 브라우저 기반
      DNS 리바인딩을 막기 위한 것이고, 이 엔드포인트는 Gemini Enterprise가
      서버 대 서버로 호출하므로 해당 위협 모델이 아니다.
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
