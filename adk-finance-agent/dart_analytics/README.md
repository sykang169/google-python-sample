# DART Analytics Agent

한국 금융감독원 전자공시시스템(DART) Open API를 활용하여 기업 공시 및 재무 데이터를 분석하는 Google ADK 기반 AI 에이전트입니다.

## 목차

- [개요](#개요)
- [주요 기능](#주요-기능)
- [기술 스택](#기술-스택)
- [설치 및 설정](#설치-및-설정)
- [사용법](#사용법)
- [API 그룹별 기능](#api-그룹별-기능)
- [아키텍처](#아키텍처)
- [성능 최적화](#성능-최적화)
- [예시](#예시)
- [트러블슈팅](#트러블슈팅)
- [라이선스](#라이선스)

## 개요

DART Analytics Agent는 Google ADK (Agent Development Kit)를 기반으로 구축된 지능형 금융 데이터 분석 에이전트입니다. 자연어 질의를 DART API 호출로 변환하여 한국 상장기업의 다양한 공시 및 재무 정보를 조회하고 분석할 수 있습니다.

### 핵심 특징

- **Google ADK 통합**: Google의 Agent Development Kit을 활용한 고도화된 AI 에이전트 프레임워크
- **Gemini 2.5 Pro/Flash 모델**: 최신 Google Gemini 모델을 활용한 고성능 자연어 처리
- **고성능 데이터 캐싱**: SQLite 기반의 고속 기업 코드 검색 시스템 (1ms 미만 응답속도)
- **자동화된 문서 처리**: ZIP 파일 자동 다운로드, 압축해제, 분석
- **포괄적 API 지원**: DART의 모든 주요 API 엔드포인트 완벽 지원

## 주요 기능

### 1. 공시정보 조회 (DS001)
- 기업개황 조회
- 공시검색 및 필터링
- 고유번호 관리
- 공시서류 원본 다운로드 및 분석

### 2. 사업보고서 주요정보 (DS002)
- 배당정보, 임원현황, 직원현황
- 최대주주현황, 임원보수현황
- 기타 15개 상세 정보 엔드포인트

### 3. 상장기업 재무정보 (DS003)
- 단일/다중회사 주요계정
- 재무비율 분석
- 현금흐름표
- XBRL 재무제표 처리

### 4. 지분공시 (DS004/DS005)
- 대량보유 현황
- 임원소유 현황
- 상세 지분공시 정보

### 5. 증권신고서 정보 (DS006)
- 지분증권 신고
- 채무증권 신고

## 기술 스택

### Google ADK (Agent Development Kit)
- **LlmAgent**: 대화형 AI 에이전트 구현
- **OpenAPIToolset**: REST API 자동 도구화
- **FunctionTool**: 커스텀 함수를 에이전트 도구로 변환
- **AuthCredential**: API 키 기반 인증 관리

### Google Gemini Models
- **Gemini 2.5 Pro**: 복합적 분석 및 평가 작업용 모델
- **Gemini 2.5 Flash**: 빠른 응답이 필요한 작업용 경량 모델
- **Vertex AI**: Google Cloud 기반 모델 호스팅

### 데이터 처리 및 캐싱
- **SQLite**: 고성능 기업 코드 저장소
- **XML/XBRL 파싱**: BeautifulSoup, lxml을 활용한 문서 처리
- **압축 파일 처리**: 자동 ZIP 다운로드 및 압축해제

## 설치 및 설정

### 1. 환경 변수 설정

`.env` 파일을 프로젝트 루트에 생성:

```bash
# DART API 설정 (필수)
DART_API_KEY=your_dart_api_key_here

# Google Cloud 설정 (Vertex AI 사용 시)
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=global
GOOGLE_GENAI_USE_VERTEXAI=True

# 또는 AI Studio 사용 시
GOOGLE_GENAI_USE_VERTEXAI=False
GOOGLE_API_KEY=your_google_ai_studio_api_key
```

### 2. 필수 의존성 설치

```bash
pip install google-adk
pip install requests beautifulsoup4 lxml
pip install python-dotenv
```

### 3. DART API 키 발급
1. [DART 홈페이지](https://opendart.fss.or.kr) 접속
2. 사용자 등록 및 API 키 신청
3. 발급받은 40자리 API 키를 환경변수에 설정

## 사용법

### 기본 사용법

```python
from dart_analytics import root_agent

# 자연어 질의를 통한 데이터 조회
result = root_agent.run("삼성전자의 2023년 배당 정보를 알려주세요")
print(result.data.get("dart_result"))
```

### 직접 함수 호출

```python
from dart_analytics.sub_functions import utils

# 기업 코드 조회
corp_code = utils.get_corp_code("삼성전자")
print(f"삼성전자 코드: {corp_code}")  # 00126380

# 기업 검색
companies = utils.search_corporations("전자", limit=5)
for company in companies:
    print(f"{company['corp_name']}: {company['corp_code']}")
```

### XBRL 재무제표 처리

```python
from dart_analytics.sub_functions.xbrl_processor import download_xbrl_financial_statement

# 2023년 사업보고서 XBRL 다운로드
result = download_xbrl_financial_statement(
    rcept_no="20240401004781",  # 삼성전자 2023년 사업보고서
    reprt_code="11011"  # 사업보고서
)
print(result)
```

## API 그룹별 기능

### DS001: 공시정보
- `get_corp_code()` - 기업 고유번호 조회
- `get_company_json()` - 기업개황
- `search_disclosure_json()` - 공시검색
- `get_document()` - 공시서류 원본 다운로드

### DS002: 사업보고서 주요정보
- `get_dvdnd_json()` - 배당정보
- `get_exctv_sttus_json()` - 임원현황
- `get_emp_sttus_json()` - 직원현황
- `get_hyslr_sttus_json()` - 최대주주현황
- `get_hmv_audit_json()` - 임원보수현황

### DS003: 상장기업 재무정보
- `get_fnltt_singl_acnt_json()` - 단일회사 주요계정
- `get_fnltt_multi_acnt_json()` - 다중회사 주요계정
- `get_fnltt_singl_indx_json()` - 재무비율
- `get_cash_flow_json()` - 현금흐름표
- `get_fnltt_xbrl()` - XBRL 재무제표

## 아키텍처

### 모듈 구조

```
dart_analytics/
├── __init__.py              # 모듈 진입점 (Google ADK 조건부 import)
├── agent.py                 # 메인 LlmAgent 정의 및 도구 통합
├── config.py                # Gemini 모델 설정 및 환경변수 관리
├── prompt.py                # DART 전문 프롬프트 엔지니어링
├── dart_openapi_full_specification.yml  # OpenAPI 3.0 명세서
├── CORPCODE.xml             # 기업 코드 데이터 (자동 생성)
├── CORPCODE.zip             # 압축된 원본 파일
├── storage/                 # 고성능 캐싱 시스템
│   ├── corpcode.db         # SQLite 데이터베이스
│   ├── corpcode_cache.pkl  # 메모리 캐시
│   └── corpcode_index.json # 빠른 검색 인덱스
└── sub_functions/          # 핵심 기능 모듈
    ├── utils.py            # 공통 유틸리티 및 기업 코드 관리
    ├── corpcode_storage.py # 고성능 기업 코드 저장소
    ├── document_analyzer.py # 공시서류 분석 및 파싱
    ├── xbrl_processor.py   # XBRL 재무제표 처리
    ├── file_handlers.py    # 파일 다운로드 및 압축 처리
    └── dart_zip_processor.py # ZIP 파일 전용 처리기
```

### Google ADK 통합 아키텍처

```
User Query (자연어)
    ↓
Google Gemini 2.5 Pro/Flash
    ↓
LlmAgent (Google ADK)
    ↓
OpenAPIToolset + FunctionTool
    ↓
DART Open API + 로컬 캐시
    ↓
Structured Response
```

## 성능 최적화

### 1. 고성능 기업 코드 캐싱

```python
# SQLite + 메모리 캐싱으로 1ms 미만 응답 속도
@lru_cache(maxsize=1000)
def get_corp_code(corp_name: str) -> Optional[str]:
    # 캐시 우선 검색 → DB 검색 → API 폴백
```

### 2. 자동화된 데이터 관리

- **자동 다운로드**: CORPCODE.xml 없을 시 자동 다운로드
- **지능형 캐싱**: 자주 사용되는 데이터 우선 캐시
- **세션 추적**: 검색 패턴 분석 및 최적화

### 3. 스마트 폴백 시스템

```python
def get_corp_code(corp_name: str) -> Optional[str]:
    # 1. 고성능 저장소 우선 검색
    # 2. XML 파싱 폴백
    # 3. 자동 다운로드 및 재시도
```

## 예시

### 1. 기본 질의

```python
# 자연어로 배당 정보 질의
agent_response = root_agent.run(
    "네이버의 2023년 배당금과 배당수익률을 알려주세요"
)
print(agent_response.data.get("dart_result"))
```

**출력:**
```
네이버(035420)의 2023년 배당 정보:
- 주당 배당금: 334원
- 배당수익률: 1.8%
- 배당 기준일: 2023-12-29
```

### 2. 재무제표 분석

```python
# XBRL 재무제표 다운로드 및 분석
result = root_agent.run(
    "삼성전자의 2023년 연결재무제표에서 매출액과 영업이익을 추출해주세요"
)
```

### 3. 기업 검색 및 비교

```python
# 여러 기업 비교 분석
result = root_agent.run(
    "반도체 관련 기업들의 2023년 R&D 투자 현황을 비교해주세요"
)
```

## 트러블슈팅

### 1. Google ADK 관련 문제

**문제**: `ImportError: No module named 'google.adk'`

**해결책**:
```bash
pip install google-adk
# 또는 개발 버전
pip install git+https://github.com/google/adk-python.git
```

### 2. Gemini API 인증 문제

**문제**: `Authentication failed`

**해결책**:
```bash
# Vertex AI 사용 시
gcloud auth application-default login
export GOOGLE_CLOUD_PROJECT=your-project-id

# AI Studio 사용 시
export GOOGLE_API_KEY=your-api-key
export GOOGLE_GENAI_USE_VERTEXAI=False
```

### 3. DART API 관련 문제

**문제**: `status: "013"` (API 키 오류)

**해결책**:
- DART API 키 재확인
- 환경변수 DART_API_KEY 설정 확인
- API 키 유효성 검증

### 4. 데이터 없음 오류

**문제**: 조회 결과가 없음

**해결책**:
```python
# 기업 코드 수동 갱신
from dart_analytics.sub_functions.utils import refresh_corpcode_data
refresh_corpcode_data()
```

### 5. 성능 최적화

**메모리 사용량 최적화**:
```python
# 캐시 정리
from dart_analytics.sub_functions.corpcode_storage import get_storage
storage = get_storage()
storage.clear_cache()
```

## 모니터링 및 통계

### 저장소 통계 확인

```python
from dart_analytics.sub_functions.utils import get_corpcode_file_info

# 파일 및 캐시 상태 확인
info = get_corpcode_file_info()
print(info)
```

**출력 예시:**
```
CORPCODE 파일 정보:
• CORPCODE.xml: 5.2MB, 112,869개 기업
• 캐시 적중률: 95.3%
• 평균 검색 시간: 0.8ms
```

## 보안 고려사항

### API 키 관리
- 환경변수를 통한 안전한 API 키 저장
- `.env` 파일의 버전 관리 제외 (`.gitignore` 추가)
- 로그에서 API 키 자동 마스킹

### 데이터 보안
- 로컬 캐시 암호화 옵션
- HTTPS를 통한 모든 API 통신
- 개인정보 필터링

## 라이선스

```
Copyright 2025 Google LLC

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
```

## 기여 방법

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/new-feature`)
3. Commit your changes (`git commit -am 'Add new feature'`)
4. Push to the branch (`git push origin feature/new-feature`)
5. Create a Pull Request

## 지원 및 문의

- **Google ADK 관련**: [Google ADK Documentation](https://developers.google.com/adk)
- **DART API 관련**: [DART Open API](https://opendart.fss.or.kr)
- **이슈 리포팅**: GitHub Issues

---

**DART Analytics Agent**는 Google ADK와 Gemini의 강력한 AI 능력을 활용하여 한국 금융 시장의 복잡한 데이터를 쉽고 빠르게 분석할 수 있는 차세대 금융 AI 에이전트입니다.