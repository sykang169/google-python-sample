"""FSC 보험 MCP Server — 금융위원회 공공데이터 보험 계열.

실손보험 기준보험료, 생보·손보사 재무와 경영지표, 변액보험 펀드, 보험 가입·사고 통계

설계
----
이 데스크가 다루는 API는 9종 / 오퍼레이션 20개다. 전부 도구로 펼치면
tools/list가 커져 다른 MCP 서버와 함께 붙일 때 컨텍스트를 잡아먹으므로,
자주 쓰는 경로만 이름 있는 도구로 내고 나머지는 search_apis + call_api로 연다.
(dart-mcp-server와 같은 점진적 공개 방식이다.)

search_apis는 오퍼레이션의 **응답 필드 목록**을 함께 준다. 금융위 API는 응답
필드명이 곧 필터 파라미터로 쓰이므로, 그 목록이 사실상 파라미터 명세다.
필드는 실제 호출로 수집한 것이라 문서와 어긋날 일이 없다.

주의: 보험료는 회사가 실제로 청구하는 값이 아니라 공시 기준 보험료다. 담보·유형·연령·성별이 같아야 비교가 성립하며, 조건이 다르면 숫자가 달라도 우열이 아니다. 업권 지표는 생보와 손보의 계정 체계가 달라 서로 직접 빼지 않는다.

Gemini Enterprise 데이터 스토어가 소비할 수 있도록 StreamableHTTP를 쓴다.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

import fsc_core
from fsc_core import READ_ONLY, FscError

CATALOG = fsc_core.load_catalog('insurance')

# 서버 단위 전제. MCP initialize 응답으로 나가며, 도구 목록과 달리 매 호출
# 컨텍스트를 차지하지 않는다. 클라이언트가 이걸 모델에 넘기지 않을 수도 있어
# search_apis 설명에도 같은 문장을 넣어 둔다.
INSTRUCTIONS = """보험 — 실손보험 기준보험료, 생보·손보사 재무와 경영지표, 변액보험 펀드, 보험 가입·사고 통계

보험료는 회사가 실제로 청구하는 값이 아니라 공시 기준 보험료다. 담보·유형·연령·성별이 같아야 비교가 성립하며, 조건이 다르면 숫자가 달라도 우열이 아니다. 업권 지표는 생보와 손보의 계정 체계가 달라 서로 직접 빼지 않는다."""

mcp = FastMCP('fsc-insurance-mcp', instructions=INSTRUCTIONS)


@mcp.tool(annotations=READ_ONLY)
def search_apis(query: str = "", limit: int = 8) -> dict:
    """이 서버가 다루는 API와 오퍼레이션을 찾는다. call_api 이전 단계다.

    이 서버의 전제: 보험료는 회사가 실제로 청구하는 값이 아니라 공시 기준 보험료다. 담보·유형·연령·성별이 같아야 비교가 성립하며, 조건이 다르면 숫자가 달라도 우열이 아니다. 업권 지표는 생보와 손보의 계정 체계가 달라 서로 직접 빼지 않는다.

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
def get_medical_insurance_premium(params: dict | None = None, rows: int = 20, page: int = 1) -> dict:
    """실손의료보험 기준보험료를 조회한다. 회사·담보·유형·연령·성별로 갈린다.

mlInsRt가 남성, fmlInsRt가 여성 보험료다(원). 한 회사가 담보(mog)마다
다른 행으로 나오므로 **행 하나를 그 회사 보험료로 읽으면 안 된다.**
회사를 비교하려면 ptrn(유형)과 mog(담보)를 고정하고 같은 조합끼리 본다.
값이 0인 행이 섞여 있는데 미판매 담보이지 무료가 아니다.

age는 '40' 같은 숫자다('40세'가 아니다). cmpyNm은 'KB손보',
'메리츠화재'처럼 줄인 이름이라 법인명으로 찾으면 0건이 나온다.

    필터로 쓸 수 있는 필드(응답 필드와 같다):
        ofrInstNm, basDt, cmpyCd, cmpyNm, ptrn, mog, prdNm, age, mlInsRt, fmlInsRt

    Args:
        params: 필터 딕셔너리 (예: {"basDt": "20260831"}). 비우면 최신부터 반환한다.
        rows: 페이지당 건수 (최대 권장 100).
        page: 페이지 번호.
    """
    return fsc_core.call(CATALOG, 'GetMedicalReimbursementInsuranceInfoService', 'getInsuranceInfo', params, rows, page)


