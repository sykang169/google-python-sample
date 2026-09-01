"""FINLIFE MCP Server — 금융감독원 금융상품통합비교공시를 MCP 도구로 노출한다.

예금·적금·대출 상품의 **금융회사별 실제 판매 금리**를 조회한다.
한국은행 ECOS(기준금리 같은 거시 지표)와 다르고, 주식시세와도 무관하다.

설계상 핵심
-----------
FINLIFE API는 응답을 두 배열로 쪼개서 준다:

  baseList    상품 정보 (회사명, 상품명, 가입방법, 우대조건 …)
  optionList  조건별 금리 (예금은 기간별, 대출은 담보/상환방식별 …)

둘은 (fin_co_no, fin_prdt_cd)로 연결되는데, LLM에게 두 배열을 주고 조인하라고
하면 틀리기 쉽다. 이 서버가 조인해서 상품 하나에 금리 옵션이 붙은 형태로 돌려준다.

optionList의 스키마는 **상품군마다 다르다** — 예금/적금은 save_trm(기간),
주택담보대출은 mrtg_type(담보유형), 신용대출은 crdt_grad_*(신용등급별 금리).
그래서 도구를 상품군별로 나눴다.

Gemini Enterprise 데이터 스토어가 소비할 수 있도록 StreamableHTTP를 쓴다.
"""

from __future__ import annotations

import os
import random
import time
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

FINLIFE_BASE = "https://finlife.fss.or.kr/finlifeapi"
TIMEOUT = httpx.Timeout(30.0, connect=10.0)

API_KEY = os.environ.get("FINLIFE_API_KEY", "")

READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True}

# 금융권역 코드. 상품군에 따라 실제 데이터가 있는 권역이 다르다
# (예: 정기예금은 은행/저축은행에만 있고 보험·금융투자에는 없다).
FIN_GROUPS = {
    "은행": "020000",
    "여신전문": "030200",
    "저축은행": "030300",
    "보험": "050000",
    "금융투자": "060000",
}

# 재시도 정책. 다른 한국 공공 API와 마찬가지로 간헐적 지연이 있을 수 있다.
MAX_ATTEMPTS = 3
BACKOFF_BASE = 1.0
BACKOFF_CAP = 6.0

# FINLIFE 오류 코드 중 재시도할 가치가 있는 것.
RETRYABLE_CODES = {"900"}  # 기타 오류

mcp = FastMCP("finlife-mcp")


class FinlifeError(RuntimeError):
    """FINLIFE가 err_cd로 돌려주는 오류."""


def _backoff(attempt: int) -> None:
    delay = min(BACKOFF_BASE * (2 ** attempt), BACKOFF_CAP)
    time.sleep(delay * (0.5 + random.random()))


def _resolve_group(group: str) -> str:
    """한글 권역명 또는 코드를 코드로 정규화한다."""
    term = (group or "은행").strip()
    if term in FIN_GROUPS:
        return FIN_GROUPS[term]
    if term in FIN_GROUPS.values():
        return term
    raise FinlifeError(
        f"알 수 없는 금융권역 '{group}'. 가능한 값: "
        + ", ".join(f"{k}({v})" for k, v in FIN_GROUPS.items())
    )


def _call(operation: str, group_code: str, page: int) -> dict:
    """FINLIFE API를 호출한다.

    오류는 HTTP 200과 함께 result.err_cd로 온다. 상태 코드만 보면 안 된다.
    """
    if not API_KEY:
        raise FinlifeError(
            "FINLIFE_API_KEY가 설정되지 않았습니다. Cloud Run에서는 "
            "--set-secrets=FINLIFE_API_KEY=FINLIFE_API_KEY:latest 로 주입하세요."
        )
    params = {"auth": API_KEY, "topFinGrpNo": group_code, "pageNo": page}

    last_error: str | None = None
    for attempt in range(MAX_ATTEMPTS):
        if attempt:
            _backoff(attempt - 1)
        try:
            with httpx.Client(timeout=TIMEOUT) as client:
                resp = client.get(f"{FINLIFE_BASE}/{operation}", params=params)
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
            raise FinlifeError(f"JSON이 아닌 응답: {resp.text[:200]}") from exc

        result = payload.get("result") or {}
        code = str(result.get("err_cd", ""))
        if code and code != "000":
            message = f"FINLIFE {code}: {result.get('err_msg', '')}"
            if code in RETRYABLE_CODES:
                last_error = message
                continue
            raise FinlifeError(message)
        return result

    raise FinlifeError(
        f"FINLIFE 호출이 {MAX_ATTEMPTS}회 모두 실패했습니다. 마지막 오류 — {last_error}"
    )


