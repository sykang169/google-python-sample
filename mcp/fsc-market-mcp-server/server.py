"""FSC 시세 통합 MCP Server — 금융위원회 공공데이터 시세 통합 계열.

주식·지수·채권·ETF/ETN/ELW·선물·일반상품(금·석유·배출권) 일별 확정시세와 KRX 상장종목 마스터

설계
----
이 데스크가 다루는 API는 7종 / 오퍼레이션 16개다. 전부 도구로 펼치면
tools/list가 커져 다른 MCP 서버와 함께 붙일 때 컨텍스트를 잡아먹으므로,
자주 쓰는 경로만 이름 있는 도구로 내고 나머지는 search_apis + call_api로 연다.
(dart-mcp-server와 같은 점진적 공개 방식이다.)

search_apis는 오퍼레이션의 **응답 필드 목록**을 함께 준다. 금융위 API는 응답
필드명이 곧 필터 파라미터로 쓰이므로, 그 목록이 사실상 파라미터 명세다.
필드는 실제 호출로 수집한 것이라 문서와 어긋날 일이 없다.

주의: 장중 시세가 아니다. 기준일 다음 영업일 13시 이후에 갱신되는 확정 시세다.

Gemini Enterprise 데이터 스토어가 소비할 수 있도록 StreamableHTTP를 쓴다.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

import fsc_core
from fsc_core import READ_ONLY, FscError

CATALOG = fsc_core.load_catalog('market')

# 서버 단위 전제. MCP initialize 응답으로 나가며, 도구 목록과 달리 매 호출
# 컨텍스트를 차지하지 않는다. 클라이언트가 이걸 모델에 넘기지 않을 수도 있어
# search_apis 설명에도 같은 문장을 넣어 둔다.
INSTRUCTIONS = """시세 통합 — 주식·지수·채권·ETF/ETN/ELW·선물·일반상품(금·석유·배출권) 일별 확정시세와 KRX 상장종목 마스터

장중 시세가 아니다. 기준일 다음 영업일 13시 이후에 갱신되는 확정 시세다."""

mcp = FastMCP('fsc-market-mcp', instructions=INSTRUCTIONS)


@mcp.tool(annotations=READ_ONLY)
def search_apis(query: str = "", limit: int = 8) -> dict:
    """이 서버가 다루는 API와 오퍼레이션을 찾는다. call_api 이전 단계다.

    이 서버의 전제: 장중 시세가 아니다. 기준일 다음 영업일 13시 이후에 갱신되는 확정 시세다.

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
def get_stock_price(params: dict | None = None, rows: int = 20, page: int = 1) -> dict:
    """주식(주권) 일별 시세를 조회한다. KOSPI/KOSDAQ/KONEX 상장 주식.

종목명 정확 일치는 itmsNm, 부분 일치는 likeItmsNm이다. 우선주가 섞이는 것을
막으려면 isinCd로 고정하는 편이 안전하다.
**ETF·ETN·ELW는 여기 없다.** get_etf_price를 쓴다.

    필터로 쓸 수 있는 필드(응답 필드와 같다):
        basDt, clpr, fltRt, hipr, isinCd, itmsNm, lopr, lstgStCnt, mkp, mrktCtg, mrktTotAmt, srtnCd, trPrc, trqu, vs

    Args:
        params: 필터 딕셔너리 (예: {"basDt": "20260831"}). 비우면 최신부터 반환한다.
        rows: 페이지당 건수 (최대 권장 100).
        page: 페이지 번호.
    """
    return fsc_core.call(CATALOG, 'GetStockSecuritiesInfoService', 'getStockPriceInfo', params, rows, page)


