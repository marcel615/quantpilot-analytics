"""Evaluate defensive ETF allocations over all sessions in two historical windows."""

from datetime import date
from fractions import Fraction

from .experiment import (
    HOLDING,
    MIN_DOWNSIDE_DAYS,
    average_on,
    downside_indices,
    downside_threshold,
    exact_returns,
    missing_dates,
)
from .weight_study import VALIDATION_YEARS, WEIGHTS


def evaluate_holding_period(closes, calendar, candidates):
    windows = {}
    for year in VALIDATION_YEARS:
        selection = [day for day in calendar if day < date(year, 1, 1)]
        validation = [day for day in calendar if day.year == year]
        windows[str(year)] = evaluate_window(closes, selection, validation, candidates)
    return {
        "mode": "holding_period_study",
        "holding": HOLDING,
        "input_candidates": list(candidates),
        "candidate_weights_percent": list(WEIGHTS),
        "cash_daily_return": 0,
        "trading_cost": 0,
        "rebalance": "daily",
        "minimum_validation_downside_days": MIN_DOWNSIDE_DAYS,
        "windows": windows,
        "status": ("insufficient_data" if any(
            window["status"] == "insufficient_data" for window in windows.values()
        ) else "comparison_complete"),
    }


def evaluate_window(closes, selection, validation, candidates):
    report = {
        "status": "insufficient_data",
        "selection_start": None,
        "selection_end": selection[-1].isoformat() if selection else None,
        "validation_start": validation[0].isoformat() if validation else None,
        "validation_end": validation[-1].isoformat() if validation else None,
        "selected": None,
        "candidates": {},
        "allocations": None,
        "validation_target_met": None,
    }
    if not selection or not validation:
        return {**report, "reason": "missing_selection_or_validation_sessions"}

    first_days = {
        symbol: next((day for day in selection if day in closes[symbol]), None)
        for symbol in (HOLDING, *candidates)
    }
    if first_days[HOLDING] is None:
        return {**report, "reason": "no_holding_selection_prices"}
    start = max(day for day in first_days.values() if day is not None)
    report["selection_start"] = start.isoformat()
    selection = [day for day in selection if day >= start]
    missing = missing_dates(closes[HOLDING], selection)
    if missing:
        return {**report, "reason": "missing_holding_selection_prices", "missing_selection_dates": missing}
    if len(selection) < 2:
        return {**report, "status": "insufficient_sample", "reason": "too_few_selection_sessions"}

    holding = exact_returns(closes[HOLDING], selection)
    threshold = downside_threshold(holding)
    report["downside_threshold"] = float(threshold)
    report["selection_downside_days"] = len(downside_indices(holding, threshold))
    by_weight = {}
    for weight in WEIGHTS:
        share = Fraction(weight, 100)
        cash = [(1 - share) * change for change in holding]
        by_weight[weight] = (cash, path_performance(cash))

    options = []
    complete_count = 0
    for symbol in candidates:
        prices = closes[symbol]
        entry = {"exclusion_reason": None, "allocations": {}}
        report["candidates"][symbol] = entry
        missing = missing_dates(prices, selection)
        if missing:
            entry["exclusion_reason"] = (
                "no_selection_prices" if first_days[symbol] is None else "missing_selection_prices"
            )
            entry["missing_selection_dates"] = missing
            continue
        complete_count += 1
        if prices[selection[-1]] < prices[selection[0]]:
            entry["exclusion_reason"] = "negative_selection_return"
            continue

        candidate = exact_returns(prices, selection)
        for weight, (cash, cash_performance) in by_weight.items():
            mixed = combine_returns(cash, candidate, weight)
            performance = path_performance(mixed)
            return_delta = performance[0] - cash_performance[0]
            drawdown_reduction = cash_performance[1] - performance[1]
            entry["allocations"][str(weight)] = comparison(performance, cash_performance)
            if return_delta >= 0 and drawdown_reduction > 0:
                options.append((-drawdown_reduction, -performance[0], weight, symbol))
        if not any(item["target_met"] for item in entry["allocations"].values()):
            entry["exclusion_reason"] = "target_unmet_at_all_weights"

    if not complete_count:
        return {**report, "reason": "no_candidates_with_complete_selection_prices"}
    if options:
        _, _, weight, symbol = min(options)
        report["selected"] = {
            "symbol": symbol,
            "weight_percent": weight,
            **report["candidates"][symbol]["allocations"][str(weight)],
        }
    return evaluate_validation(report, closes, [selection[-1], *validation], threshold)


def combine_returns(cash, candidate, weight):
    share = Fraction(weight, 100)
    return [core + share * change for core, change in zip(cash, candidate)]


def path_performance(returns):
    value = Fraction(1)
    relative_to_peak = Fraction(1)
    drawdown = Fraction(0)
    for change in returns:
        factor = 1 + change
        value *= factor
        relative_to_peak = min(Fraction(1), relative_to_peak * factor)
        drawdown = max(drawdown, 1 - relative_to_peak)
    return value - 1, drawdown


def comparison(performance, cash_performance):
    cumulative_return, drawdown = performance
    return_delta = cumulative_return - cash_performance[0]
    drawdown_reduction = cash_performance[1] - drawdown
    return {
        "cumulative_return": float(cumulative_return),
        "maximum_drawdown": float(drawdown),
        "cash_cumulative_return": float(cash_performance[0]),
        "cash_maximum_drawdown": float(cash_performance[1]),
        "excess_cumulative_return_over_cash_pp": float(100 * return_delta),
        "maximum_drawdown_reduction_vs_cash_pp": float(100 * drawdown_reduction),
        "target_met": return_delta >= 0 and drawdown_reduction > 0,
    }


def validation_metrics(returns, performance, downside):
    mean = average_on(returns, downside)
    return {
        "cumulative_return": float(performance[0]),
        "maximum_drawdown": float(performance[1]),
        "downside_mean_return": None if mean is None else float(mean),
        "downside_worst_return": min((float(returns[index]) for index in downside), default=None),
    }


def evaluate_validation(report, closes, days, threshold):
    selected = report["selected"]
    symbols = (HOLDING,) if selected is None else (HOLDING, selected["symbol"])
    missing = {symbol: gaps for symbol in symbols if (gaps := missing_dates(closes[symbol], days))}
    if missing:
        return {**report, "reason": "missing_validation_prices", "missing_validation_dates": missing}

    holding = exact_returns(closes[HOLDING], days)
    downside = downside_indices(holding, threshold)
    report["validation_downside_days"] = len(downside)
    report["validation_downside_sample_sufficient"] = len(downside) >= MIN_DOWNSIDE_DAYS
    allocations = {"holding_only": validation_metrics(holding, path_performance(holding), downside)}
    report["allocations"] = allocations
    if selected is None:
        return {**report, "status": "no_suitable_candidate", "reason": "no_candidate_met_selection_target"}

    weight = selected["weight_percent"]
    cash = [(1 - Fraction(weight, 100)) * change for change in holding]
    candidate = exact_returns(closes[selected["symbol"]], days)
    mixed = combine_returns(cash, candidate, weight)
    cash_performance, mixed_performance = path_performance(cash), path_performance(mixed)
    allocations["with_cash"] = validation_metrics(cash, cash_performance, downside)
    allocations["with_etf"] = validation_metrics(mixed, mixed_performance, downside)
    delta = comparison(mixed_performance, cash_performance)
    for key in ("excess_cumulative_return_over_cash_pp", "maximum_drawdown_reduction_vs_cash_pp"):
        allocations["with_etf"][key] = delta[key]
    return {**report, "status": "evaluated", "validation_target_met": delta["target_met"]}
