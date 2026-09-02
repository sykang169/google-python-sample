"""금융위원회 공공데이터 API 공용 클라이언트.

5개 FSC MCP 서버(market / ficc / research / equity-ops / industry)가 공유한다.
원본은 mcp/fsc-common/에 있고 sync.py가 각 서버 디렉터리로 복사한다.
서버 디렉터리의 사본을 직접 고치지 말 것 — 다음 sync에서 덮어쓴다.

이 API 계열에서 실제로 걸리는 것들
-----------------------------------
1. 호출 경로가 두 갈래다. 절반은 `/1160100/service/<서비스>`, 나머지 절반
   (주로 _V2/_V3)은 `/service/` 없이 `/1160100/<서비스>`다. 틀리면 권한과
   무관하게 resultCode 12가 나서 미승인으로 오해하기 쉽다. catalog.json의
   base_url이 서비스마다 이 값을 들고 있다.
2. 응답 포맷 지정이 API마다 다르다. `resultType=json`인 것과 `_type=json`인 것,
   JSON을 아예 안 주고 XML만 주는 것이 섞여 있다. param_style로 구분한다.
3. 오류가 HTTP 200과 함께 온다. 상태 코드만 보면 전부 성공으로 보인다.
4. 응답 껍데기가 한 겹 더 있는 API가 있다(body.tableList[].items.item).
5. 전부 비실시간이다. 기준일 다음 영업일 13시 이후에 갱신된다.
6. 연결이 간헐적으로 실패한다(ConnectTimeout). 호출을 몰아치면 소스 IP 단위로
   일시 제한되는 것으로 보이지만, 콜드 스타트 직후의 일시적 실패도 섞여 있어
   원인을 단정하기 어렵다. 그래서 이 모듈은 응답 캐시, 호출 간 최소 간격,
   호출 안에서의 연결 재시도, 그리고 회로 차단을 함께 쓴다.
   **회로에는 절반 열림이 있다.** 열려 있어도 주기적으로 한 건을 통과시켜
   상류를 확인하고, 성공하면 즉시 닫는다. 이것이 없으면 상류가 멀쩡한데도
   쿨다운이 끝날 때까지 도구가 잠긴다 — 실제로 겪은 문제다.
"""

from __future__ import annotations

import json
import logging
import os
import pathlib
import random
import threading
import time
import xml.etree.ElementTree as ET
from collections import OrderedDict
from typing import Any

import httpx

TIMEOUT = httpx.Timeout(30.0, connect=10.0)
API_KEY = os.environ.get("STOCK_API_KEY", "")

# httpx는 INFO 레벨로 "HTTP Request: GET <전체 URL>"을 남긴다. 이 URL에는
# 쿼리스트링의 serviceKey가 그대로 들어 있어 Cloud Logging에 인증키가 적재된다.
# 금융 환경에서 자격증명이 로그에 남는 것은 그 자체로 사고이므로 WARNING으로 올린다.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# 조회 전용 도구 annotation. readOnlyHint=True면 Gemini Enterprise가
# 호출 전 사용자 확인 단계를 건너뛴다.
READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True}

# data.go.kr 공통 결과 코드.
RESULT_CODES = {
    "00": None,
    "01": "애플리케이션 에러",
    "02": "데이터베이스 에러",
    "03": "데이터 없음 (조건에 맞는 행이 없다 — 오류가 아니다)",
    "04": "HTTP 에러",
    "05": "서비스 연결 실패",
    "10": "잘못된 요청 파라미터",
    "11": "필수 요청 파라미터 누락",
    "12": "해당 오픈API 서비스가 없거나 폐기됨 (경로나 오퍼레이션명 확인)",
    "20": "서비스 접근 거부",
    "22": "서비스 요청 제한 횟수 초과",
    "30": "등록되지 않은 서비스키 (data.go.kr에서 이 API 활용신청 필요)",
    "31": "활용기간 만료된 서비스키",
    "32": "등록되지 않은 IP",
    "33": "서명되지 않은 호출",
}

