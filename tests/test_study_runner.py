import pandas as pd
import pytest

from green_direct.economy import AvoidedGridPurchaseParams, EconomicParams
from green_direct.services import build_recommendation_study, run_economic_study


def _summary() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "scenario_id": "S_SERVICE",
                "pass_policy": True,
                "wind_capacity": 1.0,
                "pv_capacity": 0.0,
                "bess_power": 0.0,
                "bess_energy": 0.0,
                "grid_export_energy": 10.0,
                "self_use_energy": 100.0,
                "annual_equivalent_cycles": 0.0,
                "replacement_year": float("inf"),
                "green_load_rate": 0.4,
                "self_use_rate": 0.8,
                "curtail_rate": 0.02,
                "curtail_energy": 2.0,
            }
        ]
    )


def test_economic_study_preserves_recommendation_input_snapshot():
    result = run_economic_study(
        _summary(),
        economic_params=EconomicParams(operation_years=2, construction_input_vat_rate=0.0),
        avoided_grid_params=AvoidedGridPurchaseParams(net_avoided_grid_cost_price=0.5),
        load_side_avoided_charge_price=0.55,
        green_power_settlement_price_with_vat=0.35,
        environmental_value_per_kwh=0.01,
        min_power_side_acceptable_firr=0.07,
    )

    assert result.power_summary["scenario_id"].tolist() == ["S_SERVICE"]
    assert result.single_entity_summary["scenario_id"].tolist() == ["S_SERVICE"]
    assert result.recommendation_inputs.load_side_avoided_charge_price == 0.55
    assert result.recommendation_inputs.to_session_dict()["green_power_settlement_price_with_vat"] == 0.35


def test_recommendation_study_builds_portfolio_and_load_side_detail():
    economy = run_economic_study(
        _summary(),
        economic_params=EconomicParams(operation_years=2, construction_input_vat_rate=0.0),
        avoided_grid_params=AvoidedGridPurchaseParams(net_avoided_grid_cost_price=0.5),
        load_side_avoided_charge_price=0.55,
        green_power_settlement_price_with_vat=0.35,
        min_power_side_acceptable_firr=None,
    )

    recommendation = build_recommendation_study(
        _summary(),
        economy.power_summary,
        economy.recommendation_inputs,
        single_entity_summary=economy.single_entity_summary,
        engineering_view="min_investment",
    )

    assert not recommendation.portfolio.empty
    assert "load_side_saving_price" in recommendation.load_side_detail.columns
    assert recommendation.load_side_detail["load_side_saving_price"].iloc[0] == pytest.approx(0.20)
