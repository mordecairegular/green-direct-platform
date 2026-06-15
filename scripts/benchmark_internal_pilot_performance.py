"""Benchmark technical and economy batch paths for internal pilot sizing.

This script is intentionally lightweight: it creates deterministic synthetic
8760-style curves, runs the current batch/economy APIs, and reports elapsed
time plus Python heap peak measured by tracemalloc. It is a decision aid, not a
pytest performance gate.
"""

from __future__ import annotations

import argparse
import gc
import json
import math
from pathlib import Path
import sys
import time
import tracemalloc
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pandas as pd

from green_direct.batch.batch_runner import BatchResult, run_batch
from green_direct.batch.scenario_generator import generate_scenarios
from green_direct.economy import AvoidedGridPurchaseParams, EconomicParams
from green_direct.models.params import PerformanceParams
from green_direct.services.study_runner import EconomicStudyResult, run_economic_study


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


def _nonnegative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be non-negative")
    return parsed


def _parse_durations(value: str) -> list[float]:
    durations = [float(item.strip()) for item in value.split(",") if item.strip()]
    if not durations:
        raise argparse.ArgumentTypeError("at least one duration is required")
    if any(duration < 0 for duration in durations):
        raise argparse.ArgumentTypeError("durations must be non-negative")
    return durations


def _synthetic_curves(hours: int) -> pd.DataFrame:
    timestamps = pd.date_range("2026-01-01", periods=hours, freq="h")
    load: list[float] = []
    pv: list[float] = []
    wind: list[float] = []
    for index in range(hours):
        hour = index % 24
        day = index / 24
        season = 0.5 + 0.5 * math.sin(2 * math.pi * day / 365)
        daily_load = 0.85 + 0.25 * math.sin(2 * math.pi * (hour - 8) / 24)
        load.append(12.0 * (1 + 0.12 * season) * daily_load)

        daylight = max(0.0, math.sin(math.pi * (hour - 6) / 12))
        pv.append(min(1.0, daylight * (0.65 + 0.35 * season)))

        wind_value = 0.42 + 0.18 * math.sin(2 * math.pi * index / 168) + 0.10 * math.cos(
            2 * math.pi * day / 365
        )
        wind.append(max(0.0, min(1.0, wind_value)))
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "load_power": load,
            "pv_pu": pv,
            "wind_pu": wind,
        }
    )


def _capacity_range(count: int) -> dict[str, float]:
    return {"start": 0.0, "end": float(count - 1), "step": 1.0}


def _scenario_grid(
    *,
    pv_count: int,
    wind_count: int,
    bess_power_count: int,
    durations: list[float],
) -> dict[str, Any]:
    return {
        "pv_capacity": _capacity_range(pv_count),
        "wind_capacity": _capacity_range(wind_count),
        "bess_power": _capacity_range(bess_power_count),
        "bess_duration_hours": durations,
    }


def _measure(name: str, func: Callable[[], Any]) -> tuple[Any, dict[str, Any]]:
    gc.collect()
    tracemalloc.start()
    started = time.perf_counter()
    result = func()
    seconds = time.perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return result, {
        "case": name,
        "seconds": round(seconds, 4),
        "peak_python_heap_mb": round(peak / (1024 * 1024), 3),
    }


def _batch_stats(result: BatchResult) -> dict[str, Any]:
    return {
        "scenario_count": int(result.scenario_count),
        "summary_rows": int(len(result.summary)),
        "hourly_detail_count": int(len(result.hourly_details)),
        "error_count": int(len(result.errors)),
        "warning_count": int(len(result.warnings)),
    }


def _economy_stats(result: EconomicStudyResult) -> dict[str, Any]:
    return {
        "power_summary_rows": int(len(result.power_summary)),
        "single_entity_summary_rows": int(len(result.single_entity_summary)),
        "power_cashflow_count": int(len(result.power_annual_cashflows)),
        "single_entity_cashflow_count": int(len(result.single_entity_annual_cashflows)),
    }


def _render_table(payload: dict[str, Any]) -> str:
    rows = [
        "| case | seconds | peak Python heap MB | key stats |",
        "|---|---:|---:|---|",
    ]
    for record in payload["benchmarks"]:
        stats = ", ".join(f"{key}={value}" for key, value in record["stats"].items())
        rows.append(
            f"| {record['case']} | {record['seconds']} | {record['peak_python_heap_mb']} | {stats} |"
        )
    return "\n".join(rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hours", type=_positive_int, default=8760)
    parser.add_argument("--pv-count", type=_positive_int, default=6)
    parser.add_argument("--wind-count", type=_positive_int, default=5)
    parser.add_argument("--bess-power-count", type=_positive_int, default=3)
    parser.add_argument("--durations", type=_parse_durations, default=_parse_durations("0,2"))
    parser.add_argument("--parallel-workers", type=_positive_int, default=1)
    parser.add_argument("--warn-threshold", type=_positive_int, default=5000)
    parser.add_argument("--retain-detail-count", type=_nonnegative_int, default=20)
    parser.add_argument("--skip-full-retention", action="store_true")
    parser.add_argument("--skip-economy", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    curves = _synthetic_curves(args.hours)
    grid = _scenario_grid(
        pv_count=args.pv_count,
        wind_count=args.wind_count,
        bess_power_count=args.bess_power_count,
        durations=args.durations,
    )
    scenarios = generate_scenarios(grid)
    retained_ids = tuple(scenario.scenario_id for scenario in scenarios[: args.retain_detail_count])
    performance = PerformanceParams(
        warn_if_scenarios_exceed=args.warn_threshold,
        parallel_workers=args.parallel_workers,
    )
    payload: dict[str, Any] = {
        "config": {
            "hours": args.hours,
            "scenario_count": len(scenarios),
            "parallel_workers": args.parallel_workers,
            "retain_detail_count": args.retain_detail_count,
            "durations": args.durations,
        },
        "benchmarks": [],
    }

    if not args.skip_full_retention:
        full_result, record = _measure(
            "technical_full_hourly_retention",
            lambda: run_batch(curves, grid, performance_params=performance, retain_hourly_details=True),
        )
        record["stats"] = _batch_stats(full_result)
        payload["benchmarks"].append(record)
        del full_result

    summary_result, record = _measure(
        "technical_summary_first",
        lambda: run_batch(
            curves,
            grid,
            performance_params=performance,
            retain_hourly_details=False,
            hourly_detail_scenario_ids=retained_ids,
        ),
    )
    record["stats"] = _batch_stats(summary_result)
    payload["benchmarks"].append(record)

    if not args.skip_economy:
        economy_result, record = _measure(
            "economy_summary_no_annual_cashflows",
            lambda: run_economic_study(
                summary_result.summary,
                economic_params=EconomicParams(),
                avoided_grid_params=AvoidedGridPurchaseParams(net_avoided_grid_cost_price=0.55),
                load_side_avoided_charge_price=0.55,
                green_power_settlement_price_with_vat=0.40,
                retain_annual_cashflows=False,
            ),
        )
        record["stats"] = _economy_stats(economy_result)
        payload["benchmarks"].append(record)

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("# Internal Pilot Performance Benchmark")
        print()
        print(json.dumps(payload["config"], ensure_ascii=False))
        print()
        print(_render_table(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
