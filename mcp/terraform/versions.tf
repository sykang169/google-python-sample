terraform {
  required_version = ">= 1.5"

  # 백엔드는 부분 구성이다. 계정/프로젝트마다 다르므로 init 시 지정한다:
  #
  #   terraform init \
  #     -backend-config="bucket=MY-TFSTATE-BUCKET" \
  #     -backend-config="prefix=mcp-servers"
  #
  # 로컬 state로 시작하려면 이 backend 블록을 주석 처리한다.
  backend "gcs" {}

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region

  # ADC가 사용자 자격증명이면 요청에 할당량 프로젝트가 붙지 않는다. orgpolicy처럼
  # 이를 요구하는 API는 403으로 거절한다 — 게다가 소비자로 잡히는 프로젝트가
  # var.project_id가 아니라 ADC에 박힌 다른 프로젝트다.
  #
  #   Error 403: ... requires a quota project, which is not set by default
  #   "consumer": "projects/<무관한 번호>", "reason": "SERVICE_DISABLED"
  #
  # 프로바이더는 ADC 파일의 quota_project_id를 읽지 않는다. user_project_override가
  # 유일한 경로다 — 켜면 모든 요청에 X-Goog-User-Project를 붙인다.
  # (호출자에게 프로젝트의 serviceusage.services.use 권한이 있어야 한다.)
  billing_project       = var.project_id
  user_project_override = true
}
