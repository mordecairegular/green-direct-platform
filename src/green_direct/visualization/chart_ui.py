"""Streamlit UI for chart analysis."""

from __future__ import annotations

from typing import Callable

import pandas as pd

from green_direct.visualization.chart_contracts import ChartResult
from green_direct.visualization.export_charts import (
    chart_to_excel_bytes,
    chart_to_html_bytes,
    chart_to_meta_markdown,
    try_chart_to_png_bytes,
)
from green_direct.visualization.heatmap_charts import build_heatmap_chart
from green_direct.visualization.multi_scenario_charts import (
    build_curtailment_vs_self_consumption_scatter,
    build_multi_battery_cycles_comparison,
    build_multi_capacity_comparison,
    build_multi_policy_comparison,
    build_multi_renewable_flow_comparison,
)
from green_direct.visualization.single_scenario_charts import (
    build_abnormal_day_table,
    build_battery_power_chart,
    build_daily_balance_chart,
    build_grid_exchange_chart,
    build_indicator_cards,
    build_monthly_load_source_chart,
    build_monthly_renewable_flow_chart,
    build_policy_bar_chart,
    build_soc_chart,
)


def _show_result(st, result: ChartResult, key_prefix: str) -> None:
    st.subheader(result.chart_name)
    for warning in result.warnings:
        st.warning(warning)
    if result.figure is not None:
        st.plotly_chart(result.figure, use_container_width=True, key=f"{key_prefix}_{result.chart_id}")
    elif result.data.empty:
        st.info("该图表当前无法生成。")
    if result.note:
        st.caption(result.note)
    with st.expander("图表数据与导出", expanded=False):
        if not result.data.empty:
            st.dataframe(result.data, use_container_width=True)
        c1, c2, c3, c4 = st.columns(4)
        html_bytes = chart_to_html_bytes(result)
        c1.download_button(
            "HTML",
            data=html_bytes,
            file_name=f"{result.chart_id}.html",
            mime="text/html",
            disabled=not html_bytes,
            key=f"{key_prefix}_{result.chart_id}_html",
        )
        c2.download_button(
            "Excel 数据",
            data=chart_to_excel_bytes(result),
            file_name=f"{result.chart_id}_data.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"{key_prefix}_{result.chart_id}_xlsx",
        )
        c3.download_button(
            "口径说明",
            data=chart_to_meta_markdown(result).encode("utf-8-sig"),
            file_name=f"{result.chart_id}_meta.md",
            mime="text/markdown",
            key=f"{key_prefix}_{result.chart_id}_md",
        )
        png_bytes, png_error = try_chart_to_png_bytes(result)
        c4.download_button(
            "PNG",
            data=png_bytes or b"",
            file_name=f"{result.chart_id}.png",
            mime="image/png",
            disabled=png_bytes is None,
            key=f"{key_prefix}_{result.chart_id}_png",
        )
        if png_error:
            st.caption(png_error)


def _summary_for_ids(summary: pd.DataFrame, scenario_ids: list[str]) -> pd.DataFrame:
    if "scenario_id" not in summary.columns:
        return pd.DataFrame()
    return summary[summary["scenario_id"].astype(str).isin([str(item) for item in scenario_ids])].copy()


def render_chart_analysis(st, batch_result, summary: pd.DataFrame) -> None:
    """Render chart analysis section inside the existing Streamlit app."""

    st.markdown("---")
    st.header("图表分析")
    st.caption("图表模块仅读取本次测算的方案汇总和逐小时明细，做展示性聚合与导出，不修改计算结果。")

    scenario_ids = [str(item) for item in batch_result.hourly_details.keys()]
    if not scenario_ids:
        st.info("当前没有可用于图表分析的逐小时明细。")
        return

    tabs = st.tabs(["方案选择", "单方案诊断", "典型日 / 热力图", "储能与电网", "多方案对比"])
    with tabs[0]:
        default_ids = scenario_ids[: min(3, len(scenario_ids))]
        selected_ids = st.multiselect("选择需要分析的方案", scenario_ids, default=default_ids, key="chart_selected_ids")
        if not selected_ids:
            st.info("请选择至少一个方案。")
            return
        st.dataframe(_summary_for_ids(summary, selected_ids), use_container_width=True, hide_index=True)

    selected_ids = st.session_state.get("chart_selected_ids", scenario_ids[:1])
    active_id = selected_ids[0]
    active_hourly = batch_result.hourly_details[active_id]
    active_summary = _summary_for_ids(summary, [active_id])
    active_row = active_summary.iloc[0] if not active_summary.empty else pd.Series({"scenario_id": active_id})

    with tabs[1]:
        for index, builder in enumerate(
            [
                lambda: build_indicator_cards(active_row),
                lambda: build_policy_bar_chart(active_row),
                lambda: build_monthly_load_source_chart(active_hourly),
                lambda: build_monthly_renewable_flow_chart(active_hourly),
                lambda: build_abnormal_day_table(active_hourly),
            ]
        ):
            _show_result(st, builder(), f"single_{index}_{active_id}")

    with tabs[2]:
        c1, c2, c3 = st.columns(3)
        day_mode = c1.selectbox("日期选择方式", ["首日", "自选日期", "最大负荷日", "最大弃电日", "最大下网日", "SOC 最低日", "SOC 最高日"])
        min_date = pd.to_datetime(active_hourly["timestamp"], errors="coerce").dt.date.dropna().min()
        selected_date = c2.date_input("自选日期", value=min_date)
        heatmap_field = c3.selectbox(
            "热力图指标",
            ["grid_import_power", "grid_export_power", "curtail_power", "soc_end", "load_power", "renewable_power"],
        )
        _show_result(
            st,
            build_daily_balance_chart(
                active_hourly,
                mode=day_mode,
                selected_date=selected_date if day_mode == "自选日期" else None,
            ),
            f"daily_{active_id}",
        )
        _show_result(st, build_heatmap_chart(active_hourly, heatmap_field), f"heatmap_{active_id}")

    with tabs[3]:
        for index, builder in enumerate(
            [
                lambda: build_soc_chart(active_hourly),
                lambda: build_battery_power_chart(active_hourly),
                lambda: build_grid_exchange_chart(active_hourly),
            ]
        ):
            _show_result(st, builder(), f"energy_{index}_{active_id}")

    with tabs[4]:
        selected_summary = _summary_for_ids(summary, selected_ids)
        builders: list[Callable[[pd.DataFrame], ChartResult]] = [
            build_multi_policy_comparison,
            build_multi_capacity_comparison,
            build_multi_renewable_flow_comparison,
            build_curtailment_vs_self_consumption_scatter,
            build_multi_battery_cycles_comparison,
        ]
        for index, builder in enumerate(builders):
            _show_result(st, builder(selected_summary), f"multi_{index}")
