"""배포된 MCP 서버 9종과 스킬 9종을 붙인 검증용 에이전트.

Gemini Enterprise의 재현이 아니다. 모델도 스킬 선택 방식도 다르다. 목적은 하나다
— **도구 설명과 데이터 함정이 실제로 작동하는지** 사람 없이 확인하는 것이다.
GE는 API로 MCP 액션을 부를 수 없어서(Assistant.enabled_tools 미구현) 검증할
때마다 사람이 답변을 옮겨 붙여야 했다. 여기서는 시나리오를 바로 돌린다.

무엇이 옮겨지고 무엇이 안 옮겨지는지 구분해서 읽어야 한다.

  옮겨진다    도구 설명, 카탈로그, 서버가 붙이는 warning, 스킬 본문의 규칙
  안 옮겨진다 GE의 모델·라우팅·스킬 자동선택, 답변 문체
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess

from google.adk.agents import Agent
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams

from .auth import auth_header
from .skills import list_skills, read_skill

REPO = pathlib.Path(__file__).resolve().parents[2]
MODEL = os.environ.get("HARNESS_MODEL", "gemini-2.5-pro")

os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "us-central1")


def _service_urls() -> dict[str, str]:
    """terraform이 1순위, 막히면 Cloud Run 조회.

    tfstate는 ADC를 쓰므로 만료되면 못 읽는다. 검증이 거기 묶이면 안 된다.
    """
    out = subprocess.run(["terraform", "output", "-json", "mcp_urls"],
                         cwd=REPO / "mcp" / "terraform",
                         capture_output=True, text=True)
    if out.returncode == 0:
        try:
            return json.loads(out.stdout)
        except json.JSONDecodeError:
            pass
    project = os.environ.get("GOOGLE_CLOUD_PROJECT") or subprocess.run(
        ["gcloud", "config", "get-value", "project"],
        capture_output=True, text=True).stdout.strip()
    listing = subprocess.run(
        ["gcloud", "run", "services", "list", f"--project={project}",
         "--format=value(metadata.name,status.url)"],
        capture_output=True, text=True).stdout
    known = {p.name.replace("-server", "") for p in (REPO / "mcp").glob("*-mcp-server")}
    urls = {}
    for line in listing.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] in known:
            urls[parts[0]] = parts[1].rstrip("/") + "/mcp"
    if not urls:
        raise RuntimeError("MCP 서버 URL을 찾지 못했습니다. terraform 또는 gcloud를 확인하세요.")
    return urls


# fsc 6종이 공통으로 갖는 도구. GE는 서버마다 스토어가 나뉘어 괜찮지만
# ADK는 한 목록으로 합치므로 이름이 충돌한다.
SHARED = ("search_apis", "call_api")


def _toolsets() -> list[McpToolset]:
    """도메인 도구는 **실제 이름 그대로** 노출한다.

    이름이 검증 대상이다 — 도구 이름과 내용이 어긋나 오답이 나온 적이 있어서,
    여기서 이름을 바꾸면 그 부류를 못 잡는다. 그래서 서버마다 둘로 쪼갠다.

      도메인 도구   접두사 없음 → GE와 같은 이름
      공통 도구 둘  접두사 붙임 → 충돌만 피한다
    """
    sets = []
    for name, url in sorted(_service_urls().items()):
        params = lambda: StreamableHTTPConnectionParams(
            url=url, timeout=30.0, sse_read_timeout=600.0)
        sets.append(McpToolset(
            connection_params=params(),
            header_provider=auth_header,
            tool_filter=lambda t, ctx=None: t.name not in SHARED,
        ))
        short = name.replace("-mcp", "").replace("-", "_")
        sets.append(McpToolset(
            connection_params=params(),
            header_provider=auth_header,
            tool_filter=list(SHARED),
            tool_name_prefix=short,
        ))
    return sets


def _instruction() -> str:
    """운영에 쓰는 시스템 지시를 그대로 쓴다. 여기서 따로 쓰면 검증이 무의미하다."""
    text = (REPO / "mcp" / "SYSTEM_PROMPT.md").read_text(encoding="utf-8")
    # 문서 앞머리(제목·설명)와 뒤쪽 운영 안내를 걷어내고 지시 본문만 남긴다.
    start = text.find("당신은")
    end = text.find("\n## 줄여 쓸 때")
    body = text[start if start != -1 else 0: end if end != -1 else len(text)]
    return body.strip() + """

## 이 환경에서의 추가 지시

답하기 전에 **list_skills를 먼저 부른다.** 질문에 해당하는 스킬이 있으면
read_skill로 전문을 읽고 그 규칙을 지킨다. 스킬에는 조용히 틀리는 함정이
정리되어 있어서, 읽지 않으면 오류 없이 잘못된 답을 만들게 된다.

도구 응답에 `warning`이 있으면 **무시하지 말고 답변에 반영한다.**
"""


root_agent = Agent(
    name="mcp_harness",
    model=MODEL,
    description="배포된 MCP 서버와 스킬을 붙여 시나리오를 검증하는 에이전트",
    instruction=_instruction(),
    tools=[list_skills, read_skill, *_toolsets()],
)
