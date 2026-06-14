import pandas as pd

from green_direct.visualization.heatmap_charts import build_heatmap_chart
from green_direct.visualization.multi_scenario_charts import (
    build_curtailment_vs_self_consumption_scatter,
    build_multi_policy_comparison,
)
from green_direct.visualization.single_scenario_charts import (
    build_daily_balance_chart,
    build_full_year_operation_chart,
    build_grid_exchange_chart,
    build_monthly_load_source_chart,
    build_monthly_renewable_flow_chart,
    build_policy_bar_chart,
    build_soc_chart,
)
from green_direct.visualization.style import CHART_COLORS, MONTHLY_LOAD_SOURCE_COLORS, MONTHLY_RENEWABLE_FLOW_COLORS
from green_direct.visualization.chart_ui import (
    _render_energy_flow,
    _render_policy_radar,
    _representative_from_recommendation_portfolio,
)


def _hourly(hours=8760):
    timestamps = pd.date_range("2020-01-01", periods=hours, freq="h")
    return pd.DataFrame(
        {
            "scenario_id": ["S0001"] * hours,
            "timestamp": timestamps,
            "hour_index": range(hours),
            "load_power": [10.0] * hours,
            "pv_generation_power": [2.0] * hours,
            "wind_generation_power": [3.0] * hours,
            "direct_self_use_power": [4.0] * hours,
            "bess_discharge_power": [1.0] * hours,
            "grid_import_power": [5.0] * hours,
            "bess_charge_power": [0.5] * hours,
            "grid_export_power": [0.2] * hours,
            "curtail_power": [0.1] * hours,
            "renewable_power": [5.0] * hours,
            "station_use_power": [0.0] * hours,
            "soc_end": [0.5] * hours,
        }
    )


def _summary():
    return pd.DataFrame(
        {
            "scenario_id": ["S0001", "S0002"],
            "pv_capacity": [10.0, 20.0],
            "wind_capacity": [5.0, 10.0],
            "bess_power": [2.0, 3.0],
            "bess_energy": [4.0, 6.0],
            "self_use_rate": [0.7, 0.8],
            "green_load_rate": [0.35, 0.4],
            "export_rate": [0.1, 0.12],
            "curtail_rate": [0.05, 0.03],
            "self_use_energy": [100.0, 120.0],
            "grid_export_energy": [10.0, 12.0],
            "curtail_energy": [5.0, 4.0],
            "bess_loss_energy": [1.0, 1.5],
            "annual_equivalent_cycles": [100.0, 120.0],
        }
    )


def test_single_scenario_charts_smoke():
    hourly = _hourly()
    summary_row = _summary().iloc[0]

    results = [
        build_policy_bar_chart(summary_row),
        build_daily_balance_chart(hourly),
        build_heatmap_chart(hourly),
        build_full_year_operation_chart(hourly),
        build_soc_chart(hourly),
        build_grid_exchange_chart(hourly),
    ]

    assert all(result.figure is not None for result in results)


def test_heatmap_supports_8784_hours():
    result = build_heatmap_chart(_hourly(8784), "grid_import_power")

    assert result.figure is not None


def test_multi_scenario_charts_smoke():
    summary = _summary()

    results = [
        build_multi_policy_comparison(summary),
        build_curtailment_vs_self_consumption_scatter(summary),
    ]

    assert all(result.figure is not None for result in results)
    scatter = results[1]
    assert scatter.figure.layout.xaxis.range == (0, 1)
    assert scatter.figure.layout.yaxis.range == (0, 1)


def test_curtailment_scatter_skips_single_scenario():
    result = build_curtailment_vs_self_consumption_scatter(_summary().head(1))

    assert result.figure is None
    assert result.warnings
    assert "至少需要 2 个方案" in result.warnings[0]
    assert result.meta["export_ready"] is False


def test_report_charts_use_explicit_readable_colors():
    hourly = _hourly(72)
    summary_row = _summary().iloc[0]

    policy = build_policy_bar_chart(summary_row)
    assert [trace.type for trace in policy.figure.data] == ["bar", "scatter", "scatter"]
    assert {trace.name for trace in policy.figure.data} == {"实际值", "阈值线", "阈值标注"}

    day = build_daily_balance_chart(hourly)
    day_colors = {trace.name: trace.marker.color for trace in day.figure.data if trace.type == "bar"}
    assert day_colors["电网下网"] == CHART_COLORS["grid_import"]
    assert day_colors["上网"] == CHART_COLORS["grid_export"]
    assert day_colors["电网下网"] != day_colors["上网"]

    monthly_load = build_monthly_load_source_chart(hourly)
    load_colors = {trace.name: trace.marker.color for trace in monthly_load.figure.data}
    assert load_colors == MONTHLY_LOAD_SOURCE_COLORS

    monthly_renewable = build_monthly_renewable_flow_chart(hourly)
    renewable_colors = {trace.name: trace.marker.color for trace in monthly_renewable.figure.data}
    assert renewable_colors == MONTHLY_RENEWABLE_FLOW_COLORS

    heatmap = build_heatmap_chart(hourly, "grid_import_power")
    assert "电网下网功率" in heatmap.figure.layout.title.text
    assert len({item[1] for item in heatmap.figure.layout.coloraxis.colorscale}) > 2

    full_year = build_full_year_operation_chart(hourly)
    full_year_colors = {trace.name: trace.line.color for trace in full_year.figure.data}
    assert full_year_colors["下网"] == CHART_COLORS["grid_import"]
    assert full_year_colors["上网"] == CHART_COLORS["grid_export"]
    assert full_year.figure.layout.yaxis3.title.text == "SOC"


