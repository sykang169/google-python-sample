"""FSC 상품·업계 MCP Server — 금융위원회 공공데이터 상품·업계 계열.

펀드 표준코드·판매현황, 퇴직연금, 증권사 경영지표·수수료 공시, 금투협 통계

설계
----
이 데스크가 다루는 API는 15종 / 오퍼레이션 52개다. 전부 도구로 펼치면
tools/list가 커져 다른 MCP 서버와 함께 붙일 때 컨텍스트를 잡아먹으므로,
자주 쓰는 경로만 이름 있는 도구로 내고 나머지는 search_apis + call_api로 연다.
(dart-mcp-server와 같은 점진적 공개 방식이다.)

search_apis는 오퍼레이션의 **응답 필드 목록**을 함께 준다. 금융위 API는 응답
필드명이 곧 필터 파라미터로 쓰이므로, 그 목록이 사실상 파라미터 명세다.
필드는 실제 호출로 수집한 것이라 문서와 어긋날 일이 없다.

주의: 자사와 경쟁사를 같은 잣대로 비교할 때 쓴다. 특정 회사를 유리하거나 불리하게 보이도록 지표를 골라 제시하지 않는다.

Gemini Enterprise 데이터 스토어가 소비할 수 있도록 StreamableHTTP를 쓴다.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

import fsc_core
from fsc_core import READ_ONLY, FscError

CATALOG = fsc_core.load_catalog('industry')

# 서버 단위 전제. MCP initialize 응답으로 나가며, 도구 목록과 달리 매 호출
# 컨텍스트를 차지하지 않는다. 클라이언트가 이걸 모델에 넘기지 않을 수도 있어
# search_apis 설명에도 같은 문장을 넣어 둔다.
INSTRUCTIONS = """상품·업계 — 펀드 표준코드·판매현황, 퇴직연금, 증권사 경영지표·수수료 공시, 금투협 통계

자사와 경쟁사를 같은 잣대로 비교할 때 쓴다. 특정 회사를 유리하거나 불리하게 보이도록 지표를 골라 제시하지 않는다."""

mcp = FastMCP('fsc-industry-mcp', instructions=INSTRUCTIONS)


@mcp.tool(annotations=READ_ONLY)
def search_apis(query: str = "", limit: int = 8) -> dict:
    """이 서버가 다루는 API와 오퍼레이션을 찾는다. call_api 이전 단계다.

    이 서버의 전제: 자사와 경쟁사를 같은 잣대로 비교할 때 쓴다. 특정 회사를 유리하거나 불리하게 보이도록 지표를 골라 제시하지 않는다.

    이름 있는 도구로 나와 있지 않은 데이터가 필요할 때 여기서 먼저 찾는다.
    반환되는 fields가 그 오퍼레이션의 응답 필드이자 **필터 파라미터 후보**다
    (예: basDt로 기준일, itmsNm으로 종목명, likeItmsNm으로 부분 일치).

    Args:
        query: 검색어. 한글 API명, 영문 오퍼레이션명, 응답 필드명에 부분 일치시킨다
            (예: "채권", "배당", "basDt", "ETF"). 비우면 전체 목록을 반환한다.
        limit: 최대 반환 건수.

    Returns:
        rows: [{service, operation, api_name, purpose, fields, approx_total_rows}]
    """
    return fsc_core.search(CATALOG, query, limit)


@mcp.tool(annotations=READ_ONLY)
def call_api(
    service: str,
    operation: str,
    params: dict | None = None,
    rows: int = 20,
    page: int = 1,
) -> dict:
    """search_apis로 찾은 오퍼레이션을 실행한다.

    인증키는 서버가 넣으므로 params에 포함하지 않는다.
    params의 키는 search_apis가 알려준 fields 중에서 고른다.

    자주 쓰는 필터:
        basDt        기준일자 YYYYMMDD (하루)
        beginBasDt / endBasDt   기간 조회
        itmsNm       종목명 정확 일치 / likeItmsNm  부분 일치
        isinCd       ISIN 12자리 (가장 정확)
        crno         법인등록번호 (기업 정보 계열)

    Args:
        service: 서비스명 (예: "GetStockSecuritiesInfoService").
        operation: 오퍼레이션명 (예: "getStockPriceInfo").
        params: 필터 딕셔너리. 없으면 최신 데이터부터 반환된다.
        rows: 페이지당 건수 (최대 권장 100).
        page: 페이지 번호.

    Returns:
        total_count, page_no, num_of_rows, rows
    """
    return fsc_core.call(CATALOG, service, operation, params, rows, page)


@mcp.tool(annotations=READ_ONLY)
def get_fund_code(params: dict | None = None, rows: int = 20, page: int = 1) -> dict:
    """펀드 표준코드를 조회한다. 판매 상품 마스터.

    필터로 쓸 수 있는 필드(응답 필드와 같다):
        asoStdCd, basDt, ctg, fndNm, fndTp, prdClsfCd, setpDt, srtnCd

    Args:
        params: 필터 딕셔너리 (예: {"basDt": "20260831"}). 비우면 최신부터 반환한다.
        rows: 페이지당 건수 (최대 권장 100).
        page: 페이지 번호.
    """
    return fsc_core.call(CATALOG, 'GetFundProductInfoService', 'getStandardCodeInfo', params, rows, page)


@mcp.tool(annotations=READ_ONLY)
def get_fund_sales(params: dict | None = None, rows: int = 20, page: int = 1) -> dict:
    """펀드 판매현황을 조회한다. 판매기관·고객유형·펀드유형별 점유율을 본다.

    필터로 쓸 수 있는 필드(응답 필드와 같다):
        basDt, corpCustTrprSleBalStot, finCorpCustTrprSleBal, finCorpCustTrprSleRipt, fundItemClsfCd, fundPtrnCd, fundSleBalSum, genCorpCustTrprSleBal, genCorpCustTrprSleRipt, idvpnCustTrprSleBal, idvpnCustTrprSleRipt, ivsAreaClsfCd

    Args:
        params: 필터 딕셔너리 (예: {"basDt": "20260831"}). 비우면 최신부터 반환한다.
        rows: 페이지당 건수 (최대 권장 100).
        page: 페이지 번호.
    """
    return fsc_core.call(CATALOG, 'GetFdSaleInfoService_V2', 'getCustFundSaleInfo_V2', params, rows, page)


@mcp.tool(annotations=READ_ONLY)
def get_securities_firm_stats(params: dict | None = None, rows: int = 20, page: int = 1) -> dict:
    """증권사 일반현황을 조회한다. 재무·경영지표는 search_apis로 같은 서비스의
