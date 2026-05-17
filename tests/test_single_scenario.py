import pandas as pd
import pytest

from green_direct.core.single_scenario_simulator import run_single_scenario
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
