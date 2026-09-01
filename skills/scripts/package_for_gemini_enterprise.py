#!/usr/bin/env python3
"""스킬 디렉터리를 Gemini Enterprise가 가져올 수 있는 ZIP으로 묶는다.

Gemini Enterprise의 스킬 ZIP 가져오기는 루트의 `SKILL.md`와 선택적인 `scripts/`
디렉터리를 읽는다. 이 저장소의 스킬은 Agent Skills 명세를 따르므로 SKILL.md는
그대로 쓸 수 있지만, `references/`는 Gemini Enterprise 쪽에 "필요할 때 읽는"
단계적 공개가 없어서 그냥 무시된다. 이 스크립트가 그 차이를 메운다:

  SKILL.md      -> 루트에 그대로
  references/*  -> SKILL.md 끝에 부록으로 이어붙임
  scripts/*     -> 그대로 복사 (Python, Bash만 실행 가능)
  assets/*      -> 그대로 복사

숨김 파일과 빌드 부산물(.DS_Store, __pycache__, *.pyc 등)은 업로드를 실패시키므로
제외한다. 전체 크기 100MB 상한도 여기서 확인한다.

한국어 문서는 루트 파일명을 `skill.md`(소문자)로 적고 영어 문서는 `SKILL.md`로
적는다. 기본은 명세와 같은 `SKILL.md`이며, 가져오기가 파일을 못 찾으면
`--lowercase`로 다시 만들어 시도한다.

사용법:
    python3 scripts/package_for_gemini_enterprise.py <스킬경로> [출력디렉터리]
    python3 scripts/package_for_gemini_enterprise.py --all [출력디렉터리]
    python3 scripts/package_for_gemini_enterprise.py --all --lowercase

출력 기본 위치는 `dist/`다.
"""

from __future__ import annotations

import pathlib
import shutil
import sys
import zipfile

APPENDIX_HEADER = "\n\n---\n\n# 부록: 참조 자료\n"

# 업로드를 실패시키는 숨김 파일·빌드 부산물. 문서가 명시적으로 경고하는 항목이다.
EXCLUDE_NAMES = {".DS_Store", "Thumbs.db", "__pycache__", ".git", ".ipynb_checkpoints"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".swp"}

# 업로드 파일 전체 크기 상한.
MAX_TOTAL_BYTES = 100 * 1024 * 1024


def is_junk(path: pathlib.Path, root: pathlib.Path) -> bool:
    """숨김 파일이나 빌드 부산물이면 True. 경로 중간의 디렉터리도 본다."""
    for part in path.relative_to(root).parts:
        if part in EXCLUDE_NAMES or part.startswith("."):
            return True
    return path.suffix in EXCLUDE_SUFFIXES


def build_skill_md(skill_dir: pathlib.Path) -> str:
    """SKILL.md 본문에 references/*.md를 부록으로 이어붙인 문자열을 만든다."""
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")

    refs = sorted((skill_dir / "references").glob("*.md")) \
        if (skill_dir / "references").is_dir() else []
    if not refs:
        return text

    parts = [text.rstrip(), APPENDIX_HEADER]
    for ref in refs:
        body = ref.read_text(encoding="utf-8").strip()
        # 부록 안에서는 제목 수준을 한 단계 낮춰 목차 구조가 뒤집히지 않게 한다.
        body = "\n".join(
            ("#" + line) if line.startswith("#") else line
            for line in body.splitlines()
        )
        parts.append(f"\n## {ref.stem}\n\n(원본: references/{ref.name})\n\n{body}\n")
    return "\n".join(parts)


def package(
    skill_dir: pathlib.Path, out_dir: pathlib.Path, lowercase: bool = False
) -> pathlib.Path:
    if not (skill_dir / "SKILL.md").is_file():
        raise SystemExit(f"{skill_dir}에 SKILL.md가 없다.")

    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / f"{skill_dir.name}.zip"

    total = 0
    skipped: list[str] = []
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        skill_md = build_skill_md(skill_dir)
        total += len(skill_md.encode("utf-8"))
        zf.writestr("skill.md" if lowercase else "SKILL.md", skill_md)

        for sub in ("scripts", "assets"):
            src = skill_dir / sub
            if not src.is_dir():
                continue
            for file in sorted(src.rglob("*")):
                if not file.is_file():
                    continue
                if is_junk(file, skill_dir):
                    skipped.append(str(file.relative_to(skill_dir)))
                    continue
                total += file.stat().st_size
                zf.write(file, str(file.relative_to(skill_dir)))

    if total > MAX_TOTAL_BYTES:
        raise SystemExit(
            f"{skill_dir.name}: 파일 총합이 {total / 1024 / 1024:.1f}MB로 "
            "100MB 상한을 넘는다. assets를 줄인다."
        )
    for name in skipped:
        print(f"  건너뜀(숨김/부산물): {name}")
    return zip_path


def main(argv: list[str]) -> int:
    root = pathlib.Path(__file__).resolve().parent.parent
    args = argv[1:]
    lowercase = "--lowercase" in args
    args = [a for a in args if a != "--lowercase"]
    if not args:
        print(__doc__)
        return 1

    positional = [a for a in args if a != "--all"]
    out_dir = pathlib.Path(positional[-1]) if len(positional) > (0 if "--all" in args else 1) \
        else root / "dist"

    if "--all" in args:
        skills = sorted(d for d in root.iterdir() if (d / "SKILL.md").is_file())
    else:
        skills = [pathlib.Path(positional[0]).resolve()]

    for skill in skills:
        zip_path = package(skill, out_dir, lowercase=lowercase)
        size_kb = zip_path.stat().st_size / 1024
        print(f"{zip_path}  ({size_kb:.1f} KB)")

    print(
        "\nGemini Enterprise 웹앱 > 스킬 > 추가 > 스킬 업로드 에서 위 ZIP을 올린다.\n"
        "스킬 이름은 조직 내에서 고유해야 한다.\n"
        "가져오기가 SKILL.md를 못 찾는다고 하면 --lowercase 로 다시 만든다."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
