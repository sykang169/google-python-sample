#!/usr/bin/env bash
# 배포된 MCP 서버를 Gemini Enterprise Custom MCP 데이터 스토어로 연결한다.
#
#   usage: ./connect_ge.sh [서비스명 ...]
#          ./connect_ge.sh                 # 3개 전부
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

ALL=(ecos-mcp dart-mcp stock-mcp finlife-mcp)
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

  cid="${svc}-connector"
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
      \"collectionDisplayName\": \"${svc}\",
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
