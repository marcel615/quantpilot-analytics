"""Command-line entry point for historical market data."""

import argparse
from datetime import date
from decimal import Decimal
import os
import sys
from zoneinfo import ZoneInfoNotFoundError

from .alpaca import Alpaca, DataError
from .pipeline import Query, collect, publish


def check_sample(result):
    rows = {(symbol, day): values for symbol, day, _, *values in result.rows}
    if len(rows) != 504:
        raise DataError(f"2024 IEX acceptance: expected 504 rows, got {len(rows)}")
    for symbol in ("NVDA", "SPY"):
        days = sorted(day for ticker, day in rows if ticker == symbol)
        if len(days) != 252 or (days[0], days[-1]) != ("2024-01-02", "2024-12-31"):
            raise DataError(f"{symbol}: acceptance requires 252 sessions with 2024 boundaries")
    before = list(map(Decimal, rows["NVDA", "2024-06-07"]))
    after = list(map(Decimal, rows["NVDA", "2024-06-10"]))
    if not Decimal("9.999") <= before[3] / before[8] <= Decimal("10.001"):
        raise DataError("NVDA 2024-06-07: unexpected close ratio")
    if before[9] != before[4] * 10 or after[8:10] != after[3:5]:
        raise DataError("NVDA: unexpected volume or post-split price/volume")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate Alpaca Basic IEX daily prices.")
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--save", action="store_true",
                        help="Save files after confirming the account permits retention.")
    parser.add_argument("--check-2024-sample", action="store_true",
                        help="Check the NVDA/SPY 2024 acceptance sample.")
    args = parser.parse_args(argv)
    try:
        query = Query(tuple(args.symbols), args.start, args.end)
        if args.check_2024_sample and query != Query(
            ("NVDA", "SPY"), date(2024, 1, 1), date(2024, 12, 31)
        ):
            raise DataError("--check-2024-sample requires NVDA SPY and the full 2024 date range.")
        client = Alpaca(os.getenv("APCA_API_KEY_ID"), os.getenv("APCA_API_SECRET_KEY"))
        result = collect(client.get, query)
        if args.check_2024_sample:
            check_sample(result)
        if args.save:
            directory = publish(query, result)
            print(f"Validated {len(result.rows)} rows and published {directory}")
        else:
            print(f"Validated {len(result.rows)} rows in memory")
    except ZoneInfoNotFoundError:
        print("Install tzdata to provide the America/New_York time zone.", file=sys.stderr)
        return 1
    except (DataError, OSError) as error:
        print(f"Collection failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
