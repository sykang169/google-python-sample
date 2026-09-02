"""DART MCP Server — 금융감독원 전자공시(OPEN DART) API 82개를 4개 도구로 노출한다.

설계 의도
---------
DART는 JSON 엔드포인트가 82개다. 이를 그대로 MCP 도구로 펼치면 `tools/list`
페이로드가 약 3.7만 토큰이 되어, 에이전트가 MCP 서버를 여러 개 붙이는 순간
컨텍스트 예산을 다 먹는다. 그래서 "점진적 공개(progressive disclosure)" 구조를 쓴다.

  resolve_company  회사명 -> corp_code (거의 모든 호출의 첫 단계)
  search_dart_apis 82개 카탈로그에서 필요한 엔드포인트와 파라미터 명세를 찾는다
  call_dart_api    찾은 엔드포인트를 결정론적으로 실행한다
  ask_dart         (선택) 서버 내부 Gemini가 엔드포인트를 골라 실행한다

앞의 3개는 LLM을 쓰지 않는다. 판단은 호출하는 에이전트가 하고 이 서버는
카탈로그와 실행만 담당하므로 결정론적이고 디버깅이 쉽다. ask_dart는 도메인
지식이 필요한 질문("배당"이 alotMatter인지 stockTotqySttus인지 같은)을 위한
편의 도구이며, 어떤 엔드포인트를 골랐는지 함께 반환해 추적 가능하게 한다.
DART_ENABLE_ASK=0으로 끌 수 있다.

Gemini Enterprise 데이터 스토어가 소비할 수 있도록 StreamableHTTP를 쓴다.
(Gemini Enterprise는 레거시 SSE 전송을 지원하지 않는다.)
"""

from __future__ import annotations

import gzip
import json
import os
import pathlib
import random
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

DART_BASE = "https://opendart.fss.or.kr/api"
TIMEOUT = httpx.Timeout(30.0, connect=10.0)
ASSETS = pathlib.Path(__file__).parent / "assets"

API_KEY = os.environ.get("DART_API_KEY", "")
ENABLE_ASK = os.environ.get("DART_ENABLE_ASK", "1") != "0"

# 조회 전용 도구 annotation. readOnlyHint=True면 Gemini Enterprise가
# 호출 전 사용자 확인 단계를 건너뛴다.
READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True}

# DART가 HTTP 200과 함께 돌려주는 상태 코드.
DART_STATUS = {
    "000": None,
    "010": "등록되지 않은 키입니다.",
    "011": "사용할 수 없는 키입니다. 오픈API에 등록되었으나 일시적으로 사용 중지된 키입니다.",
    "012": "접근할 수 없는 IP입니다.",
    "013": "조회된 데이터가 없습니다.",
    "014": "파일이 존재하지 않습니다.",
    "020": "요청 제한을 초과하였습니다. (분당 1,000건)",
    "021": "조회 가능한 회사 개수가 초과하였습니다. (최대 100건)",
    "100": "필드의 부적절한 값입니다.",
    "101": "부적절한 접근입니다. (존재하지 않는 엔드포인트)",
    "800": "시스템 점검으로 인한 서비스가 중지 중입니다.",
    "900": "정의되지 않은 오류가 발생하였습니다.",
    "901": "사용자 계정의 개인정보 보유기간이 만료되었습니다.",
}

