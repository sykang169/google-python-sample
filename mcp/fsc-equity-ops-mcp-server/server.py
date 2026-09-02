"""FSC 권리·대차 MCP Server — 금융위원회 공공데이터 권리·대차 계열.

주식 배당·권리일정·사고주권·발행, 주식/채권 대차, REPO 금리와 거래

설계
----
이 데스크가 다루는 API는 12종 / 오퍼레이션 31개다. 전부 도구로 펼치면
tools/list가 커져 다른 MCP 서버와 함께 붙일 때 컨텍스트를 잡아먹으므로,
자주 쓰는 경로만 이름 있는 도구로 내고 나머지는 search_apis + call_api로 연다.
(dart-mcp-server와 같은 점진적 공개 방식이다.)

search_apis는 오퍼레이션의 **응답 필드 목록**을 함께 준다. 금융위 API는 응답
필드명이 곧 필터 파라미터로 쓰이므로, 그 목록이 사실상 파라미터 명세다.
필드는 실제 호출로 수집한 것이라 문서와 어긋날 일이 없다.

주의: 권리업무와 백오피스 판단에 쓰는 데이터다. 사고주권 조회처럼 결과가 업무 처리를 가르는 것이 있으므로, 조회 실패를 '해당 없음'으로 답하지 않도록 주의한다.

Gemini Enterprise 데이터 스토어가 소비할 수 있도록 StreamableHTTP를 쓴다.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

import fsc_core
from fsc_core import READ_ONLY, FscError

CATALOG = fsc_core.load_catalog('equity-ops')

# 서버 단위 전제. MCP initialize 응답으로 나가며, 도구 목록과 달리 매 호출
# 컨텍스트를 차지하지 않는다. 클라이언트가 이걸 모델에 넘기지 않을 수도 있어
# search_apis 설명에도 같은 문장을 넣어 둔다.
INSTRUCTIONS = """권리·대차 — 주식 배당·권리일정·사고주권·발행, 주식/채권 대차, REPO 금리와 거래

권리업무와 백오피스 판단에 쓰는 데이터다. 사고주권 조회처럼 결과가 업무 처리를 가르는 것이 있으므로, 조회 실패를 '해당 없음'으로 답하지 않도록 주의한다."""

mcp = FastMCP('fsc-equity-ops-mcp', instructions=INSTRUCTIONS)


@mcp.tool(annotations=READ_ONLY)
def search_apis(query: str = "", limit: int = 8) -> dict:
    """이 서버가 다루는 API와 오퍼레이션을 찾는다. call_api 이전 단계다.

    이 서버의 전제: 권리업무와 백오피스 판단에 쓰는 데이터다. 사고주권 조회처럼 결과가 업무 처리를 가르는 것이 있으므로, 조회 실패를 '해당 없음'으로 답하지 않도록 주의한다.

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
def get_dividend(params: dict | None = None, rows: int = 20, page: int = 1) -> dict:
    """주식 배당정보(기준일·금액)를 조회한다. 배당락 처리와 고객 안내의 근거.

    필터로 쓸 수 있는 필드(응답 필드와 같다):
        basDt, cashDvdnPayDt, cashGrdnDvdnRt, crno, dvdnBasDt, isinCd, isinCdNm, scrsItmsKcd, scrsItmsKcdNm, stckDvdnRcd, stckDvdnRcdNm, stckGenrCashDvdnRt, stckGenrDvdnAmt, stckGenrDvdnRt, stckGrdnDvdnAmt, stckGrdnDvdnRt, stckHndvDt, stckIssuCmpyNm, stckParPrc, stckStacMd, trsnmDptyDcd, trsnmDptyDcdNm

    Args:
        params: 필터 딕셔너리 (예: {"basDt": "20260831"}). 비우면 최신부터 반환한다.
        rows: 페이지당 건수 (최대 권장 100).
        page: 페이지 번호.
    """
    return fsc_core.call(CATALOG, 'GetStocDiviInfoService_V2', 'getDiviInfo_V2', params, rows, page)


