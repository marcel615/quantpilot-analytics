from datetime import date, datetime, timedelta, UTC
from decimal import Decimal
from contextlib import redirect_stderr
from io import StringIO
import json
import unittest
from zoneinfo import ZoneInfo

from downside.__main__ import main, parse_holdings, run
from downside.experiment import compare
from market_data.alpaca import BARS_URL, CALENDAR_URL, DataError
from market_data.pipeline import Query


PREVIOUS = date(2025, 12, 30)
ANCHOR = date(2025, 12, 31)
FIRST_VALIDATION = date(2026, 1, 2)


def prices_from_returns(start, returns):
    prices = [Decimal(start)]
    for change in returns:
        prices.append(prices[-1] * (1 + Decimal(change)))
    return prices


def sample(count=10, candidate_change="0.05"):
    validation = [
        date(2026, 1, day) for day in (2, 5, 6, 7, 8, 9, 12, 13, 14, 15, 16)
    ][:count]
    days = [PREVIOUS, ANCHOR, *validation]
    holding = prices_from_returns("100", ["-0.10"] * (count + 1))
    candidate = prices_from_returns("100", ["0.05", *([candidate_change] * count)])
    return {"NVDA": dict(zip(days, holding)), "AAA": dict(zip(days, candidate))}, days


class DownsideTests(unittest.TestCase):
    def test_portfolio_returns_set_the_threshold_and_keep_validation_separate(self):
        closes, days = sample()
        closes["SPY"] = dict(zip(days, prices_from_returns("100", ["0.02"] * (len(days) - 1))))
        holdings = parse_holdings(["NVDA=50", "SPY=50"])
        result = compare(closes, days, ("AAA",), holdings)
        self.assertEqual(result["holdings_percent"], {"NVDA": "50", "SPY": "50"})
        self.assertEqual(result["downside_threshold"], -0.04)
        self.assertEqual(result["validation"]["downside_days"], 10)
        self.assertEqual(result["validation"]["holding_only"]["downside_mean_return"], -0.04)
        self.assertEqual(result["validation"]["with_cash"]["downside_mean_return"], -0.032)
        metrics = result["validation"]["with_candidates"]["AAA"]
        self.assertEqual(metrics["downside_mean_return"], -0.022)
        self.assertEqual(metrics["downside_excess_over_cash_pp"], 1)

        closes["SPY"].update({day: Decimal("105") for day in days if day > ANCHOR})
        changed = compare(closes, days, ("AAA",), holdings)
        for key in ("candidates", "downside_threshold", "selection"):
            self.assertEqual(changed[key], result[key])
        self.assertNotEqual(changed["validation"], result["validation"])

    def test_missing_baseline_constituent_is_reported_by_symbol(self):
        closes, days = sample()
        closes["SPY"] = dict.fromkeys(days, Decimal(100))
        holdings = parse_holdings(["NVDA=75", "SPY=25"])
        del closes["SPY"][days[3]]
        result = compare(closes, days, ("AAA",), holdings)
        self.assertEqual(result["missing_validation_dates"], {"SPY": [days[3].isoformat()]})
        self.assertEqual(result["status"], "insufficient_data")
        self.assertIsNone(result["validation"])

        earlier = date(2025, 12, 29)
        days.insert(0, earlier)
        for prices in closes.values():
            prices[earlier] = Decimal(100)
        del closes["SPY"][PREVIOUS]
        result = compare(closes, days, ("AAA",), holdings)
        self.assertEqual(result["missing_selection_dates"], {"SPY": [PREVIOUS.isoformat()]})
        self.assertIsNone(result["selection"])

    def test_nearly_equal_portfolio_returns_do_not_create_a_downside_tie(self):
        days = [PREVIOUS, ANCHOR, FIRST_VALIDATION]
        closes = {
            "NVDA": dict(zip(days, map(Decimal, ["100", "90", "72"]))),
            "SPY": dict(zip(days, map(Decimal, ["100", "80", "72"]))),
            "AAA": dict.fromkeys(days, Decimal(100)),
        }
        holdings = parse_holdings([
            "NVDA=49.9999999999999999999999999999",
            "SPY=50.0000000000000000000000000001",
        ])
        result = compare(closes, days, ("AAA",), holdings)
        self.assertEqual(result["selection"]["downside_days"], 1)
        self.assertEqual(result["validation"]["downside_days"], 0)

    def test_holdings_require_distinct_symbols_and_an_exact_positive_total(self):
        self.assertEqual(
            parse_holdings(["NVDA=33.33", "SPY=33.33", "GLD=33.34"]),
            {"NVDA": Decimal("33.33"), "SPY": Decimal("33.33"), "GLD": Decimal("33.34")},
        )
        for values in (["NVDA=100"], ["NVDA=50", "NVDA=50"], ["NVDA=50", "SPY=49"],
                       ["NVDA=NaN", "SPY=50"], ["NVDA=100", "SPY=0"], ["NVDA", "SPY=50"]):
            with self.subTest(values=values), self.assertRaises(DataError):
                parse_holdings(values)

        error = StringIO()
        with redirect_stderr(error), self.assertRaises(SystemExit) as raised:
            main(["--holdings", "NVDA=50", "SPY=50", "--candidates", "SPY", "--end", "2026-01-02"])
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("distinct from the reference holdings", error.getvalue())

    def test_hand_calculated_returns_and_anchor(self):
        closes, days = sample()
        result = compare(closes, days, ("AAA",))
        self.assertEqual(result["status"], "additional_defense_found")
        self.assertEqual(result["additional_defense"], ["AAA"])
        self.assertEqual(result["validation"]["first_return_date"], FIRST_VALIDATION.isoformat())
        for period, count in (("selection", 1), ("validation", 10)):
            metrics = result[period]
            self.assertEqual(metrics["downside_days"], count)
            self.assertIsNone(metrics["holding_only"]["upside_mean_return"])
            self.assertEqual(metrics["holding_only"]["downside_mean_return"], -0.10)
            self.assertEqual(metrics["with_cash"]["downside_mean_return"], -0.08)
            candidate = metrics["with_candidates"]["AAA"]
            self.assertEqual(candidate["downside_mean_return"], -0.07)
            self.assertEqual(candidate["downside_excess_over_cash_pp"], 1)
            expected = 1 - 0.93 ** count
            self.assertAlmostEqual(candidate["maximum_drawdown"], expected)
            self.assertAlmostEqual(candidate["cumulative_return"], -expected)

    def test_sample_boundary_and_cash_tie(self):
        closes, days = sample(9)
        result = compare(closes, days, ("AAA",))
        self.assertEqual(result["status"], "insufficient_sample")
        self.assertFalse(result["validation_sample_sufficient"])
        self.assertEqual(result["additional_defense"], [])
        closes, days = sample(10, "0")
        result = compare(closes, days, ("AAA",))
        self.assertTrue(result["validation_sample_sufficient"])
        self.assertEqual(result["validation"]["with_candidates"]["AAA"]["downside_excess_over_cash_pp"], 0)
        self.assertEqual(result["status"], "no_suitable_candidate")

    def test_offsetting_fractional_returns_tie_cash(self):
        closes, days = sample()
        candidate = map(Decimal, [49, 49, 56, 48, *([48] * 8)])
        closes["AAA"] = dict(zip(days, candidate))
        result = compare(closes, days, ("AAA",))
        self.assertEqual(result["validation"]["with_candidates"]["AAA"]["downside_excess_over_cash_pp"], 0)
        self.assertEqual(result["status"], "no_suitable_candidate")

    def test_tied_downside_threshold_and_upside_returns(self):
        days = [date(2025, 12, 15) + timedelta(days=offset) for offset in range(11)]
        selections = ["-0.1", "-0.1", *["0.1"] * 8]
        calendar = [*days, FIRST_VALIDATION]
        closes = {
            "NVDA": dict(zip(calendar, prices_from_returns("100", [*selections, "-0.1"]))),
            "AAA": dict.fromkeys(calendar, Decimal("100")),
        }
        result = compare(closes, calendar, ("AAA",))
        self.assertEqual(result["downside_threshold"], -0.1)
        self.assertEqual(result["selection"]["downside_days"], 2)
        self.assertEqual(result["selection"]["upside_days"], 8)
        self.assertEqual(result["selection"]["with_cash"]["upside_mean_return"], 0.08)
        self.assertEqual(result["validation"]["downside_days"], 1)

    def test_common_start_negative_recent_and_out_of_sample_isolation(self):
        closes, days = sample()
        early, common, recent = date(2021, 1, 4), date(2022, 1, 3), date(2023, 1, 3)
        days = [early, common, recent, *days]
        closes["NVDA"].update({early: Decimal("101"), common: Decimal("100"), recent: Decimal("100")})
        closes["AAA"].update({common: Decimal("80"), recent: Decimal("120")})
        closes["BBB"] = dict.fromkeys(days, Decimal("100"))
        closes["BBB"][ANCHOR] = Decimal("75")
        result = compare(closes, days, ("AAA", "BBB"))
        self.assertEqual(result["common_start"], common.isoformat())
        self.assertTrue(result["candidates"]["AAA"]["selected"])
        self.assertEqual(result["candidates"]["AAA"]["recent_three_year_status"], "negative_return")
        self.assertAlmostEqual(result["candidates"]["AAA"]["recent_three_year_price_metrics"]["maximum_drawdown"], 1 / 6)
        self.assertFalse(result["candidates"]["BBB"]["selected"])
        closes["AAA"].update({day: Decimal("1") for day in days if day > ANCHOR})
        closes["BBB"].update({day: Decimal("10000") for day in days if day > ANCHOR})
        updated = compare(closes, days, ("AAA", "BBB"))
        for key in ("candidates", "downside_threshold", "selection"):
            self.assertEqual(updated[key], result[key])
        self.assertNotEqual(updated["validation"], result["validation"])

    def test_missing_sessions_do_not_join_prices_across_the_gap(self):
        closes, days = sample()
        missing = days[4]
        del closes["AAA"][missing]
        result = compare(closes, days, ("AAA",))
        self.assertTrue(result["candidates"]["AAA"]["selected"])
        self.assertEqual(result["missing_validation_dates"], {"AAA": [missing.isoformat()]})
        self.assertEqual(result["status"], "insufficient_data")
        self.assertIsNone(result["validation"])

        middle = date(2025, 12, 29)
        first = date(2025, 12, 26)
        days = [first, middle, *days]
        closes["NVDA"].update({first: Decimal("100"), middle: Decimal("100")})
        closes["AAA"][first] = Decimal("100")
        result = compare(closes, days, ("AAA",))
        self.assertEqual(result["candidates"]["AAA"]["selection_missing_dates"], [middle.isoformat()])
        self.assertFalse(result["candidates"]["AAA"]["selected"])
        self.assertEqual(result["status"], "insufficient_data")

    def test_candidates_failing_selection_need_no_validation_prices(self):
        closes, days = sample()
        closes["AAA"] = {PREVIOUS: Decimal("100"), ANCHOR: Decimal("90")}
        result = compare(closes, days, ("AAA",))
        self.assertEqual(result["candidates"]["AAA"]["exclusion_reason"], "negative_selection_return")
        self.assertEqual(result["missing_validation_dates"], {})
        self.assertEqual(result["status"], "no_suitable_candidate")
        self.assertEqual(result["reason"], "no_candidate_passed_selection")

    def test_collection_feeds_split_prices_and_repeatable_input_digest(self):
        closes, days = sample()
        query = Query(tuple(closes), date(2016, 1, 1), days[-1])
        zone = ZoneInfo("America/New_York")

        def fake_get(url, params):
            if url == CALENDAR_URL:
                return json.dumps([{"date": day.isoformat(), "close": "16:00"} for day in days])
            self.assertEqual(url, BARS_URL)
            self.assertEqual(params["feed"], "iex")
            self.assertEqual(params["currency"], "USD")
            self.assertEqual(params["asof"], "-")
            bars = {}
            for symbol, prices in closes.items():
                bars[symbol] = []
                for day, price in prices.items():
                    value = float(price) if params["adjustment"] == "split" else 100
                    timestamp = datetime.combine(day, datetime.min.time(), zone)
                    bars[symbol].append({
                        "t": timestamp.isoformat(), "o": value, "h": value,
                        "l": value, "c": value, "v": 1,
                    })
            return json.dumps({"bars": bars})

        now = datetime(2026, 2, 1, tzinfo=UTC)
        report = run(fake_get, query, now)
        self.assertEqual(report, run(fake_get, query, now))
        self.assertEqual(report["input"]["price"], "close_split")
        self.assertEqual(report["validation"]["downside_days"], 10)
        self.assertEqual(report["status"], "additional_defense_found")
        closes["SPY"] = dict.fromkeys(days, Decimal(100))
        portfolio_query = Query(tuple(closes), query.start, query.end)
        holdings = parse_holdings(["NVDA=50", "SPY=50"])
        portfolio = run(fake_get, portfolio_query, now, holdings)
        self.assertEqual(portfolio["input_candidates"], ["AAA"])
        self.assertEqual(portfolio["downside_threshold"], -0.05)
        self.assertEqual(portfolio, run(fake_get, portfolio_query, now, holdings))
        before_close = datetime.combine(days[-1], datetime.min.time(), zone)
        with self.assertRaisesRegex(DataError, "session has not closed"):
            run(fake_get, query, before_close)


if __name__ == "__main__":
    unittest.main()
