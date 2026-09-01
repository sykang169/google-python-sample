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
}
