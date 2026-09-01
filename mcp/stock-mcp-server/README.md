# Stock MCP Server

금융위원회 **주식시세정보**(공공데이터포털 `GetStockSecuritiesInfoService`)를 MCP
도구로 노출하는 서버입니다. 국내 상장 증권의 일자별 시세를 조회합니다.

## 도구 4개

| 도구 | 대상 | 수록 건수 |
|---|---|---|
| `get_stock_price` | 주권 (KOSPI/KOSDAQ/KONEX) | 442만 |
| `get_fund_price` | 수익증권 (공모펀드) | 13.5만 |
| `get_warrant_price` | 신주인수권증권 (워런트) | 3.4만 |
| `get_subscription_right_price` | 신주인수권증서 | 2,016 |

`get_stock_price`가 사실상 본체이고 나머지 셋은 특수 증권입니다. 모두 조회 전용이라
Gemini Enterprise에서 확인 프롬프트 없이 호출됩니다.

## 조회 방법

네 도구가 같은 조건을 받습니다.

| 인자 | 설명 |
|---|---|
| `item_name` | 종목명 정확 일치 (예: `삼성전자`) |
| `item_name_like` | 종목명 부분 일치 (`삼성전자`로 검색하면 `삼성전자우`도 포함) |
| `isin_cd` / `short_code` | ISIN 12자리 / 단축코드 |
| `base_date` | 특정 하루 (YYYYMMDD) |
| `begin_date` ~ `end_date` | 기간 조회 |
| `market` | `get_stock_price`만 — `KOSPI` / `KOSDAQ` / `KONEX` |

반환 항목은 기준일자(`basDt`), 단축코드, ISIN, 종목명, 시장구분, 종가(`clpr`),
전일대비(`vs`), 등락률(`fltRt`), 시가·고가·저가, 거래량(`trqu`), 거래대금,
상장주식수, 시가총액입니다.

조건을 하나도 주지 않으면 최신 일자부터 전체를 훑으므로, 종목이나 기간을 지정하시는
편이 좋습니다.

## 알아 두실 데이터 한계

**ETF는 이 서비스에 없습니다.** KODEX·TIGER 같은 ETF는 `get_stock_price`에도
`get_fund_price`에도 수록되어 있지 않습니다. `get_fund_price`의 수익증권은
자산운용사 공모펀드(예: "한투한미핵심성장포커스1(A)")로, 일자당 100건 미만입니다.
ETF 시세는 이 서비스키로 접근할 수 없는 별도 서비스에 있습니다.

**잘못된 `market` 값은 조용히 무시됩니다.** `KOSPI`/`KOSDAQ`/`KONEX` 외의 값을 주면
오류 없이 **필터가 적용되지 않은** 결과가 돌아옵니다. 반환된 `mrktCtg`를 확인해
주세요.

**종목 기본정보는 없습니다.** 업종이나 상장일 같은 정보는 조회할 수 없고 시세만
제공합니다.

## 배포

인프라는 [`../terraform`](../terraform)이 관리합니다.

```bash
cd ../terraform
./build.sh stock-mcp   # 이미지 빌드
terraform apply        # 새 리비전 배포
```

## 확인

```bash
URL=https://stock-mcp-<PROJECT_NUMBER>.us-central1.run.app/mcp

curl -sN --max-time 30 -X POST "$URL" \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

## 서비스키 형태

공공데이터포털 키는 `+`, `/`, `=`를 포함하는 **디코딩된 형태**를 그대로 넣어
주세요. 서버가 퍼센트 인코딩을 처리하므로, 미리 인코딩한 값을 넣으면 이중
인코딩으로 실패합니다.

공공데이터포털은 서비스마다 개별 신청이 필요합니다. 이 키로는 주식시세정보
서비스만 접근할 수 있고, 상장종목정보나 지수시세 같은 인접 서비스는 별도로
신청하셔야 합니다.
