# 한국 금융 데이터 MCP 서버

국내 금융·경제 공공 API를 **MCP(Model Context Protocol) 서버**로 감싸 Cloud Run에
배포하고, **Gemini Enterprise**에 연결하는 샘플입니다.

연결하고 나면 Gemini Enterprise 채팅에서 이렇게 물어볼 수 있습니다.

> "삼성전자 작년 배당 얼마였어?"
> "예금 금리 제일 높은 은행 알려줘"
> "카카오 임원이 몇 명이야?"
> "최근 기준금리 추이 보여줘"

| 서버 | 데이터 원천 | 도구 수 |
|---|---|---|
| [`ecos-mcp-server`](./ecos-mcp-server) | 한국은행 경제통계시스템(ECOS) | 6 |
| [`dart-mcp-server`](./dart-mcp-server) | 금융감독원 전자공시(OPEN DART) | 4 (82개 API 커버) |
| [`stock-mcp-server`](./stock-mcp-server) | 금융위원회 주식시세정보 | 4 |
| [`finlife-mcp-server`](./finlife-mcp-server) | 금융감독원 금융상품통합비교공시 | 6 |

```
Gemini Enterprise
  └─ Custom MCP 데이터 스토어 4개
       │  Discovery Engine 서비스 에이전트 신원으로 호출
       ↓
  Cloud Run (비공개 — 인터넷에 열지 않습니다)
       ├─ ecos-mcp     ├─ dart-mcp
       ├─ stock-mcp    └─ finlife-mcp
            └─ Secret Manager (서버별 전용 서비스 계정으로 격리)
```

---

## 시작하기 전에

다음이 준비되어 있어야 합니다.

- **Google Cloud 프로젝트** — 결제가 활성화되어 있어야 합니다
- **Gemini Enterprise 앱** — 이미 만들어져 있어야 합니다
- **로컬 도구** — `gcloud`, `terraform`(1.5 이상), `python3`
- **API 키 4개** — 아래에서 발급받습니다

### API 키 발급

각 기관에서 무료로 발급받을 수 있습니다. 승인까지 하루 정도 걸리는 곳도 있습니다.

