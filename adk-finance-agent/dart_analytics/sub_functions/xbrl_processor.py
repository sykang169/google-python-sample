"""
XBRL 파일 처리 모듈

XBRL(eXtensible Business Reporting Language) 파일의 다운로드, 파싱 및 분석을 담당합니다.
"""

import os
from bs4 import BeautifulSoup
from .file_handlers import download_and_extract_file


def download_xbrl_financial_statement(rcept_no: str, reprt_code: str, download_folder: str = "./downloads") -> str:
    """
    재무제표 원본파일(XBRL) 다운로드 및 처리
    
    Args:
        rcept_no: 접수번호 (8자리)
        reprt_code: 보고서 코드 (11013: 1분기, 11012: 반기, 11014: 3분기, 11011: 사업보고서 등)
        download_folder: 다운로드할 폴더 경로
        
    Returns:
        처리 결과 메시지
    """
    return download_and_extract_file(
        endpoint='fnlttXbrl.xml',
        params={
            'rcept_no': rcept_no,
            'reprt_code': reprt_code
        },
        download_folder=download_folder,
        file_prefix=f'xbrl_{rcept_no}_{reprt_code}'
    )


def process_xbrl_files(rcept_no: str, reprt_code: str, download_folder: str = "./downloads") -> str:
    """
    XBRL 파일을 다운로드하고 내용을 분석하여 사용자에게 표시
    
    Args:
        rcept_no: 접수번호 (8자리)
        reprt_code: 보고서 코드
        download_folder: 다운로드할 폴더 경로
        
    Returns:
        분석된 XBRL 내용
    """
    # 1. XBRL 파일 다운로드
    download_result = download_xbrl_financial_statement(rcept_no, reprt_code, download_folder)
    
    if "❌" in download_result:
        return download_result
    
    # 2. 압축 해제된 XBRL 파일들 분석
    extract_folder = os.path.join(download_folder, f"extracted_xbrl_{rcept_no}_{reprt_code}")
    
    try:
        if not os.path.exists(extract_folder):
            return f"❌ XBRL 압축 해제 폴더를 찾을 수 없습니다: {extract_folder}"
        
        # XBRL 파일들 찾기
        xbrl_files = []
        for root, dirs, files in os.walk(extract_folder):
            for file in files:
                if file.lower().endswith(('.xbrl', '.xml')):
                    xbrl_files.append(os.path.join(root, file))
        
        if not xbrl_files:
            return f"❌ XBRL 파일을 찾을 수 없습니다"
        
        # 주요 XBRL 파일 분석
        result = []
        result.append(f"📊 XBRL 재무제표 분석 결과")
        result.append("=" * 50)
        result.append(f"📋 접수번호: {rcept_no}")
        result.append(f"📋 보고서 코드: {reprt_code}")
        result.append(f"📁 총 {len(xbrl_files)}개 XBRL 파일 발견")
        result.append("")
        
        # 각 XBRL 파일에서 주요 재무 정보 추출
        for i, xbrl_file in enumerate(xbrl_files[:3]):  # 최대 3개 파일만 처리
            filename = os.path.basename(xbrl_file)
            result.append(f"📄 파일 {i+1}: {filename}")
            
            # XBRL 파일 파싱 시도
            financial_data = extract_xbrl_financial_data(xbrl_file)
            if financial_data:
                result.extend(financial_data)
            else:
                result.append("   ⚠️ 재무 데이터 추출 실패")
            
            result.append("")
        
        if len(xbrl_files) > 3:
            result.append(f"💡 총 {len(xbrl_files)}개 파일 중 3개만 표시됨")
        
        return "\n".join(result)
        
    except Exception as e:
        return f"❌ XBRL 분석 중 오류: {str(e)}"


def extract_xbrl_financial_data(xbrl_file_path: str) -> list:
    """XBRL 파일에서 주요 재무 데이터 추출"""
    try:
        # 여러 인코딩으로 시도
        encodings = ['utf-8', 'cp949', 'euc-kr', 'latin1']
        content = None
        
        for encoding in encodings:
            try:
                with open(xbrl_file_path, 'r', encoding=encoding) as f:
                    content = f.read()
                break
            except UnicodeDecodeError:
                continue
        
        if not content:
            return ["   ❌ 파일 읽기 실패"]
        
        # BeautifulSoup으로 파싱
        soup = BeautifulSoup(content, 'xml')
        
        result = []
        
        # XBRL 네임스페이스와 주요 태그들 찾기
        financial_items = [
            ('자산총계', ['assets', 'totalassets', '자산총계']),
            ('부채총계', ['liabilities', 'totalliabilities', '부채총계']),
            ('자본총계', ['equity', 'totalequity', '자본총계']),
            ('매출액', ['revenue', 'sales', '매출액']),
            ('영업이익', ['operatingincome', '영업이익']),
            ('당기순이익', ['netincome', '당기순이익'])
        ]
        
        found_items = []
        for item_name, search_terms in financial_items:
            for term in search_terms:
                # 태그 이름에 포함된 경우
                elements = soup.find_all(lambda tag: tag.name and term.lower() in tag.name.lower())
                if elements:
                    for elem in elements[:1]:  # 첫 번째 매칭만
                        if elem.get_text().strip():
                            found_items.append(f"   • {item_name}: {elem.get_text().strip()}")
                            break
                    break
        
        if found_items:
            result.append("   💰 주요 재무 데이터:")
            result.extend(found_items)
        else:
            # 일반적인 텍스트 정보라도 추출
            text_content = soup.get_text()
            if text_content.strip():
                result.append(f"   📋 파일 크기: {len(text_content):,}자")
                result.append(f"   📋 XML 요소 수: {len(soup.find_all())}개")
            else:
                result.append("   ⚠️ 내용 추출 실패")
        
        return result
        
    except Exception as e:
        return [f"   ❌ 파싱 오류: {str(e)}"]