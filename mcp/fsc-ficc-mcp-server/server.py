"""FSC 채권·단기자금 MCP Server — 금융위원회 공공데이터 채권·단기자금 계열.

채권 기본·발행·권리행사·권리일정, CP/CD 매매금리, 소매채권 수익률, 채무증권 발행실적(DCM)

설계
----
이 데스크가 다루는 API는 9종 / 오퍼레이션 31개다. 전부 도구로 펼치면
tools/list가 커져 다른 MCP 서버와 함께 붙일 때 컨텍스트를 잡아먹으므로,
자주 쓰는 경로만 이름 있는 도구로 내고 나머지는 search_apis + call_api로 연다.
(dart-mcp-server와 같은 점진적 공개 방식이다.)

search_apis는 오퍼레이션의 **응답 필드 목록**을 함께 준다. 금융위 API는 응답
필드명이 곧 필터 파라미터로 쓰이므로, 그 목록이 사실상 파라미터 명세다.
필드는 실제 호출로 수집한 것이라 문서와 어긋날 일이 없다.

주의: 거시 금리 지표(기준금리, 국고채 시장금리)는 이 서버가 아니라 한국은행 ECOS에 있다. 스프레드를 계산하려면 두 소스를 함께 써야 한다.

Gemini Enterprise 데이터 스토어가 소비할 수 있도록 StreamableHTTP를 쓴다.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

import fsc_core
from fsc_core import READ_ONLY, FscError

CATALOG = fsc_core.load_catalog('ficc')

# 서버 단위 전제. MCP initialize 응답으로 나가며, 도구 목록과 달리 매 호출
# 컨텍스트를 차지하지 않는다. 클라이언트가 이걸 모델에 넘기지 않을 수도 있어
# search_apis 설명에도 같은 문장을 넣어 둔다.
INSTRUCTIONS = """채권·단기자금 — 채권 기본·발행·권리행사·권리일정, CP/CD 매매금리, 소매채권 수익률, 채무증권 발행실적(DCM)

거시 금리 지표(기준금리, 국고채 시장금리)는 이 서버가 아니라 한국은행 ECOS에 있다. 스프레드를 계산하려면 두 소스를 함께 써야 한다."""

mcp = FastMCP('fsc-ficc-mcp', instructions=INSTRUCTIONS)


@mcp.tool(annotations=READ_ONLY)
def search_apis(query: str = "", limit: int = 8) -> dict:
    """이 서버가 다루는 API와 오퍼레이션을 찾는다. call_api 이전 단계다.

    이 서버의 전제: 거시 금리 지표(기준금리, 국고채 시장금리)는 이 서버가 아니라 한국은행 ECOS에 있다. 스프레드를 계산하려면 두 소스를 함께 써야 한다.

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
def get_bond_basic(params: dict | None = None, rows: int = 20, page: int = 1) -> dict:
    """채권 기본정보(마스터)를 조회한다. 종목 식별의 출발점이다.

    필터로 쓸 수 있는 필드(응답 필드와 같다):
        basDt, bnkHldyIntPydyDcd, bnkHldyIntPydyDcdNm, bondBal, bondExprDt, bondGrnInstNm, bondIntTcd, bondIntTcdNm, bondIssuAmt, bondIssuCurCd, bondIssuCurCdNm, bondIssuDt, bondIsurNm, bondOffrMcd, bondOffrMcdNm, bondPymtAmt, bondRegInstDcd, bondRegInstDcdNm, bondRnknDcd, bondRnknDcdNm, bondSrfcInrt, bondUndtInstNm, cpbdMngCmpyNm, cptUsgeDcd, cptUsgeDcdNm, crfndYn, crno, elpsIntPayYn, fnScrsItmsKcd, fnScrsItmsKcdNm, grnDcd, grnDcdNm, intCmpuMcd, intCmpuMcdNm, intPayCyclCtt, intPayMmntDcd, intPayMmntDcdNm, irtChngDcd, irtChngDcdNm, isinCd, isinCdNm, issuDptyNm, kbpScrsItmsKcd, kbpScrsItmsKcdNm, kisScrsItmsKcd, kisScrsItmsKcdNm, lstgDt, niceScrsItmsKcd, niceScrsItmsKcdNm, nxtmCopnDt, optnTcd, optnTcdNm, pamtRdptMcd, pamtRdptMcdNm, pclrBondKcd, pclrBondKcdNm, piamPayBrofNm, piamPayInstNm, prisLnkgBondYn, prmncBondTmnDt, prmncBondYn, qibTmnDt, qibTrgtScrtYn, rbfCopnDt, rgtExertMnbdDcd, rgtExertMnbdDcdNm, scrsItmsKcd, scrsItmsKcdNm, sicNm, stripsNm, stripsPsblYn, sttrHldyIntPydyDcd, sttrHldyIntPydyDcdNm, txtnDcd, txtnDcdNm

    Args:
        params: 필터 딕셔너리 (예: {"basDt": "20260831"}). 비우면 최신부터 반환한다.
        rows: 페이지당 건수 (최대 권장 100).
        page: 페이지 번호.
    """
    return fsc_core.call(CATALOG, 'GetBondIssuInfoService_V2', 'getBondBasiInfo_V2', params, rows, page)


