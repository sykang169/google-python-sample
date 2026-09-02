#!/usr/bin/env bash
# 배포된 MCP 서버를 Gemini Enterprise Custom MCP 데이터 스토어로 연결한다.
#
#   usage: ./connect_ge.sh [서비스명 ...]
#          ./connect_ge.sh                 # 9개 전부
#          ./connect_ge.sh dart-mcp        # 하나만
#
# Terraform이 Cloud Run 배포와 IAM까지 끝낸 뒤에 실행한다.
# 데이터 커넥터는 Terraform 프로바이더에 리소스가 없어 REST로 만든다
# (gcloud에도 discovery-engine 명령군이 없다).
#
# 사전 조건
#   1. terraform apply 완료 (grant_gemini_enterprise_access = true)
#   2. constraints/discoveryengine.managed.disableCustomMcpServerConnector 해제
#      (disable_custom_mcp_org_policy_override = true 또는 조직 관리자가 처리)
set -euo pipefail

cd "$(dirname "$0")"

PROJECT_ID="$(terraform output -raw project_id 2>/dev/null || true)"
if [[ -z "$PROJECT_ID" ]]; then
  echo "terraform output에서 project_id를 못 읽었습니다. terraform apply를 먼저 실행하세요." >&2
  exit 1
fi

# 데이터 커넥터는 GE 앱과 같은 멀티리전에 만든다. 기본은 global.
LOCATION="${GE_LOCATION:-global}"
BASE="https://discoveryengine.googleapis.com/v1alpha"

ALL=(ecos-mcp dart-mcp finlife-mcp
     fsc-market-mcp fsc-ficc-mcp fsc-research-mcp fsc-equity-ops-mcp fsc-industry-mcp)

# 콘솔 목록에 보이는 이름. 목록이 가나다순으로 정렬되므로 주제를 앞에 둔다 —
# 기관을 앞에 두면 금감원이 공시와 금융상품 두 곳으로 흩어지고, 정작 무엇을
# 묻는 데이터인지가 뒤로 밀린다.
#
# 이 이름은 모델의 도구 선택에 쓰이지 않는다. 라우팅은 MCP 서버가 주는 도구
# 이름과 설명으로 결정된다. 여기는 사람이 콘솔에서 찾기 위한 이름이다.
#
# 이미 만들어진 커넥터에는 영향이 없다(생성 시에만 쓰인다). 기존 것을 바꾸려면
# collections.patch로 displayName을 갱신한다 — instance_uri와 달리 변경 가능하다.
declare -A DISPLAY_NAME=(
  [ecos-mcp]="거시경제 — 한국은행 ECOS"
  [dart-mcp]="공시·재무 — 금감원 DART"
  [finlife-mcp]="금융상품 금리 — 금감원"
  [fsc-research-mcp]="기업재무 — 금융위"
  [fsc-equity-ops-mcp]="배당·권리사무 — 금융위"
  [fsc-market-mcp]="주식·지수·ETF·채권 시세 — 금융위"
  [fsc-ficc-mcp]="채권·단기금리 — 금융위"
  [fsc-industry-mcp]="펀드·증권업계 — 금융위"
)
TARGETS=("${@:-}")
[[ -z "${TARGETS[0]:-}" ]] && TARGETS=("${ALL[@]}")

TOKEN="$(gcloud auth print-access-token)"

# 상태 조회 모드 — 이름을 추측하지 않고 custom_mcp 커넥터를 전부 나열한다.
# 콘솔에서 만든 것은 ID에 타임스탬프가 붙으므로 목록 조회가 안전하다.
if [[ "${1:-}" == "--status" ]]; then
  echo "project=$PROJECT_ID location=$LOCATION"
  curl -s "${BASE}/projects/${PROJECT_ID}/locations/${LOCATION}/collections?pageSize=100" \
    -H "Authorization: Bearer ${TOKEN}" \
  | python3 -c "
import sys, json
d = json.load(sys.stdin)
if d.get('error'):
    print('  조회 실패:', str(d['error'].get('message'))[:150]); raise SystemExit(1)
