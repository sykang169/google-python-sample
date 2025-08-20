"""
SSL 호환 API 호출 도구
한국 정부 APIs (apis.data.go.kr)의 SSL 문제를 해결하는 함수 도구들
"""

import json
import xml.etree.ElementTree as ET
from typing import Optional
from .ssl_adapter import create_ssl_session
from .config import config


def get_stock_price_info_ssl(
    itms_nm: Optional[str] = None,
    like_itms_nm: Optional[str] = None,
    isin_cd: Optional[str] = None,
    bas_dt: Optional[str] = None,
    begin_bas_dt: Optional[str] = None,
    end_bas_dt: Optional[str] = None,
    mrkt_ctg: Optional[str] = None,
    num_of_rows: int = 10,
    page_no: int = 1,
    result_type: str = "JSON"
) -> str:
    """
    주식시세정보 조회 (SSL 호환)
    
    Args:
        itms_nm: 종목명 (정확한 매칭)
        like_itms_nm: 종목명 포함 검색 (부분 매칭)
        isin_cd: ISIN 코드
        bas_dt: 기준일자 (YYYYMMDD)
        begin_bas_dt: 기간 조회 시작일
        end_bas_dt: 기간 조회 종료일
        mrkt_ctg: 시장구분 (KOSPI/KOSDAQ/KONEX)
        num_of_rows: 조회 건수 (1-100)
        page_no: 페이지 번호
        result_type: 결과 타입 (JSON/XML)
    
    Returns:
        str: API 응답 결과 (JSON 또는 XML 텍스트)
    """
    
    # SSL 호환 세션 생성
    session = create_ssl_session()
    
    # API 엔드포인트
    url = "https://apis.data.go.kr/1160100/service/GetStockSecuritiesInfoService/getStockPriceInfo"
    
    # 파라미터 구성
    params = {
        'serviceKey': config.STOCK_API_KEY,
        'resultType': result_type,
        'numOfRows': num_of_rows,
        'pageNo': page_no
    }
    
    # 선택적 파라미터 추가
    if itms_nm:
        params['itmsNm'] = itms_nm
    if like_itms_nm:
        params['likeItmsNm'] = like_itms_nm
    if isin_cd:
        params['isinCd'] = isin_cd
    if bas_dt:
        params['basDt'] = bas_dt
    if begin_bas_dt:
        params['beginBasDt'] = begin_bas_dt
    if end_bas_dt:
        params['endBasDt'] = end_bas_dt
    if mrkt_ctg:
        params['mrktCtg'] = mrkt_ctg
    
    try:
        # API 호출 (SSL 어댑터 사용, verify=False 추가)
        response = session.get(url, params=params, timeout=30, verify=False)
        
        if response.status_code == 200:
            # 성공적인 응답 처리
            content = response.text.strip()
            
            # 실제 응답 형식 확인 (한국 정부 API는 JSON 요청시에도 XML 반환할 수 있음)
            if content.startswith('<?xml') or content.startswith('<response>'):
                # XML 응답인 경우 그대로 반환
                return content
            elif result_type.upper() == "JSON":
                try:
                    json_data = json.loads(content)
                    return json.dumps(json_data, ensure_ascii=False, indent=2)
                except json.JSONDecodeError:
                    return content
            else:
                return content
        else:
            return f"❌ API 호출 실패 - HTTP {response.status_code}: {response.text[:500]}"
            
    except Exception as e:
        return f"❌ API 호출 중 오류 발생: {str(e)}"


def get_securities_price_info_ssl(
    itms_nm: Optional[str] = None,
    like_itms_nm: Optional[str] = None,
    isin_cd: Optional[str] = None,
    bas_dt: Optional[str] = None,
    begin_bas_dt: Optional[str] = None,
    end_bas_dt: Optional[str] = None,
    num_of_rows: int = 10,
    page_no: int = 1,
    result_type: str = "JSON"
) -> str:
    """
    수익증권시세정보 조회 (SSL 호환)
    
    Args:
        itms_nm: 종목명
        like_itms_nm: 종목명 포함 검색
        isin_cd: ISIN 코드
        bas_dt: 기준일자 (YYYYMMDD)
        begin_bas_dt: 시작일
        end_bas_dt: 종료일
        num_of_rows: 조회 건수
        page_no: 페이지 번호
        result_type: 결과 타입 (JSON/XML)
    
    Returns:
        str: API 응답 결과
    """
    
    session = create_ssl_session()
    url = "https://apis.data.go.kr/1160100/service/GetStockSecuritiesInfoService/getSecuritiesPriceInfo"
    
    params = {
        'serviceKey': config.STOCK_API_KEY,
        'resultType': result_type,
        'numOfRows': num_of_rows,
        'pageNo': page_no
    }
    
    # 선택적 파라미터 추가
    if itms_nm:
        params['itmsNm'] = itms_nm
    if like_itms_nm:
        params['likeItmsNm'] = like_itms_nm
    if isin_cd:
        params['isinCd'] = isin_cd
    if bas_dt:
        params['basDt'] = bas_dt
    if begin_bas_dt:
        params['beginBasDt'] = begin_bas_dt
    if end_bas_dt:
        params['endBasDt'] = end_bas_dt
    
    try:
        response = session.get(url, params=params, timeout=30, verify=False)
        
        if response.status_code == 200:
            content = response.text.strip()
            
            # 실제 응답 형식 확인 (한국 정부 API는 JSON 요청시에도 XML 반환할 수 있음)
            if content.startswith('<?xml') or content.startswith('<response>'):
                # XML 응답인 경우 그대로 반환
                return content
            elif result_type.upper() == "JSON":
                try:
                    json_data = json.loads(content)
                    return json.dumps(json_data, ensure_ascii=False, indent=2)
                except json.JSONDecodeError:
                    return content
            else:
                return content
        else:
            return f"❌ API 호출 실패 - HTTP {response.status_code}: {response.text[:500]}"
            
    except Exception as e:
        return f"❌ API 호출 중 오류 발생: {str(e)}"