# 코드별 "다음에 무엇을 할 것인가". 증상만 주면 013(데이터 없음)과
# 101(없는 엔드포인트)을 똑같이 "조회 실패"로 다루게 된다.
DART_NEXT_STEP = {
    "013": "실패가 아니다. 사업연도를 한 해 낮추거나 reprt_code를 바꿔 최소 한 번은"
           " 재시도한다 — 실제로 대부분의 원인이다. 그래도 없으면 '해당 조건의 공시"
           " 없음'으로 답한다.",
    "010": "인증키 문제다. 재시도해도 같으므로 가져오지 못했다고 답한다.",
    "011": "일시 중지된 키다. 재시도해도 같다.",
    "012": "허용되지 않은 IP다. 재시도해도 같다.",
    "020": "분당 요청 제한을 넘었다. 같은 호출을 즉시 반복하지 않는다.",
    "021": "조회 회사 수가 한 번에 처리할 수 있는 범위를 넘었다. 나눠서 조회한다.",
    "100": "파라미터 값이 형식에 맞지 않는다. search_dart_apis로 명세를 다시 확인한다.",
    "101": "엔드포인트 이름을 지어냈다는 신호다. search_dart_apis로 실제 경로를 찾는다.",
    "800": "시스템 점검 중이다. 잠시 후 재시도한다.",
}


def dart_message(status: str, fallback: str = "") -> str:
    """상태 코드를 "증상 — 다음 행동"으로 만든다. 모델이 읽는 문자열이다."""
    what = DART_STATUS.get(status) or fallback or "알 수 없는 오류"
    step = DART_NEXT_STEP.get(status)
    return f"{what} — {step}" if step else what


# 재시도 정책. 한국 공공 API는 앞단에서 연결을 끊거나 일시적으로 스로틀하는
# 구간이 실제로 관측된다. 지수 백오프 + 지터로 짧은 장애 구간을 넘긴다.
MAX_ATTEMPTS = 3
BACKOFF_BASE = 1.0
BACKOFF_CAP = 6.0

# 재시도할 가치가 있는 DART status. 013(데이터 없음)이나 100(잘못된 값)처럼
# 다시 호출해도 같은 결과가 나오는 것은 넣지 않는다.
RETRYABLE_STATUS = {
    "020",  # 요청 제한 초과 (분당 1,000건)
    "800",  # 시스템 점검
    "900",  # 정의되지 않은 오류
}

# 서버 단위 전제. MCP initialize 응답으로 나간다.
INSTRUCTIONS = """금융감독원 전자공시(OPEN DART) — 공시 원문·사업보고서·재무제표·XBRL.

엔드포인트 82개를 resolve_company → search_dart_apis → call_dart_api 순으로 연다.
corp_code를 먼저 확정하지 않으면 동명 법인이 섞인다. 국내 공시 전용이며 SEC
EDGAR 같은 해외 공시는 다루지 않는다."""

mcp = FastMCP("dart-mcp", instructions=INSTRUCTIONS)


class DartError(RuntimeError):
    """DART가 status 코드로 돌려주는 오류."""


# ── 자산 로딩 (이미지에 구워져 있다) ────────────────────────────────────────

def _load_catalog() -> list[dict]:
    return json.loads((ASSETS / "catalog.json").read_text(encoding="utf-8"))


def _load_corp_index() -> list[list[str]]:
    with gzip.open(ASSETS / "corp_index.json.gz", "rt", encoding="utf-8") as fh:
        return json.load(fh)


CATALOG = _load_catalog()
BY_ENDPOINT = {c["endpoint"]: c for c in CATALOG}
CORPS = _load_corp_index()


# ── 공통 호출 ───────────────────────────────────────────────────────────────

def _backoff(attempt: int) -> None:
    """attempt(0부터)에 따라 지터를 섞어 대기한다."""
    delay = min(BACKOFF_BASE * (2 ** attempt), BACKOFF_CAP)
    time.sleep(delay * (0.5 + random.random()))


