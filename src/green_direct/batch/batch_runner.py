"""Batch scenario runner."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd

from green_direct.batch.scenario_generator import generate_scenarios
from green_direct.core.single_scenario_simulator import run_single_scenario
from green_direct.models.params import BessParams, PerformanceParams, PolicyParams
from green_direct.models.results import ScenarioResult
from green_direct.models.scenario import Scenario


@dataclass
class BatchResult:
    summary: pd.DataFrame
    hourly_details: dict[str, pd.DataFrame]
    errors: pd.DataFrame
    warnings: list[str]
    scenario_count: int


def estimate_scenario_count(raw_grid: dict) -> int:
    return len(generate_scenarios(raw_grid))


def run_batch(
    curves: pd.DataFrame,
    scenario_grid: dict,
    *,
    bess_params: BessParams | None = None,
    policy_params: PolicyParams | None = None,
    performance_params: PerformanceParams | None = None,
    dt_hours: float = 1.0,
    progress_callback: Callable[[int, int, Scenario], None] | None = None,
) -> BatchResult:
    scenarios = generate_scenarios(scenario_grid)
    performance = performance_params or PerformanceParams()
    warnings: list[str] = []
    if len(scenarios) > performance.warn_if_scenarios_exceed:
        warnings.append(
            f"本次配置将生成 {len(scenarios)} 个方案，可能计算较慢，建议增大步长或缩小范围。"
        )

    summaries: list[dict] = []
    hourly_details: dict[str, pd.DataFrame] = {}
    errors: list[dict] = []
    total = len(scenarios)
    for index, scenario in enumerate(scenarios, start=1):
        try:
            result: ScenarioResult = run_single_scenario(
                curves,
                scenario,
                bess_params=bess_params,
                policy_params=policy_params,
                dt_hours=dt_hours,
            )
            summaries.append(result.summary)
            hourly_details[scenario.scenario_id] = result.hourly_detail
            warnings.extend(result.warnings)
        except Exception as exc:  # noqa: BLE001 - per-scenario failure must be recorded
            errors.append(
                {
                    "scenario_id": scenario.scenario_id,
                    "pv_capacity": scenario.pv_capacity,
                    "wind_capacity": scenario.wind_capacity,
                    "bess_power": scenario.bess_power,
                    "bess_energy": scenario.bess_energy,
                    "error": str(exc),
                }
            )
        finally:
            if progress_callback is not None:
                progress_callback(index, total, scenario)

    summary = pd.DataFrame(summaries)
    if not summary.empty and "pass_policy" in summary.columns:
        summary = summary.sort_values(
            by=[
                "pass_policy",
                "green_load_rate",
                "self_use_rate",
                "export_rate",
                "curtail_rate",
                "bess_energy",
            ],
            ascending=[False, False, False, True, True, True],
        ).reset_index(drop=True)
    return BatchResult(
        summary=summary,
        hourly_details=hourly_details,
        errors=pd.DataFrame(errors),
        warnings=warnings,
        scenario_count=len(scenarios),
    )
