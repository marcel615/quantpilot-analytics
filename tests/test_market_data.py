import csv
from datetime import date, datetime, timedelta
from decimal import Decimal
from http.client import IncompleteRead
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from market_data.__main__ import check_sample, main
from market_data.alpaca import Alpaca, BARS_URL, CALENDAR_URL, DataError
from market_data.pipeline import HEADER, Query, Result, collect, price_return, publish


DAYS = (date(2024, 6, 7), date(2024, 6, 10))
QUERY = Query(("SPY", "NVDA"), *DAYS)


def bar(day, close=100):
    timestamp = datetime.combine(day, datetime.min.time(), ZoneInfo("America/New_York"))
    return {"t": timestamp.isoformat(), "o": close, "h": close + 1, "l": close - 1,
            "c": close, "v": 100}


class Sample:
    def __init__(self):
        self.calendar = [{"date": day.isoformat()} for day in DAYS]
        self.pages = {
            (mode, token): {"bars": {symbol: [bar(day) for day in DAYS]},
                            "next_page_token": next_token}
            for mode in ("raw", "split")
            for token, symbol, next_token in
            ((None, "NVDA", "next"), ("next", "SPY", None))
        }
        self.calls = []

    def get(self, endpoint, params):
        self.calls.append((endpoint, dict(params)))
        if endpoint == CALENDAR_URL:
            return json.dumps(self.calendar)
        if endpoint != BARS_URL:
            raise AssertionError(endpoint)
        page = self.pages[params["adjustment"], params.get("page_token")]
        if isinstance(page, Exception):
            raise page
        return json.dumps(page)


