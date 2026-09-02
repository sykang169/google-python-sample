# 금융권 Agent Skills

한국 금융 도메인용 [Agent Skills](https://agentskills.io/specification) 모음입니다.
Claude Code, Gemini CLI, Gemini Enterprise 등 스킬 표준을 지원하는 에이전트에서 쓸 수
있습니다.

## 왜 만들었나

Google 공식 스킬 카탈로그를 먼저 찾아봤는데, **금융 도메인 스킬이 없었습니다.**

| 카탈로그 | 스킬 수 | 금융 도메인 |
| --- | --- | --- |
| [google/skills](https://github.com/google/skills) | 127 (ads / analytics / cloud / developers) | 없음 |
| [google-gemini/gemini-skills](https://github.com/google-gemini/gemini-skills) | 4 (Gemini API 개발) | 없음 |

서드파티에는 금융 스킬이 있지만([OctagonAI/skills](https://github.com/OctagonAI/skills) 등)
대부분 미국 시장·SEC 기준이라 국내 규제와 데이터 소스에 맞지 않습니다. 그래서 이
저장소의 MCP 서버([`../mcp`](../mcp))와 국내 규제 환경에 맞춰 직접 만들었습니다.

작성 기준은 [google-gemini/gemini-skills](https://github.com/google-gemini/gemini-skills)의
구조와 서술 방식, [Agent Skills 명세](https://agentskills.io/specification),
[Gemini Enterprise 스킬 문서](https://docs.cloud.google.com/gemini/enterprise/docs/skills?hl=ko),
그리고 [anthropics/skills](https://github.com/anthropics/skills)의 `skill-creator`
지침입니다.

## 스킬 목록

| 스킬 | 다루는 것 | 짝이 되는 MCP 서버 |
| --- | --- | --- |
| [`krx-stock-quote-analysis`](krx-stock-quote-analysis/) | 주식·지수·ETF·ETN·채권 시세, 초과수익률 | `mcp/fsc-market-mcp-server` |
| [`kr-bond-ficc-analysis`](kr-bond-ficc-analysis/) | 채권 발행·권리일정·콜, CP/CD 실거래 금리, DCM | `mcp/fsc-ficc-mcp-server` |
| [`kr-corporate-research`](kr-corporate-research/) | 정규화 재무제표, 계열사, 공시 33종 | `mcp/fsc-research-mcp-server` |
| [`kr-equity-operations`](kr-equity-operations/) | 배당·권리일정·사고주권·대차·REPO | `mcp/fsc-equity-ops-mcp-server` |
| [`kr-securities-industry-benchmark`](kr-securities-industry-benchmark/) | 펀드·퇴직연금·증권사 경영지표·수수료·금투협 통계 | `mcp/fsc-industry-mcp-server` |
| [`dart-disclosure-analysis`](dart-disclosure-analysis/) | 전자공시 원문·XBRL·사업보고서 | `mcp/dart-mcp-server` |
| [`ecos-macro-analysis`](ecos-macro-analysis/) | 한국은행 ECOS — 기준금리·환율·물가 시계열 | `mcp/ecos-mcp-server` |
| [`finlife-product-comparison`](finlife-product-comparison/) | 예적금·대출 금리 비교 | `mcp/finlife-mcp-server` |
| [`kr-financial-ai-compliance`](kr-financial-ai-compliance/) | 금융권 AI 규제 가드레일 | (없음, 횡단 스킬) |

앞의 넷은 **데이터 스킬**이고 마지막 하나는 **횡단 스킬**입니다. 데이터 스킬은 각자
마지막 절에서 규제 스킬을 참조합니다. 금융 수치를 사용자에게 내보내는 순간 규제
경계가 걸리기 때문입니다.

## 설계 원칙

각 스킬은 "이 API를 어떻게 호출하는가"가 아니라 **"모델이 무엇을 조용히
틀리는가"**를 중심으로 썼습니다. 도구 시그니처는 MCP 서버의 설명에 이미 있으므로
반복하지 않고, 대신 다음을 담았습니다.

- **코드를 기억에서 쓰지 말 것** — ECOS `stat_code`나 DART 엔드포인트명은 추측하면
  오류가 아니라 *다른 데이터*가 돌아옵니다
- **오류가 아닌 실패** — HTTP 200과 함께 오는 `status 013`, `INFO-200`,
  `resultCode 03`은 대부분 재시도로 풀리는 조건 문제입니다
- **수록 범위 밖** — ETF는 주식시세 API에 없고, 개별 회사 금리는 ECOS에 없습니다
- **해석의 함정** — 연결/별도, 지수와 상승률, 기본금리와 우대금리, 액면분할, 휴장일
- **출처와 기준시점을 반드시 함께** — 금융 답변에서 시점 없는 숫자는 틀린 숫자입니다

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

## 한계

- 여기 담긴 도메인 지식은 작성 시점(2026년 9월) 기준입니다. API 명세와 규제는 바뀝니다
- `kr-financial-ai-compliance`는 **법률 자문이 아닙니다.** 배포 전 준법감시인 검토가
  필요합니다
- 평가(eval) 세트는 아직 없습니다. 스킬 품질을 정량적으로 다루시려면
  [`skill-creator`](https://github.com/anthropics/skills/tree/main/skills/skill-creator)의
  eval 루프를 붙이는 것이 다음 단계입니다
