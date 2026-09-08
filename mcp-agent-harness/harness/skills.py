"""`skills/`의 SKILL.md를 ADK 도구로 노출한다.

Gemini Enterprise는 질문에 맞는 스킬을 자동으로 골라 읽는다. ADK에는 그 기능이
없으므로 같은 모양을 도구로 만든다 — 목록을 보여 주고, 고른 것을 읽어 준다.

전문을 시스템 지시에 다 넣지 않는 이유가 있다. 9종을 합치면 수만 자라 매 호출에
실리고, 무엇보다 **스킬이 제때 선택되는지**를 확인할 수 없게 된다. 프런트매터의
description이 실제로 발동을 일으키는지가 검증 대상이다.
"""
from __future__ import annotations

import pathlib
import re

SKILLS_DIR = pathlib.Path(__file__).resolve().parents[2] / "skills"


def _frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    head, body = text[3:end], text[end + 4:]
    meta, key = {}, None
    for line in head.splitlines():
        m = re.match(r"^([a-zA-Z_]+):\s*(.*)$", line)
        if m:
            key, meta[key] = m.group(1), m.group(2).strip()
        elif key and line.startswith("  "):        # 여러 줄 값
            meta[key] += " " + line.strip()
    return meta, body


def _load() -> dict[str, dict[str, str]]:
    out = {}
    for d in sorted(SKILLS_DIR.glob("kr-*")):
        f = d / "SKILL.md"
        if not f.exists():
            continue
        meta, body = _frontmatter(f.read_text(encoding="utf-8"))
        out[meta.get("name") or d.name] = {
            "description": meta.get("description", ""),
            "body": body.strip(),
        }
    return out


SKILLS = _load()


def list_skills() -> dict:
    """사용 가능한 스킬과 각각 어떤 질문에 쓰이는지 돌려준다.

    금융 데이터 질문에 답하기 전에 **먼저 호출한다.** 설명을 읽고 해당하는
    스킬을 read_skill로 읽은 뒤에 도구를 부른다. 스킬에는 그 도메인에서
    조용히 틀리는 함정이 정리되어 있다.
    """
    return {"skills": [{"name": n, "description": s["description"]}
                       for n, s in SKILLS.items()]}


def read_skill(name: str) -> dict:
    """스킬 전문을 읽는다. list_skills가 준 이름을 그대로 준다.

    Args:
        name: 스킬 이름 (예: kr-equity-analysis).
    """
    s = SKILLS.get(name)
    if s is None:
        return {"error": f"'{name}' 스킬이 없습니다.",
                "available": sorted(SKILLS)}
    return {"name": name, "content": s["body"]}
