# 금융권 Agent Skills

국내 금융 업무의 **판단 규칙**을 모은
[Agent Skills](https://agentskills.io/specification) 8종입니다. Claude Code,
Gemini CLI, Gemini Enterprise 등 스킬 표준을 지원하는 에이전트에서 쓸 수 있습니다.

도구를 어떻게 호출하는지는 담지 않았습니다. 담은 것은 **호출한 다음에 내려야 하는
판단**입니다 — 스프레드를 재려면 잔존만기를 맞춰야 하고, 초과수익률의 벤치마크는
종목이 속한 계열이어야 하며, 부채비율은 은행에 쓰면 의미가 없고, 최고우대금리는
우대조건 없이는 틀린 안내입니다.

이런 것들은 **API가 알려주지 않습니다.** 만기가 다른 채권을 비교해도, 코스닥
종목을 코스피와 견주어도 숫자는 나옵니다. 오류로 드러나지 않는 실수만 골라
담았습니다.

## 무엇이 어떤 질문에 붙나

**업무 5종** — 실무에서 하는 일별로 나눴습니다. 데이터 소스별이 아닙니다.
하나의 질문이 여러 소스를 가로지르는 것이 보통이기 때문입니다.

| 스킬 | 이런 질문에 | 필요한 데이터 |
| --- | --- | --- |
| [`kr-equity-analysis`](kr-equity-analysis/) | "삼성전자 지난달 수익률", "코스피 대비 초과수익", "금 ETF 괴리" | 시세 |
| [`kr-macro-and-rates`](kr-macro-and-rates/) | "기준금리 추이", "국고채 대비 스프레드", "CP 91일물" | 거시 시계열 + 채권 |
| [`kr-corporate-financials`](kr-corporate-financials/) | "부채비율 3년 추이", "유상증자 공시 원문", "사외이사 몇 명" | 재무제표 + 전자공시 |
| [`kr-product-comparison`](kr-product-comparison/) | "예금 금리 제일 높은 곳", "증권사 수수료 비교", "펀드 판매 점유율" | 상품 금리 + 업계 통계 |
| [`kr-equity-operations`](kr-equity-operations/) | "배당 기준일", "사고주권 조회", "대차잔고" | 권리·대차 |

**횡단 3종** — 어느 일을 하든 똑같이 걸립니다. 업무 스킬들이 이 셋을 참조만 하고
내용을 옮겨 적지 않습니다.

| 스킬 | 다루는 것 |
| --- | --- |
| [`kr-market-calendar`](kr-market-calendar/) | 휴장일·영업일, 배당락·권리락, 결산월과 공시 제출기한 |
| [`kr-entity-resolution`](kr-entity-resolution/) | ISIN·단축코드·`crno`·`corp_code`·펀드 표준코드 확정 |
| [`kr-financial-ai-compliance`](kr-financial-ai-compliance/) | 금융권 AI 규제 가드레일 (설계 문서) |

날짜와 식별자를 따로 뽑은 이유는 분량이 아니라 **실패 방식**입니다. 둘 다 거의 모든
질문의 밑바닥에 깔려 있고, 틀려도 오류가 나지 않습니다. 조용히 틀리는 지식은 한
곳에 모아야 어긋나지 않습니다.

> [!NOTE]
> `kr-financial-ai-compliance`는 **에이전트를 설계할 때 읽는 문서**입니다.
> 런타임 가드레일(투자권유 경계, 편향 비교 금지)은 스킬이 아니라 시스템
> 프롬프트가 담당합니다 — 스킬은 질문에 따라 선택적으로 로드되므로, 규제 경계를
> 스킬에만 두면 그 스킬을 부르지 않는 질문에서 빠집니다.

## 무엇을 담고 무엇을 담지 않나

각 스킬은 "이 API를 어떻게 호출하는가"가 아니라 **"모델이 무엇을 조용히
틀리는가"**를 씁니다.

**담는 것**

- **코드를 기억에서 쓰지 말 것** — 통계표 코드나 공시 엔드포인트명은 추측하면
  오류가 아니라 *다른 데이터*가 돌아옵니다
- **비교와 계산의 설계** — 만기를 맞추지 않은 스프레드, 계열이 다른 벤치마크,
  구간이 다른 수수료 비교는 숫자는 나오지만 답이 아닙니다
- **수록 범위 밖** — ETF는 주식시세 API에 없고, 개별 회사 금리는 거시 통계에 없습니다
- **해석의 함정** — 연결/별도, 지수와 상승률, 기본금리와 우대금리, 대차와 공매도
- **출처와 기준시점** — 금융 답변에서 시점 없는 숫자는 틀린 숫자입니다

**담지 않는 것.** 있어야 할 자리가 따로 있고, 스킬에 옮겨 적으면 **어긋날 수 있는
중복**이 됩니다.

| 지식 | 있어야 할 곳 |
| --- | --- |
| 응답 필드·필터 파라미터 이름 | MCP 서버의 `search_apis` 응답 — 실측이라 어긋나지 않습니다 |
| 오류 코드와 대응 지침 | 서버가 오류 메시지에 함께 실어 보냅니다 |
| 어느 서버·도구를 쓸지 | 도구 이름과 설명 |
| 답변 형식, 규제 가드레일 | 시스템 프롬프트 ([`../mcp/SYSTEM_PROMPT.md`](../mcp/SYSTEM_PROMPT.md)) |

## 데이터는 어디서 오나

스킬은 도메인 지식만 담고 데이터는 다루지 않습니다. 이 저장소의
[MCP 서버 8종](../mcp)이 짝을 이루지만, **다른 방식으로 같은 데이터를 조회해도
스킬은 그대로 쓸 수 있습니다.**

| 스킬 | 이 저장소의 짝 |
| --- | --- |
| `kr-equity-analysis` | [`fsc-market-mcp-server`](../mcp/fsc-market-mcp-server) |
| `kr-macro-and-rates` | [`ecos-mcp-server`](../mcp/ecos-mcp-server) + [`fsc-ficc-mcp-server`](../mcp/fsc-ficc-mcp-server) |
| `kr-corporate-financials` | [`fsc-research-mcp-server`](../mcp/fsc-research-mcp-server) + [`dart-mcp-server`](../mcp/dart-mcp-server) |
| `kr-product-comparison` | [`finlife-mcp-server`](../mcp/finlife-mcp-server) + [`fsc-industry-mcp-server`](../mcp/fsc-industry-mcp-server) |
| `kr-equity-operations` | [`fsc-equity-ops-mcp-server`](../mcp/fsc-equity-ops-mcp-server) |

실제 질문이 이 스킬들을 어떻게 가로지르는지는
[`../mcp/SCENARIOS.md`](../mcp/SCENARIOS.md)에 데스크별 시나리오 13개로 있습니다.

## 사용 방법

### Claude Code

```bash
ln -s "$(pwd)" ~/.claude/skills/kr-finance
```

또는 `.claude/skills/` 아래로 복사하셔도 됩니다.

### Gemini CLI 등 스킬 표준을 지원하는 에이전트

스킬 디렉터리를 그대로 두거나 심볼릭 링크로 연결하면 `SKILL.md`의 frontmatter가
자동으로 인덱싱됩니다.

### Gemini Enterprise

경로가 두 가지입니다. 어느 쪽이든 `references/`는 GE에 단계적 공개가 없어 무시되므로,
패키징 스크립트가 `SKILL.md` 끝에 부록으로 이어붙입니다.

**(A) 웹앱 업로드** — 한 번 올려 보고 끝내실 때

```bash
python3 scripts/package_for_gemini_enterprise.py --all
```

생성된 `dist/*.zip`을 웹앱에서 올리시면 됩니다.

```
웹앱 → 스킬 → 추가(+) → 스킬 업로드 → 드래그 → 가져오기
```

업로드하면 기본으로 사용 설정됩니다. 호출 방법은 세 가지입니다 — 채팅에서
`@스킬이름` 또는 `/`로 멘션, 프롬프트에서 이름을 직접 언급, 그리고 `description`
기반 자동 선택입니다. 자동 선택이 잘 되도록 `description`에 사용자가 실제로 쓸
표현을 넣어 두었습니다.

**(B) Skill Registry API** — CI에 넣거나 여러 환경에 반복 배포하실 때

```bash
gcloud auth application-default login
python3 scripts/upload_to_skill_registry.py --all \
    --project <PROJECT_ID> --location us-central1
```

이미 등록된 스킬을 덮어쓰려면 `--update`, 확인만 하려면 `--dry-run`을 붙이세요.

`POST .../v1beta1/projects/{p}/locations/{l}/skills?skillId={id}`에 ZIP을
base64(`zippedFilesystem`)로 실어 보냅니다. 생성·수정·삭제가 장기 실행 작업이라
스크립트가 완료까지 기다립니다. 필요한 권한은 `roles/aiplatform.user`와
`roles/serviceusage.serviceUsageConsumer`입니다.

### 알아 두실 제약

| 항목 | 내용 |
| --- | --- |
| 에이전트 | **스킬은 에이전트와 함께 쓸 수 없습니다.** GE 어시스턴트 전용입니다 |
| 실행 언어 | `scripts/`는 Python과 Bash만 지원합니다 |
| 크기 | 업로드 파일 총합 100MB 이하 |
| 스킬 이름 | 조직 내에서 고유해야 합니다. 소문자·숫자·하이픈 |
| skillId (API) | 1~63자, 문자로 시작하고 문자/숫자로 끝나며 `gcp-` 접두사는 예약되어 있습니다 |
| 삭제 후 재사용 | 삭제한 skillId는 **24시간** 동안 다시 쓸 수 없습니다 |
| 숨김 파일 | `.DS_Store`, `__pycache__`, `*.pyc`가 있으면 업로드가 실패합니다 (스크립트가 제외합니다) |
| 상대 링크 | `../다른-스킬/SKILL.md`는 ZIP 안에서 풀리지 않습니다 |
| 웹앱 편집기 | `SKILL.md` 한 장짜리만 편집할 수 있습니다. 스크립트가 있으면 ZIP 업로드만 가능합니다 |

> [!WARNING]
> **Skill Registry 제공 리전은 `us-central1` / `europe-west4` / `us-east5`뿐이고
> 서울(`asia-northeast3`)이 없습니다.** 국내 금융회사 배포에서는
> [`kr-financial-ai-compliance`](kr-financial-ai-compliance/SKILL.md)의 데이터
> 레지던시 항목과 정면으로 부딪히는 지점입니다. 스킬 본문에 고객 데이터를 넣지
> 않는다는 전제를 확인하시고 법무·준법감시인과 정리하신 뒤 올려 주세요.
>
> 파일명 대소문자는 문서가 엇갈립니다(한국어 `skill.md` / 영어 `SKILL.md`).
> 기본은 `SKILL.md`이며, 가져오기가 실패하면 `--lowercase`로 다시 만들어 보세요.

## 검증

```bash
python3 scripts/validate_skills.py
```

명세가 기계적으로 확인할 수 있는 것만 봅니다 — `name` 형식(소문자·숫자·하이픈,
64자, 디렉터리명과 일치), `description` 1,024자, `compatibility` 500자, 본문 500줄
권고, 상대 링크의 존재 여부입니다. 내용의 품질은 사람이 봐야 합니다.

## 스킬을 추가하실 때

1. `<skill-name>/SKILL.md`를 만듭니다. 디렉터리명과 `name`이 같아야 합니다
2. `description`에 **무엇을 하는지와 언제 쓰는지**를 모두 넣습니다. 모델은 스킬을
   과소 트리거하는 경향이 있으므로, 사용자가 실제로 쓸 표현("주담대 금리 비교",
   "기준금리 추이")을 키워드로 넣어 두세요
3. 본문은 500줄 이하로 씁니다. 넘치면 `references/`로 분리하고 SKILL.md에서
   **언제 읽어야 하는지**와 함께 링크합니다
4. `python3 scripts/validate_skills.py`로 검사합니다

## 왜 만들었나

Google 공식 스킬 카탈로그를 먼저 찾아봤는데, **금융 도메인 스킬이 없었습니다.**

| 카탈로그 | 스킬 수 | 금융 도메인 |
| --- | --- | --- |
| [google/skills](https://github.com/google/skills) | 127 (ads / analytics / cloud / developers) | 없음 |
| [google-gemini/gemini-skills](https://github.com/google-gemini/gemini-skills) | 4 (Gemini API 개발) | 없음 |

서드파티에는 금융 스킬이 있지만([OctagonAI/skills](https://github.com/OctagonAI/skills) 등)
대부분 미국 시장·SEC 기준이라 국내 규제와 데이터 소스에 맞지 않습니다.

작성 기준은 [google-gemini/gemini-skills](https://github.com/google-gemini/gemini-skills)의
구조와 서술 방식, [Agent Skills 명세](https://agentskills.io/specification),
[Gemini Enterprise 스킬 문서](https://docs.cloud.google.com/gemini/enterprise/docs/skills?hl=ko),
그리고 [anthropics/skills](https://github.com/anthropics/skills)의 `skill-creator`
지침입니다.

## 한계

- 여기 담긴 도메인 지식은 작성 시점(2026년 9월) 기준입니다. API 명세와 규제는 바뀝니다
- `kr-financial-ai-compliance`는 **법률 자문이 아닙니다.** 배포 전 준법감시인 검토가
  필요합니다
- 평가(eval) 세트는 아직 없습니다. 스킬 품질을 정량적으로 다루시려면
  [`skill-creator`](https://github.com/anthropics/skills/tree/main/skills/skill-creator)의
  eval 루프를 붙이는 것이 다음 단계입니다
