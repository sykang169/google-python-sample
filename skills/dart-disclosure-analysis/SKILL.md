---
name: dart-disclosure-analysis
description: 금융감독원 전자공시(OPEN DART) 데이터로 한국 기업의 공시·재무제표·지배구조·지분변동을 조회하고 분석한다. 사업보고서, 재무제표, 배당, 임원현황, 최대주주, 자기주식, 증자, 합병, 감사보고서 같은 국내 기업 공시 질문에 사용한다. "삼성전자 작년 배당", "이 회사 부채비율", "공시 확인해줘", "DART", "corp_code", "reprt_code", "사업보고서", "재무제표 뽑아줘" 같은 요청이면 기억에 의존해 API를 추측하지 말고 반드시 이 스킬을 먼저 읽는다. 미국 SEC EDGAR나 해외 공시에는 쓰지 않는다.
license: MIT
compatibility: dart-mcp-server(resolve_company / search_dart_apis / call_dart_api / ask_dart) MCP 도구 또는 OPEN DART API 키가 필요하다.
metadata:
  author: google-python-sample
  version: "1.0"
---

# DART 전자공시 분석

한국 기업의 "사실"은 대부분 DART에 있다. 실적, 배당, 지분, 임원, 소송, 증자 —
기억이나 웹 검색으로 답하면 숫자가 틀리거나 오래된 값을 말하게 된다.
**항상 DART 원문 수치로 답하고, 어떤 보고서(사업연도·보고서코드)에서 나온 값인지 함께 밝힌다.**

## 핵심 규칙

> [!IMPORTANT]
> 아래 세 가지가 이 도메인에서 가장 자주 나는 사고다.

1. **엔드포인트 이름을 기억해서 쓰지 않는다.** DART JSON API는 82개이고 이름이
   서로 비슷하다(`alotMatter` vs `stockTotqySttus`). 반드시 `search_dart_apis`로
   이름과 파라미터 명세를 먼저 확인한 뒤 `call_dart_api`를 호출한다.
2. **회사명으로는 아무것도 조회할 수 없다.** 거의 모든 API가 8자리 `corp_code`를
   요구한다. 첫 단계는 언제나 `resolve_company`다.
3. **연도를 추측하지 않는다.** 사업보고서는 해당 사업연도가 끝난 뒤 이듬해
   3월경에 제출된다. 따라서 "최신 사업보고서"는 보통 **직전 연도**다.
   학습 시점 기준으로 연도를 고르면 매번 `status 013`(데이터 없음)이 난다.

## 표준 워크플로

```
resolve_company(회사명)      → corp_code
      ↓
search_dart_apis(주제어)     → endpoint + 필수 파라미터
      ↓
call_dart_api(endpoint, {corp_code, bsns_year, reprt_code, ...})
      ↓
summary.field_distributions로 집계, list로 개별 값 인용
```

무엇을 조회해야 할지 자체가 불분명할 때만 `ask_dart(question, corp_name)`를 쓴다.
서버 내부 LLM이 엔드포인트를 고르므로 비결정적이다. 반환된 `routed.endpoint`를
사용자에게 함께 보여 어떤 공시를 봤는지 추적 가능하게 한다.

### 필수 파라미터 값

| 파라미터 | 값 |
| --- | --- |
| `corp_code` | 8자리. `resolve_company`로만 획득. 회사명 금지 ([kr-entity-resolution](../kr-entity-resolution/SKILL.md)) |
| `bsns_year` | 4자리. **2015년 이후만 제공** |
| `reprt_code` | 1분기 `11013`, 반기 `11012`, 3분기 `11014`, 사업보고서 `11011` |
| `bgn_de` / `end_de` | `YYYYMMDD` |
| `crtfc_key` | **절대 넣지 않는다.** 서버가 주입한다 |

동명이인 회사가 많다. "한국전력"처럼 상장사를 원하는 게 분명하면
`resolve_company(name, listed_only=True)`로 비상장 계열사를 걸러낸다.
`stock_code`가 빈 문자열이면 비상장이다.

