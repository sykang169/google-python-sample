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

age는 '40' 같은 숫자다('40세'가 아니다). cmpyNm은 **약칭으로**
등록돼 있어 정식 법인명으로 찾으면 0건이 나온다. 필터 없이 한 번
조회해 실제 표기를 확인한 뒤 회사를 특정한다.

    필터로 쓸 수 있는 필드(응답 필드와 같다):
        ofrInstNm, basDt, cmpyCd, cmpyNm, ptrn, mog, prdNm, age, mlInsRt, fmlInsRt

    Args:
        params: 필터 딕셔너리 (예: {"basDt": "20260831"}). 비우면 최신부터 반환한다.
        rows: 페이지당 건수 (최대 권장 100).
        page: 페이지 번호.
    """
    return fsc_core.call(CATALOG, 'GetMedicalReimbursementInsuranceInfoService', 'getInsuranceInfo', params, rows, page)


@mcp.tool(annotations=READ_ONLY)
def get_insurer_financials(sector: str, params: dict | None = None, rows: int = 20, page: int = 1) -> dict:
    """보험사 재무현황을 조회한다.

**title을 반드시 준다.** 이 API는 한 오퍼레이션 안에 여러 통계표가
들어 있고 title이 그중 하나를 고른다. 안 주면 임의의 표가 나오는데,
오류가 아니라 정상 응답이라 알아채기 어렵다. title 없이 부르면
오퍼레이션 이름과 무관한 표가 오고, 업권마다 다른 표가 온다 —
그대로 비교하면 서로 다른 지표를 나란히 놓게 된다.
**돌아온 표의 이름을 확인하고 요청한 것과 같은지 대조한다.**
  요약재무상태표  생보_재무현황_요약재무상태표(자산-전체)
                  손보_재무현황_요약재무상태표(자산-전체)
형식은 <업권>_<현황>_<세부표>다. 다른 표는 search_apis로 확인한다.

요약재무상태표를 받으면 계정은 astSmryStfnpsAcitCdNm으로 구분한다.
보험사는 보험계약 준비금이 부채의 대부분이라 제조업 기준으로 부채비율을
읽으면 결론이 뒤집힌다.
**생보와 손보를 같은 표에 놓고 빼지 않는다.**

    Args:
        sector: 생명보험/손해보험 중 하나. 업권마다 다른 API로 나뉘어 있을 뿐 형식은 같다.
        params: 필터 딕셔너리 (예: {"basYm": "202412"}). 비우면 최신부터 반환한다.
        rows: 페이지당 건수 (최대 권장 100).
        page: 페이지 번호.

    필터로 쓸 수 있는 필드(응답 필드와 같다):
        title, astSmryStfnpsAcitAmt, astSmryStfnpsAcitCd, astSmryStfnpsAcitCdNm, astSmryStfnpsAcitCmpsRto, basYm, crno, fncoCd, fncoNm
    """
    route = {'생명보험': ('GetLifeInsuCompInfoService', 'getLifeInsuCompFinaInfo'), '손해보험': ('GetNonlInsuCompInfoService', 'getNonlInsuCompFinaInfo')}
    if sector not in route:
        raise FscError(
            f"sector는 생명보험/손해보험 중 하나다. 받은 값: {sector!r}")
    service, operation = route[sector]
    return fsc_core.call(CATALOG, service, operation, params, rows, page)


@mcp.tool(annotations=READ_ONLY)
def get_insurer_indicators(sector: str, params: dict | None = None, rows: int = 20, page: int = 1) -> dict:
    """보험사 주요경영지표(지급여력 등)를 조회한다.

**title을 반드시 준다.** 지급여력은 '자본적정성' 표에 있다.
  생보_주요경영지표_자본적정성  /  손보_주요경영지표_자본적정성
title 없이 부르면 생명보험은 대출채권 연체액이 나온다 — 지표가 아니다.

지표 이름은 cpaqItemCdNm이고 **값 필드는 업권마다 다르다** —
생명보험은 cpaqItemAmt, 손해보험은 cpaqItemValCtt다. 한쪽 이름만
찾으면 값이 비어 있는 것으로 읽힌다.

**basYm 없이 한 번 불러 최신 기준년월을 먼저 확인한다.** 최근
분기를 짐작해서 넣으면 오래된 시점의 표를 최신인 것처럼 제시하게
된다. 답변에 조회한 기준년월을 그대로 밝힌다.

**값이 0인 것을 해석하지 않는다.** 어떤 회사는 특정 지표가 0으로
온다. 0이 '해당 없음'인지 '미수록'인지 이 데이터는 구분해 주지
않는다. 이유를 지어내지 말고 **0이라고 그대로 적거나 비운다.**
같은 지표에서 값이 실려 있는 회사와 0인 회사는 성격이 다를 수
있으므로 하나로 묶어 설명하지 않는다.

**업계 합계 행이 회사 행과 섞여 온다.** 회사만 비교할 때는 걸러내고,
합계를 쓸 때는 합계임을 밝힌다.

    Args:
        sector: 생명보험/손해보험 중 하나. 업권마다 다른 API로 나뉘어 있을 뿐 형식은 같다.
        params: 필터 딕셔너리 (예: {"basYm": "202412"}). 비우면 최신부터 반환한다.
        rows: 페이지당 건수 (최대 권장 100).
        page: 페이지 번호.

    필터로 쓸 수 있는 필드(응답 필드와 같다):
        title, basYm, cpaqItemAmt, cpaqItemCd, cpaqItemCdNm, crno, fncoCd, fncoNm, cpaqItemValCtt
    """
    route = {'생명보험': ('GetLifeInsuCompInfoService', 'getLifeInsuCompKeyManaIndi'), '손해보험': ('GetNonlInsuCompInfoService', 'getNonlInsuCompKeyManaIndi')}
    if sector not in route:
        raise FscError(
            f"sector는 생명보험/손해보험 중 하나다. 받은 값: {sector!r}")
    service, operation = route[sector]
    return fsc_core.call(CATALOG, service, operation, params, rows, page)


@mcp.tool(annotations=READ_ONLY)
def get_nonlife_insurer_business(params: dict | None = None, rows: int = 20, page: int = 1) -> dict:
    """손해보험사 보종별 경과손해율을 조회한다.

**갱신이 오래 전에 멈춘 표다.** 최근 기준년월로 조회하면 0건이
나오는데 오류가 아니라 수록 범위 밖이다. **basYm 없이 한 번 불러
최신 기준년월을 먼저 확인하고**, 답변에 그 시점을 밝힌다. 오래된
값을 '최근 손해율'로 제시하지 않는다. 최신 손해율이 필요하면 이
도구로는 답할 수 없다고 말하고 추정하지 않는다.

isuKindElpsLosRatDcdNm이 보종, 같은 접두사의 금액 필드가 그 값이다.
손해율은 보종마다 정상 범위가 다르다.

생명보험 쪽 같은 자리(getLifeInsuCompMajoBusiActi)는 해약환급금이라
성격이 다르다. 하나로 묶지 않았다.

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
    """변액보험 펀드별 기준가(basprc)와 순자산(nPptAmt)을 조회한다.
회사는 cmpyNm, 펀드는 fndNm·fndCd다.

**수익률은 없다.** 기간 수익률을 물으면 두 시점의 기준가를 직접
조회해 계산하고, 계산했다는 사실과 두 기준일을 밝힌다.
**사업비·수수료도 없다.** 기준가 변화는 실제 고객 수익률과 다르다.

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
