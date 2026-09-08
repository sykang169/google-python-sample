"""Cloud Run에 올린 MCP 서버를 부르기 위한 신원 토큰.

서버는 IAM 인증이 걸려 있어 ID 토큰이 필요하다. 토큰은 한 시간이면 만료되므로
호출할 때마다 캐시를 확인하고, 만료가 가까우면 다시 받는다. 세션이 길어지면
중간에 401이 나는 것을 막기 위해서다.
"""
from __future__ import annotations

import subprocess
import threading
import time

# 만료 5분 전에 갈아 끼운다. gcloud가 주는 토큰의 수명은 대략 한 시간이다.
_TTL_SEC = 55 * 60

_lock = threading.Lock()
_token: str | None = None
_issued_at: float = 0.0


def identity_token() -> str:
    global _token, _issued_at
    with _lock:
        if _token is None or time.time() - _issued_at > _TTL_SEC:
            out = subprocess.run(
                ["gcloud", "auth", "print-identity-token"],
                capture_output=True, text=True)
            if out.returncode != 0:
                raise RuntimeError(
                    "신원 토큰을 받지 못했습니다. gcloud 로그인을 확인하세요: "
                    + out.stderr.strip()[:200])
            _token = out.stdout.strip()
            _issued_at = time.time()
        return _token


def auth_header(_ctx=None) -> dict[str, str]:
    """McpToolset의 header_provider. 호출 시점마다 유효한 토큰을 준다."""
    return {"Authorization": "Bearer " + identity_token()}
