# fsc-ficc-mcp-server

채권 기본·발행·권리행사·권리일정, CP/CD 매매금리, 소매채권 수익률, 채무증권 발행실적(DCM)

금융위원회가 공공데이터포털에 개방한 API 중 **채권·단기자금** 계열
9종(오퍼레이션 31개)을 MCP 도구로 노출한다.

- 짝이 되는 스킬: [`kr-bond-ficc-analysis`](../../skills/kr-bond-ficc-analysis/SKILL.md)
- Cloud Run 서비스명: `fsc-ficc-mcp`

## 이런 질문에 답한다

| 질문 | 어떻게 |
| --- | --- |
| "이 회사채 국고채 대비 스프레드가 얼마야?" | get_bond_basic + ECOS (서버 2개) |
| "다음 분기에 콜 행사 가능한 채권 목록" | get_bond_call_redemption |
| "CP 91일물 금리가 기준금리 대비 어떻게 움직였어?" | get_short_term_rate + ECOS |
| "지금 리테일에 팔 만한 채권 수익률 알려줘" | get_retail_bond_yield (구간별 요약) |
| "이 채권 이자지급일 언제야" | get_bond_right_schedule |
| "올해 회사채 발행 규모 상위 보여줘" | search_apis('발행실적') + call_api |

## 도구

| 도구 | 내용 |
| --- | --- |
| `search_apis` | 이 서버가 다루는 오퍼레이션 검색. 응답 필드(=필터 파라미터)까지 반환 |
| `call_api` | 찾은 오퍼레이션 실행 |
| `get_bond_basic` | 채권 기본정보(마스터)를 조회한다. 종목 식별의 출발점이다. |
| `get_bond_principal_interest` | 채권 원리금 정보를 조회한다. 캐시플로 산출의 근거. |
| `get_bond_right_schedule` | 채권 권리행사 일정(이자지급·상환)을 조회한다. |
| `get_bond_call_redemption` | 옵션부채권의 조기상환(콜) 내역을 조회한다. 콜 리스크 점검용. |
| `get_retail_bond_yield` | 소매채권 수익률을 조회한다. 리테일 채권 판매에 바로 쓰이는 값이다. |
| `get_short_term_rate` | 단기금융증권(CP·CD)의 매매 금액·금리를 조회한다. |

이름 있는 도구는 자주 쓰는 경로만 감싼 것이다. 나머지는 `search_apis` →
`call_api` 순으로 접근한다. 전부 도구로 펼치면 `tools/list`가 커져 다른 MCP
서버와 함께 붙일 때 컨텍스트를 잡아먹기 때문이다.

## 필요한 data.go.kr 활용신청

인증키는 공공데이터포털 계정당 **하나**(`STOCK_API_KEY`)이고 이 저장소의 fsc-*
서버 5종이 공유한다. 다만 **승인은 API마다 따로** 받아야 하며, 미승인 API는
같은 키로도 `resultCode 30`이 난다.

이 서버를 쓰려면 아래 9건을 각각 활용신청해야 한다.

| 서비스 | 이름 | 활용신청 |
| --- | --- | --- |
| `GetShorTermSecuTradInfoService_V2` | 단기금융증권거래정보 | [신청](https://www.data.go.kr/data/15043446/openapi.do) |
| `GetShorTermSecuIssuInfoService_V2` | 단기금융증권발행정보 | [신청](https://www.data.go.kr/data/15059591/openapi.do) |
| `GetCMSctBondInfoService` | 사회적채권정보 | [신청](https://www.data.go.kr/data/15124847/openapi.do) |
| `GetBondInfoService` | 소매채권수익률정보 | [신청](https://www.data.go.kr/data/15094783/openapi.do) |
| `GetPBFincDiscInfoService` | 자금조달 공시정보 | [신청](https://www.data.go.kr/data/15139255/openapi.do) |
| `GetBondRighScheInfoService_V2` | 채권권리일정정보 | [신청](https://www.data.go.kr/data/15059611/openapi.do) |
| `GetBondRedeInfoService_V2` | 채권권리행사정보 | [신청](https://www.data.go.kr/data/15059595/openapi.do) |
| `GetBondIssuInfoService_V2` | 채권기본정보 | [신청](https://www.data.go.kr/data/15059592/openapi.do) |
| `GetBondTradInfoService_V2` | 채권발행정보 | [신청](https://www.data.go.kr/data/15043421/openapi.do) |

승인 여부는 실제 호출로만 알 수 있다. 저장소 루트에서:

```bash
python3 mcp/fsc-common/check_access.py ficc
```

## 주의

거시 금리 지표(기준금리, 국고채 시장금리)는 이 서버가 아니라 한국은행 ECOS에 있다. 스프레드를 계산하려면 두 소스를 함께 써야 한다.

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
cd ../terraform && ./build.sh fsc-ficc-mcp && terraform apply
```

## 생성 파일

`server.py`, `fsc_core.py`, `catalog.json`, 이 README는 `mcp/fsc-common/`에서
생성된다. 여기서 직접 고치지 말고 원본을 고친 뒤 `python3 sync.py`를 다시 실행한다.