def _call(endpoint: str, params: dict[str, Any]) -> dict:
    """DART API를 호출한다.

    네트워크 오류, HTTP 5xx/429, RETRYABLE_STATUS 응답은 최대 MAX_ATTEMPTS회까지
    지수 백오프로 재시도한다.
    """
    if not API_KEY:
        raise DartError(
            "DART_API_KEY가 설정되지 않았습니다. Cloud Run에서는 "
            "--set-secrets=DART_API_KEY=DART_API_KEY:latest 로 주입하세요."
        )
    query = {k: str(v) for k, v in params.items() if v not in (None, "")}
    query["crtfc_key"] = API_KEY

    last_error: str | None = None
    for attempt in range(MAX_ATTEMPTS):
        if attempt:
            _backoff(attempt - 1)
        try:
            with httpx.Client(timeout=TIMEOUT) as client:
                resp = client.get(f"{DART_BASE}/{endpoint}.json", params=query)
        except httpx.TransportError as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            continue

        if resp.status_code == 429 or resp.status_code >= 500:
            last_error = f"HTTP {resp.status_code}"
            continue
        resp.raise_for_status()

        try:
            data = resp.json()
        except ValueError as exc:
            raise DartError(
                f"DART가 JSON이 아닌 응답을 반환했습니다: {resp.text[:200]}") from exc

        # DART는 오류도 HTTP 200으로 준다. status를 반드시 봐야 한다.
        status = str(data.get("status", ""))
        if status and status != "000":
            message = f"DART {status}: {dart_message(status, data.get('message', ''))}"
            if status in RETRYABLE_STATUS:
                last_error = message
                continue
            raise DartError(message)
        return data

    raise DartError(
        f"DART 호출이 {MAX_ATTEMPTS}회 모두 실패했습니다. 마지막 오류 — {last_error}"
    )


def _summarize(rows: list[dict]) -> dict:
    """DART 응답 행들의 건수와 범주형 필드 분포를 미리 계산한다.

    LLM이 수십 행짜리 JSON을 직접 세면 틀리기 쉽다("임원 몇 명" 같은 질문에서
    실제로 오답이 나왔다). 서버가 세어서 함께 돌려주면 그 실수가 사라진다.

    값의 종류가 2~8개인 필드만 고른다. 1개면 상수(corp_name 등)라 정보가 없고,
    9개 이상이면 이름·경력처럼 분포가 의미 없는 필드다.
    """
    if not rows:
        return {"row_count": 0}

    summary: dict[str, Any] = {"row_count": len(rows)}
    distributions: dict[str, dict[str, int]] = {}

    for field in rows[0]:
        values = [str(r.get(field, "")) for r in rows]
        counts: dict[str, int] = {}
        for v in values:
            counts[v] = counts.get(v, 0) + 1
        if 2 <= len(counts) <= 8:
            distributions[field] = dict(
                sorted(counts.items(), key=lambda kv: -kv[1]))

    if distributions:
        summary["field_distributions"] = distributions
    return summary


# ── 도구 1: 회사 해석 ───────────────────────────────────────────────────────

@mcp.tool(annotations=READ_ONLY)
def resolve_company(name: str, listed_only: bool = False, limit: int = 10) -> dict:
    """회사명으로 DART 고유번호(corp_code)를 찾는다. 거의 모든 조회의 첫 단계다.

    DART의 다른 모든 API는 회사명이 아니라 8자리 corp_code를 요구한다.
    이 서버는 11.8만 개 기업 인덱스를 내장하고 있어 외부 호출 없이 즉시 응답한다.

    정확히 일치하는 이름, 상장사, 부분 일치 순으로 정렬해 반환한다.

    Args:
        name: 회사명 또는 그 일부 (예: "삼성전자", "카카오").
        listed_only: True면 상장사(stock_code가 있는 곳)만 반환한다.
            동명의 비상장 계열사를 걸러낼 때 쓴다.
        limit: 최대 반환 건수.

    Returns:
        rows: [{corp_code, corp_name, stock_code}] — stock_code가 빈 문자열이면 비상장.
    """
    term = name.strip()
    if not term:
        raise DartError("회사명을 입력하세요.")

    hits = []
    for code, corp_name, stock in CORPS:
        if term not in corp_name:
            continue
        if listed_only and not stock:
            continue
        # 정렬 우선순위: 완전일치 > 상장사 > 이름이 짧은 순(부분일치 노이즈 억제)
        rank = (0 if corp_name == term else 1, 0 if stock else 1, len(corp_name))
        hits.append((rank, {"corp_code": code, "corp_name": corp_name, "stock_code": stock}))

    hits.sort(key=lambda h: h[0])
    return {"total_count": len(hits), "rows": [h[1] for h in hits[:limit]]}


