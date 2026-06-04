import pandas as pd
import pytest

from green_direct.economy import AvoidedGridPurchaseParams, EconomicParams
from green_direct.models.params import PolicyParams
from green_direct.services import (
    StudyResult,
    TechnicalStudyInput,
    build_recommendation_study,
    run_economic_study,
    run_technical_study,
)


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


def _curve_csv(values: list[float], column: str) -> bytes:
    frame = pd.DataFrame(
        {
            "时间": pd.date_range("2020-01-01", periods=len(values), freq="h"),
            column: values,
        }
    )
    return frame.to_csv(index=False).encode("utf-8-sig")


def test_technical_study_wraps_curve_reading_batch_run_and_study_result():
    grid = {
        "pv_capacity": {"start": 0, "end": 1, "step": 1},
        "wind_capacity": {"start": 0, "end": 1, "step": 1},
        "bess_power": {"start": 0, "end": 0, "step": 1},
        "bess_duration_hours": [0],
    }

    technical = run_technical_study(
        TechnicalStudyInput(
            load_source=_curve_csv([10.0, 10.0], "负荷"),
            pv_source=_curve_csv([1.0, -0.01], "光伏"),
            wind_source=_curve_csv([0.0, 1.0], "风电"),
            load_time_col="时间",
            load_value_col="负荷",
            pv_time_col="时间",
            pv_value_col="光伏",
            wind_time_col="时间",
            wind_value_col="风电",
            scenario_grid=grid,
            policy_params=PolicyParams(allow_export=False),
            validate_length=False,
            config_metadata={"demo": True},
        ),
        study_id="study-test",
    )
    study = StudyResult.from_technical(technical)

    assert technical.study_id == "study-test"
    assert technical.scenario_count == 3
    assert set(technical.hourly_details) == set(technical.summary["scenario_id"])
    assert technical.config_snapshot["demo"] is True
    assert technical.config_snapshot["policy"]["allow_export"] is False
    assert technical.input_diagnostics.warnings_as_messages()
    assert study.batch_result is technical.batch_result
    assert study.summary.equals(technical.summary)


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
