"""Evaluate the minimum defensive ETF weight at two historical cutoffs."""

from datetime import date
from fractions import Fraction

from .experiment import (
    HOLDING,
    MIN_DOWNSIDE_DAYS,
    average_on,
    comparison_metrics,
    downside_indices,
    downside_threshold,
    exact_returns,
    missing_dates,
)


WEIGHTS = (10, 15, 20)
TARGET_PP = Fraction(1, 10)
VALIDATION_YEARS = (2025, 2026)


def evaluate_weight_study(closes, calendar, candidates):
    windows = {}
    for year in VALIDATION_YEARS:
        selection = [day for day in calendar if day < date(year, 1, 1)]
        validation = [day for day in calendar if day.year == year]
        windows[str(year)] = evaluate_window(closes, selection, validation, candidates)
    return {
        "mode": "weight_study",
        "holding": HOLDING,
        "input_candidates": list(candidates),
        "candidate_weights_percent": list(WEIGHTS),
        "target_excess_over_cash_pp": float(TARGET_PP),
        "minimum_validation_downside_days": MIN_DOWNSIDE_DAYS,
        "cash_daily_return": 0,
        "trading_cost": 0,
        "rebalance": "daily",
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
        "downside_threshold": None,
        "selection_downside_days": None,
        "candidates": {},
        "selected": None,
        "validation_downside_days": None,
        "validation_sample_sufficient": None,
        "validation_target_met": None,
        "allocations": None,
    }
    if not selection or not validation:
        return {**report, "reason": "missing_selection_or_validation_sessions"}

    first_days = {}
    for symbol in (HOLDING, *candidates):
        first_days[symbol] = next((day for day in selection if day in closes[symbol]), None)
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
    downside = downside_indices(holding, threshold)
    report["downside_threshold"] = float(threshold)
    report["selection_downside_days"] = len(downside)
    if not downside:
        return {**report, "status": "insufficient_sample", "reason": "no_selection_downside_days"}

    scores, complete_count = score_candidates(
        closes, candidates, first_days, selection, downside, report["candidates"],
    )
    if not complete_count:
        return {**report, "reason": "no_candidates_with_complete_selection_prices"}

    options = [
        (weight, -score * weight, symbol)
        for symbol, score in scores.items()
        for weight in WEIGHTS
        if score * weight >= TARGET_PP
    ]
    symbol = None
    weight = 0
    if options:
        weight, negative_excess, symbol = min(options)
        report["selected"] = {
            "symbol": symbol,
            "weight_percent": weight,
            "selection_excess_over_cash_pp": float(-negative_excess),
        }
    return evaluate_fixed_allocation(report, closes, [selection[-1], *validation], threshold, symbol, weight)


def score_candidates(closes, candidates, first_days, selection, downside, details):
    scores = {}
    complete_count = 0
    for symbol in candidates:
        prices = closes[symbol]
        missing = missing_dates(prices, selection)
        entry = {"exclusion_reason": None, "selection_downside_mean_return": None}
        details[symbol] = entry
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
        score = average_on(exact_returns(prices, selection), downside)
        scores[symbol] = score
        entry["selection_downside_mean_return"] = float(score)
        if score * max(WEIGHTS) < TARGET_PP:
            entry["exclusion_reason"] = "target_unmet_at_all_weights"
    return scores, complete_count


def evaluate_fixed_allocation(report, closes, days, threshold, symbol, weight):
    symbols = (HOLDING, symbol) if symbol is not None else (HOLDING,)
    missing = {ticker: gaps for ticker in symbols if (gaps := missing_dates(closes[ticker], days))}
    if missing:
        return {**report, "reason": "missing_validation_prices", "missing_validation_dates": missing}

    holding = exact_returns(closes[HOLDING], days)
    downside = downside_indices(holding, threshold)
    upside = [index for index, change in enumerate(holding) if change > 0]
    report["validation_downside_days"] = len(downside)
    report["validation_sample_sufficient"] = len(downside) >= MIN_DOWNSIDE_DAYS
    allocations = {"holding_only": comparison_metrics(holding, None, downside, upside)}
    report["allocations"] = allocations
    if symbol is None:
        return {**report, "status": "no_suitable_candidate", "reason": "no_candidate_met_selection_target"}

    etf_weight = Fraction(weight, 100)
    cash = [(1 - etf_weight) * change for change in holding]
    etf = exact_returns(closes[symbol], days)
    mixed = [core + etf_weight * change for core, change in zip(cash, etf)]
    allocations["with_cash"] = comparison_metrics(cash, cash, downside, upside)
    allocations["with_etf"] = comparison_metrics(mixed, cash, downside, upside)
    if not report["validation_sample_sufficient"]:
        return {**report, "status": "insufficient_sample", "reason": "too_few_validation_downside_days"}

    report["validation_target_met"] = average_on(etf, downside) * weight >= TARGET_PP
    return {**report, "status": "evaluated"}
