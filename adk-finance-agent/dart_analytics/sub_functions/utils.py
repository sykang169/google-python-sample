"""
DART Analytics 유틸리티 모듈

공통 헬퍼 함수들과 유틸리티 기능을 제공합니다.
"""

import os
import requests
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from ..config import config
from .corpcode_storage import get_corp_code_quick, quick_search, initialize_storage, get_storage

# Initialize storage on module import
_storage_initialized = False


def _download_and_extract_corpcode():
    """Download and extract CORPCODE.xml from DART API or use existing zip file"""
    try:
        dart_analytics_dir = os.path.dirname(os.path.dirname(__file__))
        xml_path = os.path.join(dart_analytics_dir, 'CORPCODE.xml')
        zip_path = os.path.join(dart_analytics_dir, 'CORPCODE.zip')
        
        # First try to use existing zip file if available
        if os.path.exists(zip_path):
            print("📂 기존 CORPCODE.zip 파일을 발견했습니다. 압축 해제 중...")
            try:
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(dart_analytics_dir)
                
                if os.path.exists(xml_path):
                    print("✅ 기존 zip 파일에서 CORPCODE.xml 압축 해제 완료")
                    return True
            except Exception as e:
                print(f"⚠️ 기존 zip 파일 처리 실패: {e}")
        
        # If no existing zip or extraction failed, download from DART API
        print("📥 CORPCODE.xml이 없습니다. DART에서 다운로드 중...")
        
        # Check if API key is configured
        if not hasattr(config, 'DART_API_KEY') or not config.DART_API_KEY:
            print("❌ DART API 키가 설정되지 않았습니다. config.py에서 DART_API_KEY를 확인해주세요.")
            return False
        
        api_url = "https://opendart.fss.or.kr/api/corpCode.xml"
        params = {'crtfc_key': config.DART_API_KEY}
        
        response = requests.get(api_url, params=params, timeout=60, stream=True)
        
        if response.status_code != 200:
            print(f"❌ 다운로드 실패: HTTP {response.status_code}")
            return False
        
        # Save as ZIP file
        with open(zip_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        # Extract ZIP file
        print("📂 압축 해제 중...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            # Extract to dart_analytics directory
            zip_ref.extractall(dart_analytics_dir)
        
        print("✅ CORPCODE.xml 다운로드 및 압축 해제 완료")
        
        # Check if CORPCODE.xml exists after extraction
        return os.path.exists(xml_path)
        
    except Exception as e:
        print(f"❌ CORPCODE.xml 처리 중 오류: {str(e)}")
        return False


def _ensure_storage_initialized():
    """Ensure storage is initialized before use"""
    global _storage_initialized
    if not _storage_initialized:
        xml_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'CORPCODE.xml')
        
        # If CORPCODE.xml doesn't exist, try to download it
        if not os.path.exists(xml_path):
            if _download_and_extract_corpcode():
                # Check again after download
                if os.path.exists(xml_path):
                    initialize_storage(xml_path)
                    _storage_initialized = True
        else:
            initialize_storage(xml_path)
            _storage_initialized = True


def get_corp_code(corp_name: str) -> str:
    """
    회사명을 입력받아 고유번호(8자리)를 반환합니다.
    CORPCODE.xml이 없는 경우 자동으로 다운로드하여 처리합니다.
    새로운 고성능 저장소 시스템을 사용하여 빠른 조회를 제공합니다.
    """
    try:
        # Ensure storage is initialized (will download if needed)
        _ensure_storage_initialized()
        
        # Check if storage was successfully initialized
        if not _storage_initialized:
            # Try direct XML parsing as fallback
            xml_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'CORPCODE.xml')
            if os.path.exists(xml_path):
                tree = ET.parse(xml_path)
                root = tree.getroot()
                for corp in root.findall('list'):
                    corp_name_elem = corp.find('corp_name')
                    if corp_name_elem is not None and corp_name_elem.text == corp_name:
                        return corp.find('corp_code').text
                return f"{corp_name}에 해당하는 고유번호를 찾을 수 없습니다."
            else:
                return f"❌ CORPCODE.xml 파일을 다운로드할 수 없습니다. DART API 키를 확인해주세요."
        
        # Try new storage system first
        corp_code = get_corp_code_quick(corp_name)
        if corp_code:
            return corp_code
        
        # If not found, try partial search
        search_results = quick_search(corp_name)
        if search_results:
            # Return the first exact match or the first result
            for result in search_results:
                if result['corp_name'] == corp_name:
                    return result['corp_code']
            # No exact match, suggest alternatives
            suggestions = [f"{r['corp_name']} ({r['corp_code']})" for r in search_results[:3]]
            return f"{corp_name}에 해당하는 정확한 고유번호를 찾을 수 없습니다. 유사한 회사: {', '.join(suggestions)}"
        
        return f"{corp_name}에 해당하는 고유번호를 찾을 수 없습니다."
    except Exception as e:
        return f"오류가 발생했습니다: {e}"


