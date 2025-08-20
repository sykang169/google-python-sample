"""dart_analytics: An agent for analyzing corporate data using the DART API."""

# Google ADK 의존성이 없을 때를 위한 조건부 import
try:
    from . import agent
    from .agent import root_agent
except ImportError as e:
    if "google" in str(e).lower():
        # Google ADK가 설치되지 않은 경우 agent 모듈은 로드하지 않음
        agent = None
        root_agent = None
    else:
        raise e