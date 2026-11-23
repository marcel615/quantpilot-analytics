# Current Work Log

## 2026-11-24 — QP-2 금융 데이터 수집 기반 구축

- 작업 브랜치는 `codex/QP-2-price-data-ingestion`이며 기준은 `d0b6367bac47d85d20cfb0321b3d61380549c5af`다.
- Alpaca Paper 달력과 IEX 일봉의 원가격·분할조정 가격을 검증하고, 성공 실행만 `latest`로 공개한다.
- Python 3.12.14에서 `python -m unittest discover -s tests -v` 8건 통과. 실제 IEX NVDA·SPY 2024년 일봉 504행과 NVDA 분할 전후 조건을 저장 없이 확인했다.
- 합성 입력으로 기본 저장 경로의 산출물, Git 무시, 배포용 Git 아카이브 제외를 확인했다.
- 독립 리뷰의 HTTP 응답 중단 처리와 SPY 배당락 검증을 수정했다. Windows 저장 경로를 줄인 뒤 재검증하고 독립 재검토를 완료했다.
- [Analytics PR #2](https://github.com/marcel615/quantpilot-analytics/pull/2)를 [QP-2](https://marcel615.atlassian.net/browse/QP-2)에 연결하고 Jira 검토 중 상태를 재조회했다.
- 실제 가격 파일의 지속 저장은 계정 보관 조건 확인 후 별도로 검증한다. PR 머지는 사용자 검토 후 진행한다.
