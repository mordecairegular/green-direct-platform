import pandas as pd
import pytest

from green_direct.economy import AvoidedGridPurchaseParams, EconomicParams, read_price_curve
from green_direct.models.params import PolicyParams
from green_direct.services import (
    StudyResult,
    TechnicalStudyInput,
    build_recommendation_study,
    run_hourly_detail_for_scenario,
    run_economic_study,
    run_technical_study,
    scenario_from_summary_row,
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


def _small_technical_input(
    *,
    retain_hourly_details: bool = True,
    hourly_detail_scenario_ids: tuple[str, ...] = (),
) -> TechnicalStudyInput:
    grid = {
        "pv_capacity": {"start": 0, "end": 1, "step": 1},
        "wind_capacity": {"start": 0, "end": 1, "step": 1},
        "bess_power": {"start": 0, "end": 0, "step": 1},
        "bess_duration_hours": [0],
    }
    return TechnicalStudyInput(
        load_source=_curve_csv([10.0, 10.0], "负荷"),
        pv_source=_curve_csv([1.0, 0.0], "光伏"),
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
        retain_hourly_details=retain_hourly_details,
        hourly_detail_scenario_ids=hourly_detail_scenario_ids,
    )


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


def test_technical_study_can_skip_hourly_detail_retention():
    grid = {
        "pv_capacity": {"start": 0, "end": 1, "step": 1},
        "wind_capacity": {"start": 0, "end": 1, "step": 1},
        "bess_power": {"start": 0, "end": 0, "step": 1},
        "bess_duration_hours": [0],
    }

    technical = run_technical_study(
        TechnicalStudyInput(
            load_source=_curve_csv([10.0, 10.0], "负荷"),
            pv_source=_curve_csv([1.0, 0.0], "光伏"),
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
            retain_hourly_details=False,
        ),
        study_id="study-summary-only",
    )

    assert technical.scenario_count == 3
    assert len(technical.summary) == 3
    assert technical.hourly_details == {}
    assert technical.config_snapshot["detail_retention"]["retain_hourly_details"] is False


def test_hourly_detail_can_be_regenerated_for_selected_summary_scenario():
    full = run_technical_study(_small_technical_input(), study_id="study-full")
    summary_only = run_technical_study(
        _small_technical_input(retain_hourly_details=False),
        study_id="study-summary-only",
    )
    selected_id = str(summary_only.summary["scenario_id"].iloc[-1])

    regenerated = run_hourly_detail_for_scenario(
        _small_technical_input(retain_hourly_details=False),
        scenario_id=selected_id,
        summary=summary_only.summary,
    )

    assert selected_id not in summary_only.hourly_details
    assert regenerated.summary["scenario_id"] == selected_id
    pd.testing.assert_frame_equal(
        regenerated.hourly_detail.reset_index(drop=True),
        full.hourly_details[selected_id].reset_index(drop=True),
    )
    expected_summary = full.summary.loc[full.summary["scenario_id"] == selected_id].iloc[0]
    for column, value in regenerated.summary.items():
        if isinstance(value, float):
            assert value == pytest.approx(expected_summary[column])
        else:
            assert value == expected_summary[column]


def test_hourly_detail_regeneration_rejects_missing_summary_scenario():
    technical = run_technical_study(
        _small_technical_input(retain_hourly_details=False),
        study_id="study-summary-only",
    )

    with pytest.raises(ValueError, match="Scenario is not present"):
        run_hourly_detail_for_scenario(
            _small_technical_input(retain_hourly_details=False),
            scenario_id="S_DOES_NOT_EXIST",
            summary=technical.summary,
        )


def test_scenario_from_summary_row_requires_capacity_columns():
    with pytest.raises(ValueError, match="bess_energy"):
        scenario_from_summary_row(
            {
                "scenario_id": "S0001",
                "pv_capacity": 1.0,
                "wind_capacity": 0.0,
                "bess_power": 0.0,
            }
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


def test_economic_study_can_skip_annual_cashflow_retention():
    result = run_economic_study(
        _summary(),
        economic_params=EconomicParams(operation_years=2, construction_input_vat_rate=0.0),
        avoided_grid_params=AvoidedGridPurchaseParams(net_avoided_grid_cost_price=0.5),
        load_side_avoided_charge_price=0.55,
        green_power_settlement_price_with_vat=0.35,
        retain_annual_cashflows=False,
    )

    assert result.power_summary["scenario_id"].tolist() == ["S_SERVICE"]
    assert result.single_entity_summary["scenario_id"].tolist() == ["S_SERVICE"]
    assert result.power_annual_cashflows == {}
    assert result.single_entity_annual_cashflows == {}


def test_economic_study_can_keep_selected_annual_cashflows_only():
    result = run_economic_study(
        _summary(),
        economic_params=EconomicParams(operation_years=2, construction_input_vat_rate=0.0),
        avoided_grid_params=AvoidedGridPurchaseParams(net_avoided_grid_cost_price=0.5),
        load_side_avoided_charge_price=0.55,
        green_power_settlement_price_with_vat=0.35,
        retain_annual_cashflows=False,
        annual_cashflow_scenario_ids=["S_SERVICE"],
    )

    assert set(result.power_annual_cashflows) == {"S_SERVICE"}
    assert set(result.single_entity_annual_cashflows) == {"S_SERVICE"}


def test_economic_study_adds_fixed_landed_price_summary():
    summary = _summary().assign(
        total_load_energy=250.0,
        grid_import_energy=150.0,
        self_use_energy=100.0,
        grid_import_rate=0.6,
        green_load_rate=0.4,
    )

    result = run_economic_study(
        summary,
        economic_params=EconomicParams(operation_years=2, construction_input_vat_rate=0.0),
        avoided_grid_params=AvoidedGridPurchaseParams(net_avoided_grid_cost_price=0.5),
        load_side_avoided_charge_price=0.55,
        green_power_settlement_price_with_vat=0.42,
        fixed_down_grid_landed_price_with_vat=0.65,
        fixed_green_self_use_extra_fee_with_vat=0.18,
        min_power_side_acceptable_firr=None,
    )

    power = result.power_summary.set_index("scenario_id")
    single_entity = result.single_entity_summary.set_index("scenario_id")
    expected_after = (150.0 * 0.65 + 100.0 * (0.42 + 0.18)) / 250.0
    assert result.price_mode == "fixed_price"
    assert result.landed_price_summary["scenario_id"].tolist() == ["S_SERVICE"]
    assert power.loc["S_SERVICE", "load_landed_price_before_green_with_vat"] == pytest.approx(0.65)
    assert power.loc["S_SERVICE", "load_landed_price_after_green_with_vat"] == pytest.approx(expected_after)
    assert power.loc["S_SERVICE", "weighted_down_grid_landed_price_with_vat"] == pytest.approx(0.65)
    assert power.loc["S_SERVICE", "green_self_use_landed_price_with_vat_effective"] == pytest.approx(0.60)
    assert single_entity.loc["S_SERVICE", "load_landed_price_after_green_with_vat"] == pytest.approx(expected_after)


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


def test_economic_study_uses_hourly_price_curve_by_scenario_self_use_timing():
    hours = 8760
    summary = pd.DataFrame(
        [
            {
                **_summary().iloc[0].to_dict(),
                "scenario_id": "S_LOW_PRICE_SELF_USE",
                "self_use_energy": 10.0,
                "grid_export_energy": 0.0,
            },
            {
                **_summary().iloc[0].to_dict(),
                "scenario_id": "S_HIGH_PRICE_SELF_USE",
                "self_use_energy": 10.0,
                "grid_export_energy": 0.0,
            },
        ]
    )
    prices = pd.DataFrame(
        {
            "hour_index": range(hours),
            "energy_market_price_with_vat": [0.10] + [0.50] * (hours - 2) + [1.00],
        }
    )
    price_curve = read_price_curve(prices.to_csv(index=False).encode("utf-8-sig"))

    def hourly_for(scenario_id: str, self_use_hour: int) -> pd.DataFrame:
        frame = pd.DataFrame(
            {
                "scenario_id": scenario_id,
                "timestamp": pd.date_range("2025-01-01", periods=hours, freq="h"),
                "hour_index": range(hours),
                "direct_self_use_power": [0.0] * hours,
                "bess_discharge_power": [0.0] * hours,
                "grid_export_power": [0.0] * hours,
            }
        )
        frame.loc[self_use_hour, "direct_self_use_power"] = 10.0
        return frame

    economy = run_economic_study(
        summary,
        economic_params=EconomicParams(
            operation_years=2,
            construction_input_vat_rate=0.0,
            wind_capex_per_kw_with_vat=0.0,
        ),
        avoided_grid_params=AvoidedGridPurchaseParams(
            net_avoided_grid_cost_price=None,
            grid_purchase_vat_rate=0.13,
        ),
        load_side_avoided_charge_price=0.50,
        green_power_settlement_price_with_vat=0.20,
        min_power_side_acceptable_firr=None,
        price_curve=price_curve,
        hourly_details={
            "S_LOW_PRICE_SELF_USE": hourly_for("S_LOW_PRICE_SELF_USE", 0),
            "S_HIGH_PRICE_SELF_USE": hourly_for("S_HIGH_PRICE_SELF_USE", hours - 1),
        },
    )

    single_entity = economy.single_entity_summary.set_index("scenario_id")
    assert economy.price_mode == "hourly_curve"
    assert single_entity.loc[
        "S_HIGH_PRICE_SELF_USE",
        "annual_self_use_saving",
    ] > single_entity.loc["S_LOW_PRICE_SELF_USE", "annual_self_use_saving"]

    recommendation = build_recommendation_study(
        summary,
        economy.power_summary,
        economy.recommendation_inputs,
        single_entity_summary=economy.single_entity_summary,
    )
    load_side = recommendation.load_side_detail.set_index("scenario_id")
    assert load_side.loc["S_HIGH_PRICE_SELF_USE", "load_side_annual_benefit"] == pytest.approx(8.0)
    assert load_side.loc["S_LOW_PRICE_SELF_USE", "load_side_annual_benefit"] == pytest.approx(-1.0)


def test_economic_study_adds_hourly_curve_landed_price_summary():
    hours = 8760
    summary = _summary().assign(
        total_load_energy=10.0,
        grid_import_energy=6.0,
        self_use_energy=4.0,
        grid_import_rate=0.6,
        green_load_rate=0.4,
    )
    prices = pd.DataFrame(
        {
            "hour_index": range(hours),
            "energy_market_price_with_vat": [0.40] * hours,
            "line_loss_price_with_vat": [0.0] * hours,
            "system_operation_fee_with_vat": [0.0] * hours,
            "transmission_distribution_tariff_with_vat": [0.10] * hours,
            "gov_fund_surcharge": [0.02] * hours,
        }
    )
    price_curve = read_price_curve(prices.to_csv(index=False).encode("utf-8-sig"))
    hourly = pd.DataFrame(
        {
            "scenario_id": "S_SERVICE",
            "timestamp": pd.date_range("2025-01-01", periods=hours, freq="h"),
            "hour_index": range(hours),
            "load_power": [0.0] * hours,
            "direct_self_use_power": [0.0] * hours,
            "bess_discharge_power": [0.0] * hours,
            "grid_import_power": [0.0] * hours,
            "grid_export_power": [0.0] * hours,
        }
    )
    hourly.loc[0, "load_power"] = 10.0
    hourly.loc[0, "direct_self_use_power"] = 4.0
    hourly.loc[0, "grid_import_power"] = 6.0

    result = run_economic_study(
        summary,
        economic_params=EconomicParams(operation_years=2, construction_input_vat_rate=0.0),
        avoided_grid_params=AvoidedGridPurchaseParams(
            net_avoided_grid_cost_price=None,
            grid_purchase_vat_rate=0.13,
        ),
        load_side_avoided_charge_price=0.50,
        green_power_settlement_price_with_vat=0.30,
        min_power_side_acceptable_firr=None,
        price_curve=price_curve,
        hourly_details={"S_SERVICE": hourly},
    )

    power = result.power_summary.set_index("scenario_id")
    expected_before = 0.40 + 0.10 + 0.02
    expected_green_landed = 0.30 + 0.10 + 0.02
    expected_after = (6.0 * expected_before + 4.0 * expected_green_landed) / 10.0
    assert result.price_mode == "hourly_curve"
    assert power.loc["S_SERVICE", "load_landed_price_before_green_with_vat"] == pytest.approx(expected_before)
    assert power.loc["S_SERVICE", "load_landed_price_after_green_with_vat"] == pytest.approx(expected_after)
    assert power.loc["S_SERVICE", "weighted_down_grid_landed_price_with_vat"] == pytest.approx(expected_before)
    assert power.loc["S_SERVICE", "green_self_use_landed_price_with_vat_effective"] == pytest.approx(expected_green_landed)
