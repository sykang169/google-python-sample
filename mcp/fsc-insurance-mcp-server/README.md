# fsc-insurance-mcp-server

실손보험 기준보험료, 생보·손보사 재무와 경영지표, 변액보험 펀드, 보험 가입·사고 통계

금융위원회가 공공데이터포털에 개방한 API 중 **보험** 계열
9종(오퍼레이션 20개)을 MCP 도구로 노출한다.

- 짝이 되는 스킬: 아직 없다. 이 데스크의 도메인 규칙은 시스템 지시로만 걸린다
- Cloud Run 서비스명: `fsc-insurance-mcp`

## 이런 질문에 답한다

| 질문 | 어떻게 |
| --- | --- |
| "40대 남성 실손보험료 회사별로 비교해줘" | get_medical_insurance_premium — 담보·유형을 맞춘다 |
| "생보사 지급여력 지표 보여줘" | get_insurer_indicators(sector='생명보험') |
| "손해보험사 경과손해율 어떻게 돼?" | get_nonlife_insurer_business |
| "삼성생명 총자산 얼마야?" | get_insurer_financials(sector='생명보험') |
| "변액보험 펀드 기준가 알려줘" | get_variable_insurance_fund |
| "자동차보험 사고 피해자 통계 있어?" | search_apis('자동차') + call_api |

## 도구

| 도구 | 내용 |
| --- | --- |
| `search_apis` | 이 서버가 다루는 오퍼레이션 검색. 응답 필드(=필터 파라미터)까지 반환 |
| `call_api` | 찾은 오퍼레이션 실행 |
| `get_medical_insurance_premium` | 실손의료보험 기준보험료를 조회한다. 회사·담보·유형·연령·성별로 갈린다. |
| `get_insurer_financials` | 보험사 재무현황(요약 재무상태표)을 조회한다. 생보·손보 응답 형식이 같다. |
| `get_insurer_indicators` | 보험사 주요경영지표를 조회한다. 지급여력·수익성 등 업권 지표. |
| `get_nonlife_insurer_business` | 손해보험사 주요영업활동을 조회한다. 보종별 경과손해율이 핵심이다. |
| `get_variable_insurance_fund` | 변액보험 펀드별 기준가와 순자산을 조회한다. |

이름 있는 도구는 자주 쓰는 경로만 감싼 것이다. 나머지는 `search_apis` →
`call_api` 순으로 접근한다. 전부 도구로 펼치면 `tools/list`가 커져 다른 MCP
서버와 함께 붙일 때 컨텍스트를 잡아먹기 때문이다.

## 필요한 data.go.kr 활용신청

인증키는 공공데이터포털 계정당 **하나**(`STOCK_API_KEY`)이고 이 저장소의 fsc-*
서버 6종이 공유한다. 다만 **승인은 API마다 따로** 받아야 하며, 미승인 API는
같은 키로도 `resultCode 30`이 난다(HTTP 403과 함께 오기도 한다).

이 서버가 도는 데 필요한 것은 아래 9건이고, **각각 따로 승인되어 있어야
한다.** 이미 승인된 것도 있을 수 있으니 아래 명령으로 먼저 확인한다.

| 서비스 | 이름 | 활용신청 |
| --- | --- | --- |
| `GetLifeInsuCompInfoService` | 금융통계생명보험정보 | [신청](https://www.data.go.kr/data/15061306/openapi.do) |
| `GetNonlInsuCompInfoService` | 금융통계손해보험정보 | [신청](https://www.data.go.kr/data/15061307/openapi.do) |
| `GetVariableInsuranceInfoService` | 변액보험기본정보 | [신청](https://www.data.go.kr/data/15094793/openapi.do) |
| `GetLifeAccInfoService` | 생명보험 사고원인정보 | [신청](https://www.data.go.kr/data/15151237/openapi.do) |
| `GetFPLifeInsuJoinInfoService` | 생명보험가입정보 | [신청](https://www.data.go.kr/data/15124892/openapi.do) |
| `GetMedicalReimbursementInsuranceInfoService` | 실손보험정보 | [신청](https://www.data.go.kr/data/15094797/openapi.do) |
| `GetFPPptInsuJoinInfoService` | 일반손해보험가입정보 | [신청](https://www.data.go.kr/data/15124894/openapi.do) |
| `GetAutoInsVicInfoService` | 자동차보험 피해자 통계정보 | [신청](https://www.data.go.kr/data/15151234/openapi.do) |
| `GetFPAtmbInsujoinInfoService` | 자동차보험가입정보 | [신청](https://www.data.go.kr/data/15124891/openapi.do) |

승인 여부는 실제 호출로만 알 수 있다. 저장소 루트에서:

```bash
python3 mcp/fsc-common/check_access.py insurance
```

## 주의

보험료는 회사가 실제로 청구하는 값이 아니라 공시 기준 보험료다. 담보·유형·연령·성별이 같아야 비교가 성립하며, 조건이 다르면 숫자가 달라도 우열이 아니다. 업권 지표는 생보와 손보의 계정 체계가 달라 서로 직접 빼지 않는다.

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
cd ../terraform && ./build.sh fsc-insurance-mcp && terraform apply
```

## 생성 파일

`server.py`, `fsc_core.py`, `catalog.json`, 이 README는 `mcp/fsc-common/`에서
생성된다. 여기서 직접 고치지 말고 원본을 고친 뒤 `python3 sync.py`를 다시 실행한다.
