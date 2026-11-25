"""Compare downside candidates using Alpaca Basic IEX daily bars."""

import argparse
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import json
import os
import sys
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from market_data.alpaca import Alpaca, DataError, fetch_calendar
from market_data.pipeline import OHLCV, Query, collect_mode, trading_days

from .experiment import HOLDING, SELECTION_END, compare, input_digest


HISTORY_START = date(2016, 1, 1)
VALIDATION_END_LIMIT = date(2026, 12, 31)
ALLOCATION_COMPARISON_END = date(2026, 11, 24)
ALLOCATION_COMPARISON_CANDIDATES = frozenset(("QQQ", "XLP", "XLU", "IEF", "SHY", "GLD", "UUP"))


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


def run(get, query, now, holdings=None, *, allocation_comparison=False):
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
    holding_symbols = (HOLDING,) if holdings is None else holdings
    candidates = tuple(symbol for symbol in query.symbols if symbol not in holding_symbols)
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
        **compare(closes, days, candidates, holdings, allocation_comparison=allocation_comparison),
    }


def parse_holdings(values):
    holdings = {}
    if len(values) not in (2, 3):
        raise DataError("provide two or three holdings as TICKER=PERCENT")
    for value in values:
        symbol, separator, percent = value.partition("=")
        try:
            weight = Decimal(percent)
        except InvalidOperation:
            raise DataError("provide holdings as TICKER=PERCENT") from None
        if not separator or not symbol or symbol in holdings:
            raise DataError("provide distinct holdings as TICKER=PERCENT")
        if not weight.is_finite() or not 0 < weight < 100:
            raise DataError("each holding must have a positive weight below 100%")
        holdings[symbol] = weight
    if sum(map(Fraction, holdings.values())) != 100:
        raise DataError("holding weights must sum to 100%")
    return holdings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", nargs="+", required=True, metavar="TICKER")
    parser.add_argument("--holdings", nargs="+", metavar="TICKER=PERCENT",
                        help="Two or three reference holdings. Omit to use NVDA as the reference.")
    parser.add_argument("--end", type=date.fromisoformat, required=True, metavar="YYYY-MM-DD",
                        help="Last completed New York trading session to evaluate in 2026.")
    parser.add_argument("--compare-allocations", action="store_true",
                        help="Compare NVDA/SPY with cash, one portfolio ETF and two individual ETFs.")
    args = parser.parse_args(argv)
    if args.compare_allocations:
        if args.holdings:
            parser.error("--compare-allocations uses NVDA=50 SPY=50; omit --holdings")
        if (args.end != ALLOCATION_COMPARISON_END
                or len(args.candidates) != len(ALLOCATION_COMPARISON_CANDIDATES)
                or set(args.candidates) != ALLOCATION_COMPARISON_CANDIDATES):
            parser.error("--compare-allocations uses --end 2026-11-24 and candidates QQQ XLP XLU IEF SHY GLD UUP")
    try:
        holdings = parse_holdings(args.holdings) if args.holdings else None
    except DataError as error:
        parser.error(str(error))
    if args.compare_allocations:
        holdings = {"NVDA": Decimal(50), "SPY": Decimal(50)}
    holding_symbols = (HOLDING,) if holdings is None else tuple(holdings)
    if not 1 <= len(args.candidates) <= 10 or set(holding_symbols).intersection(args.candidates):
        parser.error("provide 1 to 10 candidates distinct from the reference holdings")
    if not SELECTION_END < args.end <= VALIDATION_END_LIMIT:
        parser.error("--end must be a 2026 trading date")
    try:
        query = Query((*holding_symbols, *args.candidates), HISTORY_START, args.end)
        client = Alpaca(os.getenv("APCA_API_KEY_ID"), os.getenv("APCA_API_SECRET_KEY"))
        report = run(client.get, query, datetime.now().astimezone(), holdings,
                     allocation_comparison=args.compare_allocations)
    except ZoneInfoNotFoundError:
        print("Install tzdata to provide the America/New_York time zone.", file=sys.stderr)
        return 1
    except (DataError, OSError) as error:
        report = {
            "status": "insufficient_data",
            "reason": str(error),
            "requested_start": HISTORY_START.isoformat(),
            "requested_end": args.end.isoformat(),
            "input_candidates": args.candidates,
        }
        if holdings is not None:
            report["holdings_percent"] = {symbol: str(weight) for symbol, weight in holdings.items()}
        print(json.dumps(report, indent=2))
        return 1
    print(json.dumps(report, indent=2, allow_nan=False))
    return int(report["status"] == "insufficient_data")


if __name__ == "__main__":
    sys.exit(main())
