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

## NVDA 하락 방어 후보 비교

[QP-1](https://marcel615.atlassian.net/browse/QP-1)은 위와 같은 Alpaca 자격 증명으로 IEX 일봉을 메모리에서 읽는다. 후보 목록과 마지막으로 검증할 2026년 뉴욕 거래일을 지정한다. 다음 명령의 후보와 거래일은 사용 예시다.

```text
python -m downside --candidates SPY IEF GLD --end 2026-11-24
```

2016년부터 조회하고 입력 종목의 공통 시작일부터 2025년 마지막 거래일까지 후보를 선별한다. NVDA의 하위 10% 급락 경계와 선정 후보를 2026년 거래일에 그대로 적용한다. 검증 첫날 수익률에는 2025년 마지막 거래일 종가를 사용한다. 수익률은 배당을 제외한 분할조정 종가로 계산한다. 매일 NVDA 단독, NVDA 80%·현금 20%, NVDA 80%·후보 20%를 비교하며 현금 수익률과 거래 비용은 0이다.

JSON 결과에 후보별 선정 여부와 제외 사유, 기간, 입력 SHA-256, 급락일 표본 수, 조합별 누적 수익률·최대 낙폭·상승일과 급락일 평균을 표시한다. 수익률과 최대 낙폭은 소수로, 현금 대비 급락일 차이는 퍼센트포인트로 표시한다. 검증 급락일이 10일 이상일 때 현금 대비 차이가 양수인 후보를 집계한다. 필수 일봉을 확보하지 못하면 결과의 `status`에 `insufficient_data`가 표시되고 명령은 종료 코드 1을 반환한다. [공식 분석 명세](https://github.com/marcel615/quantpilot-specs/blob/2974ead957829dadca8103b6f77bdde9b455474c/docs/analytics-spec.md#보유-희망-종목-한-개의-하락-방어-후보-비교)

## 여러 보유 희망 종목의 하락 방어 후보 비교

[QP-11](https://marcel615.atlassian.net/browse/QP-11)은 두세 종목의 기준 포트폴리오를 지원한다. `--holdings`에 종목과 양의 비중을 합계 100으로 지정하고, 기준 종목과 겹치지 않는 후보 ETF를 입력한다. 다음은 첫 수용 검증 명령이다.

```text
python -m downside --holdings NVDA=50 SPY=50 --candidates QQQ XLP XLU IEF SHY GLD UUP --end 2026-11-24
```

[QP-3](https://marcel615.atlassian.net/browse/QP-3)의 별도 실험은 NVDA·SPY 각각 40%에 20% 가상 현금, 포트폴리오 ETF 하나 20%, 종목별 ETF 두 개 각 10%를 더한 조합을 비교한다. 선정 기간에서 고정한 ETF를 사용하며 같은 검증 급락일의 평균·최악 수익률, 누적 수익률과 최대 낙폭을 출력한다.

```bash
python -m downside --compare-allocations --candidates QQQ XLP XLU IEF SHY GLD UUP --end 2026-11-24
```

매 거래일 목표 비중으로 합산한 기준 포트폴리오 수익률로 급락일을 판단한다. 기존과 같은 비중으로 현금 또는 후보 ETF를 편입해 비교한다. JSON의 `holdings_percent`는 입력 비중을 문자열로 기록하며, `holding_only`는 기준 포트폴리오 전체의 성과를 담는다. [공식 분석 명세](https://github.com/marcel615/quantpilot-specs/blob/7d46cb83a9fe49af0cbababfe74c839951a90560/docs/analytics-spec.md#여러-보유-희망-종목의-하락-방어-후보-비교)

### 방어 ETF와 최소 편입 비중의 시점별 검증

[QP-4](https://marcel615.atlassian.net/browse/QP-4)는 NVDA와 고정 ETF 후보 7개로 2025년과 2026년의 검증 결과를 따로 출력한다. 앞선 연말까지의 자료에서 현금 대비 급락일 평균 수익률을 0.10%p 이상 개선하는 최소 ETF 비중(10%, 15%, 20%)을 찾고, 각 검증 기간에 선택을 고정한다.

```text
python -m downside --weight-study --candidates QQQ XLP XLU IEF SHY GLD UUP --end 2026-11-24
```

JSON의 `windows`에는 기간별 선택과 검증 상태, 급락일 표본 수, 기준·현금·ETF 조합의 성과가 담긴다. 적합 후보가 없으면 NVDA 기준 성과만 표시한다. `validation_target_met`은 평가에 충분한 표본이 있을 때 목표 달성 여부를 나타낸다. [공식 분석 명세](https://github.com/marcel615/quantpilot-specs/blob/4b98783213447210368a591b4ea2a0cd1b910837/docs/analytics-spec.md#방어-etf와-최소-편입-비중의-시점별-검증)

### 방어 ETF 후보군 확대 비교

[QP-6](https://marcel615.atlassian.net/browse/QP-6)은 동일한 IEX 조회를 사용해 기존 ETF 7개와 이를 포함한 고정 후보 35개를 각각 평가한다.

```text
python -m downside --expanded-weight-study --end 2026-11-24
```

JSON의 `baseline`과 `expanded`에 각 후보군의 시점별 선정·검증 결과와 제외 사유가 담긴다. 두 후보군은 같은 규칙으로 공통 선정 시작일을 각각 계산한다. `comparisons`에서 시작일 차이를 확인할 수 있다. 조회한 가격은 메모리에서 처리한다. [공식 분석 명세](https://github.com/marcel615/quantpilot-specs/blob/1202d3bd9d1a0eb82332e67acc1f208b16dc51ad/docs/analytics-spec.md#방어-etf-후보군-확대-비교)

## 전체 보유 기간 기준 방어 ETF 재평가

QP-16은 QP-6의 ETF 35개와 두 검증 구간에서 급락일 기준 대신 전체 거래일의 누적 주가 수익률과 최대 낙폭으로 후보를 선정한다.

```powershell
python -m downside --holding-period-study --end 2026-11-24
```

`windows`에 기간, ETF·비중별 선정 지표, 선택 결과와 고정된 이후 구간의 조합별 성과가 나온다. 급락일 지표와 표본 충족 여부도 표시한다.
