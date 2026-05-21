"""V1 annual economic evaluation.

The evaluator reads technical summary fields and builds an annual cash-flow
table. It does not mutate or recompute technical dispatch results.
"""

from __future__ import annotations

from dataclasses import dataclass
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


def _replacement_operation_year(summary: Mapping[str, Any], params: EconomicParams) -> int | None:
    bess_energy = _value(summary, "bess_energy")
    if bess_energy <= 0:
        return None
    replacement_year = _value(summary, "replacement_year", math.inf)
    if not math.isfinite(replacement_year) or replacement_year <= 0:
        cycles = _value(summary, "annual_equivalent_cycles")
        replacement_year = params.bess_cycle_life / cycles if cycles > 0 else math.inf
    if not math.isfinite(replacement_year) or replacement_year <= 0:
        return None
    operation_year = int(math.ceil(replacement_year))
    if 1 <= operation_year < params.operation_years:
        return operation_year
    return None


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


def _calculate_irr(cashflows: list[float]) -> tuple[float | None, str]:
    nonzero = [value for value in cashflows if abs(value) > 1e-9]
    if not nonzero or not any(value < 0 for value in nonzero) or not any(value > 0 for value in nonzero):
        return None, "IRR 无法可靠计算：现金流缺少有效正负变号。"
    signs = [1 if value > 0 else -1 for value in nonzero]
    sign_changes = sum(1 for left, right in zip(signs, signs[1:]) if left != right)
    if sign_changes != 1:
        return None, "IRR 无法可靠计算：现金流存在多次变号或变号结构不稳定。"

    candidates = [
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
    values = [(rate, _npv(cashflows, rate)) for rate in candidates]
    for rate, value in values:
        if abs(value) < 1e-7:
            return rate, "ok"
    bracket: tuple[float, float] | None = None
    for (left_rate, left_value), (right_rate, right_value) in zip(values, values[1:]):
        if left_value * right_value < 0:
            bracket = (left_rate, right_rate)
            break
    if bracket is None:
        return None, "IRR 无法可靠计算：未找到稳定求解区间。"

    low, high = bracket
    low_value = _npv(cashflows, low)
    for _ in range(200):
        mid = (low + high) / 2
        mid_value = _npv(cashflows, mid)
        if abs(mid_value) < 1e-8 or abs(high - low) < 1e-10:
            return mid, "ok"
        if low_value * mid_value <= 0:
            high = mid
        else:
            low = mid
            low_value = mid_value
    return None, "IRR 无法可靠计算：数值迭代未收敛。"


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
    other_fixed_asset_with_vat = economic_params.other_fixed_asset_investment_with_vat
    construction_cash_outflow = (
        wind_capex_with_vat + pv_capex_with_vat + bess_capex_with_vat + other_fixed_asset_with_vat
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
    other_depreciation_basis, other_input_vat = split_amount_with_vat(
        other_fixed_asset_with_vat,
        economic_params.construction_input_vat_rate,
        deductible_or_taxable=economic_params.construction_input_vat_deductible,
    )
    construction_input_vat = wind_input_vat + pv_input_vat + bess_input_vat + other_input_vat

    replacement_year = _replacement_operation_year(summary_map, economic_params)
    bess_replacement_cash_outflow = bess_capex_with_vat * economic_params.bess_replacement_cost_ratio

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

        replacement_cash_outflow = bess_replacement_cash_outflow if operation_year == replacement_year else 0.0
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
            other_fixed_asset_depreciation = other_depreciation_basis / 20
        else:
            wind_depreciation = 0.0
            pv_depreciation = 0.0
            bess_depreciation = 0.0
            other_fixed_asset_depreciation = 0.0
        depreciation = wind_depreciation + pv_depreciation + bess_depreciation + other_fixed_asset_depreciation

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
        "bess_replacement_operation_year": replacement_year,
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
