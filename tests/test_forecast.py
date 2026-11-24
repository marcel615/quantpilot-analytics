from datetime import date, datetime, timedelta
import json
from math import sqrt
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from forecast.__main__ import ensure_session_closed, save_model
from forecast.experiment import (
    ALPHAS, SYMBOLS, Sample, features_at, load_model, mae, model_payload,
    predict_day, prepare, run_experiment, select_model,
)
from market_data.alpaca import DataError


def weekdays(start, end):
    days = []
    while start <= end:
        if start.weekday() < 5:
            days.append(start)
        start += timedelta(days=1)
    return days


def row(symbol, day, split_close, volume=100):
    raw = str(split_close * 10)
    split = str(split_close)
    return (symbol, day.isoformat(), "USD", raw, raw, raw, raw, str(volume),
            split, split, split, split, str(volume))


class ForecastTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.days = weekdays(date(2024, 1, 1), date(2024, 12, 31))
        cls.rows = [row(symbol, day, 100 + index + (index % 7) ** 2 + offset,
                        100 + (index % 11) * 10)
                    for index, day in enumerate(cls.days)
                    for offset, symbol in enumerate(SYMBOLS)]

    def test_hand_calculated_features_and_no_future_dependency(self):
        history = [("100", 100)] * 20 + [("110", 200), ("121", 999)]
        self.assertEqual(features_at(history, 19), (None, "insufficient_history"))
        features, reason = features_at(history, 20)
        self.assertIsNone(reason)
        expected = (0.1, 0.1, 0.1, 0.1 / sqrt(20), 2)
        for value, target in zip(features, expected, strict=True):
            self.assertAlmostEqual(value, target)
        history[-1] = ("99", 0)
        self.assertEqual(features_at(history, 20), (features, None))
        self.assertEqual(features_at([("100", 0)] * 20 + [("110", 200)], 20),
                         (None, "zero_prior_volume"))

    def test_calendar_target_and_exclusions(self):
        samples, excluded = prepare(self.rows, self.days)
        self.assertEqual(excluded, {
            "insufficient_history": 40, "zero_prior_volume": 0,
            "cross_period": 4, "missing_target": 2,
        })
        self.assertEqual(sum(map(len, samples.values())) + sum(excluded.values()), len(self.rows))
        for name, next_boundary in (
            ("train", date(2024, 10, 1)), ("validation", date(2024, 11, 1)),
            ("evaluation", date(2025, 1, 1)),
        ):
            self.assertTrue(all(sample.target_day < next_boundary for sample in samples[name]))
        first = samples["train"][0]
        index = self.days.index(first.day)
        start = float(self.rows[index * 2][-2])
        end = float(self.rows[(index + 1) * 2][-2])
        self.assertEqual(first.target_day, self.days[index + 1])
        self.assertAlmostEqual(first.target, end / start - 1)
        self.assertEqual(samples["train"][1].day, first.day)
        # A synthetic company split changes raw prices and leaves the split return intact.
        changed = list(self.rows)
        original = changed[(index + 1) * 2]
        changed[(index + 1) * 2] = (*original[:3], *([original[-2]] * 4), *original[7:])
        self.assertEqual(prepare(changed, self.days), (samples, excluded))

    def test_rejects_missing_duplicate_and_invalid_price_rows(self):
        for rows in (self.rows[1:], self.rows + self.rows[:1],
                     [(*self.rows[0][:-2], "0", self.rows[0][-1]), *self.rows[1:]]):
            with self.subTest(size=len(rows)), self.assertRaises(DataError):
                prepare(rows, self.days)

    def test_evaluation_has_no_effect_on_model_selection_or_preprocessing(self):
        first, report, predictions = run_experiment(self.rows, self.days)
        changed = [item if item[1] < "2024-11-01"
                   else row(item[0], date.fromisoformat(item[1]), int(item[-2]) * 2)
                   for item in self.rows]
        second, changed_report, changed_predictions = run_experiment(changed, self.days)
        self.assertEqual(first, second)
        self.assertEqual(report["validation_mae"], changed_report["validation_mae"])
        self.assertNotEqual(predictions, changed_predictions)
        self.assertEqual(run_experiment(self.rows, self.days), (first, report, predictions))

    def test_mae_and_ridge_tie_break(self):
        day = date(2024, 10, 1)
        rows = [Sample("NVDA", day, day, (1.0,) * 5, target) for target in (0.1, -0.3)]
        self.assertAlmostEqual(mae(rows, [0.2, -0.1]), 0.15)
        train = [Sample("NVDA", day, day, (0.1,) * 5, index / 100) for index in range(10)]
        validation = [Sample("NVDA", day, day, (0.2,) * 5, 0.045)]
        model, scores = select_model(train, validation)
        self.assertEqual(model.center, (0.1,) * 5)
        self.assertEqual(model.coefficients, (0.0,) * 5)
        self.assertEqual(model.alpha, min(ALPHAS))
        self.assertEqual(model.scale, (1.0,) * 5)
        self.assertEqual(len(set(scores.values())), 1)

    def test_same_day_prediction_requires_the_actual_session_close(self):
        day = date(2025, 11, 28)
        calendar = [{"date": day.isoformat(), "close": "13:00"}]
        with self.assertRaisesRegex(DataError, "has not closed"):
            ensure_session_closed(day, calendar, datetime(2025, 11, 28, 12, 59))
        ensure_session_closed(day, calendar, datetime(2025, 11, 28, 13))
        with self.assertRaisesRegex(DataError, "unable to confirm"):
            ensure_session_closed(day, [], datetime(2025, 11, 28, 14))

    def test_published_model_predicts_on_later_day_and_survives_failed_replacement(self):
        model, _, _ = run_experiment(self.rows, self.days)
        later = date(2025, 1, 2)
        rows = [*self.rows, *(row(symbol, later, 300) for symbol in SYMBOLS)]
        days = [*self.days, later]
        expected = predict_day(model, rows, days, later)
        self.assertTrue(all("expected_return" in item for item in expected))
        with TemporaryDirectory() as directory:
            path = Path(directory) / "forecast" / "model.json"
            save_model(path, model_payload(model))
            with self.assertRaises(ValueError):
                save_model(path, {"invalid": float("nan")})
            payload = json.loads(path.read_text(encoding="utf-8"))
            restored = load_model(payload)
            self.assertEqual(predict_day(restored, rows, days, later), expected)
            payload["model_version"] = "unknown"
            with self.assertRaises(DataError):
                load_model(payload)


if __name__ == "__main__":
    unittest.main()
