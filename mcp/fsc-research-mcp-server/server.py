"""FSC 기업분석·공시 MCP Server — 금융위원회 공공데이터 기업분석·공시 계열.

기업 개요·계열사·종속기업, 정규화 재무제표, 공시 32종, 지배구조, ESG 지수

설계
----
이 데스크가 다루는 API는 7종 / 오퍼레이션 48개다. 전부 도구로 펼치면
tools/list가 커져 다른 MCP 서버와 함께 붙일 때 컨텍스트를 잡아먹으므로,
자주 쓰는 경로만 이름 있는 도구로 내고 나머지는 search_apis + call_api로 연다.
(dart-mcp-server와 같은 점진적 공개 방식이다.)

search_apis는 오퍼레이션의 **응답 필드 목록**을 함께 준다. 금융위 API는 응답
필드명이 곧 필터 파라미터로 쓰이므로, 그 목록이 사실상 파라미터 명세다.
필드는 실제 호출로 수집한 것이라 문서와 어긋날 일이 없다.

주의: DART(전자공시)와 겹치는 영역이 있다. 이 서버는 정규화된 표 형태라 계산에 바로 쓰기 좋고, 원문 공시 전문이나 XBRL이 필요하면 DART 쪽을 쓴다.

Gemini Enterprise 데이터 스토어가 소비할 수 있도록 StreamableHTTP를 쓴다.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

import fsc_core
from fsc_core import READ_ONLY, FscError

CATALOG = fsc_core.load_catalog('research')

# 서버 단위 전제. MCP initialize 응답으로 나가며, 도구 목록과 달리 매 호출
# 컨텍스트를 차지하지 않는다. 클라이언트가 이걸 모델에 넘기지 않을 수도 있어
# search_apis 설명에도 같은 문장을 넣어 둔다.
INSTRUCTIONS = """기업분석·공시 — 기업 개요·계열사·종속기업, 정규화 재무제표, 공시 32종, 지배구조, ESG 지수

DART(전자공시)와 겹치는 영역이 있다. 이 서버는 정규화된 표 형태라 계산에 바로 쓰기 좋고, 원문 공시 전문이나 XBRL이 필요하면 DART 쪽을 쓴다."""

mcp = FastMCP('fsc-research-mcp', instructions=INSTRUCTIONS)


@mcp.tool(annotations=READ_ONLY)
def search_apis(query: str = "", limit: int = 8) -> dict:
    """이 서버가 다루는 API와 오퍼레이션을 찾는다. call_api 이전 단계다.

    이 서버의 전제: DART(전자공시)와 겹치는 영역이 있다. 이 서버는 정규화된 표 형태라 계산에 바로 쓰기 좋고, 원문 공시 전문이나 XBRL이 필요하면 DART 쪽을 쓴다.

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
def get_financial_statement(params: dict | None = None, rows: int = 20, page: int = 1) -> dict:
    """재무상태표를 조회한다. DART XBRL 파싱 없이 정규화된 계정 값을 받는다.

손익계산서와 요약재무제표는 search_apis로 같은 서비스의 다른 오퍼레이션을 찾는다.
법인등록번호(crno)와 사업연도(bizYear)로 거르는 것이 보통이다.

**금융회사(은행·증권·보험)는 여기 없다.** 0건이 나오면 권한 문제가 아니라
수록 범위 밖이라는 뜻이다. 그때는 dart-mcp의 fnlttSinglAcnt로 간다.

    필터로 쓸 수 있는 필드(응답 필드와 같다):
        acitId, acitNm, basDt, bizYear, bpvtrAcitAmt, crno, crtmAcitAmt, curCd, fnclDcd, fnclDcdNm, lsqtAcitAmt, pvtrAcitAmt, thqrAcitAmt

    Args:
        params: 필터 딕셔너리 (예: {"basDt": "20260831"}). 비우면 최신부터 반환한다.
        rows: 페이지당 건수 (최대 권장 100).
        page: 페이지 번호.
    """
    return fsc_core.call(CATALOG, 'GetFinaStatInfoService_V2', 'getBs_V2', params, rows, page)