@mcp.tool(annotations=READ_ONLY)
def get_market_index(params: dict | None = None, rows: int = 20, page: int = 1) -> dict:
    """주가지수 시세를 조회한다. KOSPI/KOSDAQ 대표지수와 섹터지수를 모두 담는다.

idxNm으로 지수명, idxCsf로 계열(KOSPI시리즈/KOSDAQ시리즈)을 거른다.
개별 종목의 초과수익률을 낼 때 이 값이 벤치마크가 된다.

**같은 이름의 지수가 계열마다 따로 있다.** idxCsf를 고정하지 않으면
KOSPI 계열과 KOSDAQ 계열이 한 시계열에 섞인다.

**구성종목은 없다.** 편입종목 수(epyItmsCnt)만 있고 어떤 종목인지는
이 데이터에 없다. 지수에 무엇이 들어 있는지 물으면 답할 수 없다.

    필터로 쓸 수 있는 필드(응답 필드와 같다):
        basDt, basIdx, basPntm, clpr, epyItmsCnt, fltRt, hipr, idxCsf, idxNm, lopr, lsYrEdVsFltRg, lsYrEdVsFltRt, lstgMrktTotAmt, mkp, trPrc, trqu, vs, yrWRcrdHgst, yrWRcrdHgstDt, yrWRcrdLwst, yrWRcrdLwstDt

    Args:
        params: 필터 딕셔너리 (예: {"basDt": "20260831"}). 비우면 최신부터 반환한다.
        rows: 페이지당 건수 (최대 권장 100).
        page: 페이지 번호.
    """
    return fsc_core.call(CATALOG, 'GetMarketIndexInfoService', 'getStockMarketIndex', params, rows, page)


@mcp.tool(annotations=READ_ONLY)
def get_etf_price(params: dict | None = None, rows: int = 20, page: int = 1) -> dict:
    """ETF 시세를 조회한다. 주식시세 API에는 ETF가 없으므로 여기를 쓴다.
순자산가치는 nav, 기초지수는 bssIdxIdxNm·bssIdxClpr다.

ETN은 get_etn_price, ELW는 search_apis로 getELWPriceInfo를 찾아 call_api한다.

**구성종목·보수·분배금은 없다.** 무엇을 담고 있는지 물으면 이
도구로는 답할 수 없다. 괴리율 필드도 없다 — 종가(clpr)와 nav로
직접 계산했다면 계산했다고 밝힌다.

    필터로 쓸 수 있는 필드(응답 필드와 같다):
        basDt, bssIdxClpr, bssIdxIdxNm, clpr, fltRt, hipr, isinCd, itmsNm, lopr, mkp, mrktTotAmt, nPptTotAmt, nav, srtnCd, stLstgCnt, trPrc, trqu, vs

    Args:
        params: 필터 딕셔너리 (예: {"basDt": "20260831"}). 비우면 최신부터 반환한다.
        rows: 페이지당 건수 (최대 권장 100).
        page: 페이지 번호.
    """
    return fsc_core.call(CATALOG, 'GetSecuritiesProductInfoService', 'getETFPriceInfo', params, rows, page)


@mcp.tool(annotations=READ_ONLY)
def get_etn_price(params: dict | None = None, rows: int = 20, page: int = 1) -> dict:
    """ETN 시세를 조회한다. 기초지수는 bssIdxIdxNm, 그 종가는 bssIdxClpr,
지표가치는 indcVal이다.

**ETF가 아니다.** ETF는 get_etf_price, ELW는 search_apis로
getELWPriceInfo를 찾아 call_api한다.

괴리는 종가(clpr)와 지표가치(indcVal)의 차이다. 직접 계산했다면
계산했다고 밝힌다 — 응답에 괴리율 필드는 없다.

    필터로 쓸 수 있는 필드(응답 필드와 같다):
        basDt, bssIdxClpr, bssIdxIdxNm, clpr, fltRt, hipr, indcVal, indcValTotAmt, isinCd, itmsNm, lopr, lstgScrtCnt, mkp, mrktTotAmt, srtnCd, trPrc, trqu, vs

    Args:
        params: 필터 딕셔너리 (예: {"basDt": "20260831"}). 비우면 최신부터 반환한다.
        rows: 페이지당 건수 (최대 권장 100).
        page: 페이지 번호.
    """
    return fsc_core.call(CATALOG, 'GetSecuritiesProductInfoService', 'getETNPriceInfo', params, rows, page)


