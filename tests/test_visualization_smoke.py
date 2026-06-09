import pandas as pd

from green_direct.visualization.heatmap_charts import build_heatmap_chart
from green_direct.visualization.multi_scenario_charts import (
    build_curtailment_vs_self_consumption_scatter,
    build_multi_policy_comparison,
)
from green_direct.visualization.single_scenario_charts import (
    build_daily_balance_chart,
    build_grid_exchange_chart,
    build_policy_bar_chart,
    build_soc_chart,
)
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


def test_overview_comparison_uses_grouped_bar_labels_with_capacity():
    class FakeStreamlit:
        def __init__(self):
            self.figure = None

        def plotly_chart(self, fig, use_container_width=True):
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

        def plotly_chart(self, fig, use_container_width=True):
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

        def plotly_chart(self, fig, use_container_width=True):
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