# ── 도구 2: API 검색 ────────────────────────────────────────────────────────

@mcp.tool(annotations=READ_ONLY)
def search_dart_apis(query: str = "", group: str = "", limit: int = 8) -> dict:
    """DART의 82개 API 중 필요한 것을 찾고 그 파라미터 명세를 받는다.

    call_dart_api를 호출하기 전에 이 도구로 엔드포인트 이름과 필요한 파라미터를
    먼저 확인한다. 82개를 전부 도구로 노출하지 않고 여기서 검색하게 하는 이유는
    컨텍스트를 아끼기 위해서다.

    Args:
        query: 검색어. 한글 API명/설명과 영문 엔드포인트명에 부분 일치시킨다
            (예: "배당", "재무제표", "임원", "최대주주", "합병").
            비우면 group 기준으로 목록을 반환한다.
        group: 그룹으로 좁힌다. 다음 중 하나 —
            "공시정보", "정기보고서 주요정보", "정기보고서 재무정보",
            "지분공시", "주요사항보고서", "증권신고서".
        limit: 최대 반환 건수.

    Returns:
        rows: [{endpoint, name, group_name, desc, params}]
            params의 각 항목은 {name, ko, type, required, desc}이며,
            crtfc_key(인증키)는 서버가 자동으로 넣으므로 전달할 필요가 없다.
    """
    term = query.strip()
    rows = CATALOG
    if group:
        rows = [c for c in rows if c["group_name"] == group]
    if term:
        low = term.lower()
        rows = [
            c for c in rows
            if term in c["name"] or term in c["desc"] or low in c["endpoint"].lower()
        ]
        # 이름에 걸린 것을 설명에만 걸린 것보다 앞세운다.
        rows.sort(key=lambda c: (0 if term in c["name"] else 1, c["endpoint"]))

    trimmed = []
    for c in rows[:limit]:
        trimmed.append({
            "endpoint": c["endpoint"],
            "name": c["name"],
            "group_name": c["group_name"],
            "desc": c["desc"],
            # crtfc_key는 서버가 채우므로 노출하지 않는다.
            "params": [p for p in c["params"] if p["name"] != "crtfc_key"],
        })
    return {"total_count": len(rows), "rows": trimmed}


# ── 도구 3: 실행 ────────────────────────────────────────────────────────────

@mcp.tool(annotations=READ_ONLY)
def call_dart_api(endpoint: str, params: dict | None = None) -> dict:
    """search_dart_apis로 찾은 DART 엔드포인트를 실행한다.

    인증키는 서버가 넣으므로 params에 포함하지 않는다.

    자주 쓰는 파라미터:
        corp_code:  8자리 고유번호 (resolve_company로 획득)
        bsns_year:  사업연도 4자리. 2015년 이후만 제공된다.
        reprt_code: 1분기 "11013", 반기 "11012", 3분기 "11014", 사업보고서 "11011"
        bgn_de / end_de: 기간 조회형 API의 시작/종료일 (YYYYMMDD)

    Args:
        endpoint: 엔드포인트 이름 (예: "alotMatter", "fnlttSinglAcntAll").
            ".json"은 붙이지 않는다.
        params: 파라미터 딕셔너리 (예: {"corp_code": "00126380",
            "bsns_year": "2025", "reprt_code": "11011"}).

    Returns:
        DART 원본 응답(status/message/list)에 `summary`를 덧붙여 반환한다.
        summary.row_count는 결과 행 수이고, summary.field_distributions는
        범주형 필드의 값별 건수다. **"몇 명/몇 건" 같은 집계 질문은 행을 직접
        세지 말고 이 값을 쓸 것.** 예를 들어 임원현황(exctvSttus)의
        rgist_exctv_at은 "사내이사"/"사외이사"/"미등기" 세 값을 가지며,
        summary가 각각의 인원수를 이미 세어 준다.
    """
    endpoint = endpoint.strip().removesuffix(".json")
    spec = BY_ENDPOINT.get(endpoint)
    if spec is None:
        raise DartError(
            f"'{endpoint}'는 DART에 없는 엔드포인트입니다. "
            "search_dart_apis로 올바른 이름을 먼저 확인하세요."
        )

    params = dict(params or {})
    missing = [
        p["name"] for p in spec["params"]
        if p["required"] and p["name"] != "crtfc_key" and not params.get(p["name"])
    ]
    if missing:
        raise DartError(
            f"'{endpoint}'({spec['name']})에 필수 파라미터가 빠졌습니다: {', '.join(missing)}. "
            "search_dart_apis로 명세를 확인하세요."
        )

    data = _call(endpoint, params)
    data["summary"] = _summarize(data.get("list") or [])
    return data


