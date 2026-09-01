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

output "image_repository" {
  description = "build.sh가 이미지를 밀어 넣는 Artifact Registry 경로."
  value       = local.repo
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
