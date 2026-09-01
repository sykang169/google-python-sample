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
PROJECT_ID="${PROJECT_ID:-$(from_tfvars project_id)}"
[[ -z "$PROJECT_ID" ]] && PROJECT_ID="$(gcloud config get-value project 2>/dev/null)"
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

APPLY=0
[[ "${1:-}" == "--apply" ]] && APPLY=1

echo "project: $PROJECT_ID"
echo

need_key=()
for svc in "${SERVICES[@]}"; do
  var="TF_VAR_${svc}_api_key"
  val="${!var:-}"
  secret="${SECRET[$svc]}"
  exists=0
  gcloud secrets describe "$secret" --project="$PROJECT_ID" >/dev/null 2>&1 && exists=1

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
    if gcloud secrets create "$secret" --project="$PROJECT_ID" \
         --replication-policy=automatic --data-file=<(printf '%s' "$val") >/dev/null 2>&1; then
      echo "OK"
    else
      echo "실패"
    fi
  else
    # 값이 같으면 새 버전을 만들지 않는다. 버전만 늘어나고 얻는 게 없다.
    cur="$(gcloud secrets versions access latest --secret="$secret" --project="$PROJECT_ID" 2>/dev/null)"
    if [[ "$cur" == "$val" ]]; then
      ok "$secret  값 동일 — 새 버전 만들지 않음"
    else
      printf '  %s 새 버전 추가 ... ' "$secret"
      if printf '%s' "$val" | gcloud secrets versions add "$secret" \
           --project="$PROJECT_ID" --data-file=- >/dev/null 2>&1; then
        echo "OK"
      else
        echo "실패"
      fi
    fi
  fi
done

echo
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