# ── 도구 4: 내부 LLM 라우팅 (선택) ──────────────────────────────────────────

_ROUTER_PROMPT = """\
너는 DART(한국 금융감독원 전자공시) API 라우터다.
아래 API 목록에서 사용자 질문에 답하기에 가장 적합한 엔드포인트 하나와 파라미터를 고른다.

오늘은 {today} (KST)다. 현재 사업연도는 {this_year}년이다.

규칙:
- corp_code는 이미 해석되어 주어지면 그대로 쓴다.
- bsns_year는 4자리, 2015년 이상만 가능하다.
  **명시가 없으면 {default_year}를 쓴다.** 사업보고서는 해당 연도가 끝난 뒤
  이듬해 3월경에 제출되므로, 지금 조회 가능한 가장 최근 사업연도는
  {default_year}년이다. 학습 시점 기준으로 연도를 추측하지 말 것.
- reprt_code: 1분기 11013, 반기 11012, 3분기 11014, 사업보고서 11011. 기본은 11011.
- bgn_de/end_de는 YYYYMMDD.
- crtfc_key는 절대 포함하지 않는다.

API 목록:
{catalog}

질문: {question}
{corp_hint}

JSON만 출력한다: {{"endpoint": "...", "params": {{...}}, "reason": "한 줄 근거"}}
"""


