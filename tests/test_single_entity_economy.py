import math

import pytest

from green_direct.economy import (
    AvoidedGridPurchaseParams,
    EconomicParams,
    calc_net_avoided_grid_cost_price,
    evaluate_single_entity_pre_tax_economy,
)


def _summary(**overrides):
    data = {
        "scenario_id": "S_SINGLE_ENTITY",
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


def test_net_avoided_grid_cost_price_strips_vat_for_bill_build_up_items():
    params = AvoidedGridPurchaseParams(
        energy_market_price_with_vat=0.50,
        line_loss_price_with_vat=0.05,
        system_operation_fee_with_vat=0.03,
        transmission_distribution_tariff_with_vat=0.17,
        gov_fund_surcharge=0.05,
        green_direct_retained_transmission_distribution_tariff_with_vat=0.17,
        green_direct_retained_gov_fund_surcharge=0.05,
        grid_purchase_vat_rate=0.13,
    )

    assert calc_net_avoided_grid_cost_price(params) == pytest.approx(0.58 / 1.13)


def test_single_entity_uses_avoided_grid_cost_not_green_power_settlement_price():
    result = evaluate_single_entity_pre_tax_economy(
        _summary(self_use_energy=100.0, grid_export_energy=113.0),
        AvoidedGridPurchaseParams(
            net_avoided_grid_cost_price=0.60,
        ),
        EconomicParams(
            operation_years=1,
            grid_export_price_with_vat=0.25,
            self_use_price_with_vat=999.0,
        ),
    )
    year1 = result.annual_cashflow.loc[result.annual_cashflow["year"] == 1].iloc[0]

    assert "self_use_revenue_with_vat" not in result.annual_cashflow.columns
    assert year1["self_use_saving"] == pytest.approx(60.0)
    assert year1["grid_export_revenue_without_vat"] == pytest.approx(25.0)
    assert year1["net_cash_flow"] == pytest.approx(85.0)


def test_single_entity_pre_tax_firr_uses_investment_basis_after_deductible_vat():
    result = evaluate_single_entity_pre_tax_economy(
        _summary(self_use_energy=100.0),
        AvoidedGridPurchaseParams(net_avoided_grid_cost_price=0.50),
        EconomicParams(
            operation_years=3,
            other_fixed_asset_investment_with_vat=110.0,
            construction_input_vat_rate=0.10,
            construction_input_vat_deductible=True,
            discount_rate=0.0,
        ),
    )

    assert result.annual_cashflow["net_cash_flow"].tolist() == pytest.approx(
        [-100.0, 50.0, 50.0, 50.0]
    )
    assert result.metrics["initial_investment_basis"] == pytest.approx(100.0)
    assert result.metrics["construction_cash_outflow_with_vat"] == pytest.approx(110.0)
    assert result.metrics["single_entity_static_payback_year"] == pytest.approx(2.0)
    assert result.metrics["single_entity_firr_status"] == "ok"
    assert result.metrics["single_entity_firr_pre_tax"] == pytest.approx(0.23375, abs=1e-4)


def test_single_entity_environmental_value_is_scalar_advanced_benefit():
    result = evaluate_single_entity_pre_tax_economy(
        _summary(self_use_energy=100.0),
        AvoidedGridPurchaseParams(
            net_avoided_grid_cost_price=0.0,
            environmental_value_per_kwh=0.02,
        ),
        EconomicParams(operation_years=1),
    )
    year1 = result.annual_cashflow.loc[result.annual_cashflow["year"] == 1].iloc[0]

    assert year1["environmental_value"] == pytest.approx(2.0)
    assert year1["net_cash_flow"] == pytest.approx(2.0)


def test_avoided_grid_validation_rejects_negative_bill_component():
    with pytest.raises(ValueError, match="energy_market_price_with_vat"):
        calc_net_avoided_grid_cost_price(
            AvoidedGridPurchaseParams(energy_market_price_with_vat=-0.01)
        )