def refresh_corpcode_data() -> str:
    """
    CORPCODE.xml 파일을 강제로 다시 다운로드하고 갱신합니다.
    
    Returns:
        처리 결과 메시지
    """
    global _storage_initialized
    try:
        dart_analytics_dir = os.path.dirname(os.path.dirname(__file__))
        xml_path = os.path.join(dart_analytics_dir, 'CORPCODE.xml')
        zip_path = os.path.join(dart_analytics_dir, 'CORPCODE.zip')
        
        # Delete existing files if exist
        if os.path.exists(xml_path):
            os.remove(xml_path)
            print("🗑️ 기존 CORPCODE.xml 파일 삭제")
        
        if os.path.exists(zip_path):
            os.remove(zip_path)
            print("🗑️ 기존 CORPCODE.zip 파일 삭제")
        
        # Reset initialization flag
        _storage_initialized = False
        
        # Download and extract new file
        if _download_and_extract_corpcode():
            # Reinitialize storage
            if os.path.exists(xml_path):
                initialize_storage(xml_path)
                _storage_initialized = True
                
                # Provide file statistics
                file_size = os.path.getsize(xml_path) / (1024*1024)
                import xml.etree.ElementTree as ET
                try:
                    tree = ET.parse(xml_path)
                    root = tree.getroot()
                    corp_count = len(root.findall('list'))
                    return f"✅ CORPCODE.xml 파일이 성공적으로 갱신되었습니다.\n📊 파일 크기: {file_size:.2f} MB\n🏢 총 기업 수: {corp_count:,}개"
                except:
                    return f"✅ CORPCODE.xml 파일이 성공적으로 갱신되었습니다.\n📊 파일 크기: {file_size:.2f} MB"
            else:
                return "❌ 파일 다운로드는 성공했으나 CORPCODE.xml을 찾을 수 없습니다."
        else:
            return "❌ CORPCODE.xml 파일 갱신에 실패했습니다."
    except Exception as e:
        return f"❌ 갱신 중 오류 발생: {str(e)}"


