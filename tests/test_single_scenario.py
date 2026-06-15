import pandas as pd
import pytest

from green_direct.core.bess_dispatch import DispatchStrategy
from green_direct.core.single_scenario_simulator import (
    HOURLY_LEDGER_COLUMNS,
    collect_single_scenario_input_diagnostics,
    run_single_scenario,
)
from green_direct.models.diagnostics import DiagnosticSeverity
from green_direct.models.params import BessParams, PolicyParams
from green_direct.models.scenario import Scenario


def _curves(load, renewable):
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2020-01-01", periods=len(load), freq="h"),
            "load_power": load,
            "pv_pu": renewable,
            "wind_pu": [0] * len(load),
        }
    )


def _run(load, renewable, *, scenario=None, bess_params=None, policy_params=None):
    scenario = scenario or Scenario("S001", pv_capacity=1, wind_capacity=0, bess_power=0, bess_energy=0)
    return run_single_scenario(
        _curves(load, renewable),
        scenario,
        bess_params=bess_params,
        policy_params=policy_params,
    )


def test_case_1_no_renewable_no_bess():
    result = _run(
        [10, 20, 30],
        [0, 0, 0],
        scenario=Scenario("S001", 0, 0, 0, 0),
    )

    assert result.hourly_detail["grid_import_power"].tolist() == [10, 20, 30]
    assert result.hourly_detail["direct_self_use_power"].tolist() == [0, 0, 0]
    assert result.summary["total_load_energy"] == 60
    assert result.summary["grid_import_energy"] == 60


def test_case_2_no_bess_renewable_less_than_load():
    result = _run([10, 10, 10], [5, 6, 7])

    assert result.hourly_detail["direct_self_use_power"].tolist() == [5, 6, 7]
    assert result.hourly_detail["grid_import_power"].tolist() == [5, 4, 3]
    assert result.hourly_detail["grid_export_power"].tolist() == [0, 0, 0]
    assert result.hourly_detail["curtail_power"].tolist() == [0, 0, 0]


def test_case_3_no_bess_surplus_export_not_allowed():
    result = _run(
        [10, 10, 10],
        [12, 15, 8],
        policy_params=PolicyParams(allow_export=False),
    )

    assert result.hourly_detail["direct_self_use_power"].tolist() == [10, 10, 8]
    assert result.hourly_detail["curtail_power"].tolist() == [2, 5, 0]
    assert result.hourly_detail["grid_import_power"].tolist() == [0, 0, 2]
    assert result.hourly_detail["grid_export_power"].tolist() == [0, 0, 0]


def test_case_4_no_bess_surplus_export_allowed():
    result = _run(
        [10, 10, 10],
        [12, 15, 8],
        policy_params=PolicyParams(allow_export=True, export_power_max=None),
    )

    assert result.hourly_detail["direct_self_use_power"].tolist() == [10, 10, 8]
    assert result.hourly_detail["grid_export_power"].tolist() == [2, 5, 0]
    assert result.hourly_detail["curtail_power"].tolist() == [0, 0, 0]
    assert result.hourly_detail["grid_import_power"].tolist() == [0, 0, 2]


def test_case_5_bess_charge_power_limit():
    result = _run(
        [10],
        [20],
        scenario=Scenario("S001", 1, 0, 3, 10),
        bess_params=BessParams(soc_initial=0.5, soc_min=0.1, soc_max=0.9, eta_charge=1.0),
        policy_params=PolicyParams(allow_export=False),
    )

    row = result.hourly_detail.iloc[0]
    assert row["bess_charge_power"] == 3
    assert row["curtail_power"] == 7
    assert row["soc_end"] == pytest.approx(0.8)


def test_case_6_bess_charge_capacity_limit():
    result = _run(
        [10],
        [20],
        scenario=Scenario("S001", 1, 0, 10, 10),
        bess_params=BessParams(soc_initial=0.85, soc_min=0.1, soc_max=0.9, eta_charge=1.0),
        policy_params=PolicyParams(allow_export=False),
    )

    row = result.hourly_detail.iloc[0]
    assert row["bess_charge_power"] == pytest.approx(0.5)
    assert row["curtail_power"] == pytest.approx(9.5)
    assert row["soc_end"] == pytest.approx(0.9)


def test_case_7_bess_discharge_power_limit():
    result = _run(
        [20],
        [10],
        scenario=Scenario("S001", 1, 0, 3, 10),
        bess_params=BessParams(soc_initial=0.9, soc_min=0.1, soc_max=0.9, eta_discharge=1.0),
    )

    row = result.hourly_detail.iloc[0]
    assert row["bess_discharge_power"] == 3
    assert row["grid_import_power"] == 7
    assert row["soc_end"] == pytest.approx(0.6)


