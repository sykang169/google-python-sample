"""
SSL 어댑터 모듈
한국 정부 API (apis.data.go.kr)를 위한 커스텀 SSL 설정
"""

import ssl
import urllib3
from urllib3.exceptions import InsecureRequestWarning
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

# SSL 경고 비활성화
urllib3.disable_warnings(InsecureRequestWarning)


class KoreanGovAPIAdapter(HTTPAdapter):
    """
    한국 정부 APIs (apis.data.go.kr) 전용 SSL 어댑터
    TLS 1.2 강제 사용 및 SSL 검증 비활성화
    """
    
    def init_poolmanager(self, *args, **kwargs):
        """풀 매니저 초기화 - 커스텀 SSL 컨텍스트 적용"""
        # SSL 컨텍스트 생성
        context = create_urllib3_context()
        
        # TLS 1.2 강제 사용 (한국 정부 API 호환성)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.maximum_version = ssl.TLSVersion.TLSv1_2
        
        # SSL 검증 비활성화 (한국 정부 API SSL 인증서 문제 해결)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        
        # Cipher suite 설정 (선택사항)
        try:
            context.set_ciphers('DHE-RSA-AES256-SHA:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-RSA-AES128-GCM-SHA256')
        except Exception:
            # Cipher 설정이 실패해도 계속 진행
            pass
        
        kwargs['ssl_context'] = context
        return super().init_poolmanager(*args, **kwargs)


def create_ssl_session():
    """
    한국 정부 API 호출용 requests.Session 생성
    
    Returns:
        requests.Session: SSL 설정이 적용된 세션
    """
    import requests
    
    session = requests.Session()
    session.mount('https://', KoreanGovAPIAdapter())
    
    # 기본 헤더 설정
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': '*/*',
        'Connection': 'keep-alive'
    })
    
    return session