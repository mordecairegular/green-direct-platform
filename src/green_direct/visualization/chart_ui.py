"""Streamlit UI for sample-inspired scenario insight charts."""

from __future__ import annotations

import html
import hashlib
import math
from typing import Any

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from green_direct.visualization.chart_data import (
    adapt_hourly,
    select_day as select_operating_day,
    select_typical_season_day,
)
from green_direct.visualization.single_scenario_charts import build_operation_day_figure
from green_direct.visualization.style import CHART_COLORS


COLORS = {
    "pv": CHART_COLORS["pv"],
    "wind": CHART_COLORS["wind"],
    "bess": CHART_COLORS["bess"],
    "grid": "#2f3542",
    "grid_import": CHART_COLORS["grid_import"],
    "grid_export": CHART_COLORS["grid_export"],
    "curtail": CHART_COLORS["curtail"],
    "loss": CHART_COLORS["loss"],
    "line": CHART_COLORS["line"],
    "accent": CHART_COLORS["accent"],
    "muted": CHART_COLORS["muted"],
    "soc": CHART_COLORS["soc"],
}


INSIGHT_CSS = """
<style>
.gd-insight-hero {
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 18px 20px;
    margin: 8px 0 18px 0;
    background: #ffffff;
}
.gd-insight-title {
    font-size: 22px;
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
    border-left: 4px solid #3b82f6;
    padding: 10px 12px;
    background: #f8fbff;
    border-radius: 6px;
    margin: 8px 0 14px 0;
    color: #334155;
}
.gd-active-strip strong {
    color: #0f172a;
}
.gd-active-strip span {
    color: #64748b;
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
        f"储能 {_fmt(row.get('bess_power', 0), ' 万kW')} / {_fmt(row.get('bess_energy', 0), ' 万kWh')}"
    )


def _short_capacity_text(row: pd.Series) -> str:
    return (
        f"光{_fmt(row.get('pv_capacity', 0), digits=0)} "
        f"风{_fmt(row.get('wind_capacity', 0), digits=0)} "
        f"储{_fmt(row.get('bess_power', 0), digits=0)}/{_fmt(row.get('bess_energy', 0), digits=0)}"
    )


def _scenario_with_capacity_label(row: pd.Series) -> str:
    return f"{row['scenario_id']} · {_short_capacity_text(row)}"


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


def _representative_from_recommendation_portfolio(
    summary: pd.DataFrame,
    recommendation_portfolio: pd.DataFrame | None,
) -> list[dict[str, Any]]:
    if (
        recommendation_portfolio is None
        or recommendation_portfolio.empty
        or "scenario_id" not in recommendation_portfolio.columns
        or summary.empty
        or "scenario_id" not in summary.columns
    ):
        return []

    available_ids = set(summary["scenario_id"].astype(str))
    picked: list[dict[str, Any]] = []
    for _, row in recommendation_portfolio.iterrows():
        scenario_id = row.get("scenario_id")
        if scenario_id is None or pd.isna(scenario_id):
            continue
        scenario_id = str(scenario_id)
        if scenario_id not in available_ids:
            continue

        raw_labels = row.get("recommendation_labels", "推荐方案")
        labels = [item.strip() for item in str(raw_labels).split("/") if item.strip()]
        if not labels:
            labels = ["推荐方案"]
        reason = str(row.get("recommendation_reason", "推荐组合入选方案"))

        existing = next((item for item in picked if item["scenario_id"] == scenario_id), None)
        if existing is not None:
            for label in labels:
                if label not in existing["labels"]:
                    existing["labels"].append(label)
            if reason and reason not in existing["reason"]:
                existing["reason"] = f"{existing['reason']}；{reason}"
            continue

        picked.append(
            {
                "label": labels[0],
                "labels": labels,
                "scenario_id": scenario_id,
                "reason": reason,
            }
        )

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


def _scenario_label(
    scenario_id: str,
    representative: list[dict[str, Any]],
    summary: pd.DataFrame | None = None,
) -> str:
    capacity = ""
    if summary is not None and not summary.empty and "scenario_id" in summary.columns:
        hit = summary[summary["scenario_id"].astype(str) == str(scenario_id)]
        if not hit.empty:
            capacity = f" · {_short_capacity_text(hit.iloc[0])}"
    for item in representative:
        if item["scenario_id"] == scenario_id:
            return f"{'/'.join(item['labels'])} · {scenario_id}{capacity}"
    return f"用户加入 · {scenario_id}{capacity}"


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
    selector_signature = hashlib.sha1("|".join(selected_ids).encode("utf-8")).hexdigest()[:10]
    active = st.radio(
        "当前图表对应方案",
        selected_ids,
        format_func=lambda sid: _scenario_label(sid, representative, summary),
        horizontal=True,
        key=f"insight_active_scenario_{selector_signature}",
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
    scenario_id = str(active_row["scenario_id"])
    labels: list[str] = []
    for item in representative:
        if item["scenario_id"] == scenario_id:
            labels = list(item.get("labels", []))
            break
    label_text = " / ".join(labels) if labels else "用户指定方案"
    strip = f"""
    <div class="gd-active-strip">
      <strong>当前复核方案：</strong>{_safe_text(scenario_id)}
      <span>　{_safe_text(_capacity_text(active_row))}</span>
      <br><span>{_safe_text(label_text)}</span>
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
    labels = ["绿电占比", "自发自用率", "弃电率", "上网比例"]
    colors = ["#2563eb", "#16a34a", "#dc2626", "#9333ea", "#f59e0b"]
    for _, row in selected_summary.head(5).iterrows():
        values = [
            float(row["green_load_rate"]),
            float(row["self_use_rate"]),
            float(row["curtail_rate"]),
            float(row["export_rate"]),
        ]
        fig.add_trace(
            go.Bar(
                x=labels,
                y=values,
                name=_scenario_with_capacity_label(row),
                marker_color=colors[len(fig.data) % len(colors)],
                hovertemplate="%{fullData.name}<br>%{x}: %{y:.1%}<extra></extra>",
            )
        )
    fig.update_layout(
        title="多方案关键指标对比",
        barmode="group",
        height=460,
        margin=dict(l=30, r=20, t=60, b=110),
        legend=dict(orientation="h", yanchor="top", y=-0.18, xanchor="left", x=0),
    )
    fig.update_yaxes(range=[0, 1], tickformat=".0%", title_text="比例")
    st.plotly_chart(fig, width="stretch")


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
        st.plotly_chart(fig, width="stretch")
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
        st.plotly_chart(fig, width="stretch")
        st.caption("光伏、风电到各去向的分摊按年度发电占比近似展示，核心电量仍来自逐小时台账汇总。")


