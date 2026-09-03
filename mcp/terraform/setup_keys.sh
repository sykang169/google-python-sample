#!/usr/bin/env bash
# API 키를 Secret Manager에 넣는다. Terraform 밖에서 처리해 키가 tfstate에
# 남지 않게 하는 것이 목적이다.
#
#   ./setup_keys.sh          점검만 (아무것도 바꾸지 않는다)
#   ./setup_keys.sh --apply  .env 값으로 시크릿 생성 또는 새 버전 추가
#
# 사전에 키를 환경변수로 불러온다:
#   cp .env.example .env && vi .env
#   set -a && . ./.env && set +a
set -uo pipefail

cd "$(dirname "$0")"

from_tfvars() { [[ -f terraform.tfvars ]] && grep -m1 "^[[:space:]]*$1" terraform.tfvars | sed 's/.*"\(.*\)".*/\1/'; }
if [[ -n "${PROJECT_ID:-}" ]]; then
  PROJECT_SRC="환경변수 PROJECT_ID"
else
  PROJECT_ID="$(from_tfvars project_id)"
  PROJECT_SRC="terraform.tfvars"
fi
if [[ -z "$PROJECT_ID" ]]; then
  PROJECT_ID="$(gcloud config get-value project 2>/dev/null)"
  PROJECT_SRC="gcloud config"
fi
if [[ -z "$PROJECT_ID" ]]; then
  echo "project_id를 찾지 못했습니다. terraform.tfvars에 넣으세요." >&2
  exit 1
fi

SERVICES=(ecos dart stock finlife)
declare -A SECRET=(
  [ecos]=ECOS_API_KEY [dart]=DART_API_KEY
  [stock]=STOCK_API_KEY [finlife]=FINLIFE_API_KEY
)

ok()   { printf '  \033[32m OK \033[0m %s\n' "$1"; }
warn() { printf '  \033[33mWARN\033[0m %s\n' "$1"; }
bad()  { printf '  \033[31mMISS\033[0m %s\n' "$1"; }
# gcloud가 뱉은 이유를 그대로 옮긴다. 권한 부족·API 미활성화·조직 정책이
# 전부 "실패" 한 줄로 뭉개지면 어디를 고쳐야 할지 알 수 없다.
why()  { [[ -n "${1:-}" ]] && printf '%s\n' "$1" | sed 's/^/        /'; }

APPLY=0
[[ "${1:-}" == "--apply" ]] && APPLY=1

echo "project: $PROJECT_ID  ($PROJECT_SRC)"
echo "account: $(gcloud config get-value account 2>/dev/null)"
echo

# 새 프로젝트에서는 API가 꺼져 있다. Terraform의 google_project_service가
# 켜 주지만, 그 리소스 자체가 Service Usage API를 호출하므로 Service Usage가
# 꺼져 있으면 terraform apply가 통째로 죽는다(닭-달걀). Terraform이 스스로
# 부트스트랩할 수 없는 두 개를 여기서 먼저 켠다.
#   serviceusage      — Terraform이 나머지 API를 켜려면 이게 먼저다
#   secretmanager     — 이 스크립트가 바로 아래에서 쓴다
api_ready=1
for api in serviceusage.googleapis.com secretmanager.googleapis.com; do
  if gcloud services list --enabled --project="$PROJECT_ID" \
       --filter="config.name=$api" --format='value(config.name)' 2>/dev/null | grep -q .; then
    continue
  fi
  if [[ $APPLY -eq 0 ]]; then
    warn "$api 가 꺼져 있다(또는 확인 불가) — --apply 로 켠다"
    api_ready=0
    continue
  fi
  printf '  %s 활성화 ... ' "$api"
  if api_err="$(gcloud services enable "$api" --project="$PROJECT_ID" 2>&1 >/dev/null)"; then
    echo "OK"
  else
    echo "실패"
    why "$api_err"
    api_ready=0
  fi
done
if [[ $api_ready -eq 0 && $APPLY -eq 1 ]]; then
  cat <<MSG

API를 켜지 못했다. Service Usage API가 꺼진 새 프로젝트는 gcloud로도 부트스트랩이
안 되는 경우가 있다. 그때는 콘솔에서 한 번만 켜고 다시 실행한다.

  https://console.developers.google.com/apis/api/serviceusage.googleapis.com/overview?project=$PROJECT_ID

켠 뒤 1~2분 전파를 기다려야 한다. 결제 계정이 연결되지 않은 프로젝트도 같은 지점에서 막힌다.
MSG
  exit 1
fi

