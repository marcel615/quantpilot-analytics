# Current Work Log

## 2026-11-26 — QP-6 방어 ETF 후보군 확대 비교

- [QP-6](https://marcel615.atlassian.net/browse/QP-6)의 선행 [Specs PR #9](https://github.com/marcel615/quantpilot-specs/pull/9)이 병합됐다. 공식 분석 명세의 SHA는 `1202d3bd9d1a0eb82332e67acc1f208b16dc51ad`다.
- 고정 35개와 NVDA를 한 요청 범위에서 조회한 뒤, 기존 7개와 확장 35개를 QP-4 평가기로 각각 평가한다. 두 후보군의 공통 선정 시작일 차이와 각 구간의 성과를 출력한다.
- Python 3.12.14에서 `python -m unittest discover -s tests -v` 39개와 `git diff --check`를 통과했다. 자체·독립 리뷰에서 공식 목록과 기존 모드, 한 번의 데이터 수집, 합성 일봉에서 기존 결과 일치 및 공통 시작일 격리를 확인했다.
- 실제 IEX 35개 후보군의 반복 실행 결과 확인이 진행 중이다. 결과와 입력 식별값을 devlog에 반영한다.
