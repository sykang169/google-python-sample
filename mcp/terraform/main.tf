data "google_project" "this" {
  project_id = var.project_id
}

# ── API 활성화 ──────────────────────────────────────────────────────────────
# 신규 프로젝트에서 바로 apply할 수 있도록 필요한 API를 켠다.

resource "google_project_service" "required" {
  for_each = var.enable_apis ? toset([
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "discoveryengine.googleapis.com", # Gemini Enterprise 데이터 스토어
    "aiplatform.googleapis.com",      # dart-mcp의 ask_dart
  ]) : toset([])

  project = var.project_id
  service = each.value

  # 이 구성을 destroy해도 API는 끄지 않는다. 다른 리소스가 쓰고 있을 수 있다.
  disable_on_destroy = false
}

locals {
  repo = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.mcp.repository_id}"

  # MCP 서버 3종. 구조가 같아 for_each로 묶는다.
  services = {
    ecos-mcp = {
      secret_id       = "ECOS_API_KEY"
      secret_env      = "ECOS_API_KEY"
      memory          = "512Mi"
      needs_vertex_ai = false
      extra_env       = {}
    }
    dart-mcp = {
      secret_id       = "DART_API_KEY"
      secret_env      = "DART_API_KEY"
      memory          = "1Gi" # 11.8만 건 회사 인덱스를 메모리에 올린다
      needs_vertex_ai = true  # ask_dart의 내부 라우팅이 Gemini를 호출한다
      extra_env = {
        GOOGLE_CLOUD_PROJECT  = var.project_id
        GOOGLE_CLOUD_LOCATION = "global"
      }
    }
    stock-mcp = {
      secret_id       = "STOCK_API_KEY"
      secret_env      = "STOCK_API_KEY"
      memory          = "512Mi"
      needs_vertex_ai = false
      extra_env       = {}
    }
    finlife-mcp = {
      secret_id       = "FINLIFE_API_KEY"
      secret_env      = "FINLIFE_API_KEY"
      memory          = "512Mi"
      needs_vertex_ai = false
      extra_env       = {}
    }
  }

  vertex_ai_services = toset([for k, v in local.services : k if v.needs_vertex_ai])
}

# ── Artifact Registry ───────────────────────────────────────────────────────
# gcloud run deploy --source 가 자동 생성하는 cloud-run-source-deploy 대신
# Terraform이 소유하는 저장소를 쓴다.

resource "google_artifact_registry_repository" "mcp" {
  project       = var.project_id
  location      = var.region
  repository_id = "mcp-servers"
  description   = "MCP 서버 컨테이너 이미지 (Terraform 관리)"
  format        = "DOCKER"

  depends_on = [google_project_service.required]

  labels = {
    managed = "terraform"
    owner   = "mcp"
  }
}

# ── 서비스 계정 ─────────────────────────────────────────────────────────────
# 서비스마다 전용 SA를 둔다. 프로젝트 기본 컴퓨트 SA는 roles/owner를 갖고 있어
# MCP 서버 런타임으로 쓰기에 과도하다.
#
# SA를 서비스별로 분리하는 이유는 시크릿 격리다. 하나로 묶으면 ecos-mcp가
# DART/STOCK 키까지 읽을 수 있다.

resource "google_service_account" "mcp" {
  for_each = local.services

  project      = var.project_id
  account_id   = "${each.key}-run"
  display_name = "${each.key} Cloud Run runtime"
  description  = "MCP 서버 ${each.key}의 런타임 계정 (Terraform 관리)"
}

# Cloud Run 컨테이너가 로그와 메트릭을 쓰려면 필요하다.
# 기본 컴퓨트 SA는 owner/editor를 통해 암묵적으로 갖고 있던 권한이라,
# 전용 SA로 바꾸면 명시적으로 부여해야 한다.
resource "google_project_iam_member" "runtime_telemetry" {
  for_each = {
    for pair in setproduct(keys(local.services), [
      "roles/logging.logWriter",
      "roles/monitoring.metricWriter",
    ]) : "${pair[0]}:${pair[1]}" => { service = pair[0], role = pair[1] }
  }

  project = var.project_id
  role    = each.value.role
  member  = "serviceAccount:${google_service_account.mcp[each.value.service].email}"
}

# ── Cloud Run ───────────────────────────────────────────────────────────────

