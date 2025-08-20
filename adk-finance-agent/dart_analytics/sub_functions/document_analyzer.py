"""
DART 문서 분석 모듈

공시서류의 분석, XML 파싱, 내용 추출 등을 담당합니다.
"""

import os
import re
import zipfile
from pathlib import Path
from bs4 import BeautifulSoup
from .dart_zip_processor import DartZipProcessor
from .file_handlers import download_document_zip


# ZIP 파일 처리기 인스턴스 생성
zip_processor = DartZipProcessor()


def check_extracted_files_exist(rcept_no: str, download_folder: str = "./downloads") -> str:
    """
    이미 압축 해제된 파일들이 있는지 확인합니다.
    
    Args:
        rcept_no: 접수번호 (14자리)
        download_folder: 다운로드 폴더 경로
        
    Returns:
        파일 존재 여부 및 파일 목록
    """
    try:
        extract_folder = os.path.join(download_folder, f"extracted_{rcept_no}")
        
        if not os.path.exists(extract_folder):
            return f"❌ 압축 해제된 폴더가 없습니다: {extract_folder}"
        
        # 압축 해제된 파일 목록 확인
        extracted_files = []
        for root, dirs, files in os.walk(extract_folder):
            for file in files:
                file_path = os.path.join(root, file)
                extracted_files.append({
                    'name': file,
                    'path': file_path,
                    'size_kb': os.path.getsize(file_path) / 1024
                })
        
        result = []
        result.append(f"✅ 압축 해제된 파일들이 이미 존재합니다")
        result.append(f"📁 폴더 경로: {extract_folder}")
        result.append(f"📋 총 {len(extracted_files)}개 파일")
        
        if extracted_files:
            result.append("\n📄 파일 목록:")
            for file_info in extracted_files[:10]:  # 최대 10개만 표시
                result.append(f"   • {file_info['name']} ({file_info['size_kb']:.1f} KB)")
            
            if len(extracted_files) > 10:
                result.append(f"   ... 및 {len(extracted_files) - 10}개 추가 파일")
        
        result.append("\n💡 분석을 원하시면 analyze_extracted_dart_document 함수를 사용하세요.")
        
        return "\n".join(result)
        
    except Exception as e:
        return f"❌ 파일 확인 중 오류 발생: {str(e)}"


