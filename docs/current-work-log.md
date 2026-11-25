# Current Work Log

## 2026-11-25 — QP-1 NVDA 하락 방어 후보 비교

- Jira의 착수 가능 전환 이력, 선행 QP-10 완료, 이전 QP-8 완료와 devlog를 확인했다. QP-1을 진행 중으로 전환한 뒤 다시 조회했다. GitHub의 Specs main SHA는 `2974ead957829dadca8103b6f77bdde9b455474c`였다.
- Analytics develop `b99f1f833d9e77f9697fe17099d6798ac4956846`에서 `codex/QP-1-downside-candidate-comparison`을 만들었다. 착수 전 기존 테스트 15개가 통과했다.
- 기존 IEX 일봉의 원가격·분할조정 품질 검사를 공유한다. QP-1에서 최초 가격 가용성으로 공통 시작일을 계산하고 기간 내부의 누락은 기록한다. 검증 가격이 부족한 선정 후보가 있으면 비교를 완료하지 않는다.
- 첫 실행에서는 현재 세션에 Alpaca 환경 변수가 없었다. 저장소의 `.env`에 기존 설정이 있는 것을 뒤이어 확인해 실행 프로세스에만 로드했다.

- Python 3.12.14에서 `python -m unittest discover -s tests -v` 23개가 통과했다. CLI 실행에서 자격 증명이 없으면 데이터 부족과 종료 코드 1을 반환하는 것을 확인했다.
- 자체 리뷰와 독립 리뷰에서 공식 명세, 누락 거래일 처리, 선정 기간 격리와 현금 비교를 확인했다. 독립 리뷰에서 발견한 상쇄 수익률의 반올림 판정 오류를 유리수 계산으로 수정하고 회귀 테스트를 추가했다.
- 독립 재검토에서 상쇄 수익률의 현금 동률과 회귀 테스트를 확인했다. 추가 필수 지적은 없었으며 전체 테스트 23개를 독립 실행했다.
- [Analytics PR #4](https://github.com/marcel615/quantpilot-analytics/pull/4)를 develop 대상으로 열고 Jira QP-1에 웹 링크로 기록했다. Jira가 검토 중으로 전환된 것을 재조회했다.
- `python -m downside --candidates SPY QQQ XLP XLU IEF SHY GLD UUP --end 2026-11-24`를 실제 IEX 일봉으로 두 번 실행해 전체 JSON과 입력 SHA-256 `2029c595c1a741809ee3f0c5d3ab9ae7fee90da5c9eb7c860959e2a6e41147a8`가 일치하는 것을 확인했다. 원천과 정제 가격 파일은 메모리에서 처리했다.
- 공통 선정 구간은 2020-07-27~2025-12-31이었다. IEF·SHY는 누적 주가 수익률이 음수였고 UUP는 선정 구간 거래일 4개가 누락됐다. 나머지 5개와 NVDA의 검증 가격에 누락이 없었다. 2026-01-02~2026-11-24의 급락일은 22일이었으며 XLP·XLU가 현금보다 평균 +0.160%p·+0.028%p 높았다.
