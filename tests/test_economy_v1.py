import math

import pytest

from green_direct.economy import (
    EconomicParams,
    OtherOperatingRevenueItem,
    evaluate_scenario_economy,
)


def _summary(**overrides):
    data = {
        "scenario_id": "S_ECO",
        "wind_capacity": 0.0,
        "pv_capacity": 0.0,
        "bess_power": 0.0,
        "bess_energy": 0.0,
        "grid_export_energy": 0.0,
        "self_use_energy": 0.0,
        "annual_equivalent_cycles": 0.0,
        "replacement_year": math.inf,
    }
    data.update(overrides)
    return data


def test_no_input_vat_pays_value_added_tax_normally():
    result = evaluate_scenario_economy(
        _summary(grid_export_energy=452.0),
        EconomicParams(operation_years=1, construction_input_vat_rate=0.0, grid_export_price_with_vat=0.25),
    )

    year1 = result.annual_cashflow.loc[result.annual_cashflow["year"] == 1].iloc[0]

    assert year1["grid_export_revenue_with_vat"] == pytest.approx(113.0)
    assert year1["output_vat"] == pytest.approx(13.0)
    assert year1["vat_payable"] == pytest.approx(13.0)
    assert year1["taxes_and_surcharges"] == pytest.approx(1.3)


def test_construction_input_vat_carries_forward_into_operation_years():
    result = evaluate_scenario_economy(
        _summary(wind_capacity=1.0, grid_export_energy=452.0),
        EconomicParams(operation_years=2, construction_input_vat_rate=0.10, grid_export_price_with_vat=0.25),
    )
    annual = result.annual_cashflow
    year0 = annual.loc[annual["year"] == 0].iloc[0]
    year1 = annual.loc[annual["year"] == 1].iloc[0]

    assert year0["construction_input_vat"] == pytest.approx(4500.0 - 4500.0 / 1.10)
    assert year0["vat_credit_end"] == pytest.approx(year0["construction_input_vat"])
    assert year1["vat_credit_begin"] == pytest.approx(year0["vat_credit_end"])
    assert year1["vat_payable"] == 0
    assert year1["vat_credit_end"] == pytest.approx(year0["vat_credit_end"] - year1["output_vat"])


def test_bess_replacement_input_vat_reduces_vat_or_creates_credit():
    result = evaluate_scenario_economy(
        _summary(bess_energy=10.0, replacement_year=2.0, grid_export_energy=452.0),
        EconomicParams(
            operation_years=5,
            construction_input_vat_rate=0.0,
            grid_export_price_with_vat=0.25,
            bess_replacement_cost_ratio=0.5,
        ),
    )
    year2 = result.annual_cashflow.loc[result.annual_cashflow["year"] == 2].iloc[0]

    assert year2["bess_replacement_cash_outflow"] == pytest.approx(10.0 * 900.0 * 0.5)
    assert year2["bess_replacement_input_vat"] > 0
    assert year2["vat_payable"] == 0
    assert year2["vat_credit_end"] > 0


def test_initial_assets_depreciate_for_20_years_then_stop():
    result = evaluate_scenario_economy(
        _summary(wind_capacity=1.0, pv_capacity=1.0, bess_energy=1.0),
        EconomicParams(operation_years=25),
    )
    annual = result.annual_cashflow
    year1 = annual.loc[annual["year"] == 1].iloc[0]
    year20 = annual.loc[annual["year"] == 20].iloc[0]
    year21 = annual.loc[annual["year"] == 21].iloc[0]

    assert year1["wind_depreciation"] == pytest.approx((4500.0 / 1.10) / 20)
    assert year1["pv_depreciation"] == pytest.approx((2500.0 / 1.10) / 20)
    assert year1["bess_depreciation"] == pytest.approx((900.0 / 1.10) / 20)
    assert year20["depreciation"] == pytest.approx(year1["depreciation"])
    assert year21["depreciation"] == 0


def test_no_actual_vat_payment_means_no_surcharges():
    result = evaluate_scenario_economy(
        _summary(wind_capacity=1.0, grid_export_energy=10.0),
        EconomicParams(operation_years=1),
    )
    year1 = result.annual_cashflow.loc[result.annual_cashflow["year"] == 1].iloc[0]

    assert year1["vat_payable"] == 0
    assert year1["taxes_and_surcharges"] == 0


def test_income_tax_rate_supports_25_and_15_percent():
    summary = _summary(grid_export_energy=452.0)
    params_25 = EconomicParams(operation_years=1, construction_input_vat_rate=0.0, income_tax_rate=0.25)
    params_15 = EconomicParams(operation_years=1, construction_input_vat_rate=0.0, income_tax_rate=0.15)

    year1_25 = evaluate_scenario_economy(summary, params_25).annual_cashflow.iloc[1]
    year1_15 = evaluate_scenario_economy(summary, params_15).annual_cashflow.iloc[1]

    assert year1_25["taxable_income"] == pytest.approx(year1_15["taxable_income"])
    assert year1_25["income_tax"] == pytest.approx(year1_25["taxable_income"] * 0.25)
    assert year1_15["income_tax"] == pytest.approx(year1_15["taxable_income"] * 0.15)


def test_irr_returns_clear_status_when_unreliable():
    result = evaluate_scenario_economy(
        _summary(grid_export_energy=452.0),
        EconomicParams(operation_years=1, construction_input_vat_rate=0.0),
    )

    assert result.metrics["firr"] is None
    assert "IRR 无法可靠计算" in result.metrics["firr_status"]


def test_cashflow_table_excludes_working_capital_and_residual_fields():
    result = evaluate_scenario_economy(_summary(wind_capacity=1.0), EconomicParams(operation_years=1))

    forbidden = {
        "working_capital",
        "working_capital_recovery",
        "salvage_value",
        "residual_value_recovery",
        "amortization",
    }
    assert forbidden.isdisjoint(result.annual_cashflow.columns)


def test_operating_cost_has_no_input_vat_in_v1():
    result = evaluate_scenario_economy(
        _summary(wind_capacity=1.0),
        EconomicParams(operation_years=1, construction_input_vat_rate=0.0),
    )
    year1 = result.annual_cashflow.iloc[1]

    assert year1["operating_cost_with_vat"] > 0
    assert year1["input_vat"] == 0


def test_negative_other_operating_revenue_has_no_input_or_output_vat():
    params = EconomicParams(
        operation_years=1,
        construction_input_vat_rate=0.0,
        other_operating_revenues=(
            OtherOperatingRevenueItem(name="额外成本", amount_with_vat=-10.0, vat_rate=0.13),
        ),
    )
    result = evaluate_scenario_economy(_summary(), params)
    year1 = result.annual_cashflow.iloc[1]

    assert year1["other_operating_revenue_with_vat"] == -10
    assert year1["output_vat"] == 0
    assert year1["input_vat"] == 0


def test_bess_replacement_is_skipped_when_triggered_in_final_operation_year():
    result = evaluate_scenario_economy(
        _summary(bess_energy=10.0, replacement_year=5.0),
        EconomicParams(operation_years=5),
    )

    assert result.metrics["bess_replacement_operation_year"] is None
    assert result.annual_cashflow["bess_replacement_cash_outflow"].sum() == 0
