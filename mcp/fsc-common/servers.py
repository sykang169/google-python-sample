"""6개 FSC 서버의 정의. sync.py가 이걸 읽어 server.py를 생성한다.

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
             "여기 담긴 것은 자산운용사가 설정한 공모펀드이고 일자당 100건 안팎이다."},
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
             "인한 오인을 막을 수 있다.\n\n"
             "**사용자가 말한 이름과 종목명이 다른 경우가 많다.** 종목명은 KRX\n"
             "등록 표기라 축약형이 정식이거나 영문 표기이거나 한글과 영문이 섞이기도\n"
             "한다. 어긋나면 오류가 아니라 0건이\n"
             "나온다. **0건을 \'그런 종목이 없다\'로 답하지 않는다.**\n\n"
             "  1. 짧고 확실한 조각으로 likeItmsNm 부분 일치를 건다. 회사 형태를\n"
             "     가리키는 꼬리(홀딩스·그룹·주식회사)는 떼고 찾는다\n"
             "  2. 0건이면 한글↔영문을 바꿔 두세 번 더 시도한다\n"
             "  3. 후보가 여럿이면 **추측하지 말고 사용자에게 어느 쪽인지 묻는다.**\n"
             "     부분 일치는 이름이 겹치는 다른 회사를 함께 끌어온다\n"
             "  4. 확정한 isinCd로 이후 조회를 고정한다\n\n"
             "한 건만 나왔더라도 **그 종목명을 답변에 밝힌다.** 사용자가 말한 이름과\n"
             "다르면 다르다고 적는다. 끝내 못 찾으면 \'없다\'가 아니라 \'이 표기로는\n"
             "찾지 못했다\'로 답하고 정확한 종목명이나 종목코드를 되묻는다."},
   ],
 },
 "ficc": {
   "prompts": [
     ('이 회사채 국고채 대비 스프레드가 얼마야?', 'get_bond_basic + ECOS (서버 2개)'),
     ('다음 분기에 콜 행사 가능한 채권 목록', 'get_bond_call_redemption'),
     ('CP 91일물 금리가 기준금리 대비 어떻게 움직였어?', 'get_short_term_rate + ECOS'),
     ('이 CP 종목 발행일이랑 금리 알려줘', 'get_short_term_issue (종목별은 여기만 있다)'),
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
     {"name": "get_short_term_rate", "svc": "GetShorTermSecuTradInfoService_V2", "op": "getBuyAndSellInteRate_V2",
      "doc": "단기금융증권(CP·전단채 등)의 매매 수익률을 조회한다. 금리 값은\n"
             "rmngExprTrdBnfRt다.\n\n"
             "발행 조건이 아니라 **실거래** 기준이라 단기자금 운용의 체감 금리에 가깝다.\n\n"
             "**개별 종목이 아니라 집계다.** 발행인 업종(isurPtrnNm)·상품구분\n"
             "(shtrFinPrdDcdNm)·잔존만기(shtrPrdRmngExprDcdNm)로 묶인 값이라\n"
             "여기에 종목 식별자가 없다. 종목별 금리는 get_short_term_issue를 쓴다.\n"
             "거래 규모는 get_short_term_trade_amount다."},
     {"name": "get_short_term_trade_amount", "svc": "GetShorTermSecuTradInfoService_V2", "op": "getBuyAndSellAmou_V2",
      "doc": "단기금융증권의 잔존만기별 매매 **금액**을 조회한다(rmngExprTrdAmt).\n\n"
             "**금리가 아니다.** 이 오퍼레이션에는 금리 필드가 없다. 금리는\n"
             "get_short_term_rate를 쓴다. 여기 값을 금리로 읽으면 자릿수가 억 단위인\n"
             "금액을 수익률로 제시하게 된다.\n\n"
             "매도/매수는 trdDcdNm으로 갈린다. 합산하면 같은 거래를 두 번 세게 된다."},
     {"name": "get_short_term_issue", "svc": "GetShorTermSecuTradInfoService_V2", "op": "getCaseBuyAndSellInfo_V2",
      "doc": "단기금융증권 **건별** 매매 내역을 조회한다. 이 서비스에서 종목\n"
             "식별자(isinCd·isinCdNm)가 있는 유일한 오퍼레이션이다.\n\n"
             "종목별 발행일(shtrFinPrdIssuDt)·만기(shtrFinPrdExprDt)·금리\n"
             "(shtrFinPrdIrt)·거래금액(shtrFinPrdTrdAmt)이 한 행에 있다.\n"
             "특정 CP의 조건을 물으면 여기를 본다.\n\n"
             "매수·매도 주체가 각각 다른 필드(buynShtrFinBzcDcdNm/slngShtrFinBzcDcdNm)다."},
   ],
 },
 "research": {
   "prompts": [
     ('이 회사 부채비율 계산해줘', 'get_corp_outline → get_financial_statement'),
     ('계열회사 목록 보여줘', 'get_affiliates'),
     ('최근 유상증자 결정 공시 있었어?', "search_apis('유상증자') + call_api"),
     ('자기주식 취득 공시 확인해줘', "search_apis('자기주식') + call_api"),
     ('2010년 재무제표도 볼 수 있어?', 'get_financial_statement (DART는 2015년 이후만)'),
     ('이 회사 사외이사 몇 명이야?', 'get_executives — 건수는 서버가 센다'),
     ('증권사 순이익 뽑아줘', 'get_financial_statement는 0건이다 → dart-mcp로 간다'),
   ],
   "title": "기업분석·공시",
   "desc": "기업 개요·계열사·종속기업, 정규화 재무제표, 공시 32종, 지배구조, ESG 지수",
   "hint": "DART(전자공시)와 겹치는 영역이 있다. 이 서버는 정규화된 표 형태라 계산에 바로 쓰기 좋고, "
           "원문 공시 전문이나 XBRL이 필요하면 DART 쪽을 쓴다.",
   "tools": [
     {"name": "get_financial_statement", "svc": "GetFinaStatInfoService_V2", "op": "getBs_V2",
      "doc": "재무상태표를 조회한다. DART XBRL 파싱 없이 정규화된 계정 값을 받는다.\n\n"
             "손익계산서와 요약재무제표는 search_apis로 같은 서비스의 다른 오퍼레이션을 찾는다.\n"
             "법인등록번호(crno)와 사업연도(bizYear)로 거르는 것이 보통이다.\n\n"
             "**금융회사(은행·증권·보험)는 여기 없다.** 0건이 나오면 권한 문제가 아니라\n"
             "수록 범위 밖이라는 뜻이다. 그때는 dart-mcp의 fnlttSinglAcnt로 간다."},
     {"name": "get_corp_outline", "svc": "GetCorpBasicInfoService_V2", "op": "getCorpOutline_V2",
      "doc": "기업 개요를 조회한다. 법인등록번호(crno) 확정의 출발점."},
     {"name": "get_affiliates", "svc": "GetCorpBasicInfoService_V2", "op": "getAffiliate_V2",
      "doc": "계열회사 목록을 조회한다. 지배구조 맵을 그릴 때 쓴다."},
     {"name": "get_executives", "svc": "GetCorpGoveInfoService", "op": "getExecutivesInfo",
      "doc": "임원 현황을 조회한다. 사외이사 수 같은 지배구조 질문의 근거.\n\n"
             "**행을 세는 것은 서버가 한다.** 응답의 건수와 범주 분포를 쓰고,\n"
             "JSON을 직접 세지 않는다. 보수는 search_apis로 getExecRemuStat을 찾는다."},
     {"name": "get_dividend_disclosure", "svc": "GetDiscInfoService_V2", "op": "getDiviDiscInfo_V2",
      "doc": "**배당 공시만** 조회한다. 공시 일반이 아니다.\n\n"
             "이 서비스에는 유상증자·합병·자기주식·소송 등 30종이 넘는 공시\n"
             "오퍼레이션이 있고 이 도구는 그중 배당 하나만 감싼다. 다른 공시를\n"
             "물으면 search_apis로 해당 오퍼레이션을 찾아 call_api로 실행한다.\n"
             "**여기서 0건이 나온 것을 '공시가 없다'로 답하지 않는다.**\n\n"
             "당기·전기·전전기 세 시점이 crtm/pvtr/bpvtr 접두사로 한 행에 함께 온다.\n"
             "접두사를 확인하지 않으면 전기 값을 당기로 답하게 된다.\n\n"
             "배당 기준일·지급일 같은 권리 일정은 여기가 아니라 fsc-equity-ops의\n"
             "get_dividend다. 공시 **원문 본문**은 DART 서버를 쓴다."},
   ],
 },
 "equity-ops": {
   "prompts": [
     ('이 주권 사고 등록된 거 아니야?', "check_irregular_stock — 실패를 '이상 없음'으로 답하지 않는다"),
     ('다음 달 배당 기준일인 종목 알려줘', 'get_dividend'),
     ('이번 분기 청약 일정 정리해줘', 'get_right_schedule'),
     ('대차잔고 높은 종목 보여줘', 'get_stock_lending — 종목별. 대차 ≠ 공매도'),
     ('대차 시장 전체 규모 추이', 'get_lending_market_total — 월별 시장 합계'),
     ('REPO 금리 추이 보여줘', 'get_repo_rate (담보 종류별로 갈린다)'),
   ],
   "title": "권리·대차",
   "desc": "주식 배당·권리일정·사고주권·발행, 주식/채권 대차, REPO 금리와 거래",
   "hint": "권리업무와 백오피스 판단에 쓰는 데이터다. 사고주권 조회처럼 결과가 업무 처리를 "
           "가르는 것이 있으므로, 조회 실패를 '해당 없음'으로 답하지 않도록 주의한다.",
   "tools": [
     {"name": "get_dividend", "svc": "GetStocDiviInfoService_V2", "op": "getDiviInfo_V2",
      "doc": "주식 배당정보(기준일·금액)를 조회한다. 배당락 처리와 고객 안내의 근거.\n\n"
             "**필터는 isinCd 또는 isinCdNm을 쓴다.** like를 붙인 이름\n"
             "(likeIsinCdNm 등)은 이 API가 받지 않는데 **오류 없이 무시되고 전체\n"
             "목록이 돌아온다.** 건수가 수만 단위면 필터가 안 걸린 것이고, 그 결과를\n"
             "그 종목의 배당으로 읽으면 다른 종목의 배당을 안내하게 된다.\n"
             "돌아온 행의 isinCd를 조회하려던 종목과 **대조한 뒤** 답한다.\n\n"
             "기준일은 dvdnBasDt, 현금배당 지급일은 cashDvdnPayDt,\n"
             "주당 배당금은 stckGenrDvdnAmt다. 이름이 비슷한 필드가 많으니\n"
             "search_apis가 준 fields에서 고르고 지어내지 않는다.\n\n"
             "**우선주는 별도 종목이다.** scrsItmsKcdNm으로 보통주/우선주를 구분해\n"
             "어느 쪽 배당인지 밝힌다."},
     {"name": "get_right_schedule", "svc": "GetStocRighScheService_V2", "op": "getRighExerReasSche_V2",
      "doc": "권리행사 사유별 일정을 조회한다. 청약·행사 업무의 달력."},
     {"name": "check_irregular_stock", "svc": "GetStocTradInfoService_V2", "op": "getIrreRigforSecu_V2",
      "doc": "사고주권 여부를 조회한다. 실물 입고 심사에서 확인이 필요한 항목이다.\n\n"
             "**필터는 isinCdNm 또는 stckIssuCmpyNm을 쓴다.**\n"
             "like를 붙인 이름(likeIsinCdNm 등)은 이 API가\n"
             "받지 않는데 **오류 없이 무시되고 전체 목록이 돌아온다.**\n"
             "건수가 수만 단위면 필터가 안 걸린 것이다. 그 결과를 그 종목의\n"
             "사고 이력으로 읽으면\n"
             "엉뚱한 종목의 사고를 보고하게 된다.\n"
             "돌아온 행의 isinCd가 조회하려던 종목과 같은지 **반드시 대조한다.**\n\n"
             "**조회에 실패했을 때 \'사고 없음\'으로 답하지 않는다.** 실패는 실패로 보고한다."},
     {"name": "get_stock_lending", "svc": "GetStocLendBorrInfoService_V2", "op": "getStItemLendAndBorrStatu_V2",
      "doc": "**종목별** 대차거래 현황을 조회한다. isinCd 또는 isinCdNm으로 거른다.\n\n"
             "체결(lnbCclStckCnt)·잔고(lnbRmanStckCnt)·상환(lnbRdptStckCnt) 주식 수다.\n"
             "금액이 아니라 **주식 수**이므로 잔고 금액을 물으면 종가를 곱해야 하고,\n"
             "곱했다는 사실을 밝힌다.\n\n"
             "대차잔고는 공매도 압력의 대리지표로 읽히지만 **대차가 곧 공매도는\n"
             "아니다.** 차입 후 공매도하지 않는 경우가 있으므로 답변에 밝힌다.\n"
             "공매도 잔고 자체는 이 데이터에 없다.\n\n"
             "시장 전체 합계는 get_lending_market_total이다."},
     {"name": "get_lending_market_total", "svc": "GetStocLendBorrInfoService_V2", "op": "getMontLendAndBorrStatu_V2",
      "doc": "대차거래 **월별 시장 전체 합계**를 조회한다.\n\n"
             "**종목별이 아니다.** 이 오퍼레이션에는 종목 식별자가 없고 한 달에 한\n"
             "행뿐이다. 특정 종목의 대차잔고를 물으면 get_stock_lending을 쓴다.\n"
             "여기 값을 한 종목의 잔고로 제시하면 시장 전체를 그 종목 것으로\n"
             "답하게 된다.\n\n"
             "기준일(basDt)이 월 단위라 일별 추이는 낼 수 없다."},
     {"name": "get_repo_rate", "svc": "GetRepoItemInfoService_V2", "op": "getInteRateInfo_V2",
      "doc": "REPO 금리를 조회한다. 단기 조달비용의 기준."},
   ],
 },
 "insurance": {
   "prompts": [
     ('40대 남성 실손보험료 회사별로 비교해줘', 'get_medical_insurance_premium — 담보·유형을 맞춘다'),
     ('생보사 지급여력 지표 보여줘', "get_insurer_indicators — title에 '자본적정성'을 준다"),
     ('손해보험사 경과손해율 어떻게 돼?', 'get_nonlife_insurer_business — 2019년까지만 있다'),
     ('삼성생명 총자산 얼마야?', "get_insurer_financials — title에 '요약재무상태표'를 준다"),
     ('변액보험 펀드 기준가 알려줘', 'get_variable_insurance_fund'),
     ('자동차보험 사고 피해자 통계 있어?', "search_apis('자동차') + call_api"),
   ],
   "title": "보험",
   "desc": "실손보험 기준보험료, 생보·손보사 재무와 경영지표, 변액보험 펀드, 보험 가입·사고 통계",
   "hint": "보험료는 회사가 실제로 청구하는 값이 아니라 공시 기준 보험료다. 담보·유형·연령·성별이 "
           "같아야 비교가 성립하며, 조건이 다르면 숫자가 달라도 우열이 아니다. "
           "업권 지표는 생보와 손보의 계정 체계가 달라 서로 직접 빼지 않는다.",
   "tools": [
     {"name": "get_medical_insurance_premium", "svc": "GetMedicalReimbursementInsuranceInfoService",
      "op": "getInsuranceInfo",
      "doc": "실손의료보험 기준보험료를 조회한다. 회사·담보·유형·연령·성별로 갈린다.\n\n"
             "mlInsRt가 남성, fmlInsRt가 여성 보험료다(원). 한 회사가 담보(mog)마다\n"
             "다른 행으로 나오므로 **행 하나를 그 회사 보험료로 읽으면 안 된다.**\n"
             "회사를 비교하려면 ptrn(유형)과 mog(담보)를 고정하고 같은 조합끼리 본다.\n"
             "값이 0인 행이 섞여 있는데 미판매 담보이지 무료가 아니다.\n\n"
             "age는 '40' 같은 숫자다('40세'가 아니다). cmpyNm은 **약칭으로**\n"
             "등록돼 있어 정식 법인명으로 찾으면 0건이 나온다. 필터 없이 한 번\n"
             "조회해 실제 표기를 확인한 뒤 회사를 특정한다."},
     {"name": "get_insurer_financials",
      "route": {"생명보험": ("GetLifeInsuCompInfoService", "getLifeInsuCompFinaInfo"),
                "손해보험": ("GetNonlInsuCompInfoService", "getNonlInsuCompFinaInfo")},
      "doc": "보험사 재무현황을 조회한다.\n\n"
             "**title을 반드시 준다.** 이 API는 한 오퍼레이션 안에 여러 통계표가\n"
             "들어 있고 title이 그중 하나를 고른다. 안 주면 임의의 표가 나오는데,\n"
             "오류가 아니라 정상 응답이라 알아채기 어렵다(실측: title 없이 부르면\n"
             "생명보험은 대손충당금, 손해보험은 요약재무상태표가 나온다 — 그대로\n"
             "비교하면 다른 것을 비교하게 된다).\n"
             "  요약재무상태표  생보_재무현황_요약재무상태표(자산-전체)\n"
             "                  손보_재무현황_요약재무상태표(자산-전체)\n"
             "형식은 <업권>_<현황>_<세부표>다. 다른 표는 search_apis로 확인한다.\n\n"
             "요약재무상태표를 받으면 계정은 astSmryStfnpsAcitCdNm으로 구분한다.\n"
             "보험사는 보험계약 준비금이 부채의 대부분이라 제조업 기준으로 부채비율을\n"
             "읽으면 결론이 뒤집힌다.\n"
             "**생보와 손보를 같은 표에 놓고 빼지 않는다.**"},
     {"name": "get_insurer_indicators",
      "route": {"생명보험": ("GetLifeInsuCompInfoService", "getLifeInsuCompKeyManaIndi"),
                "손해보험": ("GetNonlInsuCompInfoService", "getNonlInsuCompKeyManaIndi")},
      "doc": "보험사 주요경영지표(지급여력 등)를 조회한다.\n\n"
             "**title을 반드시 준다.** 지급여력은 '자본적정성' 표에 있다.\n"
             "  생보_주요경영지표_자본적정성  /  손보_주요경영지표_자본적정성\n"
             "title 없이 부르면 생명보험은 대출채권 연체액이 나온다 — 지표가 아니다.\n\n"
             "지표 이름은 cpaqItemCdNm이고 **값 필드는 업권마다 다르다** —\n"
             "생명보험은 cpaqItemAmt, 손해보험은 cpaqItemValCtt다. 한쪽 이름만\n"
             "찾으면 값이 비어 있는 것으로 읽힌다."},
     {"name": "get_nonlife_insurer_business", "svc": "GetNonlInsuCompInfoService",
      "op": "getNonlInsuCompMajoBusiActi",
      "doc": "손해보험사 보종별 경과손해율을 조회한다.\n\n"
             "**이 표는 2019년 12월이 마지막이다**(실측). 최근 기준년월로 조회하면\n"
             "0건이 나오는데 오류가 아니라 수록 범위 밖이다. 최신 손해율이 필요하면\n"
             "이 도구로는 답할 수 없다고 말하고 추정하지 않는다.\n\n"
             "isuKindElpsLosRatDcdNm이 보종, 같은 접두사의 금액 필드가 그 값이다.\n"
             "손해율은 보종마다 정상 범위가 다르다.\n\n"
             "생명보험 쪽 같은 자리(getLifeInsuCompMajoBusiActi)는 해약환급금이라\n"
             "성격이 다르다. 하나로 묶지 않았다."},
     {"name": "get_variable_insurance_fund", "svc": "GetVariableInsuranceInfoService",
      "op": "getFundInfo",
      "doc": "변액보험 펀드별 기준가와 순자산을 조회한다.\n\n"
             "변액보험은 투자성 상품이라 원금이 보장되지 않는다. 수익률을 제시할 때\n"
             "사업비 차감 전후를 구분하지 않고 단정하지 않는다."},
   ],
 },
 "industry": {
   "prompts": [
     ('우리 수수료가 경쟁사 대비 어디쯤이야?', "get_brokerage_fee — ctg='변경후'로 거른다"),
     ('펀드 판매 점유율 순위 보여줘', 'get_fund_sales — 모집단을 밝힌다'),
     ('업계 ELS 발행 규모 알려줘', "search_apis('ELS') + call_api"),
     ('IRP 라인업에 넣을 펀드 후보', "get_fund_code + search_apis('퇴직연금')"),
     ('경쟁 증권사 경영지표 비교해줘', 'get_securities_firm_stats — basYm 필수'),
     ('이 은행 BIS비율이랑 연체율 얼마야?', 'get_bank_stats — 재무제표로는 안 보이는 건전성 지표'),
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
      "doc": "증권사 일반현황(임직원·점포 등)을 조회한다.\n\n"
             "같은 서비스의 다른 오퍼레이션은 이름과 내용이 어긋나므로 주의한다\n"
             "(search_apis로 접근한다).\n"
             "  getSecuCompFinaInfo    '재무현황'이지만 실제로는 **주석항목**이다\n"
             "                         (채무보증·대차/대주·대손상각채권). 재무제표가 아니다\n"
             "  getSecuCompKeyManaIndi '주요경영지표'지만 **유동성비율**만 들어 있다\n"
             "  getSecuCompMajoBusiActi 금융투자상품 수탁수수료 항목별 실적\n\n"
             "**증권사의 자기자본·순이익은 여기가 아니라 DART다.** 금융위 재무제표\n"
             "API(GetFinaStatInfoService_V2)에는 증권사가 없어 0건이 나온다\n"
             "(같은 키로 일반기업은 조회된다 — 권한이 아니라 수록 범위 문제다).\n"
             "dart-mcp의 fnlttSinglAcnt로 가면 나온다."},
     {"name": "get_bank_stats", "svc": "GetDomeBankInfoService", "op": "getDomeBankKeyManaIndi",
      "doc": "국내은행 주요경영지표를 조회한다. BIS비율·연체율 같은 건전성 지표.\n\n"
             "재무제표로는 보이지 않는 업권 지표다. 예금 금리를 비교할 때 그 은행이\n"
             "어떤 상태인지 함께 봐야 하면 여기를 쓴다.\n"
             "재무현황은 search_apis로 getDomeBankFinaInfo를 찾는다."},
     {"name": "get_brokerage_fee", "svc": "GetOfficialNoticeInfoService", "op": "getStockTradingFeeInfo",
      "doc": "증권사 주식거래 수수료 공시를 조회한다. 가격 경쟁 포지션 확인용.\n\n"
             "**ctg로 먼저 거른다. 같은 cfe 필드에 금액과 비율이 섞여 있다.**\n"
             "ctg='변경후'는 수수료 금액(원), ctg='변경율'은 변경 비율이다.\n"
             "나누지 않고 정렬하면 수천 원과 0.00x를 한 줄에 놓게 된다.\n\n"
             "**cfe가 null인 행이 절반 가까이 된다.** 그 채널 미제공이지\n"
             "수수료 0이 아니다. 최저가로 읽지 않는다.\n\n"
             "**trAmt는 금액이 아니라 구간 코드다.** 실측으로 확정한 대응은\n"
             "  100=10만원  150=50만원  200=100만원\n"
             "  250=500만원 300=1000만원 350=1억원\n"
             "(정률 상품의 수수료를 각 구간 금액으로 나누면 전 구간이 같은 요율로\n"
             "떨어져 검산된다.)\n"
             "trAmt를 만원 단위로 읽으면 요율 계산이 전부 틀린다.\n\n"
             "**행마다 basDt가 다르다. 표 전체에 기준일 하나를 붙이지 않는다.**\n"
             "회사가 수수료를 바꾼 날이 곧 basDt이고 회사마다 몇 년씩 벌어진다.\n"
             "**회사별 최신 basDt를 각각 확인해** 그것만 남겨 비교하고, 공시일이\n"
             "벌어진 사실을 먼저 밝힌다. 한 회사의 공시일을 표 전체 기준일로 적으면\n"
             "몇 년 된 값이 현재 수수료로 제시된다.\n\n"
             "채널은 brofOpnActCtg 값을 **그대로** 쓴다(증권사지점개설계좌 /\n"
             "은행개설계좌 × 오프라인·HTS·스마트폰·ARS). '다이렉트'나 상품\n"
             "브랜드명으로 바꾸지 않는다 — 데이터에 없는 구분이다.\n\n"
             "**개설 경로만 보고 요약하지 않는다. 접속 수단까지 나눈다.**\n"
             "같은 개설 경로 안에서도 접속 수단에 따라 요율이 10배까지 갈리는\n"
             "회사가 있다(같은 은행개설계좌인데 HTS만 저율인 식이다).\n"
             "'은행개설은 저율'처럼 뭉뚱그리면 스마트폰 이용자에게 틀린 안내가 된다.\n\n"
             "요율을 요약할 때는 **구간별로 다른지 확인한다.** 한 구간 값으로\n"
             "'정률'이라고 단정하지 않는다. 소액 구간만 다른 회사가 있어,\n"
             "**구간별 요율을 모두 계산해 본 뒤** 판단한다."},
     {"name": "get_kofia_stat", "svc": "GetKofiaStatisticsInfoService", "op": "getCMAStatus",
      "doc": "금융투자협회 종합통계를 조회한다. CMA 잔고 외에 펀드 순자산·신탁 규모 등은\n"
             "search_apis로 같은 서비스의 다른 오퍼레이션을 찾는다."},
   ],
 },
}