def test_case_8_bess_discharge_capacity_limit():
    result = _run(
        [20],
        [10],
        scenario=Scenario("S001", 1, 0, 10, 10),
        bess_params=BessParams(soc_initial=0.15, soc_min=0.1, soc_max=0.9, eta_discharge=1.0),
    )

    row = result.hourly_detail.iloc[0]
    assert row["bess_discharge_power"] == pytest.approx(0.5)
    assert row["grid_import_power"] == pytest.approx(9.5)
    assert row["soc_end"] == pytest.approx(0.1)


def test_case_9_efficiency_loss_and_balance():
    result = _run(
        [10, 20],
        [20, 10],
        scenario=Scenario("S001", 1, 0, 10, 20),
        bess_params=BessParams(
            soc_initial=0.5,
            soc_min=0,
            soc_max=1,
            eta_charge=0.9,
            eta_discharge=0.9,
        ),
        policy_params=PolicyParams(allow_export=False),
    )

    assert result.summary["bess_loss_energy"] > 0
    assert result.hourly_detail["soc_end"].between(0, 1).all()
    balance = (
        result.hourly_detail["direct_self_use_power"]
        + result.hourly_detail["bess_discharge_power"]
        + result.hourly_detail["grid_import_power"]
    )
    assert balance.tolist() == pytest.approx(result.hourly_detail["load_power"].tolist())


def test_summary_only_mode_matches_full_hourly_summary_without_ledger_retention():
    curves = _curves([10, 20, 10, 15], [20, 5, 15, 0])
    scenario = Scenario("S001", 1, 0, 10, 20)
    bess_params = BessParams(soc_initial=0.5, soc_min=0.1, soc_max=0.9, eta_charge=0.9, eta_discharge=0.92)
    policy_params = PolicyParams(allow_export=True, export_rate_max=0.2, grid_exchange_power_limit=12)

    full = run_single_scenario(curves, scenario, bess_params=bess_params, policy_params=policy_params)
    summary_only = run_single_scenario(
        curves,
        scenario,
        bess_params=bess_params,
        policy_params=policy_params,
        retain_hourly_detail=False,
    )

    assert summary_only.hourly_detail.empty
    assert list(summary_only.hourly_detail.columns) == HOURLY_LEDGER_COLUMNS
    assert summary_only.summary.keys() == full.summary.keys()
    for key, expected in full.summary.items():
        actual = summary_only.summary[key]
        if isinstance(expected, float):
            assert actual == pytest.approx(expected), key
        else:
            assert actual == expected, key


def test_case_11_load_side_self_use_consistency():
    result = _run(
        [10, 20, 10],
        [20, 5, 15],
        scenario=Scenario("S001", 1, 0, 10, 20),
        policy_params=PolicyParams(allow_export=False),
    )
    hourly = result.hourly_detail

    assert (
        hourly["load_power"] - hourly["grid_import_power"]
    ).tolist() == pytest.approx(
        (hourly["direct_self_use_power"] + hourly["bess_discharge_power"]).tolist(),
        abs=1e-6,
    )


def test_case_12_soc_rolls_between_hours():
    result = _run(
        [10, 20, 10],
        [20, 5, 15],
        scenario=Scenario("S001", 1, 0, 10, 20),
        policy_params=PolicyParams(allow_export=False),
    )
    hourly = result.hourly_detail

    assert hourly["soc_start"].iloc[1:].tolist() == pytest.approx(hourly["soc_end"].iloc[:-1].tolist())


def test_case_13_bess_never_charges_and_discharges_same_hour():
    result = _run(
        [10, 20, 10],
        [20, 5, 15],
        scenario=Scenario("S001", 1, 0, 10, 20),
        policy_params=PolicyParams(allow_export=False),
    )
    hourly = result.hourly_detail

    assert not ((hourly["bess_charge_power"] > 0) & (hourly["bess_discharge_power"] > 0)).any()


def test_case_15_all_capacity_zero_no_division_error():
    result = _run(
        [10, 20],
        [0, 0],
        scenario=Scenario("S001", 0, 0, 0, 0),
    )

    assert result.summary["grid_import_energy"] == 30
    assert result.summary["grid_import_rate"] == 1
    assert result.summary["self_use_rate"] == 0
    assert result.summary["annual_equivalent_cycles"] == 0


