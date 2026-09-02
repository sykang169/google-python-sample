# 금융권 Agent Skills

국내 금융 업무에서 **AI가 자주 틀리는 것들을 정리한 규칙 모음**입니다.

스킬(Agent Skill)은 AI가 필요할 때 꺼내 읽는 참고 문서입니다. 질문에 맞는 스킬이
자동으로 선택되어, AI가 답하기 전에 그 분야의 규칙을 먼저 확인하게 됩니다.

[Agent Skills 표준](https://agentskills.io/specification)을 따르므로 **특정 도구에
묶여 있지 않습니다.** Antigravity, Gemini CLI, Claude Code, Cursor, Codex CLI,
GitHub Copilot, Gemini Enterprise에서 같은 파일을 그대로 씁니다 — 두는 위치만
다릅니다([설치](#설치) 참고). 스킬 기능이 없는 도구를 위한 경로도 있습니다.

여기 담은 8종은 **데이터를 어떻게 가져오는지가 아니라, 가져온 다음 어떻게 읽어야
하는지**를 다룹니다.

## 어떤 실수를 막나

아래 세 가지는 모두 **오류가 나지 않습니다.** API는 정상 응답을 주고, AI도
자신 있게 답합니다. 검토하는 사람이 원자료를 다시 뽑아 보기 전까지는 틀린 줄
모릅니다.

**"이 종목 시장 대비 얼마나 올랐어?"**

시장 대비 수익률은 종목 수익률에서 지수 수익률을 빼서 구합니다. 그런데 코스닥
종목을 코스피 지수와 빼도 계산은 그대로 됩니다. 두 지수는 다르게 움직이기 때문에
값이 달라지고, 때로는 플러스가 마이너스로 바뀝니다. 답변에는 "지수 대비 몇 %p"만
남고 **어느 지수를 썼는지는 적히지 않습니다.**

**"이 회사 부채비율 얼마야?"**

은행은 고객이 맡긴 예금이 회계상 부채입니다. 그래서 부채비율이 제조업 기준으로는
위험해 보이는 수준이어도 은행에서는 정상입니다. **계산도 맞고 숫자도 맞는데
결론만 틀립니다.**

**"예금 금리 제일 높은 곳 알려줘"**

은행이 공시하는 금리는 두 가지입니다. 기본금리, 그리고 급여이체나 카드 실적 같은
조건을 다 채웠을 때 받는 최고우대금리입니다. 최고우대금리만 뽑아서 "이 은행이
가장 높다"고 안내하면, 조건을 못 채우는 고객에게는 **사실과 다른 안내**가 됩니다.

이런 실수를 막는 규칙만 모았습니다.

## 어떤 질문에 어떤 스킬이 쓰이나

**업무 스킬 5종** — 데이터가 어디서 오는지가 아니라, **실무에서 하는 일**로
나눴습니다. 질문 하나가 여러 데이터 소스를 넘나드는 경우가 많기 때문입니다.

| 스킬 | 이런 질문에 | 필요한 데이터 |
| --- | --- | --- |
| [`kr-equity-analysis`](kr-equity-analysis/) | "삼성전자 지난달 수익률", "코스피 대비 초과수익", "금 ETF 괴리" | 시세 |
| [`kr-macro-and-rates`](kr-macro-and-rates/) | "기준금리 추이", "국고채 대비 스프레드", "CP 91일물" | 거시 시계열 + 채권 |
| [`kr-corporate-financials`](kr-corporate-financials/) | "부채비율 3년 추이", "유상증자 공시 원문", "사외이사 몇 명" | 재무제표 + 전자공시 |
| [`kr-product-comparison`](kr-product-comparison/) | "예금 금리 제일 높은 곳", "증권사 수수료 비교", "펀드 판매 점유율" | 상품 금리 + 업계 통계 |
| [`kr-equity-operations`](kr-equity-operations/) | "배당 기준일", "사고주권 조회", "대차잔고" | 권리·대차 |

**공통 스킬 3종** — 어떤 질문이든 밑에 깔리는 것들입니다. 업무 스킬들은 이 셋을
링크로 가리키기만 하고, 같은 내용을 다시 적지 않습니다.

| 스킬 | 다루는 것 |
| --- | --- |
| [`kr-market-calendar`](kr-market-calendar/) | 휴장일·영업일, 배당락·권리락, 결산월과 공시 제출기한 |
| [`kr-entity-resolution`](kr-entity-resolution/) | 종목·회사를 코드로 확정하기 (ISIN, 법인등록번호 등) |
| [`kr-financial-ai-compliance`](kr-financial-ai-compliance/) | 금융권 AI 규제 가드레일 (설계용 문서) |

날짜와 종목 코드를 따로 뽑은 이유는 **틀렸을 때 아무 신호가 없기 때문**입니다.
주말이나 공휴일 날짜로 시세를 조회하면 에러가 아니라 빈 결과가 옵니다.
"삼성전자"로 검색하면 삼성전자우(우선주)가 함께 딸려 오는데 경고가 없습니다.
이런 규칙을 여러 스킬에 나눠 적으면 하나만 고쳤을 때 서로 다른 말을 하게 되므로,
한 곳에 모았습니다.

> [!NOTE]
> `kr-financial-ai-compliance`는 **에이전트를 만들 때 참고하는 문서**입니다.
> 투자권유 금지 같은 규제는 답변할 때마다 지켜져야 하는데, 스킬은 질문에 따라
> 선택적으로만 읽힙니다. 그래서 실제 답변에 항상 적용되는 규칙은 스킬이 아니라
> 시스템 프롬프트에 두었습니다
> ([`../mcp/SYSTEM_PROMPT.md`](../mcp/SYSTEM_PROMPT.md)).

## 무엇을 담고 무엇을 담지 않나

각 스킬이 답하는 질문은 "이 API를 어떻게 호출하는가"가 아니라 **"어떤 답이
그럴듯한데 틀렸는가"**입니다.

**담는 것**

- **코드를 기억으로 쓰지 말 것** — 통계표 번호나 공시 API 이름을 짐작해서 쓰면
  에러가 아니라 *엉뚱한 데이터*가 돌아옵니다
- **비교를 설계하는 법** — 만기가 다른 채권끼리, 시장이 다른 지수와, 금액 구간이
  다른 수수료끼리 비교하면 숫자는 나오지만 답은 아닙니다
- **이 데이터에 없는 것** — ETF는 주식시세 API에 없고, 개별 은행 금리는 한국은행
  통계에 없습니다
- **해석이 갈리는 지점** — 연결재무제표와 별도재무제표, 지수와 상승률, 기본금리와
  우대금리, 대차잔고와 공매도
- **출처와 기준일** — 금융에서 시점 없는 숫자는 틀린 숫자입니다

**담지 않는 것.** 아래는 각각 더 나은 자리가 있습니다. 스킬에도 적어 두면 한쪽만
고쳤을 때 서로 다른 말을 하게 됩니다.

| 지식 | 있어야 할 곳 | 왜 |
| --- | --- | --- |
| 조회 조건으로 쓸 수 있는 항목 이름 | MCP 서버의 `search_apis` 응답 | 실제 호출로 수집한 값이라 API가 바뀌어도 어긋나지 않습니다 |
| 오류 코드와 대응 방법 | 서버가 오류 메시지에 함께 담아 보냅니다 | 오류가 났을 때만 필요하고, 그때 바로 도착합니다 |
| 어떤 도구를 쓸지 | 도구 이름과 설명 | AI가 도구를 고를 때 반드시 읽는 자리입니다 |
| 답변 형식, 규제 가드레일 | 시스템 프롬프트 | 질문과 무관하게 항상 적용돼야 합니다 |

## 데이터는 어디서 오나

스킬에는 규칙만 있고 데이터는 없습니다. 데이터는 이 저장소의
[MCP 서버 8종](../mcp)이 가져옵니다. **다른 방법으로 같은 데이터를 조회하더라도
스킬은 그대로 쓸 수 있습니다.**

| 스킬 | 이 저장소의 짝 |
| --- | --- |
| `kr-equity-analysis` | [`fsc-market-mcp-server`](../mcp/fsc-market-mcp-server) |
| `kr-macro-and-rates` | [`ecos-mcp-server`](../mcp/ecos-mcp-server) + [`fsc-ficc-mcp-server`](../mcp/fsc-ficc-mcp-server) |
| `kr-corporate-financials` | [`fsc-research-mcp-server`](../mcp/fsc-research-mcp-server) + [`dart-mcp-server`](../mcp/dart-mcp-server) |
| `kr-product-comparison` | [`finlife-mcp-server`](../mcp/finlife-mcp-server) + [`fsc-industry-mcp-server`](../mcp/fsc-industry-mcp-server) |
| `kr-equity-operations` | [`fsc-equity-ops-mcp-server`](../mcp/fsc-equity-ops-mcp-server) |

실제 질문이 이 스킬들을 어떻게 넘나드는지는
[`../mcp/SCENARIOS.md`](../mcp/SCENARIOS.md)에 데스크별 시나리오 13개로 있습니다.

## 설치

스킬 형식([Agent Skills](https://agentskills.io/specification))은 도구마다 같고
**두는 위치만 다릅니다.** 스크립트에 경로를 주면 8종을 연결합니다.

```bash
cd skills
./scripts/install.sh                    # 설치 가능한 위치를 보여줍니다
./scripts/install.sh .agents/skills     # 그 경로에 연결
```

기본은 심볼릭 링크입니다. 저장소를 업데이트하면 스킬도 함께 갱신됩니다. 저장소를
지우거나 옮길 예정이면 `--copy`를 쓰세요.

### 어느 경로에 넣나

**`.agents/skills/`가 가장 넓게 통합니다** — Antigravity와 Gemini CLI가 같은
경로를 봅니다.

| 경로 | 도구 |
| --- | --- |
| `.agents/skills` | [Antigravity](https://antigravity.google/docs/ide/skills/), [Gemini CLI](https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/using-agent-skills.md) — 이 프로젝트에서만 |
| `~/.agents/skills` | Gemini CLI — 모든 프로젝트 |
| `.claude/skills` | Claude Code — 이 프로젝트에서만 |
| `~/.claude/skills` | Claude Code — 모든 프로젝트 |
| `.gemini/skills` | Gemini CLI 구 경로. `.agents` 쪽이 우선합니다 |

Cursor, Codex CLI, GitHub Copilot도 `SKILL.md`를 읽습니다. 경로만 각 도구 문서에서
확인해 인자로 주면 되고, **파일은 고칠 필요가 없습니다.**

> [!NOTE]
> 경로는 2026년 9월 기준입니다. 도구가 바뀌면 위 표보다 각 도구 문서가 맞습니다.

### 스킬 기능이 없는 도구라면

저장소 루트의 [`AGENTS.md`](../AGENTS.md)에 **질문 유형 → 읽을 파일** 표를 넣어
두었습니다. `AGENTS.md`는 여러 도구가 공통으로 읽는 파일이라, 스킬을 지원하지
않는 환경에서도 라우팅이 됩니다.

그것도 안 되면 해당 `SKILL.md`를 대화에 그대로 붙여넣어도 됩니다. 스킬은 특별한
실행 형식이 아니라 **마크다운 문서**입니다.

### API를 직접 호출한다면

시스템 프롬프트에 스킬 8종의 `description`만 목록으로 넣고, 모델이 고른 스킬의
본문을 그때 이어붙이는 방식이 가장 효율적입니다. 8종 전부를 항상 넣으면 약
23,000토큰을 매 호출 지불하게 됩니다(`description`만이면 2,000토큰 남짓).

### Gemini Enterprise

올리는 방법이 두 가지입니다.

어느 쪽이든 먼저 패키징 스크립트를 돌려야 합니다. Gemini Enterprise는 `references/`
폴더를 읽지 않기 때문입니다(필요할 때만 꺼내 읽는 기능이 없습니다). 스크립트가
참조 문서를 `SKILL.md` 끝에 부록으로 붙여서 내용이 빠지지 않게 합니다.

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

형식만 검사합니다. 이름 규칙(소문자·숫자·하이픈, 64자 이내, 폴더명과 일치),
`description` 1,024자, `compatibility` 500자, 본문 500줄 권고, 그리고 문서 안의
링크가 실제로 존재하는지입니다.

**내용이 맞는지는 검사하지 못합니다.** 그건 사람이 읽어야 합니다.

### 스킬이 실제로 발동하는지

본문이 아무리 좋아도 **읽히지 않으면 없는 것과 같습니다.** 선택은 `description`만
보고 이뤄지므로, 스킬을 고치면 발동 여부도 함께 바뀝니다.

```bash
python3 scripts/eval_triggers.py              # 실전 조건 1회
python3 scripts/eval_triggers.py --repeat 3   # 같은 질문을 3번씩, 변동성 확인
```

질문을 주고 "무엇을 할지 계획을 세워라"라고만 합니다. **스킬을 고르라고 유도하지
않고**, MCP 도구 55개를 함께 제시합니다 — 모델이 스킬을 건너뛰고 도구로 직행하는
것이 실제 위험이기 때문입니다. 금융과 무관한 질문(대조군)도 함께 돌립니다.
발동률만 보면 "항상 읽히는" 스킬이 만점을 받으므로, 안 붙어야 할 때 안 붙는지도
봐야 합니다.

Vertex AI Gemini를 호출하므로 `gcloud auth login`과 프로젝트 설정이 필요합니다.

> [!NOTE]
> Gemini Enterprise의 실제 선택 메커니즘은 공개돼 있지 않습니다. 이 스크립트가
> 재는 것은 **모델이 `description`을 읽고 고르는 경로**입니다. GE가 임베딩 검색을
> 쓴다면 결과가 다를 수 있습니다.

현재 8종 기준 측정값(`gemini-2.5-flash`, 도구 55개와 함께, temperature 1.0):
질문 19개 발동 100%, 대조군 3개 오발동 0건. 같은 조건에서 3회 반복해도 24/24로
같았습니다.

## 스킬을 추가하실 때

1. `<skill-name>/SKILL.md`를 만듭니다. 디렉터리명과 `name`이 같아야 합니다
2. `description`에 **무엇을 하는지**와 **언제 읽어야 하는지**를 모두 씁니다.
   스킬 선택은 본문이 아니라 `description`만 보고 이뤄지므로, 사용자가 실제로
   입력할 법한 말("주담대 금리 비교", "기준금리 추이")을 그대로 넣어 둡니다.
   추가한 뒤에는 `eval_triggers.py`에 케이스를 넣고 실제로 발동하는지 확인합니다
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
- 평가는 **발동 여부만** 봅니다(`eval_triggers.py`). 스킬을 읽은 뒤 답이 실제로
  나아지는지는 재지 않습니다. 그건
  [`skill-creator`](https://github.com/anthropics/skills/tree/main/skills/skill-creator)의
  eval 루프처럼 답변 품질을 채점하는 단계가 따로 필요합니다
