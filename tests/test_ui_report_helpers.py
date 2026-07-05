import inspect

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


def test_recommendation_economy_hover_includes_recommendation_labels():
    summary = pd.DataFrame(
        {
            "scenario_id": ["S0001", "S0002"],
            "pv_capacity": [5.0, 10.0],
            "wind_capacity": [5.0, 10.0],
            "bess_energy": [4.0, 8.0],
            "green_load_rate": [0.5, 0.6],
            "curtail_rate": [0.02, 0.04],
            "pass_policy": [True, True],
        }
    )
    economy = pd.DataFrame({"scenario_id": ["S0001", "S0002"], "firr": [0.08, 0.11]})
    portfolio = pd.DataFrame(
        {
            "scenario_id": ["S0002", "S0002"],
            "recommendation_labels": ["电源侧FIRR最优", "工程代表方案"],
        }
    )

    fig, message = app._build_recommendation_economy_comparison_figure(
        summary,
        economy,
        None,
        portfolio,
        active_scenario_id="S0002",
    )

    assert message is None
    traces = {trace.name: trace for trace in fig.data}
    recommendation_trace = traces["推荐组合"]
    assert "推荐席位" in recommendation_trace.hovertemplate
    assert "电源侧FIRR最优；工程代表方案" in str(recommendation_trace.customdata)


def test_active_recommendation_economy_scenario_prefers_card_selection():
    class DummySt:
        session_state = {
            app.RECOMMENDATION_ACTIVE_ECONOMY_SCENARIO_KEY: "S0003",
            "chart_overview_active_detail_scenario": "S0002",
            "export_report_scenario": "S0001",
        }

    summary = pd.DataFrame({"scenario_id": ["S0001", "S0002", "S0003"]})
    portfolio = pd.DataFrame({"scenario_id": ["S0001"]})

    assert app._active_recommendation_economy_scenario_id(DummySt, summary, portfolio) == "S0003"

    DummySt.session_state[app.RECOMMENDATION_ACTIVE_ECONOMY_SCENARIO_KEY] = "missing"
    assert app._active_recommendation_economy_scenario_id(DummySt, summary, portfolio) == "S0002"


def test_recommendation_card_query_selection_updates_active_scenario():
    class DummySt:
        session_state = {}
        query_params = {app.RECOMMENDATION_CARD_QUERY_PARAM: "S0002"}

    summary = pd.DataFrame({"scenario_id": ["S0001", "S0002"]})

    app._consume_recommendation_card_query_selection(DummySt, summary)

    assert DummySt.session_state[app.RECOMMENDATION_ACTIVE_ECONOMY_SCENARIO_KEY] == "S0002"
    assert DummySt.session_state["chart_overview_active_detail_scenario"] == "S0002"
    assert app.RECOMMENDATION_CARD_QUERY_PARAM not in DummySt.query_params


def test_recommendation_cards_keep_html_card_layout_with_link_target():
    source = inspect.getsource(app._render_recommendation_cards)
    html_source = inspect.getsource(app._recommendation_card_html)

    assert "_recommendation_card_html" in source
    assert "st.button" not in source
    assert "gd-rec-card-link" in html_source
    assert "RECOMMENDATION_CARD_QUERY_PARAM" in html_source
    assert "gd-rec-card" in html_source
    assert "gd-rec-top" in html_source
    assert "gd-rec-metrics" in html_source
    assert "gd-rec-click-frame" in html_source
    assert "切换到此方案" not in source
    assert "target=\"_self\"" not in source


def test_recommendation_card_html_marks_active_card_without_button_copy():
    html = app._recommendation_card_html(
        pd.Series(
            {
                "scenario_id": "S0002",
                "recommendation_reason": "兼顾收益和工程代表性",
                "pv_capacity": 5.0,
                "wind_capacity": 10.0,
                "bess_power": 2.0,
                "bess_energy": 4.0,
                "green_load_rate": 0.5,
                "self_use_rate": 0.8,
                "curtail_rate": 0.01,
                "single_entity_firr_pre_tax": 0.12,
                "firr": 0.09,
                "load_side_annual_benefit": 1200,
            }
        ),
        rank_text="1",
        labels="电源侧FIRR最优",
        scenario_id="S0002",
        status_text="已入选",
        status_state="ok",
        active=True,
    )

    assert 'class="gd-rec-card is-active"' in html
    assert 'class="gd-rec-card-link"' in html
    assert "gd_rec_scenario=S0002" in html
    assert '<div class="gd-rec-id">S0002</div>' in html
    assert "gd-rec-metric" in html
    assert "切换到此方案" not in html
    assert "###" not in html
    assert "**" not in html