def test_annual_export_cap_runtime_turns_excess_export_to_curtailment():
    result = _run(
        [0, 0, 0],
        [50, 50, 0],
        policy_params=PolicyParams(allow_export=True, export_rate_max=0.2),
    )

    assert result.summary["total_renewable_generation"] == 100
    assert result.summary["export_cap_energy"] == 20
    assert result.summary["grid_export_energy"] == 20
    assert result.summary["export_rate"] == pytest.approx(0.2)
    assert result.summary["curtail_energy"] == 80
    assert result.summary["curtail_due_to_export_cap_energy"] == 80
    assert result.summary["export_control_mode"] == "annual_cap_runtime"
    assert result.hourly_detail["grid_export_power"].tolist() == [20, 0, 0]
    assert result.hourly_detail["curtail_due_to_export_cap_power"].tolist() == [30, 50, 0]


def test_post_check_mode_keeps_export_and_marks_policy_failure():
    result = _run(
        [0, 0],
        [50, 50],
        policy_params=PolicyParams(
            allow_export=True,
            export_rate_max=0.2,
            export_control_mode="post_check",
        ),
    )

    assert result.summary["grid_export_energy"] == 100
    assert result.summary["export_rate"] == 1
    assert result.summary["curtail_energy"] == 0
    assert result.summary["curtail_due_to_export_cap_energy"] == 0
    assert result.summary["pass_policy"] is False
    assert "上网比例超限" in result.summary["fail_reasons"]


def test_negative_pv_is_counted_as_station_use_and_participates_in_balance():
    result = _run(
        [10],
        [-0.2],
        scenario=Scenario("S001", pv_capacity=10, wind_capacity=0, bess_power=0, bess_energy=0),
    )

    row = result.hourly_detail.iloc[0]
    assert row["pv_power"] == -2
    assert row["pv_station_use_power"] == 2
    assert row["renewable_generation_power"] == 0
    assert row["renewable_power"] == 0
    assert row["grid_import_power"] == 12
    assert result.summary["pv_station_use_energy"] == 2
    assert result.summary["station_use_energy"] == 2
    assert result.summary["total_renewable_generation"] == 0


def test_positive_wind_first_offsets_pv_station_use_then_supplies_load():
    curves = pd.DataFrame(
        {
            "timestamp": pd.date_range("2020-01-01", periods=1, freq="h"),
            "load_power": [10],
            "pv_pu": [-0.2],
            "wind_pu": [0.5],
        }
    )
    result = run_single_scenario(curves, Scenario("S001", pv_capacity=10, wind_capacity=10, bess_power=0, bess_energy=0))

    row = result.hourly_detail.iloc[0]
    assert row["pv_station_use_power"] == 2
    assert row["wind_generation_power"] == 5
    assert row["renewable_generation_power"] == 5
    assert row["renewable_power"] == 3
    assert row["direct_self_use_power"] == 3
    assert row["grid_import_power"] == 7
    assert result.summary["total_renewable_generation"] == 5
    assert result.summary["pv_station_use_energy"] == 2


def test_grid_exchange_limit_curtails_surplus_export():
    result = _run(
        [10],
        [30],
        policy_params=PolicyParams(
            allow_export=True,
            export_control_mode="post_check",
            grid_exchange_power_limit=5,
        ),
    )

    row = result.hourly_detail.iloc[0]
    assert row["grid_export_power"] == 5
    assert row["curtail_power"] == 15
    assert row["curtail_due_to_exchange_limit_power"] == 15
    assert result.summary["max_grid_export_power"] == 5
    assert result.summary["curtail_due_to_exchange_limit_energy"] == 15


def test_grid_exchange_limit_caps_import_and_marks_policy_failure():
    result = _run(
        [20],
        [0],
        policy_params=PolicyParams(grid_exchange_power_limit=8),
    )

    row = result.hourly_detail.iloc[0]
    assert row["grid_import_power"] == 8
    assert row["exchange_import_shortfall_power"] == 12
    assert result.summary["exchange_import_shortfall_energy"] == 12
    assert result.summary["pass_policy"] is False
    assert "电网交换功率限制导致下网缺口" in result.summary["fail_reasons"]


