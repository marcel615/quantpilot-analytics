"""Run the approved experiment or predict from its saved model."""

import argparse
from datetime import date, datetime, time
import json
import os
from pathlib import Path
import platform
import shlex
import sys
from tempfile import NamedTemporaryFile
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import numpy as np

from market_data.__main__ import check_sample
from market_data.alpaca import Alpaca, DataError
from market_data.pipeline import Query, collect, trading_days

from .experiment import (
    PERIODS, SYMBOLS, input_digest, load_model, model_payload, predict_day, run_experiment,
)

MODEL_PATH = Path(__file__).resolve().parents[1] / ".local" / "forecast" / "model.json"


def save_model(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(payload, stream, indent=2, allow_nan=False)
            stream.write("\n")
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def ensure_session_closed(day, calendar, now):
    if day < now.date():
        return
    if day == now.date():
        try:
            closing = next(session["close"] for session in calendar
                           if session["date"] == day.isoformat())
            if now.time() >= time.fromisoformat(closing):
                return
        except (KeyError, StopIteration, TypeError, ValueError):
            raise DataError(f"{day}: unable to confirm the session close") from None
    raise DataError(f"{day}: session has not closed in New York")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("train", help="Train and evaluate the fixed NVDA/SPY 2024 experiment.")
    predict = commands.add_parser("predict", help="Predict returns as of a new session.")
    predict.add_argument("--history-start", type=date.fromisoformat, required=True)
    predict.add_argument("--as-of", type=date.fromisoformat, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "train":
            query = Query(SYMBOLS, PERIODS[0][1], PERIODS[-1][2])
        else:
            model = load_model(json.loads(MODEL_PATH.read_text(encoding="utf-8")))
            if args.as_of <= PERIODS[-1][2]:
                raise DataError("--as-of must follow the 2024 experiment")
            query = Query(SYMBOLS, args.history_start, args.as_of)
            requested_at = datetime.now(ZoneInfo("America/New_York"))
        client = Alpaca(os.getenv("APCA_API_KEY_ID"), os.getenv("APCA_API_SECRET_KEY"))
        result = collect(client.get, query)
        calendar = json.loads(result.calendar_body)
        days = sorted(trading_days(calendar, query))
        metadata = {
            "input": {**result.metadata, "sha256": input_digest(result.rows, days)},
            "command": shlex.join(["python", "-m", "forecast", *argv]),
            "environment": {
                "python": platform.python_version(),
                "numpy": np.__version__,
                "platform": platform.platform(),
            },
        }
        if args.command == "train":
            check_sample(result)
            model, report, _ = run_experiment(result.rows, days)
            payload = {**model_payload(model), **metadata, "report": report}
            save_model(MODEL_PATH, payload)
            report = {**metadata, **report, "model_path": str(MODEL_PATH)}
        else:
            ensure_session_closed(args.as_of, calendar, requested_at)
            report = {**metadata, "predictions": predict_day(model, result.rows, days, args.as_of)}
        print(json.dumps(report, indent=2, allow_nan=False))
    except ZoneInfoNotFoundError:
        print("Install tzdata to provide the America/New_York time zone.", file=sys.stderr)
        return 1
    except (DataError, OSError, ValueError, np.linalg.LinAlgError) as error:
        print(f"Forecast failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
