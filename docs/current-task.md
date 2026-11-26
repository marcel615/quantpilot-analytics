# Current Task

## QP-16 전체 보유 기간 기준 방어 ETF 재평가

- [Analytics 작업](https://marcel615.atlassian.net/browse/QP-16) · [명세 작업](https://marcel615.atlassian.net/browse/QP-17) · [공식 명세](https://github.com/marcel615/quantpilot-specs/blob/8178aa64543a93c4049354b7e52c4a54a03e478e/docs/analytics-spec.md#전체-보유-기간-기준-방어-etf-재평가)
- QP-6의 수집 경로, 35개 목록, 거래일 구간과 10·15·20% 비중을 재사용한다. 이번 실험은 별도 CLI 모드로 실행한다.
- 선정 기간의 전체 일수익률에서 동일 비중 가상 현금 대비 수익률과 최대 낙폭을 비교한다. 선정 결과는 다음 검증 기간에 고정하고 급락일 지표를 보조로 표시한다.
- 합성 시계열로 결측·경계·동률·기간 격리와 CLI를 확인한다. 전체 테스트 후 동일 IEX 요청의 집계와 입력 식별값을 두 번 대조한다.
- “퀀트파일럿 사이클 1회 진행하자” 요청으로 착수, PR 생성과 조건부 병합이 위임되었다.
