"""Read Alpaca Paper calendar and IEX stock bars."""

from datetime import datetime, time
from decimal import Decimal
from http.client import HTTPException
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class DataError(ValueError):
    """The request could not produce a complete, valid data set."""


CALENDAR_URL = "https://paper-api.alpaca.markets/v2/calendar"
BARS_URL = "https://data.alpaca.markets/v2/stocks/bars"


class Alpaca:
    def __init__(self, key, secret):
        if not key or not secret:
            raise DataError("Set APCA_API_KEY_ID and APCA_API_SECRET_KEY for Alpaca Paper.")
        self.key = key
        self.secret = secret

    def get(self, url, params):
        request = Request(f"{url}?{urlencode(params)}")
        request.add_unredirected_header("APCA-API-KEY-ID", self.key)
        request.add_unredirected_header("APCA-API-SECRET-KEY", self.secret)
        try:
            with urlopen(request, timeout=30) as response:
                return response.read().decode("utf-8")
        except HTTPError as error:
            raise DataError(f"Alpaca HTTP {error.code}") from None
        except (HTTPException, URLError, OSError, UnicodeError):
            raise DataError("Unable to read the Alpaca response") from None


def read_json(body, context):
    try:
        return json.loads(body, parse_float=Decimal)
    except (ValueError, TypeError):
        raise DataError(f"{context}: invalid JSON") from None


def fetch_calendar(get, start, end):
    try:
        body = get(CALENDAR_URL, {"start": start, "end": end, "date_type": "TRADING"})
    except DataError as error:
        raise DataError(f"Trading calendar: {error}") from None
    return body, read_json(body, "Trading calendar")


def iter_bar_pages(get, symbols, start, end, market_zone, adjustment):
    params = {
        "symbols": ",".join(symbols),
        "start": datetime.combine(start, time.min, market_zone).isoformat(),
        "end": datetime.combine(end, time.max, market_zone).isoformat(),
        "timeframe": "1Day",
        "currency": "USD",
        "feed": "iex",
        "adjustment": adjustment,
        "asof": "-",
        "sort": "asc",
    }
    seen_tokens = set()
    page = 1
    while True:
        context = f"{','.join(symbols)} {start}..{end} {adjustment} page {page}"
        try:
            body = get(BARS_URL, params)
        except DataError as error:
            raise DataError(f"{context}: {error}") from None
        payload = read_json(body, context)
        if not isinstance(payload, dict) or not isinstance(payload.get("bars"), dict):
            raise DataError(f"{context}: invalid bars response")
        yield body, payload["bars"]
        token = payload.get("next_page_token")
        if token is None:
            return
        if not isinstance(token, str) or not token or token in seen_tokens:
            raise DataError(f"{context}: invalid or repeated page token")
        seen_tokens.add(token)
        params["page_token"] = token
        page += 1
