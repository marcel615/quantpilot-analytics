"""Prepare chronological samples, select a ridge model, and evaluate it."""

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date
import hashlib
import json
from math import isfinite
from statistics import mean, stdev

import numpy as np

from market_data.alpaca import DataError
from market_data.pipeline import HEADER, price_return

FEATURES = ("return_1", "return_5", "return_20", "volatility_20", "relative_volume")
PERIODS = (
    ("train", date(2024, 1, 1), date(2024, 9, 30)),
    ("validation", date(2024, 10, 1), date(2024, 10, 31)),
    ("evaluation", date(2024, 11, 1), date(2024, 12, 31)),
)
ALPHAS = (0.01, 0.1, 1.0, 10.0, 100.0)
SYMBOLS = ("NVDA", "SPY")
MODEL_VERSION = "ridge-v1"
PREPROCESSING_VERSION = "standardize-v1"


@dataclass(frozen=True)
class Sample:
    symbol: str
    day: date
    target_day: date
    features: tuple[float, ...]
    target: float


@dataclass(frozen=True)
class Model:
    center: tuple[float, ...]
    scale: tuple[float, ...]
    coefficients: tuple[float, ...]
    intercept: float
    alpha: float

    def predict(self, features):
        return self.intercept + sum(
            (value - center) / scale * coefficient
            for value, center, scale, coefficient in zip(
                features, self.center, self.scale, self.coefficients, strict=True
            )
        )


def prices_by_symbol(rows, symbols, days):
    """Align the collector's canonical rows to its expected trading calendar."""
    if list(days) != sorted(set(days)):
        raise DataError("Expected unique trading days in chronological order")
    keys = {(symbol, day.isoformat()) for symbol in symbols for day in days}
    prices = {}
    for row in rows:
        if len(row) != len(HEADER):
            raise DataError("Unexpected cleaned row width")
        symbol, day, currency, *values = row
        key = (symbol, day)
        if key not in keys or key in prices or currency != "USD":
            raise DataError(f"{symbol} {day}: unexpected or duplicate cleaned row")
        try:
            numbers = tuple(float(value) for value in values)
        except (TypeError, ValueError, OverflowError):
            raise DataError(f"{symbol} {day}: invalid cleaned values") from None
        for opened, high, low, closed, volume in (numbers[:5], numbers[5:]):
            if (not all(map(isfinite, (opened, high, low, closed, volume)))
                    or not 0 < low <= min(opened, closed)
                    or high < max(opened, closed) or volume < 0):
                raise DataError(f"{symbol} {day}: invalid cleaned OHLCV")
        prices[key] = (values[8], numbers[9])
    if missing := keys - prices.keys():
        symbol, day = min(missing)
        raise DataError(f"{symbol} {day}: missing cleaned trading day")
    return {
        symbol: [prices[symbol, day.isoformat()] for day in days]
        for symbol in symbols
    }


def features_at(prices, index):
    if index < 20:
        return None, "insufficient_history"
    history = prices[index - 20:index + 1]
    average_volume = mean(volume for _, volume in history[:-1])
    if not average_volume:
        return None, "zero_prior_volume"
    close, volume = history[-1]
    returns = [float(price_return(history[-n - 1][0], close)) for n in (1, 5, 20)]
    daily_returns = [
        float(price_return(prior[0], current[0]))
        for prior, current in zip(history, history[1:])
    ]
    features = (*returns, stdev(daily_returns), volume / average_volume)
    if not all(map(isfinite, features)):
        raise DataError("Non-finite feature derived from cleaned prices")
    return features, None


def period_for(day):
    return next((name for name, start, end in PERIODS if start <= day <= end), None)


def prepare(rows, days):
    prices = prices_by_symbol(rows, SYMBOLS, days)
    samples = {name: [] for name, _, _ in PERIODS}
    excluded = Counter(dict.fromkeys(
        ("insufficient_history", "zero_prior_volume", "missing_target", "cross_period"), 0
    ))
    for index, day in enumerate(days):
        period = period_for(day)
        if period is None:
            raise DataError("Training calendar must be within the 2024 experiment window")
        for symbol, series in prices.items():
            features, reason = features_at(series, index)
            if reason is None:
                if index + 1 == len(days):
                    reason = "missing_target"
                elif period_for(days[index + 1]) != period:
                    reason = "cross_period"
            if reason:
                excluded[reason] += 1
                continue
            target = float(price_return(series[index][0], series[index + 1][0]))
            if not isfinite(target):
                raise DataError("Non-finite target derived from cleaned prices")
            samples[period].append(Sample(symbol, day, days[index + 1], features, target))
    return samples, dict(excluded)