@mcp.tool(annotations=READ_ONLY)
def get_bond_principal_interest(params: dict | None = None, rows: int = 20, page: int = 1) -> dict:
    """채권 원리금 정보를 조회한다. 캐시플로 산출의 근거.

    필터로 쓸 수 있는 필드(응답 필드와 같다):
        bondIssuCurCd, bondIssuCurCdNm, bondIsurNm, bondSrfcInrt, crno, hldyAplPiamPayDt, intPayAmt, isinCd, isinCdNm, pamtPayAmt, piamDcd, piamDcdNm, piamPayDt, rmanDpsgCnt, scrsItmsKcd, scrsItmsKcdNm, ttwBasInt

    Args:
        params: 필터 딕셔너리 (예: {"basDt": "20260831"}). 비우면 최신부터 반환한다.
        rows: 페이지당 건수 (최대 권장 100).
        page: 페이지 번호.
    """
    return fsc_core.call(CATALOG, 'GetBondTradInfoService_V2', 'getBondPrinAndInte_V2', params, rows, page)


@mcp.tool(annotations=READ_ONLY)
def get_bond_right_schedule(params: dict | None = None, rows: int = 20, page: int = 1) -> dict:
    """채권 권리행사 일정(이자지급·상환)을 조회한다.

    필터로 쓸 수 있는 필드(응답 필드와 같다):
        basDt, bondExprDt, bondIntTcd, bondIntTcdNm, bondIssuAmt, bondIssuDt, bondIssuFrmtNm, bondIsurNm, crno, irtChngDcd, irtChngDcdNm, isinCd, isinCdNm, scrsItmsKcd, scrsItmsKcdNm, scrsScedDcd, scrsScedDcdNm

    Args:
        params: 필터 딕셔너리 (예: {"basDt": "20260831"}). 비우면 최신부터 반환한다.
        rows: 페이지당 건수 (최대 권장 100).
        page: 페이지 번호.
    """
    return fsc_core.call(CATALOG, 'GetBondRighScheInfoService_V2', 'getBondRighExerSche_V2', params, rows, page)


@mcp.tool(annotations=READ_ONLY)
def get_bond_call_redemption(params: dict | None = None, rows: int = 20, page: int = 1) -> dict:
    """옵션부채권의 조기상환(콜) 내역을 조회한다. 콜 리스크 점검용.

    필터로 쓸 수 있는 필드(응답 필드와 같다):
        bondIssuAmt, bondIssuFrmtNm, crno, intCmpuMcd, intCmpuMcdNm, isinCd, isinCdNm, opbdClrdDt, opbdExprDt, opbdIntPayAmt, opbdIssuAmt, opbdIssuDt, opbdIsurNm, opbdPamtPayAmt, optnExertRto, optnTcd, optnTcdNm

    Args:
        params: 필터 딕셔너리 (예: {"basDt": "20260831"}). 비우면 최신부터 반환한다.
        rows: 페이지당 건수 (최대 권장 100).
        page: 페이지 번호.
    """
    return fsc_core.call(CATALOG, 'GetBondRedeInfoService_V2', 'getBondWithOptiCallRede_V2', params, rows, page)


@mcp.tool(annotations=READ_ONLY)
def get_retail_bond_yield(params: dict | None = None, rows: int = 20, page: int = 1) -> dict:
    """소매채권 수익률을 조회한다. 리테일 채권 판매에 바로 쓰이는 값이다.

    필터로 쓸 수 있는 필드(응답 필드와 같다):
        basDt, bnfRt, crdtSc, ctg

    Args:
        params: 필터 딕셔너리 (예: {"basDt": "20260831"}). 비우면 최신부터 반환한다.
        rows: 페이지당 건수 (최대 권장 100).
        page: 페이지 번호.
    """
    return fsc_core.call(CATALOG, 'GetBondInfoService', 'getBondSecurityBenefitRate', params, rows, page)


@mcp.tool(annotations=READ_ONLY)
def get_short_term_rate(params: dict | None = None, rows: int = 20, page: int = 1) -> dict:
    """단기금융증권(CP·CD)의 매매 금액·금리를 조회한다.

발행 정보가 아니라 **실거래** 기준이라 단기자금 운용의 체감 금리에 가깝다.

    필터로 쓸 수 있는 필드(응답 필드와 같다):
        basDt, rmngExprTrdAmt, shtrFinBzcDcd, shtrFinBzcDcdNm, shtrFinPrdDcd, shtrFinPrdDcdNm, shtrPrdRmngExprDcd, shtrPrdRmngExprDcdNm, stlSqno, trdDcd, trdDcdNm

    Args:
        params: 필터 딕셔너리 (예: {"basDt": "20260831"}). 비우면 최신부터 반환한다.
        rows: 페이지당 건수 (최대 권장 100).
        page: 페이지 번호.
    """
    return fsc_core.call(CATALOG, 'GetShorTermSecuTradInfoService_V2', 'getBuyAndSellAmou_V2', params, rows, page)


if __name__ == "__main__":
    fsc_core.run(mcp)
