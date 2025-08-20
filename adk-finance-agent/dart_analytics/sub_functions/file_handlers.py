"""
DART API 파일 처리 모듈

ZIP, XML, JSON 등 다양한 파일 형식의 다운로드 및 처리를 담당합니다.
"""

import os
import requests
import zipfile
from pathlib import Path
from ..config import config


def download_and_extract_file(endpoint: str, params: dict, download_folder: str, file_prefix: str) -> str:
    """
    범용 DART API 파일 다운로드 및 처리 함수
    
    Args:
        endpoint: API 엔드포인트 (예: 'document.xml', 'corpCode.xml', 'fnlttXbrl.xml')
        params: API 파라미터 딕셔너리
        download_folder: 다운로드할 폴더 경로
        file_prefix: 저장할 파일명 접두사
        
    Returns:
        처리 결과 메시지
    """
    try:
        # 다운로드 폴더 생성
        Path(download_folder).mkdir(parents=True, exist_ok=True)
        
        # API 호출
        api_url = f"https://opendart.fss.or.kr/api/{endpoint}"
        full_params = {'crtfc_key': config.DART_API_KEY, **params}
        
        response = requests.get(api_url, params=full_params, timeout=60, stream=True)
        
        if response.status_code != 200:
            return f"❌ 다운로드 실패: HTTP {response.status_code}"
        
        # Content-Type 확인 및 처리
        content_type = response.headers.get('content-type', '').lower()
        
        if 'application/zip' in content_type or 'application/octet-stream' in content_type:
            return _handle_zip_response(response, download_folder, file_prefix)
        elif 'application/xml' in content_type or 'text/xml' in content_type:
            return _handle_xml_response(response, download_folder, file_prefix)
        elif 'application/json' in content_type:
            return _handle_json_response(response, download_folder, file_prefix)
        else:
            # 오류 응답 파싱 시도
            try:
                xml_content = response.text
                if 'status' in xml_content and '000' not in xml_content:
                    return f"❌ DART API 오류: {xml_content}"
            except:
                pass
            return f"❌ 예상치 못한 응답 형식: {content_type}"
        
    except requests.exceptions.Timeout:
        return "❌ 다운로드 시간 초과 (60초)"
    except requests.exceptions.RequestException as e:
        return f"❌ 네트워크 오류: {str(e)}"
    except Exception as e:
        return f"❌ 처리 중 오류: {str(e)}"


