#!/usr/bin/env bash
# 첫 배포를 순서대로 실행한다.
#
#   ./deploy.sh          점검만 — 무엇이 준비됐고 무엇이 빠졌는지 보여준다
#   ./deploy.sh --apply  빠진 것을 채우며 끝까지 진행한다
#
# 이 저장소의 배포는 단계 사이에 순서 의존이 있는데, 그게 오류 메시지에
# 드러나지 않는다. 실제로 새 프로젝트에서 세 번 막혔다.
#
#   Service Usage가 꺼져 있으면  → terraform이 API를 켜다가 통째로 죽는다
#   Artifact Registry가 없으면   → build.sh가 이미지를 밀어 넣을 곳이 없다
#   build.sh를 건너뛰면          → Cloud Run이 몇 분 뒤 Image not found
#
# 각 단계는 멱등이므로 중간에 실패하면 원인을 고치고 다시 돌리면 된다.
# 손으로 하시려면 ../README.md의 1~10단계가 같은 순서다.
set -uo pipefail

cd "$(dirname "$0")"

ok()   { printf '  \033[32m OK \033[0m %s\n' "$1"; }
warn() { printf '  \033[33mWARN\033[0m %s\n' "$1"; }
bad()  { printf '  \033[31mMISS\033[0m %s\n' "$1"; }
why()  { [[ -n "${1:-}" ]] && printf '%s\n' "$1" | sed 's/^/        /'; }
step() { printf '\n\033[1m── %s\033[0m\n' "$1"; }

APPLY=0
[[ "${1:-}" == "--apply" ]] && APPLY=1

halt() {
  printf '\n\033[31m중단: %s\033[0m\n' "$1"
  [[ -n "${2:-}" ]] && printf '%s\n' "$2"
  exit 1
}

# 점검 모드에서 "이건 --apply가 해준다"고 알리고 넘어가기 위한 표시
todo=0
pending() { warn "$1"; todo=1; }

# ── 사전 점검 ───────────────────────────────────────────────────────────────

step "사전 점검"

for cmd in gcloud terraform python3; do
  command -v "$cmd" >/dev/null 2>&1 || halt "$cmd 가 없습니다."
done
ok "gcloud · terraform · python3"

from_tfvars() { [[ -f terraform.tfvars ]] && grep -m1 "^[[:space:]]*$1" terraform.tfvars | sed 's/.*"\(.*\)".*/\1/'; }
if [[ -n "${PROJECT_ID:-}" ]]; then
  PROJECT_SRC="환경변수 PROJECT_ID"
else
  PROJECT_ID="$(from_tfvars project_id)"
  PROJECT_SRC="terraform.tfvars"
fi
if [[ -z "$PROJECT_ID" ]]; then
  halt "project_id를 찾지 못했습니다." \
    "  cp terraform.tfvars.example terraform.tfvars && vi terraform.tfvars"
fi
ok "project: $PROJECT_ID  ($PROJECT_SRC)"
ok "account: $(gcloud config get-value account 2>/dev/null)"

# 결제는 확인만 한다. run·aiplatform·compute는 결제 없이는 활성화가 거부되는데,
# 그때 나오는 오류가 원인을 알려주지 않는다.
billing="$(gcloud beta billing projects describe "$PROJECT_ID" \
             --format='value(billingEnabled)' 2>/dev/null)"
case "$billing" in
  True) ok "결제 계정 연결됨" ;;
  False) halt "결제 계정이 연결되지 않았습니다." \
           "  https://console.cloud.google.com/billing/linkedaccount?project=$PROJECT_ID" ;;
  *) warn "결제 상태를 확인하지 못했습니다 (권한 또는 billing API). 계속 진행합니다" ;;
esac

# ── 1. API ──────────────────────────────────────────────────────────────────
#
# main.tf의 google_project_service와 같은 목록이다. Terraform도 켜지만,
# Terraform 자신이 Service Usage API를 호출하므로 그게 꺼져 있으면 apply가
# 시작도 못 한다. 그래서 여기서 먼저 켠다.

step "1. API 활성화"

APIS=(
  serviceusage.googleapis.com        # 이게 먼저다. Terraform이 나머지를 켜려면 필요하다
  cloudresourcemanager.googleapis.com
  run.googleapis.com
  secretmanager.googleapis.com
  artifactregistry.googleapis.com
  cloudbuild.googleapis.com
  discoveryengine.googleapis.com
  aiplatform.googleapis.com
  compute.googleapis.com
)

enabled_list="$(gcloud services list --enabled --project="$PROJECT_ID" \
                  --format='value(config.name)' 2>/dev/null)"
missing=()
for api in "${APIS[@]}"; do
  grep -qx "$api" <<<"$enabled_list" || missing+=("$api")
done

