# ECOS MCP Server

한국은행 경제통계시스템(ECOS)을 MCP 도구로 노출하는 서버입니다. 기준금리, 환율,
물가, GDP 같은 거시 경제 통계를 조회합니다.

## 도구 6개

| 도구 | 설명 |
|---|---|
| `list_key_statistics` | 100대 주요 경제지표의 최신값 (환율·기준금리·물가 등) |
| `search_statistic_tables` | 통계표를 이름으로 검색해 `stat_code`를 찾습니다 |
| `list_statistic_items` | 통계표의 세부항목(`item_code`) 목록 |
| `get_statistic_series` | **핵심 도구.** 시계열 데이터를 조회합니다 |
| `search_statistic_glossary` | 통계용어사전 |
| `get_statistic_metadata` | 통계 메타정보 |

모두 조회 전용이라 Gemini Enterprise에서 확인 프롬프트 없이 호출됩니다.

## 사용 흐름

ECOS는 통계표 코드와 항목 코드를 알아야 시계열을 조회할 수 있습니다.

```
search_statistic_tables  →  list_statistic_items  →  get_statistic_series
   (stat_code 찾기)          (item_code 찾기)         (시계열 조회)
```

알아 두시면 좋은 점이 두 가지 있습니다.

- **`stat_code`를 이미 아신다면** `search_statistic_tables`에 `stat_code` 인자로
  직접 넘기세요. 이름 검색보다 훨씬 빠릅니다.
- **`get_statistic_series`에서 `item_code1`을 생략하면** 해당 통계표의 모든
  세부항목이 반환됩니다. 기준금리 통계표(`722Y001`)의 경우 항목을 지정하면 6건,
  생략하면 54건이 나옵니다.

주기(`cycle`)는 `A`(연), `S`(반년), `Q`(분기), `M`(월), `SM`(반월), `D`(일)이며,
조회 시점 형식을 주기에 맞춰야 합니다 — 연 `2020`, 분기 `2020Q1`, 월 `202001`,
일 `20200101`.

## 배포

인프라는 [`../terraform`](../terraform)이 관리합니다.

```bash
cd ../terraform
./build.sh ecos-mcp    # 이미지 빌드
terraform apply        # 새 리비전 배포
```

`ECOS_API_KEY`는 Secret Manager에서 주입되며 이미지에는 포함되지 않습니다.

## 확인

```bash
URL=https://ecos-mcp-<PROJECT_NUMBER>.us-central1.run.app/mcp

curl -sN --max-time 30 -X POST "$URL" \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

도구 6개가 나오면 Gemini Enterprise의 `Reload custom actions`도 같은 결과를 봅니다.

## 참고

[`openapi_spec/`](./openapi_spec)에 한국은행 공식 API 개발명세서가 있습니다.
이 서버는 그 명세를 기준으로 만들었고 라이브 API로 6개 서비스를 모두 검증했습니다.

> 저장소의 `adk-finance-agent/ecos_analytics/ecos_final_openapi.yml`은 참고하지
> 마세요. `StatisticTableList`가 이름 검색 파라미터를 받는다고 적혀 있으나 실제로는
> 존재하지 않습니다.