# 코드별 "다음에 무엇을 할 것인가". 증상만 돌려주면 모델이 03(데이터 없음)과
# 30(권한 미승인)을 똑같이 "조회 실패"로 뭉뚱그린다. 03은 조건을 넓혀 다시
# 물어야 하고 30은 재시도가 무의미하다 — 대응이 정반대다.
NEXT_STEP = {
    "03": "기간·필터를 넓혀 다시 조회한다. 그래도 없으면 '해당 기간에 데이터 없음'으로"
          " 답한다. 사고주권·배당처럼 업무를 가르는 조회는 '해당 없음'으로 단정하지"
          " 않는다.",
    "10": "파라미터 이름을 지어내지 말고 search_apis가 돌려준 fields에서 고른다.",
    "11": "필수 파라미터가 빠졌다. search_apis의 fields를 확인한다.",
    "12": "미승인이 아니라 경로 오류다. search_apis로 서비스·오퍼레이션명을 다시 확인한다.",
    "20": "재시도해도 같다. 데이터를 가져오지 못했다고 답하고 추측으로 채우지 않는다.",
    "22": "호출 한도를 넘었다. 같은 호출을 즉시 반복하지 않는다. 잠시 뒤 풀린다.",
    "30": "이 API는 활용신청이 승인되지 않았다. 재시도해도 같으므로 다른 도구를 쓰거나"
          " 가져오지 못했다고 답한다.",
    "31": "서비스키 활용기간이 만료됐다. 재시도해도 같다.",
    "32": "등록되지 않은 IP다. 재시도해도 같다.",
    "33": "서명되지 않은 호출이다. 재시도해도 같다.",
}


def result_message(code: str, fallback: str = "") -> str:
    """오류 코드를 "증상 — 다음 행동"으로 만든다.

    이 문자열은 사람이 아니라 모델이 읽는다. 증상만 주면 03과 30을 똑같이
    다루게 되고, 그 차이가 답을 가른다.
    """
    what = RESULT_CODES.get(code) or fallback or "알 수 없는 오류"
    step = NEXT_STEP.get(code)
    return f"{what} — {step}" if step else what


# 재시도 정책. 서버측 일시 오류(resultCode)에만 적용한다.
MAX_ATTEMPTS = 3
BACKOFF_BASE = 1.0
BACKOFF_CAP = 6.0

# 다시 호출하면 결과가 달라질 수 있는 것만 재시도한다.
RETRYABLE = {"01", "02", "04", "05", "22"}

# ── 호출량 억제 ─────────────────────────────────────────────────────────────
# 이 값들은 전부 환경변수로 덮어쓸 수 있다. 운영 중 차단이 잦으면 간격을 늘린다.

# 응답 캐시 TTL(초). 데이터가 D+1로 하루 한 번 갱신되므로 몇 시간 캐시해도
# 정확도 손실이 없다. 기본 6시간.
#
# 끄려면 FSC_CACHE=off 또는 FSC_CACHE_TTL=0. 디버깅이나 상류가 막 갱신된 직후처럼
# 캐시가 방해될 때 쓴다. 끄면 상류 호출이 그대로 늘어 소스 IP 차단에 걸리기
# 쉬워지므로 상시로 꺼 두지는 않는 편이 낫다.
CACHE_TTL = float(os.environ.get("FSC_CACHE_TTL", 6 * 3600))
CACHE_MAX_ENTRIES = int(os.environ.get("FSC_CACHE_MAX", 512))
CACHE_ENABLED = (
    os.environ.get("FSC_CACHE", "on").strip().lower() not in {"off", "0", "false", "no"}
    and CACHE_TTL > 0
)

# 상류 호출 사이의 최소 간격(초). 프로세스 전체에 걸린다.
MIN_INTERVAL = float(os.environ.get("FSC_MIN_INTERVAL", 0.5))