def _join(result: dict, option_fields: list[str]) -> dict:
    """baseList와 optionList를 (fin_co_no, fin_prdt_cd)로 조인한다.

    상품 하나에 options 배열이 붙은 형태로 만들어, 호출하는 쪽이 두 배열을
    맞춰 볼 필요가 없게 한다.
    """
    options: dict[tuple, list[dict]] = {}
    for opt in result.get("optionList") or []:
        key = (opt.get("fin_co_no"), opt.get("fin_prdt_cd"))
        options.setdefault(key, []).append(
            {f: opt.get(f) for f in option_fields if opt.get(f) is not None}
        )

    products = []
    for base in result.get("baseList") or []:
        key = (base.get("fin_co_no"), base.get("fin_prdt_cd"))
        item = dict(base)
        item["options"] = options.get(key, [])
        products.append(item)

    # 공시월(dcls_month)은 result 최상위가 아니라 각 항목에 들어 있다.
    months = {p.get("dcls_month") for p in products if p.get("dcls_month")}

    return {
        "total_count": result.get("total_count"),
        "page_no": result.get("now_page_no"),
        "max_page_no": result.get("max_page_no"),
        # 공시 기준월(YYYYMM). 금융회사가 매월 제출하므로 최신 공시가 언제인지
        # 알려준다. 보통 한 값이지만 갱신 시점에 섞일 수 있어 목록으로 준다.
        "disclosure_months": sorted(months),
        "products": products,
    }


# ── 예금·적금 ───────────────────────────────────────────────────────────────

_SAVING_OPTS = [
    "intr_rate_type_nm",  # 단리/복리
    "save_trm",           # 저축 기간(개월)
    "intr_rate",          # 기본금리
    "intr_rate2",         # 최고우대금리
    "rsrv_type_nm",       # 적립유형(적금만: 정액적립식/자유적립식)
]


@mcp.tool(annotations=READ_ONLY)
def search_deposit_products(group: str = "은행", page: int = 1) -> dict:
    """정기예금 상품과 기간별 금리를 조회한다.

    "예금 금리 어디가 제일 높아" 같은 질문에 쓴다. 회사별 실제 판매 상품이며,
    한국은행 기준금리 같은 거시 지표가 아니다.

    각 상품의 options에 기간별 금리가 들어 있다:
      save_trm    저축 기간(개월). 보통 1/3/6/12/24/36
      intr_rate   기본금리(%)
      intr_rate2  최고우대금리(%) — 우대조건 충족 시. spcl_cnd 참고

    Args:
        group: 금융권역. "은행"(기본), "저축은행", "여신전문", "보험", "금융투자"
            또는 코드(020000 등). **정기예금은 은행·저축은행에만 있다.**
        page: 페이지 번호. 응답의 max_page_no로 전체 페이지 수를 알 수 있다.

    Returns:
        products의 각 항목 — kor_co_nm(회사명), fin_prdt_nm(상품명),
        join_way(가입방법), spcl_cnd(우대조건), mtrt_int(만기 후 금리),
        join_deny(가입제한 1:제한없음 2:서민전용 3:일부제한),
        etc_note(기타), max_limit(최고한도), options(기간별 금리).
    """
    return _join(_call("depositProductsSearch.json", _resolve_group(group), page),
                 _SAVING_OPTS)


@mcp.tool(annotations=READ_ONLY)
def search_savings_products(group: str = "은행", page: int = 1) -> dict:
    """적금 상품과 기간별 금리를 조회한다.

    정기예금(search_deposit_products)과 달리 매월 납입하는 상품이다.
    options의 rsrv_type_nm이 "정액적립식"/"자유적립식"을 구분한다.

    Args:
        group: 금융권역. "은행"(기본), "저축은행" 등.
        page: 페이지 번호.
    """
    return _join(_call("savingProductsSearch.json", _resolve_group(group), page),
                 _SAVING_OPTS)


# ── 대출 ────────────────────────────────────────────────────────────────────

_MORTGAGE_OPTS = [
    "mrtg_type_nm",       # 담보유형(아파트 등)
    "rpay_type_nm",       # 상환방식(분할상환/일시상환)
    "lend_rate_type_nm",  # 금리유형(고정/변동)
    "lend_rate_min", "lend_rate_max", "lend_rate_avg",
]

_RENT_OPTS = [
    "rpay_type_nm", "lend_rate_type_nm",
    "lend_rate_min", "lend_rate_max", "lend_rate_avg",
]


