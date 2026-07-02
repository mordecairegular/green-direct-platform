import pandas as pd

from green_direct.ui import app


def test_scenario_grid_has_positive_capacity_detects_zero_range():
    grid = {
        "pv_capacity": {"start": 0, "end": 0, "step": 1},
        "wind_capacity": {"start": 0, "end": 5, "step": 5},
    }

    assert app._scenario_grid_has_positive_capacity(grid, "pv_capacity") is False
    assert app._scenario_grid_has_positive_capacity(grid, "wind_capacity") is True


def test_zero_pu_curve_from_load_uses_load_timestamps():
    load = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=3, freq="h"),
            "load": [1.0, 2.0, 3.0],
        }
    )

    zero_df, zero_file, encoding, time_col = app._zero_pu_curve_from_load(
        load,
        "timestamp",
        file_name="auto_zero_pv_pu.csv",
        value_col="pv_pu",
    )

    assert zero_file is not None
    assert encoding == "utf-8-sig"
    assert time_col == "timestamp"
    assert zero_df["pv_pu"].tolist() == [0.0, 0.0, 0.0]
    assert b"pv_pu" in zero_file.getvalue()


def test_recommendation_economy_comparison_figure_uses_firr_and_portfolio():
    summary = pd.DataFrame(
        {
            "scenario_id": ["S0001", "S0002"],
            "pv_capacity": [5.0, 5.0],
            "wind_capacity": [5.0, 10.0],
            "bess_power": [2.0, 4.0],
            "bess_energy": [4.0, 8.0],
            "green_load_rate": [0.5, 0.6],
            "curtail_rate": [0.02, 0.04],
            "pass_policy": [False, True],
        }
    )
    economy = pd.DataFrame({"scenario_id": ["S0001", "S0002"], "firr": [0.08, 0.11]})
    portfolio = pd.DataFrame({"scenario_id": ["S0002"]})

    fig, message = app._build_recommendation_economy_comparison_figure(
        summary,
        economy,
        None,
        portfolio,
        active_scenario_id="S0002",
    )

    assert message is None
    assert fig is not None
    traces = {trace.name: trace for trace in fig.data}
    assert traces["达标候选"].type == "scatter3d"
    assert list(traces["达标候选"].x) == [5.0]
    assert list(traces["达标候选"].y) == [10.0]
    assert list(traces["达标候选"].z) == [11.0]
    assert traces["未达政策"].marker.symbol == "x"
    assert traces["推荐组合"].marker.symbol == "diamond"
    assert traces["当前查看方案"].marker.size == 15
    assert "当前查看方案定位线" in traces
    assert fig.layout.scene.dragmode == "orbit"
    assert fig.to_json()