# 회로를 여는 기준. 개별 시도가 아니라 **호출 단위**로 센다 — 한 호출이
# MAX_ATTEMPTS를 모두 소진하고도 연결에 실패한 경우만 1회로 친다. 순간적인
# 연결 실패 한 번으로 도구 전체가 잠기면 안 된다.
BREAKER_THRESHOLD = int(os.environ.get("FSC_BREAKER_THRESHOLD", 3))
# 회로를 열어 두는 시간(초).
BREAKER_COOLDOWN = float(os.environ.get("FSC_BREAKER_COOLDOWN", 300))
# 회로가 열려 있어도 이 간격마다 한 건은 통과시켜 상류가 회복됐는지 확인한다
# (절반 열림). 이것이 없으면 상류가 곧바로 회복돼도 쿨다운을 통째로 기다린다.
BREAKER_PROBE_INTERVAL = float(os.environ.get("FSC_BREAKER_PROBE", 60))


class _Throttle:
    """호출 간 최소 간격과 회로 차단을 함께 관리한다.

    FastMCP는 동기 도구를 스레드풀에서 돌리므로 여러 스레드가 동시에 들어온다.
    락으로 직렬화해 상류에 동시 연결이 몰리지 않게 한다.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last_call = 0.0
        self._consecutive_failures = 0
        self._open_until = 0.0
        self._next_probe = 0.0

    def acquire(self) -> float:
        """호출을 허용하면 0을, 막으면 남은 초를 반환한다.

        회로가 열려 있어도 BREAKER_PROBE_INTERVAL마다 한 건은 통과시킨다
        (절반 열림). 그 한 건이 성공하면 record_success가 회로를 즉시 닫으므로,
        상류가 30초 만에 회복돼도 쿨다운을 끝까지 기다리는 일이 없다.

        통과시킬 때 다음 시험 시각을 락 안에서 미리 밀어 두므로, 여러 스레드가
        동시에 들어와도 시험 호출은 주기당 하나만 나간다.
        """
        with self._lock:
            now = time.monotonic()
            remaining = self._open_until - now
            if remaining <= 0:
                return 0.0
            if now >= self._next_probe:
                self._next_probe = now + BREAKER_PROBE_INTERVAL
                return 0.0
            return remaining

    def check_open(self) -> float:
        """상태 조회용. 회로를 소비하지 않는다."""
        with self._lock:
            return max(0.0, self._open_until - time.monotonic())

    def wait_turn(self) -> None:
        """최소 간격을 지켜 순서를 기다린다."""
        with self._lock:
            gap = MIN_INTERVAL - (time.monotonic() - self._last_call)
            if gap > 0:
                time.sleep(gap)
            self._last_call = time.monotonic()

    def record_success(self) -> None:
        """성공하면 회로를 즉시 닫는다. 절반 열림 시험의 성공도 여기로 온다."""
        with self._lock:
            self._consecutive_failures = 0
            self._open_until = 0.0
            self._next_probe = 0.0

    def record_connect_failure(self) -> None:
        """한 호출이 재시도를 모두 소진하고도 연결에 실패했을 때만 부른다."""
        with self._lock:
            self._consecutive_failures += 1
            if self._consecutive_failures >= BREAKER_THRESHOLD:
                now = time.monotonic()
                self._open_until = now + BREAKER_COOLDOWN
                self._next_probe = now + BREAKER_PROBE_INTERVAL


class _Cache:
    """TTL + 용량 제한이 있는 응답 캐시. 성공 응답만 담는다."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: OrderedDict[str, tuple[float, dict]] = OrderedDict()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> dict | None:
        if not CACHE_ENABLED:
            return None
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                self.misses += 1
                return None
            stored_at, value = entry
            if time.monotonic() - stored_at > CACHE_TTL:
                del self._data[key]
                self.misses += 1
                return None
            self._data.move_to_end(key)
            self.hits += 1
            # 호출자가 결과를 수정해도 캐시가 오염되지 않게 복사해서 준다.
            return json.loads(json.dumps(value))

    def put(self, key: str, value: dict) -> None:
        if not CACHE_ENABLED:
            return
        with self._lock:
            self._data[key] = (time.monotonic(), value)
            self._data.move_to_end(key)
            while len(self._data) > CACHE_MAX_ENTRIES:
                self._data.popitem(last=False)

    def clear(self) -> dict:
        with self._lock:
            n = len(self._data)
            self._data.clear()
            return {"cleared": n}

    def stats(self) -> dict:
        with self._lock:
            return {"enabled": CACHE_ENABLED, "entries": len(self._data),
                    "hits": self.hits, "misses": self.misses,
                    "ttl_seconds": CACHE_TTL if CACHE_ENABLED else 0}