@mcp.tool(annotations=READ_ONLY)
def get_right_schedule(params: dict | None = None, rows: int = 20, page: int = 1) -> dict:
    """권리행사 사유별 일정을 조회한다. 청약·행사 업무의 달력.

    필터로 쓸 수 있는 필드(응답 필드와 같다):
        basDt, crno, issuCmpyKsdCustNo, nmlsLckEdDt, nmlsLckSttgDt, rgtExertEdDt, rgtExertRcd, rgtExertRcdNm, rgtExertSttgDt, scrsIssuMnbdCd, scrsIssuMnbdCdNm, stckIssuCmpyNm, stckIssuRcd, stckIssuRcdNm, stckParPrc, stckStacMd, trsnmDptyDcd, trsnmDptyDcdNm

    Args:
        params: 필터 딕셔너리 (예: {"basDt": "20260831"}). 비우면 최신부터 반환한다.
        rows: 페이지당 건수 (최대 권장 100).
        page: 페이지 번호.
    """
    return fsc_core.call(CATALOG, 'GetStocRighScheService_V2', 'getRighExerReasSche_V2', params, rows, page)


@mcp.tool(annotations=READ_ONLY)
def check_irregular_stock(params: dict | None = None, rows: int = 20, page: int = 1) -> dict:
    """사고주권 여부를 조회한다. 실물 입고 심사에서 확인이 필요한 항목이다.

**조회에 실패했을 때 '사고 없음'으로 답하지 않는다.** 실패는 실패로 보고한다.

    필터로 쓸 수 있는 필드(응답 필드와 같다):
        acdnRgscKindCnt, acdnScrtNo, acdnScrtNoClsfNm, basDt, crno, isinCd, isinCdNm, scrsDcd, scrsDcdNm, stckAcdnDcd, stckAcdnDcdNm, stckIssuCmpyNm, stckIssuSqno

    Args:
        params: 필터 딕셔너리 (예: {"basDt": "20260831"}). 비우면 최신부터 반환한다.
        rows: 페이지당 건수 (최대 권장 100).
        page: 페이지 번호.
    """
    return fsc_core.call(CATALOG, 'GetStocTradInfoService_V2', 'getIrreRigforSecu_V2', params, rows, page)


@mcp.tool(annotations=READ_ONLY)
def get_stock_lending(params: dict | None = None, rows: int = 20, page: int = 1) -> dict:
    """주식 대차 현황을 조회한다. 대차잔고는 공매도 압력의 대리지표로 읽히지만,
대차가 곧 공매도는 아니라는 점을 답변에 밝힌다.

    필터로 쓸 수 있는 필드(응답 필드와 같다):
        basDt, lnbBal, lnbCclAmt, lnbCclStckCnt, lnbExprItmsCnt, lnbRdptAmt, lnbRdptStckCnt, lnbRmanStckCnt

    Args:
        params: 필터 딕셔너리 (예: {"basDt": "20260831"}). 비우면 최신부터 반환한다.
        rows: 페이지당 건수 (최대 권장 100).
        page: 페이지 번호.
    """
    return fsc_core.call(CATALOG, 'GetStocLendBorrInfoService_V2', 'getMontLendAndBorrStatu_V2', params, rows, page)


@mcp.tool(annotations=READ_ONLY)
def get_repo_rate(params: dict | None = None, rows: int = 20, page: int = 1) -> dict:
    """REPO 금리를 조회한다. 단기 조달비용의 기준.

    필터로 쓸 수 있는 필드(응답 필드와 같다):
        basDt, purcBzcTcd, purcBzcTcdNm, rdptTermCcd, rdptTermCcdNm, rpBuyAplCurCd, rpBuyAplCurCdNm, rpBuyScrtKcd, rpBuyScrtKcdNm, rpInrt, rpRmngExprDcd, rpRmngExprDcdNm, rpSqno, slrBzcTcd, slrBzcTcdNm

    Args:
        params: 필터 딕셔너리 (예: {"basDt": "20260831"}). 비우면 최신부터 반환한다.
        rows: 페이지당 건수 (최대 권장 100).
        page: 페이지 번호.
    """
    return fsc_core.call(CATALOG, 'GetRepoItemInfoService_V2', 'getInteRateInfo_V2', params, rows, page)


if __name__ == "__main__":
    fsc_core.run(mcp)