def test_bess_discharge_never_exports_to_grid():
    result = _run(
        [5, 0],
        [0, 0],
        scenario=Scenario("S001", pv_capacity=1, wind_capacity=0, bess_power=10, bess_energy=20),
        bess_params=BessParams(soc_initial=0.9, soc_min=0.1, soc_max=0.9, eta_discharge=1.0),
        policy_params=PolicyParams(allow_export=True, export_control_mode="post_check"),
    )
    hourly = result.hourly_detail

    assert hourly["bess_discharge_power"].tolist() == [5, 0]
    assert hourly["grid_export_power"].tolist() == [0, 0]
    assert result.summary["bess_discharge_to_load"] == 5
    assert result.summary["grid_export_energy"] == 0


def test_default_dispatch_strategy_is_recorded():
    result = _run([10], [0])

    assert result.summary["dispatch_strategy"] == DispatchStrategy.GRID_CONNECTED_RENEWABLE_FIRST_GREEDY.value


def test_omitted_strategy_uses_grid_connected_renewable_first_greedy():
    result = run_single_scenario(
        _curves([10], [0]),
        Scenario("S001", pv_capacity=1, wind_capacity=0, bess_power=0, bess_energy=0),
        strategy=None,
    )

    assert result.summary["dispatch_strategy"] == DispatchStrategy.GRID_CONNECTED_RENEWABLE_FIRST_GREEDY.value


def test_explicit_default_strategy_matches_omitted_strategy_results():
    curves = _curves([10, 20, 0], [20, 5, 30])
    scenario = Scenario("S001", pv_capacity=1, wind_capacity=0, bess_power=10, bess_energy=20)
    bess_params = BessParams(soc_initial=0.5, soc_min=0.1, soc_max=0.9)
    policy_params = PolicyParams(allow_export=True, export_control_mode="post_check")

    default_result = run_single_scenario(curves, scenario, bess_params=bess_params, policy_params=policy_params)
    explicit_result = run_single_scenario(
        curves,
        scenario,
        bess_params=bess_params,
        policy_params=policy_params,
        strategy=DispatchStrategy.GRID_CONNECTED_RENEWABLE_FIRST_GREEDY,
    )

    pd.testing.assert_frame_equal(default_result.hourly_detail, explicit_result.hourly_detail)
    comparable_summary = {
        key: value
        for key, value in default_result.summary.items()
        if key != "dispatch_strategy"
    }
    explicit_summary = {
        key: value
        for key, value in explicit_result.summary.items()
        if key != "dispatch_strategy"
    }
    assert comparable_summary == explicit_summary


def test_unimplemented_dispatch_strategy_raises_clear_error():
    with pytest.raises(ValueError, match="Unsupported dispatch strategy"):
        run_single_scenario(
            _curves([10], [0]),
            Scenario("S001", pv_capacity=1, wind_capacity=0, bess_power=0, bess_energy=0),
            strategy="OFF_GRID_DIESEL",
        )


def test_hourly_detail_is_v0_1_hourly_energy_ledger_shape():
    result = _run([10, 20, 30], [0, 5, 40])
    core_fields = {
        "scenario_id",
        "timestamp",
        "hour_index",
        "load_power",
        "renewable_power",
        "direct_self_use_power",
        "bess_charge_power",
        "bess_discharge_power",
        "grid_import_power",
        "grid_export_power",
        "curtail_power",
        "soc_start",
        "soc_end",
        "bess_energy_start",
        "bess_energy_end",
        "hour_case",
    }

    assert core_fields.issubset(result.hourly_detail.columns)
    assert list(result.hourly_detail.columns) == HOURLY_LEDGER_COLUMNS


def test_hourly_ledger_row_count_matches_input_hours():
    result = _run([10, 20, 30, 40], [0, 5, 40, 10])

    assert len(result.hourly_detail) == 4


def test_hourly_ledger_shape_stays_compatible_with_dispatch_strategy():
    default_result = _run([10, 20], [30, 0])
    explicit_result = run_single_scenario(
        _curves([10, 20], [30, 0]),
        Scenario("S001", pv_capacity=1, wind_capacity=0, bess_power=0, bess_energy=0),
        strategy=DispatchStrategy.GRID_CONNECTED_RENEWABLE_FIRST_GREEDY,
    )

    assert list(default_result.hourly_detail.columns) == list(explicit_result.hourly_detail.columns)
    assert list(explicit_result.hourly_detail.columns) == HOURLY_LEDGER_COLUMNS


def test_single_scenario_result_records_input_diagnostics():
    result = _run([10], [0])
    codes = {item.code for item in result.diagnostics.items}

    assert "DISPATCH_STRATEGY_SELECTED" in codes
    assert not result.diagnostics.has_errors()


