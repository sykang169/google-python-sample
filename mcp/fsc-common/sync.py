#!/usr/bin/env python3
"""5개 FSC MCP 서버 디렉터리를 생성/갱신한다.

fsc_core.py와 catalog.json은 여기가 원본이고, 각 서버 디렉터리로 복사된다.
빌드 컨텍스트가 서버 디렉터리 하나이므로(build.sh의 gcloud builds submit)
공유 모듈을 심볼릭 링크로 둘 수 없어 복사한다.

  python3 sync.py          # 5개 전부 생성
  python3 sync.py market   # 하나만
"""
from __future__ import annotations

import json
import pathlib
import sys

import servers

HERE = pathlib.Path(__file__).parent
MCP = HERE.parent
CATALOG = json.loads((HERE / "catalog.json").read_text(encoding="utf-8"))

# 서버 <-> 스킬 대응. README에서 서로를 가리키게 한다.
SKILL_OF = {
    "market": "krx-stock-quote-analysis",
    "ficc": "kr-bond-ficc-analysis",
    "research": "kr-corporate-research",
    "equity-ops": "kr-equity-operations",
    "industry": "kr-securities-industry-benchmark",
}

REQUIREMENTS = "mcp==1.27.0\nhttpx==0.28.1\nuvicorn==0.35.0\n"

DOCKERFILE = """FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY fsc_core.py catalog.json server.py ./

# Cloud Run이 PORT를 주입한다. 로컬 실행 시의 기본값.
ENV PORT=8080
EXPOSE 8080

CMD ["python", "server.py"]
"""

HEADER = '''"""FSC {title} MCP Server — 금융위원회 공공데이터 {title} 계열.

{desc}

설계
----
이 데스크가 다루는 API는 {n_svc}종 / 오퍼레이션 {n_op}개다. 전부 도구로 펼치면
tools/list가 커져 다른 MCP 서버와 함께 붙일 때 컨텍스트를 잡아먹으므로,
자주 쓰는 경로만 이름 있는 도구로 내고 나머지는 search_apis + call_api로 연다.
(dart-mcp-server와 같은 점진적 공개 방식이다.)

search_apis는 오퍼레이션의 **응답 필드 목록**을 함께 준다. 금융위 API는 응답
필드명이 곧 필터 파라미터로 쓰이므로, 그 목록이 사실상 파라미터 명세다.
필드는 실제 호출로 수집한 것이라 문서와 어긋날 일이 없다.

주의: {hint}

Gemini Enterprise 데이터 스토어가 소비할 수 있도록 StreamableHTTP를 쓴다.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

import fsc_core
from fsc_core import READ_ONLY, FscError

CATALOG = fsc_core.load_catalog({server!r})

# 서버 단위 전제. MCP initialize 응답으로 나가며, 도구 목록과 달리 매 호출
# 컨텍스트를 차지하지 않는다. 클라이언트가 이걸 모델에 넘기지 않을 수도 있어
# search_apis 설명에도 같은 문장을 넣어 둔다.
INSTRUCTIONS = """{title} — {desc}

{hint}"""

mcp = FastMCP({mcp_name!r}, instructions=INSTRUCTIONS)
'''

