# 이 저장소에서 작업할 때

한국 금융 공공데이터를 다루는 MCP 서버 8종과 Agent Skills 8종이 들어 있습니다.
`AGENTS.md`는 여러 에이전트 도구가 공통으로 읽는 파일이라, 스킬 기능이 없는
도구에서도 아래 라우팅은 적용됩니다.

## 금융 데이터 질문에 답하기 전에

**스킬을 지원하는 도구**(Claude Code, Antigravity, Gemini CLI, Cursor, Codex,
GitHub Copilot 등)는 `skills/`가 연결돼 있으면 알아서 고릅니다. 연결은
`skills/scripts/install.sh`로 합니다.

**스킬 기능이 없는 도구**는 아래 표에서 해당 파일을 직접 읽고 시작하세요.

| 질문이 이런 것이면 | 먼저 읽을 것 |
| --- | --- |
| 주가·수익률·초과수익률·변동성·ETF | [`skills/kr-equity-analysis/SKILL.md`](skills/kr-equity-analysis/SKILL.md) |
| 기준금리·환율·물가, 채권 스프레드·CP/CD·REPO | [`skills/kr-macro-and-rates/SKILL.md`](skills/kr-macro-and-rates/SKILL.md) |
| 재무제표·재무비율·공시·계열사 | [`skills/kr-corporate-financials/SKILL.md`](skills/kr-corporate-financials/SKILL.md) |
| 예적금·대출 금리, 펀드·수수료·업계 비교 | [`skills/kr-product-comparison/SKILL.md`](skills/kr-product-comparison/SKILL.md) |
| 배당 기준일·권리일정·사고주권·대차 | [`skills/kr-equity-operations/SKILL.md`](skills/kr-equity-operations/SKILL.md) |
| 날짜·기간·휴장일·배당락·결산월 | [`skills/kr-market-calendar/SKILL.md`](skills/kr-market-calendar/SKILL.md) |
| 종목·회사를 코드로 확정 (ISIN, 법인번호) | [`skills/kr-entity-resolution/SKILL.md`](skills/kr-entity-resolution/SKILL.md) |
| 금융 AI 규제·개인정보·감사 로그 설계 | [`skills/kr-financial-ai-compliance/SKILL.md`](skills/kr-financial-ai-compliance/SKILL.md) |

날짜와 종목 코드는 거의 모든 질문에 걸립니다. 뒤의 둘은 다른 스킬과 함께 읽습니다.

## 답변에 항상 적용되는 것

질문 종류와 무관하게 지켜야 합니다. 어시스턴트를 배포할 때는
[`mcp/SYSTEM_PROMPT.md`](mcp/SYSTEM_PROMPT.md)를 시스템 지시로 넣으세요.

- **출처와 기준일을 밝힙니다.** 금융에서 시점 없는 숫자는 틀린 숫자입니다
- **조회 실패를 "해당 없음"으로 바꾸지 않습니다.** 특히 사고주권·배당 기준일은
  실패를 데이터 없음으로 답하면 업무 사고가 됩니다
- **투자권유를 하지 않습니다.** 조회한 사실과 판단 기준까지가 범위입니다
- **비교를 편향되게 설계하지 않습니다.** 유리한 지표만 고르지 않습니다
- **개인 식별정보를 도구 인자나 답변에 넣지 않습니다**

## 코드를 고칠 때

- `mcp/fsc-*-mcp-server/`의 `server.py` · `fsc_core.py` · `catalog.json` ·
  `README.md`는 **생성물입니다.** 직접 고치지 말고 `mcp/fsc-common/`의 원본
  (`servers.py`, `fsc_core.py`)을 고친 뒤 `python3 mcp/fsc-common/sync.py`를
  실행하세요. 생성물만 고치면 다음 sync에서 조용히 사라집니다
- 스킬을 고쳤으면 `python3 skills/scripts/validate_skills.py`로 형식을,
  `python3 skills/scripts/eval_triggers.py`로 발동 여부를 확인하세요
- 문서에 적힌 숫자(서버 수, 도구 수, 스킬 수)는 실제 파일을 세어 확인하세요.
  과거에 여러 번 어긋난 적이 있습니다

## 문서 어디에 무엇이 있나

| | |
| --- | --- |
| [`mcp/README.md`](mcp/README.md) | 서버 배포와 Gemini Enterprise 연결 |
| [`mcp/SYSTEM_PROMPT.md`](mcp/SYSTEM_PROMPT.md) | 어시스턴트 시스템 지시 초안 |
| [`mcp/SCENARIOS.md`](mcp/SCENARIOS.md) | 데스크별 질문 시나리오 13개 |
| [`skills/README.md`](skills/README.md) | 스킬 설치·검증·작성 |
