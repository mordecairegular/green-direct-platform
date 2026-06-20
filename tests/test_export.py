from datetime import datetime
from zipfile import ZipFile

import pandas as pd

from green_direct.export.csv_exporter import (
    export_config_snapshot,
    export_hourly_detail_csv,
    export_hourly_details_zip,
)
from green_direct.export.excel_exporter import SUMMARY_COLUMNS, export_summary_excel


def _summary():
    return pd.DataFrame(
        [
            {
                "scenario_id": "S0001",
                "pv_capacity": 1,
                "wind_capacity": 2,
                "bess_power": 0,
                "bess_energy": 0,
                "pass_policy": True,
                "green_load_rate": 0.5,
                "self_use_rate": 0.8,
                "export_rate": 0.1,
                "curtail_rate": 0.0,
            }
        ]
    )


def _hourly():
    return pd.DataFrame(
        [
            {
                "scenario_id": "S0001",
                "timestamp": "2020-01-01 00:00:00",
                "hour_index": 0,
                "load_power": 10,
                "pv_power": 1,
                "wind_power": 2,
                "renewable_power": 3,
                "direct_self_use_power": 3,
                "bess_charge_power": 0,
                "bess_discharge_power": 0,
                "grid_import_power": 7,
                "grid_export_power": 0,
                "curtail_power": 0,
                "soc_start": 0,
                "soc_end": 0,
                "bess_energy_start": 0,
                "bess_energy_end": 0,
                "hour_case": "GEN_SHORT_GRID_IMPORT",
            }
        ]
    )


def test_export_summary_excel(tmp_path):
    path = export_summary_excel(
        _summary(),
        tmp_path,
        config_snapshot={"a": {"b": 1}},
        warnings=["warn"],
        now=datetime(2026, 1, 2, 3, 4, 5),
    )

    assert path.exists()
    loaded = pd.read_excel(path, sheet_name="Summary")
    assert list(loaded.columns) == SUMMARY_COLUMNS


def test_export_summary_excel_keeps_extra_economy_columns(tmp_path):
    summary = _summary().assign(fnpv=1234.0, firr=0.08)
    path = export_summary_excel(summary, tmp_path, now=datetime(2026, 1, 2, 3, 4, 5))

    loaded = pd.read_excel(path, sheet_name="Summary")

    assert list(loaded.columns[: len(SUMMARY_COLUMNS)]) == SUMMARY_COLUMNS
    assert loaded["fnpv"].iloc[0] == 1234.0
    assert loaded["firr"].iloc[0] == 0.08


def test_export_hourly_detail_csv(tmp_path):
    path = export_hourly_detail_csv(_hourly(), tmp_path, now=datetime(2026, 1, 2, 3, 4, 5))

    assert path.exists()
    loaded = pd.read_csv(path)
    assert loaded["scenario_id"].iloc[0] == "S0001"


def test_export_hourly_details_zip(tmp_path):
    path = export_hourly_details_zip({"S0001": _hourly()}, tmp_path, now=datetime(2026, 1, 2, 3, 4, 5))

    assert path.exists()
    with ZipFile(path) as archive:
        assert "hourly_detail_S0001.csv" in archive.namelist()


def test_export_config_snapshot(tmp_path):
    path = export_config_snapshot({"hello": "世界"}, tmp_path, now=datetime(2026, 1, 2, 3, 4, 5))

    assert path.exists()
    assert "世界" in path.read_text(encoding="utf-8")