def test_grid_exchange_chart_uses_export_minus_import_for_display():
    hourly = _hourly(24)
    hourly["grid_export_power"] = [1.0] * 24
    hourly["grid_import_power"] = [3.0] * 24
    hourly["grid_exchange_power"] = [99.0] * 24

    result = build_grid_exchange_chart(hourly)
    net_trace = next(trace for trace in result.figure.data if trace.name == "净交换功率")

    assert list(net_trace.y[:3]) == [-2.0, -2.0, -2.0]
    assert "net_export_power" in result.data.columns


def test_overview_comparison_uses_grouped_bar_labels_with_capacity():
    class FakeStreamlit:
        def __init__(self):
            self.figure = None

        def plotly_chart(self, fig, width="stretch", **kwargs):
            self.figure = fig

    st = FakeStreamlit()

    _render_policy_radar(st, _summary())

    assert st.figure is not None
    assert all(trace.type == "bar" for trace in st.figure.data)
    assert "光10" in st.figure.data[0].name
    assert "风5" in st.figure.data[0].name


def test_chart_representative_scenarios_follow_recommendation_portfolio():
    summary = pd.concat(
        [
            _summary(),
            pd.DataFrame(
                [
                    {
                        "scenario_id": "S0003",
                        "pv_capacity": 30.0,
                        "wind_capacity": 15.0,
                        "bess_power": 4.0,
                        "bess_energy": 8.0,
                    }
                ]
            ),
        ],
        ignore_index=True,
    )
    portfolio = pd.DataFrame(
        [
            {
                "scenario_id": "S0002",
                "recommendation_labels": "电源侧 FIRR 最优/工程代表方案",
                "recommendation_reason": "正式推荐组合命中。",
            },
            {
                "scenario_id": "S9999",
                "recommendation_labels": "不存在方案",
                "recommendation_reason": "不应进入图表。",
            },
            {
                "scenario_id": "S0001",
                "recommendation_labels": "同一主体 FIRR 最优",
                "recommendation_reason": "第二个正式推荐方案。",
            },
        ]
    )

    representative = _representative_from_recommendation_portfolio(summary, portfolio)

    assert [item["scenario_id"] for item in representative] == ["S0002", "S0001"]
    assert representative[0]["labels"] == ["电源侧 FIRR 最优", "工程代表方案"]
    assert "正式推荐组合" in representative[0]["reason"]


def test_energy_flow_sankey_uses_readable_text_style():
    class FakeColumn:
        def __init__(self, owner):
            self.owner = owner

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def plotly_chart(self, fig, width="stretch", **kwargs):
            self.owner.figures.append(fig)

        def metric(self, *args, **kwargs):
            return None

        def caption(self, *args, **kwargs):
            return None

    class FakeStreamlit:
        def __init__(self):
            self.figures = []

        def subheader(self, *args, **kwargs):
            return None

        def columns(self, spec):
            return [FakeColumn(self), FakeColumn(self)]

        def plotly_chart(self, fig, width="stretch", **kwargs):
            self.figures.append(fig)

        def metric(self, *args, **kwargs):
            return None

        def caption(self, *args, **kwargs):
            return None

    hourly = pd.DataFrame(
        {
            "pv_generation_power": [10.0, 12.0],
            "wind_generation_power": [5.0, 6.0],
        }
    )
    active_row = pd.Series(
        {
            "direct_self_use_energy": 12.0,
            "bess_charge_energy": 3.0,
            "grid_export_energy": 2.0,
            "curtail_energy": 1.0,
            "bess_discharge_to_load": 2.5,
            "bess_loss_energy": 0.5,
            "grid_import_energy": 8.0,
        }
    )
    st = FakeStreamlit()

    _render_energy_flow(st, hourly, active_row)

    sankey_fig = next(fig for fig in st.figures if fig.data and fig.data[0].type == "sankey")
    sankey = sankey_fig.data[0]
    assert sankey.textfont.color == "#111827"
    assert sankey.node.line.width == 0.4


def test_missing_fields_returns_warning():
    result = build_soc_chart(pd.DataFrame({"timestamp": pd.date_range("2020-01-01", periods=2, freq="h")}))

    assert result.figure is None
    assert result.warnings