def read_extracted_file_content(rcept_no: str, filename: str, download_folder: str = "./downloads") -> str:
    """
    압축 해제된 특정 파일의 내용을 읽어서 보여줍니다.
    
    Args:
        rcept_no: 접수번호 (14자리)
        filename: 읽을 파일명 (확장자 포함)
        download_folder: 다운로드 폴더 경로
        
    Returns:
        파일 내용 또는 오류 메시지
    """
    try:
        extract_folder = os.path.join(download_folder, f"extracted_{rcept_no}")
        
        if not os.path.exists(extract_folder):
            return f"❌ 압축 해제된 폴더가 없습니다: {extract_folder}\n먼저 download_and_extract_dart_document 함수를 실행해주세요."
        
        # 파일 찾기
        target_file = None
        for root, dirs, files in os.walk(extract_folder):
            for file in files:
                if file == filename or file.lower() == filename.lower():
                    target_file = os.path.join(root, file)
                    break
            if target_file:
                break
        
        if not target_file:
            # 사용가능한 파일 목록 제공
            available_files = []
            for root, dirs, files in os.walk(extract_folder):
                for file in files:
                    available_files.append(file)
            
            result = [f"❌ '{filename}' 파일을 찾을 수 없습니다."]
            result.append("\n📄 사용 가능한 파일들:")
            for file in available_files[:10]:
                result.append(f"   • {file}")
            if len(available_files) > 10:
                result.append(f"   ... 및 {len(available_files) - 10}개 추가 파일")
            
            return "\n".join(result)
        
        # 파일 내용 읽기
        file_size = os.path.getsize(target_file)
        file_ext = os.path.splitext(target_file)[1].lower()
        
        result = []
        result.append(f"📄 파일 내용: {filename}")
        result.append("=" * 50)
        result.append(f"📁 파일 경로: {target_file}")
        result.append(f"💾 파일 크기: {file_size / 1024:.1f} KB")
        result.append("")
        
        # 파일 유형별 처리
        if file_ext in ['.xml', '.html', '.htm']:
            # XML/HTML 파일 처리
            encodings = ['utf-8', 'cp949', 'euc-kr', 'latin1']
            content = None
            
            for encoding in encodings:
                try:
                    with open(target_file, 'r', encoding=encoding) as f:
                        content = f.read()
                    break
                except UnicodeDecodeError:
                    continue
            
            if content:
                # BeautifulSoup으로 정리된 텍스트 추출
                soup = BeautifulSoup(content, 'html.parser')
                text_content = soup.get_text()
                
                # 처음 2000자만 표시
                if len(text_content) > 2000:
                    result.append(f"📝 내용 (처음 2000자):")
                    result.append(text_content[:2000] + "\n...")
                else:
                    result.append(f"📝 전체 내용:")
                    result.append(text_content)
                    
        elif file_ext == '.txt':
            # 텍스트 파일 처리
            encodings = ['utf-8', 'cp949', 'euc-kr']
            content = None
            
            for encoding in encodings:
                try:
                    with open(target_file, 'r', encoding=encoding) as f:
                        content = f.read()
                    break
                except UnicodeDecodeError:
                    continue
            
            if content:
                if len(content) > 2000:
                    result.append(f"📝 내용 (처음 2000자):")
                    result.append(content[:2000] + "\n...")
                else:
                    result.append(f"📝 전체 내용:")
                    result.append(content)
        else:
            result.append(f"⚠️  {file_ext} 파일은 직접 읽기를 지원하지 않습니다.")
            result.append("💡 analyze_extracted_dart_document 함수를 사용하여 분석하세요.")
        
        return "\n".join(result)
        
    except Exception as e:
        return f"❌ 파일 읽기 중 오류 발생: {str(e)}"


def analyze_extracted_dart_document(rcept_no: str, user_query: str = "", analysis_focus: str = "all", download_folder: str = "./downloads") -> str:
    """
    압축 해제된 DART 공시서류를 분석합니다.
    
    Args:
        rcept_no: 접수번호 (14자리) 
        user_query: 사용자 질문 (선택사항)
        analysis_focus: 분석 초점 ("financial", "governance", "business", "all")
        download_folder: 압축 해제된 폴더가 있는 경로 (기본값: ./downloads)
        
    Returns:
        분석 결과
    """
    try:
        # 압축 해제된 폴더 경로
        extract_folder = os.path.join(download_folder, f"extracted_{rcept_no}")
        
        if not os.path.exists(extract_folder):
            return f"❌ 압축 해제된 폴더를 찾을 수 없습니다: {extract_folder}\n먼저 download_and_extract_dart_document 함수를 실행해주세요."
        
        # 임시 ZIP 파일 생성 (DartZipProcessor 호환성을 위해)
        temp_zip_path = os.path.join(download_folder, f"temp_{rcept_no}.zip")
        
        with zipfile.ZipFile(temp_zip_path, 'w', zipfile.ZIP_DEFLATED) as zip_ref:
            for root, dirs, files in os.walk(extract_folder):
                for file in files:
                    file_path = os.path.join(root, file)
                    # 폴더 구조 유지하면서 ZIP에 추가
                    arcname = os.path.relpath(file_path, extract_folder)
                    zip_ref.write(file_path, arcname)
        
        # ZIP 파일 분석
        response = zip_processor.process_document_zip(temp_zip_path, user_query, analysis_focus)
        
        # 임시 ZIP 파일 삭제
        os.remove(temp_zip_path)
        
        if response["status"] != "success":
            return f"❌ 문서 분석 실패: {response.get('message', '알 수 없는 오류')}"
        
        # 사용자 친화적 형태로 포맷팅
        formatted_response = zip_processor.format_for_display(response)
        
        # 헤더 추가
        result = []
        result.append(f"📊 DART 공시서류 분석 결과 (접수번호: {rcept_no})")
        result.append("=" * 60)
        result.append(formatted_response)
        
        return "\n".join(result)
        
    except Exception as e:
        return f"❌ 문서 분석 중 오류 발생: {str(e)}"


