# MCP 검증 하네스

배포된 MCP 서버 9종과 `skills/`의 스킬 9종을 붙인 ADK 에이전트입니다.
시나리오를 사람 손을 거치지 않고 돌려 **도구 설명과 데이터 함정이 실제로
작동하는지** 확인합니다.

## 왜 필요한가

Gemini Enterprise는 **API로 MCP 도구를 부를 수 없습니다.** `streamAssist`는
호출되지만 커넥터 액션이 붙지 않습니다. 확인한 것:

```
readOnlyHint          69/69 도구에 true
DataConnector         9개 등록, 전부 ACTIVE
bapConfig             enabledActions에 도구명 전부 등재
엔진 dataStoreIds     MCP 9개 연결
actionSpec            actionDisabled=false로 명시해도 동일
자격증명              서비스 계정 · 사용자(ADC) 둘 다 동일
```

우리 쪽 설정은 다 맞는데도 "도구 미연결"이라고 답합니다. 원인은 API 스키마에
있습니다 — `Assistant.enabledTools`가 **"not implemented yet"**이고, 설명이
가리키는 `enabled_actions`는 Assistant 리소스에 없습니다. `toolsSpec`에도 MCP
항목이 없어 요청으로 켤 방법이 없습니다.

그래서 검증할 때마다 사람이 웹 UI 답변을 옮겨 붙여야 했습니다. 이 하네스가
그 자리를 대신합니다.

## 무엇이 옮겨지고 무엇이 안 옮겨지는가

**GE의 재현이 아닙니다.** 결과를 읽을 때 구분해야 합니다.

| 옮겨진다 | 안 옮겨진다 |
| --- | --- |
| 도구 이름·설명 | GE의 모델과 라우팅 |
| 카탈로그와 필터 동작 | 스킬 자동 선택 방식 |
| 서버가 붙이는 `warning` | 답변 문체 |
| 스킬 본문의 규칙 | |

지금까지 발견한 문제는 대부분 왼쪽이었습니다.

## 쓰는 법

```bash
export GOOGLE_CLOUD_PROJECT=<프로젝트>

python3 run.py "코스피 지수 최근 값 알려줘"

# 시나리오 파일 — 한 줄에 하나, #로 시작하면 주석
python3 run.py --file scenarios-single.txt --out results/single

# 멀티턴은 한 세션에서 이어 묻는다 ("이 회사" 같은 지시어가 풀린다)
python3 run.py --file scenarios-chain.txt --out results/chain --chain
```

`gcloud` 로그인이 필요합니다. MCP 서버는 Cloud Run IAM 인증이라 호출마다 신원
토큰을 붙입니다(만료 전 자동 갱신).

## 결과에 무엇이 남는가

답변만으로는 검증이 안 됩니다. **어떤 도구를 어떤 인자로 불렀는지**가 있어야
"필터가 걸렸나", "스킬을 읽었나", "경고를 봤나"를 판정할 수 있습니다.

```json
{
  "question": "...",
  "answer": "...",
  "tool_calls": [{"tool": "get_market_index", "args": {"params": {"idxNm": "코스피"}}}],
  "warnings": [{"tool": "get_dividend", "warning": "필터가 걸리지 않았습니다 — …"}],
  "elapsed_sec": 112.0
}
```

## 구조

| | |
| --- | --- |
| `harness/agent.py` | MCP 9종 연결. 시스템 지시는 `mcp/SYSTEM_PROMPT.md`를 **그대로** 읽는다 |
| `harness/skills.py` | `list_skills` / `read_skill` — 스킬 선택이 되는지도 검증 대상이라 전문을 지시에 넣지 않는다 |
| `harness/auth.py` | Cloud Run 신원 토큰 |
| `run.py` | 시나리오 실행과 기록 |

**`search_apis`·`call_api`는 6개 fsc 서버에 모두 있어 이름이 충돌합니다.** GE는
스토어가 나뉘어 괜찮지만 ADK는 한 목록으로 합칩니다. 도메인 도구는 **실제 이름을
그대로 두고**(이름 자체가 검증 대상입니다) 겹치는 둘만 서버 접두사를 붙입니다.
