"""Streamlit UI for sample-inspired scenario insight charts."""

from __future__ import annotations

import html
import math
from typing import Any

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


COLORS = {
    "pv": "#f4c20d",
    "wind": "#58c7df",
    "bess": "#56c596",
    "grid": "#2f3542",
    "curtail": "#ef7d22",
    "loss": "#9aa4b2",
    "line": "#111827",
    "accent": "#e9b400",
    "muted": "#6b7280",
}


INSIGHT_CSS = """
<style>
.gd-insight-hero {
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 18px 20px;
    margin: 8px 0 18px 0;
    background: linear-gradient(135deg, #f8fafc 0%, #fffdf3 100%);
}
.gd-insight-title {
    font-size: 28px;
    font-weight: 760;
    color: #111827;
    margin-bottom: 6px;
}
.gd-insight-copy {
    color: #6b7280;
    font-size: 14px;
}
.gd-card {
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 14px 14px 12px 14px;
    min-height: 178px;
    background: #ffffff;
}
.gd-card-active {
    border-color: #f0b90b;
    background: #fffaf0;
}
.gd-card-kicker {
    color: #6b7280;
    font-size: 12px;
    margin-bottom: 4px;
}
.gd-card-title {
    font-weight: 700;
    font-size: 17px;
    color: #111827;
    margin-bottom: 4px;
}
.gd-card-reason {
    color: #6b7280;
    font-size: 13px;
    min-height: 36px;
}
.gd-chip-row {
    margin-top: 10px;
    color: #374151;
    font-size: 13px;
}
.gd-mini-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
    margin-top: 12px;
}
.gd-mini {
    border-top: 1px solid #eef2f7;
    padding-top: 8px;
}
.gd-mini-label {
    color: #6b7280;
    font-size: 12px;
}
.gd-mini-value {
    color: #111827;
    font-size: 16px;
    font-weight: 720;
}
.gd-active-strip {
    border-left: 4px solid #f0b90b;
    padding: 10px 12px;
    background: #fffaf0;
    border-radius: 6px;
    margin: 8px 0 14px 0;
}
</style>
"""


def _inject_style(st) -> None:
    st.markdown(INSIGHT_CSS, unsafe_allow_html=True)


def _summary_for_ids(summary: pd.DataFrame, scenario_ids: list[str]) -> pd.DataFrame:
    if "scenario_id" not in summary.columns:
        return pd.DataFrame()
    ids = [str(item) for item in scenario_ids]
    data = summary[summary["scenario_id"].astype(str).isin(ids)].copy()
    if data.empty:
        return data
    order = {scenario_id: index for index, scenario_id in enumerate(ids)}
    data["_display_order"] = data["scenario_id"].astype(str).map(order).fillna(len(order))
    return data.sort_values("_display_order").drop(columns=["_display_order"])


