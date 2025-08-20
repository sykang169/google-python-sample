"""
Stock Analytics Agent
금융위원회 주식시세정보 API를 활용하는 ADK 에이전트 (OpenAPIToolset + SSL 호환성)
"""
import os
from google.adk.tools.openapi_tool.openapi_spec_parser.openapi_toolset import OpenAPIToolset
from google.adk.auth.auth_credential import AuthCredential, AuthCredentialTypes
from google.adk.tools.function_tool import FunctionTool
from google.adk.agents import LlmAgent
from .config import config
from . import prompt
from .ssl_api_tool import (
    get_stock_price_info_ssl,
    get_securities_price_info_ssl
)

# OpenAPI 스펙 파일 경로
openapi_spec_path = os.path.join(os.path.dirname(__file__), 'stock_openapi.yml')

# OpenAPI 스펙 로드
with open(openapi_spec_path, 'r', encoding='utf-8') as f:
    openapi_spec_yaml = f.read()

# API 키 인증 정보 생성
auth_credential = AuthCredential(
    auth_type=AuthCredentialTypes.API_KEY,
    api_key=config.STOCK_API_KEY
)

# OpenAPIToolset 생성 (참고용)
try:
    toolset = OpenAPIToolset(
        spec_str=openapi_spec_yaml,
        spec_str_type="yaml", 
        auth_credential=auth_credential
    )
    print(f"✅ OpenAPIToolset 초기화 성공 (참고용)")
except Exception as e:
    print(f"⚠️ OpenAPIToolset 초기화 실패 (SSL 대안 사용): {e}")
    toolset = None

# SSL 호환 함수 도구들 생성
ssl_tools = [
    FunctionTool(func=get_stock_price_info_ssl),
    FunctionTool(func=get_securities_price_info_ssl)
]

# Tools 리스트 구성 - SSL 호환 도구를 우선 사용
tools_list = []
tools_list.extend(ssl_tools)
if toolset is not None:
    tools_list.append(toolset)  # OpenAPIToolset 백업용으로 추가


stock_analytics = LlmAgent(
    model=config.worker_model,
    name="stock_analytics", 
    description="금융위원회 주식시세정보 OpenAPI를 활용한 주식/증권 시세 조회 및 분석 에이전트",
    instruction=prompt.STOCK_ANALYTICS_PROMPT,
    tools=tools_list,
    output_key="stock_result",
)

root_agent = stock_analytics