"""Single-scenario chart builders."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from green_direct.visualization.chart_contracts import ChartResult, missing_fields_result
from green_direct.visualization.chart_data import adapt_hourly, adapt_summary, missing_columns, select_day
from green_direct.visualization.style import (
    CHART_COLOR_SEQUENCE,
    CHART_COLORS,
    MONTHLY_LOAD_SOURCE_COLORS,
    MONTHLY_RENEWABLE_FLOW_COLORS,
)
from green_direct.ui.field_labels import format_display_frame

BASIS = "本图基于 summary/hourly_detail 已有字段绘制，图表模块仅做筛选、求和、透视等展示性处理，不重新计算储能调度、上网或弃电。"


def _result(chart_id: str, chart_name: str, figure, data: pd.DataFrame, fields: list[str], **meta) -> ChartResult:
    base_meta = {
        "fields_used": fields,
        "calculation_basis": BASIS,
        "export_ready": True,
    }
    base_meta.update(meta)
    return ChartResult(chart_id=chart_id, chart_name=chart_name, figure=figure, data=data, meta=base_meta)


def build_indicator_cards(summary_row: pd.Series | dict) -> ChartResult:
    row = pd.Series(summary_row)
    fields = [
        "total_load_energy",
        "total_renewable_generation",
        "self_use_energy",
        "grid_import_energy",
        "grid_export_energy",
        "curtail_energy",
        "annual_equivalent_cycles",
        "final_soc",
    ]
    data = pd.DataFrame(
        [{"指标": field, "数值": row.get(field, pd.NA)} for field in fields if field in row.index]
    )
    display_data = data.copy()
    display_data["数值"] = [
        format_display_frame(pd.DataFrame([{field: value}])).iloc[0, 0]
        for field, value in zip(data["指标"], data["数值"])
    ]
    fig = go.Figure(
        data=[
            go.Table(
                header={"values": ["指标", "数值"], "fill_color": "#305c64", "font": {"color": "white"}},
                cells={"values": [display_data["指标"], display_data["数值"]], "fill_color": "#f7f9f8"},
            )
        ]
    )
    fig.update_layout(title="方案指标卡", height=360, margin=dict(l=10, r=10, t=50, b=10))
    return _result("S01", "方案指标卡", fig, data, fields)


def build_policy_bar_chart(summary_row: pd.Series | dict, thresholds: dict[str, float] | None = None) -> ChartResult:
    row = pd.Series(summary_row)
    required = ["self_use_rate", "green_load_rate", "export_rate"]
    missing = [field for field in required if field not in row.index]
    if missing:
        return missing_fields_result("S02", "政策指标达标条形图", missing)
    thresholds = thresholds or {"self_use_rate": 0.60, "green_load_rate": 0.30, "export_rate": 0.20}
    labels = {
        "self_use_rate": "自发自用率",
        "green_load_rate": "绿电占用电比例",
        "export_rate": "上网比例",
    }
    data = pd.DataFrame(
        {
            "指标": [labels[field] for field in required],
            "实际值": [float(row[field]) for field in required],
            "阈值": [thresholds[field] for field in required],
            "方向": ["不低于", "不低于", "不高于"],
        }
    )
    fig = go.Figure()
    x_positions = list(range(len(data)))
    fig.add_bar(
        x=x_positions,
        y=data["实际值"],
        name="实际值",
        marker_color=CHART_COLORS["actual"],
        text=[f"{value:.1%}" for value in data["实际值"]],
        textposition="outside",
        hovertemplate="%{customdata}<br>实际值：%{y:.1%}<extra></extra>",
        customdata=data["指标"],
    )
    threshold_x: list[float | None] = []
    threshold_y: list[float | None] = []
    for index, value in enumerate(data["阈值"]):
        threshold_x.extend([index - 0.34, index + 0.34, None])
        threshold_y.extend([float(value), float(value), None])
    fig.add_scatter(
        x=threshold_x,
        y=threshold_y,
        name="阈值线",
        mode="lines",
        line=dict(color=CHART_COLORS["threshold"], width=3),
        hoverinfo="skip",
    )
    fig.add_scatter(
        x=x_positions,
        y=data["阈值"],
        name="阈值标注",
        mode="text",
        text=[f"{value:.1%}" for value in data["阈值"]],
        textposition="top center",
        textfont=dict(color=CHART_COLORS["threshold"]),
        hovertemplate="%{customdata}<br>阈值：%{y:.1%}<extra></extra>",
        customdata=data["指标"],
        showlegend=False,
    )
    fig.update_yaxes(tickformat=".1%", range=[0, max(1.0, float(data[["实际值", "阈值"]].max().max()) * 1.15)])
    fig.update_xaxes(tickvals=x_positions, ticktext=data["指标"])
    fig.update_layout(
        title="政策指标达标对比",
        height=420,
        template="plotly_white",
        colorway=CHART_COLOR_SEQUENCE,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return _result("S02", "政策指标达标条形图", fig, data, required, policy_thresholds=thresholds)


def _series_or_zero(data: pd.DataFrame, column: str) -> pd.Series:
    if column in data.columns:
        return pd.to_numeric(data[column], errors="coerce").fillna(0.0)
    return pd.Series([0.0] * len(data), index=data.index, dtype=float)


def _hourly_energy(hourly: pd.DataFrame, column: str) -> float:
    if column not in hourly.columns:
        return 0.0
    return float(pd.to_numeric(hourly[column], errors="coerce").fillna(0.0).sum())


def build_energy_flow_chart(hourly: pd.DataFrame, summary_row: pd.Series | dict) -> ChartResult:
    row = pd.Series(summary_row)
    fields = [
        "pv_generation_power",
        "wind_generation_power",
        "direct_self_use_energy",
        "bess_charge_energy",
        "grid_export_energy",
        "curtail_energy",
        "bess_discharge_to_load",
        "bess_loss_energy",
        "grid_import_energy",
    ]
    pv_gen = _hourly_energy(hourly, "pv_generation_power")
    wind_gen = _hourly_energy(hourly, "wind_generation_power")
    total_gen = pv_gen + wind_gen
    if total_gen <= 0:
        fallback_total = float(row.get("total_renewable_generation", 0.0) or 0.0)
        total_gen = fallback_total
        pv_gen = fallback_total * 0.5
        wind_gen = fallback_total * 0.5

    direct = float(row.get("direct_self_use_energy", 0.0) or 0.0)
    bess_charge = float(row.get("bess_charge_energy", 0.0) or 0.0)
    grid_export = float(row.get("grid_export_energy", 0.0) or 0.0)
    curtail = float(row.get("curtail_energy", 0.0) or 0.0)
    bess_discharge = float(row.get("bess_discharge_to_load", 0.0) or 0.0)
    bess_loss = float(row.get("bess_loss_energy", 0.0) or 0.0)
    grid_import = float(row.get("grid_import_energy", 0.0) or 0.0)

    source_share = [pv_gen / total_gen if total_gen else 0.0, wind_gen / total_gen if total_gen else 0.0]
    labels = ["光伏", "风电", "储能", "负荷", "上网", "弃电", "损耗", "电网下网"]
    colors = [
        CHART_COLORS["pv"],
        CHART_COLORS["wind"],
        CHART_COLORS["bess"],
        "#2f3542",
        CHART_COLORS["grid_export"],
        CHART_COLORS["curtail"],
        CHART_COLORS["loss"],
        CHART_COLORS["grid_import"],
    ]
    destinations = [(3, direct), (2, bess_charge), (4, grid_export), (5, curtail)]
    source: list[int] = []
    target: list[int] = []
    value: list[float] = []
    for source_index, share in enumerate(source_share):
        for destination, amount in destinations:
            if amount > 0 and share > 0:
                source.append(source_index)
                target.append(destination)
                value.append(amount * share)
    if bess_discharge > 0:
        source.append(2)
        target.append(3)
        value.append(bess_discharge)
    if bess_loss > 0:
        source.append(2)
        target.append(6)
        value.append(bess_loss)
    if grid_import > 0:
        source.append(7)
        target.append(3)
        value.append(grid_import)

    data = pd.DataFrame(
        {
            "source": [labels[index] for index in source],
            "target": [labels[index] for index in target],
            "energy": value,
        }
    )
    fig = go.Figure(
        data=[
            go.Sankey(
                textfont=dict(family="Arial, sans-serif", size=13, color="#111827"),
                node=dict(
                    label=labels,
                    pad=18,
                    thickness=18,
                    color=colors,
                    line=dict(color="rgba(17, 24, 39, 0.18)", width=0.4),
                ),
                link=dict(
                    source=source,
                    target=target,
                    value=value,
                    color="rgba(88, 199, 223, 0.18)",
                    hovertemplate="%{source.label} → %{target.label}<br>%{value:,.0f} 万kWh<extra></extra>",
                ),
            )
        ]
    )
    fig.update_layout(
        title="年度能源流向",
        height=500,
        margin=dict(l=10, r=10, t=50, b=10),
        font=dict(family="Arial, sans-serif", size=13, color="#111827"),
    )
    return _result(
        "S04",
        "年度能源流向图",
        fig,
        data,
        fields,
        display_basis="光伏、风电去向按年度发电占比分摊展示；年度电量来自 summary 和 hourly_detail 汇总，不重新计算调度。",
    )


def build_operation_day_figure(day: pd.DataFrame, title: str, *, height: int = 620) -> go.Figure:
    """Build the same 24H operation figure used by the web page and exports."""

    x = day["timestamp"] if "timestamp" in day.columns else list(range(len(day)))
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.72, 0.28], vertical_spacing=0.08)
    has_pv_or_wind = "pv_generation_power" in day.columns or "wind_generation_power" in day.columns
    if has_pv_or_wind:
        fig.add_bar(
            x=x,
            y=_series_or_zero(day, "pv_generation_power"),
            name="光伏可发",
            marker_color=CHART_COLORS["pv"],
            row=1,
            col=1,
        )
        fig.add_bar(
            x=x,
            y=_series_or_zero(day, "wind_generation_power"),
            name="风电可发",
            marker_color=CHART_COLORS["wind"],
            row=1,
            col=1,
        )
    elif "renewable_power" in day.columns:
        fig.add_bar(
            x=x,
            y=_series_or_zero(day, "renewable_power"),
            name="新能源净可用",
            marker_color=CHART_COLORS["renewable"],
            row=1,
            col=1,
        )
    fig.add_bar(
        x=x,
        y=_series_or_zero(day, "bess_discharge_power"),
        name="储能放电",
        marker_color=CHART_COLORS["bess_discharge"],
        row=1,
        col=1,
    )
    fig.add_bar(
        x=x,
        y=_series_or_zero(day, "grid_import_power"),
        name="电网下网",
        marker_color=CHART_COLORS["grid_import"],
        row=1,
        col=1,
    )
    fig.add_bar(
        x=x,
        y=-_series_or_zero(day, "bess_charge_power"),
        name="储能充电",
        marker_color=CHART_COLORS["bess_charge"],
        row=1,
        col=1,
    )
    fig.add_bar(
        x=x,
        y=-_series_or_zero(day, "grid_export_power"),
        name="上网",
        marker_color=CHART_COLORS["grid_export"],
        row=1,
        col=1,
    )
    fig.add_bar(
        x=x,
        y=-_series_or_zero(day, "curtail_power"),
        name="弃电",
        marker_color=CHART_COLORS["curtail"],
        row=1,
        col=1,
    )
    fig.add_scatter(
        x=x,
        y=_series_or_zero(day, "load_power"),
        name="负荷",
        mode="lines",
        line=dict(color=CHART_COLORS["load"], width=3),
        row=1,
        col=1,
    )
    soc = _series_or_zero(day, "soc_end")
    if not soc.empty and float(soc.max()) > 1:
        soc = soc / 100
    fig.add_scatter(
        x=x,
        y=soc,
        name="SOC",
        mode="lines",
        line=dict(color=CHART_COLORS["soc"], width=3),
        row=2,
        col=1,
    )
    fig.update_layout(
        title=title,
        barmode="relative",
        height=height,
        template="plotly_white",
        colorway=CHART_COLOR_SEQUENCE,
        legend=dict(orientation="h", yanchor="top", y=-0.12, xanchor="center", x=0.5),
        hovermode="x unified",
    )
    fig.update_yaxes(title_text="万kW", tickformat=",.2f", row=1, col=1)
    fig.update_yaxes(title_text="SOC", tickformat=".1%", range=[0, 1], row=2, col=1)
    return fig


def build_daily_balance_chart(
    hourly: pd.DataFrame,
    mode: str = "首日",
    selected_date=None,
    title: str | None = None,
    chart_name: str | None = None,
) -> ChartResult:
    adapted = adapt_hourly(hourly)
    data = adapted.data
    required = [
        "timestamp",
        "load_power",
        "bess_discharge_power",
        "grid_import_power",
        "bess_charge_power",
        "grid_export_power",
        "curtail_power",
        "soc_end",
    ]
    missing = missing_columns(data, required)
    if missing:
        return missing_fields_result("S03", "24H 源网荷储运行策略图", missing)
    day, label = select_day(data, mode=mode, selected_date=selected_date)
    fig = build_operation_day_figure(day, title or f"24H 源网荷储运行策略 · {label}")
    return _result(
        "S03",
        chart_name or "24H 源网荷储运行策略图",
        fig,
        day,
        required,
        time_range=label,
        warnings=adapted.warnings,
    )


def build_monthly_load_source_chart(hourly: pd.DataFrame) -> ChartResult:
    data = adapt_hourly(hourly).data
    required = ["month", "direct_self_use_power", "bess_discharge_power", "grid_import_power"]
    missing = missing_columns(data, required)
    if missing:
        return missing_fields_result("S05", "月度用户用电来源堆叠图", missing)
    monthly = data.groupby("month", as_index=False)[required[1:]].sum()
    long = monthly.melt(id_vars="month", var_name="来源", value_name="电量")
    names = {"direct_self_use_power": "新能源直供", "bess_discharge_power": "储能放电", "grid_import_power": "电网下网"}
    long["来源"] = long["来源"].map(names)
    fig = px.bar(
        long,
        x="month",
        y="电量",
        color="来源",
        title="月度用户用电来源",
        labels={"month": "月份", "电量": "万千瓦时"},
        color_discrete_map=MONTHLY_LOAD_SOURCE_COLORS,
        template="plotly_white",
    )
    fig.update_layout(colorway=CHART_COLOR_SEQUENCE)
    fig.update_yaxes(tickformat=",.0f")
    return _result("S05", "月度用户用电来源堆叠图", fig, monthly, required, aggregation_method="按月求和")


def build_monthly_renewable_flow_chart(hourly: pd.DataFrame) -> ChartResult:
    data = adapt_hourly(hourly).data
    required = ["month", "direct_self_use_power", "bess_charge_power", "grid_export_power", "curtail_power", "station_use_power"]
    missing = missing_columns(data, required)
    if missing:
        return missing_fields_result("S06", "月度新能源去向堆叠图", missing)
    monthly = data.groupby("month", as_index=False)[required[1:]].sum()
    long = monthly.melt(id_vars="month", var_name="去向", value_name="电量")
    names = {
        "direct_self_use_power": "直供负荷",
        "bess_charge_power": "充入储能",
        "grid_export_power": "上网",
        "curtail_power": "弃电",
        "station_use_power": "站用电",
    }
    long["去向"] = long["去向"].map(names)
    fig = px.bar(
        long,
        x="month",
        y="电量",
        color="去向",
        title="月度新能源去向",
        labels={"month": "月份", "电量": "万千瓦时"},
        color_discrete_map=MONTHLY_RENEWABLE_FLOW_COLORS,
        template="plotly_white",
    )
    fig.update_layout(colorway=CHART_COLOR_SEQUENCE)
    fig.update_yaxes(tickformat=",.0f")
    return _result("S06", "月度新能源去向堆叠图", fig, monthly, required, aggregation_method="按月求和")


def build_soc_chart(hourly: pd.DataFrame) -> ChartResult:
    data = adapt_hourly(hourly).data
    required = ["timestamp", "soc_end"]
    missing = missing_columns(data, required)
    if missing:
        return missing_fields_result("S07", "SOC 时序图", missing)
    fig = px.line(data, x="timestamp", y="soc_end", title="储能 SOC 时序", labels={"timestamp": "时间", "soc_end": "SOC"}, template="plotly_white")
    fig.update_traces(line_color=CHART_COLORS["soc"])
    fig.update_yaxes(tickformat=".1%")
    return _result("S07", "SOC 时序图", fig, data[required], required)


def build_battery_power_chart(hourly: pd.DataFrame) -> ChartResult:
    data = adapt_hourly(hourly).data
    required = ["timestamp", "bess_charge_power", "bess_discharge_power"]
    missing = missing_columns(data, required)
    if missing:
        return missing_fields_result("S08", "储能充放电功率图", missing)
    chart = data[required].copy()
    chart["放电功率"] = chart["bess_discharge_power"]
    chart["充电功率"] = -chart["bess_charge_power"]
    fig = go.Figure()
    fig.add_scatter(x=chart["timestamp"], y=chart["放电功率"], name="放电", mode="lines", line=dict(color=CHART_COLORS["bess_discharge"]))
    fig.add_scatter(x=chart["timestamp"], y=chart["充电功率"], name="充电", mode="lines", line=dict(color=CHART_COLORS["bess_charge"]))
    fig.update_layout(title="储能充放电功率", height=420, template="plotly_white", colorway=CHART_COLOR_SEQUENCE)
    fig.update_yaxes(title_text="万千瓦", tickformat=",.2f")
    return _result("S08", "储能充放电功率图", fig, chart, required)


def build_grid_exchange_chart(hourly: pd.DataFrame) -> ChartResult:
    data = adapt_hourly(hourly).data
    required = ["timestamp", "grid_exchange_power", "grid_import_power", "grid_export_power"]
    missing = missing_columns(data, required)
    if missing:
        return missing_fields_result("S09", "电网交换功率图", missing)
    chart = data[required].copy()
    chart["grid_import_power_signed"] = -_series_or_zero(chart, "grid_import_power")
    chart["net_export_power"] = _series_or_zero(chart, "grid_export_power") - _series_or_zero(chart, "grid_import_power")
    fig = go.Figure()
    fig.add_scatter(x=chart["timestamp"], y=chart["grid_export_power"], name="上网", mode="lines", line=dict(color=CHART_COLORS["grid_export"]))
    fig.add_scatter(x=chart["timestamp"], y=chart["grid_import_power_signed"], name="下网", mode="lines", line=dict(color=CHART_COLORS["grid_import"]))
    fig.add_scatter(x=chart["timestamp"], y=chart["net_export_power"], name="净交换功率", mode="lines", line=dict(color=CHART_COLORS["load"], width=1.6))
    fig.update_layout(title="电网交换功率（上网为正，下网为负）", height=420, template="plotly_white", colorway=CHART_COLOR_SEQUENCE)
    fig.update_yaxes(title_text="万千瓦", tickformat=",.2f")
    return _result(
        "S09",
        "电网交换功率图",
        fig,
        chart,
        required,
        display_basis="图中净交换功率 = grid_export_power - grid_import_power；原始 grid_exchange_power 保留在导出数据中用于复核。",
    )


def build_full_year_operation_chart(hourly: pd.DataFrame) -> ChartResult:
    data = adapt_hourly(hourly).data
    required = ["timestamp", "load_power", "renewable_power", "grid_import_power", "grid_export_power", "curtail_power", "soc_end"]
    missing = missing_columns(data, required)
    if missing:
        return missing_fields_result("S10", "全年 8760/8784 小时运行曲线", missing)
    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.48, 0.28, 0.24],
        vertical_spacing=0.07,
        subplot_titles=("供需与下网", "上网与弃电", "储能 SOC"),
    )
    for label, column, color, width in [
        ("负荷", "load_power", CHART_COLORS["load"], 1.5),
        ("新能源净可用", "renewable_power", CHART_COLORS["renewable"], 1.3),
        ("下网", "grid_import_power", CHART_COLORS["grid_import"], 1.2),
    ]:
        fig.add_scatter(
            x=data["timestamp"],
            y=_series_or_zero(data, column),
            name=label,
            mode="lines",
            line=dict(color=color, width=width),
            row=1,
            col=1,
        )
    for label, column, color in [
        ("上网", "grid_export_power", CHART_COLORS["grid_export"]),
        ("弃电", "curtail_power", CHART_COLORS["curtail"]),
    ]:
        fig.add_scatter(
            x=data["timestamp"],
            y=_series_or_zero(data, column),
            name=label,
            mode="lines",
            fill="tozeroy",
            line=dict(color=color, width=0.9),
            opacity=0.68,
            row=2,
            col=1,
        )
    soc = _series_or_zero(data, "soc_end")
    if not soc.empty and float(soc.max()) > 1:
        soc = soc / 100
    fig.add_scatter(
        x=data["timestamp"],
        y=soc,
        name="SOC",
        mode="lines",
        line=dict(color=CHART_COLORS["soc"], width=1.6),
        row=3,
        col=1,
    )
    fig.update_layout(
        title="全年 8760/8784 小时运行曲线",
        height=760,
        template="plotly_white",
        colorway=CHART_COLOR_SEQUENCE,
        hovermode="x unified",
        legend=dict(orientation="h"),
    )
    fig.update_yaxes(title_text="万kW", tickformat=",.2f", row=1, col=1)
    fig.update_yaxes(title_text="万kW", tickformat=",.2f", row=2, col=1)
    fig.update_yaxes(title_text="SOC", tickformat=".1%", range=[0, 1], row=3, col=1)
    return _result("S10", "全年 8760/8784 小时运行曲线", fig, data[required], required)


def build_abnormal_day_table(hourly: pd.DataFrame) -> ChartResult:
    data = adapt_hourly(hourly).data
    required = ["date", "load_power", "grid_import_power", "grid_export_power", "curtail_power", "soc_end"]
    missing = missing_columns(data, required)
    if missing:
        return missing_fields_result("S11", "异常日排行榜", missing)
    daily = data.groupby("date", as_index=False).agg(
        load_energy=("load_power", "sum"),
        grid_import_energy=("grid_import_power", "sum"),
        grid_export_energy=("grid_export_power", "sum"),
        curtail_energy=("curtail_power", "sum"),
        min_soc=("soc_end", "min"),
        max_soc=("soc_end", "max"),
    )
    rows = []
    for label, column, ascending in [
        ("最大负荷日", "load_energy", False),
        ("最大下网日", "grid_import_energy", False),
        ("最大上网日", "grid_export_energy", False),
        ("最大弃电日", "curtail_energy", False),
        ("SOC 最低日", "min_soc", True),
        ("SOC 最高日", "max_soc", False),
    ]:
        if not daily.empty:
            row = daily.sort_values(column, ascending=ascending).iloc[0].to_dict()
            row["类型"] = label
            row["排序指标"] = column
            rows.append(row)
    table = pd.DataFrame(rows)
    display_table = format_display_frame(table)
    fig = go.Figure(
        data=[
            go.Table(
                header={"values": list(display_table.columns), "fill_color": "#305c64", "font": {"color": "white"}},
                cells={"values": [display_table[column] for column in display_table.columns], "fill_color": "#f7f9f8"},
            )
        ]
    )
    fig.update_layout(title="异常日排行榜", height=360)
    return _result("S11", "异常日排行榜", fig, table, required, aggregation_method="按日聚合后排序")
