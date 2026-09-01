#!/usr/bin/env python3
"""스킬을 Gemini Enterprise Agent Platform의 Skill Registry에 등록한다.

웹앱 업로드(스킬 > 추가 > 스킬 업로드)와 달리 이쪽은 API라서 CI에 넣을 수 있다.
ZIP을 base64로 실어 보내고, 생성은 장기 실행 작업(LRO)이라 완료를 기다린다.

사용법:
    python3 scripts/upload_to_skill_registry.py <스킬경로> \
        --project my-project --location us-central1
    python3 scripts/upload_to_skill_registry.py --all \
        --project my-project --location us-central1
    ... --update      # 이미 있는 스킬을 덮어쓴다 (PATCH)
    ... --dry-run     # 요청만 만들고 보내지 않는다

필요 권한: roles/aiplatform.user (또는 viewer + 생성 권한),
          roles/serviceusage.serviceUsageConsumer
인증: gcloud auth application-default login
"""

from __future__ import annotations

import argparse
import base64
import json
import pathlib
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from package_for_gemini_enterprise import package  # noqa: E402
from validate_skills import parse_scalars, split_frontmatter  # noqa: E402

# Skill Registry가 제공되는 리전. 다른 리전을 주면 404가 난다.
SUPPORTED_LOCATIONS = {"us-central1", "europe-west4", "us-east5"}

# skillId 규칙: 1~63자, 소문자·숫자·하이픈, 문자로 시작, 문자/숫자로 끝.
SKILL_ID_RE = re.compile(r"^[a-z][a-z0-9-]{0,61}[a-z0-9]$")

POLL_INTERVAL_SEC = 5
POLL_TIMEOUT_SEC = 600


def access_token() -> str:
    """ADC 액세스 토큰을 가져온다."""
    result = subprocess.run(
        ["gcloud", "auth", "application-default", "print-access-token"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise SystemExit(
            "액세스 토큰을 얻지 못했다. `gcloud auth application-default login`을 먼저 실행한다.\n"
            + result.stderr.strip()
        )
    return result.stdout.strip()


def read_metadata(skill_dir: pathlib.Path) -> tuple[str, str, str]:
    """SKILL.md에서 (skill_id, displayName, description)을 읽는다.

    displayName은 레지스트리 목록에 그대로 보이므로 본문 첫 H1(사람이 읽는
    제목)을 쓰고, 없으면 name으로 떨어진다.
    """
    parts = split_frontmatter((skill_dir / "SKILL.md").read_text(encoding="utf-8"))
    if parts is None:
        raise SystemExit(f"{skill_dir.name}: frontmatter를 읽지 못했다.")
    front, body = parts
    fields = parse_scalars(front)
    name = fields.get("name", "")
    description = fields.get("description", "")
    if not name or not description:
        raise SystemExit(f"{skill_dir.name}: name/description이 없다.")

    display = name
    for line in body.splitlines():
        if line.startswith("# "):
            display = line[2:].strip()
            break
    return name, display, description


def check_skill_id(skill_id: str) -> None:
    if not SKILL_ID_RE.match(skill_id):
        raise SystemExit(
            f"skillId '{skill_id}'가 규칙에 맞지 않는다 — "
            "1~63자, 소문자·숫자·하이픈, 문자로 시작하고 문자/숫자로 끝나야 한다."
        )
    if skill_id.startswith("gcp-"):
        # gcp- 접두사는 내장 스킬용으로 예약되어 있다.
        raise SystemExit(f"skillId '{skill_id}': 'gcp-' 접두사는 예약되어 있다.")


def request(url: str, token: str, method: str = "GET", body: dict | None = None) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    if data:
        req.add_header("Content-Type", "application/json; charset=utf-8")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:800]
        raise SystemExit(f"HTTP {exc.code} {method} {url}\n{detail}") from exc


def wait_for_operation(base: str, token: str, operation_name: str) -> dict:
    """LRO가 끝날 때까지 기다린다. operation_name은 전체 리소스 경로다."""
    url = f"{base}/{operation_name}" if not operation_name.startswith("http") else operation_name
    deadline = time.monotonic() + POLL_TIMEOUT_SEC
    while time.monotonic() < deadline:
        op = request(url, token)
        if op.get("done"):
            if "error" in op:
                raise SystemExit(f"작업 실패: {json.dumps(op['error'], ensure_ascii=False)}")
            return op
        time.sleep(POLL_INTERVAL_SEC)
    raise SystemExit(f"작업이 {POLL_TIMEOUT_SEC}초 안에 끝나지 않았다: {operation_name}")


def upload(skill_dir: pathlib.Path, args: argparse.Namespace, token: str) -> None:
    skill_id, display_name, description = read_metadata(skill_dir)
    check_skill_id(skill_id)

    out_dir = pathlib.Path(args.out) if args.out else skill_dir.parent / "dist"
    zip_path = package(skill_dir, out_dir)
    encoded = base64.b64encode(zip_path.read_bytes()).decode("ascii")

    body = {
        "displayName": display_name,
        "description": description,
        "zippedFilesystem": encoded,
    }

    host = f"https://{args.location}-aiplatform.googleapis.com/v1beta1"
    parent = f"{host}/projects/{args.project}/locations/{args.location}"

    if args.update:
        url = (f"{parent}/skills/{skill_id}"
               "?updateMask=displayName,description,zippedFilesystem")
        method = "PATCH"
    else:
        url = f"{parent}/skills?skillId={skill_id}"
        method = "POST"

    if args.dry_run:
        print(f"[dry-run] {method} {url}  (zip {zip_path.stat().st_size / 1024:.1f} KB)")
        return

    print(f"{method} {skill_id} ...")
    op = request(url, token, method=method, body=body)

    # 생성/수정/삭제는 비동기다. 이름만 받고 끝내면 실패를 놓친다.
    name = op.get("name", "")
    if name and not op.get("done"):
        wait_for_operation(host, token, name)
    print(f"  완료 — projects/{args.project}/locations/{args.location}/skills/{skill_id}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill", nargs="?", help="스킬 디렉터리 경로")
    parser.add_argument("--all", action="store_true", help="skills/ 전체를 등록")
    parser.add_argument("--project", required=True, help="GCP 프로젝트 ID")
    parser.add_argument(
        "--location", default="us-central1",
        help="리전. " + " / ".join(sorted(SUPPORTED_LOCATIONS)),
    )
    parser.add_argument("--update", action="store_true", help="기존 스킬을 PATCH로 갱신")
    parser.add_argument("--out", help="ZIP 출력 디렉터리 (기본 skills/dist)")
    parser.add_argument("--dry-run", action="store_true", help="요청을 보내지 않는다")
    args = parser.parse_args()

    if args.location not in SUPPORTED_LOCATIONS:
        raise SystemExit(
            f"'{args.location}'은 Skill Registry 제공 리전이 아니다. "
            + " / ".join(sorted(SUPPORTED_LOCATIONS))
        )

    root = pathlib.Path(__file__).resolve().parent.parent
    if args.all:
        skills = sorted(d for d in root.iterdir() if (d / "SKILL.md").is_file())
    elif args.skill:
        skills = [pathlib.Path(args.skill).resolve()]
    else:
        parser.error("스킬 경로를 주거나 --all을 쓴다.")

    token = "" if args.dry_run else access_token()
    for skill in skills:
        upload(skill, args, token)
    return 0


if __name__ == "__main__":
    sys.exit(main())
