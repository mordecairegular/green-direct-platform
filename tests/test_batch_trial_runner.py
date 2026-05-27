from datetime import datetime
from zipfile import ZipFile

import pandas as pd

from green_direct.services.batch_trial_runner import (
    BatchTrialRunConfig,
    CurveColumnConfig,
    load_scenario_grid_file,
    run_batch_trial,
)


def _write_trial_curves(tmp_path):
    hours = pd.date_range("2020-01-01", periods=8760, freq="h")
    load = tmp_path / "load.csv"
    pv = tmp_path / "pv.csv"
    wind = tmp_path / "wind.csv"
    pd.DataFrame({"时间": hours, "负荷": [10.0] * len(hours)}).to_csv(load, index=False, encoding="utf-8-sig")
    pd.DataFrame({"时间": hours, "光伏": [0.5] * len(hours)}).to_csv(pv, index=False, encoding="utf-8-sig")
    pd.DataFrame({"时间": hours, "风电": [0.0] * len(hours)}).to_csv(wind, index=False, encoding="utf-8-sig")
    return load, pv, wind


def test_run_batch_trial_exports_overview_detail_and_snapshot(tmp_path):
    load, pv, wind = _write_trial_curves(tmp_path)
    config = BatchTrialRunConfig(
        load_csv=load,
        pv_csv=pv,
        wind_csv=wind,
        output_dir=tmp_path / "outputs",
        scenario_grid={
            "pv_capacity": {"start": 1, "end": 1, "step": 1},
            "wind_capacity": {"start": 0, "end": 0, "step": 1},
            "bess_power": {"start": 0, "end": 0, "step": 1},
            "bess_duration_hours": [0],
        },
        columns=CurveColumnConfig(),
    )

    artifacts = run_batch_trial(config, now=datetime(2026, 1, 2, 3, 4, 5))

    assert artifacts.scenario_count == 1
    assert artifacts.success_count == 1
    assert artifacts.summary_excel.name == "方案概览_20260102_030405.xlsx"
    assert artifacts.hourly_zip.name == "方案详表_20260102_030405.zip"
    assert artifacts.config_snapshot.name == "本次测算配置_20260102_030405.json"
    assert artifacts.result_note.exists()
    assert artifacts.errors_csv is None
    assert artifacts.summary_excel.exists()
    assert artifacts.hourly_zip.exists()
    with ZipFile(artifacts.hourly_zip) as archive:
        assert "hourly_detail_S0001.csv" in archive.namelist()


def test_load_scenario_grid_file_accepts_documented_wrapper(tmp_path):
    path = tmp_path / "grid.yaml"
    path.write_text(
        """
scenario_grid:
  pv_capacity: {start: 1, end: 2, step: 1}
  wind_capacity: {start: 0, end: 0, step: 1}
  bess_power: {start: 0, end: 0, step: 1}
  bess_duration_hours: [0]
""",
        encoding="utf-8",
    )

    grid = load_scenario_grid_file(path)

    assert grid["pv_capacity"]["start"] == 1
    assert grid["bess_duration_hours"] == [0]