def test_collect_input_diagnostics_detects_invalid_soc_without_running():
    diagnostics = collect_single_scenario_input_diagnostics(
        _curves([10], [0]),
        Scenario("S001", pv_capacity=1, wind_capacity=0, bess_power=0, bess_energy=0),
        BessParams(soc_initial=0.5, soc_min=0.8, soc_max=0.9),
        PolicyParams(),
        dt_hours=1,
        strategy=DispatchStrategy.GRID_CONNECTED_RENEWABLE_FIRST_GREEDY,
    )

    errors = [item for item in diagnostics.items if item.severity is DiagnosticSeverity.ERROR]
    assert [item.code for item in errors] == ["INVALID_SOC_PARAMETERS"]


def test_collect_input_diagnostics_warns_for_policy_parameter_edges():
    diagnostics = collect_single_scenario_input_diagnostics(
        _curves([10], [0]),
        Scenario("S001", pv_capacity=1, wind_capacity=0, bess_power=0, bess_energy=0),
        BessParams(),
        PolicyParams(export_rate_max=1.2, grid_exchange_power_limit=-1, export_control_mode="unknown"),
        dt_hours=1,
        strategy=DispatchStrategy.GRID_CONNECTED_RENEWABLE_FIRST_GREEDY,
    )

    warning_codes = {item.code for item in diagnostics.items if item.severity is DiagnosticSeverity.WARNING}
    assert warning_codes == {
        "EXPORT_RATE_MAX_OUT_OF_NORMAL_RANGE",
        "NEGATIVE_GRID_EXCHANGE_POWER_LIMIT",
        "UNKNOWN_EXPORT_CONTROL_MODE",
    }


def test_v02_golden_grid_connected_dispatch_regression():
    result = run_single_scenario(
        _curves([10, 10, 10, 10], [20, 0, 15, 5]),
        Scenario("S_GOLDEN", pv_capacity=1, wind_capacity=0, bess_power=5, bess_energy=10),
        bess_params=BessParams(
            soc_initial=0.5,
            soc_min=0.1,
            soc_max=0.9,
            eta_charge=1.0,
            eta_discharge=1.0,
        ),
        policy_params=PolicyParams(allow_export=True, export_control_mode="post_check"),
    )
    hourly = result.hourly_detail
    summary = result.summary

    assert summary["dispatch_strategy"] == DispatchStrategy.GRID_CONNECTED_RENEWABLE_FIRST_GREEDY.value
    assert len(hourly) == 4
    assert list(hourly.columns) == HOURLY_LEDGER_COLUMNS
    assert hourly["soc_start"].between(0.1, 0.9).all()
    assert hourly["soc_end"].between(0.1, 0.9).all()

    assert hourly["direct_self_use_power"].tolist() == pytest.approx([10, 0, 10, 5])
    assert hourly["bess_charge_power"].tolist() == pytest.approx([4, 0, 5, 0])
    assert hourly["bess_discharge_power"].tolist() == pytest.approx([0, 5, 0, 5])
    assert hourly["grid_import_power"].tolist() == pytest.approx([0, 5, 0, 0])
    assert hourly["grid_export_power"].tolist() == pytest.approx([6, 0, 0, 0])
    assert hourly["curtail_power"].tolist() == pytest.approx([0, 0, 0, 0])
    assert hourly["soc_end"].tolist() == pytest.approx([0.9, 0.4, 0.9, 0.4])

    expected_summary = {
        "total_load_energy": 40,
        "total_renewable_generation": 40,
        "direct_self_use_energy": 25,
        "bess_charge_energy": 9,
        "bess_discharge_to_load": 10,
        "self_use_energy": 35,
        "grid_import_energy": 5,
        "grid_export_energy": 6,
        "curtail_energy": 0,
        "bess_loss_energy": 0,
        "self_use_rate": 0.875,
        "green_load_rate": 0.875,
        "export_rate": 0.15,
        "curtail_rate": 0,
        "annual_equivalent_cycles": 1,
        "final_soc": 0.4,
    }
    for key, expected in expected_summary.items():
        assert summary[key] == pytest.approx(expected)

    for key in [
        "scenario_id",
        "pv_capacity",
        "wind_capacity",
        "bess_power",
        "bess_energy",
        "pass_policy",
        "fail_reasons",
        "dispatch_strategy",
    ]:
        assert key in summary
    assert summary["pass_policy"] is True
    assert summary["fail_reasons"] == ""

    assert result.diagnostics.items
    assert not result.diagnostics.has_errors()
    assert {item.code for item in result.diagnostics.items} >= {"DISPATCH_STRATEGY_SELECTED"}