need_key=()
failed=()
for svc in "${SERVICES[@]}"; do
  var="TF_VAR_${svc}_api_key"
  val="${!var:-}"
  secret="${SECRET[$svc]}"
  exists=0
  if desc_err="$(gcloud secrets describe "$secret" --project="$PROJECT_ID" 2>&1 >/dev/null)"; then
    exists=1
  elif grep -qiE 'not found|NOT_FOUND' <<<"$desc_err" && grep -qF "$secret" <<<"$desc_err"; then
    exists=0   # 정말로 시크릿이 없는 경우만 생성으로 넘어간다
  else
    # 프로젝트가 없거나 권한이 없는 것이다. 생성해도 같은 이유로 실패한다.
    bad "$secret  조회 불가 — 시크릿이 없어서가 아니다"
    why "$desc_err"
    failed+=("$svc")
    continue
  fi

  if [[ $APPLY -eq 0 ]]; then
    # ── 점검 모드 ──
    if [[ $exists -eq 1 ]]; then
      ver="$(gcloud secrets versions list "$secret" --project="$PROJECT_ID" \
              --filter='state=ENABLED' --format='value(name)' 2>/dev/null | head -1)"
      ok "$secret  존재 (최신 버전 $ver)"
    elif [[ -n "$val" ]]; then
      warn "$secret  없음 — .env에 값이 있으니 --apply로 만들 수 있다"
      need_key+=("$svc")
    else
      bad "$secret  없음, $var 도 미설정"
      need_key+=("$svc")
    fi
    continue
  fi

  # ── 적용 모드 ──
  if [[ -z "$val" ]]; then
    if [[ $exists -eq 1 ]]; then
      ok "$secret  건너뜀 ($var 미설정, 기존 값 유지)"
    else
      bad "$secret  없는데 $var 도 미설정 — 건너뜀"
      need_key+=("$svc")
    fi
    continue
  fi

  if [[ $exists -eq 0 ]]; then
    printf '  %s 생성 ... ' "$secret"
    if create_err="$(gcloud secrets create "$secret" --project="$PROJECT_ID" \
         --replication-policy=automatic --data-file=<(printf '%s' "$val") 2>&1 >/dev/null)"; then
      echo "OK"
    else
      echo "실패"
      why "$create_err"
      failed+=("$svc")
    fi
  else
    # 값이 같으면 새 버전을 만들지 않는다. 버전만 늘어나고 얻는 게 없다.
    cur="$(gcloud secrets versions access latest --secret="$secret" --project="$PROJECT_ID" 2>/dev/null)"
    if [[ "$cur" == "$val" ]]; then
      ok "$secret  값 동일 — 새 버전 만들지 않음"
    else
      printf '  %s 새 버전 추가 ... ' "$secret"
      if add_err="$(printf '%s' "$val" | gcloud secrets versions add "$secret" \
           --project="$PROJECT_ID" --data-file=- 2>&1 >/dev/null)"; then
        echo "OK"
      else
        echo "실패"
        why "$add_err"
        failed+=("$svc")
      fi
    fi
  fi
done

echo
if [[ ${#failed[@]} -gt 0 ]]; then
  cat <<MSG
[실패] ${failed[*]}

위 gcloud 오류가 원인이다. 다른 프로젝트에서 전부 실패한다면 대개 셋 중 하나다.

  1. 활성 계정이 $PROJECT_ID 에 권한이 없다 (PERMISSION_DENIED / 프로젝트가 안 보임)
       gcloud auth list                     # 지금 어떤 신원으로 도는지
       gcloud config set account <계정>
       필요 권한: roles/secretmanager.admin

  2. Secret Manager API가 꺼져 있다 (SERVICE_DISABLED)
       gcloud services enable secretmanager.googleapis.com --project=$PROJECT_ID

  3. 리소스 위치 조직 정책이 automatic 복제를 막는다 (FAILED_PRECONDITION)
       이 스크립트의 --replication-policy=automatic 을
       --replication-policy=user-managed --locations=<리전> 으로 바꿔야 한다

프로젝트를 잘못 잡은 것이라면 위 'project:' 줄의 출처를 보라.
terraform.tfvars 를 고치거나 PROJECT_ID=<프로젝트> ./setup_keys.sh --apply 로 덮어쓴다.
MSG
  exit 1
fi

if [[ ${#need_key[@]} -gt 0 ]]; then
  cat <<MSG
[누락] ${need_key[*]}

  cp .env.example .env && vi .env
  set -a && . ./.env && set +a
  ./setup_keys.sh --apply
MSG
  exit 1
fi

if [[ $APPLY -eq 1 ]]; then
  cat <<'MSG'
[다음 단계]
  Cloud Run은 시크릿을 :latest로 참조하며, 값은 **컨테이너 기동 시점에** 읽는다.
  이미 떠 있는 인스턴스는 옛 키를 계속 쓰므로 새 리비전을 만들어야 반영된다:

    ./build.sh && terraform apply
MSG
else
  echo "[준비 완료] terraform apply 로 진행한다."
fi