if [[ ${#missing[@]} -eq 0 ]]; then
  ok "${#APIS[@]}개 모두 활성화됨"
elif [[ $APPLY -eq 0 ]]; then
  pending "${#missing[@]}개가 꺼져 있습니다: ${missing[*]}"
else
  printf '  활성화 중 (%d개) ... ' "${#missing[@]}"
  if api_err="$(gcloud services enable "${missing[@]}" --project="$PROJECT_ID" 2>&1 >/dev/null)"; then
    echo "OK"
    echo "  전파에 1~2분 걸립니다."
  else
    echo "실패"
    why "$api_err"
    halt "API를 켜지 못했습니다." \
"Service Usage API가 꺼진 새 프로젝트는 gcloud로도 부트스트랩이 안 되는 경우가
있습니다. 콘솔에서 한 번만 켜고 다시 실행하세요.

  https://console.developers.google.com/apis/api/serviceusage.googleapis.com/overview?project=$PROJECT_ID"
  fi
fi

# ── 2. API 키 ───────────────────────────────────────────────────────────────

step "2. API 키를 Secret Manager에"

if [[ ! -f .env ]]; then
  bad ".env 가 없습니다"
  halt "API 키를 먼저 넣어 주세요." \
    "  cp .env.example .env && vi .env"
fi
set -a && . ./.env && set +a
if [[ $APPLY -eq 1 ]]; then
  ./setup_keys.sh --apply || halt "setup_keys.sh 실패 (위 오류 참고)"
else
  ./setup_keys.sh || pending "키가 아직 Secret Manager에 없습니다"
fi

# ── 3. Terraform 초기화 ─────────────────────────────────────────────────────
#
# 백엔드 버킷은 계정마다 다르므로 여기서 정하지 않는다. 안내만 한다.

step "3. Terraform 초기화"

if [[ -d .terraform ]] && terraform providers >/dev/null 2>&1; then
  ok "초기화됨"
else
  bad "초기화되지 않았습니다"
  halt "terraform init 을 먼저 실행하세요." \
"  gcloud storage buckets create gs://MY-TFSTATE-BUCKET --location=US
  gcloud storage buckets update gs://MY-TFSTATE-BUCKET --versioning
  terraform init -backend-config=\"bucket=MY-TFSTATE-BUCKET\" -backend-config=\"prefix=mcp-servers\"

로컬 state로 시험만 하실 거면 versions.tf의 backend \"gcs\" {} 를 주석 처리하고
terraform init 만 실행하셔도 됩니다."
fi

# ── 4. 빌드에 필요한 것 ─────────────────────────────────────────────────────
#
# 이미지를 밀어 넣을 저장소와, 빌드를 돌릴 계정이 먼저 있어야 build.sh가 돈다.
# 2024년 이후 만든 프로젝트는 기본 컴퓨트 SA로 빌드가 되지 않는다.

step "4. Artifact Registry · 빌드 계정"

REGION="$(from_tfvars region)"; [[ -z "$REGION" ]] && REGION="us-central1"
BUILD_SA="mcp-build@${PROJECT_ID}.iam.gserviceaccount.com"
need_bootstrap=0

if gcloud artifacts repositories describe mcp-servers \
     --location="$REGION" --project="$PROJECT_ID" >/dev/null 2>&1; then
  ok "mcp-servers ($REGION)"
else
  need_bootstrap=1
  [[ $APPLY -eq 0 ]] && pending "mcp-servers 저장소가 $REGION 에 없습니다"
fi

if gcloud iam service-accounts describe "$BUILD_SA" --project="$PROJECT_ID" >/dev/null 2>&1; then
  ok "$BUILD_SA"
else
  need_bootstrap=1
  [[ $APPLY -eq 0 ]] && pending "빌드 계정 mcp-build 가 없습니다"
fi

if [[ $need_bootstrap -eq 1 && $APPLY -eq 1 ]]; then
  terraform apply \
    -target=google_artifact_registry_repository.mcp \
    -target=google_service_account.build \
    -target=google_project_iam_member.build \
    || halt "Artifact Registry / 빌드 계정 생성 실패"
fi

# ── 5. DART 자산 ────────────────────────────────────────────────────────────
#
# 회사 코드 인덱스 약 11.9만 건. 런타임에 내려받으면 4분이 걸려 이미지에 넣는다.

step "5. DART 자산"

if [[ -f ../dart-mcp-server/assets/catalog.json && -f ../dart-mcp-server/assets/corp_index.json.gz ]]; then
  ok "assets/ 준비됨"
elif [[ $APPLY -eq 0 ]]; then
  pending "assets/ 가 없습니다 (생성에 약 4분)"
else
  echo "  생성 중 — 약 4분 걸립니다."
  ( cd ../dart-mcp-server && python3 build_assets.py ) || halt "build_assets.py 실패"
fi

# ── 6. 이미지 빌드 ──────────────────────────────────────────────────────────
#
# image.auto.tfvars는 생성물이라 저장소에 없다. 빌드해야 태그가 생긴다.

step "6. 이미지 빌드"

if [[ -f image.auto.tfvars ]]; then
  ok "image.auto.tfvars 있음 — 코드를 고쳤다면 ./build.sh 로 다시 빌드하세요"
  why "$(grep -E '^\s+[a-z]' image.auto.tfvars)"
elif [[ $APPLY -eq 0 ]]; then
  pending "이미지 태그가 없습니다 — ./build.sh 가 필요합니다"
else
  ./build.sh || halt "build.sh 실패"
fi

# ── 7. 배포 ─────────────────────────────────────────────────────────────────

step "7. 배포"

if [[ $APPLY -eq 0 ]]; then
  if [[ $todo -eq 1 ]]; then
    printf '\n빠진 것이 있습니다. --apply 로 채우며 진행하세요.\n\n  ./deploy.sh --apply\n\n'
    exit 1
  fi
  ok "준비 완료 — terraform apply 로 진행하세요"
  exit 0
fi

terraform apply || halt "terraform apply 실패"

# ── 8. 다음 단계 ────────────────────────────────────────────────────────────

cat <<MSG

배포가 끝났습니다. Gemini Enterprise 연결은 조직 정책 확인이 필요해서
자동으로 하지 않습니다.

  1) 조직 정책 해제 (README 7단계)
       constraints/discoveryengine.managed.disableCustomMcpServerConnector
  2) ./connect_ge.sh          데이터 커넥터 8개 생성
  3) 콘솔에서 도구 활성화 (README 9단계 — 빠뜨리기 쉽습니다)
       데이터 스토어 → Actions → Reload custom actions → Enable actions
  4) ./connect_ge.sh --status 여덟 개 모두 tools == enabled 이면 완료
MSG
