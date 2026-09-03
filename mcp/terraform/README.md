# MCP 서버 인프라 (Terraform)

MCP 서버 8종의 Cloud Run 배포와 Gemini Enterprise 연결을 관리합니다.
모두 서울 리전(`asia-northeast3`)에 있고, 전용 이그레스 IP를 함께 씁니다.

처음 배포하시는 경우 [`../README.md`](../README.md)의 단계별 안내를 먼저 봐 주세요.
이 문서는 구성 요소와 운영 방법을 다룹니다.

## 스크립트

| 스크립트 | 하는 일 |
|---|---|
| `setup_keys.sh` | API 키를 Secret Manager에 저장합니다. `--apply` 없이 실행하면 점검만 합니다 |
| `build.sh` | 컨테이너 이미지를 빌드해 Artifact Registry에 올립니다. 서비스명을 주면 그것만 빌드합니다 |
| `connect_ge.sh` | Gemini Enterprise 데이터 커넥터를 만듭니다. `--status`로 상태를 봅니다 |

## 관리 대상

| 리소스 | 설명 |
|---|---|
| `google_project_service.required` | 필요한 API 6종 (`enable_apis`) |
| `data.google_secret_manager_secret.api_key` | 시크릿 존재 확인 (값은 관리하지 않습니다) |
| `google_artifact_registry_repository.mcp` | `mcp-servers` 도커 저장소 |
| `google_service_account.mcp[*]` | 서비스별 전용 런타임 서비스 계정 |
| `google_cloud_run_v2_service.mcp[*]` | 서비스 4종 |
| `google_secret_manager_secret_iam_member.runtime[*]` | 각 계정이 **자기 키만** 읽습니다 |
| `google_project_iam_member.runtime_telemetry[*]` | 로그·메트릭 쓰기 |
| `google_project_iam_member.vertex_ai[*]` | `dart-mcp`의 `ask_dart`용 |
| `google_cloud_run_v2_service_iam_member.gemini_enterprise[*]` | **GE 접근 (핵심)** |
| `google_cloud_run_v2_service_iam_member.public[*]` | `allUsers` (기본 비활성) |
| `google_compute_network.mcp` / `subnetwork` | 전용 이그레스용 VPC |
| `google_compute_address.nat[*]` | **고정 이그레스 IP** |
| `google_compute_router_nat.mcp[*]` | Cloud NAT |

서비스 계정을 서비스별로 나눈 이유는 시크릿 격리입니다. 하나로 묶으면 `ecos-mcp`가
DART·주식 키까지 읽을 수 있습니다.

## API 키는 Terraform이 관리하지 않습니다

Terraform이 시크릿 값을 다루면 상태 파일(tfstate)에 평문으로 저장됩니다. 그래서
`setup_keys.sh`가 Secret Manager에 직접 넣고, Terraform은 존재를 확인한 뒤 IAM만
겁니다.

```bash
set -a && . ./.env && set +a
./setup_keys.sh            # 점검만
./setup_keys.sh --apply    # 생성 또는 새 버전 추가
```

값이 기존과 같으면 새 버전을 만들지 않으므로 여러 번 실행하셔도 됩니다.

## Cloud Run을 공개하지 않습니다

Gemini Enterprise는 다음 신원으로 MCP 엔드포인트를 호출합니다.

```
service-<PROJECT_NUMBER>@gcp-sa-discoveryengine.iam.gserviceaccount.com
```

이 서비스 에이전트에 `roles/run.invoker`만 부여하면 비공개 Cloud Run에서도
동작합니다. `grant_gemini_enterprise_access = true`(기본값)가 이 바인딩을 겁니다.

덕분에 `allUsers` 공개가 불필요하고, 조직의 도메인 제한 정책(Domain restricted
sharing)을 건드리지 않아도 됩니다. 서비스 에이전트는 조직 내부 주체라 해당 정책에
걸리지 않습니다.

`public_access` 변수는 GE 외의 공개 클라이언트에도 열어야 할 때만 씁니다.

## 전용 이그레스 IP를 씁니다

`apis.data.go.kr`은 Cloud Run **공유 이그레스 풀의 특정 IP를 거부합니다.**
같은 시각·같은 이미지로 인스턴스 13개를 동시에 띄워 같은 요청을 보냈더니
하나(`34.96.43.204`)만 `ConnectTimeout`이고 나머지 12개는 HTTP 200이었습니다.
리전이나 코드 문제가 아니라 IP 문제입니다.

MCP 서버는 인스턴스가 오래 살아 있어서, 한 번 거부되는 IP를 받으면 그 인스턴스가
재활용될 때까지 계속 실패합니다. 그래서 Cloud NAT로 우리가 소유한 고정 IP 하나를
통해 나갑니다.

```bash
terraform output egress_ips
```

공공 API가 IP 등록을 요구하거나(`resultCode 32`) 차단을 문의할 때 제출할 주소가
이 값입니다. NAT가 필요 없으시면 `nat_regions = []`로 두시면 되지만, 그러면 위
문제에 다시 노출됩니다.

## 조직 정책

