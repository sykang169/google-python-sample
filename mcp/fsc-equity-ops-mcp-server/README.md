# fsc-equity-ops-mcp-server

주식 배당·권리일정·사고주권·발행, 주식/채권 대차, REPO 금리와 거래

금융위원회가 공공데이터포털에 개방한 API 중 **권리·대차** 계열
12종(오퍼레이션 31개)을 MCP 도구로 노출한다.

- 짝이 되는 스킬: [`kr-equity-operations`](../../skills/kr-equity-operations/SKILL.md)
- Cloud Run 서비스명: `fsc-equity-ops-mcp`

## 이런 질문에 답한다

| 질문 | 어떻게 |
| --- | --- |
| "이 주권 사고 등록된 거 아니야?" | check_irregular_stock — 실패를 '이상 없음'으로 답하지 않는다 |
| "다음 달 배당 기준일인 종목 알려줘" | get_dividend |
| "이번 분기 청약 일정 정리해줘" | get_right_schedule |
| "대차잔고 높은 종목 보여줘" | get_stock_lending — 대차 ≠ 공매도 |
| "REPO 금리 추이 보여줘" | get_repo_rate (담보 종류별로 갈린다) |

## 도구

| 도구 | 내용 |
| --- | --- |
| `search_apis` | 이 서버가 다루는 오퍼레이션 검색. 응답 필드(=필터 파라미터)까지 반환 |
| `call_api` | 찾은 오퍼레이션 실행 |
| `get_dividend` | 주식 배당정보(기준일·금액)를 조회한다. 배당락 처리와 고객 안내의 근거. |
| `get_right_schedule` | 권리행사 사유별 일정을 조회한다. 청약·행사 업무의 달력. |
| `check_irregular_stock` | 사고주권 여부를 조회한다. 실물 입고 심사에서 확인이 필요한 항목이다. |
| `get_stock_lending` | 주식 대차 현황을 조회한다. 대차잔고는 공매도 압력의 대리지표로 읽히지만, |
| `get_repo_rate` | REPO 금리를 조회한다. 단기 조달비용의 기준. |

이름 있는 도구는 자주 쓰는 경로만 감싼 것이다. 나머지는 `search_apis` →
`call_api` 순으로 접근한다. 전부 도구로 펼치면 `tools/list`가 커져 다른 MCP
서버와 함께 붙일 때 컨텍스트를 잡아먹기 때문이다.

## 필요한 data.go.kr 활용신청

인증키는 공공데이터포털 계정당 **하나**(`STOCK_API_KEY`)이고 이 저장소의 fsc-*
서버 5종이 공유한다. 다만 **승인은 API마다 따로** 받아야 하며, 미승인 API는
같은 키로도 `resultCode 30`이 난다.

이 서버를 쓰려면 아래 12건을 각각 활용신청해야 한다.

| 서비스 | 이름 | 활용신청 |
| --- | --- | --- |
| `GetRepoTradInfoService_V2` | REPO거래정보 | [신청](https://www.data.go.kr/data/15059598/openapi.do) |
| `GetRepoItemInfoService_V2` | REPO종목정보 | [신청](https://www.data.go.kr/data/15059610/openapi.do) |
| `GetDrForeSecuSettInfoService_V2` | 국제거래외화증권예탁결제정보 | [신청](https://www.data.go.kr/data/15043445/openapi.do) |
| `GetDrTradItemInfoService_V2` | 국제거래종목정보 | [신청](https://www.data.go.kr/data/15059582/openapi.do) |
| `GetPreeRighSecuIssuInfoService_V2` | 신주인수권증권발행정보 | [신청](https://www.data.go.kr/data/15043461/openapi.do) |
| `GetStocRighScheService_V2` | 주식권리일정정보 | [신청](https://www.data.go.kr/data/15059609/openapi.do) |
| `GetStocLendBorrInfoService_V2` | 주식대차정보 | [신청](https://www.data.go.kr/data/15059612/openapi.do) |
| `GetStocIssuInfoService_V3` | 주식발행정보 | [신청](https://www.data.go.kr/data/15043423/openapi.do) |
| `GetStocDiviInfoService_V2` | 주식배당정보 | [신청](https://www.data.go.kr/data/15043284/openapi.do) |
| `GetStocTradInfoService_V2` | 주식분포및사고주권정보 | [신청](https://www.data.go.kr/data/15043364/openapi.do) |
| `GetCMBondLnbInfoService` | 채권대차거래정보 | [신청](https://www.data.go.kr/data/15124889/openapi.do) |
| `GetBondLendBorrInfoService_V2` | 채권대차정보 | [신청](https://www.data.go.kr/data/15043462/openapi.do) |

승인 여부는 실제 호출로만 알 수 있다. 저장소 루트에서:

```bash
python3 mcp/fsc-common/check_access.py equity-ops
```

## 주의

권리업무와 백오피스 판단에 쓰는 데이터다. 사고주권 조회처럼 결과가 업무 처리를 가르는 것이 있으므로, 조회 실패를 '해당 없음'으로 답하지 않도록 주의한다.

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
cd ../terraform && ./build.sh fsc-equity-ops-mcp && terraform apply
```

## 생성 파일

`server.py`, `fsc_core.py`, `catalog.json`, 이 README는 `mcp/fsc-common/`에서
생성된다. 여기서 직접 고치지 말고 원본을 고친 뒤 `python3 sync.py`를 다시 실행한다.
