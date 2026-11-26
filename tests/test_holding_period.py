from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from decimal import Decimal
from fractions import Fraction
from io import StringIO
import unittest
from unittest.mock import patch

from downside.__main__ import EXPANDED_WEIGHT_STUDY_CANDIDATES, main
from downside.holding_period import comparison, evaluate_holding_period, path_performance


class HoldingPeriodTests(unittest.TestCase):
    def setUp(self):
        self.days = [date.fromisoformat(value) for value in (
            "2024-12-27", "2024-12-30", "2024-12-31", "2025-01-02",
            "2025-01-03", "2026-01-02",
        )]
        self.closes = {
            "NVDA": self.prices(100, 90, 100, 110, 120, 130),
            "AAA": self.prices(100, 110, 110, 108, 109, 111),
            "BBB": self.prices(100, 110, 110, 150, 190, 200),
            "FLAT": self.prices(100, 100, 100, 100, 100, 100),
            "DOWN": self.prices(100, 101, 99, 98, 97, 96),
        }

    def prices(self, *values):
        return dict(zip(self.days, map(Decimal, values)))

    def first_window(self, *candidates):
        return evaluate_holding_period(self.closes, self.days, candidates)["windows"]["2025"]

    def test_ranks_drawdown_reduction_then_ticker_and_uses_all_validation_sessions(self):
        report = self.first_window("BBB", "AAA", "FLAT", "DOWN")
        self.assertEqual(report["status"], "evaluated")
        self.assertEqual(report["selected"]["symbol"], "AAA")
        self.assertEqual(report["selected"]["weight_percent"], 20)
        self.assertEqual(report["selected"]["maximum_drawdown_reduction_vs_cash_pp"], 2.0)
        self.assertEqual(report["candidates"]["FLAT"]["exclusion_reason"], "target_unmet_at_all_weights")
        self.assertEqual(report["candidates"]["DOWN"]["exclusion_reason"], "negative_selection_return")
        self.assertEqual(report["validation_downside_days"], 0)
        self.assertFalse(report["validation_downside_sample_sufficient"])
        self.assertFalse(report["validation_target_met"])
        self.assertEqual(report["allocations"]["holding_only"]["cumulative_return"], 0.2)
        self.assertIsNone(report["allocations"]["holding_only"]["downside_mean_return"])

    def test_validation_changes_do_not_reselect_and_selected_price_gaps_are_reported(self):
        baseline = self.first_window("AAA", "BBB")
        del self.closes["BBB"][self.days[3]]
        self.assertEqual(self.first_window("AAA", "BBB"), baseline)
        self.closes["AAA"][self.days[3]] = Decimal(1)
        changed = self.first_window("AAA", "BBB")
        self.assertEqual(changed["selected"], baseline["selected"])
        self.assertEqual(changed["downside_threshold"], baseline["downside_threshold"])
        del self.closes["AAA"][self.days[3]]
        blocked = self.first_window("AAA", "BBB")
        self.assertEqual(blocked["selected"], baseline["selected"])
        self.assertEqual(blocked["status"], "insufficient_data")
        self.assertIsNone(blocked["allocations"])
        self.assertEqual(blocked["missing_validation_dates"], {"AAA": ["2025-01-02"]})

    def test_distinguishes_no_candidate_from_missing_candidate_prices(self):
        no_candidate = self.first_window("FLAT")
        self.assertEqual(no_candidate["status"], "no_suitable_candidate")
        self.assertEqual(set(no_candidate["allocations"]), {"holding_only"})
        self.closes["FLAT"].clear()
        missing = self.first_window("FLAT")
        self.assertEqual(missing["status"], "insufficient_data")
        self.assertEqual(missing["candidates"]["FLAT"]["exclusion_reason"], "no_selection_prices")

    def test_path_counts_initial_peak_and_compounds_in_order(self):
        self.assertEqual(
            path_performance([Fraction(-1, 10), Fraction(1, 5), Fraction(-1, 20)]),
            (Fraction(13, 500), Fraction(1, 10)),
        )

    def test_exact_cash_target_boundary(self):
        cash = (Fraction(1, 10), Fraction(1, 10))
        self.assertTrue(comparison((cash[0], Fraction(9, 100)), cash)["target_met"])
        self.assertFalse(comparison(cash, cash)["target_met"])
        self.assertFalse(comparison((cash[0] - Fraction(1, 10**25), Fraction(9, 100)), cash)["target_met"])

    def test_reports_validation_even_without_selection_downside(self):
        for day, value in zip(self.days[:3], (100, 105, 110)):
            self.closes["NVDA"][day] = Decimal(value)
        report = self.first_window("AAA")
        self.assertEqual(report["selection_downside_days"], 0)
        self.assertEqual(report["status"], "no_suitable_candidate")
        self.assertIsNotNone(report["allocations"]["holding_only"])

    def test_cli_passes_the_fixed_universe_to_one_collection(self):
        with patch("downside.__main__.Alpaca"), patch("downside.__main__.run") as run:
            run.return_value = {"status": "comparison_complete"}
            with redirect_stdout(StringIO()):
                self.assertEqual(main(["--holding-period-study", "--end", "2026-11-24"]), 0)
        run.assert_called_once()
        self.assertEqual(set(run.call_args.args[1].symbols), {"NVDA", *EXPANDED_WEIGHT_STUDY_CANDIDATES})
        self.assertTrue(run.call_args.kwargs["holding_period_study"])
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as raised:
            main(["--holding-period-study", "--end", "2026-11-24", "--candidates", "QQQ"])
        self.assertEqual(raised.exception.code, 2)
