# ECOS MCP Server

한국은행 경제통계시스템(ECOS) OpenAPI를 MCP 도구로 노출하는 서버. Gemini Enterprise의
**Custom MCP Server 데이터 스토어**가 소비할 수 있도록 StreamableHTTP 전송을 쓴다.

## 도구 (6개, 전부 조회 전용)

| 도구 | 설명 |
|---|---|
| `list_key_statistics` | 100대 주요 경제지표 최신값 (환율·기준금리·물가 등) |
| `search_statistic_tables` | 통계표를 이름으로 검색해 `stat_code`를 찾는다 |
| `list_statistic_items` | 통계표의 세부항목(`item_code`) 목록 |
| `get_statistic_series` | **핵심.** 시계열 데이터 조회 |
| `search_statistic_glossary` | 통계용어사전 |
| `get_statistic_metadata` | 통계 메타정보 |

전부 `readOnlyHint: true`라 Gemini Enterprise에서 확인 팝업 없이 호출된다.

전형적인 사용 흐름:
`search_statistic_tables` → `list_statistic_items` → `get_statistic_series`

## 배포

인프라는 `mcp/terraform/`이 관리한다.

```bash
cd ../terraform
./build.sh ecos-mcp   # 이미지 빌드 + 태그 기록
terraform apply       # 새 리비전 배포
```

`ECOS_API_KEY`는 Secret Manager에서 주입된다. 이미지에 굽지 않는다.

## 검증

```bash
URL=https://ecos-mcp-<PROJECT_NUMBER>.us-central1.run.app/mcp

# 공개 배포된 경우
bash ~/.claude/skills/gemini-enterprise-custom-mcp/scripts/probe_mcp_server.sh "$URL"

# 아직 비공개인 경우
bash ~/.claude/skills/gemini-enterprise-custom-mcp/scripts/probe_mcp_server.sh \
  "$URL" "$(gcloud auth print-identity-token)"
```

도구 6개가 나오면 Gemini Enterprise의 "Reload custom actions"도 같은 결과를 본다.

## Gemini Enterprise 데이터 스토어 연결

1. 데이터 스토어 → **Create data store** → **Custom MCP Server**
2. **Add MCP server** → 인증 **No auth**
3. MCP 서버 URL: `https://ecos-mcp-<PROJECT_NUMBER>.us-central1.run.app/mcp`
4. 위치·이름 지정 후 **Create**
5. 생성 후 **Actions → Reload custom actions → 액션 선택 → Enable actions**

> 5번은 건너뛰기 쉬운 필수 단계다. 데이터 스토어를 만들어도 도구는 하나도
> 켜져 있지 않다.

## 알려진 제약 2가지

**1. Host 헤더 (해결됨).** MCP SDK의 DNS 리바인딩 보호는 기본적으로 localhost
계열 Host만 허용한다. Cloud Run에 그대로 올리면 모든 요청이
`421 Invalid Host header`로 거부되고, Gemini Enterprise 쪽에서는 "도구 0개"로만
보여 원인을 찾기 어렵다. Cloud Run에서는 보호를 꺼서 해결했다 (아래 참고).

**2. 공개 접근 (미해결 — 조직 관리자 필요).** Gemini Enterprise가 이 엔드포인트에
도달하려면 Cloud Run 서비스가 공개여야 한다 (Private Service Connect 미지원).
현재 조직 정책 `constraints/iam.allowedPolicyMemberDomains`가 `allUsers` 바인딩을
막고 있어 배포는 되지만 외부에서 403이 난다.

```
ERROR: FAILED_PRECONDITION: One or more users named in the policy do not
belong to a permitted customer, perhaps due to an organization policy.
```

조직 관리자가 이 프로젝트를 예외로 추가해야 한다. 그 전까지는 인증 토큰으로만
호출 가능하며, 데이터 스토어 연결은 불가능하다.

## 참고

ECOS API의 실제 동작이 저장소의 `adk-finance-agent/ecos_analytics/ecos_final_openapi.yml`과
다른 부분이 있다. `StatisticTableList`는 이름 검색을 지원하지 않으며 검색어를 경로에
넣으면 `INFO-200`을 반환한다. 이 서버는 전체 목록 840건을 받아 서버 측에서
필터링한다.

ECOS는 오류를 HTTP 200과 함께 `{"RESULT": {"CODE": ..., "MESSAGE": ...}}` 형태로
돌려주므로 상태 코드만 검사하면 안 된다.
