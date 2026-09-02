# ── 전용 이그레스 IP (Cloud NAT) ────────────────────────────────────────────
#
# apis.data.go.kr은 Cloud Run 공유 이그레스 풀의 **특정 IP를 거부한다.**
# 실측: 같은 시각, 같은 이미지, 같은 리전의 인스턴스 13개를 동시에 띄워
# 동일한 요청을 보냈더니 34.96.43.204 하나만 ConnectTimeout이고 나머지 12개는
# HTTP 200이었다. 리전이나 코드 문제가 아니라 IP 문제다.
#
# MCP 서버는 인스턴스가 오래 살아 있어서, 한 번 거부되는 IP를 받으면 그
# 인스턴스가 재활용될 때까지 계속 실패한다. Cloud NAT로 우리가 소유한 고정
# IP 하나를 통해 나가면 공유 풀에서 완전히 빠져나온다.
#
# 여기서 만든 IP는 data.go.kr에 등록이 필요해질 때(resultCode 32) 제출할
# 주소이기도 하다. terraform output egress_ips 로 확인한다.

resource "google_compute_network" "mcp" {
  count = length(var.nat_regions) > 0 ? 1 : 0

  project                 = var.project_id
  name                    = "mcp-egress"
  auto_create_subnetworks = false
  description             = "MCP 서버 전용 이그레스 (Cloud NAT)"

  depends_on = [google_project_service.required]
}

# Cloud Run 직접 VPC 이그레스는 인스턴스마다 이 서브넷의 IP를 하나씩 쓴다.
# /24면 최대 인스턴스 수(10)에 충분하고 여유도 넉넉하다.
resource "google_compute_subnetwork" "mcp" {
  for_each = toset(var.nat_regions)

  project       = var.project_id
  name          = "mcp-egress-${each.value}"
  region        = each.value
  network       = google_compute_network.mcp[0].id
  ip_cidr_range = cidrsubnet(var.nat_subnet_cidr_base, 8, index(var.nat_regions, each.value))
}

resource "google_compute_address" "nat" {
  for_each = toset(var.nat_regions)

  project      = var.project_id
  name         = "mcp-nat-${each.value}"
  region       = each.value
  address_type = "EXTERNAL"
  description  = "MCP 서버의 고정 이그레스 IP. 공공 API에 등록할 주소."
}

resource "google_compute_router" "mcp" {
  for_each = toset(var.nat_regions)

  project = var.project_id
  name    = "mcp-egress-${each.value}"
  region  = each.value
  network = google_compute_network.mcp[0].id
}

resource "google_compute_router_nat" "mcp" {
  for_each = toset(var.nat_regions)

  project = var.project_id
  name    = "mcp-egress-${each.value}"
  region  = each.value
  router  = google_compute_router.mcp[each.value].name

  nat_ip_allocate_option = "MANUAL_ONLY"
  nat_ips                = [google_compute_address.nat[each.value].self_link]

  # 이 VPC의 모든 서브넷이 이 NAT로 나간다. 서브넷이 MCP 전용이라 범위가 좁다.
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"

  log_config {
    enable = true
    filter = "ERRORS_ONLY"
  }
}
