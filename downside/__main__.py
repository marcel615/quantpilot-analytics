"""Compare NVDA downside candidates using Alpaca Basic IEX daily bars."""

import argparse
from datetime import date, datetime, time
from decimal import Decimal
import json
import os
import sys
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from market_data.alpaca import Alpaca, DataError, fetch_calendar
from market_data.pipeline import OHLCV, Query, collect_mode, trading_days

from .experiment import HOLDING, SELECTION_END, compare, input_digest


HISTORY_START = date(2016, 1, 1)
VALIDATION_END_LIMIT = date(2026, 12, 31)


def require_completed_session(calendar, day, now):
    if day < now.date():
        return
    session = next(entry for entry in calendar if entry["date"] == day.isoformat())
    try:
        close = time.fromisoformat(session["close"])
    except (KeyError, TypeError, ValueError):
        raise DataError(f"{day}: unable to confirm the New York session close") from None
    if day > now.date() or now.time() < close:
        raise DataError(f"{day}: session has not closed in New York")


def run(get, query, now):
    zone = ZoneInfo("America/New_York")
    _, calendar = fetch_calendar(get, query.start, query.end)
    days = sorted(trading_days(calendar, query))
    if days[-1] != query.end:
        raise DataError(f"{query.end}: choose a New York trading session for --end")
    require_completed_session(calendar, query.end, now.astimezone(zone))
    expected = {(symbol, day) for symbol in query.symbols for day in days}
    # The analysis determines the common start, then rejects gaps in the applicable
    # periods. Keep the collection validation for both price adjustments.
    raw, _ = collect_mode(get, query, zone, "raw", expected, require_complete=False)
    split, _ = collect_mode(get, query, zone, "split", expected, require_complete=False)
    closes = {symbol: {} for symbol in query.symbols}
    for (symbol, day), values in split.items():
        if (symbol, day) in raw:
            closes[symbol][day] = Decimal(values[OHLCV.index("close")])
    candidates = tuple(symbol for symbol in query.symbols if symbol != HOLDING)
    return {
        "input": {
            "source": "Alpaca Basic (Paper)",
            "feed": "iex",
            "currency": "USD",
            "price": "close_split",
            "requested_start": query.start.isoformat(),
            "requested_end": query.end.isoformat(),
            "observed_sessions": {symbol: len(prices) for symbol, prices in closes.items()},
            "sha256": input_digest(closes, days),
        },
        **compare(closes, days, candidates),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", nargs="+", required=True, metavar="TICKER")
    parser.add_argument("--end", type=date.fromisoformat, required=True, metavar="YYYY-MM-DD",
                        help="Last completed New York trading session to evaluate in 2026.")
    args = parser.parse_args(argv)
    if not 1 <= len(args.candidates) <= 10 or HOLDING in args.candidates:
        parser.error("provide 1 to 10 candidates distinct from NVDA")
    if not SELECTION_END < args.end <= VALIDATION_END_LIMIT:
        parser.error("--end must be a 2026 trading date")
    try:
        query = Query((HOLDING, *args.candidates), HISTORY_START, args.end)
        client = Alpaca(os.getenv("APCA_API_KEY_ID"), os.getenv("APCA_API_SECRET_KEY"))
        report = run(client.get, query, datetime.now().astimezone())
    except ZoneInfoNotFoundError:
        print("Install tzdata to provide the America/New_York time zone.", file=sys.stderr)
        return 1
    except (DataError, OSError) as error:
        print(json.dumps({
            "status": "insufficient_data",
            "reason": str(error),
            "requested_start": HISTORY_START.isoformat(),
            "requested_end": args.end.isoformat(),
            "input_candidates": args.candidates,
        }, indent=2))
        return 1
    print(json.dumps(report, indent=2, allow_nan=False))
    return int(report["status"] == "insufficient_data")


if __name__ == "__main__":
    sys.exit(main())