## 집계 질문은 직접 세지 않는다

"사외이사 몇 명이야", "몇 건이야" 같은 질문에서 `list` 배열을 눈으로 세면
페이지 경계와 중복 때문에 틀린다. `call_dart_api`가 붙여 주는 `summary`를 쓴다.

- `summary.row_count` — 결과 행 수
- `summary.field_distributions` — 범주형 필드의 값별 건수
  (예: `exctvSttus`의 `rgist_exctv_at` → 사내이사/사외이사/미등기 인원)

## 오류 코드 해석

DART는 **HTTP 200과 함께** `status`로 오류를 준다. 상태 코드만 보면 안 된다.
코드별 대응 지침은 **도구가 오류 메시지에 함께 실어 보내므로 여기 옮겨 적지
않는다.**

기억할 것은 하나다 — **`013`(데이터 없음)을 그대로 "데이터가 없습니다"로
돌려주지 않는다.** 최소 한 번은 직전 사업연도로 낮추거나 `reprt_code`를 바꿔
재시도한다. 이게 실제로 대부분의 원인이다.

## 재무 수치를 다룰 때

재무제표 계정 조회는 연결/별도, 그리고 재무제표 구분을 먼저 정해야 한다.
계정 코드 체계와 대표 지표 계산식은 [references/financial-statements.md](references/financial-statements.md)를 읽는다.

숫자를 인용할 때는 항상 다음을 함께 쓴다: **회사명(corp_code) · 사업연도 ·
보고서 종류 · 연결/별도 · 단위(원)**. DART 금액은 원 단위 문자열이며 쉼표가
섞여 있으므로 계산 전에 `int(x.replace(",", ""))`로 정규화한다. 음수는
`-` 또는 괄호로 온다.

## 검증된 엔드포인트 예시

`search_dart_apis`가 정답이지만, 아래는 저장소에서 실제 동작이 확인된 것들이다.

| 엔드포인트 | 내용 |
| --- | --- |
| `alotMatter` | 배당에 관한 사항 |
| `fnlttSinglAcntAll` | 단일회사 전체 재무제표 |
| `exctvSttus` | 임원 현황 |

그룹으로 좁힐 때는 `search_dart_apis(group=...)`에 다음 중 하나를 준다 —
`공시정보`, `정기보고서 주요정보`, `정기보고서 재무정보`, `지분공시`,
`주요사항보고서`, `증권신고서`.

## 답변 형식

```markdown
## [회사명] [연도] [주제]

**출처**: DART [보고서명] (corp_code, bsns_year, reprt_code)

| 항목 | 값 |
| --- | --- |
| ... | ... |

### 해석
(수치가 의미하는 바 2~4문장)
```

## 하지 말아야 할 것

- 조회한 수치에 근거하지 않은 주가 전망이나 매수/매도 의견을 덧붙이지 않는다.
  공시 분석과 투자권유는 다르다 — 규제 경계는 [kr-financial-ai-compliance](../kr-financial-ai-compliance/SKILL.md)를 참고한다.
- 조회에 실패했는데 그럴듯한 수치를 채워 넣지 않는다. 실패는 실패라고 말한다.
- 공시에 없는 항목(예: 주가)을 DART에서 찾지 않는다. 시세는
  [krx-stock-quote-analysis](../krx-stock-quote-analysis/SKILL.md)다.

**금융위 공공데이터에도 같은 기업 정보가 있다.** 계정 값으로 계산하거나 여러
기업을 한 번에 훑을 때는 정규화된
[kr-corporate-research](../kr-corporate-research/SKILL.md)가 빠르고, 공시 원문·
사업보고서 본문·XBRL 주석이 필요하면 DART가 맞다. 두 소스의 수치를 한 답변에
섞지 않는다 — 작성 기준과 정정 반영 시점이 다르다.
