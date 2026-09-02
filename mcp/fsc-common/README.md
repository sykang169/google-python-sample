# 금융 MCP 서버

한국 금융 공공데이터를 MCP로 노출하는 서버 모음. Cloud Run에 올려
Gemini Enterprise의 Custom MCP Server 데이터 스토어로 쓴다.

## 서버

| 서버 | 출처 | 다루는 것 |
| --- | --- | --- |
| `dart-mcp-server` | 금감원 OPEN DART | 전자공시 82종. 원문·XBRL·사업보고서 |
| `ecos-mcp-server` | 한국은행 ECOS | 거시 시계열. 기준금리·환율·물가 |
| `finlife-mcp-server` | 금감원 FinLife | 예적금·대출 금리 비교 |
| `fsc-market-mcp-server` | 금융위 | 주식·지수·ETF·ETN·채권·선물·일반상품 시세 |
| `fsc-ficc-mcp-server` | 금융위 | 채권 발행·권리일정·콜, CP/CD 실거래, DCM |
| `fsc-research-mcp-server` | 금융위 | 정규화 재무제표, 계열사, 공시 33종 |
| `fsc-equity-ops-mcp-server` | 금융위 | 배당·권리일정·사고주권·대차·REPO |
| `fsc-industry-mcp-server` | 금융위 | 펀드·퇴직연금·증권사 지표·수수료·금투협 통계 |

## fsc-* 5종의 구조

금융위원회가 개방한 API 110종 중 증권사 업무에 쓰이는 50종
(오퍼레이션 175개)을 데스크별로 나눈 것이다. 전부를 도구로 펼치면
`tools/list`가 커져 다른 서버와 함께 붙일 때 컨텍스트를 잡아먹으므로,
자주 쓰는 26개만 이름 있는 도구로 내고 나머지는
`search_apis` → `call_api`로 연다(dart-mcp-server와 같은 점진적 공개).

```
fsc-common/           ← 원본. 여기만 고친다
  fsc_core.py           공용 클라이언트 (호출·재시도·응답 정규화)
  catalog.json          50 서비스 × 175 오퍼레이션 + 실측 응답 필드
  servers.py            5개 서버의 도구 정의
  sync.py               서버 디렉터리 생성/갱신
fsc-<name>-mcp-server/  ← 생성물. 직접 고치지 말 것
```

```bash
python3 sync.py            # 5개 전부 재생성
python3 sync.py market     # 하나만
```

빌드 컨텍스트가 서버 디렉터리 하나라(`build.sh`의 `gcloud builds submit`)
공유 모듈을 심볼릭 링크로 둘 수 없어 복사한다.

## 카탈로그가 담고 있는 것

`catalog.json`의 각 서비스는 다음을 들고 있고, 전부 **실제 호출로 확인**했다.

| 키 | 왜 필요한가 |
| --- | --- |
| `base_url` | 호출 경로가 `/1160100/service/<서비스>`와 `/1160100/<서비스>` 두 갈래다. 틀리면 권한과 무관하게 `resultCode 12`가 난다 |
| `operations[].fields` | 금융위 API는 **응답 필드명이 곧 필터 파라미터**다. 포털 HTML에 파라미터 명세가 없어 실제 응답에서 수집했다 |
| `operations[].param_style` | 포맷 지정이 `resultType` / `_type` / XML전용으로 갈린다 |

전체 110종의 목록과 도입 우선순위는 `mcp/fsc-open-api-catalog.json`에 있다.

## 인증키

공공데이터포털 인증키는 **계정당 하나**(`STOCK_API_KEY`)이고 fsc-* 5종이 공유한다.
다만 **승인은 API마다 따로** 받는다 — 미승인 API는 같은 키로도 `resultCode 30`이 난다.

키는 디코딩 형태(`+`, `/`, `=` 포함)를 그대로 쓴다. 미리 퍼센트 인코딩하면
이중 인코딩이 되어 실패한다.

## 권한 점검

```bash
python3 check_access.py            # 5개 서버 전부
python3 check_access.py ficc       # 하나만
```

