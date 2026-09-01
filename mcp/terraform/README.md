# MCP 서버 인프라 (Terraform)

`mcp/` 아래 MCP 서버 4종을 Cloud Run에 배포하고 Gemini Enterprise에 연결한다.
**신규 프로젝트에서 처음부터 세울 수 있게** 구성돼 있다.

| 서비스 | 소스 | 도구 | API 키 |
|---|---|---|---|
| `ecos-mcp` | `../ecos-mcp-server` | 6 | 한국은행 ECOS |
| `dart-mcp` | `../dart-mcp-server` | 4 (82개 API 커버) | 금감원 OPEN DART |
| `stock-mcp` | `../stock-mcp-server` | 4 | 공공데이터포털 주식시세 |
| `finlife-mcp` | `../finlife-mcp-server` | 6 | 금감원 금융상품통합비교공시 |

---

## 처음부터 배포하기

### 1. API 키를 Secret Manager에

```bash
cp .env.example .env
vi .env                      # 실제 키 입력 (.gitignore에 있음)
set -a && . ./.env && set +a
./setup_keys.sh --apply      # Secret Manager에 생성/갱신
```

| 환경변수 | 시크릿 | 발급처 |
|---|---|---|
| `TF_VAR_ecos_api_key` | `ECOS_API_KEY` | ecos.bok.or.kr |
| `TF_VAR_dart_api_key` | `DART_API_KEY` | opendart.fss.or.kr |
| `TF_VAR_stock_api_key` | `STOCK_API_KEY` | data.go.kr |
| `TF_VAR_finlife_api_key` | `FINLIFE_API_KEY` | finlife.fss.or.kr |

> **키는 Terraform이 관리하지 않는다.** Terraform이 시크릿 값을 만들면 tfstate에
> 평문으로 저장되기 때문이다. `setup_keys.sh`가 Terraform 밖에서 Secret Manager에
> 넣고, Terraform은 존재를 확인한 뒤 IAM만 건다. **키가 tfstate에 남을 일이 없다.**

`--apply` 없이 실행하면 아무것도 바꾸지 않고 현재 상태만 점검한다:

```bash
./setup_keys.sh
#   OK  ECOS_API_KEY  존재 (최신 버전 1)
#   ...
```

값이 기존과 같으면 새 버전을 만들지 않으므로 여러 번 실행해도 안전하다.

### 2. 프로젝트 지정

```bash
cp terraform.tfvars.example terraform.tfvars
vi terraform.tfvars          # project_id 입력
```

### 3. init (백엔드는 부분 구성)

```bash
terraform init \
  -backend-config="bucket=MY-TFSTATE-BUCKET" \
  -backend-config="prefix=mcp-servers"
```

state 버킷이 없으면 먼저 만든다:

```bash
gcloud storage buckets create gs://MY-TFSTATE-BUCKET --location=US
gcloud storage buckets update gs://MY-TFSTATE-BUCKET --versioning
```

로컬 state로 시작하려면 `versions.tf`의 `backend "gcs" {}`를 주석 처리한다.

### 4. 이미지 저장소 먼저, 그다음 빌드, 그다음 전체

```bash
terraform apply -target=google_artifact_registry_repository.mcp
cd ../dart-mcp-server && python build_assets.py && cd ../terraform   # dart 전용 자산
./build.sh
terraform apply
```

`build.sh`는 타임스탬프 태그로 이미지를 올리고 `image.auto.tfvars`에 기록한다.
태그를 `latest`로 두면 Terraform이 변경을 감지하지 못해 새 리비전이 생기지 않으므로
이 방식을 쓴다.

### 5. Gemini Enterprise 연결

```bash
./connect_ge.sh            # 데이터 커넥터 4개 생성
./connect_ge.sh --status   # 상태 확인
```

그다음 콘솔에서 데이터 스토어마다:

```
Gemini Enterprise → 데이터 스토어 → 해당 항목 → Actions
  → Reload custom actions      (MCP 서버에 tools/list 호출)
  → 도구 선택 → Enable actions
```

**Reload를 누르기 전에는 도구 목록이 비어 있는 것이 정상이다.**

---

## ⭐ Cloud Run을 공개할 필요가 없다

문서만 보면 GE 연동에 공개 엔드포인트가 필수처럼 읽히지만(Private Service Connect
미지원 언급 때문에 더욱), **실측 결과 그렇지 않다.**

Gemini Enterprise는 다음 신원으로 MCP 엔드포인트를 호출한다:

```
service-<PROJECT_NUMBER>@gcp-sa-discoveryengine.iam.gserviceaccount.com
```

이 서비스 에이전트에 `roles/run.invoker`만 주면 **비공개 Cloud Run에서도
`tools/list`가 정상 동작한다.** `grant_gemini_enterprise_access = true`(기본값)가
이 바인딩을 건다.

의미하는 바:

- `allUsers` 공개가 **불필요** → API 키 할당량 무단 소진 위험 없음
- Domain restricted sharing(`iam.allowedPolicyMemberDomains`)을 **건드릴 필요 없음**
  — 서비스 에이전트는 조직 내부 주체라 DRS에 걸리지 않는다
- VPC / PSC network attachment / Cloud NAT **전부 불필요**

`public_access` 변수는 GE 외의 공개 클라이언트에도 열어야 할 때만 쓴다.

---

## 조직 정책

Custom MCP 데이터 스토어 생성은 기본적으로 차단돼 있다:

```
constraints/discoveryengine.managed.disableCustomMcpServerConnector   기본 enforce
```

`roles/orgpolicy.policyAdmin`이 있으면 Terraform이 해제할 수 있다:

```hcl
disable_custom_mcp_org_policy_override = true
```

권한이 없으면 `false`로 두고 조직 관리자에게 요청한다. **정책 전파에 약 2분이
걸리므로** 해제 직후 실패했다고 설정이 잘못됐다고 판단하지 말 것.

---

## 데이터 커넥터 페이로드 (문서 미공개)

`connect_ge.sh`가 쓰는 형태다. Terraform 프로바이더에 리소스가 없고 gcloud에도
`discovery-engine` 명령군이 없어 REST로만 만들 수 있다. 네 가지가 전부 필요하며
하나라도 빠지면 실패한다:

```json
{
  "dataConnector": {
    "dataSource": "custom_mcp",
    "refreshInterval": "86400s",
    "connectorModes": ["FEDERATED"],
    "params": { "oauth_access_token": "" },
    "entities": [{ "entityName": "mcp_data" }],
    "actionConfig": {
      "createBapConnection": true,
      "actionParams": {
        "instance_uri": "https://<host>/mcp",
        "auth_type": "NO_AUTH",
        "mcp_server_source": "BYO_MCP",
        "use_agent_gateway_egress": false
      }
    }
  }
}
```

| 항목 | 빠뜨리면 |
|---|---|
| `connectorModes: ["FEDERATED"]` | `connectorType`이 `THIRD_PARTY`가 되어 데이터 수집 파이프라인을 돌리려다 `INITIALIZATION_FAILED` |
| `params.oauth_access_token: ""` | `Missing Parameter Private App Access Token` (빈 문자열이어도 키가 있어야 한다) |
| `actionParams.auth_type: "NO_AUTH"` | `For auth_type: OAUTH, Connector params must contain client_id`. **`params`가 아니라 `actionParams`에 넣는다** |
| `entities` | 백킹 데이터 스토어가 만들어지지 않는다 |

---

## 관리 대상

| 리소스 | 설명 |
|---|---|
| `google_project_service.required` | 필요한 API 6종 (`enable_apis`) |
| `data.google_secret_manager_secret.api_key` | 시크릿 존재 확인 (값은 관리하지 않음) |
| `google_artifact_registry_repository.mcp` | `mcp-servers` 도커 저장소 |
| `google_service_account.mcp[*]` | 서비스별 전용 런타임 SA |
| `google_cloud_run_v2_service.mcp[*]` | 서비스 4종 |
| `google_secret_manager_secret_iam_member.runtime[*]` | 각 SA가 **자기 키만** 읽는다 |
| `google_project_iam_member.runtime_telemetry[*]` | 로그·메트릭 쓰기 |
| `google_project_iam_member.vertex_ai[*]` | `dart-mcp`의 `ask_dart` |
| `google_cloud_run_v2_service_iam_member.gemini_enterprise[*]` | **GE 접근 (핵심)** |
| `google_cloud_run_v2_service_iam_member.public[*]` | `allUsers` (기본 비활성) |

서비스 계정을 서비스별로 나눈 이유는 시크릿 격리다. 하나로 묶으면 `ecos-mcp`가
DART·주식 키까지 읽을 수 있다.

---

## 운영

### 코드 변경 배포

```bash
./build.sh dart-mcp     # 하나만
terraform apply
```

### 키 교체

```bash
vi .env                      # 새 키로 수정
set -a && . ./.env && set +a
./setup_keys.sh --apply      # 새 시크릿 버전 추가
./build.sh && terraform apply # 새 리비전이 :latest를 집어가게
```

Cloud Run은 시크릿을 `:latest`로 참조하며 값은 **컨테이너 기동 시점에** 읽는다.
새 버전을 만들어도 이미 떠 있는 인스턴스는 옛 키를 계속 쓰므로, 새 리비전을
만들어야 확실히 반영된다.

### 검증

```bash
TOKEN=$(gcloud auth print-identity-token)
for u in $(terraform output -json mcp_urls | jq -r '.[]'); do
  bash ~/.claude/skills/gemini-enterprise-custom-mcp/scripts/probe_mcp_server.sh "$u" "$TOKEN"
done
```

---

## 알려진 이슈

**Cloud Run 호스트명이 2개다.** `<service>-<project_number>.<region>.run.app`과
canonical `<service>-<hash>-<region>.a.run.app`이 모두 서비스된다. 해시는 생성 전에
알 수 없어 MCP SDK의 `MCP_ALLOWED_HOSTS` 허용목록에 미리 넣을 수 없고, 한쪽만
넣으면 다른 쪽 요청이 `421 Invalid Host header`로 거부된다 — 그런데 GE 쪽에서는
"도구 0개"로만 보여 원인을 찾기 어렵다. 그래서 `MCP_ALLOWED_HOSTS`를 설정하지 않고,
서버가 `K_SERVICE`(Cloud Run 주입 변수)를 보고 DNS 리바인딩 보호를 끄게 했다.

**`scaling` drift.** 프로바이더 6.50.0은 Cloud Run API가 돌려주는 서비스 단위
`scaling`(min/manual_instance_count = 0)을 "설정 안 함"과 구별하지 못해 apply 직후에도
drift를 만든다. `lifecycle { ignore_changes = [scaling] }`로 억제했다.

**프로바이더 버전.** `~> 6.0`으로 고정돼 있고 6.50.0이 설치된다. 최신은 8.x이며
메이저 2단계 차이라 업그레이드는 별도 작업으로 잡는 편이 좋다.

---

## 인증

Terraform은 ADC를 쓴다. `invalid_grant` / `invalid_rapt` 오류가 나면:

```bash
gcloud auth application-default login
```