class MarketDataTests(unittest.TestCase):
    def setUp(self):
        self.sample = Sample()

    def test_collects_all_pages_with_identical_filters_and_sorted_usd_rows(self):
        result = collect(self.sample.get, QUERY)
        self.assertEqual(
            [("NVDA", "2024-06-07"), ("NVDA", "2024-06-10"),
             ("SPY", "2024-06-07"), ("SPY", "2024-06-10")],
            [row[:2] for row in result.rows],
        )
        self.assertEqual(("USD", "100", "101", "99", "100", "100",
                          "100", "101", "99", "100", "100"), result.rows[0][2:])
        self.assertEqual(4, result.metadata["row_count"])
        self.assertEqual(
            {"start": DAYS[0], "end": DAYS[-1], "date_type": "TRADING"},
            self.sample.calls[0][1],
        )
        calls = [params for endpoint, params in self.sample.calls if endpoint == BARS_URL]
        self.assertEqual(
            [("raw", None), ("raw", "next"), ("split", None), ("split", "next")],
            [(params["adjustment"], params.get("page_token")) for params in calls],
        )
        filters = [
            {key: value for key, value in params.items() if key not in {"adjustment", "page_token"}}
            for params in calls
        ]
        self.assertEqual(filters, [filters[0]] * 4)
        self.assertEqual(
            {"symbols": "NVDA,SPY", "start": "2024-06-07T00:00:00-04:00",
             "end": "2024-06-10T23:59:59.999999-04:00", "timeframe": "1Day",
             "currency": "USD", "feed": "iex", "asof": "-", "sort": "asc"},
            filters[0],
        )

    def test_reprocessing_deduplicates_equivalent_numbers_and_preserves_sort(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            initial = publish(QUERY, collect(self.sample.get, QUERY), root)
            records = self.sample.pages["raw", None]["bars"]["NVDA"]
            duplicate = dict(records[0], c=100.0, t="2024-06-07T04:00:00Z")
            records.insert(0, duplicate)
            records.reverse()
            again = publish(QUERY, collect(self.sample.get, QUERY), root)
            self.assertEqual((initial / "prices.csv").read_bytes(),
                             (again / "prices.csv").read_bytes())
            with (again / "prices.csv").open(encoding="utf-8", newline="") as stream:
                rows = list(csv.reader(stream))
            self.assertEqual(HEADER, tuple(rows[0]))
            self.assertEqual(4, len(rows[1:]))
            self.assertEqual(again.name, (again.parent / "latest").read_text().strip())
            self.assertEqual(self.sample.calendar, json.loads((again / "calendar.json").read_text()))
            self.assertEqual(2, len(json.loads((again / "raw.json").read_text())))
            self.assertEqual(2, len(json.loads((again / "split.json").read_text())))
            self.assertEqual(4, json.loads((again / "metadata.json").read_text())["row_count"])

    def test_failures_preserve_last_published_result(self):
        def missing_price(records):
            del records[0]["c"]

        def broken_page(sample, records):
            sample.pages["split", "next"] = DataError("Alpaca HTTP 503")

        cases = (
            ("missing trading day", lambda sample, records: records.pop()),
            ("conflicting duplicate", lambda sample, records: records.append(bar(DAYS[0], 110))),
            ("missing or invalid close", lambda sample, records: missing_price(records)),
            ("invalid close", lambda sample, records: records[0].update(c=0)),
            ("invalid volume", lambda sample, records: records[0].update(v=-1)),
            ("OHLC price range", lambda sample, records: records[0].update(h=95)),
            ("unexpected trading day", lambda sample, records:
             records.append(bar(DAYS[0] + timedelta(days=1)))),
            ("split page 2: Alpaca HTTP 503", broken_page),
            ("repeated page token", lambda sample, records:
             sample.pages["split", "next"].update(next_page_token="next")),
            ("Trading calendar: empty", lambda sample, records: sample.calendar.clear()),
        )
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            initial = publish(QUERY, collect(self.sample.get, QUERY), root)
            pointer = initial.parent / "latest"
            csv_before = (initial / "prices.csv").read_bytes()
            for message, change in cases:
                with self.subTest(message=message):
                    sample = Sample()
                    change(sample, sample.pages["split", None]["bars"]["NVDA"])
                    with self.assertRaisesRegex(DataError, message):
                        publish(QUERY, collect(sample.get, QUERY), root)
                    self.assertEqual(initial.name, pointer.read_text().strip())
                    self.assertEqual(csv_before, (initial / "prices.csv").read_bytes())

    def test_publish_failure_preserves_existing_pointer(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = collect(self.sample.get, QUERY)
            initial = publish(QUERY, result, root)
            with patch("market_data.pipeline.os.replace", side_effect=OSError("file blocked")):
                with self.assertRaisesRegex(OSError, "file blocked"):
                    publish(QUERY, result, root)
            self.assertEqual(initial.name, (initial.parent / "latest").read_text().strip())
            self.assertEqual({"latest", initial.name}, {item.name for item in initial.parent.iterdir()})
            self.assertTrue((initial / "prices.csv").is_file())

    def test_split_acceptance(self):
        start, end = date(2024, 1, 2), date(2024, 12, 31)
        days = {start, end, *DAYS}
        for offset in range(1, (end - start).days):
            if len(days) == 252:
                break
            days.add(start + timedelta(days=offset))
        rows = []
        for symbol in ("NVDA", "SPY"):
            for day in sorted(days):
                raw = ("100", "100", "100", "100", "10")
                split = raw
                if (symbol, day) == ("NVDA", DAYS[0]):
                    split = ("10", "10", "10", "10", "100")
                rows.append((symbol, day.isoformat(), "USD", *raw, *split))
        check_sample(Result(rows, {}, "", {}))
        rows = [row for row in rows if row[:2] != ("NVDA", DAYS[0].isoformat())]
        with self.assertRaisesRegex(DataError, "expected 504 rows"):
            check_sample(Result(rows, {}, "", {}))

    def test_dividend_drop_is_preserved_and_returns_exclude_cash(self):
        for mode in ("raw", "split"):
            self.sample.pages[mode, "next"]["bars"]["SPY"][1] = dict(
                bar(DAYS[1], 99), dividend=1
            )
        result = collect(self.sample.get, QUERY)
        spy = [row for row in result.rows if row[0] == "SPY"]
        split_close = HEADER.index("close_split")
        self.assertEqual(["2024-06-07", "2024-06-10"], [row[1] for row in spy])
        self.assertEqual(["100", "99"], [row[split_close] for row in spy])
        self.assertEqual(Decimal("-0.01"), price_return(*(row[split_close] for row in spy)))

    def test_truncated_second_page_is_reported_and_keeps_last_result(self):
        client = Alpaca("test-key", "test-secret")
        responses = [
            json.dumps(self.sample.calendar),
            json.dumps(self.sample.pages["raw", None]),
        ]
        streams = []
        for body in responses:
            stream = MagicMock()
            stream.__enter__.return_value.read.return_value = body.encode()
            streams.append(stream)
        stream = MagicMock()
        stream.__enter__.return_value.read.side_effect = IncompleteRead(b"partial")
        streams.append(stream)
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            initial = publish(QUERY, collect(self.sample.get, QUERY), root)
            with patch("market_data.alpaca.urlopen", side_effect=streams):
                with self.assertRaisesRegex(DataError, "raw page 2: Unable to read"):
                    publish(QUERY, collect(client.get, QUERY), root)
            self.assertEqual(initial.name, (initial.parent / "latest").read_text().strip())

    def test_validate_only_does_not_publish(self):
        with patch("market_data.__main__.Alpaca") as client, patch("market_data.__main__.publish") as save:
            client.return_value.get.side_effect = self.sample.get
            with patch("builtins.print") as printed:
                code = main(["--symbols", "NVDA", "SPY", "--start", str(DAYS[0]), "--end", str(DAYS[1])])
        self.assertEqual(0, code)
        printed.assert_called_once_with("Validated 4 rows in memory")
        save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