@mcp.tool(annotations=READ_ONLY)
def get_bond_price(params: dict | None = None, rows: int = 20, page: int = 1) -> dict:
    """채권 시세를 조회한다. 개별 채권의 수익률·가격 흐름을 볼 때 쓴다.
종가 clprPrc, 종가수익률 clprBnfRt다.

거시 금리(기준금리·국고채)는 이 API가 아니라 한국은행 ECOS다.

**발행조건과 신용등급은 없다.** 쿠폰·만기·등급은 fsc-ficc의
get_bond_basic이다.

**연속 시계열이 아니다.** 개별 회사채는 거래가 드물어 체결일이 띄엄
띄엄하다. 빠진 날을 보간하지 말고 체결일만 점으로 제시하고 관측
일수를 밝힌다.

    필터로 쓸 수 있는 필드(응답 필드와 같다):
        basDt, clprBnfRt, clprPrc, clprVs, hiprBnfRt, hiprPrc, isinCd, itmsCtg, itmsNm, loprBnfRt, loprPrc, mkpBnfRt, mkpPrc, mrktCtg, srtnCd, trPrc, trqu, xpYrCnt

    Args:
        params: 필터 딕셔너리 (예: {"basDt": "20260831"}). 비우면 최신부터 반환한다.
        rows: 페이지당 건수 (최대 권장 100).
        page: 페이지 번호.
    """
    return fsc_core.call(CATALOG, 'GetBondSecuritiesInfoService', 'getBondPriceInfo', params, rows, page)


@mcp.tool(annotations=READ_ONLY)
def get_fund_price(params: dict | None = None, rows: int = 20, page: int = 1) -> dict:
    """수익증권(자산운용사 공모펀드) 시세를 조회한다.

ETF가 아니다. ETF는 get_etf_price, ETN은 get_etn_price를 쓴다.
여기 담긴 것은 자산운용사가 설정한 공모펀드이고 일자당 100건 안팎이다.

    필터로 쓸 수 있는 필드(응답 필드와 같다):
        basDt, clpr, fltRt, hipr, isinCd, itmsNm, lopr, mkp, mrktTotAmt, srtnCd, stLstgCnt, trPrc, trqu, vs

    Args:
        params: 필터 딕셔너리 (예: {"basDt": "20260831"}). 비우면 최신부터 반환한다.
        rows: 페이지당 건수 (최대 권장 100).
        page: 페이지 번호.
    """
    return fsc_core.call(CATALOG, 'GetStockSecuritiesInfoService', 'getSecuritiesPriceInfo', params, rows, page)


@mcp.tool(annotations=READ_ONLY)
def get_warrant_price(params: dict | None = None, rows: int = 20, page: int = 1) -> dict:
    """신주인수권증권(워런트) 시세를 조회한다.

증권(WR)과 증서(R)는 다르다. 증서는 get_subscription_right_price다.
purRgtScrtItmsNm/purRgtScrtItmsClpr가 기초가 되는 주권의 이름과 종가이므로,
행사가(exertPric)와 함께 보면 내가격 여부를 가늠할 수 있다.

**내가격 여부는 계산 결과이지 데이터가 아니다.** 응답에 그런 필드는
없으므로 직접 비교했다면 비교했다고 밝힌다. 행사 가능 기간은
subtPdSttgDt~subtPdEdDt다.

    필터로 쓸 수 있는 필드(응답 필드와 같다):
        basDt, clpr, exertPric, fltRt, hipr, isinCd, itmsNm, lopr, lstgScrtCnt, mkp, mrktCtg, mrktTotAmt, purRgtScrtItmsCd, purRgtScrtItmsClpr, purRgtScrtItmsNm, srtnCd, subtPdEdDt, subtPdSttgDt, trPrc, trqu, vs

    Args:
        params: 필터 딕셔너리 (예: {"basDt": "20260831"}). 비우면 최신부터 반환한다.
        rows: 페이지당 건수 (최대 권장 100).
        page: 페이지 번호.
    """
    return fsc_core.call(CATALOG, 'GetStockSecuritiesInfoService', 'getPreemptiveRightSecuritiesPriceInfo', params, rows, page)


