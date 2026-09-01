# DART MCP Server

금융감독원 전자공시(OPEN DART) API **82개**를 **4개 도구**로 노출하는 MCP 서버.
Gemini Enterprise의 Custom MCP Server 데이터 스토어가 소비할 수 있도록
StreamableHTTP 전송을 쓴다.

## 왜 82개를 그대로 노출하지 않는가

실측한 값이다. MCP 도구는 `tools/list` 응답이 매 요청 컨텍스트에 들어간다.

| 구성 | tools/list 크기 |
|---|---|
| 82개 flat | 약 74,000자 ≈ **37,000 토큰** |
| 4개 (이 서버) | 약 4,000자 ≈ **2,000 토큰** |

에이전트가 MCP 서버를 여러 개 붙이면 82개짜리 하나가 예산을 다 먹는다.
Gemini Enterprise의 액션 상한(100개)에도 위험하게 붙는다.

## 도구 4개

```
resolve_company(name)              회사명 → corp_code   (내장 인덱스, 외부 호출 없음)
search_dart_apis(query, group)     82개 카탈로그 검색 → 엔드포인트 + 파라미터 명세
call_dart_api(endpoint, params)    결정론적 실행
ask_dart(question, corp_name)      내부 Gemini가 엔드포인트를 골라 실행 (선택)
```

**기본 흐름은 앞의 3개**다. 판단을 호출하는 에이전트가 하므로 결정론적이고
디버깅이 쉽다:

```
resolve_company("삼성전자")        → 00126380
search_dart_apis("배당")           → alotMatter + 필요한 파라미터
call_dart_api("alotMatter", {...}) → 데이터
```

`ask_dart`는 "배당"이 `alotMatter`인지 `stockTotqySttus`인지 같은 도메인 지식이
필요할 때 쓰는 편의 도구다. **선택한 엔드포인트와 파라미터(`routed`)를 데이터와
함께 반환**하므로 무엇이 호출됐는지 추적할 수 있다. 결정론이 필요한 배포에서는
`DART_ENABLE_ASK=0`으로 끈다.

실측 라우팅 결과:

| 질문 | 선택된 엔드포인트 |
|---|---|
| 삼성전자 2025년 배당 현황 | `alotMatter` |
| 카카오 임원 현황 | `exctvSttus` |
| 네이버 최대주주 | `hyslrSttus` |
| 삼성전자 연결 재무제표 전체 계정과목 | `fnlttSinglAcntAll` (`fs_div=CFS`까지 채움) |
| 셀트리온 합병 결정 공시 | `cmpMgDecsn` (기간형이라 `bgn_de/end_de`로 전환) |

## 이미지에 굽는 자산

`assets/`의 두 파일은 **런타임에 만들 수 없어서** 빌드 시점에 굽는다.

| 파일 | 내용 | 크기 |
|---|---|---|
| `catalog.json` | 82개 엔드포인트의 파라미터 명세 | 90KB |
| `corp_index.json.gz` | 회사명 → corp_code (118,819건, 상장 3,988) | 1.4MB |

`corpCode.xml` 다운로드는 **실측 229초**가 걸린다. Cloud Run 요청 타임아웃(300초)에
육박해서 콜드 스타트마다 받을 수 없다.

갱신이 필요하면 (DART가 엔드포인트를 추가하거나 신규 법인이 늘었을 때):

```bash
python build_assets.py              # 둘 다
python build_assets.py --catalog    # 카탈로그만 (빠름)
python build_assets.py --corp       # 회사 인덱스만 (약 4분)
cd ../terraform && ./build.sh dart-mcp && terraform apply
```

## 배포

인프라는 `mcp/terraform/`이 관리한다.

```bash
cd ../terraform
./build.sh dart-mcp   # 이미지 빌드 + 태그 기록
terraform apply       # 새 리비전 배포
```

`DART_API_KEY`는 Secret Manager에서 주입되며 이미지에 굽지 않는다.
`ask_dart`가 Gemini를 부르므로 런타임 SA에 `roles/aiplatform.user`가 필요하다
(Terraform이 `google_project_iam_member.vertex_ai`로 부여한다).

