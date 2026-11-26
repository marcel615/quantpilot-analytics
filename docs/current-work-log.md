# Current Work Log

## 2026-11-26 — QP-6 방어 ETF 후보군 확대 비교

- [QP-6](https://marcel615.atlassian.net/browse/QP-6)의 선행 [Specs PR #9](https://github.com/marcel615/quantpilot-specs/pull/9)이 병합됐다. 공식 분석 명세의 SHA는 `1202d3bd9d1a0eb82332e67acc1f208b16dc51ad`다.
- 고정 35개와 NVDA를 한 요청 범위에서 조회한 뒤, 기존 7개와 확장 35개를 QP-4 평가기로 각각 평가한다. 두 후보군의 공통 선정 시작일 차이와 각 구간의 성과를 출력한다.
- Python 3.12.14에서 `python -m unittest discover -s tests -v` 39개와 `git diff --check`를 통과했다. 자체·독립 리뷰에서 공식 목록과 기존 모드, 한 번의 데이터 수집, 합성 일봉에서 기존 결과 일치 및 공통 시작일 격리를 확인했다.
- `python -m downside --expanded-weight-study --end 2026-11-24`를 실제 Alpaca Paper IEX에서 두 번 실행했다. 전체 JSON 집계와 입력 SHA-256 `3fcc387b84662fecbd7a011d8dbb65a6b0c5856dcd7e7c1658de1e719db0efa5`가 일치했다. 일봉은 메모리에서 처리했다.
- 두 후보군의 공통 선정 시작일은 두 구간 모두 2020-07-27이다. 2025년 검증 급락일은 20일, 2026-11-24까지는 22일이었다. 기존 7개와 확장 35개 모두 두 선정 시점에서 동일 비중 현금 대비 0.10%p 개선 기준을 충족한 조합이 없었다.
- 확장 후보는 2025년 평가의 선정 구간에서 가격 누락 3개, 음수 누적 수익률 8개, 개선 목표 미달 24개였다. 2026년 평가에서는 각각 3개, 7개, 25개였다.
- 검증 근거와 [Analytics PR #8](https://github.com/marcel615/quantpilot-analytics/pull/8)을 월간 devlog에 기록했다.