_throttle = _Throttle()
_cache = _Cache()


def cache_stats() -> dict:
    """캐시 상태. 진단용."""
    return _cache.stats()


def cache_clear() -> dict:
    """캐시를 비운다. 재배포 없이 상류 최신값을 다시 받고 싶을 때."""
    return _cache.clear()


class FscError(RuntimeError):
    """금융위 API가 resultCode로 돌려주는 오류."""


def load_catalog(server: str | None = None) -> dict[str, Any]:
    """catalog.json을 읽는다. server를 주면 그 서버 몫만 남긴다."""
    path = pathlib.Path(__file__).parent / "catalog.json"
    cat = json.loads(path.read_text(encoding="utf-8"))
    if server:
        cat = {k: v for k, v in cat.items() if v["server"] == server}
    return cat


def _backoff(attempt: int) -> None:
    delay = min(BACKOFF_BASE * (2 ** attempt), BACKOFF_CAP)
    time.sleep(delay * (0.5 + random.random()))


def _dig_items(node: Any, depth: int = 0) -> list[dict]:
    """응답에서 item 배열을 찾아낸다.

    보통 body.items.item이지만 body.tableList[].items.item처럼 한 겹 더
    들어가는 API가 있다. 구조를 가정하지 않고 훑는다.
    """
    if depth > 6:
        return []
    if isinstance(node, dict):
        if "item" in node:
            item = node["item"]
            if isinstance(item, list):
                return [x for x in item if isinstance(x, dict)]
            return [item] if isinstance(item, dict) else []
        for value in node.values():
            found = _dig_items(value, depth + 1)
            if found:
                return found
    elif isinstance(node, list):
        for value in node:
            found = _dig_items(value, depth + 1)
            if found:
                return found
    return []


def _parse_xml(text: str) -> dict:
    """JSON을 주지 않는 API의 XML 응답을 같은 형태로 바꾼다."""
    root = ET.fromstring(text)
    code = root.findtext(".//resultCode") or root.findtext(".//returnReasonCode")
    if code and code != "00":
        raise FscError(f"금융위 API {code}: {result_message(code)}")
    rows = [{c.tag: (c.text or "") for c in item} for item in root.iter("item")]
    return {
        "total_count": root.findtext(".//totalCount"),
        "page_no": root.findtext(".//pageNo"),
        "rows": rows,
    }


def _check_json(data: dict) -> None:
    """HTTP 200과 함께 오는 오류를 잡아낸다."""
    envelope = data.get("OpenAPI_ServiceResponse")
    if envelope:
        header = envelope.get("cmmMsgHeader", {})
        code = str(header.get("returnReasonCode", ""))
        raise FscError(
            f"금융위 API {code}: {result_message(code, header.get('errMsg', ''))}"
        )
    header = (data.get("response") or {}).get("header") or {}
    code = str(header.get("resultCode", ""))
    if code and code != "00":
        raise FscError(
            f"금융위 API {code}: {result_message(code, header.get('resultMsg', ''))}"
        )


