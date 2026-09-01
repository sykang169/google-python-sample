# Stock MCP Server

금융위원회 **주식시세정보** OpenAPI(data.go.kr `GetStockSecuritiesInfoService`)를
MCP 도구로 노출한다. Gemini Enterprise Custom MCP 데이터 스토어가 소비할 수 있도록
StreamableHTTP 전송을 쓴다.

DART/ECOS와 달리 API 표면이 4개뿐이라 카탈로그 검색 없이 직접 도구로 낸다.

## 도구 4개

| 도구 | 대상 | 실측 건수 |
|---|---|---|
| `get_stock_price` | 주권 (KOSPI/KOSDAQ/KONEX) | 442만 |
| `get_fund_price` | 수익증권 (공모펀드) | 13.5만 |
| `get_warrant_price` | 신주인수권증권 (워런트) | 3.4만 |
| `get_subscription_right_price` | 신주인수권증서 | 2,016 |

전부 `readOnlyHint: true`라 Gemini Enterprise에서 확인 팝업 없이 호출된다.

조회 조건은 네 도구가 동일하다 — 종목명 정확일치(`item_name`) / 부분일치
(`item_name_like`) / ISIN / 단축코드 / 기준일 / 기간(`begin_date`~`end_date`).

## 배포

인프라는 `mcp/terraform/`이 관리한다.

```bash
cd ../terraform
./build.sh stock-mcp   # 이미지 빌드 + 태그 기록
terraform apply       # 새 리비전 배포
```

`STOCK_API_KEY`는 Secret Manager에서 주입되며 이미지에 굽지 않는다.

## 검증

```bash
URL=https://stock-mcp-<PROJECT_NUMBER>.us-central1.run.app/mcp
bash ~/.claude/skills/gemini-enterprise-custom-mcp/scripts/probe_mcp_server.sh \
  "$URL" "$(gcloud auth print-identity-token)"
```

## 확인된 상위 API 동작 3가지

**1. TLS 검증을 끌 필요가 없다.** 이 저장소의 기존
`adk-finance-agent/stock_analytics/ssl_api_tool.py`는 `verify=False`로 인증서
검증을 껐지만, 실제로 `apis.data.go.kr`는 정상 인증서를 제공한다. 이 서버는
검증을 켠 상태로 동작한다.

**2. ETF는 이 서비스에 없다.** `get_fund_price`의 수익증권은 자산운용사 공모펀드
(예: "한투한미핵심성장포커스1(A)")이며, KODEX/TIGER 같은 ETF는 `get_stock_price`
에도 `get_fund_price`에도 수록되지 않는다. ETF 시세는 이 서비스키로 접근할 수
없는 별도 서비스에 있다.

**3. 알 수 없는 `market` 값은 조용히 무시된다.** `market="NASDAQ"`을 주면 오류
없이 필터가 적용되지 않은 결과가 돌아온다. 반환된 `mrktCtg`를 확인해야 한다.

## 서비스키 형태

data.go.kr 키는 `+`, `/`, `=`를 포함하는 **디코딩 형태**를 그대로 넣는다.
httpx가 퍼센트 인코딩을 처리하므로 미리 인코딩한 값을 넣으면 이중 인코딩으로 실패한다.

## 알려진 제약

**공개 접근 (미해결 — 조직 관리자 필요).** Gemini Enterprise가 도달하려면 Cloud Run
서비스가 공개여야 하는데(PSC 미지원), 조직 정책
`constraints/iam.allowedPolicyMemberDomains`가 `allUsers` 바인딩을 막고 있다.
배포는 되지만 외부에서 403이며, 인증 토큰으로만 호출된다.
