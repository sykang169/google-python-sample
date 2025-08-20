# ECOS Analytics Agent

한국은행(BOK) 경제통계정보시스템(ECOS) Open API를 활용하여 경제통계 데이터를 조회하고 분석하는 Google ADK 기반 AI 에이전트입니다.

## 목차

- [개요](#개요)
- [주요 기능](#주요-기능)
- [기술 스택](#기술-스택)
- [설치 및 설정](#설치-및-설정)
- [사용법](#사용법)
- [API 엔드포인트](#api-엔드포인트)
- [아키텍처](#아키텍처)
- [통계 코드 가이드](#통계-코드-가이드)
- [예시](#예시)
- [트러블슈팅](#트러블슈팅)
- [라이선스](#라이선스)

## 개요

ECOS Analytics Agent는 Google ADK (Agent Development Kit)를 기반으로 구축된 한국 경제통계 전문 분석 에이전트입니다. 자연어 질의를 한국은행 ECOS API 호출로 변환하여 기준금리, 환율, 물가지수, GDP 등 핵심 경제통계 데이터를 실시간으로 조회하고 분석할 수 있습니다.

### 핵심 특징

- **Google ADK 통합**: Google의 Agent Development Kit을 활용한 최신 AI 에이전트 프레임워크
- **Gemini 2.5 Pro/Flash 모델**: 최신 Google Gemini 모델을 활용한 고성능 경제 데이터 분석
- **실시간 경제통계**: 한국은행 ECOS API를 통한 실시간 경제지표 조회
- **6개 API 엔드포인트 완벽 지원**: ECOS의 모든 주요 기능을 완벽 지원
- **기업 고유번호 통합**: DART 기업 데이터와의 완벽한 연동
- **스마트 날짜 처리**: 자연어 기간 표현을 자동으로 API 파라미터로 변환

## 주요 기능

### 1. 통계 데이터 조회 (StatisticSearch)
- 기준금리, 환율, 물가지수, GDP 등 핵심 경제지표
- 시계열 데이터 조회 및 트렌드 분석
- 사용자 지정 기간별 데이터 조회

### 2. 100대 통계지표 조회 (KeyStatisticList)
- 한국은행이 선정한 100대 핵심 경제통계
- 주요 경제지표 종합 현황
- 경제 전반의 빠른 파악

### 3. 통계용어사전 (StatisticWord)
- 경제통계 용어의 정확한 정의 제공
- 복잡한 경제개념의 쉬운 설명
- 사용자 친화적인 용어 해설

### 4. 통계표 목록 조회 (StatisticTableList)
- 이용 가능한 통계표 전체 목록
- 분야별 통계 데이터 분류
- 데이터 탐색 및 발견 기능

### 5. 통계항목 세부정보 (StatisticItemList)
- 특정 통계표의 상세 항목 정보
- 데이터 구조 및 분류 체계
- 통계 메타데이터 제공

### 6. 통계 메타데이터 (StatisticMeta)
- 통계 데이터의 출처 및 작성 방법
- 데이터 품질 정보
- 통계 작성 기관 정보

## 기술 스택

### Google ADK (Agent Development Kit)
- **LlmAgent**: 대화형 AI 에이전트 구현
- **OpenAPIToolset**: ECOS REST API 자동 도구화
- **FunctionTool**: 기업 코드 관리 함수의 에이전트 도구 변환
- **AuthCredential**: API 키 기반 인증 관리 (경로 파라미터 방식)

### Google Gemini Models
- **Gemini 2.5 Pro**: 복합적 경제 분석 및 평가 작업용 모델
- **Gemini 2.5 Flash**: 빠른 응답이 필요한 실시간 데이터 조회용 경량 모델
- **Vertex AI**: Google Cloud 기반 모델 호스팅

### 경제 데이터 처리
- **ECOS OpenAPI 3.0**: 한국은행 경제통계시스템 완벽 연동
- **기업 코드 통합**: DART 기업 데이터베이스와의 원활한 연동
- **날짜 처리 엔진**: 자연어 시간 표현의 자동 변환

## 설치 및 설정

### 1. 환경 변수 설정

`.env` 파일을 프로젝트 루트에 생성:

```bash
# ECOS API 설정 (필수)
ECOS_API_KEY=your_ecos_api_key_here

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
pip install requests python-dotenv
pip install sqlite3  # 기업 코드 저장소용
```

### 3. ECOS API 키 발급
1. [한국은행 ECOS](https://ecos.bok.or.kr) 접속
2. 사용자 등록 및 API 키 신청
3. 발급받은 API 키를 환경변수에 설정

## 사용법

### 기본 사용법

```python
from ecos_analytics import root_agent

# 자연어 질의를 통한 경제 데이터 조회
result = root_agent.run("올해 기준금리 변화 추이를 보여주세요")
print(result.data.get("ecos_result"))
```

### 구체적인 통계 데이터 조회

```python
# 기준금리 조회
result = root_agent.run("2024년 한국은행 기준금리 변화 추이")

# 환율 정보 조회  
result = root_agent.run("최근 3개월 원달러 환율")

# 물가지수 조회
result = root_agent.run("2024년 소비자물가지수 현황")
```

### 경제용어 및 지표 설명

```python
# 경제용어 설명
result = root_agent.run("소비자동향지수가 뭐야?")

# 100대 통계지표 조회
result = root_agent.run("주요 경제지표 현황 보여줘")
```

### 기업 연동 기능

```python
# 기업 정보와 경제지표 연계 분석
result = root_agent.run("삼성전자의 기업 코드를 찾아서 관련 경제통계가 있는지 확인해줘")
```

## API 엔드포인트

### 1. StatisticSearch - 통계 데이터 조회
```
/StatisticSearch/{auth_key}/{file_type}/{lang}/{start_count}/{end_count}/{stat_code}/{cycle}/{start_period}/{end_period}/{item_code1}
```

**주요 파라미터:**
- `stat_code`: 통계표 코드 (예: 722Y001 - 기준금리)
- `cycle`: 주기 (M: 월별, Q: 분기별, A: 연간)
- `start_period`, `end_period`: 조회 기간 (YYYYMM 형식)

### 2. KeyStatisticList - 100대 통계지표
```
/KeyStatisticList/{auth_key}/{file_type}/{lang}/{start_count}/{end_count}
```

### 3. StatisticWord - 통계용어사전
```
/StatisticWord/{auth_key}/{file_type}/{lang}/{start_count}/{end_count}/{word}
```

### 4. StatisticTableList - 통계표 목록
```
/StatisticTableList/{auth_key}/{file_type}/{lang}/{start_count}/{end_count}
```

### 5. StatisticItemList - 통계항목 세부정보
```
/StatisticItemList/{auth_key}/{file_type}/{lang}/{start_count}/{end_count}/{stat_code}
```

### 6. StatisticMeta - 통계 메타데이터
```
/StatisticMeta/{auth_key}/{file_type}/{lang}/{start_count}/{end_count}/{data_name}
```

## 아키텍처

### 모듈 구조

```
ecos_analytics/
├── __init__.py              # 모듈 진입점
├── agent.py                 # 메인 LlmAgent 정의 및 도구 통합
├── config.py                # Gemini 모델 설정 및 환경변수 관리
├── prompt.py                # ECOS 전문 프롬프트 엔지니어링
├── corpcode_manager.py      # 기업 코드 관리 (DART 연동)
├── ecos_final_openapi.yml   # ECOS OpenAPI 3.0 명세서
└── agent_corrected.py       # 백업/보정 에이전트
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
ECOS Open API + 기업코드DB
    ↓
Structured Economic Data
```

### 기업 코드 연동 시스템

```
ECOS Analytics ←→ DART Analytics
       ↓                ↓
   경제통계 API    ←→  기업 코드 DB
       ↓                ↓
    통합 분석        기업별 데이터
```

## 통계 코드 가이드

### 금리 (Interest Rates)
- **기준금리**: 722Y001 (item_code1: 0101000)
- **예금은행 대출금리**: 121Y001
- **CD(91일) 수익률**: 817Y002
- **국고채(3년) 수익률**: 817Y003
- **회사채(AA-, 3년) 수익률**: 817Y004

### 환율 (Exchange Rates)
- **원/달러 환율**: 731Y001
- **원/엔(100엔) 환율**: 731Y002
- **원/유로 환율**: 731Y003

### 물가 (Price Indices)
- **소비자물가지수(2020=100)**: 901Y009
- **생산자물가지수(2020=100)**: 404Y014
- **수출물가지수(2020=100)**: 401Y015
- **수입물가지수(2020=100)**: 402Y015

### 경제성장 (Economic Growth)
- **국내총생산(GDP, 계절조정)**: 200Y001
- **국내총생산(GDP, 원계열)**: 200Y002
- **산업생산지수(2020=100)**: 403Y001

### 통화금융 (Money & Finance)
- **통화량(M1, 평잔)**: 731Y004
- **통화량(M2, 평잔)**: 731Y005
- **예금은행 여신(원화)**: 103Y002

## 예시

### 1. 기준금리 조회

```python
# 자연어로 기준금리 조회
agent_response = root_agent.run("2024년 한국은행 기준금리 변화를 알려주세요")
print(agent_response.data.get("ecos_result"))
```

**출력:**
```
2024년 한국은행 기준금리 변화:
| 시점    | 기준금리 | 단위 |
|---------|----------|------|
| 2024.01 | 3.50     | %    |
| 2024.02 | 3.50     | %    |
| 2024.03 | 3.50     | %    |
...
```

### 2. 경제용어 설명

```python
# 경제용어 설명 요청
result = root_agent.run("소비자동향지수가 뭐예요?")
```

**출력:**
```
소비자동향지수는 소비자들이 느끼는 경기, 소비지출계획, 
향후 경제전망에 대한 인식을 종합하여 작성한 지수입니다.
100을 기준으로 그 이상이면 낙관, 미만이면 비관을 나타냅니다.
```

### 3. 100대 통계지표 조회

```python
# 주요 경제지표 조회
result = root_agent.run("현재 주요 경제지표 현황을 보여주세요")
```

### 4. 기업 연동 기능

```python
# 기업 코드와 경제지표 연계
result = root_agent.run("삼성전자의 기업 코드를 찾아주세요")
```

**출력:**
```
삼성전자의 기업 코드: 00126380
- 기업명: 삼성전자주식회사
- 종목코드: 005930
- 상장여부: 상장기업
```

## 트러블슈팅

### 1. Google ADK 관련 문제

**문제**: `ImportError: No module named 'google.adk'`

**해결책**:
```bash
pip install google-adk
# 또는
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

### 3. ECOS API 관련 문제

**문제**: API 호출 오류 또는 데이터 없음

**해결책**:
- ECOS API 키 재확인
- 통계 코드 유효성 검증
- 조회 기간 확인 (주말, 공휴일 제외)
- API 호출 제한 확인

### 4. 기업 코드 연동 문제

**문제**: 기업 코드 조회 실패

**해결책**:
```python
# DART 분석 모듈 상태 확인
from ecos_analytics.corpcode_manager import get_storage_statistics
stats = get_storage_statistics()
print(stats)
```

### 5. 날짜 처리 문제

**문제**: 기간 표현 인식 오류

**해결책**:
- 구체적인 날짜 형식 사용 (YYYY년 MM월)
- 영어 표현보다 한국어 표현 선호
- "최근", "올해", "작년" 등의 상대적 표현 활용

## 성능 최적화

### API 호출 최적화
```python
# 적절한 조회 범위 설정
# 너무 긴 기간은 응답 시간 증가
result = root_agent.run("최근 6개월 기준금리")  # 권장
# result = root_agent.run("최근 10년 기준금리")  # 비권장
```

### 캐싱 활용
```python
# 동일한 질의에 대한 캐싱 활용
# 기업 코드는 자동으로 캐싱됨
```

## 모니터링 및 로깅

### API 호출 상태 확인
```python
# OpenAPI 도구 상태 확인
from ecos_analytics import root_agent
print(f"도구 개수: {len(root_agent.tools)}")
for tool in root_agent.tools:
    print(f"- {tool}")
```

### 응답 시간 모니터링
```python
import time
start_time = time.time()
result = root_agent.run("기준금리 조회")
end_time = time.time()
print(f"응답 시간: {end_time - start_time:.2f}초")
```

## 보안 고려사항

### API 키 관리
- 환경변수를 통한 안전한 API 키 저장
- `.env` 파일의 버전 관리 제외 (`.gitignore` 추가)
- API 키의 정기적 갱신 권장

### 데이터 보안
- HTTPS를 통한 모든 API 통신
- 민감한 경제 데이터의 적절한 처리
- 로그에서 API 키 자동 마스킹

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
- **ECOS API 관련**: [한국은행 ECOS](https://ecos.bok.or.kr)
- **이슈 리포팅**: GitHub Issues

## 관련 프로젝트

- **DART Analytics Agent**: 기업 공시 및 재무 데이터 분석 (연동 모듈)
- **Google ADK**: Google의 공식 Agent Development Kit

---

**ECOS Analytics Agent**는 Google ADK와 Gemini의 강력한 AI 능력을 활용하여 한국의 핵심 경제통계를 실시간으로 분석할 수 있는 전문적인 경제 AI 에이전트입니다. 기준금리부터 GDP까지, 복잡한 경제 데이터를 자연어로 쉽게 조회하고 분석할 수 있습니다.