def _render_day_operation_chart(st, day: pd.DataFrame, title: str) -> None:
    if day.empty:
        st.info("当前方案没有可用于运行时序的逐小时数据。")
        return
    fig = build_operation_day_figure(day, title)
    st.plotly_chart(fig, width="stretch")


def _render_full_year_operation(st, hourly: pd.DataFrame) -> None:
    if hourly.empty:
        st.info("当前方案没有可用于全年曲线的逐小时数据。")
        return
    options = {
        "负荷": ("load_power", COLORS["line"], "y"),
        "新能源净可用": ("renewable_power", COLORS["wind"], "y"),
        "下网": ("grid_import_power", COLORS["grid_import"], "y"),
        "上网": ("grid_export_power", COLORS["grid_export"], "y"),
        "弃电": ("curtail_power", COLORS["curtail"], "y"),
        "SOC": ("soc_end", COLORS["soc"], "y2"),
    }
    selected = st.multiselect(
        "显示曲线",
        list(options.keys()),
        default=["负荷", "新能源净可用", "下网", "SOC"],
        key="insight_full_year_series",
    )
    fig = go.Figure()
    for label in selected:
        column, color, axis = options[label]
        if column not in hourly.columns:
            continue
        fig.add_trace(
            go.Scattergl(
                x=hourly["timestamp"],
                y=_series_or_zero(hourly, column),
                name=label,
                yaxis=axis,
                mode="lines",
                line=dict(color=color, width=1.4),
            )
        )
    fig.update_layout(
        title="全年 8760/8784 小时运行曲线",
        height=520,
        yaxis=dict(title="万kW", tickformat=",.2f"),
        yaxis2=dict(title="SOC", overlaying="y", side="right", tickformat=".1%", range=[0, 1]),
        xaxis=dict(
            rangeslider=dict(visible=True, thickness=0.08),
            rangeselector=dict(
                buttons=[
                    dict(count=1, label="1周", step="day", stepmode="backward"),
                    dict(count=1, label="1月", step="month", stepmode="backward"),
                    dict(step="all", label="全年"),
                ]
            ),
        ),
        legend=dict(orientation="h"),
        margin=dict(l=10, r=10, t=70, b=10),
    )
    st.plotly_chart(fig, width="stretch")
    st.caption("可拖动底部范围条缩放时段；SOC 使用右轴，功率类曲线使用左轴。")


