from contextlib import redirect_stderr
from datetime import date, timedelta
from decimal import Decimal
from io import StringIO
import unittest

from downside.__main__ import main
from downside.weight_study import evaluate_weight_study


def make_prices(days, returns):
    prices = {days[0]: Decimal(100)}
    for previous, current, change in zip(days, days[1:], returns):
        prices[current] = prices[previous] * (1 + Decimal(change))
    return prices


def sample():
    days = [date(2024, 12, 30), date(2024, 12, 31)]
    days += [date(year, 1, 2) + timedelta(days=index) for year in (2025, 2026) for index in range(10)]
    closes = {
        "NVDA": make_prices(days, ["-0.10"] * 21),
        "AAA": make_prices(days, ["0.008"] + ["0.01"] * 20),
        "BBB": make_prices(days, ["0.008"] + ["0.02"] * 20),
        "CCC": make_prices(days, ["0.004"] + ["0.01"] * 20),
    }
    return closes, days


class WeightStudyTests(unittest.TestCase):
    def test_selects_smallest_weight_then_largest_excess_then_ticker(self):
        closes, days = sample()
        report = evaluate_weight_study(closes, days, ("BBB", "CCC", "AAA"))
        first = report["windows"]["2025"]
        self.assertEqual(first["selected"], {
            "symbol": "AAA", "weight_percent": 15, "selection_excess_over_cash_pp": 0.12,
        })
        self.assertEqual(first["candidates"]["CCC"]["exclusion_reason"], "target_unmet_at_all_weights")
        self.assertEqual(first["status"], "evaluated")
        self.assertEqual(first["validation_downside_days"], 10)
        self.assertTrue(first["validation_target_met"])
        self.assertEqual(first["allocations"]["holding_only"]["downside_mean_return"], -0.10)
        self.assertEqual(first["allocations"]["with_cash"]["downside_mean_return"], -0.085)
        self.assertEqual(first["allocations"]["with_etf"]["downside_mean_return"], -0.0835)
        self.assertEqual(first["allocations"]["with_etf"]["downside_excess_over_cash_pp"], 0.15)
        second = report["windows"]["2026"]
        self.assertEqual(second["selected"]["symbol"], "BBB")
        self.assertEqual(second["selected"]["weight_percent"], 10)

    def test_freezes_selection_when_validation_prices_change_or_are_missing(self):
        closes, days = sample()
        original = evaluate_weight_study(closes, days, ("AAA", "BBB"))["windows"]["2025"]
        closes["AAA"][days[2]] = Decimal("90")
        updated = evaluate_weight_study(closes, days, ("AAA", "BBB"))["windows"]["2025"]
        self.assertEqual(updated["selected"], original["selected"])
        self.assertEqual(updated["downside_threshold"], original["downside_threshold"])

        del closes["BBB"][days[2]]
        unchanged = evaluate_weight_study(closes, days, ("AAA", "BBB"))["windows"]["2025"]
        self.assertEqual(unchanged, updated)

        del closes["AAA"][days[2]]
        blocked = evaluate_weight_study(closes, days, ("AAA", "BBB"))["windows"]["2025"]
        self.assertEqual(blocked["selected"], original["selected"])
        self.assertEqual(blocked["status"], "insufficient_data")
        self.assertEqual(blocked["missing_validation_dates"], {"AAA": [days[2].isoformat()]})

    def test_reports_small_sample_and_no_candidate_without_fabricating_a_comparison(self):
        closes, days = sample()
        short = evaluate_weight_study(closes, days[:-1], ("AAA",))["windows"]["2026"]
        self.assertEqual(short["status"], "insufficient_sample")
        self.assertEqual(short["validation_downside_days"], 9)
        self.assertIsNone(short["validation_target_met"])

        no_candidate = evaluate_weight_study(closes, days, ("CCC",))["windows"]["2025"]
        self.assertEqual(no_candidate["status"], "no_suitable_candidate")
        self.assertIsNone(no_candidate["selected"])
        self.assertEqual(set(no_candidate["allocations"]), {"holding_only"})
        self.assertNotIn("downside_excess_over_cash_pp", no_candidate["allocations"]["holding_only"])

        closes["CCC"].clear()
        no_prices = evaluate_weight_study(closes, days, ("CCC",))["windows"]["2025"]
        self.assertEqual(no_prices["status"], "insufficient_data")
        self.assertEqual(no_prices["candidates"]["CCC"]["exclusion_reason"], "no_selection_prices")

    def test_compares_the_exact_target_boundary(self):
        closes, days = sample()
        closes["AAA"] = make_prices(days, ["0.01"] * 21)
        report = evaluate_weight_study(closes, days, ("AAA",))["windows"]["2025"]
        self.assertEqual(report["selected"]["weight_percent"], 10)
        self.assertEqual(report["selected"]["selection_excess_over_cash_pp"], 0.10)
        self.assertTrue(report["validation_target_met"])

    def test_cli_rejects_changing_the_fixed_weight_study_inputs(self):
        stderr = StringIO()
        with redirect_stderr(stderr), self.assertRaises(SystemExit) as raised:
            main(["--weight-study", "--candidates", "QQQ", "--end", "2026-11-24"])
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("--weight-study uses --end 2026-11-24 and candidates", stderr.getvalue())