def parse_xml_file_to_readable(rcept_no: str, filename: str, download_folder: str = "./downloads", show_full_content: bool = False, max_length: int = 10000) -> str:
    """
    압축 해제된 XML 파일을 사용자 친화적인 형태로 파싱하여 보여줍니다.
    
    Args:
        rcept_no: 접수번호 (14자리)
        filename: XML 파일명 (확장자 포함)
        download_folder: 다운로드 폴더 경로
        show_full_content: True이면 전체 텍스트 내용 표시, False이면 구조화된 정보 표시
        max_length: 전체 내용 표시 시 최대 텍스트 길이 (기본값: 10000자)
        
    Returns:
        파싱된 XML 내용 또는 오류 메시지
    """
    try:
        extract_folder = os.path.join(download_folder, f"extracted_{rcept_no}")
        
        if not os.path.exists(extract_folder):
            return f"❌ 압축 해제된 폴더가 없습니다: {extract_folder}\n먼저 download_and_extract_dart_document 함수를 실행해주세요."
        
        # XML 파일 찾기
        target_file = None
        for root, dirs, files in os.walk(extract_folder):
            for file in files:
                if (file == filename or file.lower() == filename.lower()) and file.lower().endswith('.xml'):
                    target_file = os.path.join(root, file)
                    break
            if target_file:
                break
        
        if not target_file:
            # 사용가능한 XML 파일 목록 제공
            xml_files = []
            for root, dirs, files in os.walk(extract_folder):
                for file in files:
                    if file.lower().endswith('.xml'):
                        xml_files.append(file)
            
            result = [f"❌ '{filename}' XML 파일을 찾을 수 없습니다."]
            if xml_files:
                result.append("\n📄 사용 가능한 XML 파일들:")
                for xml_file in xml_files[:10]:
                    result.append(f"   • {xml_file}")
                if len(xml_files) > 10:
                    result.append(f"   ... 및 {len(xml_files) - 10}개 추가 XML 파일")
            else:
                result.append("\n⚠️  압축 해제된 폴더에 XML 파일이 없습니다.")
            
            return "\n".join(result)
        
        # XML 파일 읽기 및 파싱
        encodings = ['utf-8', 'cp949', 'euc-kr', 'latin1']
        xml_content = None
        
        for encoding in encodings:
            try:
                with open(target_file, 'r', encoding=encoding) as f:
                    xml_content = f.read()
                break
            except UnicodeDecodeError:
                continue
        
        if not xml_content:
            return f"❌ XML 파일을 읽을 수 없습니다: {filename}"
        
        result = []
        result.append(f"📄 XML 파일 파싱 결과: {filename}")
        result.append("=" * 60)
        result.append(f"📁 파일 경로: {target_file}")
        result.append(f"💾 파일 크기: {os.path.getsize(target_file) / 1024:.1f} KB")
        result.append("")
        
        # BeautifulSoup으로 XML 파싱
        soup = BeautifulSoup(xml_content, 'xml')
        
        # show_full_content가 True이면 전체 텍스트 내용만 표시
        if show_full_content:
            result.append("📝 문서 전체 내용:")
            result.append("-" * 40)
            
            # 전체 텍스트 추출
            full_text = soup.get_text()
            
            # 공백과 줄바꿈 정리
            lines = full_text.split('\n')
            cleaned_lines = []
            for line in lines:
                line = line.strip()
                if line:  # 빈 줄 제외
                    cleaned_lines.append(line)
            
            cleaned_text = '\n'.join(cleaned_lines)
            
            if len(cleaned_text) > max_length:
                result.append(f"📋 전체 내용 (처음 {max_length:,}자, 전체 {len(cleaned_text):,}자):")
                result.append("")
                # 문단 단위로 자르기 시도
                truncated_text = cleaned_text[:max_length]
                last_period = truncated_text.rfind('.')
                if last_period > max_length * 0.8:  # 80% 이후에 마침표가 있으면 거기서 자르기
                    truncated_text = truncated_text[:last_period + 1]
                
                result.append(truncated_text)
                result.append("")
                result.append(f"... (나머지 {len(cleaned_text) - len(truncated_text):,}자 생략)")
                result.append("\n💡 전체 내용을 보려면 max_length 파라미터를 늘려주세요.")
            else:
                result.append(f"📋 전체 내용 ({len(cleaned_text):,}자):")
                result.append("")
                result.append(cleaned_text)
            
            return "\n".join(result)
        
        # 기본 모드: 구조화된 정보 표시
        result.extend(_extract_structured_xml_info(soup))
        
        return "\n".join(result)
        
    except Exception as e:
        return f"❌ XML 파일 파싱 중 오류 발생: {str(e)}"


