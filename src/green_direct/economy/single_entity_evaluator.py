"""Single-entity pre-tax incremental economic evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Iterable, Mapping

import pandas as pd

from green_direct.economy.economic_evaluator import (
    EconomicResult,
    _EMPTY_ANNUAL_CASHFLOW,
    _calculate_irr,
    _calculate_payback,
    _discount_factors,
    _other_revenue_schedule,
    _override_value,
    _replacement_operation_years,
    _scenario_id,
    _summary_records,
    _value,
    split_amount_with_vat,
)
from green_direct.economy.economic_inputs import AvoidedGridPurchaseParams, EconomicParams
from green_direct.economy.electricity_saving import (
    calc_avoided_grid_purchase_cash_price,
    calc_environmental_value,
    calc_export_revenue_without_vat,
    calc_net_avoided_grid_cost_price,
    calc_self_use_saving,
    validate_avoided_grid_purchase_params,
)


def _investment_basis(amount_with_vat: float, params: EconomicParams) -> float:
    basis, _ = split_amount_with_vat(
        amount_with_vat,
        params.construction_input_vat_rate,
        deductible_or_taxable=params.construction_input_vat_deductible,
    )
    return basis


def _bess_replacement_basis(amount_with_vat: float, params: EconomicParams) -> float:
    basis, _ = split_amount_with_vat(
        amount_with_vat,
        params.bess_replacement_input_vat_rate,
        deductible_or_taxable=params.bess_replacement_input_vat_deductible,
    )
    return basis


@dataclass(frozen=True)
class _SingleEntityEconomyContext:
    """Precomputed values shared by every scenario in one single-entity run."""

    operation_year_range: tuple[int, ...]
    discount_factors: tuple[float, ...]
    other_revenue_by_year: tuple[tuple[float, float, float], ...]
    line_capex_with_vat: float
    other_capex_with_vat: float
    line_investment_basis: float
    other_investment_basis: float
    net_avoided_grid_cost_price: float
    avoided_grid_purchase_cash_price: float


@lru_cache(maxsize=64)
def _single_entity_economy_context(
    economic_params: EconomicParams,
    avoided_grid_params: AvoidedGridPurchaseParams,
) -> _SingleEntityEconomyContext:
    operation_years = int(economic_params.operation_years)
    return _SingleEntityEconomyContext(
        operation_year_range=tuple(range(1, operation_years + 1)),
        discount_factors=_discount_factors(operation_years, float(economic_params.discount_rate)),
        other_revenue_by_year=_other_revenue_schedule(
            economic_params.other_operating_revenues,
            operation_years,
        ),
        line_capex_with_vat=economic_params.dedicated_connection_line_investment_with_vat,
        other_capex_with_vat=economic_params.other_fixed_asset_investment_with_vat,
        line_investment_basis=_investment_basis(
            economic_params.dedicated_connection_line_investment_with_vat,
            economic_params,
        ),
        other_investment_basis=_investment_basis(
            economic_params.other_fixed_asset_investment_with_vat,
            economic_params,
        ),
        net_avoided_grid_cost_price=calc_net_avoided_grid_cost_price(avoided_grid_params),
        avoided_grid_purchase_cash_price=calc_avoided_grid_purchase_cash_price(avoided_grid_params),
    )


def evaluate_single_entity_pre_tax_economy(
    summary: Mapping[str, Any] | pd.Series,
    avoided_grid_params: AvoidedGridPurchaseParams,
    params: EconomicParams | None = None,
    *,
    validate_params: bool = True,
    retain_annual_cashflow: bool = True,
    _context: _SingleEntityEconomyContext | None = None,
    _empty_annual_cashflow: pd.DataFrame | None = None,
) -> EconomicResult:
    """Evaluate same-investor incremental pre-tax cash flow for one scenario.

    This perspective is intentionally separate from the power-side evaluator.
    It treats self-use energy as avoided external grid-purchase cost, not as
    internal green-power settlement revenue.
    """

    if validate_params:
        validate_avoided_grid_purchase_params(avoided_grid_params)
    economic_params = params or EconomicParams()
    context = _context or _single_entity_economy_context(economic_params, avoided_grid_params)
    summary_map: Mapping[str, Any] = summary.to_dict() if isinstance(summary, pd.Series) else summary
    scenario_id = _scenario_id(summary_map)

    wind_capacity = _value(summary_map, "wind_capacity")
    pv_capacity = _value(summary_map, "pv_capacity")
    bess_power = _value(summary_map, "bess_power")
    bess_energy = _value(summary_map, "bess_energy")
    grid_export_energy = _value(summary_map, "grid_export_energy")
    self_use_energy = _value(summary_map, "self_use_energy")
    if self_use_energy < 0:
        raise ValueError("self_use_energy must be non-negative.")
    if grid_export_energy < 0:
        raise ValueError("grid_export_energy must be non-negative.")

    wind_capex_with_vat = wind_capacity * economic_params.wind_capex_per_kw_with_vat
    pv_capex_with_vat = pv_capacity * economic_params.pv_capex_per_kw_with_vat
    bess_capex_with_vat = bess_energy * economic_params.bess_capex_per_kwh_with_vat
    line_capex_with_vat = context.line_capex_with_vat
    other_capex_with_vat = context.other_capex_with_vat
    construction_cash_outflow_with_vat = (
        wind_capex_with_vat
        + pv_capex_with_vat
        + bess_capex_with_vat
        + line_capex_with_vat
        + other_capex_with_vat
    )
    initial_investment_basis = (
        _investment_basis(wind_capex_with_vat, economic_params)
        + _investment_basis(pv_capex_with_vat, economic_params)
        + _investment_basis(bess_capex_with_vat, economic_params)
        + context.line_investment_basis
        + context.other_investment_basis
    )

    wind_om_cost = wind_capacity * economic_params.wind_om_cost_per_kw_year
    pv_om_cost = pv_capacity * economic_params.pv_om_cost_per_kw_year
    bess_om_cost = bess_power * economic_params.bess_om_cost_per_kw_year
    operating_cost_basis = (
        wind_om_cost + pv_om_cost + bess_om_cost + economic_params.other_operating_cost_with_vat
    )

    net_avoided_grid_cost_price = _override_value(
        summary_map,
        "net_avoided_grid_cost_price_effective",
        context.net_avoided_grid_cost_price,
    )
    avoided_grid_purchase_cash_price = _override_value(
        summary_map,
        "avoided_grid_purchase_cash_price_effective",
        context.avoided_grid_purchase_cash_price,
    )
    self_use_saving = _override_value(
        summary_map,
        "self_use_saving_override",
        calc_self_use_saving(self_use_energy, avoided_grid_params),
    )
    avoided_grid_purchase_cash_saving = _override_value(
        summary_map,
        "avoided_grid_purchase_cash_saving_override",
        self_use_energy * avoided_grid_purchase_cash_price,
    )
    environmental_value = _override_value(
        summary_map,
        "environmental_value_override",
        calc_environmental_value(self_use_energy, avoided_grid_params),
    )
    grid_export_revenue_without_vat = _override_value(
        summary_map,
        "grid_export_revenue_without_vat_override",
        calc_export_revenue_without_vat(
            grid_export_energy,
            economic_params.grid_export_price_with_vat,
            economic_params.output_vat_rate,
        ),
    )

    replacement_years = _replacement_operation_years(summary_map, economic_params)
    replacement_year_set = set(replacement_years)
    first_replacement_year = replacement_years[0] if replacement_years else None
    bess_replacement_cash_outflow_with_vat = (
        bess_capex_with_vat * economic_params.bess_replacement_cost_ratio
    )
    bess_replacement_basis = _bess_replacement_basis(
        bess_replacement_cash_outflow_with_vat,
        economic_params,
    )
    other_revenue_by_year = context.other_revenue_by_year

    rows: list[dict[str, Any]] | None = [] if retain_annual_cashflow else None
    years: list[int] = []
    cashflows: list[float] = []

    def append_cashflow(year: int, net_cash_flow: float) -> None:
        years.append(int(year))
        cashflows.append(float(net_cash_flow))

    def append_row(row: dict[str, Any]) -> None:
        append_cashflow(int(row["year"]), float(row["net_cash_flow"]))
        if rows is not None:
            rows.append({"scenario_id": scenario_id, **row})

    if rows is not None:
        append_row(
            {
                "year": 0,
                "operation_year": 0,
                "period_type": "construction",
                "self_use_energy": 0.0,
                "grid_export_energy": 0.0,
                "net_avoided_grid_cost_price": net_avoided_grid_cost_price,
                "avoided_grid_purchase_cash_price": avoided_grid_purchase_cash_price,
                "self_use_saving": 0.0,
                "avoided_grid_purchase_cash_saving": 0.0,
                "environmental_value": 0.0,
                "grid_export_revenue_without_vat": 0.0,
                "other_external_revenue_without_vat": 0.0,
                "operating_cost_basis": 0.0,
                "bess_replacement_basis": 0.0,
                "bess_replacement_cash_outflow_with_vat": 0.0,
                "initial_investment_basis": initial_investment_basis,
                "construction_cash_outflow_with_vat": construction_cash_outflow_with_vat,
                "pre_tax_net_cash_flow": -initial_investment_basis,
                "net_cash_flow": -initial_investment_basis,
            }
        )
    else:
        append_cashflow(0, -initial_investment_basis)

    for operation_year in context.operation_year_range:
        _, other_revenue_without_vat, _ = other_revenue_by_year[operation_year]
        replacement_basis = bess_replacement_basis if operation_year in replacement_year_set else 0.0
        replacement_cash_outflow = (
            bess_replacement_cash_outflow_with_vat if operation_year in replacement_year_set else 0.0
        )
        pre_tax_net_cash_flow = (
            self_use_saving
            + environmental_value
            + grid_export_revenue_without_vat
            + other_revenue_without_vat
            - operating_cost_basis
            - replacement_basis
        )
        if rows is not None:
            append_row(
                {
                    "year": operation_year,
                    "operation_year": operation_year,
                    "period_type": "operation",
                    "self_use_energy": self_use_energy,
                    "grid_export_energy": grid_export_energy,
                    "net_avoided_grid_cost_price": net_avoided_grid_cost_price,
                    "avoided_grid_purchase_cash_price": avoided_grid_purchase_cash_price,
                    "self_use_saving": self_use_saving,
                    "avoided_grid_purchase_cash_saving": avoided_grid_purchase_cash_saving,
                    "environmental_value": environmental_value,
                    "grid_export_revenue_without_vat": grid_export_revenue_without_vat,
                    "other_external_revenue_without_vat": other_revenue_without_vat,
                    "operating_cost_basis": operating_cost_basis,
                    "bess_replacement_basis": replacement_basis,
                    "bess_replacement_cash_outflow_with_vat": replacement_cash_outflow,
                    "initial_investment_basis": 0.0,
                    "construction_cash_outflow_with_vat": 0.0,
                    "pre_tax_net_cash_flow": pre_tax_net_cash_flow,
                    "net_cash_flow": pre_tax_net_cash_flow,
                }
            )
        else:
            append_cashflow(operation_year, pre_tax_net_cash_flow)

    discount_factors = context.discount_factors
    discounted_cashflows = [
        cashflow * discount_factors[year]
        for year, cashflow in zip(years, cashflows)
    ]
    if rows is not None:
        annual = pd.DataFrame(rows)
        annual["cumulative_net_cash_flow"] = annual["net_cash_flow"].cumsum()
        annual["discount_factor"] = [discount_factors[year] for year in years]
        annual["discounted_net_cash_flow"] = annual["net_cash_flow"] * annual["discount_factor"]
        annual["cumulative_discounted_net_cash_flow"] = annual["discounted_net_cash_flow"].cumsum()
    else:
        annual = _empty_annual_cashflow if _empty_annual_cashflow is not None else pd.DataFrame()

    firr, firr_status = _calculate_irr(cashflows)
    metrics = {
        "scenario_id": scenario_id,
        "perspective": "single_entity_pre_tax",
        "single_entity_fnpv_pre_tax": float(sum(discounted_cashflows)),
        "single_entity_firr_pre_tax": firr,
        "single_entity_firr_status": firr_status,
        "single_entity_static_payback_year": _calculate_payback(years, cashflows),
        "single_entity_dynamic_payback_year": _calculate_payback(years, discounted_cashflows),
        "initial_investment_basis": initial_investment_basis,
        "construction_cash_outflow_with_vat": construction_cash_outflow_with_vat,
        "annual_self_use_saving": self_use_saving,
        "annual_avoided_grid_purchase_cash_saving": avoided_grid_purchase_cash_saving,
        "annual_environmental_value": environmental_value,
        "annual_grid_export_revenue_without_vat": grid_export_revenue_without_vat,
        "annual_operating_cost_basis": operating_cost_basis,
        "net_avoided_grid_cost_price": net_avoided_grid_cost_price,
        "avoided_grid_purchase_cash_price": avoided_grid_purchase_cash_price,
        "energy_market_price_with_vat": avoided_grid_params.energy_market_price_with_vat,
        "line_loss_price_with_vat": avoided_grid_params.line_loss_price_with_vat,
        "system_operation_fee_with_vat": avoided_grid_params.system_operation_fee_with_vat,
        "transmission_distribution_tariff_with_vat": (
            avoided_grid_params.transmission_distribution_tariff_with_vat
        ),
        "gov_fund_surcharge": avoided_grid_params.gov_fund_surcharge,
        "green_direct_retained_transmission_distribution_tariff_with_vat": (
            avoided_grid_params.green_direct_retained_transmission_distribution_tariff_with_vat
        ),
        "green_direct_retained_gov_fund_surcharge": (
            avoided_grid_params.green_direct_retained_gov_fund_surcharge
        ),
        "bess_replacement_operation_year": first_replacement_year,
        "bess_replacement_operation_years": ",".join(str(year) for year in replacement_years),
        "bess_replacement_count": len(replacement_years),
    }
    return EconomicResult(scenario_id=scenario_id, annual_cashflow=annual, metrics=metrics)


def evaluate_batch_single_entity_pre_tax_economy(
    summary: pd.DataFrame,
    avoided_grid_params: AvoidedGridPurchaseParams,
    params: EconomicParams | None = None,
    *,
    retain_annual_cashflows: bool = True,
    annual_cashflow_scenario_ids: Iterable[str] | None = None,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """Evaluate same-investor pre-tax cash flow for a technical summary table."""

    results: list[dict[str, Any]] = []
    annual_cashflows: dict[str, pd.DataFrame] = {}
    retained_scenario_ids = {str(scenario_id) for scenario_id in annual_cashflow_scenario_ids or []}
    economic_params = params or EconomicParams()
    validate_avoided_grid_purchase_params(avoided_grid_params)
    context = _single_entity_economy_context(economic_params, avoided_grid_params)
    for row in _summary_records(summary):
        retain_cashflow = retain_annual_cashflows or _scenario_id(row) in retained_scenario_ids
        result = evaluate_single_entity_pre_tax_economy(
            row,
            avoided_grid_params=avoided_grid_params,
            params=economic_params,
            validate_params=False,
            retain_annual_cashflow=retain_cashflow,
            _context=context,
            _empty_annual_cashflow=_EMPTY_ANNUAL_CASHFLOW,
        )
        results.append(result.metrics)
        if retain_cashflow:
            annual_cashflows[result.scenario_id] = result.annual_cashflow
    return pd.DataFrame(results), annual_cashflows
