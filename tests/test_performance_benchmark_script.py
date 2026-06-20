import json
import subprocess
import sys
from pathlib import Path


def test_internal_pilot_performance_benchmark_runs_json():
    root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "benchmark_internal_pilot_performance.py"),
            "--hours",
            "24",
            "--pv-count",
            "2",
            "--wind-count",
            "2",
            "--bess-power-count",
            "1",
            "--durations",
            "0",
            "--retain-detail-count",
            "0",
            "--skip-full-retention",
            "--json",
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)

    assert payload["config"]["hours"] == 24
    assert payload["config"]["scenario_count"] == 3
    assert [record["case"] for record in payload["benchmarks"]] == [
        "technical_summary_first",
        "economy_summary_no_annual_cashflows",
    ]
    assert payload["benchmarks"][0]["stats"]["hourly_detail_count"] == 0


def test_internal_pilot_performance_benchmark_runs_economy_only_json():
    root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "benchmark_internal_pilot_performance.py"),
            "--economy-only-summary-rows",
            "12",
            "--json",
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)

    assert payload["config"]["scenario_count"] == 12
    assert payload["config"]["economy_only_summary_rows"] == 12
    assert [record["case"] for record in payload["benchmarks"]] == [
        "economy_summary_no_annual_cashflows",
    ]
    assert payload["benchmarks"][0]["stats"]["power_summary_rows"] == 12
    assert payload["benchmarks"][0]["stats"]["single_entity_summary_rows"] == 12


def test_internal_pilot_performance_benchmark_can_retain_selected_economy_cashflows():
    root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "benchmark_internal_pilot_performance.py"),
            "--economy-only-summary-rows",
            "12",
            "--economy-retain-cashflow-count",
            "3",
            "--json",
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)

    assert payload["config"]["economy_retain_cashflow_count"] == 3
    assert [record["case"] for record in payload["benchmarks"]] == [
        "economy_summary_with_selected_annual_cashflows",
    ]
    assert payload["benchmarks"][0]["stats"]["power_summary_rows"] == 12
    assert payload["benchmarks"][0]["stats"]["single_entity_summary_rows"] == 12
    assert payload["benchmarks"][0]["stats"]["power_cashflow_count"] == 3
    assert payload["benchmarks"][0]["stats"]["single_entity_cashflow_count"] == 3


def test_internal_pilot_performance_benchmark_retains_selected_cashflows_after_technical_run():
    root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "benchmark_internal_pilot_performance.py"),
            "--hours",
            "24",
            "--pv-count",
            "2",
            "--wind-count",
            "2",
            "--bess-power-count",
            "1",
            "--durations",
            "0",
            "--retain-detail-count",
            "0",
            "--skip-full-retention",
            "--economy-retain-cashflow-count",
            "2",
            "--json",
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)

    assert payload["config"]["scenario_count"] == 3
    assert payload["config"]["economy_retain_cashflow_count"] == 2
    assert [record["case"] for record in payload["benchmarks"]] == [
        "technical_summary_first",
        "economy_summary_with_selected_annual_cashflows",
    ]
    assert payload["benchmarks"][1]["stats"]["power_cashflow_count"] == 2
    assert payload["benchmarks"][1]["stats"]["single_entity_cashflow_count"] == 2


def test_internal_pilot_performance_benchmark_can_skip_tracemalloc():
    root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "benchmark_internal_pilot_performance.py"),
            "--economy-only-summary-rows",
            "12",
            "--no-tracemalloc",
            "--json",
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)

    assert payload["config"]["track_python_heap"] is False
    assert payload["benchmarks"][0]["track_python_heap"] is False
    assert payload["benchmarks"][0]["peak_python_heap_mb"] is None
