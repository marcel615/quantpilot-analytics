# Current Task

- **작업** [QP-11 여러 보유 희망 종목의 하락 방어 후보 비교](https://marcel615.atlassian.net/browse/QP-11). 사용자의 사이클 재개 요청에 따른 위임으로 QP-12 명세 병합과 선행 조건 충족을 확인하고 착수했다.
- **공식 원본** Specs main `7d46cb83a9fe49af0cbababfe74c839951a90560`의 [요구사항](https://github.com/marcel615/quantpilot-specs/blob/7d46cb83a9fe49af0cbababfe74c839951a90560/docs/requirements.md)과 [분석 명세](https://github.com/marcel615/quantpilot-specs/blob/7d46cb83a9fe49af0cbababfe74c839951a90560/docs/analytics-spec.md).
- **구현** `downside --holdings`에 두세 종목과 합계 100%의 양의 목표 비중을 입력한다. 고정 비중 수익률로 급락일을 선정하고 기준 포트폴리오, 20% 현금, 20% 후보 ETF를 기존 일봉·기간·품질 규칙으로 비교한다. 기존 단일 NVDA 실행을 회귀 검증한다.
- **수용 검증** 손계산, 비중과 종목 검증, 정밀 급락 경계, 기간 격리, 기준 종목 일봉 누락 및 실제 IEX 재조회 결과를 확인한다.