@mcp.tool(annotations=READ_ONLY)
def search_mortgage_loans(group: str = "은행", page: int = 1) -> dict:
    """주택담보대출 상품과 금리를 조회한다.

    options는 담보유형·상환방식·금리유형 조합별로 여러 건이 나온다:
      mrtg_type_nm       담보유형 (아파트 등)
      rpay_type_nm       상환방식 (분할상환방식 / 만기일시상환방식)
      lend_rate_type_nm  금리유형 (고정금리 / 변동금리)
      lend_rate_min/max/avg  최저·최고·평균 금리(%)

    Args:
        group: 금융권역. "은행"(기본), "저축은행" 등.
        page: 페이지 번호.

    Returns:
        products의 각 항목 — kor_co_nm, fin_prdt_nm, join_way,
        loan_inci_expn(대출부대비용), erly_rpay_fee(중도상환수수료),
        dly_rate(연체이자율), loan_lmt(대출한도), options.
    """
    return _join(_call("mortgageLoanProductsSearch.json", _resolve_group(group), page),
                 _MORTGAGE_OPTS)


@mcp.tool(annotations=READ_ONLY)
def search_rent_house_loans(group: str = "은행", page: int = 1) -> dict:
    """전세자금대출 상품과 금리를 조회한다.

    주택담보대출과 달리 담보유형(mrtg_type) 구분이 없다.

    Args:
        group: 금융권역. "은행"(기본), "저축은행" 등.
        page: 페이지 번호.
    """
    return _join(_call("rentHouseLoanProductsSearch.json", _resolve_group(group), page),
                 _RENT_OPTS)


@mcp.tool(annotations=READ_ONLY)
def search_credit_loans(group: str = "은행", page: int = 1) -> dict:
    """개인신용대출 상품과 **신용점수 구간별** 금리를 조회한다.

    다른 대출과 달리 options가 신용점수 구간별 금리로 구성된다.
    필드명의 숫자는 신용점수 구간을 뜻한다 (숫자가 클수록 높은 점수):

      crdt_grad_1   900점 초과
      crdt_grad_4   801~900점
      crdt_grad_5   701~800점
      crdt_grad_6   601~700점
      crdt_grad_10  501~600점
      crdt_grad_11  401~500점
      crdt_grad_12  301~400점
      crdt_grad_13  300점 이하
      crdt_grad_avg 평균 금리

    값이 없는 구간(None)은 그 회사가 해당 구간에 대출을 취급하지 않는다는 뜻이다.

    Args:
        group: 금융권역. "은행"(기본), "저축은행", "여신전문" 등.
        page: 페이지 번호.

    Returns:
        products의 각 항목 — kor_co_nm, fin_prdt_nm, crdt_prdt_type_nm(대출종류),
        cb_name(신용평가사), join_way, options(신용점수 구간별 금리).
    """
    return _join(
        _call("creditLoanProductsSearch.json", _resolve_group(group), page),
        ["crdt_lend_rate_type_nm", "crdt_grad_1", "crdt_grad_4", "crdt_grad_5",
         "crdt_grad_6", "crdt_grad_10", "crdt_grad_11", "crdt_grad_12",
         "crdt_grad_13", "crdt_grad_avg"],
    )


# ── 금융회사 ────────────────────────────────────────────────────────────────

@mcp.tool(annotations=READ_ONLY)
def list_financial_companies(group: str = "은행", page: int = 1) -> dict:
    """금융권역에 속한 금융회사 목록과 영업 지역을 조회한다.

    상품 조회 결과의 kor_co_nm이 어떤 회사인지, 어느 지역에서 영업하는지
    확인할 때 쓴다. options에 지역별 영업 여부가 들어 있다.

    권역별 회사 수(실측): 은행 18, 저축은행 80, 여신전문 48, 보험 20, 금융투자 7.

    Args:
        group: 금융권역. "은행"(기본), "저축은행", "여신전문", "보험", "금융투자".
        page: 페이지 번호.

    Returns:
        products의 각 항목 — kor_co_nm(회사명), homp_url(홈페이지),
        cal_tel(콜센터), dcls_chrg_man(공시담당자), options(area_nm 영업지역).
    """
    return _join(_call("companySearch.json", _resolve_group(group), page),
                 ["area_cd", "area_nm", "exis_yn"])


# ── 기동 ────────────────────────────────────────────────────────────────────

def _configure_transport_security() -> None:
    """DNS 리바인딩 보호 설정.

    Cloud Run은 서비스마다 호스트명을 두 개(프로젝트번호 형식, canonical 해시
    형식) 제공하는데 해시는 생성 전에 알 수 없다. 한쪽만 허용목록에 넣으면
    다른 쪽 요청이 421로 거부되고, Gemini Enterprise 쪽에서는 "도구 0개"로만
    보여 원인을 찾기 어렵다.
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
    # 찾지 못한다. stateless 모드에서는 요청이 각자 완결되므로 안전하다.
    mcp.settings.stateless_http = True

    _configure_transport_security()
    # Gemini Enterprise는 StreamableHTTP만 지원한다. SSE로 바꾸지 말 것.
    mcp.run(transport="streamable-http")
