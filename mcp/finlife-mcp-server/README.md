# FINLIFE MCP Server

금융감독원 **금융상품통합비교공시**(finlife.fss.or.kr)를 MCP 도구로 노출하는
서버입니다. 예금·적금·대출 상품의 **금융회사별 실제 판매 금리**를 조회합니다.

한국은행 기준금리 같은 거시 지표(ECOS)와 혼동하기 쉬운데, 이쪽은 개별 금융회사가
실제로 파는 상품의 금리입니다.

## 도구 6개

| 도구 | 대상 | 은행 기준 건수 |
|---|---|---|
| `search_deposit_products` | 정기예금 | 38 |
| `search_savings_products` | 적금 | 59 |
| `search_mortgage_loans` | 주택담보대출 | 34 |
| `search_rent_house_loans` | 전세자금대출 | 41 |
| `search_credit_loans` | 개인신용대출 | 44 |
| `list_financial_companies` | 금융회사 목록·영업지역 | 18곳 |

모두 조회 전용이라 Gemini Enterprise에서 확인 프롬프트 없이 호출됩니다.

## 응답 형태

FINLIFE API는 상품 정보와 금리를 별도 배열로 주는데, 이 서버가 합쳐서 상품 하나에
`options`가 붙은 형태로 반환합니다.

```json
{
  "total_count": 392, "page_no": 1, "max_page_no": 4,
  "disclosure_months": ["202608"],
  "products": [{
    "kor_co_nm": "HB저축은행",
    "fin_prdt_nm": "스마트회전정기예금",
    "spcl_cnd": "우대조건 …",
    "options": [
      { "save_trm": "12", "intr_rate": 4.0, "intr_rate2": 4.02,
        "intr_rate_type_nm": "단리" }
    ]
  }]
}
```

`intr_rate`가 기본금리, `intr_rate2`가 우대조건을 모두 충족했을 때의 최고금리입니다.
우대조건은 상품의 `spcl_cnd`에 적혀 있습니다.

## 상품군마다 `options` 항목이 다릅니다

| 상품군 | 주요 필드 |
|---|---|
| 예금·적금 | `save_trm`(기간), `intr_rate`(기본), `intr_rate2`(최고우대), `rsrv_type_nm`(적립유형, 적금만) |
| 주택담보대출 | `mrtg_type_nm`(담보유형), `rpay_type_nm`(상환방식), `lend_rate_type_nm`(고정/변동), `lend_rate_min`/`max`/`avg` |
| 전세자금대출 | 위와 같으나 담보유형 없음 |
| 개인신용대출 | `crdt_grad_*`(신용점수 구간별 금리), `crdt_grad_avg` |

### 신용대출의 신용점수 구간

필드명의 숫자는 점수가 아니라 구간 번호입니다.

```
crdt_grad_1    900점 초과      crdt_grad_10   501~600점
crdt_grad_4    801~900점       crdt_grad_11   401~500점
crdt_grad_5    701~800점       crdt_grad_12   301~400점
crdt_grad_6    601~700점       crdt_grad_13   300점 이하
crdt_grad_avg  평균
```

값이 `null`인 구간은 그 회사가 해당 구간에 대출을 취급하지 않는다는 뜻입니다.

## 금융권역 지정

`group` 인자에 한글 이름이나 코드를 넣습니다.

| 권역 | 코드 | 회사 수 |
|---|---|---|
| 은행 | `020000` | 18 |
| 저축은행 | `030300` | 80 |
| 여신전문 | `030200` | 48 |
| 보험 | `050000` | 20 |
| 금융투자 | `060000` | 7 |

**상품군마다 데이터가 있는 권역이 다릅니다.** 정기예금은 은행(38건)과
저축은행(392건)에만 있고 보험·금융투자에는 없습니다. 저축은행은 결과가 여러
페이지에 나뉘므로 `max_page_no`를 확인하고 필요하면 다음 페이지를 조회해 주세요.

## 배포

인프라는 [`../terraform`](../terraform)이 관리합니다.

```bash
cd ../terraform
./build.sh finlife-mcp    # 이미지 빌드
terraform apply           # 새 리비전 배포
```

`FINLIFE_API_KEY`는 Secret Manager에서 주입되며 이미지에는 포함되지 않습니다.

## 확인

```bash
URL=https://finlife-mcp-<PROJECT_NUMBER>.asia-northeast3.run.app/mcp

curl -sN --max-time 30 -X POST "$URL" \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

## 참고

응답의 `disclosure_months`는 공시 기준월(YYYYMM)입니다. 금융회사가 매월 제출하므로
데이터가 언제 기준인지 답변에 함께 밝히시는 편이 좋습니다.
