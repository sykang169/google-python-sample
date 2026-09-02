# fsc-research-mcp-server

기업 개요·계열사·종속기업, 정규화 재무제표, 공시 32종, 지배구조, ESG 지수

금융위원회가 공공데이터포털에 개방한 API 중 **기업분석·공시** 계열
7종(오퍼레이션 45개)을 MCP 도구로 노출한다.

- 짝이 되는 스킬: [`kr-corporate-financials`](../../skills/kr-corporate-financials/SKILL.md)
- Cloud Run 서비스명: `fsc-research-mcp`

## 이런 질문에 답한다

| 질문 | 어떻게 |
| --- | --- |
| "이 회사 부채비율 계산해줘" | get_corp_outline → get_financial_statement |
| "계열회사 목록 보여줘" | get_affiliates |
| "최근 유상증자 결정 공시 있었어?" | search_apis('유상증자') + call_api |
| "자기주식 취득 공시 확인해줘" | search_apis('자기주식') + call_api |
| "2010년 재무제표도 볼 수 있어?" | get_financial_statement (DART는 2015년 이후만) |

## 도구

| 도구 | 내용 |
| --- | --- |
| `search_apis` | 이 서버가 다루는 오퍼레이션 검색. 응답 필드(=필터 파라미터)까지 반환 |
| `call_api` | 찾은 오퍼레이션 실행 |
| `get_financial_statement` | 재무상태표를 조회한다. DART XBRL 파싱 없이 정규화된 계정 값을 받는다. |
| `get_corp_outline` | 기업 개요를 조회한다. 법인등록번호(crno) 확정의 출발점. |
| `get_affiliates` | 계열회사 목록을 조회한다. 지배구조 맵을 그릴 때 쓴다. |
| `get_disclosure` | 배당 공시를 조회한다. 이 서비스에는 유상증자·합병 등 32종의 공시 |

이름 있는 도구는 자주 쓰는 경로만 감싼 것이다. 나머지는 `search_apis` →
`call_api` 순으로 접근한다. 전부 도구로 펼치면 `tools/list`가 커져 다른 MCP
서버와 함께 붙일 때 컨텍스트를 잡아먹기 때문이다.

## 필요한 data.go.kr 활용신청

인증키는 공공데이터포털 계정당 **하나**(`STOCK_API_KEY`)이고 이 저장소의 fsc-*
서버 5종이 공유한다. 다만 **승인은 API마다 따로** 받아야 하며, 미승인 API는
같은 키로도 `resultCode 30`이 난다.

이 서버를 쓰려면 아래 7건을 각각 활용신청해야 한다.

| 서비스 | 이름 | 활용신청 |
| --- | --- | --- |
| `GetESGIdxInfoService` | ESG지수정보 | [신청](https://www.data.go.kr/data/15151180/openapi.do) |
| `GetDiscInfoService_V2` | 공시정보 | [신청](https://www.data.go.kr/data/15059649/openapi.do) |
| `GetFinaStatInfoService_V2` | 기업 재무정보 | [신청](https://www.data.go.kr/data/15043459/openapi.do) |
| `GetCorpBasicInfoService_V2` | 기업기본정보 | [신청](https://www.data.go.kr/data/15043184/openapi.do) |
| `GetCGDiscInfoService` | 기업지배구조 공시정보 | [신청](https://www.data.go.kr/data/15151165/openapi.do) |
| `GetStkIssuInfoService` | 주식발행 공시정보 | [신청](https://www.data.go.kr/data/15150946/openapi.do) |
| `GetCorpGoveInfoService` | 지배구조정보 | [신청](https://www.data.go.kr/data/15059597/openapi.do) |

승인 여부는 실제 호출로만 알 수 있다. 저장소 루트에서:

```bash
python3 mcp/fsc-common/check_access.py research
```

## 주의

DART(전자공시)와 겹치는 영역이 있다. 이 서버는 정규화된 표 형태라 계산에 바로 쓰기 좋고, 원문 공시 전문이나 XBRL이 필요하면 DART 쪽을 쓴다.

- **전부 비실시간이다.** 기준일 다음 영업일 13시 이후에 갱신된다.
- 오류가 HTTP 200과 함께 온다. `resultCode 03`은 데이터 없음(오류 아님),
  `30`은 활용신청 미승인, `12`는 경로나 오퍼레이션명 오류다.
  **`12`를 미승인으로 읽지 않는다.**
- **`apis.data.go.kr`은 소스 IP 단위로 접속을 일시 차단한다.** 짧은 시간에 호출을
  몰아치면 그 IP의 TCP 연결을 수 분~수십 분간 받지 않는다. 서버가 응답 캐시(6시간),
  호출 간 최소 간격(0.5초), 회로 차단(연속 3회 실패 → 300초 정지)으로 대응하지만
  완전히 막지는 못한다. `ConnectTimeout`이 반복되면 코드나 키가 아니라 이쪽이다
  (`../fsc-common/README.md`의 "호출량 억제" 참고).
- 5개 fsc 서버가 같은 상류를 쓴다. **한 서버가 몰아치면 나머지도 함께 막힌다.**

## 실행

```bash
export STOCK_API_KEY="..."      # 디코딩 형태 그대로. 퍼센트 인코딩하지 말 것
pip install -r requirements.txt
python server.py                # http://localhost:8080/mcp
```

## 배포

```bash
cd ../terraform && ./build.sh fsc-research-mcp && terraform apply
```

## 생성 파일

`server.py`, `fsc_core.py`, `catalog.json`, 이 README는 `mcp/fsc-common/`에서
생성된다. 여기서 직접 고치지 말고 원본을 고친 뒤 `python3 sync.py`를 다시 실행한다.
