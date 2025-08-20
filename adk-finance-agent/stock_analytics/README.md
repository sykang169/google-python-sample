# Stock Analytics Agent 📈

금융위원회 주식시세정보 API를 활용한 Google ADK 기반 주식 분석 에이전트입니다. SSL 호환성 문제를 해결하여 한국 정부 API와 안정적으로 연동합니다.

## 🎯 주요 기능

- **실시간 주식 시세 조회**: KOSPI, KOSDAQ, KONEX 시장 데이터
- **수익증권 시세 조회**: 펀드 및 수익증권 시세 정보
- **SSL 호환성 해결**: 한국 정부 API의 SSL/TLS 문제 자동 처리
- **다양한 검색 옵션**: 종목명, ISIN 코드, 날짜별 조회 지원

## 🔧 기술 특징

### SSL 호환성 해결
```python
# 한국 정부 API SSL 문제를 해결하는 커스텀 어댑터
class KoreanGovAPIAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        context = create_urllib3_context()
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.verify_mode = ssl.CERT_NONE  # 정부 API 호환성
```

### 이중 도구 시스템
- **OpenAPIToolset**: 표준 OpenAPI 도구 (백업용)
- **SSL 호환 함수**: 실제 API 호출용 메인 도구

## 🚀 빠른 시작

### 1. 환경 설정

#### API 키 발급
1. [공공데이터포털](https://www.data.go.kr/data/15094808/openapi.do) 접속
2. 회원가입 및 로그인
3. "금융위원회_주식시세정보" API 신청
4. 승인 후 API 키 발급 받기

#### 환경변수 설정
```bash
# .env 파일에 추가
STOCK_API_KEY=your_government_api_key_here
```

### 2. 에이전트 실행

#### ADK Web UI 사용
```bash
adk web
# http://localhost:8000에서 stock_analytics 선택
```

#### 직접 실행
```python
from stock_analytics import root_agent

# 주식 시세 조회 예시
result = root_agent.run(
    "삼성전자 주식 현재가를 알려주세요"
)
print(result.stock_result)
```

## 📊 사용 예시

### 기본 주식 조회
```
사용자: "삼성전자 주식 현재가 알려주세요"
→ get_stock_price_info_ssl(itms_nm="삼성전자")
```

### 날짜별 조회
```
사용자: "어제 SK하이닉스 주가는?"
→ get_stock_price_info_ssl(itms_nm="SK하이닉스", bas_dt="20250819")
```

### 시장별 검색
```
사용자: "코스닥 상위 10개 종목 보여주세요"
→ get_stock_price_info_ssl(mrkt_ctg="KOSDAQ", num_of_rows=10)
```

### 포함 검색
```
사용자: "삼성으로 시작하는 모든 종목"
→ get_stock_price_info_ssl(like_itms_nm="삼성")
```

## 🛠️ API 파라미터

### get_stock_price_info_ssl
| 파라미터 | 타입 | 설명 | 예시 |
|----------|------|------|------|
| `itms_nm` | str | 정확한 종목명 | "삼성전자" |
| `like_itms_nm` | str | 포함 검색 | "삼성" |
| `isin_cd` | str | ISIN 코드 | "KR7005930003" |
| `bas_dt` | str | 기준일자 | "20250819" |
| `mrkt_ctg` | str | 시장구분 | "KOSPI", "KOSDAQ", "KONEX" |
| `num_of_rows` | int | 조회 건수 | 1-100 (기본: 10) |

### get_securities_price_info_ssl
수익증권(펀드) 시세 조회용 - 파라미터는 주식과 동일

## 📋 응답 데이터 구조

### 성공 응답 (JSON)
```json
{
  "header": {
    "resultCode": "00",
    "resultMsg": "정상처리"
  },
  "body": {
    "totalCount": "1",
    "items": {
      "item": [{
        "basDt": "20250819",        // 기준일자
        "itmsNm": "삼성전자",       // 종목명
        "clpr": "75000",           // 종가(현재가)
        "vs": "1000",              // 전일대비
        "fltRt": "1.35",           // 등락률
        "mkp": "74500",            // 시가
        "hipr": "75500",           // 고가
        "lopr": "74000",           // 저가
        "trqu": "25367890"         // 거래량
      }]
    }
  }
}
```

## ⚠️ SSL 보안 관련 주의사항

### 개발 환경
- 한국 정부 API SSL 인증서 문제로 `verify=False` 사용
- `check_hostname=False`로 호스트명 검증 비활성화
- TLS 1.2 강제 사용으로 호환성 확보

### 프로덕션 환경
```python
# 프로덕션에서는 적절한 인증서 검증 고려
# 현재 설정은 한국 정부 API 호환성을 위한 임시 조치
```

## 🔍 문제 해결

### API 호출 실패
1. **API 키 확인**: `.env` 파일의 `STOCK_API_KEY` 점검
2. **네트워크 연결**: 정부 API 서버 연결 상태 확인
3. **사용량 한도**: API 일일/월별 호출 한도 확인

### SSL 오류
```bash
# 일반적인 SSL 오류는 자동 해결됨
# SSL 관련 로그가 나타나더라도 정상 동작
```

### 응답 형식 오류
- 정부 API는 JSON 요청에도 XML 반환할 수 있음
- 자동으로 형식을 감지하여 처리

## 📚 관련 문서

- [공공데이터포털 API 문서](https://www.data.go.kr/data/15094808/openapi.do)
- [Google ADK 가이드](https://cloud.google.com/adk)
- [메인 README.md](../README.md)

## 🏗️ 아키텍처

```
stock_analytics/
├── agent.py          # 메인 에이전트 정의
├── config.py         # 설정 및 환경변수
├── prompt.py         # AI 프롬프트 템플릿
├── ssl_adapter.py    # SSL 호환성 어댑터
├── ssl_api_tool.py   # SSL 호환 API 함수
├── stock_openapi.yml # OpenAPI 명세서
└── __init__.py       # 모듈 초기화
```

## ⭐ 난이도: 중급 (⭐⭐☆)

### 학습 포인트
- SSL/TLS 호환성 해결 패턴
- 정부 API 연동 모범사례  
- 커스텀 HTTP 어댑터 구현
- 실시간 금융 데이터 처리

---

💡 **팁**: 이 에이전트는 한국 금융 데이터의 특수성(SSL 문제)을 해결하는 실용적인 예제입니다. 다른 정부 API 연동 시에도 유사한 패턴을 활용할 수 있습니다.