def mae(samples, predictions):
    return mean(abs(sample.target - prediction)
                for sample, prediction in zip(samples, predictions, strict=True))


def select_model(train, validation):
    x = np.asarray([row.features for row in train])
    y = np.asarray([row.target for row in train])
    center = x.mean(axis=0)
    scale = x.std(axis=0)
    constant = np.ptp(x, axis=0) == 0
    center[constant] = x[0, constant]
    scale[constant] = 1.0
    x = (x - center) / scale
    intercept = float(y.mean())
    gram = x.T @ x
    rhs = x.T @ (y - intercept)
    penalty = np.eye(len(FEATURES))
    scores = {}
    models = {}
    for alpha in ALPHAS:
        coefficients = np.linalg.solve(gram + alpha * penalty, rhs)
        model = Model(tuple(center.tolist()), tuple(scale.tolist()),
                      tuple(coefficients.tolist()), intercept, alpha)
        scores[alpha] = mae(validation, (model.predict(row.features) for row in validation))
        models[alpha] = model
    winner = min(ALPHAS, key=lambda alpha: (scores[alpha], alpha))
    return models[winner], scores


def run_experiment(rows, days):
    samples, excluded = prepare(rows, days)
    for period, group in samples.items():
        if not group:
            raise DataError(f"No eligible {period} samples")
    model, scores = select_model(samples["train"], samples["validation"])
    evaluation = samples["evaluation"]
    predicted = [model.predict(row.features) for row in evaluation]
    ridge_mae = mae(evaluation, predicted)
    baseline_mae = mae(evaluation, (0.0 for _ in evaluation))
    report = {
        "periods": {name: [start.isoformat(), end.isoformat()] for name, start, end in PERIODS},
        "counts": {name: len(group) for name, group in samples.items()},
        "excluded": excluded,
        "alphas": ALPHAS,
        "tie_break": "smallest alpha",
        "validation_mae": scores,
        "selected_alpha": model.alpha,
        "ridge_mae": ridge_mae,
        "baseline_mae": baseline_mae,
        "ridge_minus_baseline_mae": ridge_mae - baseline_mae,
        "improved": ridge_mae < baseline_mae,
    }
    return model, report, predicted


def predict_day(model, rows, days, day):
    if day not in days:
        raise DataError(f"{day}: not a trading day")
    prices = prices_by_symbol(rows, SYMBOLS, days)
    output = []
    index = days.index(day)
    for symbol, series in prices.items():
        features, reason = features_at(series, index)
        item = {"symbol": symbol, "trade_date": day.isoformat()}
        if reason:
            item["excluded"] = reason
        else:
            item["expected_return"] = model.predict(features)
        output.append(item)
    return output


def input_digest(rows, days):
    canonical = json.dumps([sorted(rows), [day.isoformat() for day in days]],
                           separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def model_payload(model):
    return {
        "model_version": MODEL_VERSION,
        "preprocessing_version": PREPROCESSING_VERSION,
        "features": FEATURES,
        "model": asdict(model),
    }


def load_model(payload):
    try:
        if (payload["model_version"] != MODEL_VERSION
                or payload["preprocessing_version"] != PREPROCESSING_VERSION
                or tuple(payload["features"]) != FEATURES):
            raise ValueError
        data = payload["model"]
        model = Model(tuple(data["center"]), tuple(data["scale"]),
                      tuple(data["coefficients"]), data["intercept"], data["alpha"])
        vectors = (model.center, model.scale, model.coefficients)
        if (any(len(vector) != len(FEATURES) for vector in vectors)
                or not all(isfinite(value) for vector in vectors for value in vector)
                or any(value <= 0 for value in model.scale)
                or not isfinite(model.intercept) or model.alpha not in ALPHAS):
            raise ValueError
    except (KeyError, TypeError, ValueError, OverflowError):
        raise DataError("Invalid or unsupported forecast model") from None
    return model
