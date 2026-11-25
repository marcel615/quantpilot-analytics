# Current Work Log

## 2026-11-25 — QP-11 여러 보유 희망 종목의 하락 방어 후보 비교

- [QP-12](https://marcel615.atlassian.net/browse/QP-12)의 [Specs PR #6](https://github.com/marcel615/quantpilot-specs/pull/6) 병합 및 Jira 완료, QP-11의 착수 가능과 진행 중 전환을 확인했다.
- Analytics develop `aead17fd89314945b20d0e4a72d5d5ab1094d755`에서 `codex/QP-11-multi-holding-downside`를 만들었다. 기존 23개 테스트를 통과한 상태에서 기준 포트폴리오 가중 수익률과 비중 입력을 추가했다.
- 독립 리뷰가 찾은 미세 비중 차이의 급락 경계 동률 문제를 수정했다. 유리수로 일자 분류를 끝낸 뒤 성과 집계에서 Decimal로 변환한다. 실패 결과에도 다종목 비중을 기록했다. 독립 재검토에서 추가 필수 지적이 없었고 전체 27개 테스트를 통과했다.
- 첫 실제 IEX 검증은 NVDA 50%, SPY 50%, 후보 QQQ·XLP·XLU·IEF·SHY·GLD·UUP 및 2026-11-24까지의 완료 거래일을 사용한다. Alpaca 인증은 실행 프로세스에만 사용하고 원천·정제 일봉은 메모리에서 처리했다.
- 최종 구현으로 실제 IEX 일봉을 두 번 조회했다. 전체 JSON과 입력 SHA-256 2029c595c1a741809ee3f0c5d3ab9ae7fee90da5c9eb7c860959e2a6e41147a8가 일치했다. 급락일 21일에서 XLP 편입 조합의 평균 수익률이 현금 조합보다 0.116%p 높았다.
- [Analytics PR #5](https://github.com/marcel615/quantpilot-analytics/pull/5)를 develop 대상으로 열었고 Jira의 PR 링크와 검토 중 전환을 확인했다.
