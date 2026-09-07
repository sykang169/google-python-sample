"""FSC 상품·업계 MCP Server — 금융위원회 공공데이터 상품·업계 계열.

펀드 표준코드·판매현황, 퇴직연금, 증권사 경영지표·수수료 공시, 금투협 통계

설계
----
이 데스크가 다루는 API는 15종 / 오퍼레이션 76개다. 전부 도구로 펼치면
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
    """펀드 표준코드를 조회한다. 판매 상품 마스터이자 식별의 출발점.

설정일(setpDt)·유형(fndTp)·운용사 구분(ctg)이 있다.

**수익률·기준가·보수는 없다.** 여기는 코드와 속성만이다. 성과를
물으면 이 도구로는 답할 수 없다.

**같은 펀드의 클래스(A/C/S 등)가 각각 다른 코드다.** 이름만 보고
묶으면 클래스가 섞인다. 표준코드로 고정한다.

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
    """펀드 판매현황을 조회한다. 고객유형(개인/일반법인/금융법인)별 판매
잔액과 비중이다.

**개별 펀드가 아니라 집계다.** 펀드 이름도 표준코드도 없다. 특정
펀드의 판매액을 물으면 이 도구로는 답할 수 없다.

**분류가 코드로만 온다.** fundItemClsfCd·fundPtrnCd·ivsAreaClsfCd에
대응하는 이름 필드가 없어서 **코드가 무슨 유형인지 이 응답만으로는
알 수 없다.** 코드의 뜻을 지어내지 말고, 모르면 모른다고 밝히거나
search_apis로 같은 서비스의 다른 오퍼레이션을 확인한다.

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
    """증권사 일반현황(임직원·점포 등)을 조회한다.

같은 서비스의 다른 오퍼레이션은 이름과 내용이 어긋나므로 주의한다
(search_apis로 접근한다).
  getSecuCompFinaInfo    '재무현황'이지만 실제로는 **주석항목**이다
                         (채무보증·대차/대주·대손상각채권). 재무제표가 아니다
  getSecuCompKeyManaIndi '주요경영지표'지만 **유동성비율**만 들어 있다
  getSecuCompMajoBusiActi 금융투자상품 수탁수수료 항목별 실적

**증권사의 자기자본·순이익은 여기가 아니라 DART다.** 금융위 재무제표
API(GetFinaStatInfoService_V2)에는 증권사가 없어 0건이 나온다
(같은 키로 일반기업은 조회된다 — 권한이 아니라 수록 범위 문제다).
dart-mcp의 fnlttSinglAcnt로 가면 나온다.

    필터로 쓸 수 있는 필드(응답 필드와 같다):
        basYm, crno, fncoCd, fncoNm, xcsmCnt, xcsmDcd, xcsmDcdNm

    Args:
        params: 필터 딕셔너리 (예: {"basDt": "20260831"}). 비우면 최신부터 반환한다.
        rows: 페이지당 건수 (최대 권장 100).
        page: 페이지 번호.
    """
    return fsc_core.call(CATALOG, 'GetSecuCompInfoService', 'getSecuCompGeneInfo', params, rows, page)


@mcp.tool(annotations=READ_ONLY)
def get_bank_stats(params: dict | None = None, rows: int = 20, page: int = 1) -> dict:
    """국내은행 주요경영지표를 조회한다. BIS비율·연체율 같은 건전성 지표.

재무제표로는 보이지 않는 업권 지표다. 예금 금리를 비교할 때 그 은행이
어떤 상태인지 함께 봐야 하면 여기를 쓴다.
재무현황은 search_apis로 getDomeBankFinaInfo를 찾는다.

지표 이름은 cpaqItemDcdNm, 값은 cpaqItemClsfVal이다. **어느 지표를
볼지 정하지 않고 부르면 여러 지표가 섞여 온다.**