@mcp.tool(annotations=READ_ONLY)
def get_corp_outline(params: dict | None = None, rows: int = 20, page: int = 1) -> dict:
    """기업 개요를 조회한다. 법인등록번호(crno) 확정의 출발점.

설립일·상장일·종업원수·대표자·업종이 있다. **재무 수치는 없다** —
get_financial_statement를 쓴다.

**상장사만 있는 게 아니다.** 외국 법인과 비상장이 함께 들어 있어
회사명으로 찾으면 의도하지 않은 법인이 먼저 나올 수 있다. 돌아온
행의 corpNm을 확인하고 crno로 대상을 고정한다.

    필터로 쓸 수 있는 필드(응답 필드와 같다):
        actnAudpnNm, audtRptOpnnCtt, bzno, corpDcd, corpDcdNm, corpEnsnNm, corpNm, corpRegMrktDcd, corpRegMrktDcdNm, crno, empeAvgCnwkTermCtt, enpBsadr, enpDtadr, enpEmpeCnt, enpEstbDt, enpFxno, enpHmpgUrl, enpKosdaqLstgAbolDt, enpKosdaqLstgDt, enpKrxLstgAbolDt, enpKrxLstgDt, enpMainBizNm, enpMntrBnkNm, enpOzpno, enpPbanCmpyNm, enpPn1AvgSlryAmt, enpRprFnm, enpStacMm, enpTlno, enpXchgLstgAbolDt, enpXchgLstgDt, fssCorpChgDtm, fssCorpUnqNo, fstOpegDt, lastOpegDt, sicNm, smenpYn

    Args:
        params: 필터 딕셔너리 (예: {"basDt": "20260831"}). 비우면 최신부터 반환한다.
        rows: 페이지당 건수 (최대 권장 100).
        page: 페이지 번호.
    """
    return fsc_core.call(CATALOG, 'GetCorpBasicInfoService_V2', 'getCorpOutline_V2', params, rows, page)


@mcp.tool(annotations=READ_ONLY)
def get_affiliates(params: dict | None = None, rows: int = 20, page: int = 1) -> dict:
    """계열회사 목록을 조회한다. 지배구조 맵을 그릴 때 쓴다.
crno로 걸어야 그 기업의 계열사가 나온다.

**지분율은 없다.** 계열사 이름·법인번호·상장여부(lstgYn)뿐이라
지배구조의 모양은 알 수 없다. '지분 몇 %'를 물으면 이 도구로는
답할 수 없다고 말한다.

**계열사 이름이 상장 종목명과 다르다.** 시세로 넘기기 전에
find_listed_item으로 대조한다.

    필터로 쓸 수 있는 필드(응답 필드와 같다):
        afilCmpyCrno, afilCmpyNm, basDt, crno, lstgYn

    Args:
        params: 필터 딕셔너리 (예: {"basDt": "20260831"}). 비우면 최신부터 반환한다.
        rows: 페이지당 건수 (최대 권장 100).
        page: 페이지 번호.
    """
    return fsc_core.call(CATALOG, 'GetCorpBasicInfoService_V2', 'getAffiliate_V2', params, rows, page)


@mcp.tool(annotations=READ_ONLY)
def get_executives(params: dict | None = None, rows: int = 20, page: int = 1) -> dict:
    """임원 현황을 조회한다. 사외이사 수 같은 지배구조 질문의 근거.
crno로 거른다.

**행을 세는 것은 서버가 한다.** 응답의 건수와 범주 분포를 쓰고,
JSON을 직접 세지 않는다.

**보수는 없다.** search_apis로 getExecRemuStat(임원 보수 통계)을,
주주 현황은 getStockholderInfo를 찾아 call_api한다.

**오래된 기준일 행은 대부분 공란이다.** 이름·직위가 비어 있으면
임원이 없는 게 아니라 그 시점 수록이 비어 있는 것이다. 최신 basDt를
먼저 확인하고 그 시점으로 거른다.

    필터로 쓸 수 있는 필드(응답 필드와 같다):
        basDt, crno, dataSqno, exutFnm, exutBornYm, exutJbttNm, rgstExutYn, rgstExutCtt, fltmsvYn, fltmsvCtt, exutChrgBzwrNm, exutMainCrrCtt, ownOnskCnt, ownPfstCnt, exutHdfTermCtt, exutJbttXpryDt, sexCd, sexCdNm, exutOwnOnskCnt, exutOwnPfstCnt

    Args:
        params: 필터 딕셔너리 (예: {"basDt": "20260831"}). 비우면 최신부터 반환한다.
        rows: 페이지당 건수 (최대 권장 100).
        page: 페이지 번호.
    """
    return fsc_core.call(CATALOG, 'GetCorpGoveInfoService', 'getExecutivesInfo', params, rows, page)


