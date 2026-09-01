#!/usr/bin/env python3
"""SKILL.md가 Agent Skills 명세(https://agentskills.io/specification)를 지키는지 검사한다.

사용법:
    python3 scripts/validate_skills.py            # skills/ 전체
    python3 scripts/validate_skills.py <스킬경로>  # 하나만

의존성 없이 동작하도록 YAML 파서를 쓰지 않고 frontmatter를 직접 읽는다.
검사하는 것은 명세가 기계적으로 확인 가능하다고 정한 항목뿐이다 —
내용의 품질은 사람이 본다.
"""

from __future__ import annotations

import pathlib
import re
import sys

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

# 명세가 정한 상한. body 500줄은 권고치이므로 경고로만 다룬다.
MAX_NAME = 64
MAX_DESCRIPTION = 1024
MAX_COMPATIBILITY = 500
RECOMMENDED_BODY_LINES = 500


def split_frontmatter(text: str) -> tuple[str, str] | None:
    """`---`로 감싼 frontmatter와 body를 분리한다. 형식이 아니면 None."""
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end == -1:
        return None
    return text[4:end], text[end + 5:]


def parse_scalars(front: str) -> dict[str, str]:
    """최상위 `key: value` 스칼라만 읽는다.

    metadata 같은 중첩 매핑은 이 검사기의 관심사가 아니므로 건너뛴다.
    들여쓰기된 줄은 상위 키에 딸린 것으로 보고 무시한다.
    """
    fields: dict[str, str] = {}
    for line in front.splitlines():
        if not line.strip() or line.startswith((" ", "\t", "#")):
            continue
        key, sep, value = line.partition(":")
        if sep:
            fields[key.strip()] = value.strip()
    return fields


def check(skill_dir: pathlib.Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    path = skill_dir / "SKILL.md"
    if not path.is_file():
        return ([f"{skill_dir.name}: SKILL.md가 없다"], [])

    parts = split_frontmatter(path.read_text(encoding="utf-8"))
    if parts is None:
        return ([f"{skill_dir.name}: YAML frontmatter(`---`)로 시작하지 않는다"], [])
    front, body = parts
    fields = parse_scalars(front)

    name = fields.get("name", "")
    if not name:
        errors.append(f"{skill_dir.name}: name이 없다 (필수)")
    else:
        if len(name) > MAX_NAME:
            errors.append(f"{skill_dir.name}: name이 {MAX_NAME}자를 넘는다")
        if not NAME_RE.match(name):
            errors.append(
                f"{skill_dir.name}: name '{name}'은 소문자·숫자·하이픈만 쓸 수 있고 "
                "하이픈으로 시작/끝나거나 연속될 수 없다"
            )
        if name != skill_dir.name:
            errors.append(
                f"{skill_dir.name}: name '{name}'이 디렉터리명과 다르다 (명세상 일치해야 함)"
            )

    description = fields.get("description", "")
    if not description:
        errors.append(f"{skill_dir.name}: description이 없다 (필수)")
    elif len(description) > MAX_DESCRIPTION:
        errors.append(
            f"{skill_dir.name}: description이 {len(description)}자로 "
            f"{MAX_DESCRIPTION}자를 넘는다"
        )

    compatibility = fields.get("compatibility", "")
    if len(compatibility) > MAX_COMPATIBILITY:
        errors.append(f"{skill_dir.name}: compatibility가 {MAX_COMPATIBILITY}자를 넘는다")

    body_lines = len(body.splitlines())
    if body_lines > RECOMMENDED_BODY_LINES:
        warnings.append(
            f"{skill_dir.name}: SKILL.md 본문이 {body_lines}줄이다 "
            f"(권고 {RECOMMENDED_BODY_LINES}줄 이하 — references/로 분리 고려)"
        )

    # 상대경로 링크가 실제로 존재하는지. 깨진 링크는 그 파일을 읽지 못하게 만든다.
    for target in re.findall(r"\]\((?!https?://|#)([^)]+)\)", body):
        if not (skill_dir / target.split("#")[0]).exists():
            warnings.append(f"{skill_dir.name}: 링크 대상이 없다 — {target}")

    return errors, warnings


def main(argv: list[str]) -> int:
    root = pathlib.Path(__file__).resolve().parent.parent
    if len(argv) > 1:
        targets = [pathlib.Path(a).resolve() for a in argv[1:]]
    else:
        targets = sorted(d for d in root.iterdir() if (d / "SKILL.md").is_file())

    if not targets:
        print("검사할 스킬을 찾지 못했다.", file=sys.stderr)
        return 1

    all_errors: list[str] = []
    all_warnings: list[str] = []
    for target in targets:
        errors, warnings = check(target)
        all_errors += errors
        all_warnings += warnings
        mark = "FAIL" if errors else ("WARN" if warnings else "ok  ")
        print(f"[{mark}] {target.name}")

    for w in all_warnings:
        print(f"  warning: {w}")
    for e in all_errors:
        print(f"  error:   {e}")

    print(f"\n{len(targets)}개 검사 — 오류 {len(all_errors)}건, 경고 {len(all_warnings)}건")
    return 1 if all_errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
