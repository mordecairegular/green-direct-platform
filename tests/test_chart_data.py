import pandas as pd

from green_direct.visualization.chart_data import adapt_hourly, adapt_summary, select_day


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