## 검증

```bash
URL=https://dart-mcp-<PROJECT_NUMBER>.us-central1.run.app/mcp

bash ~/.claude/skills/gemini-enterprise-custom-mcp/scripts/probe_mcp_server.sh "$URL"
# 비공개 상태면 토큰을 함께 준다
bash ~/.claude/skills/gemini-enterprise-custom-mcp/scripts/probe_mcp_server.sh \
  "$URL" "$(gcloud auth print-identity-token)"
```

## 환경변수

| 변수 | 기본 | 설명 |
|---|---|---|
| `DART_API_KEY` | — | 필수. Secret Manager에서 주입 |
| `MCP_ALLOWED_HOSTS` | (비움) | 허용 Host 목록. Cloud Run에서는 비워 둔다 (아래 참고) |
| `DART_ENABLE_ASK` | `1` | `0`이면 `ask_dart` 비활성화 |
| `DART_ROUTER_MODEL` | `gemini-2.5-flash` | `ask_dart`가 쓰는 모델 |
| `GOOGLE_CLOUD_PROJECT` / `GOOGLE_CLOUD_LOCATION` | — | `ask_dart`의 Vertex AI 호출용 |

## 알려진 제약 2가지

**1. Host 헤더 (해결됨).** MCP SDK의 DNS 리바인딩 보호가 기본적으로 localhost
계열 Host만 허용한다. Cloud Run에 그대로 올리면 모든 요청이 `421 Invalid Host
header`로 거부되는데, Gemini Enterprise 쪽에서는 "도구 0개"로만 보여 원인을 찾기
어렵다. Cloud Run에서는 보호를 꺼서 해결했다 (아래 참고).

> ⚠️ **Cloud Run 호스트명은 2개다.** `<service>-<project_number>.<region>.run.app`과
> canonical `<service>-<hash>-<region>.a.run.app`이 모두 서비스된다. 해시는 생성 전에
> 알 수 없어 `MCP_ALLOWED_HOSTS`에 미리 넣을 수 없고, 한쪽만 넣으면 다른 쪽으로 온
> 요청이 `421`로 거부된다. 그래서 Cloud Run에서는 `MCP_ALLOWED_HOSTS`를 비워
> DNS 리바인딩 보호를 끈다(서버가 `K_SERVICE`를 보고 자동 처리).


**2. 공개 접근 (미해결 — 조직 관리자 필요).** Gemini Enterprise가 도달하려면
Cloud Run 서비스가 공개여야 한다 (Private Service Connect 미지원). 조직 정책
`constraints/iam.allowedPolicyMemberDomains`가 `allUsers` 바인딩을 막고 있어
배포는 되지만 외부에서 403이 난다. 조직 관리자가 이 프로젝트를 예외로 추가해야 한다.

## 저장소의 기존 OpenAPI 명세에 대한 경고

`adk-finance-agent/dart_analytics/dart_openapi_full_specification.yml`은
**신뢰할 수 없다.** 삼성전자로 42개 JSON 경로를 전수 실호출한 결과:

- **19개가 존재하지 않는 엔드포인트** (`dvdnd`, `cashFlow`, `krx`, `shrs`,
  `fnlttAuditr`, `adtAllSttus`, `outcmpnyDrctr`, `hmvAudit` 등 → 전부 `status=101`)
- **59개를 누락** (`stockTotqySttus`, `fnlttCmpnyIndx`, `xbrlTaxonomy`,
  2026년 신규 `hmvAuditIndvdlBySttusV2`/`indvdlByPayV2` 등)
- 라벨 오류: `alotMatter`를 "주식총수현황"이라 적었으나 실제로는 **배당에 관한 사항**

이 서버의 `assets/catalog.json`은 그 파일이 아니라
**opendart 공식 개발가이드(`opendart.fss.or.kr/guide/`)에서 직접 수집**한 것이다.