rows = [c for c in d.get('collections', [])
        if (c.get('dataConnector') or {}).get('dataSource') == 'custom_mcp']
if not rows:
    print('  custom_mcp 커넥터가 없습니다.'); raise SystemExit
for c in rows:
    dc = c['dataConnector']
    tools = dc.get('dynamicTools') or []
    on = sum(1 for t in tools if t.get('enabled'))
    uri = ((dc.get('actionConfig') or {}).get('actionParams') or {}).get('instance_uri', '?')
    print(f\"  {c['name'].split('/')[-1][:40]:<42} state={dc.get('state')} tools={len(tools)} enabled={on}\")
    print(f\"      {uri}\")
    for e in (dc.get('errors') or [])[:1]:
        print('      error:', str(e.get('message'))[:120])
"
  exit 0
fi

for svc in "${TARGETS[@]}"; do
  url="$(terraform output -json mcp_urls | python3 -c \
    "import sys,json; print(json.load(sys.stdin).get('$svc',''))")"
  if [[ -z "$url" ]]; then
    echo "$svc: terraform output에 URL이 없습니다. 건너뜁니다." >&2
    continue
  fi

  # 커넥터의 instance_uri는 생성 후 변경할 수 없다. PATCH가 오류 없이 무시된다.
  # 서비스 URL이 바뀌면(리전 이전 등) 새 ID로 다시 만들어야 하므로 접미사를 둔다.
  #   CONNECTOR_SUFFIX=-kr ./connect_ge.sh fsc-market-mcp
  cid="${svc}${CONNECTOR_SUFFIX:-}-connector"
  printf '%-12s %s\n' "$svc" "$url"

  # 페이로드의 네 가지가 전부 필요하다. 하나라도 빠지면 실패한다:
  #   connectorModes: ["FEDERATED"]   없으면 데이터 수집 파이프라인을 돌리려다
  #                                   INITIALIZATION_FAILED
  #   params.oauth_access_token: ""   빈 문자열이어도 키 자체가 있어야 한다
  #   actionParams.auth_type          params가 아니라 actionParams에 들어간다
  #   entities                        백킹 데이터 스토어가 만들어진다
  resp="$(curl -s -X POST "${BASE}/projects/${PROJECT_ID}/locations/${LOCATION}:setUpDataConnector" \
    -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" \
    -d "{
      \"collectionId\": \"${cid}\",
      \"collectionDisplayName\": \"${DISPLAY_NAME[$svc]:-$svc}\",
      \"dataConnector\": {
        \"dataSource\": \"custom_mcp\",
        \"refreshInterval\": \"86400s\",
        \"connectorModes\": [\"FEDERATED\"],
        \"params\": {\"oauth_access_token\": \"\"},
        \"entities\": [{\"entityName\": \"mcp_data\"}],
        \"actionConfig\": {
          \"createBapConnection\": true,
          \"actionParams\": {
            \"instance_uri\": \"${url}\",
            \"auth_type\": \"NO_AUTH\",
            \"mcp_server_source\": \"BYO_MCP\",
            \"use_agent_gateway_egress\": false
          }
        }
      }
    }")"

  msg="$(python3 -c "
import sys, json
d = json.loads(sys.stdin.read())
e = d.get('error')
print('  ERROR: ' + str(e.get('message'))[:200] if e else '  생성 요청 OK')
" <<<"$resp")"
  echo "$msg"
done

cat <<'MSG'

── 다음 단계 ──────────────────────────────────────────────────────────────
초기화에 10~30초 걸린다. 상태 확인:

  ./connect_ge.sh --status     (아래 참고)

도구는 콘솔에서 켜야 한다. 데이터 스토어마다:
  Gemini Enterprise → 데이터 스토어 → 해당 항목 → Actions
    → Reload custom actions   (MCP 서버에 tools/list를 호출한다)
    → 도구 선택 → Enable actions

Reload를 누르기 전에는 도구 목록이 비어 있는 것이 정상이다.
MSG