| 키 | 발급처 | 참고 |
|---|---|---|
| ECOS | [ecos.bok.or.kr](https://ecos.bok.or.kr/api/) | 한국은행 |
| DART | [opendart.fss.or.kr](https://opendart.fss.or.kr/) | 40자리 |
| 주식시세 | [data.go.kr](https://www.data.go.kr/) | 서비스마다 개별 신청이 필요합니다. **디코딩된 형태**의 키를 사용하세요 |
| FINLIFE | [finlife.fss.or.kr](https://finlife.fss.or.kr/) | 금융감독원 |

### 필요한 권한

- 프로젝트에 대한 `roles/editor` 수준의 권한
- Gemini Enterprise 데이터 스토어를 만들려면 `roles/discoveryengine.editor`
- 조직 정책을 직접 해제하려면 `roles/orgpolicy.policyAdmin`
  (없으면 조직 관리자에게 요청하셔야 합니다 — [7단계](#7-조직-정책-확인) 참고)

---

## 배포하기

전체 과정은 20~30분 정도 걸립니다. DART 자산 생성(4분)과 이미지 빌드가 대부분입니다.

### 1. 저장소를 내려받고 terraform 디렉터리로 이동합니다

```bash
git clone https://github.com/sykang169/google-python-sample.git
cd google-python-sample/mcp/terraform
```

### 2. API 키를 Secret Manager에 저장합니다

```bash
cp .env.example .env
vi .env                      # 발급받은 키 4개를 입력하세요
set -a && . ./.env && set +a
./setup_keys.sh --apply
```

다음과 같이 나오면 성공입니다.

```
  ECOS_API_KEY 생성 ... OK
  DART_API_KEY 생성 ... OK
  STOCK_API_KEY 생성 ... OK
  FINLIFE_API_KEY 생성 ... OK
```

> 키는 Terraform이 관리하지 않습니다. Terraform이 시크릿 값을 다루면 상태
> 파일(tfstate)에 평문으로 남기 때문입니다. `setup_keys.sh`가 Secret Manager에
> 직접 넣고, Terraform은 존재 여부만 확인한 뒤 권한을 부여합니다.

`.env` 파일은 `.gitignore`에 포함되어 있으니 커밋될 걱정은 없습니다.

### 3. 배포할 프로젝트를 지정합니다

```bash
cp terraform.tfvars.example terraform.tfvars
vi terraform.tfvars          # project_id를 입력하세요
```

### 4. Terraform 상태 저장소를 준비합니다

상태 파일을 보관할 GCS 버킷이 필요합니다. 없으시면 만들어 주세요.

```bash
gcloud storage buckets create gs://MY-TFSTATE-BUCKET --location=US
gcloud storage buckets update gs://MY-TFSTATE-BUCKET --versioning

terraform init \
  -backend-config="bucket=MY-TFSTATE-BUCKET" \
  -backend-config="prefix=mcp-servers"
```

혼자 시험해 보실 거라면 `versions.tf`의 `backend "gcs" {}` 블록을 주석 처리하고
로컬 상태로 시작하셔도 됩니다.

### 5. 이미지 저장소를 먼저 만듭니다

이미지를 밀어 넣을 곳이 있어야 하므로 Artifact Registry를 먼저 만듭니다.

```bash
terraform apply -target=google_artifact_registry_repository.mcp
```

### 6. 이미지를 빌드하고 배포합니다

DART 서버는 회사 코드 인덱스(약 11.9만 건)를 이미지에 함께 넣습니다. 이 파일은
런타임에 내려받기에는 너무 느려서(실측 약 4분) 빌드 시점에 준비합니다.

```bash
cd ../dart-mcp-server && python build_assets.py && cd ../terraform
./build.sh
terraform apply
```

`terraform output`으로 배포된 주소를 확인하실 수 있습니다.

### 7. 조직 정책 확인

Gemini Enterprise는 기본적으로 Custom MCP 데이터 스토어 생성을 차단합니다.

```
constraints/discoveryengine.managed.disableCustomMcpServerConnector
```

`roles/orgpolicy.policyAdmin` 권한이 있으시면 `terraform.tfvars`에 다음을
추가하고 다시 `terraform apply` 하시면 됩니다.

```hcl
disable_custom_mcp_org_policy_override = true
```

권한이 없으시면 조직 관리자에게 **이 프로젝트에 한해** 해당 제약조건을 해제해
달라고 요청하세요. 정책이 실제로 적용되기까지 2분 정도 걸립니다.

### 8. Gemini Enterprise에 연결합니다

```bash
./connect_ge.sh            # 데이터 커넥터 4개를 만듭니다
./connect_ge.sh --status   # 상태를 확인합니다
```

### 9. 콘솔에서 도구를 활성화합니다

**이 단계를 빠뜨리기 쉽습니다.** 데이터 스토어를 만들어도 도구는 하나도 켜져
있지 않습니다.

데이터 스토어 4개 각각에 대해:

```
Gemini Enterprise → 데이터 스토어 → 해당 항목 선택 → Actions 탭
  → Reload custom actions      (MCP 서버에서 도구 목록을 가져옵니다)
  → 도구 선택 → Enable actions
```

`Reload custom actions`를 누르기 전에는 목록이 비어 있는 것이 정상입니다.

### 10. 확인합니다

```bash
./connect_ge.sh --status
```

네 개 모두 `state=ACTIVE`이고 `tools`와 `enabled` 숫자가 같으면 완료입니다.

```
  ecos-mcp-connector      state=ACTIVE tools=6 enabled=6
  dart-mcp-connector      state=ACTIVE tools=4 enabled=4
  stock-mcp-connector     state=ACTIVE tools=4 enabled=4
  finlife-mcp-connector   state=ACTIVE tools=6 enabled=6
```

이제 Gemini Enterprise 채팅에서 질문해 보세요.

---

## 어시스턴트가 도구를 잘 쓰게 하려면

기본 상태에서는 모델이 웹 검색과 MCP 도구 중 무엇을 쓸지 매번 스스로 판단합니다.
금융 수치는 원천 데이터가 정확하므로, 시스템 지시로 우선순위를 알려 주시는 편이
좋습니다.

[`SYSTEM_PROMPT.md`](./SYSTEM_PROMPT.md)에 바로 붙여 넣을 수 있는 초안과, 적용
후 확인해 볼 검증 질문이 정리되어 있습니다.

---

## 문제가 생겼을 때

| 증상 | 확인할 것 |
|---|---|
| 데이터 스토어 생성이 거부됩니다 | 조직 정책([7단계](#7-조직-정책-확인))이 아직 적용되지 않았을 수 있습니다. 해제 후 2분 정도 기다려 주세요 |
| `Reload custom actions`에 도구가 안 나옵니다 | MCP 서버에 도달하지 못하는 경우입니다. 아래 검증 명령으로 서버부터 확인해 보세요 |
| 모델이 "도구를 호출하겠습니다"만 반복합니다 | 서버가 최신 코드로 배포되었는지 확인해 주세요. `./build.sh && terraform apply` |
| `terraform apply`는 성공했는데 변경이 반영되지 않습니다 | Cloud Run 트래픽이 이전 리비전에 고정되었을 수 있습니다. `gcloud run services update-traffic SVC --to-latest` |

서버가 정상인지 직접 확인하시려면:

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
```

더 자세한 운영 방법과 알려진 이슈는 [`terraform/README.md`](./terraform/README.md)를
참고해 주세요.

---

## 운영

### 코드를 수정했을 때

```bash
cd terraform
./build.sh dart-mcp        # 수정한 서버만 빌드할 수 있습니다
terraform apply
```

### API 키를 교체할 때

```bash
vi .env                       # 새 키로 수정
set -a && . ./.env && set +a
./setup_keys.sh --apply       # 새 버전을 추가합니다
./build.sh && terraform apply # 새 리비전이 새 키를 읽도록 합니다
```

Cloud Run은 시크릿을 `:latest`로 참조하고 값은 컨테이너가 시작할 때 읽습니다.
이미 실행 중인 인스턴스는 이전 키를 계속 쓰므로, 마지막 줄이 필요합니다.

### DART 회사 인덱스를 갱신할 때

신규 법인이 늘거나 DART가 엔드포인트를 추가했을 때 다시 만듭니다.

```bash
cd dart-mcp-server
python build_assets.py --catalog   # 엔드포인트 카탈로그만 (빠름)
python build_assets.py --corp      # 회사 인덱스만 (약 4분)
cd ../terraform && ./build.sh dart-mcp && terraform apply
```

---

## 설계에 대하여

**도구 수를 억제했습니다.** DART는 JSON 엔드포인트가 82개인데, 그대로 노출하면
도구 목록만으로 약 3.7만 토큰을 차지합니다. 에이전트에 MCP 서버를 여러 개
붙이는 순간 컨텍스트 예산을 모두 소모하게 됩니다. 그래서 `search_dart_apis`로
필요한 엔드포인트를 찾고 `call_dart_api`로 실행하는 방식으로 4개까지 줄였습니다.
네 서버를 합쳐도 도구 20개, 약 3,400토큰입니다.

**집계는 서버에서 처리합니다.** "임원이 몇 명인가" 같은 질문에서 모델이 JSON
수십 행을 직접 세면 틀립니다(실제로 틀렸습니다). DART 응답에 건수와 범주형 필드
분포를 미리 계산해 함께 돌려줍니다.

**조인도 서버에서 처리합니다.** FINLIFE는 상품 정보와 금리를 별도 배열로
주는데, 서버가 합쳐서 상품 하나에 금리 옵션이 붙은 형태로 반환합니다.

**모두 조회 전용입니다.** 20개 도구 전부 `readOnlyHint`가 붙어 있어 Gemini
Enterprise가 사용자 확인 없이 호출합니다.

---

## Cloud Run을 인터넷에 공개하지 않습니다

Gemini Enterprise 문서만 보면 `allUsers` 권한이 필요한 것처럼 읽히지만, 실제로는
Discovery Engine 서비스 에이전트 신원으로 호출합니다. 이 서비스 에이전트에
`roles/run.invoker`만 부여하면 비공개 서비스에서도 동작합니다.

덕분에 VPC나 Private Service Connect 구성, 조직의 도메인 제한 정책 해제가 모두
불필요합니다. Terraform이 기본으로 이 권한을 부여하므로 별도로 하실 일은 없습니다.

---

## 이 저장소의 기존 OpenAPI 명세에 대하여

`adk-finance-agent/` 아래의 OpenAPI 명세 파일들은 실제 API와 다릅니다. 실호출로
확인한 결과입니다.

- `dart_openapi_full_specification.yml` — JSON 경로 42개 중 19개가 존재하지 않는
  엔드포인트이고, 59개가 누락되어 있습니다. 이름도 잘못된 곳이 있습니다
- `ecos_final_openapi.yml` — 존재하지 않는 검색 파라미터가 적혀 있습니다

이 서버들은 해당 파일이 아니라 각 기관 공식 개발가이드에서 직접 수집하고 실호출로
검증한 명세를 사용합니다.

---

## 디렉터리 구성

```
mcp/
├── README.md               이 문서
├── SYSTEM_PROMPT.md        Gemini Enterprise 시스템 지시 + 검증 질문
├── ecos-mcp-server/        한국은행 경제통계
│   └── openapi_spec/       공식 API 개발명세서
├── dart-mcp-server/        전자공시
│   ├── assets/             빌드 시점에 준비하는 카탈로그와 회사 인덱스
│   └── build_assets.py     자산 생성 스크립트
├── stock-mcp-server/       주식시세
├── finlife-mcp-server/     금융상품 금리
└── terraform/              인프라 정의와 배포 스크립트
    ├── setup_keys.sh       API 키를 Secret Manager에 저장
    ├── build.sh            컨테이너 이미지 빌드
    └── connect_ge.sh       Gemini Enterprise 데이터 커넥터 생성
```
