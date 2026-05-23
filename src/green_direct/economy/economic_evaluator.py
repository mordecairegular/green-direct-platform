"""V1 annual economic evaluation.

The evaluator reads technical summary fields and builds an annual cash-flow
table. It does not mutate or recompute technical dispatch results.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import math
from typing import Any, Mapping

import pandas as pd

from green_direct.economy.economic_inputs import EconomicParams, OtherOperatingRevenueItem


@dataclass
class EconomicResult:
    """Economic result for one scenario."""

    scenario_id: str
    annual_cashflow: pd.DataFrame
    metrics: dict[str, Any]


def split_amount_with_vat(
    amount_with_vat: float,
    vat_rate: float,
    *,
    deductible_or_taxable: bool = True,
) -> tuple[float, float]:
    """Return (amount_without_vat, vat_amount) in the same unit as input."""

    amount = float(amount_with_vat)
    rate = float(vat_rate)
    if not deductible_or_taxable or rate <= 0:
        return amount, 0.0
    amount_without_vat = amount / (1 + rate)
    return amount_without_vat, amount - amount_without_vat


def _value(summary: Mapping[str, Any], key: str, default: float = 0.0) -> float:
    value = summary.get(key, default)
    if value is None or pd.isna(value):
        return default
    return float(value)


def _scenario_id(summary: Mapping[str, Any]) -> str:
    value = summary.get("scenario_id", "")
    return "" if value is None else str(value)


def _other_revenue_for_year(
    items: tuple[OtherOperatingRevenueItem, ...],
    operation_year: int,
) -> tuple[float, float, float]:
    revenue_with_vat = 0.0
    revenue_without_vat = 0.0
    output_vat = 0.0
    for item in items:
        if not item.is_active(operation_year):
            continue
        amount = float(item.amount_with_vat)
        revenue_with_vat += amount
        if amount > 0:
            without_vat, vat = split_amount_with_vat(amount, item.vat_rate, deductible_or_taxable=True)
        else:
            without_vat, vat = amount, 0.0
        revenue_without_vat += without_vat
        output_vat += vat
    return revenue_with_vat, revenue_without_vat, output_vat


def _replacement_cycle_interval_years(summary: Mapping[str, Any], params: EconomicParams) -> float:
    replacement_year = _value(summary, "replacement_year", math.inf)
    if math.isfinite(replacement_year) and replacement_year > 0:
        return replacement_year
    cycles = _value(summary, "annual_equivalent_cycles")
    return params.bess_cycle_life / cycles if cycles > 0 else math.inf


def _replacement_operation_years(summary: Mapping[str, Any], params: EconomicParams) -> tuple[int, ...]:
    bess_energy = _value(summary, "bess_energy")
    if bess_energy <= 0:
        return ()

    cycle_interval = _replacement_cycle_interval_years(summary, params)
    calendar_interval = float(params.bess_calendar_life_years)
    if not math.isfinite(calendar_interval) or calendar_interval <= 0:
        calendar_interval = math.inf
    replacement_interval = min(cycle_interval, calendar_interval)
    if not math.isfinite(replacement_interval) or replacement_interval <= 0:
        return ()

    replacement_years: list[int] = []
    due_year = replacement_interval
    guard = 0
    while due_year < params.operation_years and guard < params.operation_years * 2 + 10:
        operation_year = int(math.ceil(due_year))
        if 1 <= operation_year < params.operation_years and operation_year not in replacement_years:
            replacement_years.append(operation_year)
        due_year += replacement_interval
        guard += 1
    return tuple(replacement_years)


def _replacement_depreciation_for_year(
    *,
    replacement_years: tuple[int, ...],
    replacement_depreciation_basis: float,
    operation_year: int,
    operation_years: int,
) -> float:
    depreciation = 0.0
    for replacement_year in replacement_years:
        if operation_year <= replacement_year:
            continue
        depreciation_years = operation_years - replacement_year
        if depreciation_years > 0:
            depreciation += replacement_depreciation_basis / depreciation_years
    return depreciation


def _calculate_payback(years: list[int], cashflows: list[float]) -> float | None:
    cumulative = 0.0
    previous_year = years[0]
    previous_cumulative = cashflows[0]
    if previous_cumulative >= 0:
        return float(previous_year)
    cumulative = previous_cumulative
    for year, cashflow in zip(years[1:], cashflows[1:]):
        cumulative += cashflow
        if previous_cumulative < 0 <= cumulative and cashflow > 0:
            return previous_year + abs(previous_cumulative) / cashflow
        previous_year = year
        previous_cumulative = cumulative
    return None


def _npv(cashflows: list[float], rate: float) -> float:
    return sum(value / ((1 + rate) ** index) for index, value in enumerate(cashflows))


def _linear_rates(start: float, end: float, count: int) -> list[float]:
    if count <= 1:
        return [start]
    step = (end - start) / (count - 1)
    return [start + step * index for index in range(count)]


@lru_cache(maxsize=1)
def _irr_candidate_rates() -> tuple[float, ...]:
    base_rates = [
        -0.9999,
        -0.99,
        -0.95,
        -0.90,
        -0.75,
        -0.50,
        -0.25,
        -0.10,
        0.0,
        0.03,
        0.06,
        0.10,
        0.15,
        0.20,
        0.30,
        0.50,
        0.75,
        1.0,
        1.5,
        2.0,
        3.0,
        5.0,
        10.0,
    ]
    rates = set(base_rates)
    rates.update(_linear_rates(-0.9999, -0.90, 101))
    rates.update(_linear_rates(-0.90, 0.0, 181))
    rates.update(_linear_rates(0.0, 1.0, 1001))
    rates.update(_linear_rates(1.0, 10.0, 901))
    return tuple(sorted(rates))


def _bisect_irr_root(cashflows: list[float], low: float, high: float) -> float | None:
    low_value = _npv(cashflows, low)
    high_value = _npv(cashflows, high)
    if not math.isfinite(low_value) or not math.isfinite(high_value):
        return None
    if abs(low_value) < 1e-8:
        return low
    if abs(high_value) < 1e-8:
        return high
    if low_value * high_value > 0:
        return None

    for _ in range(200):
        mid = (low + high) / 2
        mid_value = _npv(cashflows, mid)
        if not math.isfinite(mid_value):
            return None
        if abs(mid_value) < 1e-8 or abs(high - low) < 1e-10:
            return mid
        if low_value * mid_value <= 0:
            high = mid
            high_value = mid_value
        else:
            low = mid
            low_value = mid_value
    return None


def _deduplicate_roots(roots: list[float]) -> list[float]:
    unique: list[float] = []
    for root in sorted(roots):
        if not unique or abs(root - unique[-1]) > 1e-7:
            unique.append(root)
    return unique


def _calculate_irr(cashflows: list[float]) -> tuple[float | None, str]:
    nonzero = [value for value in cashflows if abs(value) > 1e-9]
    if not nonzero:
        return None, "IRR 无法可靠计算：现金流全为0。"
    if not any(value > 0 for value in nonzero):
        return None, "IRR 无法可靠计算：现金流全为非正值，项目没有形成正向净现金流。"
    if not any(value < 0 for value in nonzero):
        return None, "IRR 无法可靠计算：现金流全为非负值，项目缺少初始投资流出。"

    roots: list[float] = []
    previous: tuple[float, float] | None = None
    for rate in _irr_candidate_rates():
        try:
            value = _npv(cashflows, rate)
        except (OverflowError, ZeroDivisionError):
            previous = None
            continue
        if not math.isfinite(value):
            previous = None
            continue
        if abs(value) < 1e-7:
            roots.append(rate)
        if previous is not None:
            previous_rate, previous_value = previous
            if previous_value * value < 0:
                root = _bisect_irr_root(cashflows, previous_rate, rate)
                if root is not None:
                    roots.append(root)
        previous = (rate, value)

    unique_roots = _deduplicate_roots(roots)
    if len(unique_roots) == 1:
        return unique_roots[0], "ok"
    if not unique_roots:
        return None, "IRR 无法可靠计算：未找到稳定求解区间。"
    return None, "IRR 无法可靠计算：现金流存在多个IRR解。"


def evaluate_scenario_economy(
    summary: Mapping[str, Any] | pd.Series,
    params: EconomicParams | None = None,
) -> EconomicResult:
    """Evaluate V1 annual project cash flow for one technical scenario."""

    economic_params = params or EconomicParams()
    summary_map: Mapping[str, Any] = summary.to_dict() if isinstance(summary, pd.Series) else summary
    scenario_id = _scenario_id(summary_map)

    wind_capacity = _value(summary_map, "wind_capacity")
    pv_capacity = _value(summary_map, "pv_capacity")
    bess_power = _value(summary_map, "bess_power")
    bess_energy = _value(summary_map, "bess_energy")
    grid_export_energy = _value(summary_map, "grid_export_energy")
    self_use_energy = _value(summary_map, "self_use_energy")

    wind_capex_with_vat = wind_capacity * economic_params.wind_capex_per_kw_with_vat
    pv_capex_with_vat = pv_capacity * economic_params.pv_capex_per_kw_with_vat
    bess_capex_with_vat = bess_energy * economic_params.bess_capex_per_kwh_with_vat
    dedicated_connection_line_with_vat = economic_params.dedicated_connection_line_investment_with_vat
    other_fixed_asset_with_vat = economic_params.other_fixed_asset_investment_with_vat
    construction_cash_outflow = (
        wind_capex_with_vat
        + pv_capex_with_vat
        + bess_capex_with_vat
        + dedicated_connection_line_with_vat
        + other_fixed_asset_with_vat
    )

    wind_depreciation_basis, wind_input_vat = split_amount_with_vat(
        wind_capex_with_vat,
        economic_params.construction_input_vat_rate,
        deductible_or_taxable=economic_params.construction_input_vat_deductible,
    )
    pv_depreciation_basis, pv_input_vat = split_amount_with_vat(
        pv_capex_with_vat,
        economic_params.construction_input_vat_rate,
        deductible_or_taxable=economic_params.construction_input_vat_deductible,
    )
    bess_depreciation_basis, bess_input_vat = split_amount_with_vat(
        bess_capex_with_vat,
        economic_params.construction_input_vat_rate,
        deductible_or_taxable=economic_params.construction_input_vat_deductible,
    )
    dedicated_connection_line_depreciation_basis, dedicated_connection_line_input_vat = split_amount_with_vat(
        dedicated_connection_line_with_vat,
        economic_params.construction_input_vat_rate,
        deductible_or_taxable=economic_params.construction_input_vat_deductible,
    )
    other_depreciation_basis, other_input_vat = split_amount_with_vat(
        other_fixed_asset_with_vat,
        economic_params.construction_input_vat_rate,
        deductible_or_taxable=economic_params.construction_input_vat_deductible,
    )
    construction_input_vat = (
        wind_input_vat + pv_input_vat + bess_input_vat + dedicated_connection_line_input_vat + other_input_vat
    )

    replacement_years = _replacement_operation_years(summary_map, economic_params)
    first_replacement_year = replacement_years[0] if replacement_years else None
    bess_replacement_cash_outflow = bess_capex_with_vat * economic_params.bess_replacement_cost_ratio
    bess_replacement_depreciation_basis, _ = split_amount_with_vat(
        bess_replacement_cash_outflow,
        economic_params.bess_replacement_input_vat_rate,
        deductible_or_taxable=economic_params.bess_replacement_input_vat_deductible,
    )

    rows: list[dict[str, Any]] = []
    vat_credit_begin = 0.0
    loss_buckets: list[tuple[int, float]] = []

    def append_row(row: dict[str, Any]) -> None:
        rows.append({"scenario_id": scenario_id, **row})

    append_row(
        {
            "year": 0,
            "operation_year": 0,
            "period_type": "construction",
            "grid_export_energy": 0.0,
            "self_use_energy": 0.0,
            "grid_export_revenue_with_vat": 0.0,
            "self_use_revenue_with_vat": 0.0,
            "other_operating_revenue_with_vat": 0.0,
            "operating_revenue_with_vat": 0.0,
            "operating_revenue_without_vat": 0.0,
            "output_vat": 0.0,
            "wind_om_cost_with_vat": 0.0,
            "pv_om_cost_with_vat": 0.0,
            "bess_om_cost_with_vat": 0.0,
            "other_operating_cost_with_vat": 0.0,
            "operating_cost_with_vat": 0.0,
            "operating_cost_without_vat": 0.0,
            "construction_input_vat": construction_input_vat,
            "bess_replacement_input_vat": 0.0,
            "input_vat": construction_input_vat,
            "vat_credit_begin": 0.0,
            "vat_payable": 0.0,
            "vat_credit_end": construction_input_vat,
            "urban_maintenance_tax": 0.0,
            "education_surcharge": 0.0,
            "local_education_surcharge": 0.0,
            "taxes_and_surcharges": 0.0,
            "wind_depreciation": 0.0,
            "pv_depreciation": 0.0,
            "bess_depreciation": 0.0,
            "bess_replacement_depreciation": 0.0,
            "dedicated_connection_line_depreciation": 0.0,
            "other_fixed_asset_depreciation": 0.0,
            "depreciation": 0.0,
            "profit_before_tax": 0.0,
            "loss_offset": 0.0,
            "taxable_income": 0.0,
            "income_tax": 0.0,
            "net_profit": 0.0,
            "construction_cash_outflow": construction_cash_outflow,
            "bess_replacement_cash_outflow": 0.0,
            "net_cash_flow": -construction_cash_outflow,
        }
    )
    vat_credit_begin = construction_input_vat

    for operation_year in range(1, economic_params.operation_years + 1):
        grid_export_revenue_with_vat = grid_export_energy * economic_params.grid_export_price_with_vat
        self_use_revenue_with_vat = self_use_energy * economic_params.self_use_price_with_vat
        grid_export_revenue_without_vat, grid_export_output_vat = split_amount_with_vat(
            grid_export_revenue_with_vat,
            economic_params.output_vat_rate,
        )
        self_use_revenue_without_vat, self_use_output_vat = split_amount_with_vat(
            self_use_revenue_with_vat,
            economic_params.output_vat_rate,
        )
        other_revenue_with_vat, other_revenue_without_vat, other_output_vat = _other_revenue_for_year(
            economic_params.other_operating_revenues,
            operation_year,
        )
        operating_revenue_with_vat = (
            grid_export_revenue_with_vat + self_use_revenue_with_vat + other_revenue_with_vat
        )
        operating_revenue_without_vat = (
            grid_export_revenue_without_vat + self_use_revenue_without_vat + other_revenue_without_vat
        )
        output_vat = grid_export_output_vat + self_use_output_vat + other_output_vat

        wind_om_cost_with_vat = wind_capacity * economic_params.wind_om_cost_per_kw_year
        pv_om_cost_with_vat = pv_capacity * economic_params.pv_om_cost_per_kw_year
        bess_om_cost_with_vat = bess_power * economic_params.bess_om_cost_per_kw_year
        other_operating_cost_with_vat = economic_params.other_operating_cost_with_vat
        operating_cost_with_vat = (
            wind_om_cost_with_vat
            + pv_om_cost_with_vat
            + bess_om_cost_with_vat
            + other_operating_cost_with_vat
        )
        operating_cost_without_vat = operating_cost_with_vat

        replacement_cash_outflow = (
            bess_replacement_cash_outflow if operation_year in replacement_years else 0.0
        )
        _, replacement_input_vat = split_amount_with_vat(
            replacement_cash_outflow,
            economic_params.bess_replacement_input_vat_rate,
            deductible_or_taxable=economic_params.bess_replacement_input_vat_deductible,
        )
        input_vat = replacement_input_vat
        available_vat_credit = vat_credit_begin + input_vat
        vat_payable = max(output_vat - available_vat_credit, 0.0)
        vat_credit_end = max(available_vat_credit - output_vat, 0.0)

        urban_maintenance_tax = vat_payable * economic_params.urban_maintenance_tax_rate
        education_surcharge = vat_payable * economic_params.education_surcharge_rate
        local_education_surcharge = vat_payable * economic_params.local_education_surcharge_rate
        taxes_and_surcharges = urban_maintenance_tax + education_surcharge + local_education_surcharge

        if operation_year <= 20:
            wind_depreciation = wind_depreciation_basis / 20
            pv_depreciation = pv_depreciation_basis / 20
            bess_depreciation = bess_depreciation_basis / 20
            dedicated_connection_line_depreciation = dedicated_connection_line_depreciation_basis / 20
            other_fixed_asset_depreciation = other_depreciation_basis / 20
        else:
            wind_depreciation = 0.0
            pv_depreciation = 0.0
            bess_depreciation = 0.0
            dedicated_connection_line_depreciation = 0.0
            other_fixed_asset_depreciation = 0.0
        bess_replacement_depreciation = _replacement_depreciation_for_year(
            replacement_years=replacement_years,
            replacement_depreciation_basis=bess_replacement_depreciation_basis,
            operation_year=operation_year,
            operation_years=economic_params.operation_years,
        )
        depreciation = (
            wind_depreciation
            + pv_depreciation
            + bess_depreciation
            + bess_replacement_depreciation
            + dedicated_connection_line_depreciation
            + other_fixed_asset_depreciation
        )

        profit_before_tax = operating_revenue_without_vat - operating_cost_without_vat - depreciation - taxes_and_surcharges
        loss_buckets = [
            (origin_year, amount)
            for origin_year, amount in loss_buckets
            if amount > 1e-9 and operation_year - origin_year <= economic_params.loss_carryforward_years
        ]
        loss_offset = 0.0
        if profit_before_tax > 0 and loss_buckets:
            remaining_profit = profit_before_tax
            updated_buckets: list[tuple[int, float]] = []
            for origin_year, amount in loss_buckets:
                used = min(amount, remaining_profit)
                loss_offset += used
                remaining_profit -= used
                remaining_amount = amount - used
                if remaining_amount > 1e-9:
                    updated_buckets.append((origin_year, remaining_amount))
            loss_buckets = updated_buckets
        taxable_income = max(profit_before_tax - loss_offset, 0.0)
        income_tax = taxable_income * economic_params.income_tax_rate
        net_profit = profit_before_tax - income_tax
        if profit_before_tax < 0:
            loss_buckets.append((operation_year, -profit_before_tax))

        net_cash_flow = (
            operating_revenue_with_vat
            - operating_cost_with_vat
            - replacement_cash_outflow
            - vat_payable
            - taxes_and_surcharges
            - income_tax
        )
        append_row(
            {
                "year": operation_year,
                "operation_year": operation_year,
                "period_type": "operation",
                "grid_export_energy": grid_export_energy,
                "self_use_energy": self_use_energy,
                "grid_export_revenue_with_vat": grid_export_revenue_with_vat,
                "self_use_revenue_with_vat": self_use_revenue_with_vat,
                "other_operating_revenue_with_vat": other_revenue_with_vat,
                "operating_revenue_with_vat": operating_revenue_with_vat,
                "operating_revenue_without_vat": operating_revenue_without_vat,
                "output_vat": output_vat,
                "wind_om_cost_with_vat": wind_om_cost_with_vat,
                "pv_om_cost_with_vat": pv_om_cost_with_vat,
                "bess_om_cost_with_vat": bess_om_cost_with_vat,
                "other_operating_cost_with_vat": other_operating_cost_with_vat,
                "operating_cost_with_vat": operating_cost_with_vat,
                "operating_cost_without_vat": operating_cost_without_vat,
                "construction_input_vat": 0.0,
                "bess_replacement_input_vat": replacement_input_vat,
                "input_vat": input_vat,
                "vat_credit_begin": vat_credit_begin,
                "vat_payable": vat_payable,
                "vat_credit_end": vat_credit_end,
                "urban_maintenance_tax": urban_maintenance_tax,
                "education_surcharge": education_surcharge,
                "local_education_surcharge": local_education_surcharge,
                "taxes_and_surcharges": taxes_and_surcharges,
                "wind_depreciation": wind_depreciation,
                "pv_depreciation": pv_depreciation,
                "bess_depreciation": bess_depreciation,
                "bess_replacement_depreciation": bess_replacement_depreciation,
                "dedicated_connection_line_depreciation": dedicated_connection_line_depreciation,
                "other_fixed_asset_depreciation": other_fixed_asset_depreciation,
                "depreciation": depreciation,
                "profit_before_tax": profit_before_tax,
                "loss_offset": loss_offset,
                "taxable_income": taxable_income,
                "income_tax": income_tax,
                "net_profit": net_profit,
                "construction_cash_outflow": 0.0,
                "bess_replacement_cash_outflow": replacement_cash_outflow,
                "net_cash_flow": net_cash_flow,
            }
        )
        vat_credit_begin = vat_credit_end

    annual = pd.DataFrame(rows)
    annual["cumulative_net_cash_flow"] = annual["net_cash_flow"].cumsum()
    annual["discount_factor"] = annual["year"].map(
        lambda year: 1 / ((1 + economic_params.discount_rate) ** int(year))
    )
    annual["discounted_net_cash_flow"] = annual["net_cash_flow"] * annual["discount_factor"]
    annual["cumulative_discounted_net_cash_flow"] = annual["discounted_net_cash_flow"].cumsum()

    years = annual["year"].astype(int).tolist()
    cashflows = annual["net_cash_flow"].astype(float).tolist()
    discounted_cashflows = annual["discounted_net_cash_flow"].astype(float).tolist()
    firr, firr_status = _calculate_irr(cashflows)
    metrics = {
        "scenario_id": scenario_id,
        "fnpv": float(annual["discounted_net_cash_flow"].sum()),
        "firr": firr,
        "firr_status": firr_status,
        "static_payback_year": _calculate_payback(years, cashflows),
        "dynamic_payback_year": _calculate_payback(years, discounted_cashflows),
        "construction_cash_outflow": construction_cash_outflow,
        "dedicated_connection_line_investment_with_vat": dedicated_connection_line_with_vat,
        "annual_operating_revenue_with_vat": float(
            annual.loc[annual["period_type"] == "operation", "operating_revenue_with_vat"].iloc[0]
        )
        if economic_params.operation_years > 0
        else 0.0,
        "annual_operating_cost_with_vat": float(
            annual.loc[annual["period_type"] == "operation", "operating_cost_with_vat"].iloc[0]
        )
        if economic_params.operation_years > 0
        else 0.0,
        "bess_replacement_operation_year": first_replacement_year,
        "bess_replacement_operation_years": ",".join(str(year) for year in replacement_years),
        "bess_replacement_count": len(replacement_years),
    }
    return EconomicResult(scenario_id=scenario_id, annual_cashflow=annual, metrics=metrics)


def evaluate_batch_economy(
    summary: pd.DataFrame,
    params: EconomicParams | None = None,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """Evaluate all rows in a technical summary table."""

    results: list[dict[str, Any]] = []
    annual_cashflows: dict[str, pd.DataFrame] = {}
    for _, row in summary.iterrows():
        result = evaluate_scenario_economy(row, params=params)
        results.append(result.metrics)
        annual_cashflows[result.scenario_id] = result.annual_cashflow
    return pd.DataFrame(results), annual_cashflows
