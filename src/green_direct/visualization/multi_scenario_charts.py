"""Multi-scenario chart builders."""

from __future__ import annotations

import pandas as pd
import plotly.express as px

from green_direct.visualization.chart_contracts import ChartResult, missing_fields_result
from green_direct.visualization.chart_data import adapt_summary, missing_columns
from green_direct.visualization.style import (
    CAPACITY_COLORS,
    CHART_COLOR_SEQUENCE,
    HEATMAP_COLORSCALE,
    POLICY_METRIC_COLORS,
    RENEWABLE_FLOW_COLORS,
)

BASIS = "本图基于 summary 已有字段绘制，只做多方案对比，不重新定义政策口径或技术指标。"


def _result(chart_id: str, chart_name: str, figure, data: pd.DataFrame, fields: list[str]) -> ChartResult:
    return ChartResult(
        chart_id=chart_id,
        chart_name=chart_name,
        figure=figure,
        data=data,
        meta={"fields_used": fields, "calculation_basis": BASIS, "export_ready": True},
    )


def build_multi_policy_comparison(summary: pd.DataFrame) -> ChartResult:
    data = adapt_summary(summary).data
    required = ["scenario_id", "self_use_rate", "green_load_rate", "export_rate"]
    missing = missing_columns(data, required)
    if missing:
        return missing_fields_result("M01", "多方案政策指标对比图", missing)
    chart = data[required].melt(id_vars="scenario_id", var_name="指标", value_name="比例")
    names = {"self_use_rate": "自发自用率", "green_load_rate": "绿电占用电比例", "export_rate": "上网比例"}
    chart["指标"] = chart["指标"].map(names)
    fig = px.bar(
        chart,
        x="scenario_id",
        y="比例",
        color="指标",
        barmode="group",
        title="多方案政策指标对比",
        color_discrete_map=POLICY_METRIC_COLORS,
        template="plotly_white",
    )
    fig.update_layout(colorway=CHART_COLOR_SEQUENCE)
    fig.update_yaxes(tickformat=".1%")
    return _result("M01", "多方案政策指标对比图", fig, chart, required)


def build_multi_capacity_comparison(summary: pd.DataFrame) -> ChartResult:
    data = adapt_summary(summary).data
    required = ["scenario_id", "pv_capacity", "wind_capacity", "bess_power", "bess_energy"]
    missing = missing_columns(data, required)
    if missing:
        return missing_fields_result("M02", "多方案容量配置对比图", missing)
    chart = data[required].melt(id_vars="scenario_id", var_name="容量项", value_name="数值")
    names = {"pv_capacity": "光伏容量", "wind_capacity": "风电容量", "bess_power": "储能功率", "bess_energy": "储能容量"}
    chart["容量项"] = chart["容量项"].map(names)
    fig = px.bar(
        chart,
        x="scenario_id",
        y="数值",
        color="容量项",
        barmode="group",
        title="多方案容量配置对比",
        color_discrete_map=CAPACITY_COLORS,
        template="plotly_white",
    )
    fig.update_layout(colorway=CHART_COLOR_SEQUENCE)
    fig.update_yaxes(tickformat=",.2f")
    return _result("M02", "多方案容量配置对比图", fig, chart, required)


def build_multi_renewable_flow_comparison(summary: pd.DataFrame) -> ChartResult:
    data = adapt_summary(summary).data
    required = ["scenario_id", "self_use_energy", "grid_export_energy", "curtail_energy", "bess_loss_energy"]
    missing = missing_columns(data, required)
    if missing:
        return missing_fields_result("M03", "多方案新能源去向对比图", missing)
    chart = data[required].melt(id_vars="scenario_id", var_name="去向", value_name="电量")
    names = {"self_use_energy": "自发自用", "grid_export_energy": "上网", "curtail_energy": "弃电", "bess_loss_energy": "储能损耗"}
    chart["去向"] = chart["去向"].map(names)
    fig = px.bar(
        chart,
        x="scenario_id",
        y="电量",
        color="去向",
        title="多方案新能源去向对比",
        color_discrete_map=RENEWABLE_FLOW_COLORS,
        template="plotly_white",
    )
    fig.update_layout(colorway=CHART_COLOR_SEQUENCE)
    fig.update_yaxes(tickformat=",.0f")
    return _result("M03", "多方案新能源去向对比图", fig, chart, required)


def build_curtailment_vs_self_consumption_scatter(summary: pd.DataFrame) -> ChartResult:
    data = adapt_summary(summary).data
    required = ["scenario_id", "self_use_rate", "curtail_rate", "green_load_rate", "bess_energy"]
    missing = missing_columns(data, required)
    if missing:
        return missing_fields_result("M05", "弃电率 vs 自发自用率散点图", missing)
    chart_data = data[required].copy()
    if chart_data["scenario_id"].astype(str).nunique() < 2:
        warning = "“弃电率 vs 自发自用率”是多方案权衡图，至少需要 2 个方案才有对比意义；当前仅 1 个方案，已跳过该图。"
        return ChartResult(
            chart_id="M05",
            chart_name="弃电率 vs 自发自用率散点图",
            figure=None,
            data=chart_data,
            meta={
                "fields_used": required,
                "warnings": [warning],
                "export_ready": False,
                "calculation_basis": "单方案没有横向权衡关系，图表模块不生成散点对比图。",
            },
            warnings=[warning],
        )
    fig = px.scatter(
        chart_data,
        x="self_use_rate",
        y="curtail_rate",
        color="green_load_rate",
        size="bess_energy",
        hover_name="scenario_id",
        title="弃电率 vs 自发自用率",
        labels={"self_use_rate": "自发自用率", "curtail_rate": "弃电率", "green_load_rate": "绿电占比"},
        color_continuous_scale=HEATMAP_COLORSCALE,
        template="plotly_white",
    )
    fig.update_xaxes(tickformat=".1%", range=[0, 1])
    fig.update_yaxes(tickformat=".1%", range=[0, 1])
    return _result("M05", "弃电率 vs 自发自用率散点图", fig, chart_data, required)


def build_multi_battery_cycles_comparison(summary: pd.DataFrame) -> ChartResult:
    data = adapt_summary(summary).data
    required = ["scenario_id", "annual_equivalent_cycles"]
    missing = missing_columns(data, required)
    if missing:
        return missing_fields_result("M06", "储能等效循环次数对比图", missing)
    fig = px.bar(data, x="scenario_id", y="annual_equivalent_cycles", title="多方案储能等效循环次数对比")
    fig.update_yaxes(tickformat=",.0f")
    return _result("M06", "储能等效循环次数对比图", fig, data[required], required)
