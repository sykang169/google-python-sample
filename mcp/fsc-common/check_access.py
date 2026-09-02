#!/usr/bin/env python3
"""fsc-* 서버가 쓰는 API의 data.go.kr 활용신청 승인 여부를 실제 호출로 확인한다.

승인 여부는 포털 화면으로도 알 수 있지만, 실제로 호출되는지는 불러 봐야 안다
(경로가 두 갈래라 미승인과 경로 오류를 헷갈리기 쉽다).

  python3 check_access.py             # 5개 서버 전부
  python3 check_access.py ficc market # 일부만

STOCK_API_KEY 환경변수나 gcloud Secret Manager에서 키를 읽는다.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

import fsc_core

CODES = {"30": "미승인 — data.go.kr 활용신청 필요",
         "31": "활용기간 만료", "22": "요청 제한 초과",
         "12": "경로/오퍼레이션 불일치", "03": "데이터 없음(권한은 있음)"}


def resolve_key() -> str:
    key = os.environ.get("STOCK_API_KEY", "")
    if key:
        return key
    project = os.environ.get("GOOGLE_CLOUD_PROJECT") or subprocess.run(
        ["gcloud", "config", "get-value", "project"],
        capture_output=True, text=True).stdout.strip()
    if not project:
        raise SystemExit("STOCK_API_KEY를 찾지 못했습니다. 환경변수로 지정하세요.")
    out = subprocess.run(
        ["gcloud", "secrets", "versions", "access", "latest",
         "--secret=STOCK_API_KEY", f"--project={project}"],
        capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit(f"Secret Manager에서 키를 읽지 못했습니다.\n{out.stderr.strip()}")
    return out.stdout.strip()


def main(argv: list[str]) -> int:
    fsc_core.API_KEY = resolve_key()
    catalog = json.loads(
        (pathlib.Path(__file__).parent / "catalog.json").read_text(encoding="utf-8"))

    servers = argv[1:] or sorted({v["server"] for v in catalog.values()})
    ok_total = total = 0
    need: list[tuple[str, str]] = []

    for server in servers:
        subset = {k: v for k, v in catalog.items() if v["server"] == server}
        if not subset:
            print(f"알 수 없는 서버: {server}", file=sys.stderr)
            return 1
        print(f"\n── fsc-{server}-mcp  ({len(subset)}종)")
        for service, spec in sorted(subset.items(), key=lambda x: x[1]["name"]):
            operation = next(iter(spec["operations"]))
            total += 1
            try:
                fsc_core.call(catalog, service, operation, rows=1)
                print(f"   OK   {spec['name'][:24]:26} {service}")
                ok_total += 1
            except fsc_core.FscError as exc:
                code = str(exc).replace("금융위 API ", "").split(":")[0].strip()
                note = CODES.get(code, str(exc)[:60])
                if code == "03":            # 데이터가 없을 뿐 권한은 있다
                    print(f"   OK   {spec['name'][:24]:26} {service}  ({note})")
                    ok_total += 1
                else:
                    print(f"   {code:4} {spec['name'][:24]:26} {note}")
                    if code == "30":
                        need.append((spec["name"],
                                     f'https://www.data.go.kr/data/{spec["public_data_pk"]}/openapi.do'))

    print(f"\n호출 가능 {ok_total}/{total}")
    if need:
        print("\n활용신청이 필요한 API:")
        for name, url in need:
            print(f"  {name:28} {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