@mcp.tool(annotations=READ_ONLY)
def ask_dart(question: str, corp_name: str = "", bsns_year: str = "") -> dict:
    """자연어 질문 하나로 DART를 조회한다. 어떤 엔드포인트를 써야 할지 모를 때 쓴다.

    서버 내부의 Gemini가 82개 API 중 하나를 고르고 파라미터를 채워 실행한다.
    선택 결과(routed)를 데이터와 함께 반환하므로 무엇이 호출됐는지 확인할 수 있다.

    결정론적인 동작이 필요하거나 호출 비용을 아끼려면
    search_dart_apis + call_dart_api 조합을 쓰는 편이 낫다.

    Args:
        question: 자연어 질문 (예: "삼성전자 2025년 배당 현황").
        corp_name: 회사명. 주면 서버가 먼저 corp_code로 해석해 넘긴다.
        bsns_year: 사업연도 4자리. 주면 그 값을 강제한다.

    Returns:
        routed: 선택된 {endpoint, params, reason}
        summary: 결과 건수와 범주형 필드 분포. **"몇 명/몇 건" 질문은 반드시
            이 값을 쓴다.** data.list를 직접 세면 틀리기 쉽다.
        data: 실행 결과 (선택이 실패하면 없음)
    """
    if not ENABLE_ASK:
        raise DartError(
            "ask_dart는 이 배포에서 비활성화되어 있습니다(DART_ENABLE_ASK=0). "
            "search_dart_apis + call_dart_api를 사용하세요."
        )

    corp_hint = ""
    resolved = None
    if corp_name:
        found = resolve_company(corp_name, limit=1)
        if found["rows"]:
            resolved = found["rows"][0]
            corp_hint = f"corp_code: {resolved['corp_code']} ({resolved['corp_name']})"

    # 카탈로그를 라우팅에 필요한 최소 형태로 줄여 프롬프트에 넣는다.
    compact = "\n".join(
        f"- {c['endpoint']}: {c['name']} | {c['desc'][:60]} | 파라미터: "
        + ",".join(p["name"] for p in c["params"] if p["name"] != "crtfc_key")
        for c in CATALOG
    )

    try:
        from google import genai
    except ImportError as exc:
        raise DartError("google-genai가 설치되지 않아 ask_dart를 쓸 수 없습니다.") from exc

    client = genai.Client(
        vertexai=True,
        project=os.environ.get("GOOGLE_CLOUD_PROJECT", ""),
        location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
    )
    # Cloud Run은 UTC로 돈다. 한국 사업연도 기준이므로 KST로 계산한다.
    # tzdata 없이도 되도록 고정 오프셋을 쓴다.
    today = datetime.now(timezone(timedelta(hours=9)))
    prompt = _ROUTER_PROMPT.format(
        catalog=compact,
        question=question,
        corp_hint=corp_hint,
        today=today.strftime("%Y-%m-%d"),
        this_year=today.year,
        # 사업보고서는 이듬해 3월경 제출되므로 직전 연도가 최신이다.
        default_year=today.year - 1,
    )
    result = client.models.generate_content(
        model=os.environ.get("DART_ROUTER_MODEL", "gemini-2.5-flash"),
        contents=prompt,
        config={"response_mime_type": "application/json", "temperature": 0},
    )

    try:
        routed = json.loads(result.text)
    except (ValueError, AttributeError) as exc:
        raise DartError(f"라우터가 유효한 JSON을 내지 않았습니다: {result.text[:200]}") from exc

    params = dict(routed.get("params") or {})
    if resolved:
        params["corp_code"] = resolved["corp_code"]
    if bsns_year:
        params["bsns_year"] = bsns_year
    routed["params"] = params

    data = call_dart_api(routed.get("endpoint", ""), params)
    return {
        "routed": routed,
        "resolved_company": resolved,
        # 집계 질문은 data.list를 세지 말고 이 값을 쓸 것.
        "summary": data.get("summary"),
        "data": data,
    }


# ── 기동 ────────────────────────────────────────────────────────────────────

def _configure_transport_security() -> None:
    """DNS 리바인딩 보호 설정.

    MCP SDK는 기본적으로 Host 헤더를 localhost 계열로만 허용한다. Cloud Run에
    올리면 Host가 `<service>-<projectnumber>.<region>.run.app`이 되어
    `421 Invalid Host header`로 전부 거부되고, Gemini Enterprise 쪽에서는
    "도구 0개"로만 보여 원인을 찾기 어렵다.
    """
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


if __name__ == "__main__":
    mcp.settings.host = "0.0.0.0"
    mcp.settings.port = int(os.environ.get("PORT", 8080))

    # Cloud Run은 요청을 여러 인스턴스에 분산하고 세션 어피니티가 기본 off다.
    # MCP StreamableHTTP는 기본이 stateful이라 initialize로 만든 세션이 특정
    # 인스턴스 메모리에만 존재하고, 다음 요청이 다른 인스턴스로 가면 세션을
    # 찾지 못한다. 그러면 클라이언트(Gemini Enterprise)는 도구를 호출하려다
    # 계속 실패·재시도하고, 로그에는 "Created new transport"가 반복되며
    # "Truncated response body" 타임아웃이 남는다.
    #
    # stateless 모드에서는 요청이 각자 완결되므로 인스턴스가 몇 개든 안전하다.
    mcp.settings.stateless_http = True

    _configure_transport_security()
    # Gemini Enterprise는 StreamableHTTP만 지원한다. SSE로 바꾸지 말 것.
    mcp.run(transport="streamable-http")