def _extract_structured_xml_info(soup: BeautifulSoup) -> list:
    """XML에서 구조화된 정보 추출"""
    result = []
    
    # 1. 문서 기본 정보 추출
    result.append("📋 문서 기본 정보:")
    result.append("-" * 30)
    
    # 일반적인 DART XML 필드들 찾기
    basic_fields = {
        'corp_name': '회사명',
        'corp_code': '회사코드', 
        'report_nm': '보고서명',
        'rcept_dt': '접수일자',
        'flr_nm': '제출인',
        'bsns_year': '사업연도',
        'reprt_code': '보고서코드'
    }
    
    for field, label in basic_fields.items():
        element = soup.find(field)
        if element and element.get_text().strip():
            result.append(f"{label}: {element.get_text().strip()}")
    
    # 2. 문서 내용 섹션 추출
    result.append(f"\n📄 문서 주요 내용:")
    result.append("-" * 30)
    
    # 주요 텍스트 섹션 찾기 (p, div, section 등)
    content_sections = []
    
    # 일반적인 콘텐츠 태그들에서 텍스트 추출
    content_tags = soup.find_all(['p', 'div', 'section', 'article', 'span'])
    for tag in content_tags:
        text = tag.get_text().strip()
        # 의미있는 텍스트만 선별 (50자 이상, 3000자 이하)
        if 50 <= len(text) <= 3000:
            # 중복 제거 (이미 포함된 텍스트는 제외)
            is_duplicate = False
            for existing in content_sections:
                if text in existing or existing in text:
                    is_duplicate = True
                    break
            if not is_duplicate:
                content_sections.append(text)
    
    # 콘텐츠 섹션 표시 (최대 5개)
    if content_sections:
        result.append("📝 주요 문서 내용:")
        for i, content in enumerate(content_sections[:5]):
            result.append(f"\n🔸 섹션 {i+1}:")
            # 긴 텍스트는 줄바꿈으로 정리
            formatted_content = content.replace('. ', '.\n   ')
            if len(formatted_content) > 1000:
                result.append(f"   {formatted_content[:1000]}...")
            else:
                result.append(f"   {formatted_content}")
    
    # 3. 테이블 데이터 추출
    tables = soup.find_all(['table', 'list'])
    if tables:
        result.append(f"\n📊 데이터 테이블 ({len(tables)}개 발견):")
        result.append("-" * 30)
        
        for i, table in enumerate(tables[:3]):  # 처음 3개 테이블만
            result.extend(_extract_table_data(table, i))
    
    # 4. 특정 키워드 기반 정보 추출
    keyword_sections = {
        '💰 재무정보': ['자산', '부채', '자본', '매출', '영업이익', '순이익', '배당', '주가'],
        '👥 회사정보': ['대표이사', '본점', '설립', '직원', '사업목적', '주요사업'],
        '📈 실적정보': ['매출액', '영업실적', '시장점유율', '성장률', '수익률'],
        '🏛️ 지배구조': ['주주', '이사회', '감사', '임원', '지분율']
    }
    
    for section_name, keywords in keyword_sections.items():
        found_info = []
        for keyword in keywords:
            # 키워드를 포함한 요소들 찾기
            elements = soup.find_all(text=re.compile(keyword, re.IGNORECASE))
            for elem in elements[:2]:  # 각 키워드당 최대 2개
                parent = elem.parent
                if parent:
                    text = parent.get_text().strip()
                    # 적절한 길이의 텍스트만 선별
                    if 20 <= len(text) <= 500 and keyword.lower() in text.lower():
                        # 중복 제거
                        if not any(existing in text or text in existing for existing in found_info):
                            found_info.append(text)
        
        if found_info:
            result.append(f"\n{section_name}:")
            result.append("-" * 25)
            for info in found_info[:3]:  # 최대 3개만
                result.append(f"• {info}")
    
    # 5. XML 구조 요약
    result.append(f"\n🔧 문서 구조 정보:")
    result.append("-" * 30)
    
    # 최상위 태그들 찾기
    if soup.find():
        root_tag = soup.find()
        result.append(f"문서 유형: <{root_tag.name}>")
        
        # 주요 하위 태그들 (직접 자식만)
        child_tags = set()
        for child in root_tag.find_all(recursive=False):
            if child.name:
                child_tags.add(child.name)
        
        if child_tags:
            result.append(f"주요 섹션: {', '.join(sorted(child_tags)[:10])}")
    
    # 전체 요소 수와 텍스트 길이
    all_elements = soup.find_all()
    total_text = soup.get_text()
    result.append(f"XML 요소 수: {len(all_elements)}개")
    result.append(f"총 텍스트 길이: {len(total_text):,}자")
    
    result.append(f"\n💡 더 상세한 분석을 원하시면 analyze_extracted_dart_document 함수를 사용하세요.")
    
    return result


