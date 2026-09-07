#!/usr/bin/env python3
"""공공데이터포털에서 오퍼레이션 명세를 수집한다.

포털 상세 페이지는 오퍼레이션 목록만 보여주고, 각 오퍼레이션의 요청주소·
요청변수·출력결과는 AJAX(/tcs/dss/selectApiDetailFunction.do)로 따로 가져온다.
그래서 페이지 HTML만 긁으면 첫 오퍼레이션밖에 보이지 않는다.

저장소 루트에서 실행한다.

  python3 mcp/fsc-common/collect_operations.py <출력.json> [--built] [public_data_pk ...]

이미 수집된 서비스는 건너뛰므로 중간에 끊겨도 다시 돌리면 이어간다.
"""
from __future__ import annotations

import html
import json
import pathlib
import re
import sys
import time

import httpx

PORTAL = "https://www.data.go.kr"
DETAIL = f"{PORTAL}/tcs/dss/selectApiDetailFunction.do"
DELAY = 0.6                      # 정부 포털이다. 천천히 간다
TIMEOUT = httpx.Timeout(40.0, connect=15.0)
UA = {"User-Agent": "Mozilla/5.0 (compatible; catalog-collector/1.0)"}


def _text(fragment: str) -> str:
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragment))).strip()


def _table_after(page: str, heading: str) -> list[list[str]]:
    """제목 다음에 오는 첫 <table>의 tbody 행을 셀 목록으로 돌려준다."""
    at = page.find(heading)
    if at < 0:
        return []
    body = re.search(r"<tbody>(.*?)</tbody>", page[at:], re.S)
    if not body:
        return []
    rows = []
    for tr in re.findall(r"<tr>(.*?)</tr>", body.group(1), re.S):
        cells = [_text(td) for td in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if cells:
            rows.append(cells)
    return rows


def _columns(rows: list[list[str]]) -> list[dict]:
    out = []
    for c in rows:
        if len(c) < 4:
            continue
        out.append({"ko": c[0], "name": c[1], "required": c[3] == "필",
                    "sample": c[4] if len(c) > 4 else "",
                    "desc": c[5] if len(c) > 5 else ""})
    return out


def fetch_operation(client: httpx.Client, pk: str, detail_pk: str,
                    seq: str, ko_name: str) -> dict | None:
    resp = client.post(DETAIL, data={"oprtinSeqNo": seq,
                                     "publicDataDetailPk": detail_pk,
                                     "publicDataPk": pk}, headers=UA)
    resp.raise_for_status()
    page = resp.text

    url = re.search(r"요청주소.*?(https://[A-Za-z0-9.\-]+/[A-Za-z0-9/_\-]+)", page, re.S)
    if not url:
        return None
    full = url.group(1)
    base_url, _, operation = full.rpartition("/")

    approval = ""
    ap = re.search(r'활용승인[^<]*</strong>\s*<div class="value">(.*?)</div>', page, re.S)
    if ap:
        approval = _text(ap.group(1))

    params = _columns(_table_after(page, "요청변수(Request Parameter)"))
    fields = _columns(_table_after(page, "출력결과(Response Element)"))

    style = "resultType"
    names = {p["name"] for p in params}
    if "_type" in names:
        style = "_type"
    elif "resultType" not in names:
        style = "xml"

    skip = {"numOfRows", "pageNo", "resultType", "_type", "serviceKey",
            "resultCode", "resultMsg", "totalCount"}
    return {
        "operation": operation,
        "ko_name": ko_name,
        "base_url": base_url.rsplit("/", 1)[0],   # .../service/<Service> → .../service
        "service_from_url": base_url.rsplit("/", 1)[1],
        "approval": approval,
        "param_style": style,
        "params": [p for p in params if p["name"] not in skip],
        "fields": [f["name"] for f in fields if f["name"] not in skip],
        "field_detail": [f for f in fields if f["name"] not in skip],
    }



def _resolve(node, defs: dict, depth: int = 0):
    """$ref를 정의로 바꾼다. 순환 참조를 대비해 깊이를 제한한다."""
    if depth > 10 or not isinstance(node, dict):
        return {}
    ref = node.get("$ref")
    if ref:
        return _resolve(defs.get(ref.rsplit("/", 1)[-1], {}), defs, depth + 1)
    return node


def _item_fields(schema, defs: dict, depth: int = 0) -> list[str]:
    """응답 스키마를 따라 내려가 item 하나의 필드 이름을 모은다.

    최상위는 header/body뿐이라 그대로 쓰면 쓸모가 없다. 실제로 필터 파라미터가
    되는 것은 item의 속성이다. 정의 이름이 API마다 접두사가 붙어(FnCoBs_item)
    이름 규칙 대신 구조를 따라간다.
    """
    if depth > 10:
        return []
    node = _resolve(schema, defs, depth)
    if node.get("type") == "array" and node.get("items"):
        return _item_fields(node["items"], defs, depth + 1)
    for key, sub in (node.get("properties") or {}).items():
        if key == "item" or key.endswith("_item"):
            resolved = _resolve(sub, defs, depth)
            if resolved.get("properties"):
                return list(resolved["properties"])
        found = _item_fields(sub, defs, depth + 1)
        if found:
            return found
    return []


def _from_swagger(page: str) -> list[dict] | None:
    """새 포털 템플릿(PRDE02)은 Swagger 2.0 명세를 페이지에 그대로 심어 둔다.

    구 템플릿의 select + AJAX 경로와 달리 오퍼레이션 목록이 HTML에 없어서,
    이쪽을 먼저 본다.

    오퍼레이션 목록은 swaggerOprtinVOs가 아니라 paths에서 가져온다. VOs는
    일부만 실려 오는 경우가 있다(금융회사재무신용정보는 paths에 3개인데 VOs에는
    1개뿐이다). 파라미터 설명은 VOs에만 있으므로 operationId로 맞춰 채운다.
    """
    m = re.search(r"const swaggerJson = `(.*?)`;", page, re.S)
    if not m:
        return None
    try:
        spec = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None

    paths = spec.get("paths") or {}
    host = (spec.get("host") or "").rstrip("/")
    if not paths or not host:
        return None

    defs = spec.get("definitions") or {}
    base_url, _, service = host.rpartition("/")
    skip = {"numOfRows", "pageNo", "resultType", "_type", "serviceKey",
            "resultCode", "resultMsg", "totalCount"}

    vos = {vo.get("operationId"): vo for vo in spec.get("swaggerOprtinVOs", [])}
    ops = []
    for path, methods in paths.items():
        operation = path.lstrip("/")
        vo = vos.get(operation, {})
        schema = (methods.get("get", {}).get("responses", {})
                  .get("200", {}).get("schema", {}))
        fields = [f for f in _item_fields(schema, defs) if f not in skip]

        params = [{"ko": p.get("paramtrDc", ""), "name": p["paramtrNm"],
                   "required": p.get("paramtrDivision") == "필수",
                   "sample": p.get("paramtrBassValue", ""),
                   "desc": p.get("paramtrDc", "")}
                  for p in vo.get("reqList", []) if p["paramtrNm"] not in skip]
        names = {p["paramtrNm"] for p in vo.get("reqList", [])}
        style = "_type" if "_type" in names else "resultType"

        ops.append({
            "operation": operation,
            "ko_name": vo.get("oprtinNm", ""),
            "desc": vo.get("oprtinDc", ""),
            "base_url": f"https://{base_url}",
            "service_from_url": service,
            "alt_host": (vo.get("oprtinUrl", "").rsplit("/", 2)[0]
                         if vo.get("oprtinUrl") else ""),
            "approval": "",
            "param_style": style,
            "params": params,
            "fields": fields,
            "source": "swagger",
        })
    return ops or None


def fetch_service(client: httpx.Client, pk: str) -> dict:
    resp = client.get(f"{PORTAL}/data/{pk}/openapi.do", headers=UA)
    resp.raise_for_status()
    page = resp.text

    dp = re.search(r'id="publicDataDetailPk"\s+value="([^"]+)"', page)
    if not dp:
        return {"error": "publicDataDetailPk를 찾지 못했습니다"}
    detail_pk = dp.group(1)

    flat = _text(page)
    meta = {}
    for label, key in (("수정일", "updated"), ("등록일", "registered"),
                       ("활용신청 수", "applications"), ("심의유형", "approval")):
        m = re.search(re.escape(label) + r"\s+(\S+(?:\s*/\s*\S+\s*:\s*\S+)?)", flat)
        if m:
            meta[key] = m.group(1).strip()

    swagger_ops = _from_swagger(page)
    if swagger_ops:
        for op in swagger_ops:
            op["approval"] = meta.get("approval", "")
        return {"detail_pk": dp.group(1), "meta": meta, "operations": swagger_ops}

    sel = re.search(r'id="open_api_detail_select".*?</select>', page, re.S)
    options = re.findall(r'<option value="(\d+)">\s*(.*?)\s*</option>',
                         sel.group(0), re.S) if sel else []
    if not options:
        # 포털이 오퍼레이션 목록을 렌더링하지 않는 데이터셋이 있다. 활용가이드
        # 문서에만 명세가 있는 경우로, 사람이 받아서 채워야 한다.
        doc = re.search(r'(오픈API 활용자가이드[^<]*?\.(?:docx|doc|pdf|hwp))', flat)
        return {"error": "포털에 오퍼레이션 목록이 없습니다",
                "guide_doc": doc.group(1) if doc else "",
                "meta": meta}

    ops = []
    for seq, ko in options:
        time.sleep(DELAY)
        try:
            got = fetch_operation(client, pk, detail_pk, seq, html.unescape(ko).strip())
        except httpx.HTTPError as exc:
            ops.append({"ko_name": ko, "error": f"{type(exc).__name__}"})
            continue
        if got:
            ops.append(got)
    return {"detail_pk": detail_pk, "meta": meta, "operations": ops}


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 1
    out_path = pathlib.Path(argv[1])
    targets = argv[2:]

    survey = json.loads(
        (pathlib.Path("mcp/fsc-open-api-catalog.json")).read_text(encoding="utf-8"))["apis"]
    built = set(json.loads(
        (pathlib.Path("mcp/fsc-common/catalog.json")).read_text(encoding="utf-8")))

    # 기본은 아직 채택하지 않은 API다. --built를 주면 이미 서버로 나간 것도 본다
    # (초기 수집이 첫 오퍼레이션만 담은 적이 있어, 빠진 게 없는지 대조할 때 쓴다).
    if "--built" in targets:
        targets = [t for t in targets if t != "--built"]
        todo = list(survey)
    else:
        todo = [a for a in survey if a["service"] not in built]
    if targets:
        todo = [a for a in todo if a["public_data_pk"] in targets]

    result = {}
    if out_path.exists():
        result = json.loads(out_path.read_text(encoding="utf-8"))
        done = {k for k, v in result.items() if v.get("operations")}
        if done:
            todo = [a for a in todo if a["service"] not in done]
            print(f"이어받기: {len(done)}개는 이미 수집됨, {len(todo)}개 남음\n")

    with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
        for i, api in enumerate(todo, 1):
            pk = api["public_data_pk"]
            print(f"[{i}/{len(todo)}] {api['name']:<24} pk={pk}", flush=True)
            try:
                got = fetch_service(client, pk)
            except httpx.HTTPError as exc:
                got = {"error": f"{type(exc).__name__}: {exc}"}
            got.update({"name": api["name"], "topic": api["topic"],
                        "service": api["service"],
                        "adoption_priority": api.get("adoption_priority"),
                        "adoption_note": api.get("adoption_note", "")})
            result[api["service"]] = got
            n = len(got.get("operations", []))
            print(f"      → {n}개 오퍼레이션" if n else f"      → {got.get('error','없음')}",
                  flush=True)
            out_path.write_text(json.dumps(result, ensure_ascii=False, indent=1),
                                encoding="utf-8")
            time.sleep(DELAY)
    print(f"\n{len(result)}개 서비스 → {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
