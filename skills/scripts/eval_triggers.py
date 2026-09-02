#!/usr/bin/env python3
"""스킬이 실제로 발동하는지 잰다.

스킬은 본문이 아무리 좋아도 **읽히지 않으면 없는 것과 같다.** 선택은
`description`만 보고 이뤄지므로, 스킬을 고치면 발동 여부도 함께 바뀐다.
이 스크립트는 그 변화를 잡아낸다.

무엇을 재나
----------
질문을 주고 "무엇을 할지 계획을 세워라"라고만 한다. **스킬을 고르라고 유도하지
않는다.** 기본값은 MCP 도구 목록을 함께 제시하는 실전 조건이다 — 모델이 스킬을
건너뛰고 도구로 직행하는 것이 실제 위험이기 때문이다.

대조군(금융과 무관한 질문)도 함께 돌린다. 발동률만 보면 "전부 항상 읽는"
스킬이 만점을 받으므로, 안 붙어야 할 때 안 붙는지도 봐야 한다.

한계
----
- Gemini Enterprise의 실제 선택 메커니즘은 공개돼 있지 않다. 여기서 재는 것은
  **모델이 description을 읽고 고르는 경로**다. GE가 임베딩 검색을 쓴다면 결과가
  다를 수 있다.
- 질문은 사람이 만든다. description을 쓴 사람이 문제도 내면 편향이 생기므로,
  문서에 없는 말로 돌려 물은 질문을 일부러 섞었다.

사용법
------
    python3 scripts/eval_triggers.py                    # 실전 조건 1회
    python3 scripts/eval_triggers.py --repeat 3         # 변동성 확인
    python3 scripts/eval_triggers.py --no-tools         # 스킬만 제시
    python3 scripts/eval_triggers.py --model gemini-2.5-pro

프로젝트는 GOOGLE_CLOUD_PROJECT 또는 `gcloud config get-value project`에서 읽는다.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import pathlib
import re
import subprocess
import sys
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
MCP = ROOT.parent / "mcp"

# (질문, 발동해야 할 스킬). None이면 대조군 — 아무것도 붙지 않아야 한다.
# 앞 절반은 문서에 쓰인 표현, 뒤 절반은 일부러 돌려 물은 것이다.
CASES: list[tuple[str, str | None]] = [
    ("에코프로비엠이 코스닥 지수 대비 얼마나 언더퍼폼했어?", "kr-equity-analysis"),
    ("KODEX 골드선물 수익률이 금 시세랑 얼마나 벌어졌어?", "kr-equity-analysis"),
    ("포스코홀딩스 회사채의 국고채 3년 대비 스프레드 추이", "kr-macro-and-rates"),
    ("기준금리 인하 이후 예금 금리가 얼마나 내려왔어?", "kr-macro-and-rates"),
    ("한화오션 3년치 부채비율 추이 뽑아줘", "kr-corporate-financials"),
    ("고객이 삼성전자 실물 주권 입고를 요청했다. 처리해도 되나?", "kr-equity-operations"),
    ("온라인 주식거래 수수료를 증권사별로 비교해줘", "kr-product-comparison"),
    ("배당락일이 정확히 언제인지 어떻게 계산해?", "kr-market-calendar"),
    ("삼성전자 ISIN 코드가 뭐야?", "kr-entity-resolution"),
    ("금융 챗봇 만들 때 개인정보를 어떻게 처리해야 해?", "kr-financial-ai-compliance"),
    # 돌려 물은 것 — 스킬 설명에 없는 표현
    ("이 회사 빚이 너무 많은 거 아니야?", "kr-corporate-financials"),
    ("요즘 예금 넣으면 얼마나 받아?", "kr-product-comparison"),
    ("고객이 옛날 종이 주권을 들고 왔는데 받아도 되나", "kr-equity-operations"),
    ("작년 이맘때보다 삼성전자 얼마나 올랐어?", "kr-equity-analysis"),
    ("이 채권 사면 국채보다 얼마나 더 벌어?", "kr-macro-and-rates"),
    ("우리가 업계에서 몇 등이야?", "kr-product-comparison"),
    ("이거 언제까지 사야 배당 받을 수 있어?", "kr-equity-operations"),
    ("삼성전자랑 삼성전자우랑 다른 거야?", "kr-entity-resolution"),
    ("삼성전자 지금 사도 될까?", "kr-financial-ai-compliance"),
    # 대조군 — 아무것도 붙지 않아야 한다
    ("오늘 점심 뭐 먹을까?", None),
    ("파이썬에서 리스트 정렬하는 법 알려줘", None),
    ("이번 주 서울 날씨 어때?", None),
]

PROMPT = """너는 한국 금융 데이터 어시스턴트다. 아래를 쓸 수 있다.
{tools}
## 스킬 (답하기 전에 읽을 수 있는 참고 문서)

{skills}

사용자: "{q}"