def _extract_table_data(table, index: int) -> list:
    """테이블 데이터 추출"""
    result = []
    
    if table.name == 'table':
        result.append(f"\n📈 테이블 {index+1}:")
        rows = table.find_all('tr')
        if rows:
            # 테이블 헤더 (첫 번째 행)
            if rows:
                header_row = rows[0]
                header_cells = header_row.find_all(['td', 'th'])
                if header_cells:
                    headers = [cell.get_text().strip() for cell in header_cells]
                    result.append(f"   📋 컬럼: {' | '.join(headers)}")
            
            # 데이터 행들 (최대 10행)
            for row_idx, row in enumerate(rows[1:11]):  # 헤더 제외하고 최대 10행
                cells = row.find_all(['td', 'th'])
                if cells:
                    row_data = [cell.get_text().strip() for cell in cells]
                    # 빈 행 제외
                    if any(data.strip() for data in row_data):
                        result.append(f"   {row_idx+1:2d}. {' | '.join(row_data)}")
            
            if len(rows) > 11:
                result.append(f"   ... 및 {len(rows) - 11}개 추가 행")
    
    elif table.name == 'list':
        result.append(f"\n📋 리스트 {index+1}:")
        items = table.find_all(recursive=False)
        for idx, item in enumerate(items[:10]):  # 최대 10개 항목
            item_text = item.get_text().strip()
            if item_text:
                if len(item_text) > 200:
                    result.append(f"   {idx+1}. {item_text[:200]}...")
                else:
                    result.append(f"   {idx+1}. {item_text}")
    
    return result