def _handle_zip_response(response, download_folder: str, file_prefix: str) -> str:
    """ZIP 파일 응답 처리"""
    try:
        # ZIP 파일로 저장
        zip_file_path = os.path.join(download_folder, f"{file_prefix}.zip")
        with open(zip_file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        # 파일 크기 확인
        file_size = os.path.getsize(zip_file_path)
        if file_size == 0:
            os.remove(zip_file_path)
            return f"❌ 다운로드된 파일이 비어있습니다"
        
        # 압축 해제
        extract_folder = os.path.join(download_folder, f"extracted_{file_prefix}")
        Path(extract_folder).mkdir(parents=True, exist_ok=True)
        
        with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
            zip_ref.extractall(extract_folder)
        
        # 압축 해제된 파일 목록 확인
        extracted_files = []
        for root, dirs, files in os.walk(extract_folder):
            for file in files:
                extracted_files.append(os.path.join(root, file))
        
        os.remove(zip_file_path)  # 원본 ZIP 파일 삭제
        
        return f"✅ ZIP 파일 처리 완료: {len(extracted_files)}개 파일 추출"
        
    except zipfile.BadZipFile:
        return "❌ 손상된 ZIP 파일"
    except Exception as e:
        return f"❌ ZIP 처리 중 오류: {str(e)}"


def _handle_xml_response(response, download_folder: str, file_prefix: str) -> str:
    """XML 파일 응답 처리"""
    try:
        # XML 파일로 저장
        xml_file_path = os.path.join(download_folder, f"{file_prefix}.xml")
        with open(xml_file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        file_size = os.path.getsize(xml_file_path)
        return f"✅ XML 파일 저장 완료: {file_size/1024:.1f} KB"
        
    except Exception as e:
        return f"❌ XML 처리 중 오류: {str(e)}"


def _handle_json_response(response, download_folder: str, file_prefix: str) -> str:
    """JSON 파일 응답 처리"""
    try:
        # JSON 파일로 저장
        json_file_path = os.path.join(download_folder, f"{file_prefix}.json")
        with open(json_file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        file_size = os.path.getsize(json_file_path)
        return f"✅ JSON 파일 저장 완료: {file_size/1024:.1f} KB"
        
    except Exception as e:
        return f"❌ JSON 처리 중 오류: {str(e)}"


def download_corp_codes(download_folder: str = "./downloads") -> str:
    """
    전체 기업 고유번호 파일(CORPCODE.xml)을 다운로드하고 압축해제
    
    Args:
        download_folder: 다운로드할 폴더 경로
        
    Returns:
        처리 결과 메시지
    """
    return download_and_extract_file(
        endpoint='corpCode.xml',
        params={},
        download_folder=download_folder,
        file_prefix='corpcode'
    )


def download_document_zip(rcept_no: str, download_folder: str = "./downloads") -> str:
    """
    DART API를 통해 공시서류 원본파일(ZIP)을 다운로드하고 압축을 해제합니다.
    
    Args:
        rcept_no: 접수번호 (14자리)
        download_folder: 다운로드할 폴더 경로 (기본값: ./downloads)
        
    Returns:
        압축 해제된 폴더 경로 또는 오류 메시지
    """
    try:
        # 다운로드 폴더 생성
        Path(download_folder).mkdir(parents=True, exist_ok=True)
        
        # DART API 호출
        url = "https://opendart.fss.or.kr/api/document.xml"
        params = {
            'crtfc_key': config.DART_API_KEY,
            'rcept_no': rcept_no
        }
        
        response = requests.get(url, params=params, stream=True)
        
        if response.status_code != 200:
            return f"❌ API 호출 실패: HTTP {response.status_code}"
        
        # Content-Type 확인
        content_type = response.headers.get('content-type', '')
        
        # XML 오류 응답 체크
        if 'xml' in content_type:
            xml_content = response.text
            if 'status' in xml_content and '000' not in xml_content:
                return f"❌ DART API 오류: {xml_content}"
        
        # ZIP 파일 저장
        zip_filename = f"dart_document_{rcept_no}.zip"
        zip_filepath = os.path.join(download_folder, zip_filename)
        
        with open(zip_filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        # 파일 크기 확인
        file_size = os.path.getsize(zip_filepath)
        if file_size == 0:
            os.remove(zip_filepath)
            return f"❌ 다운로드된 파일이 비어있습니다. 접수번호를 확인해주세요: {rcept_no}"
        
        # 압축 해제 폴더 생성
        extract_folder = os.path.join(download_folder, f"extracted_{rcept_no}")
        Path(extract_folder).mkdir(parents=True, exist_ok=True)
        
        # ZIP 파일 압축 해제 (여러 방법 시도)
        extracted_count = 0
        try:
            with zipfile.ZipFile(zip_filepath, 'r') as zip_ref:
                zip_ref.extractall(extract_folder)
        except UnicodeDecodeError:
            # 인코딩 문제 발생 시 개별 파일별로 추출 시도
            with zipfile.ZipFile(zip_filepath, 'r') as zip_ref:
                for member in zip_ref.namelist():
                    try:
                        zip_ref.extract(member, extract_folder)
                        extracted_count += 1
                    except UnicodeDecodeError:
                        # 파일명을 안전한 형태로 변경하여 추출
                        safe_name = f"file_{extracted_count}.dat"
                        with zip_ref.open(member) as source:
                            safe_path = os.path.join(extract_folder, safe_name)
                            with open(safe_path, 'wb') as target:
                                target.write(source.read())
                        extracted_count += 1
        
        # 압축 해제된 파일 목록 확인
        extracted_files = []
        for root, dirs, files in os.walk(extract_folder):
            for file in files:
                extracted_files.append(os.path.join(root, file))
        
        result = []
        result.append(f"✅ ZIP 파일 다운로드 및 압축 해제 완료")
        result.append(f"📁 압축 해제 폴더: {extract_folder}")
        result.append(f"📋 총 {len(extracted_files)}개 파일 추출됨")
        result.append(f"💾 원본 ZIP 크기: {file_size/1024:.1f} KB")
        
        # 주요 파일들 표시 (최대 5개)
        if extracted_files:
            result.append("\n📄 추출된 주요 파일:")
            for file_path in extracted_files[:5]:
                filename = os.path.basename(file_path)
                file_size_kb = os.path.getsize(file_path) / 1024
                result.append(f"   • {filename} ({file_size_kb:.1f} KB)")
            
            if len(extracted_files) > 5:
                result.append(f"   ... 및 {len(extracted_files) - 5}개 추가 파일")
        
        # 원본 ZIP 파일 삭제 (옵션)
        os.remove(zip_filepath)
        
        return "\n".join(result)
        
    except zipfile.BadZipFile:
        return f"❌ 유효하지 않은 ZIP 파일입니다: {rcept_no}"
    except requests.exceptions.RequestException as e:
        return f"❌ 네트워크 오류: {str(e)}"
    except Exception as e:
        return f"❌ 다운로드 및 압축 해제 중 오류 발생: {str(e)}"