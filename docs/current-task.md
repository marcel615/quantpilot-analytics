# Current Task

- **작업** [QP-4](https://marcel615.atlassian.net/browse/QP-4). 사용자가 요청한 퀀트파일럿 사이클의 빈 Jira 후보를 재사용했다.
- **공식 원본** [QP-14](https://marcel615.atlassian.net/browse/QP-14)의 [요구사항](https://github.com/marcel615/quantpilot-specs/blob/4b98783213447210368a591b4ea2a0cd1b910837/docs/requirements.md)과 [분석 명세](https://github.com/marcel615/quantpilot-specs/blob/4b98783213447210368a591b4ea2a0cd1b910837/docs/analytics-spec.md). Specs main `4b98783213447210368a591b4ea2a0cd1b910837`.
- **범위** NVDA 및 고정 ETF 7개. 2025년과 2026년을 각각 바로 앞 연말까지의 입력으로 선정한다. 후보·급락 경계·최소 비중을 고정하고 이후 기간에 현금과 ETF를 같은 비중으로 비교한다.
- **수용 조건** 합성 일봉으로 최소 비중, 동률, 검증 기간 격리, 결측과 10일 표본 경계를 확인한다. 실제 IEX 일봉의 메모리 처리 결과를 두 번 재현하고 입력 식별값을 기록한다.
