# fsc-market-mcp-server

주식·지수·채권·ETF/ETN/ELW·선물·일반상품(금·석유·배출권) 일별 확정시세와 KRX 상장종목 마스터

금융위원회가 공공데이터포털에 개방한 API 중 **시세 통합** 계열
7종(오퍼레이션 16개)을 MCP 도구로 노출한다.

- 짝이 되는 스킬: [`kr-equity-analysis`](../../skills/kr-equity-analysis/SKILL.md)
- Cloud Run 서비스명: `fsc-market-mcp`

## 이런 질문에 답한다

| 질문 | 어떻게 |
| --- | --- |
| "삼성전자 지난달 종가 추이 보여줘" | get_stock_price |
| "KODEX 200 최근 수익률 알려줘" | get_etf_price — 주식 도구에는 ETF가 없다 |
| "이 종목이 코스피 대비 얼마나 아웃퍼폼했어?" | get_stock_price + get_market_index |
| "반도체 섹터 지수 흐름 보여줘" | get_market_index (idxCsf로 계열 지정) |
| "삼성전자 정확한 ISIN 코드가 뭐야" | find_listed_item |
| "금값이랑 금 ETF 괴리 확인해줘" | search_apis('금') + get_etf_price |

## 도구

| 도구 | 내용 |
| --- | --- |
| `search_apis` | 이 서버가 다루는 오퍼레이션 검색. 응답 필드(=필터 파라미터)까지 반환 |
| `call_api` | 찾은 오퍼레이션 실행 |
| `get_stock_price` | 주식(주권) 일별 시세를 조회한다. KOSPI/KOSDAQ/KONEX 상장 주식. |
| `get_market_index` | 주가지수 시세를 조회한다. KOSPI/KOSDAQ 대표지수와 섹터지수를 모두 담는다. |
| `get_etf_price` | ETF 시세를 조회한다. 주식시세 API에는 ETF가 없으므로 여기를 쓴다. |
| `get_etn_price` | ETN 시세를 조회한다. |
| `get_bond_price` | 채권 시세를 조회한다. 개별 채권의 수익률·가격 흐름을 볼 때 쓴다. |
| `get_fund_price` | 수익증권(자산운용사 공모펀드) 시세를 조회한다. |
| `get_warrant_price` | 신주인수권증권(워런트) 시세를 조회한다. |
| `get_subscription_right_price` | 신주인수권증서 시세를 조회한다. 유상증자 때 배정되어 짧게 거래되는 증서다. |
| `find_listed_item` | KRX 상장종목 마스터에서 종목을 찾는다. 종목코드·ISIN·시장구분 해석의 기준. |

이름 있는 도구는 자주 쓰는 경로만 감싼 것이다. 나머지는 `search_apis` →
`call_api` 순으로 접근한다. 전부 도구로 펼치면 `tools/list`가 커져 다른 MCP
서버와 함께 붙일 때 컨텍스트를 잡아먹기 때문이다.

## 필요한 data.go.kr 활용신청

인증키는 공공데이터포털 계정당 **하나**(`STOCK_API_KEY`)이고 이 저장소의 fsc-*
서버 5종이 공유한다. 다만 **승인은 API마다 따로** 받아야 하며, 미승인 API는
같은 키로도 `resultCode 30`이 난다.

이 서버를 쓰려면 아래 7건을 각각 활용신청해야 한다.

| 서비스 | 이름 | 활용신청 |
| --- | --- | --- |
| `GetKrxListedInfoService` | KRX상장종목정보 | [신청](https://www.data.go.kr/data/15094775/openapi.do) |
| `GetGeneralProductInfoService` | 일반상품시세정보 | [신청](https://www.data.go.kr/data/15094805/openapi.do) |
| `GetStockSecuritiesInfoService` | 주식시세정보 | [신청](https://www.data.go.kr/data/15094808/openapi.do) |
| `GetSecuritiesProductInfoService` | 증권상품시세정보 | [신청](https://www.data.go.kr/data/15094806/openapi.do) |
| `GetMarketIndexInfoService` | 지수시세정보 | [신청](https://www.data.go.kr/data/15094807/openapi.do) |
| `GetBondSecuritiesInfoService` | 채권시세정보 | [신청](https://www.data.go.kr/data/15094784/openapi.do) |
| `GetDerivativeProductInfoService` | 파생상품시세정보 | [신청](https://www.data.go.kr/data/15094802/openapi.do) |

승인 여부는 실제 호출로만 알 수 있다. 저장소 루트에서:

```bash
python3 mcp/fsc-common/check_access.py market
```

## 주의

장중 시세가 아니다. 기준일 다음 영업일 13시 이후에 갱신되는 확정 시세다.

- **전부 비실시간이다.** 기준일 다음 영업일 13시 이후에 갱신된다.
- 오류가 HTTP 200과 함께 온다. `resultCode 03`은 데이터 없음(오류 아님),
  `30`은 활용신청 미승인, `12`는 경로나 오퍼레이션명 오류다.
  **`12`를 미승인으로 읽지 않는다.**
- **`apis.data.go.kr`은 소스 IP 단위로 접속을 일시 차단한다.** 짧은 시간에 호출을
  몰아치면 그 IP의 TCP 연결을 수 분~수십 분간 받지 않는다. 서버가 응답 캐시(6시간),
  호출 간 최소 간격(0.5초), 회로 차단(연속 3회 실패 → 300초 정지)으로 대응하지만
  완전히 막지는 못한다. `ConnectTimeout`이 반복되면 코드나 키가 아니라 이쪽이다
  (`../fsc-common/README.md`의 "호출량 억제" 참고).
- 5개 fsc 서버가 같은 상류를 쓴다. **한 서버가 몰아치면 나머지도 함께 막힌다.**

## 실행

```bash
export STOCK_API_KEY="..."      # 디코딩 형태 그대로. 퍼센트 인코딩하지 말 것
pip install -r requirements.txt
python server.py                # http://localhost:8080/mcp
```

## 배포

```bash
cd ../terraform && ./build.sh fsc-market-mcp && terraform apply
```

## 생성 파일

`server.py`, `fsc_core.py`, `catalog.json`, 이 README는 `mcp/fsc-common/`에서
생성된다. 여기서 직접 고치지 말고 원본을 고친 뒤 `python3 sync.py`를 다시 실행한다.