무엇을 할지 계획을 JSON으로만 답한다. 다른 말은 하지 않는다.
{{"skills": [읽을 스킬 name], "tools": [호출할 도구 이름]}}"""


def load_skills() -> list[tuple[str, str]]:
    out = []
    for p in sorted(ROOT.glob("*/SKILL.md")):
        front = p.read_text(encoding="utf-8").split("---")[1]
        name = re.search(r"^name:\s*(.+)$", front, re.M)
        desc = re.search(r"^description:\s*(.+)$", front, re.M)
        if name and desc:
            out.append((name.group(1).strip(), desc.group(1).strip()))
    return out


def load_tools() -> list[str]:
    """MCP 서버의 도구 이름과 첫 줄 설명. 없으면 빈 목록."""
    out = []
    for p in sorted(MCP.glob("*-mcp-server/server.py")):
        srv = p.parent.name.replace("-mcp-server", "")
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and any(
                isinstance(d, ast.Call) and getattr(d.func, "attr", "") == "tool"
                for d in node.decorator_list
            ):
                doc = (ast.get_docstring(node) or "").splitlines()
                out.append(f"- {srv}.{node.name}: {doc[0] if doc else ''}")
    return out


def project_id() -> str:
    pid = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if pid:
        return pid
    r = subprocess.run(["gcloud", "config", "get-value", "project"],
                       capture_output=True, text=True)
    pid = r.stdout.strip()
    if not pid or pid == "(unset)":
        sys.exit("프로젝트를 찾지 못했습니다. GOOGLE_CLOUD_PROJECT를 설정하거나 "
                 "gcloud config set project <ID>를 실행하세요.")
    return pid


def ask(pid: str, model: str, prompt: str, token: str, temp: float) -> dict:
    url = (f"https://aiplatform.googleapis.com/v1/projects/{pid}/locations/global"
           f"/publishers/google/models/{model}:generateContent")
    body = json.dumps({
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temp},
    }).encode()
    req = urllib.request.Request(url, data=body, headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.load(r)
    except urllib.error.HTTPError as exc:
        sys.exit(f"Vertex AI 호출 실패 ({exc.code}): {exc.read()[:300].decode(errors='replace')}")
    try:
        txt = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        return {"skills": [], "tools": []}
    m = re.search(r"\{.*\}", txt, re.S)
    if not m:
        return {"skills": [], "tools": []}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"skills": [], "tools": []}


def main() -> int:
    ap = argparse.ArgumentParser(description="스킬 발동 여부를 잰다")
    ap.add_argument("--model", default="gemini-2.5-flash")
    ap.add_argument("--repeat", type=int, default=1, help="질문당 반복 횟수")
    ap.add_argument("--temperature", type=float, default=1.0)
    ap.add_argument("--no-tools", action="store_true",
                    help="MCP 도구 목록을 빼고 스킬만 제시한다")
    args = ap.parse_args()

    skills = load_skills()
    if not skills:
        sys.exit("스킬을 찾지 못했습니다.")
    names = {n for n, _ in skills}
    missing = {e for _, e in CASES if e and e not in names}
    if missing:
        print(f"경고: 케이스가 없는 스킬을 가리킵니다 — {', '.join(sorted(missing))}\n")

    tools = [] if args.no_tools else load_tools()
    tools_block = ("## 도구 (MCP)\n\n" + "\n".join(tools) + "\n\n") if tools else "\n"
    skills_block = "\n\n".join(f"- {n}: {d}" for n, d in skills)

    pid = project_id()
    token = subprocess.run(["gcloud", "auth", "print-access-token"],
                           capture_output=True, text=True).stdout.strip()
    if not token:
        sys.exit("액세스 토큰을 얻지 못했습니다. gcloud auth login을 먼저 실행하세요.")

    cond = "스킬만" if args.no_tools else f"도구 {len(tools)}개와 함께"
    print(f"모델 {args.model} · 스킬 {len(skills)}종 · {cond} · "
          f"temperature {args.temperature} · 질문당 {args.repeat}회\n")

    n = args.repeat
    pos_hit = pos_tot = neg_ok = neg_tot = 0
    for q, exp in CASES:
        hits = 0
        for _ in range(n):
            got = set(ask(pid, args.model, PROMPT.format(
                tools=tools_block, skills=skills_block, q=q), token,
                args.temperature).get("skills") or [])
            hits += (not got) if exp is None else (exp in got)
        bar = "●" * hits + "○" * (n - hits)
        if exp is None:
            neg_ok += hits; neg_tot += n
            print(f"  {bar} {hits}/{n}  [대조군] {q[:32]:<34}")
        else:
            pos_hit += hits; pos_tot += n
            print(f"  {bar} {hits}/{n}  {q[:32]:<34} → {exp}")

    print(f"\n  발동   {pos_hit}/{pos_tot} ({pos_hit / pos_tot * 100:.0f}%)")
    print(f"  대조군 {neg_ok}/{neg_tot} ({neg_ok / neg_tot * 100:.0f}%) — 안 붙어야 할 때 안 붙음")
    return 0 if pos_hit == pos_tot and neg_ok == neg_tot else 1


if __name__ == "__main__":
    sys.exit(main())
