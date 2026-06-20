"""Batch scenario runner."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from typing import Callable, Iterable, TypeVar

import pandas as pd

from green_direct.batch.scenario_generator import count_scenarios, iter_scenarios
from green_direct.core.single_scenario_simulator import PreparedCurveData, prepare_curve_data, run_single_scenario
from green_direct.models.params import BessParams, PerformanceParams, PolicyParams
from green_direct.models.results import ScenarioResult
from green_direct.models.scenario import Scenario

_T = TypeVar("_T")


@dataclass
class BatchResult:
    summary: pd.DataFrame
    hourly_details: dict[str, pd.DataFrame]
    errors: pd.DataFrame
    warnings: list[str]
    scenario_count: int


@dataclass
class _ScenarioRunRecord:
    scenario: Scenario
    summary: dict | None
    hourly_detail: pd.DataFrame | None
    warnings: list[str]
    error: str | None


_WORKER_CURVES: pd.DataFrame | None = None
_WORKER_PREPARED_CURVES: PreparedCurveData | None = None
_WORKER_BESS_PARAMS: BessParams | None = None
_WORKER_POLICY_PARAMS: PolicyParams | None = None
_WORKER_DT_HOURS: float = 1.0
_WORKER_RETAIN_HOURLY_DETAILS: bool = True
_WORKER_RETAINED_HOURLY_IDS: set[str] = set()


def estimate_scenario_count(raw_grid: dict) -> int:
    return count_scenarios(raw_grid)


def _error_record(scenario: Scenario, exc: Exception) -> _ScenarioRunRecord:
    return _ScenarioRunRecord(
        scenario=scenario,
        summary=None,
        hourly_detail=None,
        warnings=[],
        error=str(exc),
    )


def _scenario_run_record(
    curves: pd.DataFrame,
    scenario: Scenario,
    *,
    prepared_curves: PreparedCurveData | None = None,
    bess_params: BessParams | None,
    policy_params: PolicyParams | None,
    dt_hours: float,
    retain_hourly_detail: bool,
    collect_diagnostics: bool,
) -> _ScenarioRunRecord:
    try:
        result: ScenarioResult = run_single_scenario(
            curves,
            scenario,
            bess_params=bess_params,
            policy_params=policy_params,
            dt_hours=dt_hours,
            retain_hourly_detail=retain_hourly_detail,
            collect_diagnostics=collect_diagnostics,
            _share_empty_hourly_detail=not retain_hourly_detail,
            _prepared_curves=prepared_curves,
        )
    except Exception as exc:  # noqa: BLE001 - per-scenario failure must be recorded
        return _error_record(scenario, exc)
    return _ScenarioRunRecord(
        scenario=scenario,
        summary=result.summary,
        hourly_detail=result.hourly_detail if retain_hourly_detail else None,
        warnings=result.warnings,
        error=None,
    )


def _init_parallel_worker(
    curves: pd.DataFrame,
    prepared_curves: PreparedCurveData,
    bess_params: BessParams | None,
    policy_params: PolicyParams | None,
    dt_hours: float,
    retain_hourly_details: bool,
    retained_hourly_ids: set[str],
) -> None:
    global _WORKER_CURVES, _WORKER_PREPARED_CURVES, _WORKER_BESS_PARAMS, _WORKER_POLICY_PARAMS, _WORKER_DT_HOURS
    global _WORKER_RETAIN_HOURLY_DETAILS, _WORKER_RETAINED_HOURLY_IDS
    _WORKER_CURVES = curves
    _WORKER_PREPARED_CURVES = prepared_curves
    _WORKER_BESS_PARAMS = bess_params
    _WORKER_POLICY_PARAMS = policy_params
    _WORKER_DT_HOURS = dt_hours
    _WORKER_RETAIN_HOURLY_DETAILS = retain_hourly_details
    _WORKER_RETAINED_HOURLY_IDS = retained_hourly_ids


def _scenario_run_record_from_worker(scenario: Scenario) -> _ScenarioRunRecord:
    if _WORKER_CURVES is None:
        return _error_record(scenario, RuntimeError("Batch worker was not initialised with curve data."))
    return _scenario_run_record(
        _WORKER_CURVES,
        scenario,
        prepared_curves=_WORKER_PREPARED_CURVES,
        bess_params=_WORKER_BESS_PARAMS,
        policy_params=_WORKER_POLICY_PARAMS,
        dt_hours=_WORKER_DT_HOURS,
        retain_hourly_detail=(
            _WORKER_RETAIN_HOURLY_DETAILS or scenario.scenario_id in _WORKER_RETAINED_HOURLY_IDS
        ),
        collect_diagnostics=False,
    )


def _parallel_chunk_size(scenario_count: int, parallel_workers: int) -> int:
    if scenario_count <= 0:
        return 1
    worker_count = max(1, int(parallel_workers))
    if scenario_count <= worker_count * 4:
        return 1
    # Keep enough chunks for load balancing while avoiding one process-pool task per scenario.
    return min(32, max(1, (scenario_count + worker_count * 8 - 1) // (worker_count * 8)))


def _scenario_chunks(items: Iterable[_T], chunk_size: int) -> Iterable[list[_T]]:
    safe_chunk_size = max(1, int(chunk_size))
    chunk: list[_T] = []
    for item in items:
        chunk.append(item)
        if len(chunk) >= safe_chunk_size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def _scenario_chunk_records_from_worker(scenarios: list[Scenario]) -> list[_ScenarioRunRecord]:
    return [_scenario_run_record_from_worker(scenario) for scenario in scenarios]


def _scenario_records(
    curves: pd.DataFrame,
    scenarios: Iterable[Scenario],
    *,
    scenario_count: int,
    bess_params: BessParams | None,
    policy_params: PolicyParams | None,
    dt_hours: float,
    parallel_workers: int,
    retain_hourly_details: bool,
    retained_hourly_ids: set[str],
) -> Iterable[_ScenarioRunRecord]:
    prepared_curves = prepare_curve_data(curves)
    if parallel_workers <= 1 or scenario_count <= 1:
        for scenario in scenarios:
            yield _scenario_run_record(
                curves,
                scenario,
                prepared_curves=prepared_curves,
                bess_params=bess_params,
                policy_params=policy_params,
                dt_hours=dt_hours,
                retain_hourly_detail=retain_hourly_details or scenario.scenario_id in retained_hourly_ids,
                collect_diagnostics=False,
            )
        return

    with ProcessPoolExecutor(
        max_workers=parallel_workers,
        initializer=_init_parallel_worker,
        initargs=(
            curves,
            prepared_curves,
            bess_params,
            policy_params,
            dt_hours,
            retain_hourly_details,
            retained_hourly_ids,
        ),
    ) as executor:
        chunks = _scenario_chunks(scenarios, _parallel_chunk_size(scenario_count, parallel_workers))
        for records in executor.map(_scenario_chunk_records_from_worker, chunks):
            yield from records


def run_batch(
    curves: pd.DataFrame,
    scenario_grid: dict,
    *,
    bess_params: BessParams | None = None,
    policy_params: PolicyParams | None = None,
    performance_params: PerformanceParams | None = None,
    dt_hours: float = 1.0,
    retain_hourly_details: bool = True,
    hourly_detail_scenario_ids: Iterable[str] | None = None,
    progress_callback: Callable[[int, int, Scenario], None] | None = None,
) -> BatchResult:
    performance = performance_params or PerformanceParams()
    estimated_scenario_count = estimate_scenario_count(scenario_grid)
    max_scenarios = performance.max_scenarios_per_run
    if max_scenarios is not None and int(max_scenarios) > 0 and estimated_scenario_count > int(max_scenarios):
        raise ValueError(
            f"本次配置将生成 {estimated_scenario_count} 个方案，超过单次测算上限 {int(max_scenarios)} 个。"
            "请增大步长、缩小容量范围或改用指定单方案。"
        )
    parallel_workers = max(1, int(performance.parallel_workers or 1))
    retained_hourly_ids = {str(scenario_id) for scenario_id in hourly_detail_scenario_ids or []}
    warnings: list[str] = []
    if estimated_scenario_count > performance.warn_if_scenarios_exceed:
        warnings.append(
            f"本次配置将生成 {estimated_scenario_count} 个方案，可能计算较慢，建议增大步长或缩小范围。"
        )
    if not retain_hourly_details and not retained_hourly_ids:
        warnings.append("本次批量测算仅保留方案汇总，未常驻保存逐小时明细；如需制图或导出，请对代表方案按需生成明细。")
    elif not retain_hourly_details:
        warnings.append(
            f"本次批量测算采用汇总优先模式，仅为 {len(retained_hourly_ids)} 个指定方案生成逐小时明细；"
            "其余方案只计算汇总指标。"
        )

    summaries: list[dict] = []
    hourly_details: dict[str, pd.DataFrame] = {}
    errors: list[dict] = []
    total = estimated_scenario_count
    scenarios = iter_scenarios(scenario_grid)
    for index, record in enumerate(
        _scenario_records(
            curves,
            scenarios,
            scenario_count=estimated_scenario_count,
            bess_params=bess_params,
            policy_params=policy_params,
            dt_hours=dt_hours,
            parallel_workers=parallel_workers,
            retain_hourly_details=retain_hourly_details,
            retained_hourly_ids=retained_hourly_ids,
        ),
        start=1,
    ):
        scenario = record.scenario
        if record.error is None and record.summary is not None:
            summaries.append(record.summary)
            if record.hourly_detail is not None and (
                retain_hourly_details or scenario.scenario_id in retained_hourly_ids
            ):
                hourly_details[scenario.scenario_id] = record.hourly_detail
            warnings.extend(record.warnings)
        else:
            errors.append(
                {
                    "scenario_id": scenario.scenario_id,
                    "pv_capacity": scenario.pv_capacity,
                    "wind_capacity": scenario.wind_capacity,
                    "bess_power": scenario.bess_power,
                    "bess_energy": scenario.bess_energy,
                    "error": record.error,
                }
            )
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
        scenario_count=estimated_scenario_count,
    )
