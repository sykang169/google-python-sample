import datetime
from .config import config

from google.adk.agents import BaseAgent, LlmAgent
from google.adk.tools.openapi_tool.openapi_spec_parser.openapi_toolset import OpenAPIToolset
from google.adk.tools.function_tool import FunctionTool
from google.adk.auth.auth_credential import AuthCredential, AuthCredentialTypes
from . import prompt
from . import corpcode_manager

# Load ECOS OpenAPI spec (use final corrected version with proper parameter order)
with open('./ecos_analytics/ecos_final_openapi.yml', 'r') as f:
    openapi_spec_yaml = f.read()
print("✓ Using final corrected ECOS OpenAPI specification")

# ECOS API uses path-based authentication, so we don't need separate auth_credential
# The API key is automatically injected as default value in path parameters
toolset = OpenAPIToolset(
    spec_str=openapi_spec_yaml, 
    spec_str_type="yaml"
)

# CORPCODE 관리 함수들을 FunctionTool로 등록

ecos_analytics = LlmAgent(
    model=config.worker_model,
    name="ecos_analytics",
    description="자연어 질문을 ECOS API 호출로 변환하여 경제통계 데이터를 조회하고 요약하는 AI 에이전트를 정의합니다.",
    instruction=prompt.ECOS_ANALYTICS_PROMPT,
    tools=[
        toolset,
        FunctionTool(func=corpcode_manager.get_corp_code),
        FunctionTool(func=corpcode_manager.search_corporations),
        FunctionTool(func=corpcode_manager.get_corp_info),
        FunctionTool(func=corpcode_manager.get_listed_companies)
    ],
    output_key="ecos_result",
)

root_agent = ecos_analytics