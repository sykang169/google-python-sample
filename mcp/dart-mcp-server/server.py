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

공시 원문(document.xml)은 JSON이 아니라 ZIP을 주므로 카탈로그 82개에 들어가지
못한다. 같은 이유로 통째로 반환할 수도 없다 — 사업보고서 본문은 500만 자를
넘는다. 목차와 본문을 나눈 전용 도구 두 개로 연다.

  get_disclosure_outline   목차만 (제목 목록과 각 항목의 분량)
  get_disclosure_section   고른 항목의 본문만 (기본 상한 2만 자)

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
import html
import io
import json
import logging
import os
import pathlib
import random
import re
import time
import zipfile
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

DART_BASE = "https://opendart.fss.or.kr/api"
TIMEOUT = httpx.Timeout(30.0, connect=10.0)
ASSETS = pathlib.Path(__file__).parent / "assets"

logger = logging.getLogger("dart-mcp")

# httpx는 INFO에서 요청 URL을 통째로 남긴다. DART는 인증키를 쿼리 파라미터로만
# 받으므로(헤더 방식이 없다) 그대로 두면 **Cloud Logging에 키 원문이 쌓인다.**
# 로그 레벨을 올려 URL이 남지 않게 한다.
logging.getLogger("httpx").setLevel(logging.WARNING)

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
EDGAR 같은 해외 공시는 다루지 않는다.

