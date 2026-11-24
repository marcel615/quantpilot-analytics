# quantpilot-analytics

QuantPilot의 시장 데이터 처리, 투자 전략 백테스트, 분석 산출물을 관리한다.

- 구현 작업은 [Jira QP 보드](https://marcel615.atlassian.net/jira/software/projects/QP/boards/35)에서 `area:analytics` 라벨로 추적한다.
- 첫 가격 수집은 [공식 분석 명세](https://github.com/marcel615/quantpilot-specs/blob/49678e75e007333888e9ef413fc3fd78589e13e4/docs/analytics-spec.md)를 따른다.
- 저장소와 Jira 상태 매핑은 [AI-DLC 설정](ai-dlc.yaml)에 있다.

## IEX 일봉 수집

Python 3.12에서 저장소 루트를 기준으로 실행한다. Windows에서 `America/New_York` 시간대 데이터가 없으면 `python -m pip install tzdata`로 설치한다.

`APCA_API_KEY_ID`와 `APCA_API_SECRET_KEY`를 현재 세션에 설정한다. Alpaca Basic Paper의 IEX 피드와 Paper 거래일 달력을 사용한다. 두 조정 모드에서 정확한 입력 종목만 조회하며 과거 티커 매핑은 비활성화한다. 공급원 선정 근거와 합의 이력은 [QP-5 공급원 비교](https://marcel615.atlassian.net/wiki/spaces/QP/pages/3899708/QP-5)에 있다.

```text
python -m market_data --symbols NVDA SPY --start 2024-01-01 --end 2024-12-31 --check-2024-sample
```

시작일과 종료일은 뉴욕 거래일 기준으로 모두 포함한다. 명령은 504행과 NVDA 분할 전후 수용 조건을 메모리에서 검증한다. 다른 종목과 기간을 검증할 때는 `--check-2024-sample`을 생략한다.

계정의 저장 허용 범위와 보존 기간을 확인한 경우에만 개인 환경에서 `--save`를 추가한다. 저장 경로는 `.local/market-data/`다. 요청별 `latest` 파일이 가리키는 실행 디렉터리에 원천 `calendar.json`, `raw.json`, `split.json`과 정제 `prices.csv`, 재현 `metadata.json`이 있다. 실행 디렉터리는 기존 독자가 계속 사용할 수 있도록 보존한다. 보존 기간이 지난 디렉터리는 계정 조건에 맞춰 제거한다. 배포용 소스는 `git archive`처럼 추적 파일만 포함하는 방식으로 패키징한다.

## 테스트

```text
python -m unittest discover -s tests -v
```

네트워크나 계정 없이 합성 응답으로 페이지 처리, 정제·재실행, 분할 수용 검증, 배당 제외, 산출물 저장과 실패 시 직전 결과 보존을 확인한다.

## 일봉 수익률 예측 실험

이전 실험의 학습 데이터, 평가 기준, 결과는 [예측 모델 실험 기록](docs/forecast-experiments.md)에 있다.

[QP-8](https://marcel615.atlassian.net/browse/QP-8)은 NVDA·SPY의 2024년 IEX 일봉으로 뉴욕 장 마감 시점의 다음 거래일 수익률을 예측한다. [공식 분석 명세](https://github.com/marcel615/quantpilot-specs/blob/9ca53e9ed4f327d0b293bf43709f09a273be09fd/docs/analytics-spec.md#첫-일봉-기반-수익률-예측-실험)를 따른다.

Python 3.12에서 `python -m pip install -r requirements.txt`를 실행하고 위 수집 절차와 같은 Alpaca 자격 증명 및 시간대 데이터를 사용한다.

```text
python -m forecast train
python -m forecast predict --history-start 2024-11-01 --as-of 2025-01-02
```

학습 명령은 실제 가격 파일을 저장하지 않고 정제 일봉을 메모리에서 처리한다. 1–9월 표본으로 전처리와 모델을 적합하고, 10월 MAE로 리지 설정을 고른 뒤, 11–12월의 유효 행에서 0% 기준선과 비교한다. 리지 후보는 0.01, 0.1, 1, 10, 100이고, 동점이면 작은 값을 고른다. 오차 차이는 리지 MAE에서 기준선 MAE를 뺀 값이다.

모델과 재현 기록은 개인 환경의 `.local/forecast/model.json`에 저장된다. 예측 명령은 이 파일에서 모델을 읽고 지정한 기준일까지 확보한 이력으로 종목별 다음 거래일 예상 수익률을 JSON으로 출력한다. 수익률 0.01은 1%를 뜻한다. `--history-start`는 기준일 이전에 최소 20개 거래일을 포함하도록 설정한다.

`python -m unittest discover -s tests -v`는 합성 일봉으로 특징·목표 계산, 시간순 구간 경계, 평가 데이터 누출 방지 및 저장 모델 예측을 검증한다.
