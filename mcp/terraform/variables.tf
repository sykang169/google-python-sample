variable "project_id" {
  description = "MCP 서버를 배포할 Google Cloud 프로젝트 ID."
  type        = string
}

# 서버 전체가 한국 공공 API(한국은행·금감원·공공데이터포털)만 호출하므로
# 서울에 둔다. 왕복이 짧고, 전용 이그레스 IP(network.tf)도 이 리전에 있다.
variable "region" {
  description = "Cloud Run·Artifact Registry 리전."
  type        = string
  default     = "asia-northeast3"
}

# 전용 이그레스 IP를 붙일 리전. 빈 리스트면 Cloud NAT를 만들지 않고
# Cloud Run 공유 이그레스 풀을 그대로 쓴다(그러면 위 문제에 다시 노출된다).
variable "nat_regions" {
  description = "Cloud NAT로 고정 이그레스 IP를 붙일 리전 목록."
  type        = list(string)
  default     = ["asia-northeast3"]
}

variable "nat_subnet_cidr_base" {
  description = "NAT용 서브넷을 잘라 쓸 대역. 리전마다 /24를 하나씩 쓴다."
  type        = string
  default     = "10.90.0.0/16"
}

# ── API 키 ─────────────────────────────────────────────────────────────────
# 키는 Terraform 변수가 아니다. tfstate에 평문으로 남지 않도록 Secret Manager에
# 직접 넣고, Terraform은 참조만 한다. ./setup_keys.sh 와 .env.example 참고.

# ── 배포 ───────────────────────────────────────────────────────────────────

variable "image_tags" {
  description = <<-EOT
    서비스별 이미지 태그. build.sh가 **빌드한 서비스만** 여기에 기록하므로
    일부만 다시 빌드해도 나머지가 깨지지 않는다.
    비어 있는 서비스는 image_tag 값을 쓴다.
  EOT
  type        = map(string)
  default     = {}
}

variable "image_tag" {
  description = <<-EOT
    배포할 컨테이너 이미지 태그. build.sh가 이미지를 밀어 넣은 뒤
    image.auto.tfvars에 타임스탬프 태그를 기록하므로 보통 직접 설정하지 않는다.
    'latest'로 두면 Terraform이 이미지 변경을 감지하지 못해 새 리비전이 만들어지지 않는다.
  EOT
  type        = string
  default     = "latest"
}

variable "enable_apis" {
  description = <<-EOT
    필요한 Google Cloud API를 Terraform이 활성화할지 여부.
    신규 프로젝트에서는 true로 둔다. 이미 활성화되어 있거나 API 관리 권한이
    없으면 false로 두고 수동으로 활성화한다.
  EOT
  type        = bool
  default     = true
}

# ── Gemini Enterprise 연동 ─────────────────────────────────────────────────

variable "grant_gemini_enterprise_access" {
  description = <<-EOT
    Discovery Engine 서비스 에이전트에게 Cloud Run 호출 권한(run.invoker)을 줄지 여부.

    **Gemini Enterprise 데이터 스토어 연결에 필요한 것은 이것뿐이다.**
    서비스를 인터넷에 공개(allUsers)할 필요가 없다 — 실측으로 확인했다.
    GE는 service-<PROJECT_NUMBER>@gcp-sa-discoveryengine.iam.gserviceaccount.com
    신원으로 MCP 엔드포인트를 호출한다.

    이 서비스 에이전트는 조직 내부 주체이므로 Domain restricted sharing
    (iam.allowedPolicyMemberDomains)에 걸리지 않는다.
  EOT
  type        = bool
  default     = true
}

variable "public_access" {
  description = <<-EOT
    Cloud Run 서비스에 allUsers invoker를 부여할지 여부.

    **Gemini Enterprise 연동에는 불필요하다.** grant_gemini_enterprise_access로
    충분하며, 공개하면 URL을 아는 누구나 도구를 호출해 API 키 할당량을 소진할 수
    있다. 조직에 Domain restricted sharing이 걸려 있으면 이 값을 true로 해도
    바인딩이 거부된다.

    MCP 서버를 GE 외의 공개 클라이언트에도 열어야 할 때만 true로 한다.
  EOT
  type        = bool
  default     = false
}

variable "disable_custom_mcp_org_policy_override" {
  description = <<-EOT
    constraints/discoveryengine.managed.disableCustomMcpServerConnector를
    이 프로젝트에서 해제할지 여부.

    이 제약은 기본적으로 **enforce 상태**이며, 켜져 있으면 Custom MCP 데이터
    스토어 생성 자체가 거부된다 (Gemini Enterprise 연동의 필수 선행 조건).

    적용하려면 roles/orgpolicy.policyAdmin이 필요하다. 권한이 없으면 false로
    두고 조직 관리자에게 요청한다. 정책 전파에 약 2분이 걸린다.
  EOT
  type        = bool
  default     = false
}
