"""Validate a complete request and publish its reproducible artifacts."""

import csv
from dataclasses import dataclass
from datetime import date, datetime, UTC
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from uuid import uuid4
from zoneinfo import ZoneInfo

from .alpaca import DataError, fetch_calendar, iter_bar_pages


ROOT = Path(__file__).resolve().parents[1] / ".local" / "market-data"
MODES = ("raw", "split")
OHLCV = ("open", "high", "low", "close", "volume")
HEADER = ("symbol", "trade_date", "currency") + tuple(
    f"{field}_{mode}" for mode in MODES for field in OHLCV
)


@dataclass(frozen=True)
class Query:
    symbols: tuple[str, ...]
    start: date
    end: date

    def __post_init__(self):
        if not self.symbols or self.start > self.end:
            raise DataError("Provide symbols and an inclusive start date no later than end.")
        if any(not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-]*", symbol) for symbol in self.symbols):
            raise DataError("Use uppercase US ticker symbols.")
        if len(set(self.symbols)) != len(self.symbols):
            raise DataError("Each requested symbol must be unique.")
        object.__setattr__(self, "symbols", tuple(sorted(self.symbols)))


@dataclass
class Result:
    rows: list
    metadata: dict
    calendar_body: str
    raw_pages: dict


def trading_days(calendar, query):
    if not isinstance(calendar, list):
        raise DataError("Trading calendar: expected a list of sessions")
    try:
        days = {date.fromisoformat(entry["date"]) for entry in calendar}
    except (KeyError, TypeError, ValueError):
        raise DataError("Trading calendar: invalid session date") from None
    if not days or any(not query.start <= day <= query.end for day in days):
        raise DataError("Trading calendar: empty or outside the requested range")
    return days


def bar_day(bar, zone, context):
    try:
        timestamp = datetime.fromisoformat(bar["t"])
        if timestamp.utcoffset() is None:
            raise ValueError
        return timestamp.astimezone(zone).date()
    except (KeyError, TypeError, ValueError, OverflowError):
        raise DataError(f"{context}: invalid or missing timestamp") from None


def bar_values(bar, context):
    values = []
    for key, field in zip(("o", "h", "l", "c", "v"), OHLCV):
        value = bar.get(key)
        if type(value) not in (int, Decimal):
            raise DataError(f"{context}: missing or invalid {field}")
        number = Decimal(value)
        if not number.is_finite() or number < 0 or (key != "v" and number == 0):
            raise DataError(f"{context}: invalid {field}")
        # Canonical fixed-point output makes equal duplicates independent of input order.
        fixed = format(number, "f")
        if not number:
            fixed = "0"
        elif "." in fixed:
            fixed = fixed.rstrip("0").rstrip(".")
        values.append(fixed)
    opened, high, low, closed = map(Decimal, values[:4])
    if low > min(opened, closed) or high < max(opened, closed):
        raise DataError(f"{context}: OHLC price range violation")
    return tuple(values)


def collect_mode(get, query, zone, mode, expected):
    values = {}
    bodies = []
    for body, bars in iter_bar_pages(get, query.symbols, query.start, query.end, zone, mode):
        bodies.append(body)
        for symbol, records in bars.items():
            if symbol not in query.symbols or not isinstance(records, list):
                raise DataError(f"{symbol} {mode}: unexpected symbol or invalid bar list")
            for record in records:
                day = bar_day(record, zone, f"{symbol} {mode}")
                context = f"{symbol} {day} {mode}"
                key = (symbol, day)
                if key not in expected:
                    raise DataError(f"{context}: unexpected trading day")
                row = bar_values(record, context)
                if values.setdefault(key, row) != row:
                    raise DataError(f"{context}: conflicting duplicate")
    missing = expected - values.keys()
    if missing:
        symbol, day = min(missing)
        raise DataError(f"{symbol} {day} {mode}: missing trading day ({len(missing)} total)")
    return values, bodies


def collect(get, query):
    zone = ZoneInfo("America/New_York")
    calendar_body, calendar = fetch_calendar(get, query.start, query.end)
    days = trading_days(calendar, query)
    expected = {(symbol, day) for symbol in query.symbols for day in days}
    raw, raw_pages = collect_mode(get, query, zone, "raw", expected)
    split, split_pages = collect_mode(get, query, zone, "split", expected)
    rows = [(symbol, day.isoformat(), "USD", *raw[symbol, day], *split[symbol, day])
            for symbol, day in sorted(expected)]
    metadata = {
        "source": "Alpaca Basic (Paper)",
        "feed": "iex",
        "symbols": query.symbols,
        "start": query.start.isoformat(),
        "end": query.end.isoformat(),
        "timeframe": "1Day",
        "currency": "USD",
        "market_timezone": zone.key,
        "symbol_mapping": {"asof": "-", "description": "exact ticker without name lookup"},
        "adjustments": MODES,
        "collected_at": datetime.now(UTC).isoformat(),
        "row_count": len(rows),
    }
    return Result(rows, metadata, calendar_body, {"raw": raw_pages, "split": split_pages})


def price_return(first_split_close, last_split_close):
    """Price return over the period, based on split-adjusted closing prices."""
    return Decimal(last_split_close) / Decimal(first_split_close) - 1


def write_artifacts(directory, result):
    (directory / "calendar.json").write_text(result.calendar_body, encoding="utf-8")
    for mode in MODES:
        pages = ",\n".join(result.raw_pages[mode])
        (directory / f"{mode}.json").write_text(f"[\n{pages}\n]\n", encoding="utf-8")
    with (directory / "prices.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(HEADER)
        writer.writerows(result.rows)
    (directory / "metadata.json").write_text(
        json.dumps(result.metadata, indent=2) + "\n", encoding="utf-8"
    )


def publish(query, result, root=ROOT):
    identity = "-".join((query.start.isoformat(), query.end.isoformat(),
                         ",".join(query.symbols)))
    # Keep the request directory short enough for nested Windows worktrees.
    request_dir = root / hashlib.blake2b(identity.encode(), digest_size=16).hexdigest()
    generation = uuid4().hex
    directory = request_dir / generation
    directory.mkdir(parents=True)
    temporary_pointer = None
    try:
        write_artifacts(directory, result)
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=request_dir, delete=False) as stream:
            temporary_pointer = Path(stream.name)
            stream.write(generation + "\n")

        # This is the only publication step. Readers can use the last complete
        # generation until this replacement succeeds, including during concurrent runs.
        os.replace(temporary_pointer, request_dir / "latest")
    except OSError:
        if temporary_pointer is not None:
            temporary_pointer.unlink(missing_ok=True)
        for path in directory.iterdir():
            path.unlink()
        directory.rmdir()
        raise
    return directory