def _fmt(value: Any, suffix: str = "", digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return "-"
    if isinstance(value, (int, float)):
        if math.isinf(value):
            return "-"
        text = f"{value:,.{digits}f}"
        if digits > 0:
            text = text.rstrip("0").rstrip(".")
        return f"{text}{suffix}"
    return f"{value}{suffix}"


def _fmt_rate(value: Any) -> str:
    if value is None or pd.isna(value) or (isinstance(value, float) and math.isinf(value)):
        return "-"
    return f"{float(value):.1%}"


def _fmt_energy(value: Any, suffix: str = " 万kWh") -> str:
    return _fmt(value, suffix, digits=0)


def _apply_numeric_axis_format(fig: go.Figure, *, y_digits: int = 0) -> None:
    fig.update_yaxes(tickformat=f",.{y_digits}f")


def _safe_text(value: Any) -> str:
    return html.escape(str(value))


def _wan_kwh_to_yi_kwh(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value) / 10000


def _series_or_zero(data: pd.DataFrame, column: str) -> pd.Series:
    if column in data.columns:
        return data[column].fillna(0.0)
    return pd.Series([0.0] * len(data), index=data.index)


def _capacity_text(row: pd.Series) -> str:
    return (
        f"光伏 {_fmt(row.get('pv_capacity', 0), ' 万kW')} / "
        f"风电 {_fmt(row.get('wind_capacity', 0), ' 万kW')} / "
        f"储能 {_fmt(row.get('bess_power', 0), ' 万kW')}×{_fmt(row.get('bess_duration', 0), 'h')}"
    )


def _select_representative_scenarios(
    summary: pd.DataFrame,
    economy_summary: pd.DataFrame | None = None,
) -> list[dict[str, Any]]:
    if summary.empty or "scenario_id" not in summary.columns:
        return []
    data = summary.copy()
    data["scenario_id"] = data["scenario_id"].astype(str)
    candidate = data[data["pass_policy"] == True].copy() if "pass_policy" in data.columns else data.copy()  # noqa: E712
    if candidate.empty:
        candidate = data.copy()

    picked: list[dict[str, Any]] = []

    def add(label: str, row: pd.Series | None, reason: str) -> None:
        if row is None or row.empty:
            return
        sid = str(row["scenario_id"])
        for item in picked:
            if item["scenario_id"] == sid:
                item["labels"].append(label)
                item["reason"] = f"{item['reason']}；{reason}"
                return
        picked.append({"label": label, "labels": [label], "scenario_id": sid, "reason": reason})

    if economy_summary is not None and not economy_summary.empty and {"scenario_id", "fnpv"}.issubset(economy_summary.columns):
        econ = economy_summary.copy()
        econ["scenario_id"] = econ["scenario_id"].astype(str)
        merged = candidate.merge(econ[["scenario_id", "fnpv"]], on="scenario_id", how="left")
        sort_columns = ["fnpv"]
        ascending = [False]
        if "green_load_rate" in merged.columns:
            sort_columns.append("green_load_rate")
            ascending.append(False)
        best = merged.sort_values(sort_columns, ascending=ascending, na_position="last").iloc[0]
        add("推荐方案", best, "FNPV 优先，兼顾技术达标")
    else:
        sort_columns = [column for column in ["green_load_rate", "curtail_rate", "bess_energy"] if column in candidate.columns]
        if sort_columns:
            ascending = [False if column == "green_load_rate" else True for column in sort_columns]
            best = candidate.sort_values(sort_columns, ascending=ascending).iloc[0]
        else:
            best = candidate.iloc[0]
        add("推荐方案", best, "绿电占比优先，兼顾低弃电")

    if "green_load_rate" in candidate.columns:
        add("高消纳备选", candidate.sort_values("green_load_rate", ascending=False).iloc[0], "绿电占用电比例最高")
    if "curtail_rate" in candidate.columns:
        add("低弃电备选", candidate.sort_values("curtail_rate", ascending=True).iloc[0], "弃电率最低")
    if "bess_energy" in candidate.columns:
        add("低储能备选", candidate.sort_values(["bess_energy", "green_load_rate"], ascending=[True, False]).iloc[0], "储能容量较小")

    return picked[:4]


def _get_economy_summary(economy_result) -> pd.DataFrame | None:
    if not economy_result:
        return None
    summary = economy_result.get("summary") if isinstance(economy_result, dict) else None
    return summary if isinstance(summary, pd.DataFrame) else None


def _economy_row(economy_summary: pd.DataFrame | None, scenario_id: str) -> pd.Series | None:
    if economy_summary is None or economy_summary.empty or "scenario_id" not in economy_summary.columns:
        return None
    hit = economy_summary[economy_summary["scenario_id"].astype(str) == str(scenario_id)]
    if hit.empty:
        return None
    return hit.iloc[0]


def _scenario_label(scenario_id: str, representative: list[dict[str, Any]]) -> str:
    for item in representative:
        if item["scenario_id"] == scenario_id:
            return f"{'/'.join(item['labels'])} · {scenario_id}"
    return f"用户加入 · {scenario_id}"


def _scenario_selector(st, summary: pd.DataFrame, representative: list[dict[str, Any]]) -> tuple[list[str], str]:
    all_ids = summary["scenario_id"].astype(str).tolist()
    default_ids = [item["scenario_id"] for item in representative]
    with st.expander("加入用户关注方案参与对比", expanded=False):
        pinned = st.multiselect(
            "从本次枚举方案中加入对比",
            all_ids,
            default=[],
            key="insight_pinned_ids",
            help="用于把你心里想看的方案加入图表，不改变系统推荐结果。",
        )
    selected_ids = list(dict.fromkeys([*default_ids, *[str(item) for item in pinned]]))
    if not selected_ids:
        selected_ids = all_ids[:1]
    active = st.radio(
        "当前图表对应方案",
        selected_ids,
        format_func=lambda sid: _scenario_label(sid, representative),
        horizontal=True,
        key="insight_active_scenario",
    )
    return selected_ids, str(active)


def _render_solution_card(
    st,
    row: pd.Series,
    econ: pd.Series | None,
    label: str,
    reason: str,
    highlight: bool = False,
) -> None:
    class_name = "gd-card gd-card-active" if highlight else "gd-card"
    econ_left = _fmt(econ.get("fnpv"), " 万元", digits=0) if econ is not None else _fmt_rate(row.get("export_rate"))
    econ_left_label = "FNPV" if econ is not None else "上网比例"
    econ_right = _fmt_rate(econ.get("firr")) if econ is not None else _fmt(row.get("annual_equivalent_cycles"), " 次", digits=0)
    econ_right_label = "FIRR" if econ is not None else "年循环"
    html_card = f"""
    <div class="{class_name}">
      <div class="gd-card-kicker">{_safe_text("推荐" if highlight else "备选")}</div>
      <div class="gd-card-title">{_safe_text(label)} · {_safe_text(row["scenario_id"])}</div>
      <div class="gd-card-reason">{_safe_text(reason)}</div>
      <div class="gd-chip-row">{_safe_text(_capacity_text(row))}</div>
      <div class="gd-mini-grid">
        <div class="gd-mini"><div class="gd-mini-label">绿电占比</div><div class="gd-mini-value">{_safe_text(_fmt_rate(row.get("green_load_rate")))}</div></div>
        <div class="gd-mini"><div class="gd-mini-label">弃电率</div><div class="gd-mini-value">{_safe_text(_fmt_rate(row.get("curtail_rate")))}</div></div>
        <div class="gd-mini"><div class="gd-mini-label">{_safe_text(econ_left_label)}</div><div class="gd-mini-value">{_safe_text(econ_left)}</div></div>
        <div class="gd-mini"><div class="gd-mini-label">{_safe_text(econ_right_label)}</div><div class="gd-mini-value">{_safe_text(econ_right)}</div></div>
      </div>
    </div>
    """
    st.markdown(html_card, unsafe_allow_html=True)


def _render_active_strip(st, active_row: pd.Series, representative: list[dict[str, Any]]) -> None:
    label = _scenario_label(str(active_row["scenario_id"]), representative)
    strip = f"""
    <div class="gd-active-strip">
      <strong>当前图表：</strong>{_safe_text(label)}
      <span style="color:#6b7280;">　{_safe_text(_capacity_text(active_row))}</span>
    </div>
    """
    st.markdown(strip, unsafe_allow_html=True)


def _render_overview(
    st,
    selected_summary: pd.DataFrame,
    active_row: pd.Series,
    representative: list[dict[str, Any]],
    economy_summary: pd.DataFrame | None,
) -> None:
    st.subheader("方案总览")
    cols = st.columns(min(3, max(len(representative), 1)))
    for index, item in enumerate(representative[:3]):
        row = selected_summary[selected_summary["scenario_id"].astype(str) == item["scenario_id"]]
        if row.empty:
            continue
        econ = _economy_row(economy_summary, item["scenario_id"])
        with cols[index % len(cols)]:
            _render_solution_card(
                st,
                row.iloc[0],
                econ,
                "/".join(item["labels"]),
                item["reason"],
                highlight=index == 0,
            )

    user_rows = selected_summary[
        ~selected_summary["scenario_id"].astype(str).isin([item["scenario_id"] for item in representative])
    ]
    if not user_rows.empty:
        st.markdown("#### 用户加入方案")
        user_cols = st.columns(min(3, len(user_rows)))
        for index, (_, row) in enumerate(user_rows.head(6).iterrows()):
            with user_cols[index % len(user_cols)]:
                _render_solution_card(st, row, _economy_row(economy_summary, str(row["scenario_id"])), "用户关注方案", "手动加入对比")

    st.markdown("#### 当前方案指标")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("光伏(万kW)", _fmt(active_row.get("pv_capacity")))
    c2.metric("风电(万kW)", _fmt(active_row.get("wind_capacity")))
    c3.metric("储能功率(万kW)", _fmt(active_row.get("bess_power")))
    c4.metric("储能容量(万kWh)", _fmt_energy(active_row.get("bess_energy"), ""))
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("自发自用(亿kWh)", _fmt(_wan_kwh_to_yi_kwh(active_row.get("self_use_energy")), digits=2))
    c2.metric("绿电占比", _fmt_rate(active_row.get("green_load_rate")))
    c3.metric("弃电率", _fmt_rate(active_row.get("curtail_rate")))
    c4.metric("政策达标", "是" if bool(active_row.get("pass_policy", False)) else "否")

    if len(selected_summary) >= 2:
        _render_policy_radar(st, selected_summary)


def _render_policy_radar(st, selected_summary: pd.DataFrame) -> None:
    fields = ["green_load_rate", "self_use_rate", "curtail_rate", "export_rate"]
    if not set(fields).issubset(selected_summary.columns):
        return
    fig = go.Figure()
    labels = ["绿电占比", "消纳率", "低弃电", "低上网"]
    for _, row in selected_summary.head(5).iterrows():
        values = [
            float(row["green_load_rate"]),
            float(row["self_use_rate"]),
            1 - float(row["curtail_rate"]),
            1 - float(row["export_rate"]),
        ]
        fig.add_trace(
            go.Scatterpolar(
                r=[*values, values[0]],
                theta=[*labels, labels[0]],
                fill="toself",
                name=str(row["scenario_id"]),
            )
        )
    fig.update_layout(
        title="多方案关键指标雷达",
        polar=dict(radialaxis=dict(range=[0, 1], tickformat=".1%")),
        height=420,
        margin=dict(l=40, r=40, t=60, b=30),
        legend=dict(orientation="h"),
    )
    st.plotly_chart(fig, use_container_width=True)


def _hourly_energy(hourly: pd.DataFrame, column: str) -> float:
    if column not in hourly.columns:
        return 0.0
    return float(hourly[column].sum())


def _render_energy_flow(st, hourly: pd.DataFrame, active_row: pd.Series) -> None:
    st.subheader("能量流向")
    pv_gen = _hourly_energy(hourly, "pv_generation_power")
    wind_gen = _hourly_energy(hourly, "wind_generation_power")
    total_gen = pv_gen + wind_gen
    direct = float(active_row.get("direct_self_use_energy", 0.0))
    bess_charge = float(active_row.get("bess_charge_energy", 0.0))
    grid_export = float(active_row.get("grid_export_energy", 0.0))
    curtail = float(active_row.get("curtail_energy", 0.0))
    bess_discharge = float(active_row.get("bess_discharge_to_load", 0.0))
    bess_loss = float(active_row.get("bess_loss_energy", 0.0))
    grid_import = float(active_row.get("grid_import_energy", 0.0))

    c1, c2 = st.columns([1, 2])
    with c1:
        fig = go.Figure(
            data=[
                go.Pie(
                    labels=["光伏", "风电"],
                    values=[pv_gen, wind_gen],
                    hole=0.62,
                    marker_colors=[COLORS["pv"], COLORS["wind"]],
                    texttemplate="%{label}<br>%{percent:.1%}",
                    hovertemplate="%{label}<br>%{value:,.0f} 万kWh<br>%{percent:.1%}<extra></extra>",
                )
            ]
        )
        fig.update_layout(title="新能源发电构成", height=390, margin=dict(l=20, r=20, t=60, b=20))
        st.plotly_chart(fig, use_container_width=True)
        st.metric("光伏发电", _fmt_energy(pv_gen))
        st.metric("风电发电", _fmt_energy(wind_gen))

    with c2:
        source_share = [pv_gen / total_gen if total_gen else 0, wind_gen / total_gen if total_gen else 0]
        labels = ["光伏", "风电", "储能", "负荷", "上网", "弃电", "损耗", "电网下网"]
        colors = [
            COLORS["pv"],
            COLORS["wind"],
            COLORS["bess"],
            COLORS["grid"],
            COLORS["curtail"],
            COLORS["loss"],
            "#b8c0cc",
            "#8b95a1",
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
        fig = go.Figure(
            data=[
                go.Sankey(
                    node=dict(label=labels, pad=18, thickness=18, color=colors),
                    link=dict(
                        source=source,
                        target=target,
                        value=value,
                        color="rgba(88, 199, 223, 0.22)",
                        hovertemplate="%{source.label} → %{target.label}<br>%{value:,.0f} 万kWh<extra></extra>",
                    ),
                )
            ]
        )
        fig.update_layout(title="年度能源流向", height=500, margin=dict(l=10, r=10, t=50, b=10))
        st.plotly_chart(fig, use_container_width=True)
        st.caption("光伏、风电到各去向的分摊按年度发电占比近似展示，核心电量仍来自逐小时台账汇总。")


def _select_day(hourly: pd.DataFrame, season: str) -> pd.DataFrame:
    data = hourly.copy()
    data["timestamp"] = pd.to_datetime(data["timestamp"], errors="coerce")
    data = data.dropna(subset=["timestamp"])
    if data.empty:
        return data
    month_map = {"春季": 4, "夏季": 7, "秋季": 10, "冬季": 1}
    month = month_map.get(season, 1)
    month_data = data[data["timestamp"].dt.month == month]
    if month_data.empty:
        month_data = data
    dates = month_data["timestamp"].dt.date
    selected_date = dates.value_counts().sort_index().index[len(dates.value_counts()) // 2]
    return month_data[month_data["timestamp"].dt.date == selected_date].head(24)


def _render_operation(st, hourly: pd.DataFrame) -> None:
    st.subheader("运行时序")
    season = st.radio("典型日", ["春季", "夏季", "秋季", "冬季"], index=1, horizontal=True, key="insight_typical_day")
    day = _select_day(hourly, season)
    if day.empty:
        st.info("当前方案没有可用于运行时序的逐小时数据。")
        return
    x = day["timestamp"]
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.72, 0.28], vertical_spacing=0.08)
    fig.add_bar(x=x, y=_series_or_zero(day, "pv_generation_power"), name="光伏可发", marker_color=COLORS["pv"], row=1, col=1)
    fig.add_bar(x=x, y=_series_or_zero(day, "wind_generation_power"), name="风电可发", marker_color=COLORS["wind"], row=1, col=1)
    fig.add_bar(x=x, y=_series_or_zero(day, "bess_discharge_power"), name="储能放电", marker_color=COLORS["bess"], row=1, col=1)
    fig.add_bar(x=x, y=-_series_or_zero(day, "bess_charge_power"), name="储能充电", marker_color="#7bdcb5", row=1, col=1)
    fig.add_bar(x=x, y=-_series_or_zero(day, "curtail_power"), name="弃电", marker_color=COLORS["curtail"], row=1, col=1)
    fig.add_scatter(x=x, y=_series_or_zero(day, "load_power"), name="负荷", mode="lines", line=dict(color=COLORS["line"], width=3), row=1, col=1)
    fig.add_scatter(
        x=x,
        y=_series_or_zero(day, "soc_end"),
        name="SOC",
        mode="lines",
        line=dict(color="#4a9d8f", width=3),
        row=2,
        col=1,
    )
    fig.update_layout(title=f"24H 典型日运行策略 · {season}", barmode="relative", height=620, legend=dict(orientation="h"))
    fig.update_yaxes(title_text="万kW", tickformat=",.2f", row=1, col=1)
    fig.update_yaxes(title_text="SOC", tickformat=".1%", row=2, col=1)
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("查看 8760h 策略曲线", expanded=False):
        sample = hourly.copy()
        sample["timestamp"] = pd.to_datetime(sample["timestamp"], errors="coerce")
        fig2 = go.Figure()
        fig2.add_scatter(x=sample["timestamp"], y=_series_or_zero(sample, "load_power"), name="负荷", line=dict(color=COLORS["line"]))
        fig2.add_scatter(x=sample["timestamp"], y=_series_or_zero(sample, "renewable_power"), name="新能源净可用", line=dict(color=COLORS["wind"]))
        fig2.add_scatter(x=sample["timestamp"], y=_series_or_zero(sample, "soc_end"), name="SOC", yaxis="y2", line=dict(color="#4a9d8f"))
        fig2.update_layout(
            height=420,
            yaxis=dict(title="万kW", tickformat=",.2f"),
            yaxis2=dict(title="SOC", overlaying="y", side="right", tickformat=".1%"),
            legend=dict(orientation="h"),
        )
        st.plotly_chart(fig2, use_container_width=True)


def _render_economy(st, selected_summary: pd.DataFrame, active_id: str, economy_summary: pd.DataFrame | None) -> None:
    st.subheader("经济性分析")
    if economy_summary is None or economy_summary.empty:
        st.info("请先在“经济性评价 V1”区域计算经济性结果。计算后这里会展示 FNPV、FIRR、回收期和方案对比图。")
        return
    selected_econ = economy_summary[economy_summary["scenario_id"].astype(str).isin(selected_summary["scenario_id"].astype(str))]
    active = _economy_row(economy_summary, active_id)
    if active is not None:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("FNPV(万元)", _fmt(active.get("fnpv"), digits=0))
        c2.metric("FIRR", _fmt_rate(active.get("firr")))
        c3.metric("静态回收期(年)", _fmt(active.get("static_payback_year"), digits=1))
        c4.metric("建设投资(万元)", _fmt(active.get("construction_cash_outflow"), digits=0))
    if selected_econ.empty:
        return
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_bar(
        x=selected_econ["scenario_id"],
        y=selected_econ["construction_cash_outflow"],
        name="总投资",
        marker_color=COLORS["curtail"],
        secondary_y=False,
    )
    fig.add_bar(
        x=selected_econ["scenario_id"],
        y=selected_econ["fnpv"],
        name="FNPV",
        marker_color="#75a9f9",
        secondary_y=False,
    )
    fig.add_scatter(
        x=selected_econ["scenario_id"],
        y=selected_econ["firr"],
        name="FIRR",
        mode="lines+markers",
        line=dict(color=COLORS["accent"], width=3),
        secondary_y=True,
    )
    fig.update_layout(title="多方案经济性对比", height=500, barmode="group", legend=dict(orientation="h"))
    fig.update_yaxes(title_text="万元", tickformat=",.0f", secondary_y=False)
    fig.update_yaxes(title_text="FIRR", tickformat=".1%", secondary_y=True)
    st.plotly_chart(fig, use_container_width=True)


def render_chart_analysis(st, batch_result, summary: pd.DataFrame, economy_result=None) -> None:
    """Render chart insights around representative and user-pinned scenarios."""

    st.markdown("---")
    _inject_style(st)
    st.markdown(
        """
        <div class="gd-insight-hero">
          <div class="gd-insight-title">图表分析：方案图谱</div>
          <div class="gd-insight-copy">围绕系统代表方案和用户加入方案展示关键图，不再默认铺开全量枚举表。</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if summary.empty or not batch_result.hourly_details:
        st.info("当前没有可用于图表分析的方案结果。")
        return

    economy_summary = _get_economy_summary(economy_result)
    representative = _select_representative_scenarios(summary, economy_summary)
    selected_ids, active_id = _scenario_selector(st, summary, representative)
    selected_summary = _summary_for_ids(summary, selected_ids)
    active_summary = _summary_for_ids(summary, [active_id])
    if active_summary.empty:
        st.info("当前方案未找到汇总结果。")
        return
    active_row = active_summary.iloc[0]
    active_hourly = batch_result.hourly_details.get(active_id)
    if active_hourly is None:
        st.info("当前方案未找到逐小时台账。")
        return

    _render_active_strip(st, active_row, representative)

    tabs = st.tabs(["方案总览", "能量流向", "运行时序", "经济性分析"])
    with tabs[0]:
        _render_overview(st, selected_summary, active_row, representative, economy_summary)
    with tabs[1]:
        _render_energy_flow(st, active_hourly, active_row)
    with tabs[2]:
        _render_operation(st, active_hourly)
    with tabs[3]:
        _render_economy(st, selected_summary, active_id, economy_summary)
