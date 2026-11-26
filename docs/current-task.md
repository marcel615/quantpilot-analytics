# Current Task

- **작업** [QP-6](https://marcel615.atlassian.net/browse/QP-6). 사용자가 작성한 후보를 이번 퀀트파일럿 사이클에서 재사용했다.
- **공식 원본** [QP-15](https://marcel615.atlassian.net/browse/QP-15)의 [요구사항](https://github.com/marcel615/quantpilot-specs/blob/1202d3bd9d1a0eb82332e67acc1f208b16dc51ad/docs/requirements.md)과 [분석 명세](https://github.com/marcel615/quantpilot-specs/blob/1202d3bd9d1a0eb82332e67acc1f208b16dc51ad/docs/analytics-spec.md).
- **범위** 같은 IEX 입력에서 기존 ETF 7개와 고정 후보 35개를 QP-4 규칙으로 독립 평가한다. 두 후보군의 공통 시작일 차이와 시점별 선정·검증 결과를 표시한다.
- **수용 조건** 합성 가격으로 기존 결과 일치·독립 공통 시작일 및 CLI 입력을 확인하고, 같은 IEX 일봉을 두 번 조회하여 전체 집계와 입력 식별값을 재현한다.