**은행만 있다.** 저축은행·증권·보험은 없다. 기준은 월(basYm)이라
일별 추이는 낼 수 없다.

    필터로 쓸 수 있는 필드(응답 필드와 같다):
        title, basYm, cpaqItemClsfVal, cpaqItemDcd, cpaqItemDcdNm, crno, fncoCd, fncoNm

    Args:
        params: 필터 딕셔너리 (예: {"basDt": "20260831"}). 비우면 최신부터 반환한다.
        rows: 페이지당 건수 (최대 권장 100).
        page: 페이지 번호.
    """
    return fsc_core.call(CATALOG, 'GetDomeBankInfoService', 'getDomeBankKeyManaIndi', params, rows, page)


@mcp.tool(annotations=READ_ONLY)
def get_brokerage_fee(params: dict | None = None, rows: int = 20, page: int = 1) -> dict:
    """증권사 주식거래 수수료 공시를 조회한다. 가격 경쟁 포지션 확인용.

**ctg로 먼저 거른다. 같은 cfe 필드에 금액과 비율이 섞여 있다.**
ctg='변경후'는 수수료 금액(원), ctg='변경율'은 변경 비율이다.
나누지 않고 정렬하면 수천 원과 0.00x를 한 줄에 놓게 된다.

**cfe가 null인 행이 절반 가까이 된다.** 그 채널 미제공이지
수수료 0이 아니다. 최저가로 읽지 않는다.

**trAmt는 금액이 아니라 구간 코드다.**
  100=10만원  150=50만원  200=100만원
  250=500만원 300=1000만원 350=1억원
trAmt를 만원 단위로 읽으면 요율 계산이 전부 틀린다.

**행마다 basDt가 다르다. 표 전체에 기준일 하나를 붙이지 않는다.**
회사가 수수료를 바꾼 날이 곧 basDt이고 회사마다 몇 년씩 벌어진다.
**회사별 최신 basDt를 각각 확인해** 그것만 남겨 비교하고, 공시일이
벌어진 사실을 먼저 밝힌다. 한 회사의 공시일을 표 전체 기준일로 적으면
몇 년 된 값이 현재 수수료로 제시된다.

채널은 brofOpnActCtg 값을 **그대로** 쓴다(증권사지점개설계좌 /
은행개설계좌 × 오프라인·HTS·스마트폰·ARS). '다이렉트'나 상품
브랜드명으로 바꾸지 않는다 — 데이터에 없는 구분이다.

**개설 경로만 보고 요약하지 않는다. 접속 수단까지 나눈다.**
같은 개설 경로 안에서도 접속 수단에 따라 요율이 10배까지 갈리는
회사가 있다(같은 은행개설계좌인데 HTS만 저율인 식이다).
'은행개설은 저율'처럼 뭉뚱그리면 스마트폰 이용자에게 틀린 안내가 된다.

요율을 요약할 때는 **구간별로 다른지 확인한다.** 한 구간 값으로
'정률'이라고 단정하지 않는다. 소액 구간만 다른 회사가 있어,
**구간별 요율을 모두 계산해 본 뒤** 판단한다.

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
    """금융투자협회 종합통계 중 **CMA 현황**을 조회한다. 운용대상
(mngInvTgt)과 투자자 구분(invrCtg)별 계좌수·잔액이다.

**이 도구는 CMA 하나만 감싼다.** 같은 서비스에 ELS/ELB, DLS/DLB,
펀드 순자산, 신탁 규모, 신용공여 잔고, 시가총액, 파생상품 거래
오퍼레이션이 따로 있다. **여기서 0건이 나온 것을 '통계가 없다'로
답하지 않는다** — search_apis로 해당 오퍼레이션을 찾아 call_api로
실행한다.

**증권사별이 아니라 업계 합계다.** 회사 수(scrtCmpyCnt)는 집계에
포함된 회사의 개수이지 특정 회사의 값이 아니다.

**이 서비스의 통계는 차원이 여러 겹이고 소계·합계 행이 같이 온다.**
구분 필드를 먼저 확인해 어느 축인지 정하고, 합계 행과 세부 행을
**함께 더하지 않는다** — 이중계상이 된다. 여러 축을 합쳐서 낼
때는 무엇을 합쳤는지 밝힌다.

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