resource "google_cloud_run_v2_service" "mcp" {
  for_each = local.services

  project             = var.project_id
  name                = each.key
  location            = var.region
  deletion_protection = false

  # Gemini Enterprise가 도달해야 하므로 인그레스를 열어 둔다.
  # 실제 접근 허용 여부는 아래 IAM(public_access)이 결정한다.
  ingress = "INGRESS_TRAFFIC_ALL"

  labels = {
    managed = "terraform"
    owner   = "mcp"
  }

  template {
    service_account = google_service_account.mcp[each.key].email

    scaling {
      max_instance_count = 10
    }

    containers {
      image = "${local.repo}/${each.key}:${lookup(var.image_tags, each.key, var.image_tag)}"

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          memory = each.value.memory
          cpu    = "1"
        }
      }

      # MCP_ALLOWED_HOSTS는 일부러 설정하지 않는다.
      #
      # Cloud Run은 서비스마다 호스트명을 두 개 제공한다:
      #   <service>-<project_number>.<region>.run.app   (예측 가능)
      #   <service>-<hash>-<region_short>.a.run.app     (canonical, 예측 불가)
      # 콘솔과 status.uri가 보여주는 것은 후자이고, 해시는 생성 전에 알 수 없어
      # 허용목록에 미리 넣을 수 없다. 한쪽만 넣으면 다른 쪽으로 온 요청이
      # 421 Invalid Host header로 거부되는데, Gemini Enterprise 쪽에서는
      # "도구 0개"로만 보여 원인을 찾기 매우 어렵다.
      #
      # 서버는 MCP_ALLOWED_HOSTS가 비어 있고 K_SERVICE(Cloud Run 주입 변수)가
      # 있으면 DNS 리바인딩 보호를 끈다. 이 보호는 브라우저가 호스트명을
      # 127.0.0.1로 재해석하는 공격을 막기 위한 것이고, Gemini Enterprise가
      # 서버 대 서버로 호출하는 이 엔드포인트는 해당 위협 모델이 아니다.

      dynamic "env" {
        for_each = each.value.extra_env
        content {
          name  = env.key
          value = env.value
        }
      }

      env {
        name = each.value.secret_env
        value_source {
          secret_key_ref {
            secret  = each.value.secret_id
            version = "latest"
          }
        }
      }
    }
  }

  # 트래픽을 명시적으로 최신 리비전에 고정한다.
  # 선언하지 않으면 Terraform이 트래픽을 추적하지 않아, `gcloud run services
  # update --no-traffic` 같은 명령으로 특정 리비전에 묶여도 drift로 잡히지
  # 않는다. 그러면 apply가 성공해도 새 코드가 서비스되지 않는다.
  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  depends_on = [google_secret_manager_secret_iam_member.runtime]

  lifecycle {
    # Cloud Run v2에는 scaling 블록이 두 군데 있다:
    #   template.scaling  리비전 단위 (max_instance_count 등) — 우리가 관리한다
    #   scaling           서비스 단위 (min_instance_count, manual_instance_count)
    #
    # 후자는 우리가 설정하지 않는데도 API가 0을 돌려주고, 프로바이더 6.50.0은
    # 이를 "설정 안 함"과 구별하지 못해 apply 직후에도 계속 null로 되돌리려는
    # drift를 만든다. 둘 다 기본값(0)이라 실제로 바뀌는 것은 없으므로 무시한다.
    ignore_changes = [scaling]
  }
}

# ── IAM ─────────────────────────────────────────────────────────────────────

# 런타임 SA가 각자의 API 키 시크릿을 읽을 수 있어야 한다.
resource "google_secret_manager_secret_iam_member" "runtime" {
  for_each = { for k, v in local.services : k => v.secret_id }

  project   = var.project_id
  secret_id = each.value
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.mcp[each.key].email}"

  # 시크릿이 실제로 있는지 먼저 확인시킨다 (secrets.tf 참고).
  depends_on = [data.google_secret_manager_secret.api_key]
}

# ── Gemini Enterprise 접근 ──────────────────────────────────────────────────
#
# **GE 연동에 필요한 것은 이 바인딩 하나뿐이다.** Cloud Run을 인터넷에 공개할
# 필요가 없다. Gemini Enterprise는 Discovery Engine 서비스 에이전트 신원으로
# MCP 엔드포인트를 호출하며, 이 주체는 조직 내부이므로 Domain restricted
# sharing(iam.allowedPolicyMemberDomains)에 걸리지 않는다.
#
# 공식 문서는 공개 엔드포인트가 필수인 것처럼 읽히지만(PSC 미지원 언급 때문에
# 더욱), 실측으로 비공개 서비스에서 tools/list가 정상 동작함을 확인했다.

resource "google_cloud_run_v2_service_iam_member" "gemini_enterprise" {
  for_each = var.grant_gemini_enterprise_access ? local.services : {}

  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.mcp[each.key].name
  role     = "roles/run.invoker"
  member   = "serviceAccount:service-${data.google_project.this.number}@gcp-sa-discoveryengine.iam.gserviceaccount.com"
}

# dart-mcp의 ask_dart만 Vertex AI(Gemini)로 엔드포인트를 라우팅한다.
# 다른 서버의 SA에는 부여하지 않는다.
resource "google_project_iam_member" "vertex_ai" {
  for_each = local.vertex_ai_services

  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.mcp[each.key].email}"
}

# Gemini Enterprise 데이터 스토어 연결에 필요한 공개 접근.
# 조직 정책 constraints/iam.allowedPolicyMemberDomains가 풀린 뒤에만 적용된다.
resource "google_cloud_run_v2_service_iam_member" "public" {
  for_each = var.public_access ? local.services : {}

  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.mcp[each.key].name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
