#!/usr/bin/env python3
"""시나리오를 돌려 답변과 **도구 호출 기록**을 남긴다.

답변만 봐서는 검증이 안 된다. 어떤 도구를 어떤 인자로 불렀는지가 있어야
"필터가 걸렸나", "스킬을 읽었나", "warning을 봤나"를 판정할 수 있다.

    python3 run.py "삼성전자 지난달 종가 추이 보여줘"
    python3 run.py --file scenarios.txt --out results/
"""
from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from google.adk.runners import InMemoryRunner          # noqa: E402
from google.genai import types                          # noqa: E402

from harness.agent import root_agent                    # noqa: E402


async def ask(question: str, ctx: dict | None = None) -> dict:
    """ctx를 주면 그 세션을 이어 쓴다 — 멀티턴 시나리오는 앞 턴의 결과를
    기억해야 "이 회사" 같은 지시어가 풀린다."""
    if ctx is not None and ctx.get("runner") is not None:
        runner, session_id = ctx["runner"], ctx["session_id"]
    else:
        runner = InMemoryRunner(agent=root_agent, app_name="harness")
        session_id = (await runner.session_service.create_session(
            app_name="harness", user_id="verify")).id
        if ctx is not None:
            ctx["runner"], ctx["session_id"] = runner, session_id
    started = time.time()
    answer, calls, warnings = [], [], []
    async for ev in runner.run_async(
        user_id="verify", session_id=session_id,
        new_message=types.Content(role="user",
                                  parts=[types.Part(text=question)]),
    ):
        for part in (getattr(ev.content, "parts", None) or []):
            if getattr(part, "function_call", None):
                fc = part.function_call
                calls.append({"tool": fc.name,
                              "args": json.loads(json.dumps(dict(fc.args or {}),
                                                            default=str))})
            if getattr(part, "function_response", None):
                resp = part.function_response.response
                w = (resp or {}).get("warning") if isinstance(resp, dict) else None
                if w:
                    warnings.append({"tool": part.function_response.name,
                                     "warning": w})
            if getattr(part, "text", None) and ev.is_final_response():
                answer.append(part.text)
    return {
        "question": question,
        "answer": "".join(answer),
        "tool_calls": calls,
        "warnings": warnings,
        "elapsed_sec": round(time.time() - started, 1),
    }


def report(r: dict) -> None:
    print(f"\n{'='*70}\nQ: {r['question']}\n{'='*70}")
    print(f"\n도구 호출 {len(r['tool_calls'])}회 · {r['elapsed_sec']}초")
    for c in r["tool_calls"]:
        args = json.dumps(c["args"], ensure_ascii=False)
        print(f"   {c['tool']:<32} {args[:110]}")
    if r["warnings"]:
        print(f"\n서버 경고 {len(r['warnings'])}건")
        for w in r["warnings"]:
            print(f"   [{w['tool']}] {w['warning'][:130]}")
    print(f"\n--- 답변 ---\n{r['answer']}")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("question", nargs="*")
    ap.add_argument("--file", help="한 줄에 하나씩 질문이 든 파일")
    ap.add_argument("--out", help="결과 JSON을 저장할 디렉터리")
    ap.add_argument("--chain", action="store_true",
                    help="모든 질문을 한 세션에서 이어 묻는다 (멀티턴 시나리오)")
    args = ap.parse_args()

    questions = [" ".join(args.question)] if args.question else []
    if args.file:
        questions += [l.strip() for l in pathlib.Path(args.file).read_text(
            encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
    if not questions:
        sys.exit("질문을 주거나 --file을 쓰세요.")

    outdir = pathlib.Path(args.out) if args.out else None
    if outdir:
        outdir.mkdir(parents=True, exist_ok=True)
    ctx: dict | None = {} if args.chain else None
    for i, q in enumerate(questions, 1):
        r = await ask(q, ctx)
        report(r)
        if outdir:
            p = outdir / f"{i:02d}.json"
            p.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"\n→ {p}")


if __name__ == "__main__":
    asyncio.run(main())
