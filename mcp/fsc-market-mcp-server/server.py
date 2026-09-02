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

mcp = FastMCP('fsc-market-mcp')


@mcp.tool(annotations=READ_ONLY)
def search_apis(query: str = "", limit: int = 8) -> dict:
    """이 서버가 다루는 API와 오퍼레이션을 찾는다. call_api 이전 단계다.

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

idxNm으로 지수명(예: 'IT 서비스'), idxCsf로 계열(KOSPI시리즈/KOSDAQ시리즈)을
거른다. 개별 종목의 초과수익률을 낼 때 이 값이 벤치마크가 된다.

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

ETN은 get_etn_price, ELW는 search_apis로 getELWPriceInfo를 찾아 call_api한다.

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
    """ETN 시세를 조회한다.

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

거시 금리(기준금리·국고채)는 이 API가 아니라 한국은행 ECOS다.

    필터로 쓸 수 있는 필드(응답 필드와 같다):
        basDt, clprBnfRt, clprPrc, clprVs, hiprBnfRt, hiprPrc, isinCd, itmsCtg, itmsNm, loprBnfRt, loprPrc, mkpBnfRt, mkpPrc, mrktCtg, srtnCd, trPrc, trqu, xpYrCnt

    Args:
        params: 필터 딕셔너리 (예: {"basDt": "20260831"}). 비우면 최신부터 반환한다.
        rows: 페이지당 건수 (최대 권장 100).
        page: 페이지 번호.
    """
    return fsc_core.call(CATALOG, 'GetBondSecuritiesInfoService', 'getBondPriceInfo', params, rows, page)


@mcp.tool(annotations=READ_ONLY)
def find_listed_item(params: dict | None = None, rows: int = 20, page: int = 1) -> dict:
    """KRX 상장종목 마스터에서 종목을 찾는다. 종목코드·ISIN·시장구분 해석의 기준.

시세를 조회하기 전에 여기서 isinCd를 확정해 두면 동명 종목이나 우선주로
인한 오인을 막을 수 있다.

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
