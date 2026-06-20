import pandas as pd

from green_direct.visualization.chart_data import adapt_hourly, adapt_summary, select_day, select_typical_season_day


def test_adapt_summary_aliases():
    summary = pd.DataFrame({"scenario_id": ["S0001"], "green_power_share": [0.3]})

    adapted = adapt_summary(summary).data

    assert adapted["green_load_rate"].iloc[0] == 0.3


def test_adapt_hourly_adds_time_fields_and_exchange():
    hourly = pd.DataFrame(
        {
            "timestamp": pd.date_range("2020-01-01", periods=24, freq="h"),
            "grid_export_power": [1.0] * 24,
            "grid_import_power": [2.0] * 24,
        }
    )

    adapted = adapt_hourly(hourly).data

    assert "date" in adapted.columns
    assert "hour" in adapted.columns
    assert adapted["grid_exchange_power"].iloc[0] == -1.0


def test_select_day_by_max_load():
    hourly = pd.DataFrame(
        {
            "timestamp": pd.date_range("2020-01-01", periods=48, freq="h"),
            "load_power": [1.0] * 24 + [2.0] * 24,
        }
    )
    adapted = adapt_hourly(hourly).data

    day, label = select_day(adapted, mode="最大负荷日")

    assert label == "2020-01-02"
    assert len(day) == 24


def test_select_typical_season_day_uses_center_profile_and_reports_mmdd():
    hourly = pd.DataFrame(
        {
            "timestamp": pd.date_range("2020-03-01", periods=72, freq="h"),
            "load_power": [10.0] * 24 + [20.0] * 24 + [30.0] * 24,
            "grid_import_power": [3.0] * 24 + [6.0] * 24 + [9.0] * 24,
            "curtail_power": [0.0] * 72,
            "soc_end": [0.5] * 72,
        }
    )
    adapted = adapt_hourly(hourly).data

    selection = select_typical_season_day(
        adapted,
        "春季",
        feature_fields=["load_power", "grid_import_power", "curtail_power", "soc_end"],
    )

    assert selection.label == "03/02"
    assert len(selection.day) == 24
    assert selection.day["timestamp"].dt.strftime("%Y-%m-%d").unique().tolist() == ["2020-03-02"]
    assert "季节中心日法" in selection.method
