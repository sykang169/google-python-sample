# API 키는 **Terraform이 관리하지 않는다.**
#
# 키 값을 Terraform이 만들면 tfstate에 평문으로 저장된다. 그래서 시크릿 생성은
# ./setup_keys.sh 가 Terraform 밖에서 처리하고, Terraform은 존재를 확인하고
# IAM만 건다. 키가 tfstate에 남을 일이 없다.
#
#   ./setup_keys.sh          점검
#   ./setup_keys.sh --apply  .env 값으로 시크릿 생성/갱신
#
# 이 data 블록은 시크릿이 없을 때 apply를 명확한 메시지로 멈추게 한다.
# 없으면 IAM 바인딩 단계에서 덜 친절한 NOT_FOUND가 난다.

data "google_secret_manager_secret" "api_key" {
  for_each = local.services

  project   = var.project_id
  secret_id = each.value.secret_id

  depends_on = [google_project_service.required]
}
