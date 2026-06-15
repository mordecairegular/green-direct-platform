import pandas as pd

import green_direct.batch.batch_runner as batch_runner
from green_direct.batch.batch_runner import run_batch
from green_direct.batch.scenario_generator import RangeSpec, ScenarioGrid, generate_scenarios
from green_direct.models.params import PerformanceParams, PolicyParams


def _curves():
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2020-01-01", periods=2, freq="h"),
            "load_power": [10, 10],
            "pv_pu": [1, 0],
            "wind_pu": [0, 1],
        }
    )


def test_generate_scenarios_from_grid():
    grid = ScenarioGrid(
        pv_capacity=RangeSpec(0, 10, 10),
        wind_capacity=RangeSpec(0, 10, 10),
        bess_power=RangeSpec(0, 2, 2),
        bess_duration_hours=[0, 2],
    )

    scenarios = generate_scenarios(grid)

    assert len(scenarios) == 6
    assert all(scenario.pv_capacity > 0 or scenario.wind_capacity > 0 for scenario in scenarios)
    assert scenarios[0].pv_capacity == 0
    assert scenarios[0].wind_capacity == 10
    assert scenarios[0].bess_energy == 0
    assert scenarios[-1].bess_energy == 4


def test_batch_runner_collects_summary_and_hourly_details():
    grid = {
        "pv_capacity": {"start": 0, "end": 1, "step": 1},
        "wind_capacity": {"start": 0, "end": 1, "step": 1},
        "bess_power": {"start": 0, "end": 1, "step": 1},
        "bess_duration_hours": [0, 2],
    }

    result = run_batch(_curves(), grid, policy_params=PolicyParams(allow_export=False))

    assert result.scenario_count == 6
    assert len(result.summary) == 6
    assert not result.errors.shape[0]
    assert set(result.hourly_details) == set(result.summary["scenario_id"])


def test_batch_runner_can_skip_hourly_detail_retention():
    grid = {
        "pv_capacity": {"start": 0, "end": 1, "step": 1},
        "wind_capacity": {"start": 0, "end": 1, "step": 1},
        "bess_power": {"start": 0, "end": 1, "step": 1},
        "bess_duration_hours": [0, 2],
    }

    result = run_batch(
        _curves(),
        grid,
        policy_params=PolicyParams(allow_export=False),
        retain_hourly_details=False,
    )

    assert result.scenario_count == 6
    assert len(result.summary) == 6
    assert result.hourly_details == {}
    assert any("仅保留方案汇总" in warning for warning in result.warnings)


def test_batch_runner_can_keep_selected_hourly_details_only():
    grid = {
        "pv_capacity": {"start": 0, "end": 1, "step": 1},
        "wind_capacity": {"start": 0, "end": 1, "step": 1},
        "bess_power": {"start": 0, "end": 1, "step": 1},
        "bess_duration_hours": [0, 2],
    }

    result = run_batch(
        _curves(),
        grid,
        policy_params=PolicyParams(allow_export=False),
        retain_hourly_details=False,
        hourly_detail_scenario_ids=["S0003"],
    )

    assert set(result.hourly_details) == {"S0003"}


def test_batch_runner_uses_summary_only_mode_for_non_retained_details(monkeypatch):
    grid = {
        "pv_capacity": {"start": 0, "end": 1, "step": 1},
        "wind_capacity": {"start": 0, "end": 1, "step": 1},
        "bess_power": {"start": 0, "end": 1, "step": 1},
        "bess_duration_hours": [0, 2],
    }
    calls: list[tuple[str, bool]] = []
    original = batch_runner.run_single_scenario

    def wrapped_run_single_scenario(curves, scenario, **kwargs):
        calls.append((scenario.scenario_id, bool(kwargs.get("retain_hourly_detail", True))))
        return original(curves, scenario, **kwargs)

    monkeypatch.setattr(batch_runner, "run_single_scenario", wrapped_run_single_scenario)

    result = batch_runner.run_batch(
        _curves(),
        grid,
        policy_params=PolicyParams(allow_export=False),
        retain_hourly_details=False,
        hourly_detail_scenario_ids=["S0003"],
    )

    assert set(result.hourly_details) == {"S0003"}
    assert calls == [
        ("S0001", False),
        ("S0002", False),
        ("S0003", True),
        ("S0004", False),
        ("S0005", False),
        ("S0006", False),
    ]


def test_batch_runner_warns_when_scenario_count_exceeds_threshold():
    grid = {
        "pv_capacity": {"start": 0, "end": 1, "step": 1},
        "wind_capacity": {"start": 0, "end": 1, "step": 1},
        "bess_power": {"start": 0, "end": 0, "step": 1},
        "bess_duration_hours": [0],
    }

    result = run_batch(_curves(), grid, performance_params=PerformanceParams(warn_if_scenarios_exceed=1))

    assert result.warnings


def test_batch_runner_reports_progress():
    grid = {
        "pv_capacity": {"start": 0, "end": 1, "step": 1},
        "wind_capacity": {"start": 0, "end": 0, "step": 1},
        "bess_power": {"start": 0, "end": 0, "step": 1},
        "bess_duration_hours": [0],
    }
    calls = []

    run_batch(_curves(), grid, progress_callback=lambda done, total, scenario: calls.append((done, total, scenario.scenario_id)))

    assert calls == [(1, 1, "S0001")]


def test_batch_runner_parallel_matches_sequential_results():
    grid = {
        "pv_capacity": {"start": 0, "end": 1, "step": 1},
        "wind_capacity": {"start": 0, "end": 1, "step": 1},
        "bess_power": {"start": 0, "end": 1, "step": 1},
        "bess_duration_hours": [0, 2],
    }
    sequential = run_batch(
        _curves(),
        grid,
        policy_params=PolicyParams(allow_export=False),
        performance_params=PerformanceParams(parallel_workers=1),
    )
    calls = []
    parallel = run_batch(
        _curves(),
        grid,
        policy_params=PolicyParams(allow_export=False),
        performance_params=PerformanceParams(parallel_workers=2),
        progress_callback=lambda done, total, scenario: calls.append((done, total, scenario.scenario_id)),
    )

    pd.testing.assert_frame_equal(parallel.summary, sequential.summary)
    assert set(parallel.hourly_details) == set(sequential.hourly_details)
    for scenario_id, sequential_hourly in sequential.hourly_details.items():
        pd.testing.assert_frame_equal(parallel.hourly_details[scenario_id], sequential_hourly)
    assert parallel.errors.equals(sequential.errors)
    assert calls == [
        (index, sequential.scenario_count, scenario_id)
        for index, scenario_id in enumerate(["S0001", "S0002", "S0003", "S0004", "S0005", "S0006"], start=1)
    ]