@mcp.tool(annotations=READ_ONLY)
def get_dividend_disclosure(params: dict | None = None, rows: int = 20, page: int = 1) -> dict:
    """**배당 공시만** 조회한다. 공시 일반이 아니다.

이 서비스에는 유상증자·합병·자기주식·소송 등 30종이 넘는 공시
오퍼레이션이 있고 이 도구는 그중 배당 하나만 감싼다. 다른 공시를
물으면 search_apis로 해당 오퍼레이션을 찾아 call_api로 실행한다.
**여기서 0건이 나온 것을 '공시가 없다'로 답하지 않는다.**

당기·전기·전전기 세 시점이 crtm/pvtr/bpvtr 접두사로 한 행에 함께 온다.
접두사를 확인하지 않으면 전기 값을 당기로 답하게 된다.

배당 기준일·지급일 같은 권리 일정은 여기가 아니라 fsc-equity-ops의
get_dividend다. 공시 **원문 본문**은 DART 서버를 쓴다.

    필터로 쓸 수 있는 필드(응답 필드와 같다):
        basDt, bpvtrCashDvdnTndnCtt, bpvtrCashTdvdAmt, bpvtrIdvCrtmNpf, bpvtrOnskCashDvdnAmt, bpvtrOnskCashDvdnBnfRt, bpvtrOnskStckDvdnAmt, bpvtrOnskStckDvdnBnfRt, bpvtrParPrc, bpvtrPfstCashDvdnAmt, bpvtrPfstCashDvdnBnfRt, bpvtrPfstStckDvdnAmt, bpvtrPfstStckDvdnBnfRt, bpvtrPstcNpf, bpvtrStckTdvdAmt, crno, crtmCashDvdnTndnCtt, crtmCashTdvdAmt, crtmIdvCrtmNpf, crtmOnskCashDvdnAmt, crtmOnskCashDvdnBnfRt, crtmOnskStckDvdnAmt, crtmOnskStckDvdnBnfRt, crtmParPrc, crtmPfstCashDvdnAmt, crtmPfstCashDvdnBnfRt, crtmPfstStckDvdnAmt, crtmPfstStckDvdnBnfRt, crtmPstcNpf, crtmStckTdvdAmt, enpCrtmNpf, fnclCrtmNpf, pvtrCashDvdnTndnCtt, pvtrCashTdvdAmt, pvtrCrtmNpf, pvtrIdvCrtmNpf, pvtrOnskCashDvdnAmt, pvtrOnskCashDvdnBnfRt, pvtrOnskStckDvdnAmt, pvtrOnskStckDvdnBnfRt, pvtrParPrc, pvtrPfstCashDvdnAmt, pvtrPfstCashDvdnBnfRt, pvtrPfstStckDvdnAmt, pvtrPfstStckDvdnBnfRt, pvtrPstcNpf, pvtrStckTdvdAmt

    Args:
        params: 필터 딕셔너리 (예: {"basDt": "20260831"}). 비우면 최신부터 반환한다.
        rows: 페이지당 건수 (최대 권장 100).
        page: 페이지 번호.
    """
    return fsc_core.call(CATALOG, 'GetDiscInfoService_V2', 'getDiviDiscInfo_V2', params, rows, page)


if __name__ == "__main__":
    fsc_core.run(mcp)
