"""5개 FSC 서버의 정의. sync.py가 이걸 읽어 server.py를 생성한다.

각 서버는 공통 도구 2개(search_apis / call_api)에 더해, 그 데스크가 가장 자주
쓰는 경로를 감싼 편의 도구를 갖는다. 편의 도구는 실측한 스키마에 근거한다.
"""

SERVERS = {
 "market": {
   "prompts": [
     ('삼성전자 지난달 종가 추이 보여줘', 'get_stock_price'),
     ('KODEX 200 최근 수익률 알려줘', 'get_etf_price — 주식 도구에는 ETF가 없다'),
     ('이 종목이 코스피 대비 얼마나 아웃퍼폼했어?', 'get_stock_price + get_market_index'),
     ('반도체 섹터 지수 흐름 보여줘', 'get_market_index (idxCsf로 계열 지정)'),
     ('삼성전자 정확한 ISIN 코드가 뭐야', 'find_listed_item'),
     ('금값이랑 금 ETF 괴리 확인해줘', "search_apis('금') + get_etf_price"),
   ],
   "title": "시세 통합",
   "desc": "주식·지수·채권·ETF/ETN/ELW·선물·일반상품(금·석유·배출권) 일별 확정시세와 KRX 상장종목 마스터",
   "hint": "장중 시세가 아니다. 기준일 다음 영업일 13시 이후에 갱신되는 확정 시세다.",
   "tools": [
     {"name": "get_stock_price", "svc": "GetStockSecuritiesInfoService", "op": "getStockPriceInfo",
      "doc": "주식(주권) 일별 시세를 조회한다. KOSPI/KOSDAQ/KONEX 상장 주식.\n\n"
             "종목명 정확 일치는 itmsNm, 부분 일치는 likeItmsNm이다. 우선주가 섞이는 것을\n"
             "막으려면 isinCd로 고정하는 편이 안전하다.\n"
             "**ETF·ETN·ELW는 여기 없다.** get_etf_price를 쓴다."},
     {"name": "get_market_index", "svc": "GetMarketIndexInfoService", "op": "getStockMarketIndex",
      "doc": "주가지수 시세를 조회한다. KOSPI/KOSDAQ 대표지수와 섹터지수를 모두 담는다.\n\n"
             "idxNm으로 지수명(예: 'IT 서비스'), idxCsf로 계열(KOSPI시리즈/KOSDAQ시리즈)을\n"
             "거른다. 개별 종목의 초과수익률을 낼 때 이 값이 벤치마크가 된다."},
     {"name": "get_etf_price", "svc": "GetSecuritiesProductInfoService", "op": "getETFPriceInfo",
      "doc": "ETF 시세를 조회한다. 주식시세 API에는 ETF가 없으므로 여기를 쓴다.\n\n"
             "ETN은 get_etn_price, ELW는 search_apis로 getELWPriceInfo를 찾아 call_api한다."},
     {"name": "get_etn_price", "svc": "GetSecuritiesProductInfoService", "op": "getETNPriceInfo",
      "doc": "ETN 시세를 조회한다."},
     {"name": "get_bond_price", "svc": "GetBondSecuritiesInfoService", "op": "getBondPriceInfo",
      "doc": "채권 시세를 조회한다. 개별 채권의 수익률·가격 흐름을 볼 때 쓴다.\n\n"
             "거시 금리(기준금리·국고채)는 이 API가 아니라 한국은행 ECOS다."},
     {"name": "get_fund_price", "svc": "GetStockSecuritiesInfoService", "op": "getSecuritiesPriceInfo",
      "doc": "수익증권(자산운용사 공모펀드) 시세를 조회한다.\n\n"
             "ETF가 아니다. ETF는 get_etf_price, ETN은 get_etn_price를 쓴다.\n"
             "여기 담긴 것은 \"한투한미핵심성장포커스1(A)\" 같은 공모펀드이고 일자당 100건 안팎이다."},
     {"name": "get_warrant_price", "svc": "GetStockSecuritiesInfoService", "op": "getPreemptiveRightSecuritiesPriceInfo",
      "doc": "신주인수권증권(워런트) 시세를 조회한다.\n\n"
             "증권(WR)과 증서(R)는 다르다. 증서는 get_subscription_right_price다.\n"
             "purRgtScrtItmsNm/purRgtScrtItmsClpr가 기초가 되는 주권의 이름과 종가이므로,\n"
             "행사가(exertPric)와 함께 보면 내가격 여부를 가늠할 수 있다."},
     {"name": "get_subscription_right_price", "svc": "GetStockSecuritiesInfoService", "op": "getPreemptiveRightCertificatePriceInfo",
      "doc": "신주인수권증서 시세를 조회한다. 유상증자 때 배정되어 짧게 거래되는 증서다.\n\n"
             "증권(WR)이 아니라 증서(R)다. 증권은 get_warrant_price다.\n"
             "dltDt(상장폐지일)가 가까우면 거래 가능 기간이 얼마 남지 않았다는 뜻이다."},
     {"name": "find_listed_item", "svc": "GetKrxListedInfoService", "op": "getItemInfo",
      "doc": "KRX 상장종목 마스터에서 종목을 찾는다. 종목코드·ISIN·시장구분 해석의 기준.\n\n"
             "시세를 조회하기 전에 여기서 isinCd를 확정해 두면 동명 종목이나 우선주로\n"
             "인한 오인을 막을 수 있다."},
   ],
 },
 "ficc": {
   "prompts": [
     ('이 회사채 국고채 대비 스프레드가 얼마야?', 'get_bond_basic + ECOS (서버 2개)'),
     ('다음 분기에 콜 행사 가능한 채권 목록', 'get_bond_call_redemption'),
     ('CP 91일물 금리가 기준금리 대비 어떻게 움직였어?', 'get_short_term_rate + ECOS'),
     ('지금 리테일에 팔 만한 채권 수익률 알려줘', 'get_retail_bond_yield (구간별 요약)'),
     ('이 채권 이자지급일 언제야', 'get_bond_right_schedule'),
     ('올해 회사채 발행 규모 상위 보여줘', "search_apis('발행실적') + call_api"),
   ],
   "title": "채권·단기자금",
   "desc": "채권 기본·발행·권리행사·권리일정, CP/CD 매매금리, 소매채권 수익률, 채무증권 발행실적(DCM)",
   "hint": "거시 금리 지표(기준금리, 국고채 시장금리)는 이 서버가 아니라 한국은행 ECOS에 있다. "
           "스프레드를 계산하려면 두 소스를 함께 써야 한다.",
   "tools": [
     {"name": "get_bond_basic", "svc": "GetBondIssuInfoService_V2", "op": "getBondBasiInfo_V2",
      "doc": "채권 기본정보(마스터)를 조회한다. 종목 식별의 출발점이다."},
     {"name": "get_bond_principal_interest", "svc": "GetBondTradInfoService_V2", "op": "getBondPrinAndInte_V2",
      "doc": "채권 원리금 정보를 조회한다. 캐시플로 산출의 근거."},
     {"name": "get_bond_right_schedule", "svc": "GetBondRighScheInfoService_V2", "op": "getBondRighExerSche_V2",
      "doc": "채권 권리행사 일정(이자지급·상환)을 조회한다."},
     {"name": "get_bond_call_redemption", "svc": "GetBondRedeInfoService_V2", "op": "getBondWithOptiCallRede_V2",
      "doc": "옵션부채권의 조기상환(콜) 내역을 조회한다. 콜 리스크 점검용."},
     {"name": "get_retail_bond_yield", "svc": "GetBondInfoService", "op": "getBondSecurityBenefitRate",
      "doc": "소매채권 수익률을 조회한다. 리테일 채권 판매에 바로 쓰이는 값이다."},
     {"name": "get_short_term_rate", "svc": "GetShorTermSecuTradInfoService_V2", "op": "getBuyAndSellAmou_V2",
      "doc": "단기금융증권(CP·CD)의 매매 금액·금리를 조회한다.\n\n"
             "발행 정보가 아니라 **실거래** 기준이라 단기자금 운용의 체감 금리에 가깝다."},
   ],
 },
 "research": {
   "prompts": [
     ('이 회사 부채비율 계산해줘', 'get_corp_outline → get_financial_statement'),
     ('계열회사 목록 보여줘', 'get_affiliates'),
     ('최근 유상증자 결정 공시 있었어?', "search_apis('유상증자') + call_api"),
     ('자기주식 취득 공시 확인해줘', "search_apis('자기주식') + call_api"),
     ('2010년 재무제표도 볼 수 있어?', 'get_financial_statement (DART는 2015년 이후만)'),
   ],
   "title": "기업분석·공시",
   "desc": "기업 개요·계열사·종속기업, 정규화 재무제표, 공시 32종, 지배구조, ESG 지수",
   "hint": "DART(전자공시)와 겹치는 영역이 있다. 이 서버는 정규화된 표 형태라 계산에 바로 쓰기 좋고, "
           "원문 공시 전문이나 XBRL이 필요하면 DART 쪽을 쓴다.",
   "tools": [
     {"name": "get_financial_statement", "svc": "GetFinaStatInfoService_V2", "op": "getBs_V2",
      "doc": "재무상태표를 조회한다. DART XBRL 파싱 없이 정규화된 계정 값을 받는다.\n\n"
             "손익계산서와 요약재무제표는 search_apis로 같은 서비스의 다른 오퍼레이션을 찾는다.\n"
             "법인등록번호(crno)와 사업연도(bizYear)로 거르는 것이 보통이다."},
     {"name": "get_corp_outline", "svc": "GetCorpBasicInfoService_V2", "op": "getCorpOutline_V2",
      "doc": "기업 개요를 조회한다. 법인등록번호(crno) 확정의 출발점."},
     {"name": "get_affiliates", "svc": "GetCorpBasicInfoService_V2", "op": "getAffiliate_V2",
      "doc": "계열회사 목록을 조회한다. 지배구조 맵을 그릴 때 쓴다."},
     {"name": "get_disclosure", "svc": "GetDiscInfoService_V2", "op": "getDiviDiscInfo_V2",
      "doc": "배당 공시를 조회한다. 이 서비스에는 유상증자·합병 등 32종의 공시\n"
             "오퍼레이션이 있으므로, 다른 공시는 search_apis로 찾아 call_api로 실행한다."},
   ],
 },
 "equity-ops": {
   "prompts": [
     ('이 주권 사고 등록된 거 아니야?', "check_irregular_stock — 실패를 '이상 없음'으로 답하지 않는다"),
     ('다음 달 배당 기준일인 종목 알려줘', 'get_dividend'),
     ('이번 분기 청약 일정 정리해줘', 'get_right_schedule'),
     ('대차잔고 높은 종목 보여줘', 'get_stock_lending — 대차 ≠ 공매도'),
     ('REPO 금리 추이 보여줘', 'get_repo_rate (담보 종류별로 갈린다)'),
   ],
   "title": "권리·대차",
   "desc": "주식 배당·권리일정·사고주권·발행, 주식/채권 대차, REPO 금리와 거래",
   "hint": "권리업무와 백오피스 판단에 쓰는 데이터다. 사고주권 조회처럼 결과가 업무 처리를 "
           "가르는 것이 있으므로, 조회 실패를 '해당 없음'으로 답하지 않도록 주의한다.",
   "tools": [
     {"name": "get_dividend", "svc": "GetStocDiviInfoService_V2", "op": "getDiviInfo_V2",
      "doc": "주식 배당정보(기준일·금액)를 조회한다. 배당락 처리와 고객 안내의 근거."},
     {"name": "get_right_schedule", "svc": "GetStocRighScheService_V2", "op": "getRighExerReasSche_V2",
      "doc": "권리행사 사유별 일정을 조회한다. 청약·행사 업무의 달력."},
     {"name": "check_irregular_stock", "svc": "GetStocTradInfoService_V2", "op": "getIrreRigforSecu_V2",
      "doc": "사고주권 여부를 조회한다. 실물 입고 심사에서 확인이 필요한 항목이다.\n\n"
             "**조회에 실패했을 때 '사고 없음'으로 답하지 않는다.** 실패는 실패로 보고한다."},
     {"name": "get_stock_lending", "svc": "GetStocLendBorrInfoService_V2", "op": "getMontLendAndBorrStatu_V2",
      "doc": "주식 대차 현황을 조회한다. 대차잔고는 공매도 압력의 대리지표로 읽히지만,\n"
             "대차가 곧 공매도는 아니라는 점을 답변에 밝힌다."},
     {"name": "get_repo_rate", "svc": "GetRepoItemInfoService_V2", "op": "getInteRateInfo_V2",
      "doc": "REPO 금리를 조회한다. 단기 조달비용의 기준."},
   ],
 },
 "industry": {
   "prompts": [
     ('우리 수수료가 경쟁사 대비 어디쯤이야?', 'get_brokerage_fee — 거래금액 구간을 맞춘다'),
     ('펀드 판매 점유율 순위 보여줘', 'get_fund_sales — 모집단을 밝힌다'),
     ('업계 ELS 발행 규모 알려줘', "search_apis('ELS') + call_api"),
     ('IRP 라인업에 넣을 펀드 후보', "get_fund_code + search_apis('퇴직연금')"),
     ('경쟁 증권사 경영지표 비교해줘', 'get_securities_firm_stats — basYm 필수'),
   ],
   "title": "상품·업계",
   "desc": "펀드 표준코드·판매현황, 퇴직연금, 증권사 경영지표·수수료 공시, 금투협 통계",
   "hint": "자사와 경쟁사를 같은 잣대로 비교할 때 쓴다. 특정 회사를 유리하거나 불리하게 "
           "보이도록 지표를 골라 제시하지 않는다.",
   "tools": [
     {"name": "get_fund_code", "svc": "GetFundProductInfoService", "op": "getStandardCodeInfo",
      "doc": "펀드 표준코드를 조회한다. 판매 상품 마스터."},
     {"name": "get_fund_sales", "svc": "GetFdSaleInfoService_V2", "op": "getCustFundSaleInfo_V2",
      "doc": "펀드 판매현황을 조회한다. 판매기관·고객유형·펀드유형별 점유율을 본다."},
     {"name": "get_securities_firm_stats", "svc": "GetSecuCompInfoService", "op": "getSecuCompGeneInfo",
      "doc": "증권사 일반현황을 조회한다. 재무·경영지표는 search_apis로 같은 서비스의\n"
             "다른 오퍼레이션을 찾는다."},
     {"name": "get_brokerage_fee", "svc": "GetOfficialNoticeInfoService", "op": "getStockTradingFeeInfo",
      "doc": "증권사 주식거래 수수료 공시를 조회한다. 가격 경쟁 포지션 확인용."},
     {"name": "get_kofia_stat", "svc": "GetKofiaStatisticsInfoService", "op": "getCMAStatus",
      "doc": "금융투자협회 종합통계를 조회한다. CMA 잔고 외에 펀드 순자산·신탁 규모 등은\n"
             "search_apis로 같은 서비스의 다른 오퍼레이션을 찾는다."},
   ],
 },
}
