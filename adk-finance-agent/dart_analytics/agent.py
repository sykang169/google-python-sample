"""
DART Analytics 에이전트 메인 모듈

Google ADK를 사용하여 DART API와 연동하는 에이전트를 생성합니다.
"""

from google.adk.agents import BaseAgent, LlmAgent
from google.adk.tools.openapi_tool.openapi_spec_parser.openapi_toolset import OpenAPIToolset
from google.adk.tools.function_tool import FunctionTool
from google.adk.auth.auth_credential import AuthCredential, AuthCredentialTypes

from .config import config
from .prompt import DART_ANALYTICS_PROMPT
from .sub_functions.file_handlers import download_and_extract_file, download_corp_codes
from .sub_functions.xbrl_processor import download_xbrl_financial_statement, process_xbrl_files
from .sub_functions.document_analyzer import (
    check_extracted_files_exist,
    read_extracted_file_content,
    analyze_extracted_dart_document,
    parse_xml_file_to_readable
)
from .sub_functions.utils import get_corp_code, get_document_basic_info, ensure_document_available, process_user_request, refresh_corpcode_data, search_corporations, get_corp_info, get_corpcode_file_info

# Load OpenAPI spec
with open('./dart_analytics/dart_openapi_full_specification.yml', 'r', encoding='utf-8') as f:
    openapi_spec_yaml = f.read()

# Inject DART API key as default value in the OpenAPI spec (one-time only)
api_key_marker = f'default: "{config.DART_API_KEY}"'
if api_key_marker not in openapi_spec_yaml:
    openapi_spec_yaml = openapi_spec_yaml.replace(
        "        type: string\\n        minLength: 40\\n        maxLength: 40",
        f"        type: string\\n        minLength: 40\\n        maxLength: 40\\n        default: \\\"{config.DART_API_KEY}\\\"",
        1  # 첫 번째 매치만 치환
    )

# Create API key auth credential
auth_credential = AuthCredential(
    auth_type=AuthCredentialTypes.API_KEY,
    api_key=config.DART_API_KEY
)

# Create toolset with proper authentication
try:
    toolset = OpenAPIToolset(
        spec_str=openapi_spec_yaml, 
        spec_str_type="yaml",
        auth_credential=auth_credential
    )
except Exception as e:
    print(f"OpenAPIToolset 초기화 오류: {e}")
    # 오류 발생 시 빈 도구 세트로 대체 (기본 기능은 유지)
    toolset = None


def process_dart_document(rcept_no: str, user_request: str = "", download_folder: str = "./downloads") -> str:
    """
    DART 문서 처리 메인 함수
    1. 압축해제된 폴더 확인
    2. 없으면 다운로드 + 압축해제
    3. 사용자 요청에 따라 적절한 분석/파싱 수행
    
    Args:
        rcept_no: 접수번호 (14자리)
        user_request: 사용자 요청 내용
        download_folder: 다운로드 폴더 경로
    
    Returns:
        처리 결과
    """
    try:
        # 1단계: 문서 존재 확인 및 다운로드
        setup_result = ensure_document_available(rcept_no, download_folder)
        if setup_result.startswith("❌"):
            return setup_result
        
        # 2단계: 사용자 요청 분석 및 처리
        return process_user_request(rcept_no, user_request, download_folder, setup_result)
        
    except Exception as e:
        return f"❌ 문서 처리 중 오류 발생: {str(e)}"


def get_document_files(rcept_no: str, download_folder: str = "./downloads") -> str:
    """압축해제된 문서의 파일 목록 조회"""
    try:
        return check_extracted_files_exist(rcept_no, download_folder)
    except Exception as e:
        return f"❌ 파일 목록 조회 중 오류 발생: {str(e)}"


def read_document_file(rcept_no: str, filename: str, download_folder: str = "./downloads") -> str:
    """압축해제된 문서의 특정 파일 읽기"""
    try:
        return read_extracted_file_content(rcept_no, filename, download_folder)
    except Exception as e:
        return f"❌ 파일 읽기 중 오류 발생: {str(e)}"


def parse_document_xml(rcept_no: str, filename: str, show_full_content: bool = False, download_folder: str = "./downloads") -> str:
    """압축해제된 문서의 XML 파일 파싱"""
    try:
        return parse_xml_file_to_readable(rcept_no, filename, download_folder, show_full_content)
    except Exception as e:
        return f"❌ XML 파싱 중 오류 발생: {str(e)}"


# Tools 리스트 구성 (toolset이 None일 경우 제외)
tools_list = []
if toolset is not None:
    tools_list.append(toolset)

tools_list.extend([
    FunctionTool(func=get_corp_code),
    FunctionTool(func=refresh_corpcode_data),
    FunctionTool(func=search_corporations),
    FunctionTool(func=get_corp_info),
    FunctionTool(func=get_corpcode_file_info),
    FunctionTool(func=process_dart_document),
    FunctionTool(func=get_document_files),
    FunctionTool(func=read_document_file),
    FunctionTool(func=parse_document_xml),
    FunctionTool(func=get_document_basic_info),
    FunctionTool(func=download_corp_codes),
    FunctionTool(func=download_xbrl_financial_statement),
    FunctionTool(func=process_xbrl_files),
    FunctionTool(func=download_and_extract_file)
])

dart_analytics = LlmAgent(
    model=config.worker_model,
    name="dart_analytics",
    description="자연어 질문을 DART API 호출로 변환하여 기업 분석 데이터를 조회하고 요약하는 AI 에이전트. ZIP 파일 형태의 공시서류도 자동으로 다운로드, 압축해제하고 분석할 수 있습니다.",
    instruction=DART_ANALYTICS_PROMPT,
    tools=tools_list,
    output_key="dart_result",
)

root_agent = dart_analytics