COMMON_TOOLS = '''

@mcp.tool(annotations=READ_ONLY)
def search_apis(query: str = "", limit: int = 8) -> dict:
    """이 서버가 다루는 API와 오퍼레이션을 찾는다. call_api 이전 단계다.

    이 서버의 전제: __HINT__

    이름 있는 도구로 나와 있지 않은 데이터가 필요할 때 여기서 먼저 찾는다.
    반환되는 fields가 그 오퍼레이션의 응답 필드이자 **필터 파라미터 후보**다
    (예: basDt로 기준일, itmsNm으로 종목명, likeItmsNm으로 부분 일치).

    Args:
        query: 검색어. 한글 API명, 영문 오퍼레이션명, 응답 필드명에 부분 일치시킨다
            (예: "채권", "배당", "basDt", "ETF"). 비우면 전체 목록을 반환한다.
        limit: 최대 반환 건수.

    Returns:
        rows: [{service, operation, api_name, purpose, fields, approx_total_rows}]
    """
    return fsc_core.search(CATALOG, query, limit)


@mcp.tool(annotations=READ_ONLY)
def call_api(
    service: str,
    operation: str,
    params: dict | None = None,
    rows: int = 20,
    page: int = 1,
) -> dict:
    """search_apis로 찾은 오퍼레이션을 실행한다.

    인증키는 서버가 넣으므로 params에 포함하지 않는다.
    params의 키는 search_apis가 알려준 fields 중에서 고른다.

    자주 쓰는 필터:
        basDt        기준일자 YYYYMMDD (하루)
        beginBasDt / endBasDt   기간 조회
        itmsNm       종목명 정확 일치 / likeItmsNm  부분 일치
        isinCd       ISIN 12자리 (가장 정확)
        crno         법인등록번호 (기업 정보 계열)

    Args:
        service: 서비스명 (예: "GetStockSecuritiesInfoService").
        operation: 오퍼레이션명 (예: "getStockPriceInfo").
        params: 필터 딕셔너리. 없으면 최신 데이터부터 반환된다.
        rows: 페이지당 건수 (최대 권장 100).
        page: 페이지 번호.

    Returns:
        total_count, page_no, num_of_rows, rows
    """
    return fsc_core.call(CATALOG, service, operation, params, rows, page)
'''

TOOL = '''

@mcp.tool(annotations=READ_ONLY)
def {name}(params: dict | None = None, rows: int = 20, page: int = 1) -> dict:
    """{doc}

    필터로 쓸 수 있는 필드(응답 필드와 같다):
        {fields}

    Args:
        params: 필터 딕셔너리 (예: {{"basDt": "20260831"}}). 비우면 최신부터 반환한다.
        rows: 페이지당 건수 (최대 권장 100).
        page: 페이지 번호.
    """
    return fsc_core.call(CATALOG, {svc!r}, {op!r}, params, rows, page)
'''

FOOTER = '''

if __name__ == "__main__":
    fsc_core.run(mcp)
'''

README = """# fsc-{server}-mcp-server

{desc}

금융위원회가 공공데이터포털에 개방한 API 중 **{title}** 계열
{n_svc}종(오퍼레이션 {n_op}개)을 MCP 도구로 노출한다.

- 짝이 되는 스킬: [`{skill}`](../../skills/{skill}/SKILL.md)
- Cloud Run 서비스명: `fsc-{server}-mcp`

## 이런 질문에 답한다

| 질문 | 어떻게 |
| --- | --- |
{prompt_rows}

## 도구

| 도구 | 내용 |
| --- | --- |
| `search_apis` | 이 서버가 다루는 오퍼레이션 검색. 응답 필드(=필터 파라미터)까지 반환 |
| `call_api` | 찾은 오퍼레이션 실행 |
{tool_rows}

이름 있는 도구는 자주 쓰는 경로만 감싼 것이다. 나머지는 `search_apis` →
`call_api` 순으로 접근한다. 전부 도구로 펼치면 `tools/list`가 커져 다른 MCP
서버와 함께 붙일 때 컨텍스트를 잡아먹기 때문이다.

## 필요한 data.go.kr 활용신청

인증키는 공공데이터포털 계정당 **하나**(`STOCK_API_KEY`)이고 이 저장소의 fsc-*
서버 5종이 공유한다. 다만 **승인은 API마다 따로** 받아야 하며, 미승인 API는
같은 키로도 `resultCode 30`이 난다.

이 서버를 쓰려면 아래 {n_svc}건을 각각 활용신청해야 한다.

| 서비스 | 이름 | 활용신청 |
| --- | --- | --- |
{api_rows}

승인 여부는 실제 호출로만 알 수 있다. 저장소 루트에서:

```bash
python3 mcp/fsc-common/check_access.py {server}
```

## 주의

{hint}

- **전부 비실시간이다.** 기준일 다음 영업일 13시 이후에 갱신된다.
- 오류가 HTTP 200과 함께 온다. `resultCode 03`은 데이터 없음(오류 아님),
  `30`은 활용신청 미승인, `12`는 경로나 오퍼레이션명 오류다.
  **`12`를 미승인으로 읽지 않는다.**
- **`apis.data.go.kr`은 소스 IP 단위로 접속을 일시 차단한다.** 짧은 시간에 호출을
  몰아치면 그 IP의 TCP 연결을 수 분~수십 분간 받지 않는다. 서버가 응답 캐시(6시간),
  호출 간 최소 간격(0.5초), 회로 차단(연속 3회 실패 → 300초 정지)으로 대응하지만
  완전히 막지는 못한다. `ConnectTimeout`이 반복되면 코드나 키가 아니라 이쪽이다
  (`../fsc-common/README.md`의 "호출량 억제" 참고).
- 5개 fsc 서버가 같은 상류를 쓴다. **한 서버가 몰아치면 나머지도 함께 막힌다.**

## 실행

```bash
export STOCK_API_KEY="..."      # 디코딩 형태 그대로. 퍼센트 인코딩하지 말 것
pip install -r requirements.txt
python server.py                # http://localhost:8080/mcp
```

## 배포

```bash
cd ../terraform && ./build.sh fsc-{server}-mcp && terraform apply
```

## 생성 파일

`server.py`, `fsc_core.py`, `catalog.json`, 이 README는 `mcp/fsc-common/`에서
생성된다. 여기서 직접 고치지 말고 원본을 고친 뒤 `python3 sync.py`를 다시 실행한다.
"""


