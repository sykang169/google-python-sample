"""DART MCP 서버가 이미지에 굽는 두 자산을 생성한다.

  assets/catalog.json       82개 JSON 엔드포인트의 파라미터 명세
  assets/corp_index.json.gz 회사명 -> corp_code 인덱스 (약 11.9만 건)

둘 다 런타임에 만들 수 없어서 빌드 시점에 굽는다.
  - corpCode.xml 다운로드는 실측 229초가 걸려 Cloud Run 요청 타임아웃(300초)에
    육박한다. 콜드 스타트마다 이걸 할 수는 없다.
  - 카탈로그는 opendart 개발가이드 HTML을 긁어야 하는데, 82개 상세 페이지를
    런타임에 도는 것은 논외다.

  usage: python build_assets.py [--catalog] [--corp]
         (인자 없으면 둘 다)

DART_API_KEY 환경변수 또는 Secret Manager(gcloud)에서 키를 읽는다.
DART가 엔드포인트를 추가/변경하면 이 스크립트를 다시 돌리고 재배포한다.
"""

from __future__ import annotations

import gzip
import html
import json
import os
import pathlib
import re
import subprocess
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from concurrent.futures import ThreadPoolExecutor

ASSETS = pathlib.Path(__file__).parent / "assets"
UA = {"User-Agent": "Mozilla/5.0"}
GROUPS = {
    "DS001": "공시정보",
    "DS002": "정기보고서 주요정보",
    "DS003": "정기보고서 재무정보",
    "DS004": "지분공시",
    "DS005": "주요사항보고서",
    "DS006": "증권신고서",
}


def api_key() -> str:
    key = os.environ.get("DART_API_KEY", "")
    if key:
        return key
    project = os.environ.get("GOOGLE_CLOUD_PROJECT") or subprocess.run(
        ["gcloud", "config", "get-value", "project"],
        capture_output=True, text=True,
    ).stdout.strip()
    out = subprocess.run(
        ["gcloud", "secrets", "versions", "access", "latest",
         "--secret=DART_API_KEY", f"--project={project}"],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        sys.exit("DART_API_KEY를 환경변수나 Secret Manager에서 찾지 못했습니다.")
    return out.stdout.strip()


def _get(url: str, timeout: int = 45) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def _cells(tr: str) -> list[str]:
    return [
        html.unescape(re.sub(r"<[^>]+>", "", c)).strip()
        for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)
    ]


def build_catalog() -> None:
    """opendart 개발가이드에서 82개 JSON 엔드포인트의 명세를 수집한다."""
    meta: dict[str, dict] = {}
    for grp, grp_name in GROUPS.items():
        page = _get(f"https://opendart.fss.or.kr/guide/main.do?apiGrpCd={grp}")
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S):
            ids = re.findall(r"apiId=(\w+)", tr)
            cols = [c for c in _cells(tr) if c]
            # 표 구조: 번호 | API명 | 상세기능 | 개발가이드(바로가기)
            if ids and len(cols) >= 3:
                meta[ids[0]] = {"group": grp, "group_name": grp_name,
                                "name": cols[1], "desc": cols[2]}
    print(f"  그룹 메타 {len(meta)}건")

    def one(api_id: str):
        grp = meta[api_id]["group"]
        url = f"https://opendart.fss.or.kr/guide/detail.do?apiGrpCd={grp}&apiId={api_id}"
        page = None
        for attempt in range(3):
            try:
                page = _get(url)
                break
            except Exception:
                if attempt == 2:
                    return api_id, None, []
                time.sleep(2)
        endpoints = sorted(set(re.findall(
            r"https://opendart\.fss\.or\.kr/api/([A-Za-z0-9_]+)\.json", page)))
        params, seen = [], set()
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S):
            c = [x for x in _cells(tr) if x]
            # 요청인자 표의 행 형태: 영문명 | 한글명 | 타입 | 필수여부 | 설명
            if (len(c) >= 4
                    and re.fullmatch(r"[a-z_][a-z0-9_]{2,24}", c[0])
                    and re.match(r"(STRING|NUMBER|BOOLEAN)", c[2].upper())
                    and c[0] not in seen):
                seen.add(c[0])
                params.append({
                    "name": c[0],
                    "ko": c[1],
                    "type": c[2],
                    "required": c[3].strip().upper().startswith("Y"),
                    "desc": " ".join((c[4] if len(c) > 4 else "").split())[:200],
                })
        return api_id, (endpoints[0] if endpoints else None), params

    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(one, list(meta)))

    catalog, skipped = [], []
    for api_id, endpoint, params in results:
        info = meta[api_id]
        # JSON 엔드포인트가 없는 것(corpCode.xml, document.xml, fnlttXbrl.xml)은 제외.
        if not endpoint or not params:
            skipped.append(info["name"])
            continue
        catalog.append({
            "endpoint": endpoint, "api_id": api_id,
            "group": info["group"], "group_name": info["group_name"],
            "name": info["name"], "desc": info["desc"], "params": params,
        })
    catalog.sort(key=lambda c: (c["group"], c["endpoint"]))

    ASSETS.mkdir(exist_ok=True)
    out = ASSETS / "catalog.json"
    out.write_text(json.dumps(catalog, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  → {out.name}  {len(catalog)}개 엔드포인트, {out.stat().st_size/1024:.0f}KB")
    if skipped:
        print(f"     제외(JSON 미제공): {', '.join(skipped)}")


def build_corp_index() -> None:
    """corpCode.xml(ZIP)을 받아 [corp_code, corp_name, stock_code] 인덱스로 만든다."""
    url = f"https://opendart.fss.or.kr/api/corpCode.xml?crtfc_key={api_key()}"
    print("  corpCode.xml 다운로드 중 (실측 약 4분 소요)...")
    started = time.time()
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=600) as resp:
        blob = resp.read()
    print(f"  {len(blob)/1024/1024:.1f}MB 수신 ({time.time()-started:.0f}초)")

    with zipfile.ZipFile(__import__("io").BytesIO(blob)) as zf:
        raw = zf.read(zf.namelist()[0])
    root = ET.fromstring(raw)

    rows = []
    for el in root.findall("list"):
        code = (el.findtext("corp_code") or "").strip()
        name = (el.findtext("corp_name") or "").strip()
        stock = (el.findtext("stock_code") or "").strip()
        if code and name:
            rows.append([code, name, stock])

    ASSETS.mkdir(exist_ok=True)
    out = ASSETS / "corp_index.json.gz"
    payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode()
    out.write_bytes(gzip.compress(payload, 9))
    listed = sum(1 for r in rows if r[2])
    print(f"  → {out.name}  전체 {len(rows):,}건 (상장 {listed:,}건), "
          f"{out.stat().st_size/1024:.0f}KB")


if __name__ == "__main__":
    args = set(sys.argv[1:])
    do_all = not (args & {"--catalog", "--corp"})
    if do_all or "--catalog" in args:
        print("[카탈로그]")
        build_catalog()
    if do_all or "--corp" in args:
        print("[회사 인덱스]")
        build_corp_index()