def get_corpcode_file_info() -> str:
    """
    CORPCODE.xml 파일의 정보를 조회합니다.
    
    Returns:
        파일 정보 메시지
    """
    try:
        dart_analytics_dir = os.path.dirname(os.path.dirname(__file__))
        xml_path = os.path.join(dart_analytics_dir, 'CORPCODE.xml')
        zip_path = os.path.join(dart_analytics_dir, 'CORPCODE.zip')
        
        result = []
        result.append("📋 CORPCODE 파일 정보")
        result.append("=" * 40)
        
        # XML file info
        if os.path.exists(xml_path):
            file_size = os.path.getsize(xml_path) / (1024*1024)
            import os.path
            from datetime import datetime
            mod_time = datetime.fromtimestamp(os.path.getmtime(xml_path))
            result.append(f"📄 CORPCODE.xml: ✅ 존재")
            result.append(f"   📊 크기: {file_size:.2f} MB")
            result.append(f"   📅 수정일: {mod_time.strftime('%Y-%m-%d %H:%M:%S')}")
            
            # Parse and count corporations
            try:
                import xml.etree.ElementTree as ET
                tree = ET.parse(xml_path)
                root = tree.getroot()
                corp_count = len(root.findall('list'))
                result.append(f"   🏢 기업 수: {corp_count:,}개")
            except:
                result.append("   ⚠️ XML 파싱 오류")
        else:
            result.append("📄 CORPCODE.xml: ❌ 없음")
        
        # ZIP file info
        if os.path.exists(zip_path):
            file_size = os.path.getsize(zip_path) / (1024*1024)
            mod_time = datetime.fromtimestamp(os.path.getmtime(zip_path))
            result.append(f"📦 CORPCODE.zip: ✅ 존재")
            result.append(f"   📊 크기: {file_size:.2f} MB")
            result.append(f"   📅 수정일: {mod_time.strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            result.append("📦 CORPCODE.zip: ❌ 없음")
        
        # Storage status
        result.append(f"💾 저장소 초기화: {'✅ 완료' if _storage_initialized else '❌ 미완료'}")
        
        return "\n".join(result)
    except Exception as e:
        return f"❌ 파일 정보 조회 중 오류 발생: {str(e)}"


def search_corporations(query: str, limit: int = 10) -> str:
    """
    기업명 또는 코드를 검색하여 매칭되는 기업 목록을 반환합니다.
    
    Args:
        query: 검색 키워드 (부분 매칭 지원)
        limit: 최대 결과 개수
        
    Returns:
        검색 결과를 포맷팅한 문자열
    """
    try:
        _ensure_storage_initialized()
        
        results = quick_search(query)[:limit]
        
        if not results:
            return f"'{query}'에 대한 검색 결과가 없습니다."
        
        output = []
        output.append(f"🔍 '{query}' 검색 결과 (상위 {len(results)}개):")
        output.append("=" * 50)
        
        for i, corp in enumerate(results, 1):
            output.append(f"{i}. {corp['corp_name']}")
            output.append(f"   - 고유번호: {corp['corp_code']}")
            if corp['stock_code'].strip():
                output.append(f"   - 종목코드: {corp['stock_code']}")
            if corp['corp_eng_name']:
                output.append(f"   - 영문명: {corp['corp_eng_name']}")
            output.append("")
        
        return "\n".join(output)
    except Exception as e:
        return f"검색 중 오류 발생: {str(e)}"


def get_corp_info(corp_code: str) -> str:
    """
    고유번호로 기업 상세 정보를 조회합니다.
    
    Args:
        corp_code: 8자리 고유번호
        
    Returns:
        기업 상세 정보
    """
    try:
        _ensure_storage_initialized()
        
        storage = get_storage()
        info = storage.get_corporation_info(corp_code)
        
        if not info:
            return f"고유번호 {corp_code}에 해당하는 기업을 찾을 수 없습니다."
        
        output = []
        output.append(f"📊 기업 상세 정보")
        output.append("=" * 40)
        output.append(f"🏢 회사명: {info['corp_name']}")
        output.append(f"🔢 고유번호: {info['corp_code']}")
        if info['stock_code'].strip():
            output.append(f"📈 종목코드: {info['stock_code']}")
        if info['corp_eng_name']:
            output.append(f"🌐 영문명: {info['corp_eng_name']}")
        output.append(f"📅 최종수정일: {info['modify_date']}")
        if info['access_count'] > 0:
            output.append(f"🔍 조회횟수: {info['access_count']}회")
        if info['last_accessed']:
            output.append(f"⏰ 최근조회: {info['last_accessed']}")
        
        return "\n".join(output)
    except Exception as e:
        return f"정보 조회 중 오류 발생: {str(e)}"


def get_document_basic_info(rcept_no: str) -> str:
    """
    ZIP 파일 추출 없이 DART API를 통해 기본 공시정보만 조회합니다.
    ZIP 파일 처리에 문제가 있을 때 대안으로 사용합니다.
    
    Args:
        rcept_no: 접수번호 (14자리)
        
    Returns:
        기본 공시정보
    """
    try:
        # 공시검색 API를 통해 기본 정보 조회
        url = "https://opendart.fss.or.kr/api/list.json"
        params = {
            'crtfc_key': config.DART_API_KEY,
            'bgn_de': rcept_no[:8],  # 접수일자 추출
            'end_de': rcept_no[:8],  # 같은 날짜로 설정
            'page_count': 100
        }
        
        response = requests.get(url, params=params)
        
        if response.status_code != 200:
            return f"❌ API 호출 실패: HTTP {response.status_code}"
        
        data = response.json()
        
        if data.get('status') != '000':
            return f"❌ DART API 오류: {data.get('message', '알 수 없는 오류')}"
        
        # 해당 접수번호의 공시 찾기
        target_disclosure = None
        for item in data.get('list', []):
            if item.get('rcept_no') == rcept_no:
                target_disclosure = item
                break
        
        if not target_disclosure:
            return f"❌ 접수번호 {rcept_no}에 해당하는 공시를 찾을 수 없습니다."
        
        # 기본 정보 포맷팅
        result = []
        result.append("📋 DART 공시 기본 정보")
        result.append("=" * 40)
        result.append(f"🏢 회사명: {target_disclosure.get('corp_name', 'N/A')}")
        result.append(f"📄 보고서명: {target_disclosure.get('report_nm', 'N/A')}")
        result.append(f"📅 접수일자: {target_disclosure.get('rcept_dt', 'N/A')}")
        result.append(f"🔍 접수번호: {target_disclosure.get('rcept_no', 'N/A')}")
        
        if target_disclosure.get('flr_nm'):
            result.append(f"📨 제출인: {target_disclosure.get('flr_nm')}")
        
        if target_disclosure.get('rm'):
            result.append(f"📝 비고: {target_disclosure.get('rm')}")
        
        result.append("\n💡 상세 내용을 원하시면 원본 파일 다운로드 기능을 사용하세요.")
        result.append("   (ZIP 파일 처리에 문제가 있을 경우, 다른 재무 정보 API를 활용할 수 있습니다)")
        
        return "\n".join(result)
        
    except Exception as e:
        return f"❌ 기본 정보 조회 중 오류 발생: {str(e)}"


def ensure_document_available(rcept_no: str, download_folder: str) -> str:
    """문서가 사용 가능한지 확인하고 필요시 다운로드 (내부 함수)"""
    from .file_handlers import download_document_zip
    
    extract_folder = os.path.join(download_folder, f"extracted_{rcept_no}")
    
    # 이미 압축해제된 폴더가 있는지 확인
    if os.path.exists(extract_folder) and os.listdir(extract_folder):
        return "READY"  # 내부 상태 코드
    
    # 폴더가 없거나 비어있으면 다운로드 + 압축해제
    download_result = download_document_zip(rcept_no, download_folder)
    
    if "❌" in download_result:
        return download_result
    
    return "DOWNLOAD_COMPLETE"  # 내부 상태 코드


def process_user_request(rcept_no: str, user_request: str, download_folder: str, setup_info: str) -> str:
    """사용자 요청을 분석하고 적절한 처리 수행 (내부 함수)"""
    from .document_analyzer import (
        check_extracted_files_exist, 
        read_extracted_file_content,
        parse_xml_file_to_readable,
        analyze_extracted_dart_document
    )
    
    # 사용자 요청이 없으면 기본 분석 수행
    if not user_request.strip():
        return analyze_extracted_dart_document(rcept_no, "문서 전체 분석", "all", download_folder)
    
    # 사용자 요청 분석
    request_lower = user_request.lower()
    
    # 1. 파일 목록 요청
    if any(keyword in request_lower for keyword in ['파일', '목록', '리스트', 'list', '어떤 파일']):
        return check_extracted_files_exist(rcept_no, download_folder)
    
    # 2. 특정 파일 읽기 요청
    if '파일' in request_lower and any(keyword in request_lower for keyword in ['읽기', '내용', '보기', '표시']):
        # 간단한 파일명 추출 로직
        words = user_request.split()
        potential_filename = None
        for word in words:
            if '.xml' in word or '.html' in word or '.txt' in word:
                potential_filename = word
                break
        
        if potential_filename:
            return read_extracted_file_content(rcept_no, potential_filename, download_folder)
        else:
            return "❌ 읽을 파일명을 찾을 수 없습니다. 예: '사업보고서.xml 파일 내용 보여줘'"
    
    # 3. XML 파싱 요청
    if any(keyword in request_lower for keyword in ['xml', '파싱', 'parsing', '구조화']):
        words = user_request.split()
        xml_filename = None
        for word in words:
            if '.xml' in word:
                xml_filename = word
                break
        
        if xml_filename:
            show_full = any(keyword in request_lower for keyword in ['전체', '모든', '전문', 'full'])
            return parse_xml_file_to_readable(rcept_no, xml_filename, download_folder, show_full)
        else:
            return "❌ 파싱할 XML 파일명을 찾을 수 없습니다. 예: '사업보고서.xml 파싱해줘'"
    
    # 4. 분석 초점 결정
    analysis_focus = "all"
    if any(keyword in request_lower for keyword in ['재무', '매출', '자산', '부채', '순이익', '영업이익', '배당']):
        analysis_focus = "financial"
    elif any(keyword in request_lower for keyword in ['임원', '주주', '지배구조', '이사회', '감사']):
        analysis_focus = "governance"  
    elif any(keyword in request_lower for keyword in ['사업', '영업', '시장', '경쟁', '전략']):
        analysis_focus = "business"
    
    # 5. 기본 분석 수행
    return analyze_extracted_dart_document(rcept_no, user_request, analysis_focus, download_folder)