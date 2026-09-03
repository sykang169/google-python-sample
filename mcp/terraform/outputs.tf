output "project_id" {
  description = "배포 대상 프로젝트. connect_ge.sh가 읽는다."
  value       = var.project_id
}

output "mcp_urls" {
  description = "각 MCP 서버의 엔드포인트. 데이터 스토어에 등록할 때 /mcp를 붙인다."
  value = {
    for k, s in google_cloud_run_v2_service.mcp : k => "${s.uri}/mcp"
  }
}

output "image_repositories" {
  description = "리전별 Artifact Registry 경로. build.sh가 서비스 리전에 맞춰 고른다."
  value       = local.repos
}

output "service_regions" {
  description = "서비스별 배포 리전. build.sh와 connect_ge.sh가 읽는다."
  value       = { for k, v in local.services : k => v.region }
}

output "runtime_service_accounts" {
  description = "서비스별 전용 런타임 서비스 계정."
  value       = { for k, sa in google_service_account.mcp : k => sa.email }
}

output "public_access_enabled" {
  description = <<-EOT
    allUsers invoker 부여 여부. false이면 Gemini Enterprise가 도달할 수 없다
    (조직 정책 constraints/iam.allowedPolicyMemberDomains 확인 필요).
  EOT
  value       = var.public_access
}

output "egress_ips" {
  description = <<-EOT
    리전별 고정 이그레스 IP. 공공 API가 IP 등록을 요구할 때(resultCode 32)
    제출할 주소이며, 차단 여부를 문의할 때도 이 값을 쓴다.
  EOT
  value       = { for r, a in google_compute_address.nat : r => a.address }
}

output "build_service_account" {
  description = "build.sh가 Cloud Build를 돌릴 때 쓰는 계정"
  value       = google_service_account.build.email
}
