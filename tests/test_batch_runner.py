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


def test_estimate_scenario_count_uses_count_only_path(monkeypatch):
    grid = {
        "pv_capacity": {"start": 0, "end": 1, "step": 1},
        "wind_capacity": {"start": 0, "end": 1, "step": 1},
        "bess_power": {"start": 0, "end": 1, "step": 1},
        "bess_duration_hours": [0, 2],
    }

    def fail_generate_scenarios(raw_grid):
        raise AssertionError("estimate_scenario_count should not materialise scenarios")

    monkeypatch.setattr(batch_runner, "generate_scenarios", fail_generate_scenarios)

    assert batch_runner.estimate_scenario_count(grid) == 6


def test_estimate_scenario_count_matches_generated_scenarios():
    grid = {
        "pv_capacity": {"start": 0, "end": 2, "step": 1},
        "wind_capacity": {"start": 0, "end": 1, "step": 1},
        "bess_power": {"start": 0, "end": 2, "step": 1},
        "bess_duration_hours": [0, 1.5, 2],
    }

    assert batch_runner.estimate_scenario_count(grid) == len(generate_scenarios(grid))


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
    calls: list[tuple[str, bool, bool]] = []
    original = batch_runner.run_single_scenario

    def wrapped_run_single_scenario(curves, scenario, **kwargs):
        calls.append(
            (
                scenario.scenario_id,
                bool(kwargs.get("retain_hourly_detail", True)),
                bool(kwargs.get("collect_diagnostics", True)),
            )
        )
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
        ("S0001", False, False),
        ("S0002", False, False),
        ("S0003", True, False),
        ("S0004", False, False),
        ("S0005", False, False),
        ("S0006", False, False),
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


def test_batch_runner_rejects_scenario_count_above_hard_limit():
    grid = {
        "pv_capacity": {"start": 0, "end": 1, "step": 1},
        "wind_capacity": {"start": 0, "end": 1, "step": 1},
        "bess_power": {"start": 0, "end": 1, "step": 1},
        "bess_duration_hours": [0, 2],
    }

    try:
        run_batch(_curves(), grid, performance_params=PerformanceParams(max_scenarios_per_run=5))
    except ValueError as exc:
        assert "超过单次测算上限" in str(exc)
    else:
        raise AssertionError("Expected run_batch to reject a scenario pool above the hard limit.")


def test_batch_runner_rejects_above_hard_limit_before_materialising_scenarios(monkeypatch):
    grid = {
        "pv_capacity": {"start": 0, "end": 1, "step": 1},
        "wind_capacity": {"start": 0, "end": 1, "step": 1},
        "bess_power": {"start": 0, "end": 1, "step": 1},
        "bess_duration_hours": [0, 2],
    }

    def fail_generate_scenarios(raw_grid):
        raise AssertionError("run_batch should reject oversized pools before generating scenarios")

    monkeypatch.setattr(batch_runner, "generate_scenarios", fail_generate_scenarios)

    try:
        run_batch(_curves(), grid, performance_params=PerformanceParams(max_scenarios_per_run=5))
    except ValueError as exc:
        assert "超过单次测算上限" in str(exc)
    else:
        raise AssertionError("Expected run_batch to reject a scenario pool above the hard limit.")


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


def test_parallel_chunk_size_reduces_large_process_pool_task_count():
    assert batch_runner._parallel_chunk_size(6, 2) == 1
    chunk_size = batch_runner._parallel_chunk_size(1000, 4)
    assert chunk_size > 1
    assert chunk_size <= 32
    chunks = list(batch_runner._scenario_chunks(list(range(10)), 3))
    assert chunks == [[0, 1, 2], [3, 4, 5], [6, 7, 8], [9]]


def test_batch_runner_parallel_submits_scenario_chunks(monkeypatch):
    grid = {
        "pv_capacity": {"start": 0, "end": 4, "step": 1},
        "wind_capacity": {"start": 0, "end": 2, "step": 1},
        "bess_power": {"start": 0, "end": 1, "step": 1},
        "bess_duration_hours": [0, 2],
    }
    submitted_chunk_sizes: list[int] = []
    expected_scenario_count = len(generate_scenarios(grid))

    class FakeProcessPoolExecutor:
        def __init__(self, *, max_workers, initializer, initargs):
            self.max_workers = max_workers
            initializer(*initargs)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def map(self, func, iterable):
            chunks = list(iterable)
            submitted_chunk_sizes.extend(len(chunk) for chunk in chunks)
            for chunk in chunks:
                yield func(chunk)

    monkeypatch.setattr(batch_runner, "ProcessPoolExecutor", FakeProcessPoolExecutor)

    result = batch_runner.run_batch(
        _curves(),
        grid,
        policy_params=PolicyParams(allow_export=False),
        performance_params=PerformanceParams(parallel_workers=2),
        retain_hourly_details=False,
    )

    assert result.scenario_count == expected_scenario_count
    assert sum(submitted_chunk_sizes) == expected_scenario_count
    assert max(submitted_chunk_sizes) > 1
    assert result.hourly_details == {}
