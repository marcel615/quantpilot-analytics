# Current Task

- **작업과 착수 근거** — [QP-2](https://marcel615.atlassian.net/browse/QP-2), Jira 진행 중. 선행 [QP-5](https://marcel615.atlassian.net/browse/QP-5)의 명세가 Specs main에 병합됐다.
- **목표와 완료 조건** — NVDA·SPY 2024년 IEX 일봉의 원가격·분할조정 가격 및 공식 거래일을 수집하고, 키·값·정렬·실패 복구를 검증한다.
- **구현 범위** — Python CLI, Alpaca 페이지 수집, 가격 정제, 검증과 로컬 산출물 관리. 배당 재투자, 백테스트, 공개 표시, API·화면, 스케줄링은 제외한다.
- **공식 원본** — [요구사항](https://github.com/marcel615/quantpilot-specs/blob/49678e75e007333888e9ef413fc3fd78589e13e4/docs/requirements.md), [분석 명세](https://github.com/marcel615/quantpilot-specs/blob/49678e75e007333888e9ef413fc3fd78589e13e4/docs/analytics-spec.md), SHA `49678e75e007333888e9ef413fc3fd78589e13e4`.
- **검증 계획** — 합의한 Python 3.12와 `python -m unittest discover -s tests -v`로 고정 응답, 로컬 저장, 이전 정상 결과 보존을 검증한다. IEX 표본은 보관 조건이 확인되기 전 메모리에서 수용 검증한다.
- **미결 사항** — 실제 가격 파일의 보관 허용 범위·기간은 계정 이용 조건을 확인해야 한다.
