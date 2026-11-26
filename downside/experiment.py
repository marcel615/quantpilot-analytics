"""Screen candidates on past prices and compare fixed allocations out of sample."""

from datetime import date
from decimal import Decimal
from fractions import Fraction
import hashlib
import json
from statistics import mean

from market_data.pipeline import price_return


HOLDING = "NVDA"
SELECTION_END = date(2025, 12, 31)
RECENT_START = date(2023, 1, 1)
HOLDING_WEIGHT = Decimal("0.8")
CANDIDATE_WEIGHT = 1 - HOLDING_WEIGHT
MIN_DOWNSIDE_DAYS = 10


def maximum_drawdown(values):
    peak = values[0]
    drawdown = Decimal(0)
    for value in values:
        peak = max(peak, value)
        drawdown = max(drawdown, 1 - value / peak)
    return float(drawdown)


def price_metrics(prices, days):
    values = [prices[day] for day in days]
    return {
        "cumulative_return": float(price_return(values[0], values[-1])),
        "maximum_drawdown": maximum_drawdown(values),
    }


def daily_returns(prices, days):
    return [price_return(prices[previous], prices[current])
            for previous, current in zip(days, days[1:])]


def portfolio_returns(closes, days, holdings):
    if holdings is None:
        return daily_returns(closes[HOLDING], days)
    components = [(closes[symbol], Fraction(weight) / 100)
                  for symbol, weight in holdings.items()]
    returns = []
    for previous, current in zip(days, days[1:]):
        # Keep offsetting contributions exact before testing sign or sorting.
        weighted = sum(weight * (Fraction(prices[current]) / Fraction(prices[previous]) - 1)
                       for prices, weight in components)
        returns.append(weighted)
    return returns


def missing_dates(prices, days):
    return [day.isoformat() for day in days if day not in prices]


def screen_candidate(prices, selection, recent):
    missing = missing_dates(prices, selection)
    recent_metrics = None
    if len(recent) >= 2 and not missing_dates(prices, recent):
        recent_metrics = price_metrics(prices, recent)
    result = {
        "selection_price_metrics": None,
        "recent_three_year_price_metrics": recent_metrics,
        "recent_three_year_status": (
            "insufficient_data" if recent_metrics is None else
            "negative_return" if recent_metrics["cumulative_return"] < 0 else "available"
        ),
        "selection_missing_dates": missing,
        "selected": False,
        "exclusion_reason": None,
    }
    if missing:
        result["exclusion_reason"] = "missing_selection_prices"
    else:
        result["selection_price_metrics"] = price_metrics(prices, selection)
        result["selected"] = prices[selection[-1]] >= prices[selection[0]]
        if not result["selected"]:
            result["exclusion_reason"] = "negative_selection_return"
    return result


def average_on(returns, indices):
    return mean(returns[index] for index in indices) if indices else None


def excess_over_cash(prices, days, downside):
    if not downside:
        return None
    # Keep offsetting gains and losses exact before deciding whether a candidate beat cash.
    price_changes = (Fraction(prices[days[index + 1]]) / Fraction(prices[days[index]]) - 1
                     for index in downside)
    return float(100 * Fraction(CANDIDATE_WEIGHT) * mean(price_changes))


def allocation_metrics(returns, downside, upside):
    path = [Decimal(1)]
    for change in returns:
        path.append(path[-1] * (1 + change))
    downside_average = average_on(returns, downside)
    upside_average = average_on(returns, upside)
    return {
        "downside_mean_return": None if downside_average is None else float(downside_average),
        "upside_mean_return": None if upside_average is None else float(upside_average),
        "cumulative_return": float(path[-1] - 1),
        "maximum_drawdown": maximum_drawdown(path),
    }


def compare_period(closes, symbols, days, threshold, holding):
    downside = [index for index, change in enumerate(holding) if change < 0 and change <= threshold]
    upside = [index for index, change in enumerate(holding) if change > 0]
    if isinstance(holding[0], Fraction):
        holding = [Decimal(change.numerator) / Decimal(change.denominator) for change in holding]
    cash_mix = [HOLDING_WEIGHT * change for change in holding]
    candidates = {}
    for symbol in symbols:
        candidate = daily_returns(closes[symbol], days)
        mixed = [core + CANDIDATE_WEIGHT * change for core, change in zip(cash_mix, candidate)]
        candidates[symbol] = {
            **allocation_metrics(mixed, downside, upside),
            "downside_excess_over_cash_pp": excess_over_cash(closes[symbol], days, downside),
        }
    return {
        "first_return_date": days[1].isoformat(),
        "last_return_date": days[-1].isoformat(),
        "downside_days": len(downside),
        "upside_days": len(upside),
        "holding_only": allocation_metrics(holding, downside, upside),
        "with_cash": allocation_metrics(cash_mix, downside, upside),
        "with_candidates": candidates,
    }