@mcp.tool(annotations=READ_ONLY)
def get_life_insurer_financials(params: dict | None = None, rows: int = 20, page: int = 1) -> dict:
    """생명보험사 재무현황(요약 재무상태표)을 조회한다.

보험사는 보험계약 준비금이 부채의 대부분이다. 제조업 기준으로 부채비율을
읽으면 결론이 뒤집힌다. 계정은 astSmryStfnpsAcitCdNm으로 구분한다.
기준년월(basYm)이 필수에 가깝다 — 없으면 최신 분기가 나온다.

    필터로 쓸 수 있는 필드(응답 필드와 같다):
        title, astSmryStfnpsAcitAmt, astSmryStfnpsAcitCd, astSmryStfnpsAcitCdNm, astSmryStfnpsAcitCmpsRto, basYm, crno, fncoCd, fncoNm

    Args:
        params: 필터 딕셔너리 (예: {"basDt": "20260831"}). 비우면 최신부터 반환한다.
        rows: 페이지당 건수 (최대 권장 100).
        page: 페이지 번호.
    """
    return fsc_core.call(CATALOG, 'GetLifeInsuCompInfoService', 'getLifeInsuCompFinaInfo', params, rows, page)


@mcp.tool(annotations=READ_ONLY)
def get_life_insurer_indicators(params: dict | None = None, rows: int = 20, page: int = 1) -> dict:
    """생명보험사 주요경영지표를 조회한다. 지급여력·수익성 등 업권 지표.

지표 종류는 cpaqItemCdNm에 들어 있다. 재무제표로는 보이지 않는
건전성 맥락이 여기 있다.

    필터로 쓸 수 있는 필드(응답 필드와 같다):
        title, basYm, cpaqItemAmt, cpaqItemCd, cpaqItemCdNm, crno, fncoCd, fncoNm

    Args:
        params: 필터 딕셔너리 (예: {"basDt": "20260831"}). 비우면 최신부터 반환한다.
        rows: 페이지당 건수 (최대 권장 100).
        page: 페이지 번호.
    """
    return fsc_core.call(CATALOG, 'GetLifeInsuCompInfoService', 'getLifeInsuCompKeyManaIndi', params, rows, page)


@mcp.tool(annotations=READ_ONLY)
def get_nonlife_insurer_financials(params: dict | None = None, rows: int = 20, page: int = 1) -> dict:
    """손해보험사 재무현황을 조회한다.

생보와 계정 체계가 달라 같은 표에 놓고 빼지 않는다.

    필터로 쓸 수 있는 필드(응답 필드와 같다):
        title, astSmryStfnpsAcitAmt, astSmryStfnpsAcitCd, astSmryStfnpsAcitCdNm, astSmryStfnpsAcitCmpsRto, basYm, crno, fncoCd, fncoNm

    Args:
        params: 필터 딕셔너리 (예: {"basDt": "20260831"}). 비우면 최신부터 반환한다.
        rows: 페이지당 건수 (최대 권장 100).
        page: 페이지 번호.
    """
    return fsc_core.call(CATALOG, 'GetNonlInsuCompInfoService', 'getNonlInsuCompFinaInfo', params, rows, page)


@mcp.tool(annotations=READ_ONLY)
def get_nonlife_insurer_business(params: dict | None = None, rows: int = 20, page: int = 1) -> dict:
    """손해보험사 주요영업활동을 조회한다. 보종별 경과손해율이 핵심이다.

isuKindElpsLosRatDcdNm이 보종, 같은 접두사의 금액 필드가 그 값이다.
손해율은 보종마다 정상 범위가 다르다.

    필터로 쓸 수 있는 필드(응답 필드와 같다):
        title, basYm, crno, fncoCd, fncoNm, isuKindElpsLosRatClsfAmt, isuKindElpsLosRatDcd, isuKindElpsLosRatDcdNm

    Args:
        params: 필터 딕셔너리 (예: {"basDt": "20260831"}). 비우면 최신부터 반환한다.
        rows: 페이지당 건수 (최대 권장 100).
        page: 페이지 번호.
    """
    return fsc_core.call(CATALOG, 'GetNonlInsuCompInfoService', 'getNonlInsuCompMajoBusiActi', params, rows, page)


@mcp.tool(annotations=READ_ONLY)
def get_variable_insurance_fund(params: dict | None = None, rows: int = 20, page: int = 1) -> dict:
    """변액보험 펀드별 기준가와 순자산을 조회한다.

변액보험은 투자성 상품이라 원금이 보장되지 않는다. 수익률을 제시할 때
사업비 차감 전후를 구분하지 않고 단정하지 않는다.

    필터로 쓸 수 있는 필드(응답 필드와 같다):
        cmpyCd, cmpyNm, fndNm, fndCd, basDt, basprc, nPptAmt

    Args:
        params: 필터 딕셔너리 (예: {"basDt": "20260831"}). 비우면 최신부터 반환한다.
        rows: 페이지당 건수 (최대 권장 100).
        page: 페이지 번호.
    """
    return fsc_core.call(CATALOG, 'GetVariableInsuranceInfoService', 'getFundInfo', params, rows, page)


if __name__ == "__main__":
    fsc_core.run(mcp)
