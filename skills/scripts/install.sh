#!/usr/bin/env bash
# 스킬 8종을 에이전트 도구가 읽는 위치에 연결한다.
#
#   ./scripts/install.sh                    설치 가능한 위치를 보여준다
#   ./scripts/install.sh .agents/skills     그 경로에 심볼릭 링크로 연결
#   ./scripts/install.sh --copy ~/.claude/skills   링크 대신 복사
#
# 기본은 심볼릭 링크다. 저장소를 업데이트하면 스킬도 함께 갱신되기 때문이다.
# 복사는 저장소를 지우거나 옮길 예정일 때만 쓴다.
set -euo pipefail

SKILLS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  cat <<'MSG'
사용법: ./scripts/install.sh [--copy] <설치 경로>

도구별 경로 (2026년 9월 기준 — 각 도구 문서에서 최신 값을 확인하세요)

  .agents/skills          Antigravity, Gemini CLI  ← 한 경로로 두 도구를 덮는다
  ~/.agents/skills        Gemini CLI (사용자 전역)
  .claude/skills          Claude Code (이 프로젝트에서만)
  ~/.claude/skills        Claude Code (모든 프로젝트)
  .gemini/skills          Gemini CLI (구 경로. .agents 쪽이 우선한다)

Cursor, Codex CLI, GitHub Copilot도 SKILL.md를 읽지만 경로가 다르므로
각 도구 문서를 확인한 뒤 그 경로를 인자로 주세요. 형식은 같습니다.

Gemini Enterprise는 파일 연결이 아니라 업로드입니다:
  python3 scripts/package_for_gemini_enterprise.py --all
MSG
}

MODE=link
if [[ "${1:-}" == "--copy" ]]; then MODE=copy; shift; fi
if [[ $# -lt 1 || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then usage; exit 0; fi

TARGET="${1/#\~/$HOME}"
mkdir -p "$TARGET"
TARGET="$(cd "$TARGET" && pwd)"

if [[ "$TARGET" == "$SKILLS_DIR" ]]; then
  echo "설치 경로가 스킬 원본과 같습니다. 다른 경로를 주세요." >&2
  exit 1
fi

n=0
for dir in "$SKILLS_DIR"/*/; do
  name="$(basename "$dir")"
  [[ -f "$dir/SKILL.md" ]] || continue
  dest="$TARGET/$name"

  if [[ -e "$dest" || -L "$dest" ]]; then
    if [[ -L "$dest" && "$(readlink "$dest")" == "${dir%/}" ]]; then
      printf '  = %s (이미 연결됨)\n' "$name"; n=$((n+1)); continue
    fi
    printf '  ! %s — 이미 있어 건너뜁니다. 덮어쓰려면 먼저 지우세요\n' "$name" >&2
    continue
  fi

  if [[ "$MODE" == link ]]; then ln -s "${dir%/}" "$dest"; else cp -r "${dir%/}" "$dest"; fi
  printf '  + %s\n' "$name"; n=$((n+1))
done

echo
echo "$n개 스킬을 $TARGET 에 $([[ $MODE == link ]] && echo 연결 || echo 복사)했습니다."
echo "도구를 다시 시작하면 목록에 나타납니다."
