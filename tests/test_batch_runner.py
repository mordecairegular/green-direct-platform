import pandas as pd

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

    assert len(scenarios) == 8
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

    assert result.scenario_count == 8
    assert len(result.summary) == 8
    assert not result.errors.shape[0]
    assert set(result.hourly_details) == set(result.summary["scenario_id"])


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

    assert calls == [(1, 2, "S0001"), (2, 2, "S0002")]