각 API를 실제로 한 번씩 불러 `resultCode`를 본다. 미승인(`30`)이면 활용신청
링크를 함께 출력한다. 포털 화면만 보고 판단하지 않는 이유는, 경로가 두 갈래라
**미승인(`30`)과 경로 오류(`12`)를 헷갈리기 쉽기** 때문이다.

## 호출량 억제 — 캐시 · 최소 간격 · 회로 차단

> [!IMPORTANT]
> **`apis.data.go.kr`은 소스 IP 단위로 접속을 일시 차단한다.** 짧은 시간에 연결을
> 몰아치면 그 IP의 TCP 연결을 수 분~수십 분간 받지 않는다(`ConnectTimeout`).
> 재시도로 뚫으려 하면 차단이 길어질 뿐이다.

2026-09-02에 단계별로 재현해 확인한 내용이다.

| 시점 | 어디서 | 결과 |
| --- | --- | --- |
| 1차 | Cloud Run, TCP+TLS만 | 성공 0.4초 |
| 2차 | Cloud Run, httpx | 성공 HTTP 400, 0.9초 |
| (그 사이 한 서버를 8회 반복 호출 = 재시도 포함 24회 연결) | | |
| 3차 | Cloud Run, httpx | **전부 ConnectTimeout** (루트 경로까지) |
| 같은 시각 | 로컬 · Cloud Build | 정상 |

루트 경로까지 죽는 것은 요청 내용과 무관하다는 뜻이고, 다른 이그레스는 멀쩡한 것은
**소스 IP 단위**라는 뜻이다. Cloud Run 문제도, 코드 문제도 아니다.
고정 이그레스 IP는 오히려 트래픽을 한 IP에 몰아 임계치에 더 빨리 닿게 한다.

`fsc_core.py`가 세 가지로 대응한다. 전부 환경변수로 조정할 수 있다.

| 장치 | 기본값 | 환경변수 | 이유 |
| --- | --- | --- | --- |
| 응답 캐시 | 6시간 / 512건 | `FSC_CACHE_TTL`, `FSC_CACHE_MAX` | 데이터가 D+1로 하루 한 번 갱신되므로 몇 시간 캐시해도 정확도 손실이 없다 |
| 호출 간 최소 간격 | 0.5초 | `FSC_MIN_INTERVAL` | 프로세스 전체에 락으로 걸어 동시 연결이 몰리지 않게 한다 |
| 회로 차단 | 연속 3회 실패 → 300초 정지 | `FSC_BREAKER_THRESHOLD`, `FSC_BREAKER_COOLDOWN` | 차단 중 재시도를 멈춘다. 호출마다 30초씩 버리던 것이 즉시 반환으로 바뀐다 |

연결 실패(`ConnectError` / `ConnectTimeout`)는 **재시도하지 않는다.** 연결이 막힌
상태는 재시도로 풀리지 않기 때문이다. 읽기 타임아웃 등 연결 이후의 실패만 재시도한다.

> 캐시는 인스턴스마다 따로다. Cloud Run이 여러 인스턴스로 퍼지면 그만큼 상류
> 호출이 늘어난다. 완벽한 해법이 아니라 **임계치에 닿지 않게 하는 장치**다.
> 차단이 잦으면 `FSC_MIN_INTERVAL`을 올리고 `FSC_CACHE_TTL`을 늘린다.

진단 상태는 `fsc_core.cache_stats()`로 볼 수 있다.

## 공통 제약## 공통 제약

- **전부 비실시간이다.** 기준일 다음 영업일 13시 이후에 갱신된다. 장중 시세가 아니다.
- 오류가 HTTP 200과 함께 온다. `03`은 데이터 없음(오류 아님), `30`은 미승인,
  `12`는 경로·오퍼레이션명 오류다.
- `apis.data.go.kr`은 앞단에서 TCP 연결을 끊는 구간이 관측된다. 서버가
  지수 백오프로 재시도하지만 긴 장애는 넘기지 못한다.

## 배포

```bash
cd ../terraform
./build.sh fsc-market-mcp     # 또는 인자 없이 전체
terraform apply
```