공시 원문 본문이 필요하면 call_dart_api("list", ...)로 rcept_no를 얻은 뒤
get_disclosure_outline으로 목차를 보고 get_disclosure_section으로 해당 항목만
읽는다. 본문은 500만 자를 넘을 수 있어 통째로 반환하지 않는다."""

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


# ── 공시 원문 ────────────────────────────────────────────────────────────────
# document.xml은 다른 82개와 성격이 다르다. JSON이 아니라 ZIP 바이너리를 주고
# 그 안에 DART 고유 태그로 짜인 XML이 들어 있다. 그래서 카탈로그에서 빠져 있고
# call_dart_api로는 부를 수 없다. 전용 도구로 연다.
#
# 분량이 진짜 문제다. 삼성전자 2024 사업보고서(20250311001085)를 실측하면
# 압축 676KB, 풀면 XML 3개 7.6MB, 본문 텍스트만 580만 자다. 통째로 돌려주면
# 어떤 모델의 컨텍스트도 넘는다. 그래서 두 단계로 나눈다.
#
#   get_disclosure_outline   목차만 준다 (제목 135개, 수 KB)
#   get_disclosure_section   고른 항목의 본문만 준다 (기본 상한 2만 자)
#
# 목차의 chars가 곧 그 항목을 요청했을 때 받게 될 분량이다. 상위 제목은 하위
# 항목을 포함하지 않는다 — 포함시키면 "II. 사업의 내용" 하나가 14만 자가 되어
# 나누는 의미가 사라진다.

DOC_BASE = "https://opendart.fss.or.kr/api/document.xml"
DOC_CACHE_TTL = 600.0          # 목차를 보고 섹션을 고르는 왕복을 한 번의 다운로드로
DOC_CACHE_MAX = 2              # 문서 하나가 수십 MB라 넉넉히 두지 않는다
SECTION_CHARS_DEFAULT = 20_000
SECTION_CHARS_CAP = 60_000     # 모델이 max_chars를 크게 불러도 여기서 막는다
TABLE_ROWS_DEFAULT = 200       # 표 하나에서 가져올 최대 행 수

# 문서 안의 항목 이름을 모를 때 좁히는 힌트. adk-finance-agent의
# dart_analytics에서 쓰던 분류를 그대로 가져왔다.
FOCUS_KEYWORDS = {
    "financial": ["재무", "손익", "현금흐름", "자본변동", "매출", "자산", "부채", "주석"],
    "governance": ["임원", "주주", "감사", "지배구조", "이사회", "계열회사"],
    "business": ["사업", "영업", "시장", "경쟁", "생산", "수주", "연구개발"],
}

_doc_cache: "OrderedDict[str, tuple[float, dict]]" = OrderedDict()

# GCS 캐시. DART의 document.xml은 676KB를 받는 데 실측 43초가 걸린다(약 15KB/s).
# 병목은 우리 파싱(0.2초)이 아니라 DART 서버다. 대신 **공시 원문은 불변이다** —
# 접수번호가 확정되면 내용이 바뀌지 않으므로 무효화를 고민할 필요가 없다.
#
# 인메모리 캐시는 같은 인스턴스로 연속 호출될 때만 듣는다. Cloud Run은
# stateless_http에 인스턴스가 여러 개라 다음 호출이 다른 인스턴스로 가면 다시
# 43초를 기다린다. 파싱 결과를 버킷에 두면 그 경우에도 수백 ms로 끝난다.
#
# 버킷이 없으면(로컬 개발) 조용히 건너뛴다. GCS 오류도 요청을 실패시키지
# 않는다 — 캐시는 최적화이지 정합성의 근거가 아니다.
DOC_BUCKET = os.environ.get("DART_DOC_CACHE_BUCKET", "")
_gcs_client: Any = None


def _bucket() -> Any:
    """GCS 버킷 핸들. 버킷 미설정이거나 라이브러리가 없으면 None."""
    global _gcs_client
    if not DOC_BUCKET:
        return None
    if _gcs_client is None:
        try:
            from google.cloud import storage  # 버킷을 쓸 때만 import한다
            _gcs_client = storage.Client()
        except Exception as exc:  # 자격증명 없음, 라이브러리 없음 등
            logger.warning("GCS 캐시를 쓸 수 없습니다: %s", exc)
            _gcs_client = False
    return _gcs_client.bucket(DOC_BUCKET) if _gcs_client else None


def _cache_read(rcept_no: str) -> dict | None:
    bucket = _bucket()
    if bucket is None:
        return None
    try:
        blob = bucket.blob(f"document/{rcept_no}.json.gz")
        if not blob.exists():
            return None
        return json.loads(gzip.decompress(blob.download_as_bytes()))
    except Exception as exc:
        logger.warning("GCS 캐시 읽기 실패(%s): %s", rcept_no, exc)
        return None


def _cache_write(rcept_no: str, parsed: dict) -> None:
    bucket = _bucket()
    if bucket is None:
        return
    try:
        body = gzip.compress(json.dumps(parsed, ensure_ascii=False).encode())
        bucket.blob(f"document/{rcept_no}.json.gz").upload_from_string(
            body, content_type="application/gzip")
    except Exception as exc:
        logger.warning("GCS 캐시 쓰기 실패(%s): %s", rcept_no, exc)


def _fetch_document_zip(rcept_no: str) -> bytes:
    """document.xml을 내려받는다. 성공하면 ZIP 바이트다.

    _call은 `.json`을 붙이고 JSON을 기대하므로 쓸 수 없다. 오류일 때 DART는
    ZIP이 아니라 XML 본문을 200으로 주므로 매직 넘버로 갈라낸다.
    """
    if not API_KEY:
        raise DartError(
            "DART_API_KEY가 설정되지 않았습니다. Cloud Run에서는 "
            "--set-secrets=DART_API_KEY=DART_API_KEY:latest 로 주입하세요."
        )
    if not (rcept_no.isdigit() and len(rcept_no) == 14):
        raise DartError(
            f"rcept_no는 14자리 숫자입니다(받은 값: {rcept_no!r}). "
            "call_dart_api('list', ...)로 공시 목록을 조회하면 rcept_no가 나옵니다."
        )

    last_error: str | None = None
    for attempt in range(MAX_ATTEMPTS):
        if attempt:
            _backoff(attempt - 1)
        try:
            with httpx.Client(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
                resp = client.get(DOC_BASE, params={"crtfc_key": API_KEY,
                                                    "rcept_no": rcept_no})
        except httpx.TransportError as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            continue

        if resp.status_code == 429 or resp.status_code >= 500:
            last_error = f"HTTP {resp.status_code}"
            continue
        resp.raise_for_status()

        if resp.content[:2] == b"PK":
            return resp.content

        # ZIP이 아니면 오류 XML이다. status를 뽑아 평소와 같은 메시지로 만든다.
        text = resp.content.decode("utf-8", "replace")
        status = (re.search(r"<status>(\d+)</status>", text) or [None, ""])[1]
        message = f"DART {status}: {dart_message(status)}" if status else \
            f"DART가 ZIP이 아닌 응답을 반환했습니다: {text[:200]}"
        if status in RETRYABLE_STATUS:
            last_error = message
            continue
        raise DartError(message)

    raise DartError(
        f"공시 원문 조회가 {MAX_ATTEMPTS}회 모두 실패했습니다. 마지막 오류 — {last_error}"
    )


def _render_table(block: str, max_rows: int) -> str:
    """<TABLE> 한 덩어리를 행 단위 평문으로 만든다.

    셀은 ` | `로, 행은 줄바꿈으로 잇는다. 원본 구현은 20행에서 잘랐는데
    연결재무상태표가 그보다 길어 조용히 잘린 표를 받게 되므로 호출자가 정한다.
    """
    rows: list[str] = []
    for tr in re.findall(r"<TR\b[^>]*>(.*?)</TR>", block, re.S | re.I):
        # 셀 태그가 넷이다. TD/TH는 일반 표, **TE/TU는 재무제표 표**에 쓰인다.
        # TD/TH만 보면 연결 재무상태표가 머리글 한 줄만 남고 통째로 사라진다
        # (2024 사업보고서 실측: TE 225개, TH 4개, TD 0개).
        cells = [_strip_tags(c) for c in
                 re.findall(r"<T[DHEU]\b[^>]*>(.*?)</T[DHEU]>", tr, re.S | re.I)]
        if any(cells):
            rows.append(" | ".join(cells))
    if len(rows) > max_rows:
        rows = rows[:max_rows] + [f"... (표 {len(rows)}행 중 {max_rows}행만 표시)"]
    return "\n".join(rows)


def _strip_tags(fragment: str) -> str:
    text = re.sub(r"<[^>]+>", " ", fragment)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _to_plain(fragment: str, table_max_rows: int) -> str:
    """DART XML 조각을 사람이 읽는 평문으로 만든다. 표는 형태를 살린다."""
    out, pos = [], 0
    # `<TABLE-GROUP>`도 `<TABLE\b`에 걸린다. 공백이나 `>`가 바로 뒤에 오는 것만 표다.
    for m in re.finditer(r"<TABLE(?=[\s>])[^>]*>.*?</TABLE>", fragment, re.S | re.I):
        out.append(_strip_tags(fragment[pos:m.start()]))
        out.append("\n" + _render_table(m.group(0), table_max_rows) + "\n")
        pos = m.end()
    out.append(_strip_tags(fragment[pos:]))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(p for p in out if p.strip())).strip()


def _parse_document(rcept_no: str) -> dict:
    """ZIP을 메모리에서 열어 파일 목록과 목차를 만든다. 본문은 캐시에만 둔다.

    Cloud Run은 인스턴스가 여러 개이고 stateless_http라 다음 호출이 다른
    인스턴스로 갈 수 있다. 캐시는 **적중하면 좋은 최적화**일 뿐이며, 어긋나면
    다시 내려받으므로 정합성은 캐시에 기대지 않는다.
    """
    now = time.time()
    hit = _doc_cache.get(rcept_no)
    if hit and now - hit[0] < DOC_CACHE_TTL:
        _doc_cache.move_to_end(rcept_no)
        return hit[1]

    cached = _cache_read(rcept_no)
    if cached is not None:
        _remember(rcept_no, now, cached)
        return cached

    blob = _fetch_document_zip(rcept_no)
    files, sections = [], []
    doc_name = company = ""

    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        for info in sorted(zf.infolist(), key=lambda i: -i.file_size):
            entry = {"filename": info.filename, "bytes": info.file_size}
            if not info.filename.lower().endswith((".xml", ".html", ".htm", ".txt")):
                # PDF·HWP 첨부는 이 도구로 읽지 않는다. 있다는 사실만 알린다.
                entry["readable"] = False
                files.append(entry)
                continue

            text = zf.read(info.filename).decode("utf-8", "replace")
            entry["readable"] = True
            entry["chars"] = len(text)
            doc_name = doc_name or _strip_tags(
                (re.search(r"<DOCUMENT-NAME\b[^>]*>(.*?)</DOCUMENT-NAME>", text, re.S) or ["", ""])[1])
            company = company or _strip_tags(
                (re.search(r"<COMPANY-NAME\b[^>]*>(.*?)</COMPANY-NAME>", text, re.S) or ["", ""])[1])
            files.append(entry)

            # 제목 위치와 그때의 SECTION 중첩 깊이를 함께 수집한다.
            depth, marks = 0, []
            for m in re.finditer(
                    r"<(/?)SECTION-(\d)\b[^>]*>|<TITLE\b[^>]*>(.*?)</TITLE>", text, re.S):
                if m.group(3) is not None:
                    marks.append((m.start(), m.end(), _strip_tags(m.group(3)), max(depth, 1)))
                else:
                    depth += -1 if m.group(1) else 1
            # 평문 변환을 여기서 끝낸다. XML 길이는 실제 분량과 1.3~22.5배까지
            # 벌어져(표가 많을수록 심하다) 크기를 보고 읽을지 정하는 판단을
            # 정반대로 만든다. 155개 전부 변환해도 0.7초이고, 변환 결과만 들고
            # 있으면 원본 XML(6.9M자)을 버릴 수 있어 메모리도 줄어든다.
            for i, (_start, end, title, level) in enumerate(marks):
                nxt = marks[i + 1][0] if i + 1 < len(marks) else len(text)
                body = _to_plain(text[end:nxt], TABLE_ROWS_DEFAULT)
                sections.append({
                    "no": len(sections) + 1,
                    "file": info.filename,
                    "level": level,
                    "title": title,
                    "chars": len(body),
                    "xml_chars": nxt - end,
                    "_text": body,
                })

    parsed = {
        "rcept_no": rcept_no,
        "document_name": doc_name,
        "company_name": company,
        "files": files,
        "sections": sections,
        "text_chars": sum(x["chars"] for x in sections),
    }
    _cache_write(rcept_no, parsed)
    _remember(rcept_no, now, parsed)
    return parsed


def _remember(rcept_no: str, now: float, parsed: dict) -> None:
    _doc_cache[rcept_no] = (now, parsed)
    while len(_doc_cache) > DOC_CACHE_MAX:
        _doc_cache.popitem(last=False)


@mcp.tool(annotations=READ_ONLY)
def get_disclosure_outline(rcept_no: str, focus: str = "", limit: int = 200) -> dict:
    """공시 원문의 목차를 읽는다. 본문을 읽기 전에 **반드시 먼저 호출한다.**

    사업보고서 본문은 500만 자를 넘는다. 통째로는 읽을 수 없으므로 이 도구로
    목차를 받아 필요한 항목의 `no`를 고르고, get_disclosure_section으로 그
    항목만 읽는다.

    각 항목의 `chars`가 곧 그 항목을 요청했을 때 받게 될 분량이다. 상위 제목은
    하위 항목을 포함하지 않는다.

    Args:
        rcept_no: 접수번호 14자리. call_dart_api("list", {"corp_code": ...})로 얻는다.
        focus: 항목을 좁히는 힌트. "financial"(재무·주석), "governance"(임원·주주·
            지배구조), "business"(사업·영업·생산) 중 하나. 비우면 전부.
        limit: 반환할 항목 수 상한.

    Returns:
        document_name, company_name, files(파일별 크기·읽기 가능 여부),
        sections(no·level·title·chars), section_count.
    """
    doc = _parse_document(rcept_no)
    rows = doc["sections"]
    if focus:
        keys = FOCUS_KEYWORDS.get(focus.strip().lower())
        if keys is None:
            raise DartError(
                f"focus는 {', '.join(FOCUS_KEYWORDS)} 중 하나입니다(받은 값: {focus!r}).")
        rows = [s for s in rows if any(k in s["title"] for k in keys)]

    return {
        "rcept_no": rcept_no,
        "document_name": doc["document_name"],
        "company_name": doc["company_name"],
        "files": doc["files"],
        "text_chars": doc["text_chars"],
        "section_count": len(rows),
        "sections": [{k: s[k] for k in ("no", "level", "title", "chars", "file")}
                     for s in rows[:limit]],
        "next_step": "필요한 항목의 no를 골라 "
                     "get_disclosure_section(rcept_no, section_no=<no>)로 읽는다.",
    }


@mcp.tool(annotations=READ_ONLY)
def get_disclosure_section(
    rcept_no: str,
    section_no: int = 0,
    title: str = "",
    max_chars: int = SECTION_CHARS_DEFAULT,
) -> dict:
    """공시 원문에서 **한 항목만** 평문으로 읽는다.

    get_disclosure_outline으로 목차를 먼저 본 뒤 호출한다. 문서 전체를 반환하는
    방법은 없다 — 500만 자짜리 문서가 있기 때문이다.

    Args:
        rcept_no: 접수번호 14자리.
        section_no: 목차의 `no`. 이 값을 쓰는 것이 가장 정확하다.
        title: no를 모를 때 제목의 일부로 찾는다(부분 일치). 여러 개가 걸리면
            후보를 돌려주고 읽지 않는다.
        max_chars: 반환 상한. 넘으면 잘라서 주고 truncated로 알린다.

    Returns:
        title, chars(원본 분량), returned_chars, truncated, text.
        truncated가 True면 이어 읽을 방법을 next_step으로 함께 준다.
    """
    doc = _parse_document(rcept_no)
    rows = doc["sections"]
    if not rows:
        raise DartError(
            f"{rcept_no}에서 읽을 수 있는 항목을 찾지 못했습니다. "
            "get_disclosure_outline으로 파일 목록을 먼저 확인하세요.")

    if section_no:
        picked = [s for s in rows if s["no"] == section_no]
        if not picked:
            raise DartError(
                f"section_no={section_no}는 이 문서에 없습니다(1~{len(rows)}). "
                "get_disclosure_outline으로 목차를 다시 확인하세요.")
    elif title:
        picked = [s for s in rows if title.strip() in s["title"]]
        if not picked:
            raise DartError(
                f"제목에 {title!r}를 포함하는 항목이 없습니다. "
                "get_disclosure_outline으로 실제 제목을 확인하세요.")
        if len(picked) > 1:
            return {
                "rcept_no": rcept_no,
                "matched": [{k: s[k] for k in ("no", "level", "title", "chars")}
                            for s in picked[:20]],
                "next_step": f"{len(picked)}개가 일치합니다. section_no로 하나를 지정하세요.",
            }
    else:
        raise DartError("section_no 또는 title 중 하나는 지정해야 합니다.")

    sec = picked[0]
    plain = sec["_text"]

    cap = min(max(max_chars, 500), SECTION_CHARS_CAP)
    truncated = len(plain) > cap
    out = {
        "rcept_no": rcept_no,
        "no": sec["no"],
        "title": sec["title"],
        "chars": len(plain),
        "returned_chars": min(len(plain), cap),
        "truncated": truncated,
        "text": plain[:cap],
    }
    if truncated:
        out["next_step"] = (
            f"{len(plain):,}자 중 {cap:,}자만 반환했습니다. 하위 항목이 있으면 "
            "목차에서 더 좁은 no를 고르고, 없으면 max_chars를 올려 다시 부릅니다"
            f"(상한 {SECTION_CHARS_CAP:,}자).")
    return out


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
