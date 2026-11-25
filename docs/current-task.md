# Current Task

- **작업** [QP-1 보유 희망 종목 한 개의 하락 방어 후보 비교](https://marcel615.atlassian.net/browse/QP-1). 사용자가 2026-11-25 18:02 KST에 Jira를 착수 가능으로 전환했다. QP-2와 QP-5의 IEX 일봉 정제를 재사용하며 선행 QP-10은 완료됐다.
- **공식 원본** Specs main `2974ead957829dadca8103b6f77bdde9b455474c`의 [요구사항](https://github.com/marcel615/quantpilot-specs/blob/2974ead957829dadca8103b6f77bdde9b455474c/docs/requirements.md)과 [분석 명세](https://github.com/marcel615/quantpilot-specs/blob/2974ead957829dadca8103b6f77bdde9b455474c/docs/analytics-spec.md).
- **구현** 고정 후보 최대 10개와 NVDA의 USD 분할조정 일봉을 메모리에서 검증한다. 2016년 이후 공통 거래일부터 2025년 마지막 거래일까지 후보를 선별하고 NVDA 급락 경계를 계산한다. 2026년 검증에는 NVDA 단독, 현금 20%, 후보 20%를 각 거래일의 목표 비중으로 비교한다. 실행 결과에 기간, 입력 SHA-256, 후보별 품질·제외 사유와 지표를 남긴다.
- **검증** 손계산, 거래일 누락, 경계 동률, 급락일 9일과 10일, 현금 차이 0, 최근 3년 음수 후보, 검증 데이터 누출, 입력 식별자 재현과 장 마감을 합성 입력에서 확인했다. 승인된 Alpaca 일봉으로 8개 후보의 수용 검증을 두 번 실행했고 입력 SHA-256과 전체 결과가 일치했다.
