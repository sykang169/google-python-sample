#!/usr/bin/env python3
"""수집한 오퍼레이션을 실제로 호출해 승인 여부를 확인한다.

서비스마다 첫 오퍼레이션 하나만 부른다. 활용신청은 서비스 단위라 하나만
확인하면 나머지도 같다.

저장소 루트에서 실행한다.

  STOCK_API_KEY=... python3 mcp/fsc-common/check_candidates.py <collected.json> <출력.json>

이미 서버로 나간 API는 check_access.py가 본다. 이쪽은 아직 채택하지 않은
후보를 본다.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import time

import httpx

TIMEOUT = httpx.Timeout(30.0, connect=10.0)
DELAY = 0.5

CODES = {
    "00": ("callable", "호출 가능"),
    "03": ("callable", "호출 가능 (해당 조건 데이터 없음)"),
    "10": ("param_error", "잘못된 요청 파라미터"),
    "11": ("param_error", "필수 파라미터 누락"),
    "12": ("path_error", "경로/오퍼레이션 불일치"),
    "20": ("denied", "서비스 접근 거부"),
    "22": ("rate_limited", "요청 제한 초과"),
    "30": ("not_applied", "활용신청 필요 (미승인)"),
    "31": ("expired", "활용기간 만료"),
    "32": ("ip_error", "등록되지 않은 IP"),
}


def candidate_urls(op: dict) -> list[str]:
    """호출 경로가 여러 갈래다. 틀리면 권한과 무관하게 12가 나므로 다 시도한다.

    - apis.data.go.kr/1160100/service/<Svc>  (구 게이트웨이, 대부분)
    - openapi.fsc.go.kr/service/<Svc>        (신규 데이터셋)
    - /service/가 빠진 형태 (포털 swagger host가 그렇게 주는 경우가 있다)
    """
    svc, op_name = op["service_from_url"], op["operation"]
    bases = [op["base_url"].replace("http://", "https://")]
    alt = (op.get("alt_host") or "").rstrip("/")
    if alt:
        alt_base = alt.rpartition("/")[0]
        if alt_base:
            bases.append(f"https://{alt_base}")
    bases += ["https://apis.data.go.kr/1160100/service",
              "https://apis.data.go.kr/1160100",
              "https://openapi.fsc.go.kr/service"]
    seen, out = set(), []
    for b in bases:
        u = f"{b}/{svc}/{op_name}"
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def probe(client: httpx.Client, key: str, spec: dict, op: dict) -> dict:
    query = {"serviceKey": key, "numOfRows": 1, "pageNo": 1}
    style = op.get("param_style", "resultType")
    if style in ("resultType", "_type"):
        query[style] = "json"
    # 필수 파라미터는 포털 샘플값으로 채운다. 없으면 11이 나서 승인 여부를 못 본다.
    for p in op.get("params", []):
        if p.get("required") and p.get("sample"):
            query[p["name"]] = p["sample"]

    last = None
    for url in candidate_urls(op):
        try:
            resp = client.get(url, params=query)
        except httpx.HTTPError as exc:
            last = {"access": "unreachable", "detail": type(exc).__name__, "url": url}
            continue
        got = _classify(resp, url)
        if got["access"] not in ("path_error", "unknown"):
            return got
        last = got
    return last or {"access": "unknown", "detail": "시도할 경로가 없습니다"}


def _classify(resp, url: str) -> dict:
    body = resp.text
    code = None
    if body.lstrip().startswith("{"):
        try:
            data = resp.json()
            node = data.get("response", data)
            head = node.get("header") or node.get("body") or node
            code = str(head.get("resultCode", "")).zfill(2) if "resultCode" in head else None
            if code is None and "resultCode" in node:
                code = str(node["resultCode"]).zfill(2)
        except Exception:
            pass
    if code is None:
        import re
        m = re.search(r"<resultCode>\s*(\d+)\s*</resultCode>", body)
        if m:
            code = m.group(1).zfill(2)
        elif "SERVICE_KEY_IS_NOT_REGISTERED" in body or "SERVICE ERROR" in body:
            code = "30"
    if code is None:
        return {"access": "unknown", "detail": f"HTTP {resp.status_code}: {body[:120]}",
                "url": url}

    access, note = CODES.get(code, ("unknown", f"resultCode {code}"))
    return {"access": access, "result_code": code, "detail": note, "url": url}


def main(argv: list[str]) -> int:
    key = os.environ.get("STOCK_API_KEY", "")
    if not key:
        raise SystemExit("STOCK_API_KEY가 필요합니다.")
    collected = json.loads(pathlib.Path(argv[1]).read_text(encoding="utf-8"))
    out_path = pathlib.Path(argv[2])

    result = {}
    with httpx.Client(timeout=TIMEOUT) as client:
        items = [(s, v) for s, v in collected.items() if v.get("operations")]
        for i, (service, spec) in enumerate(items, 1):
            op = spec["operations"][0]
            got = probe(client, key, spec, op)
            got.update({"name": spec["name"], "topic": spec["topic"],
                        "operation_checked": op["operation"],
                        "approval": op.get("approval", ""),
                        "operation_count": len(spec["operations"])})
            result[service] = got
            print(f"[{i}/{len(items)}] {got['access']:<12} {spec['name'][:22]:<24} "
                  f"{got.get('detail','')}", flush=True)
            out_path.write_text(json.dumps(result, ensure_ascii=False, indent=1),
                                encoding="utf-8")
            time.sleep(DELAY)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