def _render_operation(st, hourly: pd.DataFrame) -> None:
    st.subheader("运行时序")
    adapted = adapt_hourly(hourly).data
    if "timestamp" not in adapted.columns:
        st.info("当前方案缺少 timestamp，无法生成运行时序图。")
        return
    adapted["timestamp"] = pd.to_datetime(adapted["timestamp"], errors="coerce")
    adapted = adapted.dropna(subset=["timestamp"])
    if adapted.empty:
        st.info("当前方案没有可用于运行时序的逐小时数据。")
        return

    tabs = st.tabs(["典型季节日", "关键运行日", "全年8760曲线"])
    with tabs[0]:
        season = st.radio(
            "典型日",
            ["春季", "夏季", "秋季", "冬季"],
            index=1,
            horizontal=True,
            key="insight_typical_day",
        )
        selection = select_typical_season_day(adapted, season)
        st.caption(f"{season}典型日选中日期：{selection.label}。{selection.method}")
        _render_day_operation_chart(st, selection.day, f"24H 典型日运行策略 · {season}")
    with tabs[1]:
        mode = st.selectbox(
            "关键日类型",
            ["最大负荷日", "最大弃电日", "最大下网日", "SOC 最低日", "SOC 最高日"],
            key="insight_key_day_mode",
        )
        day, label = select_operating_day(adapted, mode=mode)
        st.caption(f"{mode}选中日期：{label}。")
        _render_day_operation_chart(st, day, f"24H 关键运行日 · {mode}")
    with tabs[2]:
        _render_full_year_operation(st, adapted)


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
    st.plotly_chart(fig, width="stretch")


def render_chart_analysis(
    st,
    batch_result,
    summary: pd.DataFrame,
    economy_result=None,
    recommendation_portfolio: pd.DataFrame | None = None,
    selected_scenario_ids: list[str] | None = None,
    active_scenario_id: str | None = None,
    show_overview: bool = True,
    show_selector: bool = True,
    show_hero: bool = True,
) -> None:
    """Render chart insights around representative and user-pinned scenarios."""

    _inject_style(st)
    if show_hero:
        st.markdown("---")
        st.markdown(
            """
            <div class="gd-insight-hero">
              <div class="gd-insight-title">详细图表复核</div>
              <div class="gd-insight-copy">围绕代表方案和用户指定方案查看能量流向、运行时序和经济性图表。</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if summary.empty or not batch_result.hourly_details:
        st.info("当前没有可用于图表分析的方案结果。")
        return

    economy_summary = _get_economy_summary(economy_result)
    representative = _representative_from_recommendation_portfolio(summary, recommendation_portfolio)
    if not representative:
        representative = _select_representative_scenarios(summary, economy_summary)

    available_ids = set(summary["scenario_id"].astype(str))
    if selected_scenario_ids is not None:
        selected_ids = [
            str(scenario_id)
            for scenario_id in dict.fromkeys(selected_scenario_ids)
            if str(scenario_id) in available_ids
        ]
        if not selected_ids:
            selected_ids = [item["scenario_id"] for item in representative if item["scenario_id"] in available_ids]
        if not selected_ids:
            selected_ids = summary["scenario_id"].astype(str).head(1).tolist()
        active_id = str(active_scenario_id) if active_scenario_id and str(active_scenario_id) in selected_ids else selected_ids[0]
    elif show_selector:
        selected_ids, active_id = _scenario_selector(st, summary, representative)
    else:
        selected_ids = [item["scenario_id"] for item in representative if item["scenario_id"] in available_ids]
        if not selected_ids:
            selected_ids = summary["scenario_id"].astype(str).head(1).tolist()
        active_id = selected_ids[0]

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

    if show_overview:
        tabs = st.tabs(["方案总览", "能量流向", "运行时序", "经济性分析"])
        with tabs[0]:
            _render_overview(st, selected_summary, active_row, representative, economy_summary)
        with tabs[1]:
            _render_energy_flow(st, active_hourly, active_row)
        with tabs[2]:
            _render_operation(st, active_hourly)
        with tabs[3]:
            _render_economy(st, selected_summary, active_id, economy_summary)
    else:
        tabs = st.tabs(["能量流向", "运行时序", "经济性分析"])
        with tabs[0]:
            _render_energy_flow(st, active_hourly, active_row)
        with tabs[1]:
            _render_operation(st, active_hourly)
        with tabs[2]:
            _render_economy(st, selected_summary, active_id, economy_summary)
