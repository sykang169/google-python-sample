# ADK Finance Agent 샘플

Google ADK (Agent Development Kit)를 활용한 한국 금융 데이터 분석 AI 에이전트 예제 컬렉션입니다. DART(금융감독원)와 ECOS(한국은행) 데이터를 활용한 다양한 AI 에이전트 패턴을 학습할 수 있습니다.

![Demo](./assets/dart_demo.gif)

> ⚠️ **학습 목적**: 이 모든 에이전트는 **Google ADK 학습과 실험을 위한 샘플**입니다. 실제 금융 자문이나 투자 결정에 사용하지 마세요.

## 🎯 목표

- **Google ADK 패턴 학습**: 다양한 에이전트 아키텍처 패턴 체험
- **한국 API 통합**: DART/ECOS와 같은 실제 API 연동 방법 습득  
- **멀티모달 에이전트**: 단일/멀티 에이전트 시스템 비교 학습
- **프롬프트 엔지니어링**: 도메인 특화 프롬프트 작성 기법

## 🤖 에이전트 카탈로그

| 에이전트 | 설명 | 아키텍처 | 난이도 | 주요 기술 | 시작하기 |
|----------|------|----------|--------|-----------|----------|
| **[DART Analytics](./dart_analytics/)** | 한국 기업 공시 데이터 분석 | 단일 에이전트 | ⭐⭐⭐ | DART API, XBRL, SQLite | [📖 가이드](./dart_analytics/README.md) |
| **[ECOS Analytics](./ecos_analytics/)** | 한국은행 경제통계 분석 | 단일 에이전트 | ⭐⭐☆ | ECOS API, 시계열 분석 | [📖 가이드](./ecos_analytics/README.md) |
| **[Stock Analytics](./stock_analytics/)** | 금융위원회 주식시세 분석 | 단일 에이전트 | ⭐⭐☆ | Stock API, SSL 호환성 | [📖 가이드](./stock_analytics/README.md) |
| **[Financial Advisor](./financial_advisor/)** | 멀티 에이전트 금융 자문 | 멀티 에이전트 | ⭐⭐⭐⭐ | Google Search, AgentTool | [📖 가이드](./financial_advisor/README.md) |

### 🔧 기술 스택 비교

| 기술 요소 | DART Analytics | ECOS Analytics | Stock Analytics | Financial Advisor |
|-----------|----------------|----------------|-----------------|-------------------|
| **Gemini 모델** | 2.5-pro, 2.5-flash | 2.5-pro | 2.5-flash | 2.5-pro |
| **데이터 소스** | 금융감독원 API | 한국은행 API | 금융위원회 API | Google Search |
| **캐싱 전략** | SQLite + 메모리 | 기본 캐싱 | 없음 | 상태 관리 |
| **문서 처리** | XBRL, XML, ZIP | JSON | JSON/XML | 없음 |
| **특수 기술** | XBRL 파싱 | 통계 분석 | SSL 호환성 | 멀티 에이전트 |
| **에이전트 수** | 1개 | 1개 | 1개 | 5개 (1+4) |

## 🚀 빠른 시작

### 1. 환경 설정
```bash
# 가상환경 생성
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt

# 환경변수 설정
cp .env.example .env
# .env 파일에 API 키 입력
```

### 2. ADK Web UI 실행 (권장)
```bash
adk web
# 브라우저에서 http://localhost:8000 열림
```

### 3. 특정 에이전트 실행
```bash
# DART 에이전트
adk run dart_analytics

# ECOS 에이전트  
adk run ecos_analytics

# Stock 에이전트
adk run stock_analytics

# Financial Advisor (멀티 에이전트)
adk run financial_advisor
```

## 📋 필수 API 키

| API | 설명 | 발급처 | 필수 여부 |
|-----|------|--------|-----------|
| **DART API** | 한국 기업 공시 데이터 | [DART 홈페이지](https://opendart.fss.or.kr) | DART/Financial Advisor |
| **ECOS API** | 한국은행 경제통계 | [ECOS 홈페이지](https://ecos.bok.or.kr) | ECOS |
| **STOCK API** | 금융위원회 주식시세 | [공공데이터포털](https://www.data.go.kr/data/15094808/openapi.do) | Stock Analytics |
| **Google AI** | Gemini 모델 사용 | [AI Studio](https://aistudio.google.com) | 모든 에이전트 |

## 📚 학습 경로 추천

### 🥉 초급자
1. **[ECOS Analytics](./ecos_analytics/)** - 가장 간단한 단일 에이전트 패턴
2. 기본적인 프롬프트 엔지니어링 학습
3. OpenAPI 도구 통합 방식 이해

### 🥈 중급자  
1. **[DART Analytics](./dart_analytics/)** - 복잡한 데이터 처리와 캐싱
2. XBRL, XML 문서 처리 패턴 학습
3. 고성능 데이터 저장소 설계

### 🥇 고급자
1. **[Financial Advisor](./financial_advisor/)** - 멀티 에이전트 시스템 아키텍처
2. 에이전트 간 상태 전달 메커니즘
3. 코디네이터 패턴과 전문화된 서브 에이전트 설계

## ⚠️ 중요 주의사항

### 🔒 보안
- **API 키 보호**: `.env` 파일을 git에 커밋하지 마세요
- **민감 데이터**: 실제 개인정보나 민감한 금융 정보 사용 금지
- **사용량 모니터링**: API 호출 비용과 한도 주의

### 📖 학습 목적
- **샘플 코드**: 모든 코드는 학습/실험용입니다  
- **금융 자문 아님**: 실제 투자나 금융 결정에 사용 금지
- **정확성 보장 없음**: AI 생성 정보의 정확성을 보장하지 않습니다

### 🛠️ 기술적 제한
- **DART API 한도**: 일 10,000회 호출 제한
- **ECOS API 한도**: 분당 호출 횟수 제한 있음
- **Gemini 모델**: 사용량에 따른 과금 발생 가능

## 🔧 주요 기술

### Google ADK 기능 활용
- **LlmAgent**: 대화형 AI 에이전트 구현
- **OpenAPIToolset**: API 명세 자동 도구화
- **AgentTool**: 멀티 에이전트 조율
- **Google Search**: 실시간 정보 검색 통합

### 한국 금융 데이터 특화
- **DART API**: 12만+ 기업 공시 데이터 처리
- **XBRL 파싱**: 재무제표 자동 분석
- **경제통계**: 한국은행 100대 통계지표 활용
- **SQLite 캐싱**: 고성능 로컬 데이터 저장

## 📄 라이선스

```
Apache License 2.0 - 학습 및 실험용

이 샘플들은 Google ADK 학습 목적으로 제작되었습니다.
실제 금융 서비스나 자문에는 사용하지 마세요.
```

---

**💡 각 에이전트의 상세한 사용법과 기술 문서는 해당 폴더의 README.md를 확인하세요!**

각 에이전트마다 다른 패턴과 복잡도를 가지고 있어, Google ADK의 다양한 기능을 단계별로 학습할 수 있도록 설계되었습니다.