def build(server: str) -> pathlib.Path:
    spec = servers.SERVERS[server]
    subset = {k: v for k, v in CATALOG.items() if v["server"] == server}
    n_svc = len(subset)
    n_op = sum(len(v["operations"]) for v in subset.values())

    out = MCP / f"fsc-{server}-mcp-server"
    out.mkdir(exist_ok=True)

    parts = [HEADER.format(title=spec["title"], desc=spec["desc"], hint=spec["hint"],
                           n_svc=n_svc, n_op=n_op, server=server,
                           mcp_name=f"fsc-{server}-mcp")]
    # COMMON_TOOLS는 docstring에 중괄호가 많아 format을 쓸 수 없다. 자리표시자만 바꾼다.
    parts.append(COMMON_TOOLS.replace("__HINT__", spec["hint"]))
    for tool in spec["tools"]:
        fields = subset[tool["svc"]]["operations"][tool["op"]]["fields"]
        parts.append(TOOL.format(
            name=tool["name"], doc=tool["doc"], svc=tool["svc"], op=tool["op"],
            fields=", ".join(fields) or "(없음)"))
    parts.append(FOOTER)
    (out / "server.py").write_text("".join(parts), encoding="utf-8")

    (out / "fsc_core.py").write_text((HERE / "fsc_core.py").read_text(encoding="utf-8"),
                                     encoding="utf-8")
    (out / "catalog.json").write_text(
        json.dumps(subset, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (out / "requirements.txt").write_text(REQUIREMENTS, encoding="utf-8")
    (out / "Dockerfile").write_text(DOCKERFILE, encoding="utf-8")
    (out / ".dockerignore").write_text("__pycache__/\n*.pyc\n.env\n", encoding="utf-8")

    tool_rows = "\n".join(
        f'| `{t["name"]}` | {t["doc"].splitlines()[0]} |' for t in spec["tools"])
    api_rows = "\n".join(
        f'| `{s}` | {v["name"]} | '
        f'[신청](https://www.data.go.kr/data/{v["public_data_pk"]}/openapi.do) |'
        for s, v in sorted(subset.items(), key=lambda x: x[1]["name"]))
    prompt_rows = "\n".join(f'| "{q}" | {how} |' for q, how in spec["prompts"])
    (out / "README.md").write_text(README.format(
        server=server, title=spec["title"], desc=spec["desc"], hint=spec["hint"],
        skill=SKILL_OF[server], n_svc=n_svc, n_op=n_op,
        tool_rows=tool_rows, api_rows=api_rows, prompt_rows=prompt_rows), encoding="utf-8")
    return out


def main(argv: list[str]) -> int:
    targets = argv[1:] or list(servers.SERVERS)
    for server in targets:
        if server not in servers.SERVERS:
            print(f"알 수 없는 서버: {server}", file=sys.stderr)
            return 1
        out = build(server)
        n = len(list(out.iterdir()))
        print(f"{out.relative_to(MCP.parent)}  ({n}개 파일)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
