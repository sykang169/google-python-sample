#!/usr/bin/env bash
# MCP 서버 이미지를 빌드해 Artifact Registry에 올리고, 태그를 Terraform에 넘긴다.
#
#   usage: ./build.sh [서비스명 ...]
#          ./build.sh              # 3개 전부
#          ./build.sh dart-mcp     # 하나만
#
# 이미지를 밀어 넣은 뒤 image.auto.tfvars에 타임스탬프 태그를 기록하므로,
# 이어서 `terraform apply`만 하면 새 리비전이 배포된다.
# (태그를 latest로 두면 Terraform이 변경을 감지하지 못한다.)
set -euo pipefail

cd "$(dirname "$0")"

# 프로젝트/리전은 terraform output -> terraform.tfvars -> gcloud 순으로 찾는다.
# 환경변수로 덮어쓸 수 있다: PROJECT_ID=... REGION=... ./build.sh
from_tfvars() { [[ -f terraform.tfvars ]] && grep -m1 "^[[:space:]]*$1" terraform.tfvars | sed 's/.*"\(.*\)".*/\1/'; }
if [[ -z "${PROJECT_ID:-}" ]]; then
  PROJECT_ID="$(terraform output -raw project_id 2>/dev/null || true)"
  [[ -z "$PROJECT_ID" ]] && PROJECT_ID="$(from_tfvars project_id || true)"
  [[ -z "$PROJECT_ID" ]] && PROJECT_ID="$(gcloud config get-value project 2>/dev/null || true)"
fi
if [[ -z "${REGION:-}" ]]; then
  REGION="$(from_tfvars region || true)"
  [[ -z "$REGION" ]] && REGION="us-central1"
fi
if [[ -z "$PROJECT_ID" ]]; then
  echo "project_id를 찾지 못했습니다. terraform.tfvars에 넣거나 PROJECT_ID=... 로 지정하세요." >&2
  exit 1
fi
# 서비스마다 리전이 다르다. apis.data.go.kr을 쓰는 서버들(fsc-* 5종과
# stock-mcp)은 전용 이그레스 IP가 있는 서울에 있다. 이미지는 각자의 리전
# 저장소로 올린다 — Cloud Run이 타 리전에서 당길 수는 있지만 콜드 스타트마다
# 대륙을 건넌다.
#
# 어느 서비스가 어느 리전인지는 Terraform이 정답을 갖고 있으므로 여기서
# 추측하지 않고 output에서 읽는다. apply 전이라 output이 없으면 fsc-* 규칙으로
# 넘어간다.
SVC_REGIONS_JSON="$(terraform output -json service_regions 2>/dev/null || echo '{}')"

# 리전을 옮기는 중이라면 output이 아직 옛 리전을 가리킨다(output은 마지막
# apply 상태다). 그때는 FORCE_REGION으로 새 리전에 먼저 이미지를 올린 뒤
# apply한다: FORCE_REGION=asia-northeast3 ./build.sh stock-mcp
svc_region() {
  if [[ -n "${FORCE_REGION:-}" ]]; then echo "$FORCE_REGION"; return; fi
  local r
  r="$(python3 -c "
import json,sys
try: print(json.loads(sys.argv[1]).get(sys.argv[2],''))
except Exception: print('')
" "$SVC_REGIONS_JSON" "$1" 2>/dev/null)"
  if [[ -n "$r" ]]; then echo "$r"; else echo "$REGION"; fi
}
svc_repo() { echo "$(svc_region "$1")-docker.pkg.dev/${PROJECT_ID}/mcp-servers"; }

TAG="$(date -u +%Y%m%d-%H%M%S)"

ALL=(ecos-mcp dart-mcp stock-mcp finlife-mcp
     fsc-market-mcp fsc-ficc-mcp fsc-research-mcp fsc-equity-ops-mcp fsc-industry-mcp)
TARGETS=("${@:-}")
[[ -z "${TARGETS[0]:-}" ]] && TARGETS=("${ALL[@]}")

echo "project=$PROJECT_ID  region=$REGION  tag=$TAG"
echo

# Artifact Registry 저장소는 Terraform이 만든다. 없으면 먼저 apply 해야 한다.
for _r in $(for _s in "${TARGETS[@]}"; do svc_region "$_s"; done | sort -u); do
  if ! gcloud artifacts repositories describe mcp-servers \
        --location="$_r" --project="$PROJECT_ID" >/dev/null 2>&1; then
    echo "Artifact Registry 'mcp-servers'가 $_r 에 없습니다." >&2
    echo "먼저 'terraform apply -target=google_artifact_registry_repository.mcp'를 실행하세요." >&2
    exit 1
  fi
done

for svc in "${TARGETS[@]}"; do
  src="../${svc}-server"
  [[ -d "$src" ]] || { echo "소스 디렉터리 없음: $src" >&2; exit 1; }

  if [[ "$svc" == "dart-mcp" && ( ! -f "$src/assets/catalog.json" || ! -f "$src/assets/corp_index.json.gz" ) ]]; then
    echo "$svc: assets/가 없습니다. '$src'에서 python build_assets.py를 먼저 실행하세요." >&2
    exit 1
  fi

  echo "[$svc] 빌드 중... -> $(svc_region "$svc")"
  gcloud builds submit "$src" \
    --tag="$(svc_repo "$svc")/${svc}:${TAG}" \
    --project="$PROJECT_ID" \
    --quiet
done

# 방금 빌드한 서비스의 태그만 갱신하고 나머지는 보존한다.
# 전체 공용 태그 하나를 쓰면 부분 빌드 시 빌드하지 않은 서비스가 존재하지 않는
# 이미지를 가리켜 apply가 "Image not found"로 깨진다.
update_tags() {
  local tag="$1"; shift
  python3 -c '
import pathlib, re, sys
tag, built = sys.argv[1], sys.argv[2:]
path = pathlib.Path("image.auto.tfvars")
tags = {}
if path.exists():
    body = path.read_text()
    if "{" in body:
        body = body.split("{", 1)[1]
    tags = dict(re.findall(r"([A-Za-z0-9_-]+)\s*=\s*\"([^\"]+)\"", body))
tags.update({svc: tag for svc in built})
lines = "\n".join(f"  {k} = \"{v}\"" for k, v in sorted(tags.items()))
path.write_text("# build.sh가 생성. 직접 수정하지 말 것.\nimage_tags = {\n" + lines + "\n}\n")
for k, v in sorted(tags.items()):
    print(f"  {k} = {v}")
' "$tag" "$@"
}

echo
echo "image.auto.tfvars 갱신:"
update_tags "$TAG" "${TARGETS[@]}"
echo
echo "다음: terraform apply"
