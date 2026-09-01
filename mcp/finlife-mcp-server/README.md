# FINLIFE MCP Server

금융감독원 **금융상품통합비교공시**(finlife.fss.or.kr)를 MCP 도구로 노출한다.
예금·적금·대출 상품의 **금융회사별 실제 판매 금리**를 조회한다.

## 도구 6개

| 도구 | 대상 | 은행 기준 |
|---|---|---|
| `search_deposit_products` | 정기예금 | 38건 |
| `search_savings_products` | 적금 | 59건 |
| `search_mortgage_loans` | 주택담보대출 | 34건 |
| `search_rent_house_loans` | 전세자금대출 | 41건 |
| `search_credit_loans` | 개인신용대출 | 44건 |
| `list_financial_companies` | 금융회사 목록·영업지역 | 18곳 |

전부 `readOnlyHint: true`라 Gemini Enterprise에서 확인 팝업 없이 호출된다.

## 다른 서버와의 경계

```
finlife-mcp   금융상품 금리   "예금 금리 어디가 제일 높아", "신용점수 800점 대출금리"
ecos-mcp      거시 통계       "기준금리 추이", "원/달러 환율"
dart-mcp      기업 공시       "삼성전자 배당", "임원 현황"
stock-mcp     주식 시세       "삼성전자 어제 종가"
```

ECOS와 헷갈리기 쉽다 — ECOS는 **한국은행 기준금리 같은 거시 지표**이고,
FINLIFE는 **개별 금융회사가 실제로 파는 상품의 금리**다.

## 이 서버가 하는 일 — baseList/optionList 조인

FINLIFE API는 응답을 두 배열로 쪼개서 준다:

```
baseList    상품 정보 (회사명, 상품명, 가입방법, 우대조건 …)
optionList  조건별 금리 (예금은 기간별, 대출은 담보/상환방식별 …)
```

둘은 `(fin_co_no, fin_prdt_cd)`로 연결되는데, LLM에게 두 배열을 던져 주고
조인하라고 하면 틀리기 쉽다. 이 서버가 조인해서 **상품 하나에 `options`가 붙은
형태**로 돌려준다.

```json
{
  "total_count": 392, "page_no": 1, "max_page_no": 4,
  "disclosure_months": ["202608"],
  "products": [{
    "kor_co_nm": "HB저축은행", "fin_prdt_nm": "스마트회전정기예금",
    "spcl_cnd": "...", "join_way": "...",
    "options": [{"save_trm": "12", "intr_rate": 4.0, "intr_rate2": 4.02,
                 "intr_rate_type_nm": "단리"}]
  }]
}
```

## optionList 스키마가 상품군마다 다르다

도구를 상품군별로 나눈 이유다.

| 상품군 | options 주요 필드 |
|---|---|
| 예금·적금 | `save_trm`(기간), `intr_rate`(기본), `intr_rate2`(최고우대), `rsrv_type_nm`(적립유형, 적금만) |
| 주택담보대출 | `mrtg_type_nm`(담보유형), `rpay_type_nm`(상환방식), `lend_rate_type_nm`(고정/변동), `lend_rate_min/max/avg` |
| 전세자금대출 | 위와 같으나 `mrtg_type` 없음 |
| 개인신용대출 | `crdt_grad_*`(신용점수 구간별 금리), `crdt_grad_avg` |

### 신용대출의 신용점수 구간

숫자가 클수록 높은 점수 구간이 아니다 — 필드명의 숫자는 구간 번호다:

```
crdt_grad_1    900점 초과      crdt_grad_10   501~600점
crdt_grad_4    801~900점       crdt_grad_11   401~500점
crdt_grad_5    701~800점       crdt_grad_12   301~400점
crdt_grad_6    601~700점       crdt_grad_13   300점 이하
crdt_grad_avg  평균
```

값이 `None`인 구간은 그 회사가 해당 구간에 대출을 취급하지 않는다는 뜻이다.

## 금융권역 (`group`)

한글 이름 또는 코드로 지정한다. **상품군마다 데이터가 있는 권역이 다르다.**

| 권역 | 코드 | 회사 수 |
|---|---|---|
| 은행 | 020000 | 18 |
| 저축은행 | 030300 | 80 |
| 여신전문 | 030200 | 48 |
| 보험 | 050000 | 20 |
| 금융투자 | 060000 | 7 |

정기예금은 은행(38건)·저축은행(392건)에만 있고 보험·금융투자에는 없다.
저축은행은 페이지가 여러 개다(`max_page_no` 확인).

## 배포

인프라는 `mcp/terraform/`이 관리한다.

```bash
cd ../terraform
./build.sh finlife-mcp    # 이미지 빌드 + 태그 기록
terraform apply           # 새 리비전 배포
```

`FINLIFE_API_KEY`는 Secret Manager에서 주입되며 이미지에 굽지 않는다.

## 검증

```bash
URL=https://finlife-mcp-<PROJECT_NUMBER>.us-central1.run.app/mcp
bash ~/.claude/skills/gemini-enterprise-custom-mcp/scripts/probe_mcp_server.sh \
  "$URL" "$(gcloud auth print-identity-token)"
```

## 참고

- 오류는 HTTP 200과 함께 `result.err_cd`로 온다. 상태 코드만 보면 안 된다.
- 공시월(`dcls_month`)은 응답 최상위가 아니라 각 상품 항목에 들어 있다.
  이 서버가 모아서 `disclosure_months`로 올려 준다.
- HTTPS를 지원한다(공식 예시는 http).
