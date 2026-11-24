# Current Task

- **작업과 착수 근거** — [QP-8](https://marcel615.atlassian.net/browse/QP-8) 진행 중. [QP-2](https://marcel615.atlassian.net/browse/QP-2)와 [QP-9](https://marcel615.atlassian.net/browse/QP-9) 완료.
- **공식 원본** — Specs `main` SHA `9ca53e9ed4f327d0b293bf43709f09a273be09fd`의 [요구사항](https://github.com/marcel615/quantpilot-specs/blob/9ca53e9ed4f327d0b293bf43709f09a273be09fd/docs/requirements.md)과 [분석 명세](https://github.com/marcel615/quantpilot-specs/blob/9ca53e9ed4f327d0b293bf43709f09a273be09fd/docs/analytics-spec.md).
- **목표와 범위** — NVDA·SPY의 2024년 정제 일봉을 메모리에서 사용해 다음 뉴욕 거래일의 배당 제외 수익률을 예측한다. 고정 시간순 구간, 학습 전용 전처리, 10월 설정 선택, 11–12월 동일 행 MAE 비교, 모델 재로딩을 구현한다.
- **구현 방향** — 기존 수집·정제를 재사용하고, Python CLI와 NumPy의 선형 시스템 풀이로 오프라인 리지 회귀를 구현한다. 데이터 저장과 외부 서비스 계약 변경은 필요 없다. 테스트 명령 등록은 사용자가 승인했다.
- **검증** — `python -m unittest discover -s tests -v`로 계산·경계·누출·모델 재사용을 확인하고, 승인된 IEX 표본으로 평가와 이후 거래일 예측을 검증한다.