def call(
    catalog: dict[str, Any],
    service: str,
    operation: str,
    params: dict[str, Any] | None = None,
    rows: int = 20,
    page: int = 1,
) -> dict:
    """카탈로그에 있는 오퍼레이션을 실행하고 응답을 정규화한다.

    serviceKey는 서버가 넣으므로 params에 포함하지 않는다.
    """
    if not API_KEY:
        raise FscError(
            "STOCK_API_KEY가 설정되지 않았습니다. Cloud Run에서는 "
            "--set-secrets=STOCK_API_KEY=STOCK_API_KEY:latest 로 주입하세요."
        )
    spec = catalog.get(service)
    if spec is None:
        raise FscError(
            f"'{service}'는 이 서버가 다루는 API가 아닙니다. "
            "search_apis로 사용 가능한 서비스를 먼저 확인하세요."
        )
    op_spec = spec["operations"].get(operation)
    if op_spec is None:
        raise FscError(
            f"'{service}'에 '{operation}' 오퍼레이션이 없습니다. "
            f"가능한 값: {', '.join(spec['operations'])}"
        )

    query: dict[str, Any] = {"serviceKey": API_KEY, "numOfRows": rows, "pageNo": page}
    style = op_spec.get("param_style", "resultType")
    if style == "resultType":
        query["resultType"] = "json"
    elif style == "_type":
        query["_type"] = "json"
    # style == "xml"이면 포맷 파라미터를 주지 않고 XML을 받아 파싱한다.

    for key, value in (params or {}).items():
        if value not in (None, ""):
            query[key] = value

    url = f'{spec["base_url"]}/{service}/{operation}'

    # 캐시 키에 인증키는 넣지 않는다(계정당 하나이고 남길 이유가 없다).
    cache_key = json.dumps(
        [service, operation,
         sorted((k, str(v)) for k, v in query.items() if k != "serviceKey")],
        ensure_ascii=False, sort_keys=True)
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    # 회로가 열려 있으면 상류를 건드리지 않는다. 다만 절반 열림 주기가 되면
    # 한 건은 통과시켜 회복 여부를 확인한다.
    remaining = _throttle.acquire()
    if remaining:
        raise FscError(
            f"{service}/{operation} — 연결 실패가 반복되어 호출을 잠시 멈춘 상태입니다. "
            f"길어도 {int(remaining)}초 뒤 자동으로 풀리며, 상류가 먼저 회복되면 "
            f"{int(BREAKER_PROBE_INTERVAL)}초 주기의 확인 호출로 그 전에 풀립니다."
        )

    last_error: str | None = None
    connect_failed = False
    for attempt in range(MAX_ATTEMPTS):
        if attempt:
            _backoff(attempt - 1)
        _throttle.wait_turn()
        try:
            with httpx.Client(timeout=TIMEOUT) as client:
                resp = client.get(url, params=query)
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            # 연결 실패는 순간적인 경우가 많다(콜드 스타트 직후 특히). 같은
            # 호출 안에서 백오프를 두고 다시 시도하고, 모든 시도가 실패했을
            # 때만 회로에 1회로 기록한다.
            connect_failed = True
            last_error = f"{type(exc).__name__}: 연결 실패"
            continue
        except httpx.TransportError as exc:
            # 읽기 타임아웃 등 연결 이후의 실패는 재시도할 가치가 있다.
            last_error = f"{type(exc).__name__}: {exc}"
            continue

        if resp.status_code == 429 or resp.status_code >= 500:
            last_error = f"HTTP {resp.status_code}"
            continue
        if resp.status_code >= 400:
            # 4xx는 재시도해도 같다. 경로나 파라미터가 틀린 경우가 대부분이라
            # 무엇을 확인해야 하는지 함께 알려 준다.
            raise FscError(
                f"{service}/{operation} — HTTP {resp.status_code}. "
                f"호출 주소가 맞는지 확인하세요 (base_url={spec['base_url']}). "
                f"응답: {resp.text[:120]}"
            )

        body = resp.text.strip()
        if not body:
            last_error = "빈 응답"
            continue

        if body.startswith("<"):
            try:
                result = _parse_xml(body)
            except ET.ParseError as exc:
                raise FscError(f"XML 파싱 실패: {body[:200]}") from exc
            _throttle.record_success()
            _cache.put(cache_key, result)
            return result

        try:
            data = resp.json()
        except ValueError as exc:
            raise FscError(f"JSON이 아닌 응답: {body[:200]}") from exc

        try:
            _check_json(data)
        except FscError as exc:
            code = str(exc).split(":")[0].replace("금융위 API ", "").strip()
            if code in RETRYABLE:
                last_error = str(exc)
                continue
            raise

        payload = (data.get("response") or {}).get("body") or {}
        result = {
            "total_count": payload.get("totalCount"),
            "page_no": payload.get("pageNo"),
            "num_of_rows": payload.get("numOfRows"),
            "rows": _dig_items(payload),
        }
        _throttle.record_success()
        _cache.put(cache_key, result)
        return result

    if connect_failed:
        # 모든 시도가 연결에서 막혔을 때만 회로에 기록한다.
        _throttle.record_connect_failure()
        raise FscError(
            f"{service}/{operation} — apis.data.go.kr에 {MAX_ATTEMPTS}회 모두 "
            f"연결하지 못했습니다 ({last_error}). 호출이 몰리면 소스 IP 단위로 "
            "접속이 제한될 수 있습니다. 잠시 후 다시 시도하세요."
        )

    raise FscError(
        f"{service}/{operation} 호출이 {MAX_ATTEMPTS}회 모두 실패했습니다. "
        f"마지막 오류 — {last_error}"
    )


