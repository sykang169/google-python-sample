# fsc-industry-mcp-server

펀드 표준코드·판매현황, 퇴직연금, 증권사 경영지표·수수료 공시, 금투협 통계

금융위원회가 공공데이터포털에 개방한 API 중 **상품·업계** 계열
15종(오퍼레이션 52개)을 MCP 도구로 노출한다.

- 짝이 되는 스킬: [`kr-product-comparison`](../../skills/kr-product-comparison/SKILL.md)
- Cloud Run 서비스명: `fsc-industry-mcp`

## 이런 질문에 답한다

| 질문 | 어떻게 |
| --- | --- |
| "우리 수수료가 경쟁사 대비 어디쯤이야?" | get_brokerage_fee — 거래금액 구간을 맞춘다 |
| "펀드 판매 점유율 순위 보여줘" | get_fund_sales — 모집단을 밝힌다 |
| "업계 ELS 발행 규모 알려줘" | search_apis('ELS') + call_api |
| "IRP 라인업에 넣을 펀드 후보" | get_fund_code + search_apis('퇴직연금') |
| "경쟁 증권사 경영지표 비교해줘" | get_securities_firm_stats — basYm 필수 |

## 도구

| 도구 | 내용 |
| --- | --- |
| `search_apis` | 이 서버가 다루는 오퍼레이션 검색. 응답 필드(=필터 파라미터)까지 반환 |
| `call_api` | 찾은 오퍼레이션 실행 |
| `get_fund_code` | 펀드 표준코드를 조회한다. 판매 상품 마스터. |
| `get_fund_sales` | 펀드 판매현황을 조회한다. 판매기관·고객유형·펀드유형별 점유율을 본다. |
| `get_securities_firm_stats` | 증권사 일반현황을 조회한다. 재무·경영지표는 search_apis로 같은 서비스의 |
| `get_brokerage_fee` | 증권사 주식거래 수수료 공시를 조회한다. 가격 경쟁 포지션 확인용. |
| `get_kofia_stat` | 금융투자협회 종합통계를 조회한다. CMA 잔고 외에 펀드 순자산·신탁 규모 등은 |

이름 있는 도구는 자주 쓰는 경로만 감싼 것이다. 나머지는 `search_apis` →
`call_api` 순으로 접근한다. 전부 도구로 펼치면 `tools/list`가 커져 다른 MCP
서버와 함께 붙일 때 컨텍스트를 잡아먹기 때문이다.

## 필요한 data.go.kr 활용신청

인증키는 공공데이터포털 계정당 **하나**(`STOCK_API_KEY`)이고 이 저장소의 fsc-*
서버 5종이 공유한다. 다만 **승인은 API마다 따로** 받아야 하며, 미승인 API는
같은 키로도 `resultCode 30`이 난다.

이 서버를 쓰려면 아래 15건을 각각 활용신청해야 한다.

| 서비스 | 이름 | 활용신청 |
| --- | --- | --- |
| `GetESGPdInfoService` | ESG증권상품 정보 | [신청](https://www.data.go.kr/data/15151192/openapi.do) |
| `GetISAInfoService_V2` | ISA다모아정보 | [신청](https://www.data.go.kr/data/15094788/openapi.do) |
| `GetTrusBusiInfoService` | 금융통계공통(신탁)정보 | [신청](https://www.data.go.kr/data/15061195/openapi.do) |
| `GetDeriBusiInfoService` | 금융통계공통(파생상품)정보 | [신청](https://www.data.go.kr/data/15061288/openapi.do) |
| `GetDomeBankInfoService` | 금융통계국내은행정보 | [신청](https://www.data.go.kr/data/15061304/openapi.do) |
| `GetFutuCompInfoService` | 금융통계선물사정보 | [신청](https://www.data.go.kr/data/15061357/openapi.do) |
| `GetAsseManaCompInfoService` | 금융통계자산운용사정보 | [신청](https://www.data.go.kr/data/15061325/openapi.do) |
| `GetSecuCompInfoService` | 금융통계증권사정보 | [신청](https://www.data.go.kr/data/15061320/openapi.do) |
| `GetEtcOfficialNoticeInfoService_V2` | 금융투자협회기타공시정보 | [신청](https://www.data.go.kr/data/15094799/openapi.do) |
| `GetKofiaStatisticsInfoService` | 금융투자협회종합통계정보 | [신청](https://www.data.go.kr/data/15094809/openapi.do) |
| `GetOfficialNoticeInfoService` | 금융투자회사공시정보 | [신청](https://www.data.go.kr/data/15094795/openapi.do) |
| `GetFnCoDiscInfoService_V2` | 금융회사공시정보 | [신청](https://www.data.go.kr/data/15059651/openapi.do) |
| `GetRetirementPensionInfoService` | 퇴직연금기본정보 | [신청](https://www.data.go.kr/data/15094798/openapi.do) |
| `GetFdSaleInfoService_V2` | 펀드상품 판매현황정보 | [신청](https://www.data.go.kr/data/15151230/openapi.do) |
| `GetFundProductInfoService` | 펀드상품기본정보 | [신청](https://www.data.go.kr/data/15094792/openapi.do) |

승인 여부는 실제 호출로만 알 수 있다. 저장소 루트에서:

```bash
python3 mcp/fsc-common/check_access.py industry
```

## 주의

자사와 경쟁사를 같은 잣대로 비교할 때 쓴다. 특정 회사를 유리하거나 불리하게 보이도록 지표를 골라 제시하지 않는다.

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
cd ../terraform && ./build.sh fsc-industry-mcp && terraform apply
```

## 생성 파일

`server.py`, `fsc_core.py`, `catalog.json`, 이 README는 `mcp/fsc-common/`에서
생성된다. 여기서 직접 고치지 말고 원본을 고친 뒤 `python3 sync.py`를 다시 실행한다.
