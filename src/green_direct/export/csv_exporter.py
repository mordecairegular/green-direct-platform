"""CSV and ZIP result export."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd

from green_direct.core.single_scenario_simulator import HOURLY_COLUMNS
from green_direct.export.excel_exporter import timestamp_suffix


def align_hourly_columns(hourly: pd.DataFrame) -> pd.DataFrame:
    result = hourly.copy()
    for column in HOURLY_COLUMNS:
        if column not in result.columns:
            result[column] = pd.NA
    return result[HOURLY_COLUMNS]


def export_hourly_detail_csv(
    hourly: pd.DataFrame,
    output_dir: str | Path,
    *,
    scenario_id: str | None = None,
    now: datetime | None = None,
) -> Path:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    sid = scenario_id or str(hourly["scenario_id"].iloc[0])
    file_path = output_path / f"hourly_detail_{sid}_{timestamp_suffix(now)}.csv"
    align_hourly_columns(hourly).to_csv(file_path, index=False, encoding="utf-8-sig")
    return file_path


def export_hourly_details_zip(
    hourly_details: dict[str, pd.DataFrame],
    output_dir: str | Path,
    *,
    now: datetime | None = None,
) -> Path:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    file_path = output_path / f"hourly_details_{timestamp_suffix(now)}.zip"
    with ZipFile(file_path, mode="w", compression=ZIP_DEFLATED) as archive:
        for scenario_id, hourly in hourly_details.items():
            content = align_hourly_columns(hourly).to_csv(index=False).encode("utf-8-sig")
            archive.writestr(f"hourly_detail_{scenario_id}.csv", content)
    return file_path


def export_config_snapshot(
    config_snapshot: dict,
    output_dir: str | Path,
    *,
    now: datetime | None = None,
) -> Path:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    file_path = output_path / f"config_snapshot_{timestamp_suffix(now)}.json"
    file_path.write_text(json.dumps(config_snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    return file_path