def exact_returns(prices, days):
    return [Fraction(prices[current]) / Fraction(prices[previous]) - 1
            for previous, current in zip(days, days[1:])]


def downside_indices(returns, threshold):
    return [index for index, change in enumerate(returns) if change < 0 and change <= threshold]


def downside_threshold(returns):
    return sorted(returns)[(len(returns) - 1) // 10]


def compare_allocations(closes, selection, validation, eligible, holdings, report):
    scopes = (*holdings, "portfolio")
    references = {symbol: exact_returns(closes[symbol], selection) for symbol in holdings}
    references["portfolio"] = portfolio_returns(closes, selection, holdings)
    thresholds = {scope: downside_threshold(references[scope]) for scope in scopes}
    dates = {scope: downside_indices(references[scope], thresholds[scope]) for scope in scopes}
    report["downside_threshold"] = float(thresholds["portfolio"])
    report["selection"] = {
        scope: {"downside_threshold": float(thresholds[scope]), "downside_days": len(dates[scope])}
        for scope in scopes
    }
    if any(not indices for indices in dates.values()):
        report["reason"] = "no_selection_downside_days"
        return report
    if len(eligible) < 2:
        report["status"] = "no_suitable_candidate"
        if any(result["selection_missing_dates"] for result in report["candidates"].values()):
            report["status"] = "insufficient_data"
        report["reason"] = "fewer_than_two_eligible_candidates"
        return report

    symbols = sorted(eligible)
    returns = {symbol: exact_returns(closes[symbol], selection) for symbol in symbols}
    scores = {scope: {symbol: average_on(returns[symbol], dates[scope]) for symbol in symbols}
              for scope in scopes}
    first, second = holdings
    portfolio_etf = max(symbols, key=scores["portfolio"].__getitem__)
    pairs = ((left, right) for left in symbols for right in symbols if left != right)
    pair = max(pairs, key=lambda pair: scores[first][pair[0]] + scores[second][pair[1]])
    report["selected_etfs"] = {
        "portfolio": portfolio_etf,
        "individual": dict(zip(holdings, pair)),
    }

    days = [selection[-1], *validation]
    required = dict.fromkeys((*holdings, portfolio_etf, *pair))
    missing = {symbol: missing_dates(closes[symbol], days) for symbol in required}
    report["missing_validation_dates"] = {symbol: gaps for symbol, gaps in missing.items() if gaps}
    if report["missing_validation_dates"]:
        report["reason"] = "missing_validation_prices"
        return report

    reference = portfolio_returns(closes, days, holdings)
    downside = downside_indices(reference, thresholds["portfolio"])
    upside = [index for index, change in enumerate(reference) if change > 0]
    cash = [Fraction(HOLDING_WEIGHT) * change for change in reference]
    allocations = {
        "cash": cash,
        "portfolio": add_etfs(cash, closes, days, (portfolio_etf,)),
        "individual": add_etfs(cash, closes, days, pair),
    }
    report["validation"] = {
        "first_return_date": days[1].isoformat(),
        "last_return_date": days[-1].isoformat(),
        "downside_days": len(downside),
        "allocations": {name: comparison_metrics(values, cash, downside, upside)
                        for name, values in allocations.items()},
    }
    report["validation_sample_sufficient"] = len(downside) >= MIN_DOWNSIDE_DAYS
    if report["validation_sample_sufficient"]:
        report["status"] = "comparison_complete"
    else:
        report["status"] = "insufficient_sample"
        report["reason"] = "too_few_validation_downside_days"
    return report


def add_etfs(cash, closes, days, symbols):
    weight = Fraction(CANDIDATE_WEIGHT) / len(symbols)
    candidate_returns = [exact_returns(closes[symbol], days) for symbol in symbols]
    return [core + weight * sum(changes) for core, *changes in zip(cash, *candidate_returns)]


def comparison_metrics(returns, cash, downside, upside):
    decimal_returns = [Decimal(value.numerator) / Decimal(value.denominator) for value in returns]
    exact_mean = average_on(returns, downside)
    metrics = {
        **allocation_metrics(decimal_returns, downside, upside),
        "downside_mean_return": None if exact_mean is None else float(exact_mean),
        "downside_worst_return": min((float(returns[index]) for index in downside), default=None),
    }
    if cash is not None:
        cash_mean = average_on(cash, downside)
        metrics["downside_excess_over_cash_pp"] = (
            None if exact_mean is None else float(100 * (exact_mean - cash_mean))
        )
    return metrics


def compare(closes, calendar, candidates, holdings=None, *, allocation_comparison=False):
    selection_calendar = [day for day in calendar if day <= SELECTION_END]
    validation = [day for day in calendar if day > SELECTION_END]
    report = {
        "holding": HOLDING,
        "input_candidates": list(candidates),
        "common_start": None,
        "selection_end": selection_calendar[-1].isoformat() if selection_calendar else None,
        "validation_start": validation[0].isoformat() if validation else None,
        "validation_end": validation[-1].isoformat() if validation else None,
        "assumptions": {
            "holding_weight": float(HOLDING_WEIGHT),
            "candidate_or_cash_weight": float(CANDIDATE_WEIGHT),
            "cash_daily_return": 0,
            "trading_cost": 0,
            "rebalance": "daily",
            "downside_quantile": 0.1,
            "minimum_validation_downside_days": MIN_DOWNSIDE_DAYS,
        },
        "candidates": {},
        "downside_threshold": None,
        "selection": None,
        "validation": None,
        "validation_sample_sufficient": None,
        "additional_defense": [],
        "status": "insufficient_data",
    }
    if allocation_comparison:
        del report["additional_defense"]
        report["mode"] = "allocation_comparison"
        report["selected_etfs"] = None
    holding_symbols = (HOLDING,) if holdings is None else tuple(holdings)
    if holdings is not None:
        del report["holding"]
        report["holdings_percent"] = {symbol: str(weight) for symbol, weight in holdings.items()}
    symbols = (*holding_symbols, *candidates)
    first_days = {symbol: next((day for day in selection_calendar if day in closes[symbol]), None)
                  for symbol in symbols}
    absent = [symbol for symbol, day in first_days.items() if day is None]
    if absent or not validation:
        report["reason"] = "no_selection_prices" if absent else "no_validation_sessions"
        report["symbols_without_selection_prices"] = absent
        return report

    common_start = max(first_days.values())
    report["common_start"] = common_start.isoformat()
    selection = [day for day in selection_calendar if day >= common_start]
    if len(selection) < 2:
        report["reason"] = "too_few_common_selection_sessions"
        return report

    recent = [day for day in selection_calendar if day >= RECENT_START]
    for symbol in candidates:
        report["candidates"][symbol] = screen_candidate(closes[symbol], selection, recent)
    selected = [symbol for symbol in candidates if report["candidates"][symbol]["selected"]]
    missing_holding = {symbol: missing_dates(closes[symbol], selection) for symbol in holding_symbols}
    missing_holding = {symbol: dates for symbol, dates in missing_holding.items() if dates}
    if missing_holding:
        report["reason"] = "missing_holding_selection_prices"
        report["missing_selection_dates"] = missing_holding[HOLDING] if holdings is None else missing_holding
        return report

    if allocation_comparison:
        return compare_allocations(closes, selection, validation, selected, holdings, report)
    selection_returns = portfolio_returns(closes, selection, holdings)
    threshold = downside_threshold(selection_returns)
    report["downside_threshold"] = float(threshold)
    report["selection"] = compare_period(closes, selected, selection, threshold, selection_returns)

    validation_with_anchor = [selection[-1], *validation]
    missing_validation = {symbol: missing_dates(closes[symbol], validation_with_anchor)
                          for symbol in (*holding_symbols, *selected)}
    report["missing_validation_dates"] = {symbol: days for symbol, days in missing_validation.items() if days}
    if report["missing_validation_dates"]:
        report["reason"] = "missing_validation_prices"
        return report

    validation_returns = portfolio_returns(closes, validation_with_anchor, holdings)
    evaluation = compare_period(closes, selected, validation_with_anchor, threshold, validation_returns)
    report["validation"] = evaluation
    sufficient_sample = evaluation["downside_days"] >= MIN_DOWNSIDE_DAYS
    report["validation_sample_sufficient"] = sufficient_sample
    incomplete_selection = [symbol for symbol, result in report["candidates"].items()
                            if result["selection_missing_dates"]]
    if not selected:
        report["status"] = "no_suitable_candidate"
        report["reason"] = "no_candidate_passed_selection"
        if incomplete_selection:
            report["status"] = "insufficient_data"
            report["reason"] = "selection_prices_incomplete"
    elif not sufficient_sample:
        report["status"] = "insufficient_sample"
        report["reason"] = "too_few_validation_downside_days"
    else:
        defense = [symbol for symbol, metrics in evaluation["with_candidates"].items()
                   if metrics["downside_excess_over_cash_pp"] > 0]
        report["additional_defense"] = defense
        report["status"] = "additional_defense_found" if defense else "no_suitable_candidate"
        if not defense:
            report["reason"] = "no_candidate_outperformed_cash_on_downside_days"
    return report


def input_digest(closes, calendar):
    payload = {
        "calendar": [day.isoformat() for day in calendar],
        "close_split": {symbol: {day.isoformat(): str(price) for day, price in prices.items()}
                        for symbol, prices in closes.items()},
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