@mcp.tool(annotations=READ_ONLY)
def get_subscription_right_price(params: dict | None = None, rows: int = 20, page: int = 1) -> dict:
    """신주인수권증서 시세를 조회한다. 유상증자 때 배정되어 짧게 거래되는 증서다.

증권(WR)이 아니라 증서(R)다. 증권은 get_warrant_price다.
dltDt(상장폐지일)가 가까우면 거래 가능 기간이 얼마 남지 않았다는 뜻이다.

**청약 일정과 배정 내역은 없다.** 증자 일정은 fsc-equity-ops의
get_right_schedule, 결정 공시는 DART다. nstIssPrc는 신주 발행가이지
청약 금액이 아니다.

    필터로 쓸 수 있는 필드(응답 필드와 같다):
        basDt, clpr, dltDt, fltRt, hipr, isinCd, itmsNm, lopr, lstgCtfCnt, mkp, mrktCtg, mrktTotAmt, nstIssPrc, purRgtScrtItmsCd, purRgtScrtItmsClpr, purRgtScrtItmsNm, srtnCd, trPrc, trqu, vs

    Args:
        params: 필터 딕셔너리 (예: {"basDt": "20260831"}). 비우면 최신부터 반환한다.
        rows: 페이지당 건수 (최대 권장 100).
        page: 페이지 번호.
    """
    return fsc_core.call(CATALOG, 'GetStockSecuritiesInfoService', 'getPreemptiveRightCertificatePriceInfo', params, rows, page)


@mcp.tool(annotations=READ_ONLY)
def find_listed_item(params: dict | None = None, rows: int = 20, page: int = 1) -> dict:
    """KRX 상장종목 마스터에서 종목을 찾는다. 종목코드·ISIN·시장구분 해석의 기준.

시세를 조회하기 전에 여기서 isinCd를 확정해 두면 동명 종목이나 우선주로
인한 오인을 막을 수 있다.

**사용자가 말한 이름과 종목명이 다른 경우가 많다.** 종목명은 KRX
등록 표기라 축약형이 정식이거나 영문 표기이거나 한글과 영문이 섞이기도
한다. 어긋나면 오류가 아니라 0건이
나온다. **0건을 '그런 종목이 없다'로 답하지 않는다.**

  1. 짧고 확실한 조각으로 likeItmsNm 부분 일치를 건다. 회사 형태를
     가리키는 꼬리(홀딩스·그룹·주식회사)는 떼고 찾는다
  2. 0건이면 한글↔영문을 바꿔 두세 번 더 시도한다
  3. 후보가 여럿이면 **추측하지 말고 사용자에게 어느 쪽인지 묻는다.**
     부분 일치는 이름이 겹치는 다른 회사를 함께 끌어온다
  4. 확정한 isinCd로 이후 조회를 고정한다

한 건만 나왔더라도 **그 종목명을 답변에 밝힌다.** 사용자가 말한 이름과
다르면 다르다고 적는다. 끝내 못 찾으면 '없다'가 아니라 '이 표기로는
찾지 못했다'로 답하고 정확한 종목명이나 종목코드를 되묻는다.

    필터로 쓸 수 있는 필드(응답 필드와 같다):
        basDt, corpNm, crno, isinCd, itmsNm, mrktCtg, srtnCd

    Args:
        params: 필터 딕셔너리 (예: {"basDt": "20260831"}). 비우면 최신부터 반환한다.
        rows: 페이지당 건수 (최대 권장 100).
        page: 페이지 번호.
    """
    return fsc_core.call(CATALOG, 'GetKrxListedInfoService', 'getItemInfo', params, rows, page)


if __name__ == "__main__":
    fsc_core.run(mcp)
