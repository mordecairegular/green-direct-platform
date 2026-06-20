"""Standalone batch-trial runner for low-friction Windows packaging."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import yaml

from green_direct.batch.batch_runner import estimate_scenario_count, run_batch
from green_direct.export.csv_exporter import export_config_snapshot, export_hourly_details_zip
from green_direct.export.excel_exporter import export_summary_excel, timestamp_suffix
from green_direct.io.read_curves import read_curve_set
from green_direct.models.params import BessParams, DataCleaningParams, PerformanceParams, PolicyParams
from green_direct.models.scenario import Scenario


ProgressCallback = Callable[[int, int, str], None]


@dataclass(frozen=True)
class CurveColumnConfig:
    """Input CSV column names used by the standalone trial runner.

    When set to None, the reader auto-detects: first column = time,
    second column = value.
    """

    load_time_col: str | None = None
    load_value_col: str | None = None
    pv_time_col: str | None = None
    pv_value_col: str | None = None
    wind_time_col: str | None = None
    wind_value_col: str | None = None


@dataclass(frozen=True)
class BatchTrialRunConfig:
    """Configuration for one standalone batch trial run."""

    load_csv: Path
    pv_csv: Path
    wind_csv: Path
    output_dir: Path
    scenario_grid: dict[str, Any]
    columns: CurveColumnConfig = field(default_factory=CurveColumnConfig)
    bess_params: BessParams = field(default_factory=BessParams)
    policy_params: PolicyParams = field(default_factory=PolicyParams)
    warn_if_scenarios_exceed: int = 5000
    dt_hours: float = 1.0


@dataclass(frozen=True)
class BatchTrialArtifacts:
    """Files written by one standalone batch trial run."""

    run_dir: Path
    summary_excel: Path
    hourly_zip: Path
    config_snapshot: Path
    result_note: Path
    errors_csv: Path | None
    warnings_txt: Path | None
    scenario_count: int
    success_count: int
    error_count: int
    warning_count: int


def default_scenario_grid() -> dict[str, Any]:
    """Return the same small first-run grid used by the Streamlit UI."""

    return {
        "pv_capacity": {"start": 0, "end": 30, "step": 5},
        "wind_capacity": {"start": 0, "end": 30, "step": 5},
        "bess_power": {"start": 0, "end": 10, "step": 2},
        "bess_duration_hours": [0, 2, 4],
    }


def load_scenario_grid_file(path: str | Path) -> dict[str, Any]:
    """Load a scenario grid YAML file.

    The file may either be a raw grid mapping or use the documented
    ``scenario_grid:`` wrapper.
    """

    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict):
        raise ValueError("方案范围配置文件必须是 YAML 对象。")
    grid = raw.get("scenario_grid", raw)
    if not isinstance(grid, dict):
        raise ValueError("scenario_grid 必须是 YAML 对象。")
    return grid


def estimate_trial_scenario_count(scenario_grid: dict[str, Any]) -> int:
    """Estimate usable candidate count after generator filtering."""

    return estimate_scenario_count(scenario_grid)


def run_batch_trial(
    config: BatchTrialRunConfig,
    *,
    progress_callback: ProgressCallback | None = None,
    now: datetime | None = None,
) -> BatchTrialArtifacts:
    """Run a full standalone trial and export overview/detail files."""

    _validate_config(config)
    run_stamp = timestamp_suffix(now)
    run_dir = Path(config.output_dir) / f"batch_trial_{run_stamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    curve_set = read_curve_set(
        config.load_csv,
        config.pv_csv,
        config.wind_csv,
        load_time_col=config.columns.load_time_col,
        load_value_col=config.columns.load_value_col,
        pv_time_col=config.columns.pv_time_col,
        pv_value_col=config.columns.pv_value_col,
        wind_time_col=config.columns.wind_time_col,
        wind_value_col=config.columns.wind_value_col,
        cleaning=DataCleaningParams(),
    )

    def on_progress(done: int, total: int, scenario: Scenario) -> None:
        if progress_callback is not None:
            progress_callback(done, total, scenario.scenario_id)

    batch_result = run_batch(
        curve_set.data,
        config.scenario_grid,
        bess_params=config.bess_params,
        policy_params=config.policy_params,
        performance_params=PerformanceParams(warn_if_scenarios_exceed=config.warn_if_scenarios_exceed),
        dt_hours=config.dt_hours,
        progress_callback=on_progress,
    )

    snapshot = _build_config_snapshot(config, curve_set.encodings, curve_set.warnings)
    summary_excel = export_summary_excel(
        batch_result.summary,
        run_dir,
        config_snapshot=snapshot,
        warnings=batch_result.warnings,
        filename_prefix="方案概览",
        now=now,
    )
    hourly_zip = export_hourly_details_zip(batch_result.hourly_details, run_dir, now=now)
    hourly_zip = _rename_with_prefix(hourly_zip, "方案详表")
    config_snapshot = export_config_snapshot(snapshot, run_dir, now=now)
    config_snapshot = _rename_with_prefix(config_snapshot, "本次测算配置")

    errors_csv = None
    if not batch_result.errors.empty:
        errors_csv = run_dir / f"方案计算错误_{run_stamp}.csv"
        batch_result.errors.to_csv(errors_csv, index=False, encoding="utf-8-sig")

    warnings = [*curve_set.warnings, *batch_result.warnings]
    warnings_txt = None
    if warnings:
        warnings_txt = run_dir / f"警告提示_{run_stamp}.txt"
        warnings_txt.write_text("\n".join(warnings), encoding="utf-8")

    result_note = run_dir / "结果说明.txt"
    result_note.write_text(
        _format_result_note(
            summary_excel=summary_excel,
            hourly_zip=hourly_zip,
            config_snapshot=config_snapshot,
            errors_csv=errors_csv,
            warnings_txt=warnings_txt,
            scenario_count=batch_result.scenario_count,
            success_count=len(batch_result.summary),
            error_count=len(batch_result.errors),
            warning_count=len(warnings),
        ),
        encoding="utf-8",
    )

    return BatchTrialArtifacts(
        run_dir=run_dir,
        summary_excel=summary_excel,
        hourly_zip=hourly_zip,
        config_snapshot=config_snapshot,
        result_note=result_note,
        errors_csv=errors_csv,
        warnings_txt=warnings_txt,
        scenario_count=batch_result.scenario_count,
        success_count=len(batch_result.summary),
        error_count=len(batch_result.errors),
        warning_count=len(warnings),
    )


def _validate_config(config: BatchTrialRunConfig) -> None:
    missing = [
        path
        for path in [config.load_csv, config.pv_csv, config.wind_csv]
        if not Path(path).exists()
    ]
    if missing:
        names = ", ".join(str(path) for path in missing)
        raise FileNotFoundError(f"找不到输入文件：{names}")
    if config.warn_if_scenarios_exceed <= 0:
        raise ValueError("方案数提醒阈值必须大于 0。")
    if config.dt_hours <= 0:
        raise ValueError("dt_hours 必须大于 0。")


def _build_config_snapshot(
    config: BatchTrialRunConfig,
    encodings: dict[str, str],
    warnings: list[str],
) -> dict[str, Any]:
    return {
        "input_files": {
            "load_csv": str(Path(config.load_csv).resolve()),
            "pv_csv": str(Path(config.pv_csv).resolve()),
            "wind_csv": str(Path(config.wind_csv).resolve()),
        },
        "input_columns": asdict(config.columns),
        "scenario_grid": config.scenario_grid,
        "bess": asdict(config.bess_params),
        "policy": asdict(config.policy_params),
        "warn_if_scenarios_exceed": config.warn_if_scenarios_exceed,
        "dt_hours": config.dt_hours,
        "encodings": encodings,
        "curve_warnings": warnings,
    }


def _rename_with_prefix(path: Path, prefix: str) -> Path:
    if path.name.startswith(prefix):
        return path
    parts = path.stem.split("_")
    if len(parts) >= 2 and parts[-2].isdigit() and parts[-1].isdigit():
        suffix = f"{parts[-2]}_{parts[-1]}{path.suffix}"
    else:
        suffix = path.name
    target = path.with_name(f"{prefix}_{suffix}")
    if target.exists():
        target.unlink()
    path.replace(target)
    return target


def _format_result_note(
    *,
    summary_excel: Path,
    hourly_zip: Path,
    config_snapshot: Path,
    errors_csv: Path | None,
    warnings_txt: Path | None,
    scenario_count: int,
    success_count: int,
    error_count: int,
    warning_count: int,
) -> str:
    lines = [
        "绿电直连方案遍历试用程序结果说明",
        "",
        f"枚举方案数：{scenario_count}",
        f"成功方案数：{success_count}",
        f"失败方案数：{error_count}",
        f"警告数量：{warning_count}",
        "",
        "输出文件：",
        f"- 方案概览 Excel：{summary_excel.name}",
        f"- 方案详表 ZIP：{hourly_zip.name}",
        f"- 本次测算配置：{config_snapshot.name}",
    ]
    if errors_csv is not None:
        lines.append(f"- 方案计算错误：{errors_csv.name}")
    if warnings_txt is not None:
        lines.append(f"- 警告提示：{warnings_txt.name}")
    lines.extend(
        [
            "",
            "说明：",
            "- 方案概览 Excel 用于筛选和复核各容量组合的年度技术指标。",
            "- 方案详表 ZIP 中每个 CSV 对应一个 scenario_id 的逐小时明细。",
            "- 本试用程序只调用现有 V0.1 风光储技术仿真，不改变调度策略。",
        ]
    )
    return "\n".join(lines) + "\n"