def search(catalog: dict[str, Any], query: str = "", limit: int = 8) -> dict:
    """카탈로그에서 오퍼레이션을 찾는다.

    반환에 응답 필드 목록이 들어 있고, 이 필드명이 곧 필터 파라미터로 쓰인다.
    """
    term = query.strip().lower()
    hits = []
    for service, spec in catalog.items():
        for operation, op_spec in spec["operations"].items():
            blob = " ".join([
                service, operation, spec["name"], spec["purpose"],
                " ".join(op_spec["fields"]),
            ]).lower()
            if term and term not in blob:
                continue
            score = 0 if (term and (term in spec["name"].lower()
                                    or term in operation.lower())) else 1
            hits.append((score, {
                "service": service,
                "operation": operation,
                "api_name": spec["name"],
                "purpose": spec["purpose"],
                "fields": op_spec["fields"],
                "approx_total_rows": op_spec.get("total_count"),
            }))
    hits.sort(key=lambda h: (h[0], h[1]["service"]))
    return {"total_count": len(hits), "rows": [h[1] for h in hits[:limit]]}


def configure_transport_security(mcp) -> None:
    """DNS 리바인딩 보호 설정.

    MCP SDK는 기본적으로 Host 헤더를 localhost 계열로만 허용한다. Cloud Run에
    올리면 Host가 `<service>-<projectnumber>.<region>.run.app`이 되어
    `421 Invalid Host header`로 전부 거부되고, Gemini Enterprise 쪽에서는
    "도구 0개"로만 보여 원인을 찾기 어렵다.
    """
    from mcp.server.transport_security import TransportSecuritySettings

    hosts = [h.strip() for h in os.environ.get("MCP_ALLOWED_HOSTS", "").split(",") if h.strip()]
    if hosts:
        mcp.settings.transport_security = TransportSecuritySettings(
            allowed_hosts=hosts,
            allowed_origins=[f"https://{h}" for h in hosts],
        )
    elif os.environ.get("K_SERVICE"):  # Cloud Run이 주입하는 변수
        mcp.settings.transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=False
        )


def run(mcp) -> None:
    """Cloud Run / Gemini Enterprise 전제로 서버를 띄운다."""
    mcp.settings.host = "0.0.0.0"
    mcp.settings.port = int(os.environ.get("PORT", 8080))
    # Cloud Run은 세션 어피니티가 기본 off라 stateful 세션이 인스턴스 간에
    # 유지되지 않는다. stateless로 두어야 도구 호출이 안정적이다.
    mcp.settings.stateless_http = True
    configure_transport_security(mcp)
    # Gemini Enterprise는 StreamableHTTP만 지원한다. SSE로 바꾸지 말 것.
    mcp.run(transport="streamable-http")