다른 오퍼레이션을 찾는다.

    필터로 쓸 수 있는 필드(응답 필드와 같다):
        basYm, crno, fncoCd, fncoNm, xcsmCnt, xcsmDcd, xcsmDcdNm

    Args:
        params: 필터 딕셔너리 (예: {"basDt": "20260831"}). 비우면 최신부터 반환한다.
        rows: 페이지당 건수 (최대 권장 100).
        page: 페이지 번호.
    """
    return fsc_core.call(CATALOG, 'GetSecuCompInfoService', 'getSecuCompGeneInfo', params, rows, page)


@mcp.tool(annotations=READ_ONLY)
def get_brokerage_fee(params: dict | None = None, rows: int = 20, page: int = 1) -> dict:
    """증권사 주식거래 수수료 공시를 조회한다. 가격 경쟁 포지션 확인용.

    필터로 쓸 수 있는 필드(응답 필드와 같다):
        basDt, brofOpnActCtg, bzds, cfe, cmpyNm, ctg, trAmt

    Args:
        params: 필터 딕셔너리 (예: {"basDt": "20260831"}). 비우면 최신부터 반환한다.
        rows: 페이지당 건수 (최대 권장 100).
        page: 페이지 번호.
    """
    return fsc_core.call(CATALOG, 'GetOfficialNoticeInfoService', 'getStockTradingFeeInfo', params, rows, page)


@mcp.tool(annotations=READ_ONLY)
def get_kofia_stat(params: dict | None = None, rows: int = 20, page: int = 1) -> dict:
    """금융투자협회 종합통계를 조회한다. CMA 잔고 외에 펀드 순자산·신탁 규모 등은
search_apis로 같은 서비스의 다른 오퍼레이션을 찾는다.

    필터로 쓸 수 있는 필드(응답 필드와 같다):
        actBal, actCnt, basDt, invrCtg, mngInvTgt, scrtCmpyCnt

    Args:
        params: 필터 딕셔너리 (예: {"basDt": "20260831"}). 비우면 최신부터 반환한다.
        rows: 페이지당 건수 (최대 권장 100).
        page: 페이지 번호.
    """
    return fsc_core.call(CATALOG, 'GetKofiaStatisticsInfoService', 'getCMAStatus', params, rows, page)


if __name__ == "__main__":
    fsc_core.run(mcp)
