# DART MCP Server

금융감독원 전자공시(OPEN DART)를 MCP 도구로 노출하는 서버입니다. 기업의 재무제표,
배당, 임원·주주 현황, 합병·증자 같은 공시 정보를 조회합니다.

DART는 JSON 엔드포인트가 82개인데, 이 서버는 **도구 4개**로 제공합니다.

## 도구 4개

```
resolve_company(name)              회사명 → corp_code   (내장 인덱스, 외부 호출 없음)
search_dart_apis(query, group)     82개 카탈로그 검색 → 엔드포인트 + 파라미터 명세
call_dart_api(endpoint, params)    찾은 엔드포인트 실행
ask_dart(question, corp_name)      자연어 질문 하나로 조회 (선택)
```

### 기본 흐름

앞의 세 도구를 순서대로 씁니다. 판단을 호출하는 쪽이 하므로 결과가 예측 가능하고
문제가 생겼을 때 원인을 찾기 쉽습니다.

```
resolve_company("삼성전자")        → 00126380
search_dart_apis("배당")           → alotMatter + 필요한 파라미터
call_dart_api("alotMatter", {...}) → 데이터
```

DART의 모든 API는 회사명이 아니라 8자리 `corp_code`를 요구하므로, 회사가 등장하면
`resolve_company`부터 부르셔야 합니다.

### `ask_dart`는 언제 쓰나

"배당"이 `alotMatter`인지 `stockTotqySttus`인지 같은 도메인 지식이 필요할 때를 위한
편의 도구입니다. 서버 내부에서 Gemini가 82개 중 하나를 고르고 파라미터를 채워
실행합니다.

선택한 엔드포인트와 파라미터를 `routed` 필드로 함께 반환하므로 무엇이 호출됐는지
확인할 수 있습니다. 실측 결과는 다음과 같습니다.

| 질문 | 선택된 엔드포인트 |
|---|---|
| 삼성전자 배당 현황 | `alotMatter` |
| 카카오 임원 현황 | `exctvSttus` |
| 네이버 최대주주 | `hyslrSttus` |
| 삼성전자 연결 재무제표 전체 계정과목 | `fnlttSinglAcntAll` (`fs_div=CFS`까지 채움) |
| 셀트리온 합병 결정 공시 | `cmpMgDecsn` (기간형이라 `bgn_de`/`end_de`로 전환) |

다만 내부에서 LLM을 한 번 더 호출하므로 느리고 매번 같은 선택을 보장하지 않습니다.
결정론적인 동작이 필요한 배포에서는 `DART_ENABLE_ASK=0`으로 끌 수 있습니다.

## 집계는 서버가 합니다

"임원이 몇 명인가" 같은 질문에서 모델이 JSON 수십 행을 직접 세면 틀립니다. 그래서
응답에 `summary`를 함께 반환합니다.

```json
{
  "summary": {
    "row_count": 34,
    "field_distributions": {
      "rgist_exctv_at": { "미등기": 27, "사외이사": 4, "사내이사": 3 }
    }
  },
  "list": [ ... ]
}
```

값의 종류가 2~8개인 범주형 필드만 골라 분포를 계산합니다. 건수를 답하실 때는 행을
세지 마시고 이 값을 쓰세요.

## 사업연도 지정

사업보고서는 해당 연도가 끝난 뒤 이듬해 3월경에 제출됩니다. 따라서 조회 가능한 가장
최근 사업연도는 **직전 연도**입니다. 2015년 이전 데이터는 제공되지 않습니다.

보고서 코드는 사업보고서 `11011`, 반기 `11012`, 1분기 `11013`, 3분기 `11014`입니다.

## 이미지에 포함되는 자산

`assets/`의 두 파일은 런타임에 만들 수 없어 빌드 시점에 준비합니다.

| 파일 | 내용 | 크기 |
|---|---|---|
| `catalog.json` | 82개 엔드포인트의 파라미터 명세 | 90KB |
| `corp_index.json.gz` | 회사명 → `corp_code` (118,819건, 상장 3,988) | 1.4MB |

회사 코드 원본(`corpCode.xml`) 다운로드는 약 4분이 걸려 Cloud Run 요청
타임아웃(300초)에 육박합니다. 콜드 스타트마다 받을 수 없어 미리 준비합니다.

DART가 엔드포인트를 추가하거나 신규 법인이 늘었을 때 갱신하시면 됩니다.

```bash
python build_assets.py              # 둘 다
python build_assets.py --catalog    # 카탈로그만 (빠름)
python build_assets.py --corp       # 회사 인덱스만 (약 4분)

cd ../terraform && ./build.sh dart-mcp && terraform apply
```

## 배포

인프라는 [`../terraform`](../terraform)이 관리합니다.

```bash
cd ../terraform
./build.sh dart-mcp    # 이미지 빌드
terraform apply        # 새 리비전 배포
```

`DART_API_KEY`는 Secret Manager에서 주입됩니다. `ask_dart`가 Gemini를 호출하므로
런타임 서비스 계정에 `roles/aiplatform.user`가 필요한데, Terraform이 부여합니다.

## 확인

```bash
URL=https://dart-mcp-<PROJECT_NUMBER>.us-central1.run.app/mcp

curl -sN --max-time 30 -X POST "$URL" \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

## 환경변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `DART_API_KEY` | — | 필수. Secret Manager에서 주입됩니다 |
| `DART_ENABLE_ASK` | `1` | `0`이면 `ask_dart`를 비활성화합니다 |
| `DART_ROUTER_MODEL` | `gemini-2.5-flash` | `ask_dart`가 사용하는 모델 |
| `GOOGLE_CLOUD_PROJECT` / `GOOGLE_CLOUD_LOCATION` | — | `ask_dart`의 Vertex AI 호출용 |

## 참고

`assets/catalog.json`은 [opendart 공식 개발가이드](https://opendart.fss.or.kr/guide/)에서
직접 수집한 것입니다.

> 저장소의 `adk-finance-agent/dart_analytics/dart_openapi_full_specification.yml`은
> 참고하지 마세요. 삼성전자로 42개 JSON 경로를 전수 실호출한 결과 **19개가 존재하지
> 않는 엔드포인트**였고 **59개가 누락**되어 있었습니다. 이름이 잘못된 곳도 있습니다
> (`alotMatter`를 "주식총수현황"이라 적었으나 실제로는 배당에 관한 사항입니다).
