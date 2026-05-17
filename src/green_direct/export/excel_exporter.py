"""Excel result export."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

SUMMARY_COLUMNS = [
    "scenario_id",
    "pv_capacity",
    "wind_capacity",
    "bess_power",
    "bess_energy",
    "bess_duration",
    "bess_c_rate",
    "total_load_energy",
    "total_renewable_generation",
    "pv_station_use_energy",
    "wind_station_use_energy",
    "station_use_energy",
    "direct_self_use_energy",
    "bess_discharge_to_load",
    "self_use_energy",
    "grid_import_energy",
    "grid_import_rate",
    "grid_export_energy",
    "export_cap_energy",
    "curtail_energy",
    "curtail_due_to_export_cap_energy",
    "curtail_due_to_exchange_limit_energy",
    "exchange_import_shortfall_energy",
    "bess_charge_energy",
    "bess_loss_energy",
    "self_use_rate",
    "green_load_rate",
    "export_rate",
    "curtail_rate",
    "annual_equivalent_cycles",
    "replacement_year",
    "max_grid_import_power",
    "max_grid_export_power",
    "grid_exchange_power_limit",
    "final_soc",
    "export_control_mode",
    "pass_policy",
    "fail_reasons",
]


def timestamp_suffix(now: datetime | None = None) -> str:
    return (now or datetime.now()).strftime("%Y%m%d_%H%M%S")


def align_summary_columns(summary: pd.DataFrame) -> pd.DataFrame:
    result = summary.copy()
    for column in SUMMARY_COLUMNS:
        if column not in result.columns:
            result[column] = pd.NA
    return result[SUMMARY_COLUMNS]


def _config_to_frame(config: dict[str, Any] | None) -> pd.DataFrame:
    if not config:
        return pd.DataFrame(columns=["key", "value"])
    rows: list[dict[str, Any]] = []

    def walk(prefix: str, value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                walk(f"{prefix}.{key}" if prefix else str(key), child)
        else:
            rows.append({"key": prefix, "value": value})

    walk("", config)
    return pd.DataFrame(rows)


def export_summary_excel(
    summary: pd.DataFrame,
    output_dir: str | Path,
    *,
    config_snapshot: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    filename_prefix: str = "scenario_summary",
    now: datetime | None = None,
) -> Path:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    file_path = output_path / f"{filename_prefix}_{timestamp_suffix(now)}.xlsx"

    aligned = align_summary_columns(summary)
    passed = aligned[aligned["pass_policy"] == True] if not aligned.empty else aligned.copy()  # noqa: E712
    failed = aligned[aligned["pass_policy"] == False] if not aligned.empty else aligned.copy()  # noqa: E712
    top_green = aligned.sort_values("green_load_rate", ascending=False).head(50) if not aligned.empty else aligned
    top_low_curtail = aligned.sort_values("curtail_rate", ascending=True).head(50) if not aligned.empty else aligned
    warnings_df = pd.DataFrame({"warning": warnings or []})

    with pd.ExcelWriter(file_path, engine="xlsxwriter") as writer:
        aligned.to_excel(writer, sheet_name="Summary", index=False)
        passed.to_excel(writer, sheet_name="Policy_Passed", index=False)
        failed.to_excel(writer, sheet_name="Policy_Failed", index=False)
        top_green.to_excel(writer, sheet_name="Top_By_Green_Load_Rate", index=False)
        top_low_curtail.to_excel(writer, sheet_name="Top_By_Low_Curtail_Rate", index=False)
        _config_to_frame(config_snapshot).to_excel(writer, sheet_name="Config", index=False)
        warnings_df.to_excel(writer, sheet_name="Warnings", index=False)
    return file_path
