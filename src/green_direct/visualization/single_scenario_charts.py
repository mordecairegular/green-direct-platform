"""Single-scenario chart builders."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from green_direct.visualization.chart_contracts import ChartResult, missing_fields_result
from green_direct.visualization.chart_data import adapt_hourly, adapt_summary, missing_columns, select_day

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
    fig = go.Figure(
        data=[
            go.Table(
                header={"values": ["指标", "数值"], "fill_color": "#305c64", "font": {"color": "white"}},
                cells={"values": [data["指标"], data["数值"]], "fill_color": "#f7f9f8"},
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
    fig.add_bar(x=data["指标"], y=data["实际值"], name="实际值", marker_color="#2e7d72")
    fig.add_scatter(x=data["指标"], y=data["阈值"], name="阈值", mode="markers", marker=dict(size=12, color="#d2603a"))
    fig.update_yaxes(tickformat=".0%", range=[0, max(1.0, float(data[["实际值", "阈值"]].max().max()) * 1.15)])
    fig.update_layout(title="政策指标达标对比", barmode="group", height=420)
    return _result("S02", "政策指标达标条形图", fig, data, required, policy_thresholds=thresholds)


def build_daily_balance_chart(hourly: pd.DataFrame, mode: str = "首日", selected_date=None) -> ChartResult:
    adapted = adapt_hourly(hourly)
    data = adapted.data
    required = [
        "timestamp",
        "load_power",
        "direct_self_use_power",
        "bess_discharge_power",
        "grid_import_power",
        "bess_charge_power",
        "grid_export_power",
        "curtail_power",
        "soc_end",
    ]
    missing = missing_columns(data, required)
    if missing:
        return missing_fields_result("S03", "典型日源网荷储平衡图", missing)
    day, label = select_day(data, mode=mode, selected_date=selected_date)
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.08, subplot_titles=("负荷供给来源", "新能源富余去向", "储能 SOC"))
    x = day["timestamp"]
    fig.add_bar(x=x, y=day["direct_self_use_power"], name="新能源直供", marker_color="#3f8f7f", row=1, col=1)
    fig.add_bar(x=x, y=day["bess_discharge_power"], name="储能放电供负荷", marker_color="#5d78b6", row=1, col=1)
    fig.add_bar(x=x, y=day["grid_import_power"], name="电网下网", marker_color="#c7a46b", row=1, col=1)
    fig.add_scatter(x=x, y=day["load_power"], name="负荷", mode="lines+markers", line=dict(color="#222"), row=1, col=1)
    fig.add_bar(x=x, y=day["bess_charge_power"], name="储能充电", marker_color="#7cae6a", row=2, col=1)
    fig.add_bar(x=x, y=day["grid_export_power"], name="上网", marker_color="#6d9dc5", row=2, col=1)
    fig.add_bar(x=x, y=day["curtail_power"], name="弃电", marker_color="#d5755d", row=2, col=1)
    fig.add_scatter(x=x, y=day["soc_end"], name="SOC", mode="lines+markers", line=dict(color="#7d4f8f"), row=3, col=1)
    fig.update_layout(title=f"{label} 源网荷储平衡", barmode="stack", height=760)
    fig.update_yaxes(title_text="万千瓦", row=1, col=1)
    fig.update_yaxes(title_text="万千瓦", row=2, col=1)
    fig.update_yaxes(title_text="SOC", tickformat=".0%", row=3, col=1)
    return _result("S03", "典型日源网荷储平衡图", fig, day, required, time_range=label, warnings=adapted.warnings)


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
    fig = px.bar(long, x="month", y="电量", color="来源", title="月度用户用电来源", labels={"month": "月份", "电量": "万千瓦时"})
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
    fig = px.bar(long, x="month", y="电量", color="去向", title="月度新能源去向", labels={"month": "月份", "电量": "万千瓦时"})
    return _result("S06", "月度新能源去向堆叠图", fig, monthly, required, aggregation_method="按月求和")


def build_soc_chart(hourly: pd.DataFrame) -> ChartResult:
    data = adapt_hourly(hourly).data
    required = ["timestamp", "soc_end"]
    missing = missing_columns(data, required)
    if missing:
        return missing_fields_result("S07", "SOC 时序图", missing)
    fig = px.line(data, x="timestamp", y="soc_end", title="储能 SOC 时序", labels={"timestamp": "时间", "soc_end": "SOC"})
    fig.update_yaxes(tickformat=".0%")
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
    fig.add_scatter(x=chart["timestamp"], y=chart["放电功率"], name="放电", mode="lines", line=dict(color="#5d78b6"))
    fig.add_scatter(x=chart["timestamp"], y=chart["充电功率"], name="充电", mode="lines", line=dict(color="#7cae6a"))
    fig.update_layout(title="储能充放电功率", height=420)
    fig.update_yaxes(title_text="万千瓦")
    return _result("S08", "储能充放电功率图", fig, chart, required)


def build_grid_exchange_chart(hourly: pd.DataFrame) -> ChartResult:
    data = adapt_hourly(hourly).data
    required = ["timestamp", "grid_exchange_power", "grid_import_power", "grid_export_power"]
    missing = missing_columns(data, required)
    if missing:
        return missing_fields_result("S09", "电网交换功率图", missing)
    fig = go.Figure()
    fig.add_scatter(x=data["timestamp"], y=data["grid_export_power"], name="上网", mode="lines", line=dict(color="#6d9dc5"))
    fig.add_scatter(x=data["timestamp"], y=-data["grid_import_power"], name="下网", mode="lines", line=dict(color="#c7a46b"))
    fig.add_scatter(x=data["timestamp"], y=data["grid_exchange_power"], name="净交换功率", mode="lines", line=dict(color="#333"))
    fig.update_layout(title="电网交换功率（上网为正，下网为负）", height=420)
    fig.update_yaxes(title_text="万千瓦")
    return _result("S09", "电网交换功率图", fig, data[required], required)


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
    fig = go.Figure(
        data=[
            go.Table(
                header={"values": list(table.columns), "fill_color": "#305c64", "font": {"color": "white"}},
                cells={"values": [table[column] for column in table.columns], "fill_color": "#f7f9f8"},
            )
        ]
    )
    fig.update_layout(title="异常日排行榜", height=360)
    return _result("S11", "异常日排行榜", fig, table, required, aggregation_method="按日聚合后排序")
