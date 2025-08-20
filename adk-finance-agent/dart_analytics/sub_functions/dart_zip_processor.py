"""
DART ZIP 파일 처리 유틸리티
공시서류 원본파일(ZIP)을 자동으로 분석하고 구조화된 데이터를 추출합니다.
"""

import zipfile
import os
import tempfile
import shutil
from pathlib import Path
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
import re
import json
from typing import Dict, List, Optional, Any
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DartZipProcessor:
    """DART ZIP 파일 처리 및 분석 클래스"""
    
    def __init__(self):
        self.temp_dirs = []
        self.supported_extensions = {'.xml', '.html', '.htm', '.txt', '.pdf', '.hwp', '.doc', '.docx'}
        
    def __del__(self):
        """임시 디렉토리 정리"""
        self.cleanup_temp_dirs()
    
    def cleanup_temp_dirs(self):
        """생성된 임시 디렉토리들을 정리"""
        for temp_dir in self.temp_dirs:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
        self.temp_dirs.clear()

    def analyze_dart_zip_file(self, zip_file_path: str) -> Dict[str, Any]:
        """
        DART ZIP 파일을 자동으로 압축 해제하고 내용을 분석
        
        Args:
            zip_file_path: ZIP 파일 경로
            
        Returns:
            분석 결과 딕셔너리
        """
        analysis_result = {
            "status": "success",
            "files": [],
            "main_document": None,
            "attachments": [],
            "financial_files": [],
            "summary": "",
            "file_count": 0,
            "total_size": 0
        }
        
        try:
            if not os.path.exists(zip_file_path):
                analysis_result["status"] = "error"
                analysis_result["error"] = "ZIP 파일을 찾을 수 없습니다."
                return analysis_result
            
            # 임시 디렉토리 생성
            temp_dir = tempfile.mkdtemp(prefix="dart_analysis_")
            self.temp_dirs.append(temp_dir)
            
            # ZIP 파일 압축 해제 (인코딩 문제 우회)
            with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
            
            # 압축 해제된 파일들 분석
            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    try:
                        file_info = self._analyze_file(file_path)
                        analysis_result["files"].append(file_info)
                        analysis_result["file_count"] += 1
                        analysis_result["total_size"] += file_info["size"]
                        
                        # 파일 분류
                        self._classify_file(file_info, analysis_result)
                        
                    except Exception as e:
                        logger.warning(f"파일 분석 중 오류 발생 {file}: {str(e)}")
            
            # 요약 생성
            analysis_result["summary"] = self._generate_file_summary(analysis_result)
            
        except Exception as e:
            analysis_result["status"] = "error"
            analysis_result["error"] = f"ZIP 파일 분석 중 오류: {str(e)}"
            logger.error(f"ZIP 분석 오류: {str(e)}")
        
        return analysis_result

    def _analyze_file(self, file_path: str) -> Dict[str, Any]:
        """개별 파일 분석"""
        file_info = {
            "name": os.path.basename(file_path),
            "path": file_path,
            "size": os.path.getsize(file_path),
            "type": Path(file_path).suffix.lower(),
            "content_summary": "",
            "encoding": "unknown",
            "is_main_document": False,
            "document_type": "unknown"
        }
        
        # 파일 유형별 분석
        if file_info["type"] in ['.xml', '.html', '.htm']:
            file_info["content_summary"] = self._extract_xml_html_summary(file_path)
            file_info["document_type"] = self._identify_document_type(file_info["name"])
            file_info["is_main_document"] = self._is_main_document(file_info["name"])
        elif file_info["type"] == '.txt':
            file_info["content_summary"] = self._extract_text_summary(file_path)
        
        return file_info

    def _classify_file(self, file_info: Dict[str, Any], analysis_result: Dict[str, Any]):
        """파일을 유형별로 분류"""
        if file_info["is_main_document"]:
            if analysis_result["main_document"] is None:
                analysis_result["main_document"] = file_info
        elif any(keyword in file_info["name"].lower() for keyword in 
                ['재무제표', '손익계산서', '재무상태표', '현금흐름표', '자본변동표']):
            analysis_result["financial_files"].append(file_info)
        elif file_info["type"] in ['.pdf', '.hwp', '.doc', '.docx']:
            analysis_result["attachments"].append(file_info)

    def _extract_xml_html_summary(self, file_path: str) -> str:
        """XML/HTML 파일에서 주요 내용 추출"""
        try:
            # 인코딩 시도 목록
            encodings = ['utf-8', 'cp949', 'euc-kr', 'latin1']
            content = None
            
            for encoding in encodings:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        content = f.read()
                    break
                except UnicodeDecodeError:
                    continue
            
            if content is None:
                return "인코딩 오류로 내용을 읽을 수 없습니다."
            
            # BeautifulSoup으로 파싱
            soup = BeautifulSoup(content, 'html.parser')
            
            # 주요 정보 추출
            summary_parts = []
            
            # 제목 정보
            title_tags = soup.find_all(['title', 'h1', 'h2'])
            for tag in title_tags[:3]:
                if tag.get_text().strip():
                    summary_parts.append(f"제목: {tag.get_text().strip()}")
            
            # 테이블 정보 (재무제표 등)
            tables = soup.find_all('table')
            if tables:
                summary_parts.append(f"테이블 {len(tables)}개 발견")
            
            # 회사명, 보고서명 등 키워드 검색
            keywords = ['회사명', '법인명', '보고서', '사업연도', '접수번호']
            for keyword in keywords:
                elements = soup.find_all(text=re.compile(keyword))
                for elem in elements[:2]:
                    parent_text = elem.parent.get_text().strip()
                    if len(parent_text) < 200:
                        summary_parts.append(parent_text)
            
            return "\n".join(summary_parts[:10])
            
        except Exception as e:
            return f"분석 오류: {str(e)}"

    def _extract_text_summary(self, file_path: str) -> str:
        """텍스트 파일에서 요약 추출"""
        try:
            encodings = ['utf-8', 'cp949', 'euc-kr']
            for encoding in encodings:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        content = f.read()
                    
                    # 처음 500자만 요약으로 사용
                    summary = content[:500].strip()
                    if len(content) > 500:
                        summary += "..."
                    
                    return summary
                except UnicodeDecodeError:
                    continue
            
            return "텍스트 인코딩 오류"
        except Exception as e:
            return f"텍스트 분석 오류: {str(e)}"

    def _identify_document_type(self, filename: str) -> str:
        """파일명을 통해 문서 유형 식별"""
        filename_lower = filename.lower()
        
        if any(keyword in filename_lower for keyword in ['사업보고서', 'business']):
            return "사업보고서"
        elif any(keyword in filename_lower for keyword in ['감사보고서', 'audit']):
            return "감사보고서"
        elif any(keyword in filename_lower for keyword in ['재무제표', 'financial']):
            return "재무제표"
        elif any(keyword in filename_lower for keyword in ['첨부', 'attachment']):
            return "첨부파일"
        else:
            return "기타문서"

    def _is_main_document(self, filename: str) -> bool:
        """주요 문서인지 판별"""
        filename_lower = filename.lower()
        main_keywords = ['사업보고서', '감사보고서', 'business', 'audit']
        return any(keyword in filename_lower for keyword in main_keywords)

    def _generate_file_summary(self, analysis_result: Dict[str, Any]) -> str:
        """파일 분석 결과 요약 생성"""
        summary_parts = []
        
        summary_parts.append(f"총 {analysis_result['file_count']}개 파일 분석 완료")
        summary_parts.append(f"전체 크기: {analysis_result['total_size'] / 1024 / 1024:.2f} MB")
        
        if analysis_result["main_document"]:
            summary_parts.append(f"주요 문서: {analysis_result['main_document']['name']}")
        
        if analysis_result["financial_files"]:
            summary_parts.append(f"재무관련 파일: {len(analysis_result['financial_files'])}개")
        
        if analysis_result["attachments"]:
            summary_parts.append(f"첨부파일: {len(analysis_result['attachments'])}개")
        
        return " | ".join(summary_parts)

    def extract_structured_data(self, analysis_result: Dict[str, Any], focus_area: str = "all") -> Dict[str, Any]:
        """
        분석된 파일에서 구조화된 데이터 추출
        
        Args:
            analysis_result: analyze_dart_zip_file의 결과
            focus_area: 분석 초점 영역 ("financial", "governance", "business", "all")
        """
        structured_data = {
            "focus_area": focus_area,
            "extracted_sections": {},
            "financial_data": {},
            "governance_data": {},
            "business_data": {},
            "metadata": {}
        }
        
        try:
            focus_keywords = self._get_focus_keywords(focus_area)
            
            # 주요 문서에서 데이터 추출
            if analysis_result.get("main_document"):
                main_doc_data = self._extract_from_main_document(
                    analysis_result["main_document"], 
                    focus_keywords
                )
                structured_data["extracted_sections"]["main_document"] = main_doc_data
            
            # 재무 파일에서 데이터 추출
            for financial_file in analysis_result.get("financial_files", []):
                financial_data = self._extract_financial_data(financial_file)
                if financial_data:
                    structured_data["financial_data"][financial_file["name"]] = financial_data
            
            # 메타데이터 생성
            structured_data["metadata"] = {
                "extraction_time": self._get_current_time(),
                "file_count": analysis_result.get("file_count", 0),
                "focus_area": focus_area
            }
            
        except Exception as e:
            logger.error(f"구조화된 데이터 추출 오류: {str(e)}")
            structured_data["error"] = str(e)
        
        return structured_data

    def _get_focus_keywords(self, focus_area: str) -> List[str]:
        """초점 영역별 키워드 반환"""
        keywords_map = {
            "financial": ["재무상태표", "손익계산서", "현금흐름표", "자본변동표", "매출", "자산", "부채", "자본"],
            "governance": ["임원현황", "주주현황", "감사의견", "지배구조", "이사회", "감사위원회"],
            "business": ["사업개요", "주요사업", "영업실적", "시장점유율", "경쟁현황", "사업전략"],
            "all": []
        }
        return keywords_map.get(focus_area, [])

    def _extract_from_main_document(self, main_doc: Dict[str, Any], focus_keywords: List[str]) -> Dict[str, Any]:
        """주요 문서에서 데이터 추출"""
        extracted_data = {
            "document_info": main_doc,
            "sections": {},
            "tables": [],
            "key_information": {}
        }
        
        try:
            if main_doc["type"] in ['.xml', '.html', '.htm']:
                with open(main_doc["path"], 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                
                soup = BeautifulSoup(content, 'html.parser')
                
                # 테이블 추출
                tables = soup.find_all('table')
                for i, table in enumerate(tables[:5]):  # 상위 5개 테이블만
                    table_data = self._parse_table(table)
                    if table_data:
                        extracted_data["tables"].append({
                            "table_id": i,
                            "data": table_data
                        })
                
                # 키워드 기반 섹션 추출
                if focus_keywords:
                    for keyword in focus_keywords:
                        sections = self._find_sections_by_keyword(soup, keyword)
                        if sections:
                            extracted_data["sections"][keyword] = sections
        
        except Exception as e:
            extracted_data["error"] = f"문서 추출 오류: {str(e)}"
        
        return extracted_data

    def _parse_table(self, table_element) -> List[List[str]]:
        """HTML 테이블을 파싱하여 2차원 리스트로 변환"""
        try:
            rows = table_element.find_all('tr')
            table_data = []
            
            for row in rows:
                cells = row.find_all(['td', 'th'])
                row_data = [cell.get_text().strip() for cell in cells]
                if any(cell for cell in row_data):  # 빈 행 제외
                    table_data.append(row_data)
            
            return table_data[:20]  # 최대 20행까지만
        except Exception:
            return []

    def _find_sections_by_keyword(self, soup, keyword: str) -> List[str]:
        """키워드를 포함한 섹션 찾기"""
        sections = []
        
        # 텍스트에서 키워드를 포함한 요소 찾기
        elements = soup.find_all(text=re.compile(keyword, re.IGNORECASE))
        
        for element in elements[:3]:  # 상위 3개까지만
            parent = element.parent
            if parent:
                section_text = parent.get_text().strip()
                if len(section_text) < 1000:  # 너무 긴 텍스트 제외
                    sections.append(section_text)
        
        return sections

    def _extract_financial_data(self, financial_file: Dict[str, Any]) -> Dict[str, Any]:
        """재무 파일에서 재무 데이터 추출"""
        financial_data = {
            "file_info": financial_file,
            "financial_statements": {},
            "key_figures": {}
        }
        
        try:
            if financial_file["type"] in ['.xml', '.html', '.htm']:
                with open(financial_file["path"], 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                
                soup = BeautifulSoup(content, 'html.parser')
                
                # 재무제표 관련 테이블 찾기
                tables = soup.find_all('table')
                for table in tables:
                    table_text = table.get_text().lower()
                    
                    if any(keyword in table_text for keyword in ['자산', '부채', '자본']):
                        financial_data["financial_statements"]["balance_sheet"] = self._parse_table(table)
                    elif any(keyword in table_text for keyword in ['매출', '영업이익', '순이익']):
                        financial_data["financial_statements"]["income_statement"] = self._parse_table(table)
                    elif any(keyword in table_text for keyword in ['현금흐름', '영업활동']):
                        financial_data["financial_statements"]["cash_flow"] = self._parse_table(table)
        
        except Exception as e:
            financial_data["error"] = f"재무 데이터 추출 오류: {str(e)}"
        
        return financial_data

    def _get_current_time(self) -> str:
        """현재 시간 반환"""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def process_document_zip(self, zip_file_path: str, user_query: str = "", analysis_focus: str = "all") -> Dict[str, Any]:
        """
        사용자 질문에 맞춰 ZIP 파일을 처리하고 답변 생성
        
        Args:
            zip_file_path: ZIP 파일 경로
            user_query: 사용자 질문
            analysis_focus: 분석 초점 ("financial", "governance", "business", "all")
        """
        logger.info(f"ZIP 파일 처리 시작: {zip_file_path}")
        
        # 1단계: ZIP 파일 분석
        analysis_result = self.analyze_dart_zip_file(zip_file_path)
        
        if analysis_result["status"] != "success":
            return {
                "status": "error",
                "message": "ZIP 파일 분석에 실패했습니다.",
                "error": analysis_result.get("error", "알 수 없는 오류")
            }
        
        # 2단계: 사용자 질문 기반 분석 초점 결정
        if analysis_focus == "all":
            analysis_focus = self._determine_focus_from_query(user_query)
        
        # 3단계: 구조화된 데이터 추출
        structured_data = self.extract_structured_data(analysis_result, analysis_focus)
        
        # 4단계: 응답 생성
        response = self._generate_response(analysis_result, structured_data, user_query)
        
        return response

    def _determine_focus_from_query(self, user_query: str) -> str:
        """사용자 질문에서 분석 초점 결정"""
        query_lower = user_query.lower()
        
        if any(keyword in query_lower for keyword in ['재무', '매출', '자산', '부채', '순이익', '영업이익']):
            return "financial"
        elif any(keyword in query_lower for keyword in ['임원', '주주', '지배구조', '이사회', '감사']):
            return "governance"
        elif any(keyword in query_lower for keyword in ['사업', '영업', '시장', '경쟁', '전략']):
            return "business"
        else:
            return "all"

    def _generate_response(self, analysis_result: Dict[str, Any], structured_data: Dict[str, Any], user_query: str) -> Dict[str, Any]:
        """분석 결과를 바탕으로 응답 생성"""
        response = {
            "status": "success",
            "query": user_query,
            "analysis_summary": analysis_result["summary"],
            "focus_area": structured_data["focus_area"],
            "key_findings": [],
            "detailed_data": {},
            "recommendations": []
        }
        
        # 주요 발견사항 생성
        if analysis_result.get("main_document"):
            response["key_findings"].append(
                f"주요 문서 발견: {analysis_result['main_document']['name']}"
            )
        
        if structured_data.get("financial_data"):
            response["key_findings"].append(
                f"재무 데이터 {len(structured_data['financial_data'])}개 파일에서 추출"
            )
        
        # 상세 데이터 포함
        response["detailed_data"] = {
            "file_structure": analysis_result,
            "extracted_content": structured_data
        }
        
        # 권장사항 생성
        response["recommendations"] = self._generate_recommendations(structured_data)
        
        return response

    def _generate_recommendations(self, structured_data: Dict[str, Any]) -> List[str]:
        """분석 결과를 바탕으로 권장사항 생성"""
        recommendations = []
        
        if structured_data.get("financial_data"):
            recommendations.append("💰 재무제표 데이터가 발견되었습니다. 재무비율 분석을 권장합니다.")
        
        if "governance" in str(structured_data).lower():
            recommendations.append("👥 지배구조 정보가 포함되어 있습니다. 임원 및 주주 현황 분석을 권장합니다.")
        
        if structured_data.get("extracted_sections", {}).get("main_document", {}).get("tables"):
            recommendations.append("📊 표 형태의 구조화된 데이터가 발견되었습니다. 세부 분석이 가능합니다.")
        
        if not recommendations:
            recommendations.append("📋 기본적인 공시서류 분석이 완료되었습니다.")
        
        return recommendations

    def format_for_display(self, response: Dict[str, Any]) -> str:
        """사용자에게 표시할 형태로 응답 포맷팅"""
        display_text = []
        
        display_text.append("📁 DART 공시서류 분석 결과")
        display_text.append("=" * 50)
        
        # 요약 정보
        display_text.append(f"📋 분석 요약: {response['analysis_summary']}")
        display_text.append(f"🎯 분석 초점: {response['focus_area']}")
        
        # 주요 발견사항
        if response["key_findings"]:
            display_text.append("\n🔍 주요 발견사항:")
            for finding in response["key_findings"]:
                display_text.append(f"  • {finding}")
        
        # 권장사항
        if response["recommendations"]:
            display_text.append("\n💡 권장사항:")
            for recommendation in response["recommendations"]:
                display_text.append(f"  • {recommendation}")
        
        # 파일 구조 요약
        file_structure = response["detailed_data"]["file_structure"]
        display_text.append(f"\n📂 파일 구조:")
        display_text.append(f"  • 총 파일 수: {file_structure['file_count']}개")
        display_text.append(f"  • 전체 크기: {file_structure['total_size'] / 1024 / 1024:.2f} MB")
        
        if file_structure.get("main_document"):
            display_text.append(f"  • 주요 문서: {file_structure['main_document']['name']}")
        
        if file_structure.get("financial_files"):
            display_text.append(f"  • 재무 관련 파일: {len(file_structure['financial_files'])}개")
        
        if file_structure.get("attachments"):
            display_text.append(f"  • 첨부파일: {len(file_structure['attachments'])}개")
        
        return "\n".join(display_text)