Custom MCP 데이터 스토어 생성은 기본적으로 차단되어 있습니다.

```
constraints/discoveryengine.managed.disableCustomMcpServerConnector
```

`roles/orgpolicy.policyAdmin`이 있으시면 Terraform이 해제할 수 있습니다.

```hcl
disable_custom_mcp_org_policy_override = true
```

권한이 없으시면 `false`로 두고 조직 관리자에게 요청하세요. 정책이 실제로 적용되기까지
2분 정도 걸리므로, 해제 직후 실패한다고 설정이 잘못됐다고 판단하지 마세요.

## 데이터 커넥터 페이로드

`connect_ge.sh`가 쓰는 형태입니다. Terraform 프로바이더에 해당 리소스가 없고
`gcloud`에도 `discovery-engine` 명령군이 없어 REST로만 만들 수 있습니다.

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

네 가지가 모두 필요하며 하나라도 빠지면 실패합니다.

> **`instance_uri`는 만든 뒤 바꿀 수 없습니다.** `PATCH`가 오류 없이 무시되므로
> 바뀐 줄 알기 쉽습니다. Cloud Run URL이 달라지면(리전 이전 등) 커넥터를 새로
> 만들어야 하고, 컬렉션 ID는 재사용까지 시간이 걸립니다. `CONNECTOR_SUFFIX`로
> 다른 ID를 주세요.
>
> ```bash
> CONNECTOR_SUFFIX=-kr ./connect_ge.sh fsc-market-mcp
> ```
>
> 새로 만든 커넥터는 콘솔에서 **Reload custom actions → Enable actions**를 거쳐야
> 도구가 활성화됩니다. 옛 커넥터는 삭제해 주세요.

| 항목 | 빠뜨렸을 때 |
|---|---|
| `connectorModes: ["FEDERATED"]` | 데이터 수집 파이프라인을 돌리려다 `INITIALIZATION_FAILED` |
| `params.oauth_access_token: ""` | `Missing Parameter Private App Access Token` (빈 문자열이어도 키는 있어야 합니다) |
| `actionParams.auth_type: "NO_AUTH"` | `For auth_type: OAUTH, Connector params must contain client_id`. `params`가 아니라 `actionParams`에 넣습니다 |
| `entities` | 백킹 데이터 스토어가 만들어지지 않습니다 |

## 운영

### 코드 수정 후 배포

```bash
./build.sh dart-mcp     # 수정한 서비스만 빌드할 수 있습니다
terraform apply
```

`build.sh`는 어느 서비스가 어느 리전인지 `terraform output service_regions`에서
읽습니다. 리전을 옮기는 중이라면 그 값이 아직 옛 리전을 가리키므로
`FORCE_REGION`으로 새 리전에 먼저 이미지를 올린 뒤 apply 하세요.

```bash
FORCE_REGION=asia-northeast3 ./build.sh fsc-market-mcp
```

`build.sh`는 빌드한 서비스의 태그만 `image.auto.tfvars`에 기록하므로, 일부만 다시
빌드해도 나머지가 깨지지 않습니다.

`image.auto.tfvars`는 **생성물이라 커밋하지 않습니다**(`.gitignore`). 태그는
프로젝트마다 다르므로, 커밋해 두면 새 프로젝트에 clone 했을 때 남의 프로젝트
태그를 물려받아 Cloud Run이 `Image not found`로 죽습니다. 빌드 없이 `apply`하면
`terraform plan` 단계에서 precondition이 막고 `./build.sh`를 먼저 실행하라고
알려줍니다.

### 키 교체

```bash
vi .env                       # 새 키로 수정
set -a && . ./.env && set +a
./setup_keys.sh --apply       # 새 시크릿 버전 추가
./build.sh && terraform apply # 새 리비전이 새 키를 읽도록
```

Cloud Run은 시크릿을 `:latest`로 참조하고 값은 컨테이너가 시작할 때 읽습니다. 이미
실행 중인 인스턴스는 이전 키를 계속 쓰므로 마지막 줄이 필요합니다.

### 검증

```bash
TOKEN=$(gcloud auth print-identity-token)
for u in $(terraform output -json mcp_urls | jq -r '.[]'); do
  curl -sN --max-time 30 -X POST "$u" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | head -c 200
  echo
done

./connect_ge.sh --status
```

## 알아 두실 점

**프로바이더 버전** — `~> 6.0`으로 고정되어 있고 6.50.0이 설치됩니다. 최신은
8.x이며 메이저 두 단계 차이라 업그레이드는 별도 작업으로 잡으시는 편이 좋습니다.

**트래픽 라우팅** — `traffic` 블록으로 최신 리비전에 고정해 두었습니다. 이 선언이
없으면 `gcloud run services update --no-traffic` 같은 명령으로 특정 리비전에 묶여도
drift로 잡히지 않아, apply가 성공해도 새 코드가 서비스되지 않습니다.

**인증** — Terraform은 ADC를 씁니다. `invalid_grant`나 `invalid_rapt` 오류가 나면
`gcloud auth application-default login`으로 재인증해 주세요.
