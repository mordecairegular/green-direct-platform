"""Streamlit app for V0.1 technical batch simulation."""

from __future__ import annotations

import html
from io import BytesIO
from numbers import Number
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

SRC_ROOT = str(Path(__file__).resolve().parents[2])
if sys.path[0] != SRC_ROOT:  # pragma: no cover - import path guard for Streamlit and installed packages
    sys.path.insert(0, SRC_ROOT)
PROJECT_ROOT = Path(__file__).resolve().parents[3]

from green_direct.batch.batch_runner import estimate_scenario_count
from green_direct.economy import (
    AvoidedGridPurchaseParams,
    EconomicParams,
    OtherOperatingRevenueItem,
    calc_avoided_grid_purchase_cash_price,
)
from green_direct.export.csv_exporter import export_hourly_details_zip
from green_direct.export.excel_exporter import export_summary_excel
from green_direct.io.read_curves import read_csv_auto_encoding
from green_direct.io.validators import DataValidationError
from green_direct.models.params import BessParams, DataCleaningParams, PerformanceParams, PolicyParams
from green_direct.recommendation import (
    ENGINEERING_VIEW_LABELS,
    SINGLE_ENTITY_VIEW_LABELS,
)
from green_direct.services import (
    RecommendationInputSnapshot,
    StudyResult,
    TechnicalStudyInput,
    build_recommendation_study,
    run_economic_study,
    run_technical_study,
)
from green_direct.ui.field_labels import FIELD_LABELS, format_display_frame, localize_columns, mapping_frame
from green_direct.visualization.chart_data import adapt_hourly, select_typical_season_day
from green_direct.visualization.export_charts import chart_to_html_bytes, chart_to_meta_markdown
from green_direct.visualization.heatmap_charts import build_heatmap_chart
from green_direct.visualization.chart_ui import render_chart_analysis
from green_direct.visualization.multi_scenario_charts import (
    build_curtailment_vs_self_consumption_scatter,
    build_multi_capacity_comparison,
    build_multi_policy_comparison,
    build_multi_renewable_flow_comparison,
)
from green_direct.visualization.single_scenario_charts import (
    build_daily_balance_chart,
    build_grid_exchange_chart,
    build_monthly_load_source_chart,
    build_monthly_renewable_flow_chart,
    build_policy_bar_chart,
    build_soc_chart,
)


TIME_COLUMN_CANDIDATES = ["时间", "timestamp", "time", "日期时间", "日期", "datetime"]
VALUE_COLUMN_CANDIDATES = {
    "负荷": ["负荷", "数值(万千瓦)", "load", "load_power", "负荷功率"],
    "光伏": ["光伏", "光伏（标幺）", "pv", "pv_pu"],
    "风电": ["风电", "风电（标幺）", "wind", "wind_pu"],
}
FILE_KEYWORDS = {
    "负荷": ["负荷", "load", "用电"],
    "光伏": ["光伏", "pv", "solar"],
    "风电": ["风电", "wind"],
}
WORKFLOW_PAGES = ["欢迎页", "方案仿真", "经济性测算", "方案推荐及图表概览", "图表下载和报告生成"]
WORKFLOW_PAGE_KEY = "workflow_page"
WORKFLOW_PAGE_TARGET_KEY = "_workflow_page_target"
WORKFLOW_PAGE_ALIASES = {
    "技术仿真": "方案仿真",
    "经济性评价": "经济性测算",
    "推荐方案与详细分析": "方案推荐及图表概览",
    "方案推荐与图表概览": "方案推荐及图表概览",
    "图表与报告": "图表下载和报告生成",
}
WORKFLOW_PAGE_META = {
    "欢迎页": {
        "index": "01",
        "title": "欢迎页",
        "subtitle": "查看项目状态、数据准备情况和下一步工作入口。",
    },
    "方案仿真": {
        "index": "02",
        "title": "方案仿真",
        "subtitle": "上传曲线、配置候选方案池和政策约束，生成技术仿真结果。",
    },
    "经济性测算": {
        "index": "03",
        "title": "经济性测算",
        "subtitle": "读取技术结果，输入经济参数并计算已实现的经济性视角。",
    },
    "方案推荐及图表概览": {
        "index": "04",
        "title": "方案推荐及图表概览",
        "subtitle": "围绕代表方案展示推荐席位、关键指标、能量流向和运行曲线。",
    },
    "图表下载和报告生成": {
        "index": "05",
        "title": "图表下载和报告生成",
        "subtitle": "集中导出复核数据、图表包和简版说明报告。",
    },
}

WORKBENCH_CSS = """
<style>
:root {
    --gd-navy: #08213f;
    --gd-navy-2: #0b2b52;
    --gd-line: #d9e2ec;
    --gd-muted: #667085;
    --gd-text: #172033;
    --gd-surface: #ffffff;
    --gd-bg: #f4f7fb;
    --gd-accent: #d8a20c;
    --gd-green: #16a34a;
    --gd-blue: #2474c7;
    --gd-orange: #d97706;
}
[data-testid="stAppViewContainer"] {
    background: var(--gd-bg);
}
[data-testid="stHeader"] {
    display: none;
    height: 0;
    visibility: hidden;
}
#MainMenu,
[data-testid="stToolbar"],
[data-testid="stDecoration"],
[data-testid="stStatusWidget"] {
    display: none !important;
}
.block-container {
    padding-top: 0.55rem;
    padding-bottom: 1.4rem;
    padding-left: 1.35rem;
    padding-right: 1.35rem;
    max-width: none;
}
[data-testid="stSidebar"] {
    background: var(--gd-navy);
    min-width: 248px !important;
    max-width: 248px !important;
    width: 248px !important;
}
[data-testid="stSidebar"] > div {
    background: var(--gd-navy);
    border-right: 1px solid rgba(255, 255, 255, 0.08);
    min-width: 248px !important;
    max-width: 248px !important;
    width: 248px !important;
}
[data-testid="stSidebar"] * {
    color: #e6eef8;
}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
    color: #b9c7da;
}
[data-testid="stSidebar"] .stButton > button {
    width: 100%;
    min-height: 45px;
    justify-content: flex-start;
    color: #dbeafe !important;
    background: rgba(255, 255, 255, 0.055);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 7px;
    padding: 8px 11px;
    font-weight: 680;
    line-height: 1.18;
}
[data-testid="stSidebar"] .stButton > button:hover {
    color: #ffffff !important;
    background: rgba(255, 255, 255, 0.11);
    border-color: rgba(255, 255, 255, 0.18);
}
.gd-nav-item {
    display: flex;
    align-items: center;
    gap: 10px;
    min-height: 45px;
    padding: 8px 11px;
    border-radius: 7px;
    margin: 0 0 6px 0;
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.1);
}
.gd-nav-item.gd-nav-active {
    background: #15529d;
    border-color: rgba(255, 255, 255, 0.22);
    box-shadow: inset 3px 0 0 #ff5b5b;
}
.gd-nav-index {
    color: #ffffff;
    font-size: 12px;
    font-weight: 760;
    min-width: 25px;
}
.gd-nav-title {
    color: #ffffff;
    font-size: 13px;
    font-weight: 720;
}
.stButton > button,
[data-testid="stDownloadButton"] button {
    border-radius: 7px;
    min-height: 38px;
    border-color: #cbd5e1;
    color: var(--gd-text);
    font-weight: 650;
}
.stButton > button:hover,
[data-testid="stDownloadButton"] button:hover {
    border-color: #94a3b8;
    color: var(--gd-navy-2);
}
.stButton > button[kind="primary"] {
    background: #ef4444;
    border-color: #ef4444;
    color: #ffffff;
}
.stButton > button[kind="primary"]:hover {
    background: #dc2626;
    border-color: #dc2626;
    color: #ffffff;
}
[data-testid="stSidebar"] div[data-testid="stButton"] button,
[data-testid="stSidebar"] button[kind="secondary"] {
    width: 100% !important;
    min-height: 45px !important;
    justify-content: flex-start !important;
    color: #dbeafe !important;
    background: rgba(255, 255, 255, 0.055) !important;
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    border-radius: 7px !important;
    padding: 8px 11px !important;
    font-weight: 680 !important;
    line-height: 1.18 !important;
}
[data-testid="stSidebar"] div[data-testid="stButton"] button:hover,
[data-testid="stSidebar"] button[kind="secondary"]:hover {
    color: #ffffff !important;
    background: rgba(255, 255, 255, 0.11) !important;
    border-color: rgba(255, 255, 255, 0.18) !important;
}
div[data-testid="stMetric"] {
    background: var(--gd-surface);
    border: 1px solid var(--gd-line);
    border-radius: 8px;
    padding: 12px 14px;
}
div[data-testid="stMetric"] label {
    color: var(--gd-muted) !important;
}
div[data-testid="stMetricValue"] {
    color: var(--gd-text);
    font-size: 1.45rem;
}
div[data-testid="stExpander"] {
    border-color: var(--gd-line);
    border-radius: 8px;
    background: var(--gd-surface);
}
.gd-sidebar-brand {
    padding: 12px 4px 16px 4px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.12);
    margin-bottom: 14px;
}
.gd-sidebar-brand .gd-brand-title {
    color: #ffffff;
    font-size: 18px;
    font-weight: 760;
    line-height: 1.25;
}
.gd-sidebar-brand .gd-brand-subtitle {
    color: #a9b8cf;
    font-size: 12px;
    margin-top: 6px;
}
.gd-sidebar-status {
    margin-top: 18px;
    padding: 12px;
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 8px;
    background: rgba(255, 255, 255, 0.05);
}
.gd-sidebar-status-row {
    display: flex;
    justify-content: space-between;
    gap: 10px;
    font-size: 12px;
    margin: 6px 0;
}
.gd-topbar {
    display: grid;
    grid-template-columns: minmax(240px, 1.25fr) repeat(6, minmax(110px, 0.75fr));
    gap: 1px;
    border: 1px solid var(--gd-line);
    background: var(--gd-line);
    border-radius: 8px;
    overflow: hidden;
    margin-bottom: 10px;
}
.gd-topbar-cell {
    background: var(--gd-surface);
    padding: 8px 11px;
    min-height: 54px;
}
.gd-topbar-label {
    color: var(--gd-muted);
    font-size: 12px;
    line-height: 1.2;
}
.gd-topbar-value {
    color: var(--gd-text);
    font-size: 14px;
    font-weight: 720;
    margin-top: 4px;
}
.gd-status-pill {
    display: inline-flex;
    align-items: center;
    min-height: 24px;
    padding: 2px 8px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 650;
    white-space: nowrap;
}
.gd-status-ok { background: #e8f7ee; color: #116b35; }
.gd-status-pending { background: #eef2f7; color: #475467; }
.gd-status-warn { background: #fff4dd; color: #8a5200; }
.gd-page-heading {
    display: flex;
    align-items: flex-start;
    gap: 14px;
    margin: 10px 0 12px 0;
}
.gd-page-index {
    min-width: 44px;
    height: 34px;
    border-radius: 6px;
    background: var(--gd-navy-2);
    color: #ffffff;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 760;
    font-size: 14px;
}
.gd-page-title {
    color: var(--gd-text);
    font-size: 24px;
    font-weight: 760;
    line-height: 1.2;
}
.gd-page-subtitle {
    color: var(--gd-muted);
    margin-top: 5px;
    font-size: 14px;
}
.gd-section-eyebrow {
    color: var(--gd-muted);
    font-size: 12px;
    letter-spacing: 0;
    margin-bottom: 3px;
}
.gd-section-title {
    color: var(--gd-text);
    font-size: 17px;
    font-weight: 720;
    margin-bottom: 4px;
}
.gd-section-copy {
    color: var(--gd-muted);
    font-size: 12px;
    margin-bottom: 8px;
}
.gd-callout {
    border-left: 4px solid var(--gd-accent);
    background: #fffaf0;
    color: #344054;
    padding: 10px 12px;
    border-radius: 6px;
    margin: 10px 0 14px 0;
    font-size: 13px;
}
.gd-rec-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(265px, 1fr));
    gap: 12px;
    margin: 8px 0 10px 0;
}
.gd-rec-card {
    background: #ffffff;
    border: 1px solid var(--gd-line);
    border-radius: 8px;
    padding: 11px 13px;
    min-height: 186px;
}
.gd-rec-card:first-child {
    border-color: #d8a20c;
    box-shadow: inset 0 3px 0 #d8a20c;
}
.gd-rec-top {
    display: flex;
    justify-content: space-between;
    gap: 10px;
    align-items: flex-start;
}
.gd-rec-titleline {
    display: flex;
    align-items: center;
    gap: 9px;
}
.gd-rec-rank {
    min-width: 24px;
    height: 24px;
    border-radius: 5px;
    background: var(--gd-navy-2);
    color: #ffffff;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-size: 13px;
    font-weight: 760;
}
.gd-rec-labels {
    color: var(--gd-blue);
    font-size: 12px;
    font-weight: 700;
    line-height: 1.25;
}
.gd-rec-id {
    color: var(--gd-text);
    font-size: 18px;
    font-weight: 760;
    margin-top: 3px;
}
.gd-rec-capacity {
    color: #475467;
    font-size: 12px;
    margin-top: 3px;
}
.gd-rec-reason {
    color: #344054;
    font-size: 12px;
    min-height: 29px;
    margin: 7px 0 6px 0;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
}
.gd-rec-metrics {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 6px 8px;
}
.gd-rec-metric {
    border-top: 1px solid #edf2f7;
    padding-top: 6px;
}
.gd-rec-metric span {
    display: block;
    color: var(--gd-muted);
    font-size: 11px;
}
.gd-rec-metric strong {
    color: var(--gd-text);
    font-size: 14px;
    overflow-wrap: anywhere;
}
.gd-risk-note {
    color: #7a4a00;
    background: #fff7e6;
    border-radius: 6px;
    padding: 7px 9px;
    margin-top: 10px;
    font-size: 12px;
}
.gd-dashboard-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin: 8px 0 8px 0;
}
.gd-dashboard-title {
    color: var(--gd-text);
    font-size: 18px;
    font-weight: 760;
}
.gd-dashboard-subtitle {
    color: var(--gd-muted);
    font-size: 12px;
    margin-top: 2px;
}
.gd-chart-panel-head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 10px;
    min-height: 42px;
    margin-bottom: 4px;
}
.gd-chart-panel-title {
    color: var(--gd-text);
    font-size: 16px;
    font-weight: 740;
}
.gd-chart-panel-note {
    color: var(--gd-muted);
    font-size: 12px;
    margin-top: 2px;
}
.gd-chart-panel-tag {
    border: 1px solid var(--gd-line);
    border-radius: 999px;
    color: #475467;
    background: #f8fafc;
    font-size: 12px;
    padding: 3px 9px;
    white-space: nowrap;
}
.gd-download-handoff {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 12px;
    margin: 10px 0 12px 0;
}
.gd-download-card {
    border: 1px solid var(--gd-line);
    border-radius: 8px;
    background: #ffffff;
    padding: 13px;
    min-height: 104px;
}
.gd-download-card strong {
    display: block;
    color: var(--gd-text);
    font-size: 15px;
    margin-bottom: 6px;
}
.gd-download-card span {
    color: var(--gd-muted);
    font-size: 12px;
    line-height: 1.45;
}
.gd-export-selected {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 14px;
    border: 1px solid var(--gd-line);
    border-radius: 8px;
    background: #ffffff;
    padding: 11px 13px;
    margin: 8px 0 12px 0;
}
.gd-export-selected strong {
    color: var(--gd-text);
}
.gd-export-selected span {
    color: var(--gd-muted);
    font-size: 12px;
}
.gd-export-panel-head {
    min-height: 56px;
    margin-bottom: 8px;
}
.gd-export-panel-head strong {
    display: block;
    color: var(--gd-text);
    font-size: 16px;
    margin-bottom: 4px;
}
.gd-export-panel-head span {
    color: var(--gd-muted);
    font-size: 12px;
    line-height: 1.4;
}
.gd-export-note {
    color: var(--gd-muted);
    font-size: 12px;
    margin-top: 8px;
}
.gd-bottom-status {
    display: flex;
    flex-wrap: wrap;
    gap: 10px 18px;
    align-items: center;
    border-top: 1px solid var(--gd-line);
    color: #475467;
    font-size: 12px;
    padding-top: 10px;
    margin-top: 12px;
}
.gd-bottom-status strong {
    color: var(--gd-text);
}
.gd-sim-file-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 8px;
    margin: 8px 0 2px 0;
}
.gd-sim-file-card {
    border: 1px solid #e5edf6;
    border-radius: 7px;
    background: #f8fafc;
    padding: 8px 9px;
    min-height: 72px;
}
.gd-sim-file-card.gd-ready {
    background: #f0f9f4;
    border-color: #bbebcb;
}
.gd-sim-file-card strong {
    display: block;
    color: var(--gd-text);
    font-size: 13px;
}
.gd-sim-file-card span {
    display: block;
    color: var(--gd-muted);
    font-size: 11px;
    line-height: 1.35;
    margin-top: 4px;
    overflow-wrap: anywhere;
}
.gd-sim-kpis {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 8px;
    margin: 8px 0 0 0;
}
.gd-sim-kpi {
    border: 1px solid #e5edf6;
    border-radius: 7px;
    background: #f8fafc;
    padding: 8px 9px;
    min-height: 58px;
}
.gd-sim-kpi span {
    display: block;
    color: var(--gd-muted);
    font-size: 11px;
}
.gd-sim-kpi strong {
    display: block;
    color: var(--gd-text);
    font-size: 18px;
    line-height: 1.2;
    margin-top: 3px;
}
.gd-run-state {
    border: 1px solid #e5edf6;
    border-radius: 8px;
    background: #ffffff;
    padding: 10px 12px;
    margin: 8px 0 10px 0;
    color: #475467;
    font-size: 13px;
}
.gd-run-state strong {
    color: var(--gd-text);
}
.gd-field-note {
    color: var(--gd-muted);
    font-size: 12px;
    line-height: 1.45;
}
@media (max-width: 900px) {
    .gd-topbar {
        grid-template-columns: 1fr;
    }
    .gd-rec-grid {
        grid-template-columns: 1fr;
    }
    .gd-rec-metrics,
    .gd-download-handoff,
    .gd-sim-file-grid,
    .gd-sim-kpis {
        grid-template-columns: 1fr;
    }
}
</style>
"""


class _LocalSampleFile:
    def __init__(self, path: Path):
        self.path = path
        self.name = path.name

    def getvalue(self) -> bytes:
        return self.path.read_bytes()


def _safe_html_text(value) -> str:
    return html.escape("" if value is None else str(value))


def _inject_workbench_style(st) -> None:
    st.markdown(WORKBENCH_CSS, unsafe_allow_html=True)


def _is_present(value) -> bool:
    if value is None:
        return False
    try:
        return not bool(pd.isna(value))
    except (TypeError, ValueError):
        return True


def _compact_number(value, digits: int = 2) -> str:
    if not _is_present(value):
        return "-"
    try:
        text = f"{float(value):,.{digits}f}"
        return text.rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return str(value)


def _status_pill(text: str, state: str) -> str:
    state_class = {
        "ok": "gd-status-ok",
        "warn": "gd-status-warn",
        "pending": "gd-status-pending",
    }.get(state, "gd-status-pending")
    return f'<span class="gd-status-pill {state_class}">{_safe_html_text(text)}</span>'


def _topbar_cell(label: str, value: str, detail: str | None = None) -> str:
    detail_html = f'<div class="gd-topbar-label">{_safe_html_text(detail)}</div>' if detail else ""
    return (
        '<div class="gd-topbar-cell">'
        f'<div class="gd-topbar-label">{_safe_html_text(label)}</div>'
        f'<div class="gd-topbar-value">{value}</div>'
        f"{detail_html}"
        "</div>"
    )


def _data_range_status(batch_result) -> tuple[str, str]:
    if not batch_result or not getattr(batch_result, "hourly_details", None):
        return "待仿真", "未生成逐小时明细"

    for hourly in batch_result.hourly_details.values():
        if not isinstance(hourly, pd.DataFrame) or hourly.empty or "timestamp" not in hourly.columns:
            continue
        timestamps = pd.to_datetime(hourly["timestamp"], errors="coerce").dropna()
        if timestamps.empty:
            continue
        start = timestamps.min().strftime("%Y-%m-%d")
        end = timestamps.max().strftime("%Y-%m-%d")
        return f"{start} ~ {end}", f"{len(timestamps)} 小时"

    return "待复核", "逐小时明细缺少 timestamp"


def _render_project_status_bar(st, current_page: str) -> None:
    batch_result = st.session_state.get("batch_result")
    economy_result = st.session_state.get("economy_v1_result")
    summary = _summary_from_batch_result(batch_result) if batch_result else pd.DataFrame()

    scenario_count = int(getattr(batch_result, "scenario_count", 0)) if batch_result else 0
    passed_count = (
        int(summary["pass_policy"].sum())
        if not summary.empty and "pass_policy" in summary.columns
        else 0
    )
    economy_done = bool(economy_result and not economy_result.get("summary", pd.DataFrame()).empty)
    recommendation_ready = _workflow_step_done(st, "方案推荐及图表概览")
    page_meta = WORKFLOW_PAGE_META.get(current_page, WORKFLOW_PAGE_META["欢迎页"])
    data_range, data_range_detail = _data_range_status(batch_result)

    cells = [
        _topbar_cell(
            "项目状态",
            "绿电直连 / 微电网方案策划",
            "工程工作台模式",
        ),
        _topbar_cell(
            "当前模块",
            f"{_safe_html_text(page_meta['index'])} {_safe_html_text(page_meta['title'])}",
        ),
        _topbar_cell(
            "方案仿真",
            _status_pill("已完成", "ok") if batch_result else _status_pill("未完成", "pending"),
        ),
        _topbar_cell(
            "经济性测算",
            _status_pill("已完成", "ok") if economy_done else _status_pill("待测算", "pending"),
        ),
        _topbar_cell(
            "方案池",
            f"{scenario_count} 个 / {passed_count} 达标",
            "推荐图表仅围绕代表方案",
        ),
        _topbar_cell(
            "数据时间",
            _safe_html_text(data_range),
            data_range_detail,
        ),
    ]
    cells.append(
        _topbar_cell(
            "推荐与导出",
            _status_pill("可查看", "ok") if recommendation_ready else _status_pill("待结果", "pending"),
        )
    )
    st.markdown(f'<div class="gd-topbar">{"".join(cells)}</div>', unsafe_allow_html=True)


def _render_page_heading(st, page: str, subtitle: str | None = None) -> None:
    meta = WORKFLOW_PAGE_META.get(page, WORKFLOW_PAGE_META["欢迎页"])
    st.markdown(
        f"""
        <div class="gd-page-heading">
          <div class="gd-page-index">{_safe_html_text(meta["index"])}</div>
          <div>
            <div class="gd-page-title">{_safe_html_text(meta["title"])}</div>
            <div class="gd-page-subtitle">{_safe_html_text(subtitle or meta["subtitle"])}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_section_intro(st, eyebrow: str, title: str, copy: str | None = None) -> None:
    copy_html = f'<div class="gd-section-copy">{_safe_html_text(copy)}</div>' if copy else ""
    st.markdown(
        f"""
        <div class="gd-section-eyebrow">{_safe_html_text(eyebrow)}</div>
        <div class="gd-section-title">{_safe_html_text(title)}</div>
        {copy_html}
        """,
        unsafe_allow_html=True,
    )


def _boolean_input(st, label: str, *, value: bool = False, help: str | None = None, key: str | None = None) -> bool:
    toggle = getattr(st, "toggle", None)
    if callable(toggle):
        return bool(toggle(label, value=value, help=help, key=key))
    return bool(st.checkbox(label, value=value, help=help, key=key))


def _render_curve_overview_cards(st, curve_files: dict[str, object], curve_columns: dict[str, tuple[str | None, str | None]]) -> None:
    cards: list[str] = []
    for curve_name in ["负荷", "光伏", "风电"]:
        file_obj = curve_files.get(curve_name)
        time_col, value_col = curve_columns.get(curve_name, (None, None))
        ready = file_obj is not None and time_col is not None and value_col is not None
        file_name = getattr(file_obj, "name", "未选择") if file_obj is not None else "未选择"
        detail = (
            f"时间列 {time_col or '待确认'} / 数值列 {value_col or '待确认'}"
            if file_obj is not None
            else "批量上传或使用 Demo 后自动识别"
        )
        cards.append(
            f'<div class="gd-sim-file-card {"gd-ready" if ready else ""}">'
            f"<strong>{_safe_html_text(curve_name)}</strong>"
            f"<span>{_safe_html_text(file_name)}</span>"
            f"<span>{_safe_html_text(detail)}</span>"
            "</div>"
        )
    st.markdown(f'<div class="gd-sim-file-grid">{"".join(cards)}</div>', unsafe_allow_html=True)


def _render_simulation_kpis(st, scenario_count: int | None, scenario_grid: dict | None, duration_text: str) -> None:
    count_text = "-" if scenario_count is None else f"{scenario_count:,}"
    if scenario_grid:
        pv_text = (
            f"{_compact_number(scenario_grid['pv_capacity']['start'])}-"
            f"{_compact_number(scenario_grid['pv_capacity']['end'])}"
        )
        wind_text = (
            f"{_compact_number(scenario_grid['wind_capacity']['start'])}-"
            f"{_compact_number(scenario_grid['wind_capacity']['end'])}"
        )
    else:
        pv_text = "-"
        wind_text = "-"
    st.markdown(
        f"""
        <div class="gd-sim-kpis">
          <div class="gd-sim-kpi"><span>当前表单方案数</span><strong>{_safe_html_text(count_text)}</strong></div>
          <div class="gd-sim-kpi"><span>光伏 / 风电范围</span><strong>{_safe_html_text(pv_text)} / {_safe_html_text(wind_text)}</strong></div>
          <div class="gd-sim-kpi"><span>储能时长</span><strong>{_safe_html_text(duration_text)}</strong></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_run_state(st, ready: bool, scenario_count: int | None, *, has_result: bool = False) -> None:
    if ready:
        text = f"输入已就绪，可开始测算。当前表单候选方案数 {scenario_count:,}。" if scenario_count is not None else "输入已就绪，可开始测算。"
        state = "就绪"
    elif has_result:
        text = "当前已有仿真结果可继续经济测算；如需重新测算，请补齐或启用曲线输入。"
        state = "已有结果"
    else:
        text = "请补齐负荷、光伏、风电三条曲线，并确认必要列名。"
        state = "待输入"
    st.markdown(
        f'<div class="gd-run-state"><strong>{_safe_html_text(state)}</strong> · {_safe_html_text(text)}</div>',
        unsafe_allow_html=True,
    )


def _capacity_config_text(row: pd.Series) -> str:
    return (
        f"光伏 {_compact_number(row.get('pv_capacity'))} 万kW · "
        f"风电 {_compact_number(row.get('wind_capacity'))} 万kW · "
        f"储能 {_compact_number(row.get('bess_power'))}/{_compact_number(row.get('bess_energy'))} 万kW/万kWh"
    )


def _recommendation_metric(label: str, value, *, rate: bool = False, digits: int = 2) -> str:
    text = _format_report_value(value, rate=rate, digits=digits)
    return (
        '<div class="gd-rec-metric">'
        f"<span>{_safe_html_text(label)}</span>"
        f"<strong>{_safe_html_text(text)}</strong>"
        "</div>"
    )


def _recommendation_economy_metric(row: pd.Series) -> str:
    labels = str(row.get("recommendation_labels", ""))
    if "负荷侧" in labels and _is_present(row.get("load_side_annual_benefit")):
        return _recommendation_metric("负荷侧收益", row.get("load_side_annual_benefit"), digits=0)
    if "同一主体" in labels and _is_present(row.get("single_entity_firr_pre_tax")):
        return _recommendation_metric("同一主体FIRR", row.get("single_entity_firr_pre_tax"), rate=True)
    if "电源侧" in labels and _is_present(row.get("firr")):
        return _recommendation_metric("电源侧FIRR", row.get("firr"), rate=True)
    for label, field, is_rate, digits in [
        ("同一主体FIRR", "single_entity_firr_pre_tax", True, 2),
        ("电源侧FIRR", "firr", True, 2),
        ("负荷侧收益", "load_side_annual_benefit", False, 0),
    ]:
        if _is_present(row.get(field)):
            return _recommendation_metric(label, row.get(field), rate=is_rate, digits=digits)
    return _recommendation_metric("经济性", None)


def _recommendation_status_display(status) -> tuple[str, str]:
    normalized = str(status or "").strip().lower()
    if normalized in {"selected", "ok", "recommended"}:
        return "已入选", "ok"
    if normalized in {"no_candidate", "failed", "fail", "blocked"}:
        return "无候选", "warn"
    if normalized in {"pending", "not_sortable", "not_ready"}:
        return "待排序", "pending"
    return str(status or "待复核"), "pending"


def _render_recommendation_cards(st, portfolio: pd.DataFrame) -> None:
    cards: list[str] = []
    for display_index, (_, row) in enumerate(portfolio.head(6).iterrows(), start=1):
        labels = row.get("recommendation_labels", "推荐方案")
        status = row.get("recommendation_status", "selected")
        status_text, status_state = _recommendation_status_display(status)
        rank = row.get("recommendation_rank", display_index)
        rank_text = _compact_number(rank, digits=0)
        risk_note = row.get("risk_note")
        risk_html = (
            f'<div class="gd-risk-note">{_safe_html_text(risk_note)}</div>'
            if _is_present(risk_note) and str(risk_note).strip()
            else ""
        )
        metric_html = "".join(
            [
                _recommendation_metric("绿电占比", row.get("green_load_rate"), rate=True),
                _recommendation_metric("自发自用率", row.get("self_use_rate"), rate=True),
                _recommendation_metric("弃电率", row.get("curtail_rate"), rate=True),
                _recommendation_metric("上网比例", row.get("export_rate"), rate=True),
                _recommendation_economy_metric(row),
            ]
        )
        cards.append(
            '<div class="gd-rec-card">'
            '<div class="gd-rec-top">'
            "<div>"
            '<div class="gd-rec-titleline">'
            f'<span class="gd-rec-rank">{_safe_html_text(rank_text)}</span>'
            f'<div class="gd-rec-labels">{_safe_html_text(labels)}</div>'
            "</div>"
            f'<div class="gd-rec-id">{_safe_html_text(row.get("scenario_id", "-"))}</div>'
            f'<div class="gd-rec-capacity">{_safe_html_text(_capacity_config_text(row))}</div>'
            "</div>"
            f"{_status_pill(status_text, status_state)}"
            "</div>"
            f'<div class="gd-rec-reason">{_safe_html_text(row.get("recommendation_reason", ""))}</div>'
            f'<div class="gd-rec-metrics">{metric_html}</div>'
            f"{risk_html}"
            "</div>"
        )
    st.markdown(f'<div class="gd-rec-grid">{"".join(cards)}</div>', unsafe_allow_html=True)


def _recommendation_portfolio_display_columns(portfolio: pd.DataFrame) -> list[str]:
    columns = [
        "recommendation_rank",
        "recommendation_labels",
        "recommendation_status",
        "scenario_id",
        "方案类型",
        "pv_capacity",
        "wind_capacity",
        "bess_energy",
        "load_side_annual_benefit",
        "load_side_saving_price",
        "single_entity_firr_pre_tax",
        "single_entity_static_payback_year",
        "firr",
        "power_side_firr_threshold",
        "construction_cash_outflow",
        "green_load_rate",
        "self_use_rate",
        "curtail_rate",
        "export_rate",
        "recommendation_reason",
        "risk_note",
    ]
    return [column for column in columns if column in portfolio.columns]


def _render_recommendation_detail_tables(st, recommendation_result) -> None:
    if recommendation_result is None:
        return
    portfolio = getattr(recommendation_result, "portfolio", pd.DataFrame())
    load_side_detail = getattr(recommendation_result, "load_side_detail", pd.DataFrame())
    if not isinstance(portfolio, pd.DataFrame) or portfolio.empty:
        return

    with st.expander("高级：推荐组合明细与负荷侧复核", expanded=False):
        display_columns = _recommendation_portfolio_display_columns(portfolio)
        st.dataframe(
            localize_columns(format_display_frame(portfolio[display_columns])),
            use_container_width=True,
            hide_index=True,
        )
        if isinstance(load_side_detail, pd.DataFrame) and not load_side_detail.empty:
            st.caption(
                "负荷侧明细用于复核可成交性筛选、节约电费单价和电源侧 FIRR 门槛；下载集中在“图表下载和报告生成”页。"
            )
            detail_columns = [
                "scenario_id",
                "pass_policy",
                "load_side_tradable",
                "load_side_tradable_status",
                "self_use_energy",
                "load_side_avoided_charge_price",
                "green_power_settlement_price_with_vat",
                "load_side_saving_price",
                "load_side_environmental_value",
                "load_side_annual_benefit",
                "firr",
                "firr_status",
                "power_side_firr_threshold",
                "green_load_rate",
                "curtail_rate",
                "construction_cash_outflow",
            ]
            detail_columns = [column for column in detail_columns if column in load_side_detail.columns]
            st.dataframe(
                localize_columns(format_display_frame(load_side_detail[detail_columns])),
                use_container_width=True,
                hide_index=True,
            )
        _display_mapping_expander(st, display_columns, "推荐组合字段对应关系")


def _load_sample_curve_files() -> tuple[dict[str, _LocalSampleFile], list[str]]:
    sample_dir = PROJECT_ROOT / "samples"
    assigned: dict[str, _LocalSampleFile] = {}
    messages: list[str] = []
    if not sample_dir.exists():
        return assigned, ["未找到 samples 示例数据目录。"]
    for path in sample_dir.glob("*.csv"):
        curve_name = _match_curve_from_filename(path.name)
        if curve_name is None:
            messages.append(f"示例文件 `{path.name}` 未能识别曲线类型。")
            continue
        assigned[curve_name] = _LocalSampleFile(path)
    missing = {"负荷", "光伏", "风电"} - set(assigned)
    if missing:
        messages.append(f"示例数据缺少：{', '.join(sorted(missing))}。")
    return assigned, messages


def _load_preview(uploaded_file):
    if uploaded_file is None:
        return None, None
    raw = uploaded_file.getvalue()
    df, encoding = read_csv_auto_encoding(raw)
    return df, encoding


def _match_curve_from_filename(filename: str) -> str | None:
    normalized = filename.lower()
    for curve_name, keywords in FILE_KEYWORDS.items():
        if any(keyword.lower() in normalized for keyword in keywords):
            return curve_name
    return None


def _auto_assign_curve_files(files) -> tuple[dict[str, object], list[str]]:
    assigned: dict[str, object] = {}
    messages: list[str] = []
    for uploaded_file in files or []:
        curve_name = _match_curve_from_filename(uploaded_file.name)
        if curve_name is None:
            messages.append(f"未能识别文件 `{uploaded_file.name}`，请使用单独上传入口。")
            continue
        if curve_name in assigned:
            messages.append(f"`{curve_name}`匹配到多个文件，已使用 `{assigned[curve_name].name}`，忽略 `{uploaded_file.name}`。")
            continue
        assigned[curve_name] = uploaded_file
    return assigned, messages


def _guess_time_column(df: pd.DataFrame | None) -> str | None:
    if df is None:
        return None
    lower_map = {str(column).lower(): column for column in df.columns}
    for candidate in TIME_COLUMN_CANDIDATES:
        if candidate.lower() in lower_map:
            return lower_map[candidate.lower()]
    for column in df.columns:
        parsed = pd.to_datetime(df[column], errors="coerce")
        if parsed.notna().mean() > 0.95:
            return column
    return None


def _guess_value_column(df: pd.DataFrame | None, time_col: str | None, curve_name: str) -> str | None:
    if df is None:
        return None
    lower_map = {str(column).lower(): column for column in df.columns}
    for candidate in VALUE_COLUMN_CANDIDATES[curve_name]:
        if candidate.lower() in lower_map and lower_map[candidate.lower()] != time_col:
            return lower_map[candidate.lower()]
    candidates = []
    for column in df.columns:
        if column == time_col:
            continue
        numeric = pd.to_numeric(df[column], errors="coerce")
        if numeric.notna().mean() > 0.95:
            candidates.append(column)
    if len(candidates) == 1:
        return candidates[0]
    return None


def _column_selector(
    st,
    label: str,
    df: pd.DataFrame | None,
    guessed: str | None,
    *,
    show_guess_caption: bool = True,
):
    if df is None:
        return None
    columns = list(df.columns)
    if guessed in columns:
        if show_guess_caption:
            st.caption(f"{label}：已自动识别为 `{guessed}`")
        return guessed
    return st.selectbox(label, columns, index=0)


def _range_inputs(st, label: str, defaults: tuple[float, float, float]) -> dict:
    c1, c2, c3 = st.columns(3)
    start = c1.number_input(f"{label}起始", value=float(defaults[0]), min_value=0.0, step=1.0)
    end = c2.number_input(f"{label}结束", value=float(defaults[1]), min_value=0.0, step=1.0)
    step = c3.number_input(f"{label}步长", value=float(defaults[2]), min_value=0.000001, step=1.0)
    return {"start": start, "end": end, "step": step}


def _trim_number(value: float) -> str:
    return f"{value:g}"


def _float_text_input(
    st,
    label: str,
    value: float,
    *,
    min_value: float | None = None,
    max_value: float | None = None,
    help: str | None = None,
) -> float:
    raw = st.text_input(label, value=_trim_number(value), help=help)
    try:
        parsed = float(str(raw).replace(",", "").strip())
    except ValueError:
        st.error(f"{label} 必须填写数字。")
        st.stop()
    if min_value is not None and parsed < min_value:
        st.error(f"{label} 不能小于 {_trim_number(min_value)}。")
        st.stop()
    if max_value is not None and parsed > max_value:
        st.error(f"{label} 不能大于 {_trim_number(max_value)}。")
        st.stop()
    return parsed


def _percent_text_input(
    st,
    label: str,
    value_percent: float,
    *,
    min_value: float = 0.0,
    max_value: float = 100.0,
    help: str | None = None,
) -> float:
    return _float_text_input(
        st,
        label,
        value_percent,
        min_value=min_value,
        max_value=max_value,
        help=help,
    ) / 100


def _optional_percent_text_input(
    st,
    label: str,
    value_percent: float,
    *,
    min_value: float = 0.0,
    max_value: float = 100.0,
    help: str | None = None,
) -> float | None:
    raw = st.text_input(label, value=_trim_number(value_percent), help=help)
    if str(raw).strip() == "":
        return None
    try:
        parsed = float(str(raw).replace(",", "").strip())
    except ValueError:
        st.error(f"{label} 必须填写数字，或留空表示不对相关席位排序。")
        st.stop()
    if parsed < min_value:
        st.error(f"{label} 不能小于 {_trim_number(min_value)}。")
        st.stop()
    if parsed > max_value:
        st.error(f"{label} 不能大于 {_trim_number(max_value)}。")
        st.stop()
    return parsed / 100


def _build_download_payloads(batch_result, config_snapshot: dict):
    with TemporaryDirectory() as tmp:
        excel_path = export_summary_excel(
            batch_result.summary,
            tmp,
            config_snapshot=config_snapshot,
            warnings=batch_result.warnings,
            filename_prefix="scenario_summary",
        )
        zip_path = export_hourly_details_zip(batch_result.hourly_details, tmp)
        return {
            "excel_name": excel_path.name,
            "excel_bytes": excel_path.read_bytes(),
            "zip_name": zip_path.name,
            "zip_bytes": zip_path.read_bytes(),
        }


def _curve_status(label: str, df: pd.DataFrame | None, encoding: str | None, time_col: str | None, value_col: str | None):
    if df is None or time_col is None or value_col is None:
        return None
    parsed = pd.to_datetime(df[time_col], errors="coerce")
    numeric = pd.to_numeric(df[value_col], errors="coerce")
    status = {
        "曲线": label,
        "编码": encoding,
        "小时数": len(df),
        "开始时间": parsed.min(),
        "结束时间": parsed.max(),
        "空值/非数字点": int(numeric.isna().sum()),
        "负值点": int((numeric < 0).sum()),
        "大于1点": int((numeric > 1).sum()) if label in {"光伏", "风电"} else 0,
    }
    return status


def _scenario_type(row: pd.Series) -> str:
    has_pv = row["pv_capacity"] > 0
    has_wind = row["wind_capacity"] > 0
    has_bess = row["bess_energy"] > 0
    if not has_bess:
        if has_pv and not has_wind:
            return "纯光伏方案"
        if has_wind and not has_pv:
            return "纯风电方案"
        if has_pv and has_wind:
            return "风光无储方案"
        return "无新能源无储能方案"
    if has_pv and not has_wind:
        return "光储方案"
    if has_wind and not has_pv:
        return "风储方案"
    if has_pv and has_wind:
        return "风光储方案"
    return "仅储能方案"


def _add_scenario_type(summary: pd.DataFrame) -> pd.DataFrame:
    if "方案类型" in summary.columns:
        return summary
    result = summary.copy()
    has_pv = result["pv_capacity"] > 0
    has_wind = result["wind_capacity"] > 0
    has_bess = result["bess_energy"] > 0
    result["方案类型"] = "仅储能方案"
    result.loc[~has_bess & ~has_pv & ~has_wind, "方案类型"] = "无新能源无储能方案"
    result.loc[~has_bess & has_pv & ~has_wind, "方案类型"] = "纯光伏方案"
    result.loc[~has_bess & has_wind & ~has_pv, "方案类型"] = "纯风电方案"
    result.loc[~has_bess & has_pv & has_wind, "方案类型"] = "风光无储方案"
    result.loc[has_bess & has_pv & ~has_wind, "方案类型"] = "光储方案"
    result.loc[has_bess & has_wind & ~has_pv, "方案类型"] = "风储方案"
    result.loc[has_bess & has_pv & has_wind, "方案类型"] = "风光储方案"
    return result


def _apply_filters(summary: pd.DataFrame, only_passed: bool, scheme_types: list[str], sort_label: str) -> pd.DataFrame:
    display = summary.copy()
    if only_passed:
        display = display[display["pass_policy"] == True]  # noqa: E712
    if scheme_types:
        display = display[display["方案类型"].isin(scheme_types)]
    sort_options = {
        "绿电占比从高到低": ("green_load_rate", False),
        "弃电率从低到高": ("curtail_rate", True),
        "自发自用率从高到低": ("self_use_rate", False),
        "上网比例从低到高": ("export_rate", True),
        "储能容量从小到大": ("bess_energy", True),
    }
    column, ascending = sort_options[sort_label]
    return display.sort_values(column, ascending=ascending).reset_index(drop=True)


def _format_summary_for_display(summary: pd.DataFrame) -> pd.DataFrame:
    return localize_columns(format_display_frame(summary))


def _display_mapping_expander(st, columns: list[str], label: str = "字段对应关系") -> None:
    with st.expander(label, expanded=False):
        st.dataframe(mapping_frame(columns), use_container_width=True, hide_index=True)


def _get_download_payloads(st, batch_result, config_snapshot: dict):
    signature = (id(batch_result), len(batch_result.summary), len(batch_result.hourly_details))
    cached = st.session_state.get("download_payloads")
    if cached and cached.get("signature") == signature:
        return cached["payloads"]
    with st.spinner("正在准备下载文件..."):
        payloads = _build_download_payloads(batch_result, config_snapshot)
        st.session_state["download_payloads"] = {"signature": signature, "payloads": payloads}
    return payloads


def _parse_specific_years(raw: object) -> tuple[int, ...]:
    text = "" if raw is None else str(raw).strip()
    if not text:
        return ()
    years: list[int] = []
    for part in re.split(r"[,，;；|\s]+", text):
        if not part:
            continue
        years.append(int(float(part)))
    return tuple(year for year in years if year > 0)


def _build_other_revenue_items(raw: pd.DataFrame) -> tuple[OtherOperatingRevenueItem, ...]:
    items: list[OtherOperatingRevenueItem] = []
    if raw.empty:
        return ()
    for _, row in raw.iterrows():
        amount = pd.to_numeric(row.get("金额(万元/年)", 0.0), errors="coerce")
        if pd.isna(amount) or abs(float(amount)) < 1e-12:
            continue
        name = str(row.get("名称", "")).strip() or "其他经营收入"
        active_rule = str(row.get("发生规则", "every_year")).strip() or "every_year"
        vat_rate = pd.to_numeric(row.get("销项税率", 0.13), errors="coerce")
        if pd.isna(vat_rate):
            vat_rate = 0.13
        items.append(
            OtherOperatingRevenueItem(
                name=name,
                amount_with_vat=float(amount),
                vat_rate=float(vat_rate),
                active_rule=active_rule,
                specific_years=_parse_specific_years(row.get("指定年份")),
            )
        )
    return tuple(items)


def _build_excel_bytes(sheets: dict[str, pd.DataFrame]) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        for sheet_name, data in sheets.items():
            data.to_excel(writer, sheet_name=sheet_name[:31], index=False)
    return output.getvalue()


SINGLE_ENTITY_ANNUAL_COLUMNS = [
    "scenario_id",
    "year",
    "operation_year",
    "period_type",
    "self_use_energy",
    "grid_export_energy",
    "net_avoided_grid_cost_price",
    "avoided_grid_purchase_cash_price",
    "self_use_saving",
    "avoided_grid_purchase_cash_saving",
    "environmental_value",
    "grid_export_revenue_without_vat",
    "other_external_revenue_without_vat",
    "operating_cost_basis",
    "bess_replacement_basis",
    "bess_replacement_cash_outflow_with_vat",
    "initial_investment_basis",
    "construction_cash_outflow_with_vat",
    "pre_tax_net_cash_flow",
    "cumulative_net_cash_flow",
    "discount_factor",
    "discounted_net_cash_flow",
    "cumulative_discounted_net_cash_flow",
]


def _label_for_column(column: str) -> str:
    return FIELD_LABELS.get(column, column)


def _value_from_frame(frame: pd.DataFrame, scenario_id: str, column: str):
    if frame.empty or column not in frame.columns or "scenario_id" not in frame.columns:
        return ""
    matched = frame[frame["scenario_id"].astype(str) == str(scenario_id)]
    if matched.empty:
        return ""
    value = matched.iloc[0][column]
    if pd.isna(value):
        return ""
    return value


def _build_scenario_info_frame(
    scenario_id: str,
    technical_summary: pd.DataFrame,
    economic_summary: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []

    def add(category: str, column: str, note: str = "") -> None:
        rows.append(
            {
                "类别": category,
                "项目": _label_for_column(column),
                "英文字段": column,
                "值": _value_from_frame(technical_summary, scenario_id, column)
                if column in technical_summary.columns
                else _value_from_frame(economic_summary, scenario_id, column),
                "说明": note,
            }
        )

    rows.append({"类别": "方案", "项目": "方案编号", "英文字段": "scenario_id", "值": scenario_id, "说明": ""})
    add("方案", "方案类型")
    add("容量", "pv_capacity")
    add("容量", "wind_capacity")
    add("容量", "bess_power")
    add("容量", "bess_energy")
    add("政策/技术指标", "pass_policy")
    add("政策/技术指标", "fail_reasons")
    add("政策/技术指标", "green_load_rate")
    add("政策/技术指标", "self_use_rate")
    add("政策/技术指标", "export_rate")
    add("政策/技术指标", "curtail_rate")
    add("电量", "self_use_energy")
    add("电量", "grid_export_energy")
    add("电量", "curtail_energy")
    add("储能更换", "annual_equivalent_cycles")
    add("储能更换", "replacement_year", "按循环寿命估算的更换年；经济性还会与电池日历寿命取早。")
    add("同一主体经济性", "single_entity_firr_pre_tax")
    add("同一主体经济性", "single_entity_firr_status")
    add("同一主体经济性", "single_entity_fnpv_pre_tax")
    add("同一主体经济性", "initial_investment_basis")
    add("同一主体经济性", "construction_cash_outflow_with_vat")
    add("同一主体经济性", "net_avoided_grid_cost_price")
    add("同一主体经济性", "annual_self_use_saving")
    add("同一主体经济性", "bess_replacement_operation_years")
    return pd.DataFrame(rows)


def _single_entity_field_descriptions(columns: list[str]) -> pd.DataFrame:
    index_by_column = {column: idx for idx, column in enumerate(columns, start=1)}

    def n(column: str) -> str:
        return str(index_by_column[column])

    descriptions = {
        "scenario_id": "方案编号，用于与方案汇总表、逐小时明细表关联。",
        "year": "项目年份。0 为建设期，1 至 N 为运营期。",
        "operation_year": "运营年。建设期为 0。",
        "period_type": "期间类型：construction 为建设期，operation 为运营期。",
        "self_use_energy": "来自技术仿真的自发自用电量，运营期各年按代表年结果重复。",
        "grid_export_energy": "来自技术仿真的上网电量，运营期各年按代表年结果重复。",
        "net_avoided_grid_cost_price": "外部购电净成本单价。表示同一主体口径下每 1 kWh 自发自用绿电替代外部购电带来的税前净节费；简化模式为用户直接输入。组价模式公式：外部购电净成本单价=原外部购网电电量类成本单价-绿电直连自发自用仍需缴纳费用单价。",
        "avoided_grid_purchase_cash_price": "少付电网电费现金单价。同一主体简化模式下与净成本单价相同；组价模式下为含税/附加现金口径，仅辅助展示，不作为负荷侧可成交收益的固定价输入。",
        "self_use_saving": f"{n('self_use_saving')}={n('self_use_energy')}×{n('net_avoided_grid_cost_price')}。进入税前 FIRR 的自发自用购电节费。",
        "avoided_grid_purchase_cash_saving": f"{n('avoided_grid_purchase_cash_saving')}={n('self_use_energy')}×{n('avoided_grid_purchase_cash_price')}。少付电网电量电费现金额，仅辅助展示，不进入税前 FIRR。",
        "environmental_value": f"{n('environmental_value')}={n('self_use_energy')}×环境价值单价。默认环境价值单价为 0。",
        "grid_export_revenue_without_vat": f"{n('grid_export_revenue_without_vat')}={n('grid_export_energy')}×上网含税电价÷(1+销项税率)。",
        "other_external_revenue_without_vat": "其他外部收益，不含税口径。来自其他经营收入设置。",
        "operating_cost_basis": "运行成本评价基础。当前 V1 运行成本不拆进项税。",
        "bess_replacement_basis": f"储能更换评价基础。可抵扣时，约等于 {n('bess_replacement_cash_outflow_with_vat')}÷(1+储能更换进项税率)；用于税前 FIRR。",
        "bess_replacement_cash_outflow_with_vat": "储能更换现金流出，含税展示口径。约等于储能容量×储能单位造价×储能更换投资比例，仅在触发更换年份发生。",
        "initial_investment_basis": "Year 0 初始投资评价基础。可抵扣时为含税建设投资扣除进项税后的金额，进入税前 FIRR。",
        "construction_cash_outflow_with_vat": "Year 0 含税建设投资现金流出，辅助展示，不直接作为税前 FIRR 的评价基础。",
        "pre_tax_net_cash_flow": f"Year 0：{n('pre_tax_net_cash_flow')}=-{n('initial_investment_basis')}；运营期：{n('pre_tax_net_cash_flow')}={n('self_use_saving')}+{n('environmental_value')}+{n('grid_export_revenue_without_vat')}+{n('other_external_revenue_without_vat')}-{n('operating_cost_basis')}-{n('bess_replacement_basis')}。",
        "cumulative_net_cash_flow": f"截至当年的 {n('pre_tax_net_cash_flow')} 累计值。",
        "discount_factor": "折现系数 = 1÷(1+折现率)^年份。",
        "discounted_net_cash_flow": f"{n('discounted_net_cash_flow')}={n('pre_tax_net_cash_flow')}×{n('discount_factor')}。",
        "cumulative_discounted_net_cash_flow": f"截至当年的 {n('discounted_net_cash_flow')} 累计值。",
    }
    return pd.DataFrame(
        [
            {
                "序号": index_by_column[column],
                "英文字段": column,
                "中文表头": _label_for_column(column),
                "计算/含义说明": descriptions.get(column, ""),
            }
            for column in columns
        ]
    )


def _build_single_entity_annual_workbook_bytes(
    *,
    scenario_id: str,
    annual: pd.DataFrame,
    technical_summary: pd.DataFrame,
    economic_summary: pd.DataFrame,
) -> bytes:
    columns = [column for column in SINGLE_ENTITY_ANNUAL_COLUMNS if column in annual.columns]
    numbered_names = {column: f"{idx}. {_label_for_column(column)}" for idx, column in enumerate(columns, start=1)}
    annual_numbered = annual[columns].rename(columns=numbered_names)
    scenario_info = _build_scenario_info_frame(scenario_id, technical_summary, economic_summary)
    field_descriptions = _single_entity_field_descriptions(columns)

    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        scenario_info.to_excel(writer, sheet_name="方案说明", index=False)
        annual_numbered.to_excel(writer, sheet_name="年度现金流", index=False)
        field_descriptions.to_excel(writer, sheet_name="字段说明", index=False)

        workbook = writer.book
        wrap = workbook.add_format({"text_wrap": True, "valign": "top"})
        for sheet_name in ["方案说明", "年度现金流", "字段说明"]:
            worksheet = writer.sheets[sheet_name]
            worksheet.freeze_panes(1, 0)
            worksheet.set_column(0, 0, 12)
            worksheet.set_column(1, 1, 24)
            worksheet.set_column(2, 2, 28)
            worksheet.set_column(3, 3, 18)
            worksheet.set_column(4, 4, 48, wrap)
        writer.sheets["年度现金流"].freeze_panes(1, 4)
        writer.sheets["字段说明"].set_column(3, 3, 90, wrap)
    return output.getvalue()


def _merge_result_context(result_summary: pd.DataFrame, technical_summary: pd.DataFrame) -> pd.DataFrame:
    context_columns = [
        column
        for column in ["scenario_id", "方案类型", "pv_capacity", "wind_capacity", "bess_energy"]
        if column in technical_summary.columns
    ]
    display_summary = result_summary.copy()
    if len(context_columns) > 1:
        display_summary = display_summary.merge(
            technical_summary[context_columns].drop_duplicates("scenario_id"),
            on="scenario_id",
            how="left",
        )
    return display_summary


def _render_recommendation_v1(
    st,
    summary: pd.DataFrame,
    power_economy_summary: pd.DataFrame,
    single_entity_summary: pd.DataFrame | None,
    economic_params: EconomicParams,
    load_side_avoided_charge_price: float,
    green_power_settlement_price_with_vat: float,
    environmental_value_per_kwh: float,
    min_power_side_acceptable_firr: float | None,
):
    _render_section_intro(
        st,
        "推荐组合",
        "推荐方案",
        (
            "读取技术汇总和经济性结果生成代表席位；不改变逐小时调度，重复命中席位会合并标签。"
        ),
    )

    single_entity_label_to_key = {label: key for key, label in SINGLE_ENTITY_VIEW_LABELS.items()}
    view_label_to_key = {label: key for key, label in ENGINEERING_VIEW_LABELS.items()}
    with st.expander("推荐席位设置", expanded=False):
        c1, c2 = st.columns(2)
        single_entity_view_label = c1.selectbox(
            "同一主体推荐视角",
            list(single_entity_label_to_key.keys()),
            index=0,
            help="默认按 FIRR 最高；也可切换为动态回收期最短，用于查看更偏快速回收的方案。",
        )
        engineering_view_label = c2.selectbox(
            "工程代表方案视角",
            list(view_label_to_key.keys()),
            index=0,
            help="第四个推荐席位的工程视角。默认政策达标最小投资，可切换低弃电、高绿电占比、高自发自用。",
        )
    single_entity_view = single_entity_label_to_key[single_entity_view_label]
    engineering_view = view_label_to_key[engineering_view_label]

    recommendation_inputs = RecommendationInputSnapshot(
        economic_params=economic_params,
        load_side_avoided_charge_price=load_side_avoided_charge_price,
        green_power_settlement_price_with_vat=green_power_settlement_price_with_vat,
        environmental_value_per_kwh=environmental_value_per_kwh,
        min_power_side_acceptable_firr=min_power_side_acceptable_firr,
    )
    recommendation_result = build_recommendation_study(
        summary,
        power_economy_summary,
        recommendation_inputs,
        single_entity_summary=single_entity_summary,
        single_entity_view=single_entity_view,
        engineering_view=engineering_view,
    )
    study_result = st.session_state.get("study_result")
    if isinstance(study_result, StudyResult):
        st.session_state["study_result"] = study_result.with_recommendation_result(recommendation_result)
    portfolio = recommendation_result.portfolio

    if portfolio.empty:
        st.info("当前没有可展示的推荐结果。")
        return recommendation_result
    if min_power_side_acceptable_firr is None:
        st.warning("电源侧最低可接受 FIRR 已留空，负荷侧可成交收益席位不参与默认排序。")

    _render_recommendation_cards(st, portfolio)

    return recommendation_result


def _render_data_status(st, statuses: list[dict]) -> None:
    status_df = pd.DataFrame(statuses)
    if status_df.empty:
        return

    has_incomplete = len(statuses) < 3
    has_invalid_length = any(item["小时数"] not in {8760, 8784} for item in statuses)
    has_high_pu = any(item["大于1点"] for item in statuses)
    has_negative = any(item["负值点"] for item in statuses)

    if has_incomplete or has_invalid_length:
        st.error("数据状态：需要复核。存在缺失曲线或小时数不符合 8760/8784。")
    elif has_high_pu:
        st.warning("数据状态：可计算，但标幺曲线存在大于 1 的点，请确认容量基准。")
    elif has_negative:
        st.info("数据状态：可计算。发现负标幺值，将按站用电口径参与计算。")
    else:
        st.success("数据状态：三条曲线已识别，小时数和基础格式正常。")

    with st.expander("查看数据状态详情", expanded=False):
        st.dataframe(status_df, use_container_width=True, hide_index=True)
        for item in statuses:
            st.caption(
                f"{item['曲线']}：{item['小时数']} 小时，"
                f"{item['开始时间']} 至 {item['结束时间']}。"
            )
            if item["大于1点"]:
                st.warning(f"{item['曲线']}标幺值曲线存在数值大于 1 的情况，共 {item['大于1点']} 个点。")
            if item["负值点"]:
                st.info(f"{item['曲线']}曲线存在负值，共 {item['负值点']} 个点，将按站用电参与计算。")


def _render_economy_v1(
    st,
    summary: pd.DataFrame,
    bess_calendar_life_years: float = 15.0,
    *,
    render_recommendation: bool = True,
) -> None:
    _render_page_heading(st, "经济性测算", "经济性测算仅读取方案汇总结果，不重新计算逐小时调度。")
    economy_notice = st.session_state.pop("_economy_notice", None)
    if economy_notice:
        st.success(economy_notice)

    with st.expander("经济性参数工作台", expanded=True):
        st.markdown("#### 基本参数")
        c1, c2, c3 = st.columns(3)
        operation_years = int(c1.number_input("运营期（年）", value=25, min_value=1, max_value=40, step=1))
        discount_rate = _percent_text_input(c2, "折现率（%）", 6, min_value=-99, max_value=100)
        min_power_side_acceptable_firr = _optional_percent_text_input(
            c3,
            "电源侧最低可接受 FIRR（%）",
            7,
            min_value=0,
            max_value=100,
            help="用于负荷侧可成交收益席位筛选。留空时，该席位不参与默认排序。",
        )

        st.markdown("##### Year 0 建设投资")
        c1, c2, c3, c4 = st.columns(4)
        wind_capex = _float_text_input(c1, "风电单位造价（元/kW，含税）", 4500, min_value=0.0)
        pv_capex = _float_text_input(
            c2,
            "光伏单位造价（元/kW，含税）",
            2500,
            min_value=0.0,
            help="需与光伏标幺曲线容量基准匹配；直流侧曲线填直流侧造价，交流侧曲线填交流侧造价。",
        )
        bess_capex = _float_text_input(c3, "储能单位造价（元/kWh，含税）", 900, min_value=0.0)
        dedicated_connection_line = _float_text_input(c4, "送出线路工程投资（万元，含税）", 0, min_value=0.0)

        c1, c2 = st.columns(2)
        other_fixed_asset = _float_text_input(c1, "其他固定资产投资（万元，含税）", 0, min_value=0.0)
        construction_vat_rate = _percent_text_input(c2, "建设投资进项税率（%）", 10)

        st.markdown("#### 成本费用")
        c1, c2, c3, c4 = st.columns(4)
        wind_om = _float_text_input(c1, "风电运维成本（元/kW/年）", 50, min_value=0.0)
        pv_om = _float_text_input(c2, "光伏运维成本（元/kW/年）", 25, min_value=0.0)
        bess_om = _float_text_input(c3, "储能运维成本（元/kW/年）", 18, min_value=0.0)
        other_operating_cost = _float_text_input(c4, "其他运行成本（万元/年）", 0, min_value=0.0)

        st.markdown("##### 储能更换")
        st.caption("储能更换发生年份以日历寿命和循环寿命哪个先到为准；更换后重新开始计算下一次更换。")
        c1, c2 = st.columns(2)
        replacement_ratio = _percent_text_input(c1, "储能更换投资比例（%）", 50)
        replacement_vat_rate = _percent_text_input(c2, "储能更换进项税率（%）", 13)
        replacement_calendar_life = float(bess_calendar_life_years)

        st.markdown("#### 收入和税金")
        c1, c2, c3, c4 = st.columns(4)
        grid_export_price = _float_text_input(c1, "上网电价（元/kWh，含税）", 0.25, min_value=0.0)
        self_use_price = _float_text_input(
            c2,
            "绿电结算价（元/kWh，含税）",
            0.40,
            min_value=0.0,
            help="原“自发自用电价”。电源侧视角中作为绿电售电收入，负荷侧视角中作为绿电购电成本。非用户到户电价，不含输配电价、政府基金及附加、系统运行费和容需量电费等。",
        )
        net_avoided_grid_cost_price = _float_text_input(
            c3,
            "外部购电净成本单价（元/kWh）",
            0.50,
            min_value=0.0,
            help=(
                "用于同一主体口径估算每 1 kWh 自发自用绿电替代外部购电带来的税前净节费。"
                "简化模式下直接使用本输入值；组价模式公式：外部购电净成本单价="
                "原外部购网电电量类成本单价-绿电直连自发自用仍需缴纳费用单价。"
                "不等同于负荷侧比较绿电结算价时使用的到户电能量全价。"
            ),
        )
        environmental_value = _float_text_input(c4, "环境价值单价（元/kWh）", 0, min_value=0.0)

        c1, c2, c3 = st.columns(3)
        output_vat_rate = _percent_text_input(c1, "销项税率（%）", 13)
        income_tax_rate = _percent_text_input(c2, "企业所得税率（%）", 25)
        urban_area = c3.selectbox("城建税地区", ["县城、镇 5%", "市区 7%", "其他 1%"])
        urban_tax_rate = {"市区 7%": 0.07, "县城、镇 5%": 0.05, "其他 1%": 0.01}[urban_area]

        with st.expander("高级：其他经营收入", expanded=False):
            st.caption("一般项目可不填。可输入负值；负值在 V1 中不产生进项税，按收入抵减或额外经营性支出处理。")
            default_other = pd.DataFrame(
                [
                    {
                        "名称": "",
                        "金额(万元/年)": 0.0,
                        "销项税率": 0.13,
                        "发生规则": "every_year",
                        "指定年份": "",
                    }
                ]
            )
            other_revenue_df = st.data_editor(
                st.session_state.get("economy_other_revenue_df", default_other),
                num_rows="dynamic",
                use_container_width=True,
                key="economy_other_revenue_editor",
            )
            st.session_state["economy_other_revenue_df"] = other_revenue_df

        st.markdown("#### 电费构成参数")
        with st.expander("高级：电费清单组价和价格曲线", expanded=False):
            use_grid_price_build_up = st.checkbox(
                "按电费清单组价覆盖外部购电净成本和负荷侧可减少费用",
                value=False,
                help="默认使用上方固定值；勾选后按电费清单中的电量电费项目分别推导同一主体净成本口径和负荷侧现金口径。",
            )
            if use_grid_price_build_up:
                c1, c2, c3 = st.columns(3)
                energy_market_price = _float_text_input(c1, "电能量/市场购电价格（元/kWh，含税）", 0.40, min_value=0.0)
                line_loss_price = _float_text_input(c2, "上网环节线损费用（元/kWh，含税）", 0, min_value=0.0)
                system_operation_fee = _float_text_input(c3, "系统运行费用（元/kWh，含税）", 0, min_value=0.0)
                c1, c2, c3 = st.columns(3)
                transmission_distribution_tariff = _float_text_input(c1, "输配电价（元/kWh，含税）", 0.15, min_value=0.0)
                gov_fund_surcharge = _float_text_input(c2, "政府性基金及附加（元/kWh）", 0.03, min_value=0.0, help="按无增值税电量附加处理。")
                grid_purchase_vat_rate = _percent_text_input(c3, "电网购电增值税率（%）", 13)
                st.caption("以下为绿电直连自发自用电量仍需缴纳的费用。1192 号文系统运行费暂按下网电量缴纳，自发自用绿电不在这里设置系统运行费扣减。")
                c1, c2 = st.columns(2)
                retained_transmission_distribution_tariff = _float_text_input(
                    c1,
                    "绿电仍缴输配电价（元/kWh，含税）",
                    transmission_distribution_tariff,
                    min_value=0.0,
                )
                retained_gov_fund_surcharge = _float_text_input(
                    c2,
                    "绿电仍缴政府性基金及附加（元/kWh）",
                    gov_fund_surcharge,
                    min_value=0.0,
                )
                net_avoided_grid_cost_price_for_calc = None
            else:
                energy_market_price = 0.0
                line_loss_price = 0.0
                system_operation_fee = 0.0
                transmission_distribution_tariff = 0.0
                gov_fund_surcharge = 0.0
                retained_transmission_distribution_tariff = 0.0
                retained_gov_fund_surcharge = 0.0
                grid_purchase_vat_rate = 0.13
                net_avoided_grid_cost_price_for_calc = net_avoided_grid_cost_price
            override_load_side_avoided_charge = st.checkbox(
                "单独覆盖负荷侧可减少购网费用单价",
                value=False,
                help=(
                    "默认由上方固定价或电费清单组价内部推导；只有负荷侧账单口径与同一主体净节费口径明显不同时才需要覆盖。"
                ),
            )
            if override_load_side_avoided_charge:
                load_side_avoided_charge_price_override = _float_text_input(
                    st,
                    "负荷侧可减少购网费用单价（元/kWh）",
                    net_avoided_grid_cost_price,
                    min_value=0.0,
                    help=(
                        "用于负荷侧可成交收益席位，表示绿电替代购网电后，负荷侧每 1 kWh "
                        "自发自用绿电可减少的电量类购网费用现金口径。"
                    ),
                )
            else:
                load_side_avoided_charge_price_override = None
            st.caption("容需量电费和力调电费 V1 默认不参与节费测算：它们通常不随自发自用电量按 kWh 线性变化，后续作为高级模型单独研究。")
            st.caption("绿电结算价曲线、外部购电净成本曲线和上网电价曲线后续按 CSV/Excel 上传处理，不做网页逐项录入。当前页面先使用固定价。")

    try:
        other_revenues = _build_other_revenue_items(other_revenue_df)
    except ValueError as exc:
        st.error(f"其他经营收入年份格式有误：{exc}")
        return

    params = EconomicParams(
        operation_years=operation_years,
        wind_capex_per_kw_with_vat=wind_capex,
        pv_capex_per_kw_with_vat=pv_capex,
        bess_capex_per_kwh_with_vat=bess_capex,
        dedicated_connection_line_investment_with_vat=dedicated_connection_line,
        other_fixed_asset_investment_with_vat=other_fixed_asset,
        construction_input_vat_rate=construction_vat_rate,
        wind_om_cost_per_kw_year=wind_om,
        pv_om_cost_per_kw_year=pv_om,
        bess_om_cost_per_kw_year=bess_om,
        other_operating_cost_with_vat=other_operating_cost,
        grid_export_price_with_vat=grid_export_price,
        self_use_price_with_vat=self_use_price,
        output_vat_rate=output_vat_rate,
        other_operating_revenues=other_revenues,
        bess_replacement_cost_ratio=replacement_ratio,
        bess_replacement_input_vat_rate=replacement_vat_rate,
        bess_calendar_life_years=replacement_calendar_life,
        urban_maintenance_tax_rate=urban_tax_rate,
        income_tax_rate=income_tax_rate,
        discount_rate=discount_rate,
    )
    avoided_grid_params = AvoidedGridPurchaseParams(
        net_avoided_grid_cost_price=net_avoided_grid_cost_price_for_calc,
        energy_market_price_with_vat=energy_market_price,
        line_loss_price_with_vat=line_loss_price,
        system_operation_fee_with_vat=system_operation_fee,
        transmission_distribution_tariff_with_vat=transmission_distribution_tariff,
        gov_fund_surcharge=gov_fund_surcharge,
        green_direct_retained_transmission_distribution_tariff_with_vat=retained_transmission_distribution_tariff,
        green_direct_retained_gov_fund_surcharge=retained_gov_fund_surcharge,
        grid_purchase_vat_rate=grid_purchase_vat_rate,
        environmental_value_per_kwh=environmental_value,
    )
    derived_load_side_avoided_charge_price = calc_avoided_grid_purchase_cash_price(
        avoided_grid_params
    )
    load_side_avoided_charge_price_for_calc = (
        load_side_avoided_charge_price_override
        if load_side_avoided_charge_price_override is not None
        else derived_load_side_avoided_charge_price
    )

    if st.button("计算经济性 V1（当前已实现视角）", key="run_economy_v1_all"):
        try:
            with st.spinner("正在计算电源侧和同一主体经济性年度现金流..."):
                economic_study_result = run_economic_study(
                    summary,
                    economic_params=params,
                    avoided_grid_params=avoided_grid_params,
                    load_side_avoided_charge_price=load_side_avoided_charge_price_for_calc,
                    green_power_settlement_price_with_vat=self_use_price,
                    environmental_value_per_kwh=environmental_value,
                    min_power_side_acceptable_firr=min_power_side_acceptable_firr,
                )
            st.session_state["economy_v1_result"] = {
                "summary": economic_study_result.power_summary,
                "annual_cashflows": economic_study_result.power_annual_cashflows,
            }
            st.session_state["single_entity_economy_result"] = {
                "summary": economic_study_result.single_entity_summary,
                "annual_cashflows": economic_study_result.single_entity_annual_cashflows,
            }
            st.session_state["recommendation_v1_inputs"] = economic_study_result.recommendation_inputs.to_session_dict()
            study_result = st.session_state.get("study_result")
            if isinstance(study_result, StudyResult):
                st.session_state["study_result"] = study_result.with_economic_result(economic_study_result)
            st.session_state.pop("download_payloads", None)
            st.session_state["_economy_notice"] = "经济性 V1 已计算，推荐页和导出页已可读取经济性结果。"
            st.rerun()
        except ValueError as exc:
            st.error(f"经济性参数有误：{exc}")

    economy_result = st.session_state.get("economy_v1_result")
    single_entity_result = st.session_state.get("single_entity_economy_result")
    if not economy_result and not single_entity_result:
        return

    if economy_result:
        economic_summary = economy_result["summary"]
        annual_cashflows = economy_result["annual_cashflows"]
        if not economic_summary.empty:
            display_economic_summary = _merge_result_context(economic_summary, summary)
            display_columns = [
                "scenario_id",
                "方案类型",
                "pv_capacity",
                "wind_capacity",
                "bess_energy",
                "fnpv",
                "firr",
                "firr_status",
                "static_payback_year",
                "dynamic_payback_year",
                "construction_cash_outflow",
                "dedicated_connection_line_investment_with_vat",
                "annual_operating_revenue_with_vat",
                "annual_operating_cost_with_vat",
                "bess_replacement_operation_year",
                "bess_replacement_operation_years",
                "bess_replacement_count",
            ]
            display_columns = [column for column in display_columns if column in display_economic_summary.columns]
            st.success("电源侧经济性 V1 已计算。技术方案汇总表仍保持纯技术指标；下载请前往“图表下载和报告生成”。")

            with st.expander("高级：电源侧经济性汇总复核表", expanded=False):
                st.dataframe(
                    localize_columns(format_display_frame(display_economic_summary[display_columns])),
                    use_container_width=True,
                    hide_index=True,
                )
                _display_mapping_expander(st, display_columns, "电源侧经济性汇总字段对应关系")

    if single_entity_result:
        single_entity_summary = single_entity_result["summary"]
        single_entity_annual_cashflows = single_entity_result["annual_cashflows"]
        if not single_entity_summary.empty:
            display_single_entity_summary = _merge_result_context(single_entity_summary, summary)
            single_entity_columns = [
                "scenario_id",
                "方案类型",
                "pv_capacity",
                "wind_capacity",
                "bess_energy",
                "single_entity_fnpv_pre_tax",
                "single_entity_firr_pre_tax",
                "single_entity_firr_status",
                "single_entity_static_payback_year",
                "single_entity_dynamic_payback_year",
                "initial_investment_basis",
                "construction_cash_outflow_with_vat",
                "annual_self_use_saving",
                "annual_avoided_grid_purchase_cash_saving",
                "annual_environmental_value",
                "annual_grid_export_revenue_without_vat",
                "annual_operating_cost_basis",
                "net_avoided_grid_cost_price",
                "avoided_grid_purchase_cash_price",
                "energy_market_price_with_vat",
                "line_loss_price_with_vat",
                "system_operation_fee_with_vat",
                "transmission_distribution_tariff_with_vat",
                "gov_fund_surcharge",
                "green_direct_retained_transmission_distribution_tariff_with_vat",
                "green_direct_retained_gov_fund_surcharge",
                "bess_replacement_operation_year",
                "bess_replacement_operation_years",
                "bess_replacement_count",
            ]
            single_entity_columns = [
                column for column in single_entity_columns if column in display_single_entity_summary.columns
            ]
            st.success("同一主体税前经济性已计算。该结果不并入技术方案概览表，也不覆盖电源侧经济性。")

            with st.expander("高级：同一主体税前经济性汇总复核表", expanded=False):
                st.dataframe(
                    localize_columns(format_display_frame(display_single_entity_summary[single_entity_columns])),
                    use_container_width=True,
                    hide_index=True,
                )
                _display_mapping_expander(st, single_entity_columns, "同一主体经济性汇总字段对应关系")

    if render_recommendation and economy_result and not economy_result["summary"].empty:
        recommendation_single_entity_summary = (
            single_entity_result["summary"]
            if single_entity_result and not single_entity_result["summary"].empty
            else None
        )
        _render_recommendation_v1(
            st,
            summary,
            economy_result["summary"],
            recommendation_single_entity_summary,
            economic_params=params,
            load_side_avoided_charge_price=load_side_avoided_charge_price_for_calc,
            green_power_settlement_price_with_vat=self_use_price,
            environmental_value_per_kwh=environmental_value,
            min_power_side_acceptable_firr=min_power_side_acceptable_firr,
        )


def _normalize_workflow_page(st) -> str:
    current = st.session_state.pop(
        WORKFLOW_PAGE_TARGET_KEY,
        st.session_state.get(WORKFLOW_PAGE_KEY, WORKFLOW_PAGES[0]),
    )
    normalized = WORKFLOW_PAGE_ALIASES.get(current, current)
    if normalized not in WORKFLOW_PAGES:
        normalized = WORKFLOW_PAGES[0]
    st.session_state[WORKFLOW_PAGE_KEY] = normalized
    return normalized


def _workflow_step_done(st, page: str) -> bool:
    if page in {"欢迎页", "方案仿真"}:
        return True
    batch_result = st.session_state.get("batch_result")
    if page == "经济性测算":
        return bool(batch_result)
    economy_result = st.session_state.get("economy_v1_result")
    economy_done = bool(economy_result and not economy_result.get("summary", pd.DataFrame()).empty)
    if page == "方案推荐及图表概览":
        return bool(batch_result) and economy_done
    if page == "图表下载和报告生成":
        return bool(batch_result)
    return False


def _render_workflow_navigation(st) -> str:
    page = _normalize_workflow_page(st)
    with st.sidebar:
        st.markdown(
            """
            <div class="gd-sidebar-brand">
              <div class="gd-brand-title">绿电直连<br/>微电网策划平台</div>
              <div class="gd-brand-subtitle">方案仿真 · 经济测算 · 推荐图表 · 报告导出</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        for workflow_item in WORKFLOW_PAGES:
            meta = WORKFLOW_PAGE_META[workflow_item]
            if workflow_item == page:
                st.markdown(
                    f"""
                    <div class="gd-nav-item gd-nav-active">
                      <div class="gd-nav-index">{_safe_html_text(meta["index"])}</div>
                      <div class="gd-nav-title">{_safe_html_text(meta["title"])}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            elif st.button(
                f"{meta['index']}  {meta['title']}",
                key=f"workflow_nav_{meta['index']}",
                help=meta["subtitle"],
            ):
                _go_to_workflow_page(st, workflow_item)
        batch_result = st.session_state.get("batch_result")
        economy_result = st.session_state.get("economy_v1_result")
        economy_done = bool(economy_result and not economy_result.get("summary", pd.DataFrame()).empty)
        st.markdown(
            f"""
            <div class="gd-sidebar-status">
              <div class="gd-sidebar-status-row"><span>方案仿真</span><strong>{'已完成' if batch_result else '未完成'}</strong></div>
              <div class="gd-sidebar-status-row"><span>经济测算</span><strong>{'已完成' if economy_done else '未完成'}</strong></div>
              <div class="gd-sidebar-status-row"><span>推荐图表</span><strong>{'可查看' if _workflow_step_done(st, '方案推荐及图表概览') else '待结果'}</strong></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    return page


def _go_to_workflow_page(st, page: str) -> None:
    # Queue the target so buttons can navigate without mutating a rendered widget key.
    st.session_state[WORKFLOW_PAGE_TARGET_KEY] = WORKFLOW_PAGE_ALIASES.get(page, page)
    rerun = getattr(st, "rerun", None)
    if callable(rerun):
        rerun()


def _get_bess_calendar_life_years(st) -> float:
    snapshot = st.session_state.get("config_snapshot", {})
    try:
        return float(snapshot.get("bess_calendar_life_years", 15.0))
    except (TypeError, ValueError):
        return 15.0


def _summary_from_batch_result(batch_result) -> pd.DataFrame:
    summary = batch_result.summary
    if summary.empty:
        return summary
    return _add_scenario_type(summary)


def _render_missing_step(st, target_page: str, message: str) -> None:
    st.info(message)
    if st.button(f"进入{target_page}", key=f"go_{target_page}"):
        _go_to_workflow_page(st, target_page)


def _render_welcome_page(st) -> None:
    _render_page_heading(
        st,
        "欢迎页",
        "当前版本优先打通方案仿真、经济性测算、推荐组合、图表概览和报告下载，不把全量枚举表作为主入口。",
    )

    batch_result = st.session_state.get("batch_result")
    economy_result = st.session_state.get("economy_v1_result")
    summary = _summary_from_batch_result(batch_result) if batch_result else pd.DataFrame()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("方案仿真", "已完成" if batch_result else "待开始")
    c2.metric("经济性测算", "已完成" if economy_result and not economy_result.get("summary", pd.DataFrame()).empty else "待开始")
    c3.metric("方案数量", int(batch_result.scenario_count) if batch_result else 0)
    c4.metric("达标方案", int(summary["pass_policy"].sum()) if not summary.empty and "pass_policy" in summary.columns else 0)

    st.markdown(
        """
        **推荐使用路径**

        1. 方案仿真：上传负荷、光伏、风电曲线，设置风光储遍历范围和政策约束。
        2. 经济性测算：输入少量核心经济参数，默认用一个外部购电净成本口径派生负荷侧节费口径。
        3. 方案推荐及图表概览：查看四个推荐席位、用户指定方案、能量流向和运行曲线。
        4. 图表下载和报告生成：集中导出方案汇总、逐小时明细、经济性表和简版说明报告。
        """
    )
    if st.button("开始方案仿真", type="primary", key="welcome_start_technical"):
        _go_to_workflow_page(st, "方案仿真")


def _valid_scenario_ids(summary: pd.DataFrame) -> list[str]:
    if summary.empty or "scenario_id" not in summary.columns:
        return []
    return [str(item) for item in summary["scenario_id"].dropna().tolist()]


def _first_report_scenario_id(summary: pd.DataFrame, recommendation_result) -> str | None:
    valid_ids = _valid_scenario_ids(summary)
    if not valid_ids:
        return None
    valid_set = set(valid_ids)
    portfolio = getattr(recommendation_result, "portfolio", None)
    if isinstance(portfolio, pd.DataFrame) and not portfolio.empty and "scenario_id" in portfolio.columns:
        for raw_id in portfolio["scenario_id"].dropna().astype(str).tolist():
            if raw_id in valid_set:
                return raw_id
    return valid_ids[0]


def _scenario_status_text(summary: pd.DataFrame, scenario_id: str | None) -> str:
    if scenario_id is None or summary.empty or "scenario_id" not in summary.columns:
        return "暂无可用方案"
    hit = summary[summary["scenario_id"].astype(str) == str(scenario_id)]
    if hit.empty:
        return str(scenario_id)
    row = hit.iloc[0]
    return f"{scenario_id} · {_capacity_config_text(row)}"


def _scenario_short_label(row: pd.Series) -> str:
    return (
        f"{row.get('scenario_id', '-')}"
        f"<br>光{_compact_number(row.get('pv_capacity'), 0)} 风{_compact_number(row.get('wind_capacity'), 0)}"
        f"<br>储{_compact_number(row.get('bess_power'), 0)}/{_compact_number(row.get('bess_energy'), 0)}"
    )


def _representative_summary_for_dashboard(
    summary: pd.DataFrame,
    recommendation_result,
    *,
    max_items: int = 5,
) -> pd.DataFrame:
    if summary.empty or "scenario_id" not in summary.columns:
        return pd.DataFrame()

    selected_id = _first_report_scenario_id(summary, recommendation_result)
    ids: list[str] = []
    portfolio = getattr(recommendation_result, "portfolio", None)
    if isinstance(portfolio, pd.DataFrame) and not portfolio.empty and "scenario_id" in portfolio.columns:
        ids.extend(portfolio["scenario_id"].dropna().astype(str).tolist())
    if selected_id is not None:
        ids.append(str(selected_id))
    ids = list(dict.fromkeys(ids))
    if not ids:
        return summary.head(max_items).copy()

    comparison = summary[summary["scenario_id"].astype(str).isin(ids)].copy()
    if comparison.empty:
        return summary.head(max_items).copy()
    order = {scenario_id: index for index, scenario_id in enumerate(ids)}
    comparison["_display_order"] = comparison["scenario_id"].astype(str).map(order).fillna(len(order))
    return comparison.sort_values("_display_order").drop(columns=["_display_order"]).head(max_items)


def _build_compact_policy_comparison_figure(comparison: pd.DataFrame):
    required = ["scenario_id", "green_load_rate", "self_use_rate", "curtail_rate", "export_rate"]
    missing = [column for column in required if column not in comparison.columns]
    if comparison.empty or missing:
        return None, missing

    labels = [_scenario_short_label(row) for _, row in comparison.iterrows()]
    metrics = [
        ("green_load_rate", "绿电占比", "#16a34a", False),
        ("self_use_rate", "自发自用率", "#2563eb", False),
        ("curtail_rate", "低弃电", "#f59e0b", True),
        ("export_rate", "低上网", "#8b5cf6", True),
    ]
    fig = go.Figure()
    for column, label, color, invert in metrics:
        values = pd.to_numeric(comparison[column], errors="coerce").fillna(0.0)
        if invert:
            values = 1 - values
        fig.add_bar(
            x=labels,
            y=values,
            name=label,
            marker_color=color,
            text=[f"{value:.1%}" for value in values],
            textposition="outside",
            cliponaxis=False,
        )
    fig.update_layout(
        barmode="group",
        height=340,
        margin=dict(l=42, r=18, t=16, b=84),
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        font=dict(family="Arial, sans-serif", size=12, color="#172033"),
    )
    fig.update_xaxes(tickfont=dict(size=11))
    fig.update_yaxes(tickformat=".0%", range=[0, 1.08], gridcolor="#e5eaf0", title_text="比例")
    return fig, []


def _first_existing_column(data: pd.DataFrame, candidates: list[str]) -> str | None:
    for column in candidates:
        if column in data.columns:
            return column
    return None


def _numeric_power(data: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_numeric(data[column], errors="coerce").fillna(0.0)


def _build_compact_typical_day_figure(hourly: pd.DataFrame, season: str = "夏季"):
    adapted = adapt_hourly(hourly)
    selection = select_typical_season_day(adapted.data, season)
    day = selection.day
    if day.empty:
        return None, selection.label, selection.method

    if "timestamp" in day.columns:
        timestamps = pd.to_datetime(day["timestamp"], errors="coerce")
        hours = timestamps.dt.hour
        x = list(range(len(day))) if hours.isna().any() else hours.astype(int)
    else:
        x = list(range(len(day)))

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    def add_power_trace(candidates: list[str], name: str, color: str, *, dash: str | None = None, negative: bool = False):
        column = _first_existing_column(day, candidates)
        if column is None:
            return
        values = _numeric_power(day, column)
        if negative:
            values = -values
        fig.add_trace(
            go.Scatter(
                x=x,
                y=values,
                name=name,
                mode="lines",
                line=dict(color=color, width=2, dash=dash or "solid"),
            ),
            secondary_y=False,
        )

    add_power_trace(["load_power"], "负荷", "#174ea6")
    add_power_trace(["pv_generation_power", "pv_power"], "光伏出力", "#f97316")
    add_power_trace(["wind_generation_power", "wind_power"], "风电出力", "#16a34a")
    add_power_trace(["bess_discharge_power"], "储能放电", "#ef4444")
    add_power_trace(["bess_charge_power"], "储能充电(负值)", "#8b5cf6", negative=True)
    add_power_trace(["grid_import_power"], "下网功率", "#0891b2", dash="dash")
    add_power_trace(["grid_export_power"], "上网功率", "#a16207", dash="dot")
    add_power_trace(["curtail_power"], "弃电功率", "#dc2626", dash="dash")

    soc_column = _first_existing_column(day, ["soc_end"])
    if soc_column is not None:
        soc = pd.to_numeric(day[soc_column], errors="coerce").fillna(0.0)
        if not soc.empty and soc.max() > 1:
            soc = soc / 100
        fig.add_trace(
            go.Scatter(
                x=x,
                y=soc,
                name="SOC",
                mode="lines",
                line=dict(color="#0f9f9a", width=2, dash="dash"),
            ),
            secondary_y=True,
        )

    fig.update_layout(
        height=340,
        margin=dict(l=42, r=42, t=16, b=84),
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=-0.32, xanchor="left", x=0),
        font=dict(family="Arial, sans-serif", size=12, color="#172033"),
    )
    fig.update_xaxes(title_text="时间（时）", tickmode="array", tickvals=list(range(0, 24, 2)), gridcolor="#eef2f6")
    fig.update_yaxes(title_text="功率（万kW）", gridcolor="#e5eaf0", secondary_y=False)
    fig.update_yaxes(title_text="SOC", tickformat=".0%", range=[0, 1], secondary_y=True)
    return fig, selection.label, selection.method


def _render_recommendation_dashboard_overview(st, batch_result, summary: pd.DataFrame, recommendation_result) -> None:
    report_scenario_id = _first_report_scenario_id(summary, recommendation_result)
    comparison = _representative_summary_for_dashboard(summary, recommendation_result)
    st.markdown(
        """
        <div class="gd-dashboard-bar">
          <div>
            <div class="gd-dashboard-title">代表方案图表概览</div>
            <div class="gd-dashboard-subtitle">默认只围绕推荐组合和当前报告方案展示，不把全量枚举表作为主视图。</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    left, right = st.columns(2)
    with left:
        with st.container(border=True):
            st.markdown(
                """
                <div class="gd-chart-panel-head">
                  <div>
                    <div class="gd-chart-panel-title">多方案关键指标对比</div>
                    <div class="gd-chart-panel-note">绿电、自用、低弃电、低上网，数值越高越好。</div>
                  </div>
                  <div class="gd-chart-panel-tag">推荐组合</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            fig, missing = _build_compact_policy_comparison_figure(comparison)
            if fig is None:
                st.info(f"缺少字段，暂不能生成代表方案对比图：{', '.join(missing) if missing else '无代表方案'}")
            else:
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    with right:
        with st.container(border=True):
            hourly = getattr(batch_result, "hourly_details", {}).get(report_scenario_id) if report_scenario_id else None
            fig = None
            label = "待计算"
            method = "缺少默认报告方案或逐小时明细。"
            if isinstance(hourly, pd.DataFrame) and not hourly.empty:
                fig, label, method = _build_compact_typical_day_figure(hourly, "夏季")
            st.markdown(
                f"""
                <div class="gd-chart-panel-head">
                  <div>
                    <div class="gd-chart-panel-title">24H 典型日运行曲线</div>
                    <div class="gd-chart-panel-note">夏季典型日 {label}，读取逐小时明细，不重新调度。</div>
                  </div>
                  <div class="gd-chart-panel-tag">{_safe_html_text(report_scenario_id or '待选')}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if fig is None:
                st.info(method)
            else:
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def _render_recommendation_export_handoff(st, batch_result, summary: pd.DataFrame, recommendation_result) -> None:
    report_scenario_id = _first_report_scenario_id(summary, recommendation_result)
    has_hourly = bool(report_scenario_id and report_scenario_id in getattr(batch_result, "hourly_details", {}))
    economy_result = st.session_state.get("economy_v1_result")
    single_entity_result = st.session_state.get("single_entity_economy_result")
    has_power_economy = bool(economy_result and isinstance(economy_result.get("summary"), pd.DataFrame) and not economy_result["summary"].empty)
    has_single_entity = bool(
        single_entity_result
        and isinstance(single_entity_result.get("summary"), pd.DataFrame)
        and not single_entity_result["summary"].empty
    )

    _render_section_intro(
        st,
        "导出状态",
        "下载与报告",
        "正式下载动作集中在最后一个页面；这里按推荐组合给出默认报告方案和可导出状态。",
    )
    cards = [
        (
            "逐小时 CSV",
            "可用" if has_hourly else "待逐小时明细",
            "所选方案逐小时明细，来自技术仿真台账。",
        ),
        (
            "图表 HTML ZIP",
            "可生成" if has_hourly else "待逐小时明细",
            "图表包读取推荐组合和当前报告方案，不绘制全量枚举。",
        ),
        (
            "简版报告",
            "含经济性" if has_power_economy or has_single_entity else "仅技术部分",
            "Markdown 报告读取技术汇总、经济性汇总和典型日口径说明。",
        ),
    ]
    card_html = "".join(
        (
            '<div class="gd-download-card">'
            f"<strong>{_safe_html_text(title)}</strong>"
            f"<span>{_safe_html_text(status)} · {_safe_html_text(description)}</span>"
            "</div>"
        )
        for title, status, description in cards
    )
    st.markdown(f'<div class="gd-download-handoff">{card_html}</div>', unsafe_allow_html=True)

    if report_scenario_id is None:
        st.info("当前没有可用于报告和下载的方案。")
        return

    st.caption(f"默认报告方案：{_scenario_status_text(summary, report_scenario_id)}")
    if st.button("进入图表下载和报告生成", type="primary", key="recommendation_go_exports"):
        st.session_state["export_report_scenario"] = report_scenario_id
        _go_to_workflow_page(st, "图表下载和报告生成")


def _render_recommendation_bottom_status(st, batch_result, summary: pd.DataFrame, recommendation_result) -> None:
    report_scenario_id = _first_report_scenario_id(summary, recommendation_result)
    hourly_count = len(getattr(batch_result, "hourly_details", {}) or {})
    status_items = [
        f"<strong>默认报告方案</strong> {_safe_html_text(_scenario_status_text(summary, report_scenario_id))}",
        f"<strong>逐小时台账</strong> {_safe_html_text(str(hourly_count))} 个方案",
        "<strong>数据来源</strong> batch_result.summary / hourly_details / economy_v1_result",
        "<strong>版本号</strong> 待接入",
        "<strong>帮助入口</strong> 待接入正式帮助页",
    ]
    st.markdown(f'<div class="gd-bottom-status">{"".join(f"<span>{item}</span>" for item in status_items)}</div>', unsafe_allow_html=True)


def _render_recommendation_analysis_page(st, batch_result, summary: pd.DataFrame) -> None:
    _render_page_heading(
        st,
        "方案推荐及图表概览",
        "集中展示推荐组合、用户指定方案和逐小时图表分析；全量枚举表仅作为高级复核数据保留。",
    )

    economy_result = st.session_state.get("economy_v1_result")
    single_entity_result = st.session_state.get("single_entity_economy_result")
    recommendation_inputs = st.session_state.get("recommendation_v1_inputs")
    if not economy_result or economy_result.get("summary", pd.DataFrame()).empty:
        _render_missing_step(st, "经济性测算", "请先完成经济性测算，再生成推荐席位和经济性图表。")
        return
    if not recommendation_inputs:
        _render_missing_step(st, "经济性测算", "请重新运行一次经济性测算，以保存推荐席位所需的价格和门槛参数。")
        return

    recommendation_single_entity_summary = (
        single_entity_result["summary"]
        if single_entity_result and not single_entity_result["summary"].empty
        else None
    )
    recommendation_result = _render_recommendation_v1(
        st,
        summary,
        economy_result["summary"],
        recommendation_single_entity_summary,
        economic_params=recommendation_inputs["economic_params"],
        load_side_avoided_charge_price=recommendation_inputs["load_side_avoided_charge_price"],
        green_power_settlement_price_with_vat=recommendation_inputs["green_power_settlement_price_with_vat"],
        environmental_value_per_kwh=recommendation_inputs["environmental_value_per_kwh"],
        min_power_side_acceptable_firr=recommendation_inputs["min_power_side_acceptable_firr"],
    )
    _render_recommendation_dashboard_overview(st, batch_result, summary, recommendation_result)
    _render_recommendation_export_handoff(st, batch_result, summary, recommendation_result)
    _render_recommendation_detail_tables(st, recommendation_result)
    with st.expander("高级：完整图表分析与用户加入方案", expanded=False):
        render_chart_analysis(
            st,
            batch_result,
            summary,
            economy_result=economy_result,
            recommendation_portfolio=recommendation_result.portfolio if recommendation_result else None,
        )
    _render_recommendation_bottom_status(st, batch_result, summary, recommendation_result)


def _format_report_value(value, *, rate: bool = False, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return "-"
    if rate:
        return f"{float(value):.{digits}%}"
    if isinstance(value, Number):
        text = f"{float(value):,.{digits}f}"
        return text.rstrip("0").rstrip(".")
    return str(value)


def _row_for_scenario(data: pd.DataFrame | None, scenario_id: str) -> pd.Series | None:
    if data is None or data.empty or "scenario_id" not in data.columns:
        return None
    matched = data[data["scenario_id"].astype(str) == str(scenario_id)]
    if matched.empty:
        return None
    return matched.iloc[0]


def _build_simple_report_markdown(
    *,
    summary: pd.DataFrame,
    selected_scenario_id: str,
    economy_summary: pd.DataFrame | None,
    single_entity_summary: pd.DataFrame | None,
) -> bytes:
    technical = _row_for_scenario(summary, selected_scenario_id)
    power_economy = _row_for_scenario(economy_summary, selected_scenario_id)
    single_entity = _row_for_scenario(single_entity_summary, selected_scenario_id)

    lines = [
        "# 绿电直连方案简版说明报告",
        "",
        f"- 方案编号：`{selected_scenario_id}`",
        "- 数据口径：技术、经济、图表均读取已生成的方案汇总和逐小时明细；本报告不重新调度。",
        "- 四季典型日：采用季节中心日法，在各季完整 24 小时日期中选离季节平均曲线最近的真实日期；图表标题会标注 MM/DD。",
        "",
        "## 技术指标",
        "",
    ]
    if technical is None:
        lines.append("未找到该方案的技术汇总。")
    else:
        rows = [
            ("方案类型", technical.get("方案类型")),
            ("光伏容量(万kW)", technical.get("pv_capacity")),
            ("风电容量(万kW)", technical.get("wind_capacity")),
            ("储能功率(万kW)", technical.get("bess_power")),
            ("储能容量(万kWh)", technical.get("bess_energy")),
            ("政策达标", "是" if bool(technical.get("pass_policy", False)) else "否"),
            ("绿电占比", _format_report_value(technical.get("green_load_rate"), rate=True)),
            ("自发自用率", _format_report_value(technical.get("self_use_rate"), rate=True)),
            ("上网比例", _format_report_value(technical.get("export_rate"), rate=True)),
            ("弃电率", _format_report_value(technical.get("curtail_rate"), rate=True)),
            ("自发自用电量(万kWh)", technical.get("self_use_energy")),
            ("下网电量(万kWh)", technical.get("grid_import_energy")),
            ("上网电量(万kWh)", technical.get("grid_export_energy")),
            ("弃电量(万kWh)", technical.get("curtail_energy")),
        ]
        lines.extend(f"- {label}：{_format_report_value(value)}" for label, value in rows)

    lines.extend(["", "## 经济性摘要", ""])
    if power_economy is None and single_entity is None:
        lines.append("尚未生成经济性结果，报告仅包含技术部分。")
    if power_economy is not None:
        lines.extend(
            [
                f"- 电源侧 FNPV(万元)：{_format_report_value(power_economy.get('fnpv'), digits=0)}",
                f"- 电源侧 FIRR：{_format_report_value(power_economy.get('firr'), rate=True)}",
                f"- 静态回收期(年)：{_format_report_value(power_economy.get('static_payback_year'), digits=1)}",
                f"- 建设投资(万元)：{_format_report_value(power_economy.get('construction_cash_outflow'), digits=0)}",
            ]
        )
    if single_entity is not None:
        lines.extend(
            [
                f"- 同一主体税前 FIRR：{_format_report_value(single_entity.get('single_entity_firr_pre_tax'), rate=True)}",
                f"- 同一主体税前 FNPV(万元)：{_format_report_value(single_entity.get('single_entity_fnpv_pre_tax'), digits=0)}",
                f"- 外部购电净成本单价(元/kWh)：{_format_report_value(single_entity.get('net_avoided_grid_cost_price'), digits=4)}",
            ]
        )

    lines.extend(
        [
            "",
            "## 复核提示",
            "",
            "- 24H 运行曲线直接读取逐小时明细字段，不平滑、不插值、不重新计算储能调度。",
            "- 年度 Sankey 中光伏/风电去向拆分仍是按年发电占比的展示近似；严格复核请看逐小时明细和负荷平衡字段。",
            "- 若要复核某张图，请用本页导出的逐小时 CSV 按图表标题标注的日期过滤。",
        ]
    )
    return "\n".join(lines).encode("utf-8-sig")


def _safe_export_name(text: str) -> str:
    return re.sub(r"[^0-9A-Za-z_.-]+", "_", text).strip("_") or "chart"


def _comparison_summary_from_portfolio(
    summary: pd.DataFrame,
    selected_scenario_id: str,
    recommendation_portfolio: pd.DataFrame | None,
) -> pd.DataFrame:
    if summary.empty or "scenario_id" not in summary.columns:
        return summary

    ids = [str(selected_scenario_id)]
    if recommendation_portfolio is not None and not recommendation_portfolio.empty and "scenario_id" in recommendation_portfolio.columns:
        ids = [
            *recommendation_portfolio["scenario_id"].dropna().astype(str).tolist(),
            str(selected_scenario_id),
        ]
    ids = list(dict.fromkeys(ids))
    comparison = summary[summary["scenario_id"].astype(str).isin(ids)].copy()
    if comparison.empty:
        return summary[summary["scenario_id"].astype(str) == str(selected_scenario_id)].copy()
    order = {scenario_id: index for index, scenario_id in enumerate(ids)}
    comparison["_display_order"] = comparison["scenario_id"].astype(str).map(order).fillna(len(order))
    return comparison.sort_values("_display_order").drop(columns=["_display_order"])


def _default_export_scenario_id(
    scenario_ids: list[str],
    current_value: str | None,
    recommendation_result,
) -> str | None:
    if not scenario_ids:
        return None
    scenario_ids = [str(item) for item in scenario_ids]
    if current_value is not None and str(current_value) in scenario_ids:
        return str(current_value)

    portfolio = getattr(recommendation_result, "portfolio", None)
    if isinstance(portfolio, pd.DataFrame) and not portfolio.empty and "scenario_id" in portfolio.columns:
        valid_ids = set(scenario_ids)
        for raw_id in portfolio["scenario_id"].dropna().astype(str).tolist():
            if raw_id in valid_ids:
                return raw_id
    return scenario_ids[0]


def _build_chart_html_zip(
    summary: pd.DataFrame,
    selected_scenario_id: str,
    hourly: pd.DataFrame,
    comparison_summary: pd.DataFrame | None = None,
) -> bytes:
    output = BytesIO()
    selected_summary = _row_for_scenario(summary, selected_scenario_id)
    comparison_summary = comparison_summary if comparison_summary is not None and not comparison_summary.empty else summary
    chart_items = []
    warnings: list[str] = []
    season_export_keys = {"春季": "spring", "夏季": "summer", "秋季": "autumn", "冬季": "winter"}

    if selected_summary is not None:
        chart_items.append(("single_policy", build_policy_bar_chart(selected_summary)))

    for season in ["春季", "夏季", "秋季", "冬季"]:
        season_key = season_export_keys[season]
        selection = select_typical_season_day(hourly, season)
        if selection.day.empty or "timestamp" not in selection.day.columns:
            warnings.append(f"{season}典型日未生成：{selection.method}")
            continue
        selected_date = pd.to_datetime(selection.day["timestamp"], errors="coerce").dropna().dt.date
        if selected_date.empty:
            warnings.append(f"{season}典型日未生成：无法解析选中日期。")
            continue
        result = build_daily_balance_chart(hourly, selected_date=selected_date.iloc[0])
        result.chart_id = f"S03_{season_key}"
        result.chart_name = f"{season}典型日源网荷储平衡图（{selection.label}）"
        result.meta["typical_day_label"] = selection.label
        result.meta["typical_day_season"] = season
        result.meta["typical_day_method"] = selection.method
        chart_items.append((f"typical_{season_key}_{selection.label}", result))

    chart_items.extend(
        [
            ("soc_full_year", build_soc_chart(hourly)),
            ("grid_exchange", build_grid_exchange_chart(hourly)),
            ("monthly_load_source", build_monthly_load_source_chart(hourly)),
            ("monthly_renewable_flow", build_monthly_renewable_flow_chart(hourly)),
            ("heatmap_grid_import", build_heatmap_chart(hourly, "grid_import_power")),
            ("multi_policy", build_multi_policy_comparison(comparison_summary)),
            ("multi_capacity", build_multi_capacity_comparison(comparison_summary)),
            ("multi_renewable_flow", build_multi_renewable_flow_comparison(comparison_summary)),
            ("curtail_vs_self_use", build_curtailment_vs_self_consumption_scatter(comparison_summary)),
        ]
    )

    with ZipFile(output, mode="w", compression=ZIP_DEFLATED) as archive:
        exported = 0
        for base_name, result in chart_items:
            if result.figure is None:
                warnings.extend(result.warnings)
                continue
            prefix = _safe_export_name(f"{base_name}_{result.chart_id}")
            archive.writestr(f"{prefix}.html", chart_to_html_bytes(result))
            archive.writestr(f"{prefix}_meta.md", chart_to_meta_markdown(result).encode("utf-8-sig"))
            exported += 1
        if warnings:
            archive.writestr("warnings.txt", "\n".join(warnings).encode("utf-8-sig"))
        archive.writestr(
            "README.md",
            (
                "# 图表 HTML 导出说明\n\n"
                f"- 方案编号：`{selected_scenario_id}`\n"
                f"- 多方案对比范围：{len(comparison_summary)} 个方案（推荐组合 + 当前报告方案）。\n"
                f"- 已导出图表数量：{exported}\n"
                "- HTML 图表只读消费方案汇总和逐小时明细，不重新计算调度。\n"
                "- 四季典型日图表使用季节中心日法，并在文件名和 meta 中记录 MM/DD。\n"
            ).encode("utf-8-sig"),
        )
    return output.getvalue()


def _render_exports_and_reports_page(st, batch_result, summary: pd.DataFrame) -> None:
    _render_page_heading(
        st,
        "图表下载和报告生成",
        "集中下载技术结果、经济性结果、单方案逐小时复核数据，并生成可复核的简版说明报告。",
    )

    scenario_ids = list(batch_result.hourly_details.keys())
    if not scenario_ids:
        st.warning("当前没有逐小时明细，无法生成图表复核数据。")
        return

    economy_result = st.session_state.get("economy_v1_result")
    single_entity_result = st.session_state.get("single_entity_economy_result")
    economy_summary = (
        economy_result.get("summary")
        if economy_result and isinstance(economy_result.get("summary"), pd.DataFrame)
        else None
    )
    single_entity_summary = (
        single_entity_result.get("summary")
        if single_entity_result and isinstance(single_entity_result.get("summary"), pd.DataFrame)
        else None
    )
    recommendation_inputs = st.session_state.get("recommendation_v1_inputs")
    recommendation_result_for_export = None
    if recommendation_inputs and economy_summary is not None and not economy_summary.empty:
        try:
            recommendation_result_for_export = build_recommendation_study(
                summary,
                economy_summary,
                RecommendationInputSnapshot(**recommendation_inputs),
                single_entity_summary=single_entity_summary,
            )
        except Exception:  # noqa: BLE001 - export page should continue without recommendation scope
            recommendation_result_for_export = None

    default_export_id = _default_export_scenario_id(
        scenario_ids,
        st.session_state.get("export_report_scenario"),
        recommendation_result_for_export,
    )
    selected_index = scenario_ids.index(default_export_id) if default_export_id in scenario_ids else 0
    selected_id = st.selectbox(
        "选择报告和逐小时复核方案",
        scenario_ids,
        index=selected_index,
        key="export_report_scenario",
    )

    hourly = batch_result.hourly_details[selected_id]
    selected_status = _scenario_status_text(summary, selected_id)
    st.markdown(
        f"""
        <div class="gd-export-selected">
          <div>
            <strong>当前导出方案：{_safe_html_text(selected_id)}</strong><br/>
            <span>{_safe_html_text(selected_status)}</span>
          </div>
          <div>{_status_pill('逐小时明细可用', 'ok')}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    technical_col, chart_col, report_col = st.columns(3)
    with technical_col:
        with st.container(border=True):
            st.markdown(
                """
                <div class="gd-export-panel-head">
                  <strong>技术数据</strong>
                  <span>下载当前方案逐小时台账；批量汇总包放在折叠区，避免默认页变重。</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.download_button(
                "下载所选方案逐小时 CSV",
                data=localize_columns(hourly).to_csv(index=False).encode("utf-8-sig"),
                file_name=f"hourly_detail_{selected_id}.csv",
                mime="text/csv",
                key="export_selected_hourly_csv",
            )
            with st.expander("批量技术结果包", expanded=False):
                st.caption("生成方案汇总 Excel 和全部逐小时明细 ZIP，适合归档或二次复核。")
                if st.checkbox("准备方案汇总 Excel 和全部逐小时 ZIP", value=False, key="export_prepare_technical"):
                    payloads = _get_download_payloads(st, batch_result, st.session_state.get("config_snapshot", {}))
                    st.download_button(
                        "下载方案汇总 Excel",
                        data=payloads["excel_bytes"],
                        file_name=payloads["excel_name"],
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="export_summary_excel",
                    )
                    st.download_button(
                        "下载全部逐小时明细 ZIP",
                        data=payloads["zip_bytes"],
                        file_name=payloads["zip_name"],
                        mime="application/zip",
                        key="export_hourly_zip",
                    )

    with chart_col:
        with st.container(border=True):
            st.markdown(
                """
                <div class="gd-export-panel-head">
                  <strong>图表包</strong>
                  <span>导出当前方案单方案图、四季典型日图，以及推荐组合范围的多方案对比图。</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.checkbox("准备所选方案图表 HTML ZIP", value=False, key="export_prepare_chart_html"):
                with st.spinner("正在生成图表 HTML ZIP..."):
                    comparison_summary = _comparison_summary_from_portfolio(
                        summary,
                        selected_id,
                        recommendation_result_for_export.portfolio if recommendation_result_for_export else None,
                    )
                    chart_zip = _build_chart_html_zip(summary, selected_id, hourly, comparison_summary=comparison_summary)
                st.download_button(
                    "下载所选方案图表 HTML ZIP",
                    data=chart_zip,
                    file_name=f"chart_html_{selected_id}.zip",
                    mime="application/zip",
                    key="export_selected_chart_html_zip",
                    help="包含四季典型日平衡图、SOC、电网交换、月度流向、热力图和多方案对比图；每张图附带 meta 说明。",
                )
            st.markdown('<div class="gd-export-note">PNG 批量导出依赖后续图像导出环境，当前先提供可交互 HTML。</div>', unsafe_allow_html=True)

    with report_col:
        with st.container(border=True):
            st.markdown(
                """
                <div class="gd-export-panel-head">
                  <strong>经济与报告</strong>
                  <span>汇总技术、经济性、推荐组合和简版说明报告，缺失结果按真实状态提示。</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
            sheets = {"方案汇总": localize_columns(summary)}
            if economy_summary is not None and not economy_summary.empty:
                sheets["电源侧经济性汇总"] = localize_columns(economy_summary)
            if single_entity_summary is not None and not single_entity_summary.empty:
                sheets["同一主体经济性汇总"] = localize_columns(single_entity_summary)
            st.download_button(
                "下载技术+经济汇总 Excel",
                data=_build_excel_bytes(sheets),
                file_name="green_direct_technical_economy_summary.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="export_technical_economy_excel",
            )
            st.download_button(
                "下载简版 Markdown 报告",
                data=_build_simple_report_markdown(
                    summary=summary,
                    selected_scenario_id=selected_id,
                    economy_summary=economy_summary,
                    single_entity_summary=single_entity_summary,
                ),
                file_name=f"green_direct_report_{selected_id}.md",
                mime="text/markdown",
                key="export_simple_markdown_report",
            )

    with st.expander("高级：年度现金流与推荐组合导出", expanded=False):
        st.caption("这里保留经济性复核文件和推荐组合 Excel，避免默认导出页过载。")
        st.download_button(
            "下载当前技术+经济汇总 Excel",
            data=_build_excel_bytes(sheets),
            file_name="green_direct_technical_economy_summary.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="export_technical_economy_excel_advanced",
        )
        power_annual_cashflows = (
            economy_result.get("annual_cashflows")
            if economy_result and isinstance(economy_result.get("annual_cashflows"), dict)
            else {}
        )
        if selected_id in power_annual_cashflows:
            st.download_button(
                "下载所选方案电源侧年度现金流 Excel",
                data=_build_excel_bytes(
                    {
                        f"电源侧年度现金流_{selected_id}": localize_columns(power_annual_cashflows[selected_id]),
                    }
                ),
                file_name=f"power_side_annual_cashflow_{selected_id}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="export_power_side_annual_cashflow",
            )

        single_entity_annual_cashflows = (
            single_entity_result.get("annual_cashflows")
            if single_entity_result and isinstance(single_entity_result.get("annual_cashflows"), dict)
            else {}
        )
        if selected_id in single_entity_annual_cashflows and single_entity_summary is not None:
            st.download_button(
                "下载所选方案同一主体年度现金流 Excel",
                data=_build_single_entity_annual_workbook_bytes(
                    scenario_id=selected_id,
                    annual=single_entity_annual_cashflows[selected_id],
                    technical_summary=summary,
                    economic_summary=single_entity_summary,
                ),
                file_name=f"single_entity_pre_tax_annual_cashflow_{selected_id}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="export_single_entity_annual_cashflow",
            )

        if recommendation_inputs and economy_summary is not None and not economy_summary.empty:
            try:
                recommendation_result = recommendation_result_for_export
                if recommendation_result is None:
                    recommendation_result = build_recommendation_study(
                        summary,
                        economy_summary,
                        RecommendationInputSnapshot(**recommendation_inputs),
                        single_entity_summary=single_entity_summary,
                    )
                st.download_button(
                    "下载推荐组合 Excel",
                    data=_build_excel_bytes(
                        {
                            "推荐组合": localize_columns(recommendation_result.portfolio),
                            "电源侧经济性汇总": localize_columns(economy_summary),
                            "同一主体经济性汇总": localize_columns(
                                single_entity_summary if single_entity_summary is not None else pd.DataFrame()
                            ),
                            "负荷侧可成交收益明细": localize_columns(recommendation_result.load_side_detail),
                        }
                    ),
                    file_name="recommendation_portfolio_v1.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="export_recommendation_portfolio_v1",
                )
            except Exception as exc:  # noqa: BLE001 - export page should stay usable
                st.info(f"推荐组合导出暂不可用：{exc}")


def _render_simulation_page(st) -> None:
    _render_page_heading(st, "方案仿真")
    simulation_notice = st.session_state.pop("_simulation_notice", None)
    if simulation_notice:
        st.success(simulation_notice)

    scenario_grid = None
    scenario_count: int | None = None
    warn_threshold = 5000
    grid_exchange_power_limit = None

    data_col, scenario_col, policy_col = st.columns([1.15, 1.08, 1.0])

    with data_col:
        with st.container(border=True):
            _render_section_intro(
                st,
                "Input",
                "数据曲线",
                "优先批量上传三条曲线；手动覆盖、编码和列识别放入复核区。",
            )
            if st.session_state.pop("_simulation_force_sample_data", False):
                st.session_state["simulation_use_sample_data"] = True
            use_sample_data = _boolean_input(
                st,
                "使用内置示例数据（Demo）",
                value=False,
                help="使用 samples 目录中的负荷、光伏、风电示例曲线，适合快速体验测算和图表分析。",
                key="simulation_use_sample_data",
            )
            sample_files: dict[str, object] = {}
            if use_sample_data:
                sample_files, sample_messages = _load_sample_curve_files()
                for message in sample_messages:
                    st.warning(message)

            batch_files = st.file_uploader(
                "批量上传曲线 CSV",
                type=["csv"],
                accept_multiple_files=True,
                help="一次选择负荷、光伏、风电文件；文件名包含 load、pv/solar、wind 或中文关键词时会自动识别。",
            )
            assigned_files, assign_messages = _auto_assign_curve_files(batch_files)
            for message in assign_messages:
                st.warning(message)

            with st.expander("高级：单独上传覆盖", expanded=False):
                st.markdown(
                    '<div class="gd-field-note">批量识别不准确时，在这里单独覆盖某一条曲线文件。</div>',
                    unsafe_allow_html=True,
                )
                c1, c2, c3 = st.columns(3)
                load_file_manual = c1.file_uploader("负荷 CSV", type=["csv"], key="load_csv_manual")
                pv_file_manual = c2.file_uploader("光伏 CSV", type=["csv"], key="pv_csv_manual")
                wind_file_manual = c3.file_uploader("风电 CSV", type=["csv"], key="wind_csv_manual")

            load_file = load_file_manual or assigned_files.get("负荷") or sample_files.get("负荷")
            pv_file = pv_file_manual or assigned_files.get("光伏") or sample_files.get("光伏")
            wind_file = wind_file_manual or assigned_files.get("风电") or sample_files.get("风电")

            try:
                load_df, load_encoding = _load_preview(load_file)
                pv_df, pv_encoding = _load_preview(pv_file)
                wind_df, wind_encoding = _load_preview(wind_file)
            except DataValidationError as exc:
                st.error(str(exc))
                load_df = pv_df = wind_df = None
                load_encoding = pv_encoding = wind_encoding = None

            load_time_guess = _guess_time_column(load_df)
            pv_time_guess = _guess_time_column(pv_df)
            wind_time_guess = _guess_time_column(wind_df)
            load_value_guess = _guess_value_column(load_df, load_time_guess, "负荷")
            pv_value_guess = _guess_value_column(pv_df, pv_time_guess, "光伏")
            wind_value_guess = _guess_value_column(wind_df, wind_time_guess, "风电")
            needs_column_review = any(
                [
                    load_df is not None and (load_time_guess is None or load_value_guess is None),
                    pv_df is not None and (pv_time_guess is None or pv_value_guess is None),
                    wind_df is not None and (wind_time_guess is None or wind_value_guess is None),
                ]
            )

            with st.expander("数据识别复核", expanded=needs_column_review):
                st.markdown(
                    '<div class="gd-field-note">自动识别正常时无需处理；列名异常时在这里人工选择时间列和数值列。</div>',
                    unsafe_allow_html=True,
                )
                load_time_col = _column_selector(
                    st, "负荷时间列", load_df, load_time_guess, show_guess_caption=False
                )
                load_value_col = _column_selector(
                    st, "负荷数值列", load_df, load_value_guess, show_guess_caption=False
                )
                pv_time_col = _column_selector(
                    st, "光伏时间列", pv_df, pv_time_guess, show_guess_caption=False
                )
                pv_value_col = _column_selector(
                    st, "光伏数值列", pv_df, pv_value_guess, show_guess_caption=False
                )
                wind_time_col = _column_selector(
                    st, "风电时间列", wind_df, wind_time_guess, show_guess_caption=False
                )
                wind_value_col = _column_selector(
                    st, "风电数值列", wind_df, wind_value_guess, show_guess_caption=False
                )
                review_rows = [
                    {
                        "曲线": "负荷",
                        "文件": getattr(load_file, "name", "-") if load_file else "-",
                        "编码": load_encoding or "-",
                        "时间列": load_time_col or "-",
                        "数值列": load_value_col or "-",
                    },
                    {
                        "曲线": "光伏",
                        "文件": getattr(pv_file, "name", "-") if pv_file else "-",
                        "编码": pv_encoding or "-",
                        "时间列": pv_time_col or "-",
                        "数值列": pv_value_col or "-",
                    },
                    {
                        "曲线": "风电",
                        "文件": getattr(wind_file, "name", "-") if wind_file else "-",
                        "编码": wind_encoding or "-",
                        "时间列": wind_time_col or "-",
                        "数值列": wind_value_col or "-",
                    },
                ]
                st.dataframe(pd.DataFrame(review_rows), use_container_width=True, hide_index=True)

            _render_curve_overview_cards(
                st,
                {"负荷": load_file, "光伏": pv_file, "风电": wind_file},
                {
                    "负荷": (load_time_col, load_value_col),
                    "光伏": (pv_time_col, pv_value_col),
                    "风电": (wind_time_col, wind_value_col),
                },
            )

    with scenario_col:
        with st.container(border=True):
            _render_section_intro(
                st,
                "Scenario Pool",
                "候选方案池",
                "枚举只作为内部搜索方法；这里控制风、光、储容量边界和步长。",
            )
            pv_range = _range_inputs(st, "光伏容量", (0, 30, 5))
            wind_range = _range_inputs(st, "风电容量", (0, 30, 5))
            bess_power_range = _range_inputs(st, "储能功率", (0, 10, 2))
            include_no_bess = _boolean_input(
                st,
                "包含无储能方案",
                value=True,
                help="保留无储能基准方案，便于比较储能增益。",
                key="simulation_include_no_bess",
            )
            duration_text = st.text_input(
                "储能时长选项（小时）",
                value="2,4",
                help="多个时长用英文逗号分隔；勾选无储能时会自动加入 0 小时。",
            )
            with st.expander("高级：枚举性能提醒", expanded=False):
                warn_threshold = int(
                    st.number_input("方案数提醒阈值", value=5000, min_value=1, step=100)
                )

            try:
                durations = [float(item.strip()) for item in duration_text.split(",") if item.strip()]
                if include_no_bess and 0.0 not in durations:
                    durations = [0.0, *durations]
                scenario_grid = {
                    "pv_capacity": pv_range,
                    "wind_capacity": wind_range,
                    "bess_power": bess_power_range,
                    "bess_duration_hours": durations,
                }
                scenario_count = estimate_scenario_count(scenario_grid)
                _render_simulation_kpis(st, scenario_count, scenario_grid, duration_text)
                if scenario_count == 0:
                    st.error("当前容量范围没有可用候选方案：至少需要配置光伏或风电容量，纯储能/无绿电来源组合不会进入候选池。")
                    scenario_grid = None
                if scenario_count > warn_threshold:
                    st.warning(f"本次配置将生成 {scenario_count} 个方案，可能计算较慢，建议增大步长或缩小范围。")
            except Exception as exc:  # noqa: BLE001 - UI should show friendly text
                st.error(f"方案范围设置有误：{exc}")
                scenario_grid = None

    with policy_col:
        with st.container(border=True):
            _render_section_intro(
                st,
                "Policy",
                "政策和电网约束",
                "只做筛选和上网控制，不改变当前基线储能调度口径。",
            )
            allow_export = _boolean_input(
                st,
                "允许上网",
                value=True,
                help="关闭后，富余电量按弃电处理。",
                key="simulation_allow_export",
            )
            enforce_export_cap = _boolean_input(
                st,
                "启用年度上网比例硬约束",
                value=True,
                help="开启后，超过年度上网额度的富余电量按弃电处理；关闭后只做结果达标检查。",
                key="simulation_enforce_export_cap",
            )
            self_use_rate_min = st.number_input(
                "自发自用率下限",
                value=0.60,
                min_value=0.0,
                max_value=1.0,
                step=0.01,
                help="方案筛选指标，内部按小数保存。",
            )
            green_load_rate_min = st.number_input(
                "绿电占用电比例下限",
                value=0.30,
                min_value=0.0,
                max_value=1.0,
                step=0.01,
                help="方案筛选指标，内部按小数保存。",
            )
            export_rate_max = st.number_input(
                "上网比例上限",
                value=0.20,
                min_value=0.0,
                max_value=1.0,
                step=0.01,
                help="方案筛选指标，内部按小数保存。",
            )
            with st.expander("高级：电网交换功率限制", expanded=False):
                limit_exchange_power = _boolean_input(
                    st,
                    "设置与电网交换功率限制",
                    value=False,
                    help="用于限制并网点交换功率，未启用时保持无限制。",
                    key="simulation_limit_exchange_power",
                )
                if limit_exchange_power:
                    grid_exchange_power_limit = st.number_input(
                        "与电网交换功率限制（万千瓦）",
                        value=10.0,
                        min_value=0.0,
                        step=1.0,
                    )

    with st.expander("专业参数：储能 SOC、效率与寿命", expanded=False):
        soc_cols = st.columns(4)
        soc_initial = soc_cols[0].number_input("初始 SOC", value=0.5, min_value=0.0, max_value=1.0, step=0.05)
        soc_min = soc_cols[1].number_input("最小 SOC", value=0.1, min_value=0.0, max_value=1.0, step=0.05)
        soc_max = soc_cols[2].number_input("最大 SOC", value=0.9, min_value=0.0, max_value=1.0, step=0.05)
        bess_calendar_life = soc_cols[3].number_input(
            "电池日历寿命（年）",
            value=15.0,
            min_value=1.0,
            max_value=40.0,
            step=1.0,
            help="当前不参与小时调度，只在经济性测算中与循环寿命共同决定储能更换年份。",
        )
        eff_cols = st.columns(3)
        eta_charge = eff_cols[0].number_input("充电效率", value=0.95, min_value=0.000001, max_value=1.0, step=0.01)
        eta_discharge = eff_cols[1].number_input("放电效率", value=0.95, min_value=0.000001, max_value=1.0, step=0.01)
        cycle_life = eff_cols[2].number_input("循环寿命", value=6000.0, min_value=0.0, step=100.0)

    ready = all(
        [
            load_file,
            pv_file,
            wind_file,
            load_time_col,
            load_value_col,
            pv_time_col,
            pv_value_col,
            wind_time_col,
            wind_value_col,
            scenario_grid,
        ]
    )

    _render_run_state(st, ready, scenario_count, has_result=bool(st.session_state.get("batch_result")))
    action_col, demo_col, next_hint_col = st.columns([0.78, 0.92, 3.0])
    start_clicked = action_col.button("开始测算", type="primary", disabled=not ready, key="simulation_start")
    demo_clicked = demo_col.button(
        "一键生成 Demo 结果",
        help="使用 samples 示例曲线和一组小规模候选方案快速生成图表演示。",
        key="simulation_demo",
    )
    next_hint_col.markdown(
        '<div class="gd-field-note">测算完成后，推荐、图表包、报告导出会围绕代表方案组织，不再把全量枚举表作为主入口。</div>',
        unsafe_allow_html=True,
    )

    if demo_clicked:
        try:
            demo_files, demo_messages = _load_sample_curve_files()
            missing_demo = {"负荷", "光伏", "风电"} - set(demo_files)
            if missing_demo:
                raise DataValidationError(f"内置示例数据不完整，缺少：{', '.join(sorted(missing_demo))}。")
            for message in demo_messages:
                st.warning(message)

            demo_load_df, _ = _load_preview(demo_files["负荷"])
            demo_pv_df, _ = _load_preview(demo_files["光伏"])
            demo_wind_df, _ = _load_preview(demo_files["风电"])
            demo_load_time_col = _guess_time_column(demo_load_df)
            demo_pv_time_col = _guess_time_column(demo_pv_df)
            demo_wind_time_col = _guess_time_column(demo_wind_df)
            demo_load_value_col = _guess_value_column(demo_load_df, demo_load_time_col, "负荷")
            demo_pv_value_col = _guess_value_column(demo_pv_df, demo_pv_time_col, "光伏")
            demo_wind_value_col = _guess_value_column(demo_wind_df, demo_wind_time_col, "风电")
            if not all(
                [
                    demo_load_time_col,
                    demo_pv_time_col,
                    demo_wind_time_col,
                    demo_load_value_col,
                    demo_pv_value_col,
                    demo_wind_value_col,
                ]
            ):
                raise DataValidationError("未能自动识别示例数据列名，请检查 samples 目录中的 CSV。")

            demo_grid = {
                "pv_capacity": {"start": 2, "end": 10, "step": 4},
                "wind_capacity": {"start": 1, "end": 5, "step": 2},
                "bess_power": {"start": 0, "end": 2, "step": 1},
                "bess_duration_hours": [0, 2],
            }
            with st.spinner("正在生成 Demo 测算结果..."):
                technical_result = run_technical_study(
                    TechnicalStudyInput(
                        load_source=demo_files["负荷"].getvalue(),
                        pv_source=demo_files["光伏"].getvalue(),
                        wind_source=demo_files["风电"].getvalue(),
                        load_time_col=demo_load_time_col,
                        load_value_col=demo_load_value_col,
                        pv_time_col=demo_pv_time_col,
                        pv_value_col=demo_pv_value_col,
                        wind_time_col=demo_wind_time_col,
                        wind_value_col=demo_wind_value_col,
                        scenario_grid=demo_grid,
                        bess_params=BessParams(),
                        policy_params=PolicyParams(export_control_mode="annual_cap_runtime"),
                        performance_params=PerformanceParams(warn_if_scenarios_exceed=int(warn_threshold)),
                        cleaning_params=DataCleaningParams(),
                        config_metadata={
                            "bess_calendar_life_years": 15.0,
                            "demo": True,
                        },
                    ),
                )
            study_result = StudyResult.from_technical(technical_result)
            st.session_state["study_result"] = study_result
            st.session_state["batch_result"] = technical_result.batch_result
            st.session_state["config_snapshot"] = technical_result.config_snapshot
            st.session_state.pop("download_payloads", None)
            st.session_state["_simulation_force_sample_data"] = True
            st.session_state["_simulation_notice"] = "Demo 结果已生成，可继续做经济测算和推荐图表。"
            st.rerun()
        except DataValidationError as exc:
            st.error(str(exc))
        except Exception as exc:  # noqa: BLE001 - UI should show friendly text
            st.error(f"Demo 生成失败：{exc}")

    statuses = [
        _curve_status("负荷", load_df, load_encoding, load_time_col, load_value_col),
        _curve_status("光伏", pv_df, pv_encoding, pv_time_col, pv_value_col),
        _curve_status("风电", wind_df, wind_encoding, wind_time_col, wind_value_col),
    ]
    statuses = [item for item in statuses if item is not None]
    if statuses:
        _render_data_status(st, statuses)

    if start_clicked:
        try:
            bess_params = BessParams(
                soc_initial=soc_initial,
                soc_min=soc_min,
                soc_max=soc_max,
                eta_charge=eta_charge,
                eta_discharge=eta_discharge,
                cycle_life=cycle_life,
            )
            policy_params = PolicyParams(
                self_use_rate_min=self_use_rate_min,
                green_load_rate_min=green_load_rate_min,
                export_rate_max=export_rate_max,
                allow_export=allow_export,
                export_power_max=None,
                grid_exchange_power_limit=grid_exchange_power_limit,
                export_control_mode="annual_cap_runtime" if enforce_export_cap else "post_check",
            )
            progress = st.progress(0)
            progress_text = st.empty()

            def update_progress(done, total, scenario):
                progress.progress(done / total if total else 1.0)
                progress_text.caption(f"正在计算 {done}/{total}：{scenario.scenario_id}")

            technical_result = run_technical_study(
                TechnicalStudyInput(
                    load_source=load_file.getvalue(),
                    pv_source=pv_file.getvalue(),
                    wind_source=wind_file.getvalue(),
                    load_time_col=load_time_col,
                    load_value_col=load_value_col,
                    pv_time_col=pv_time_col,
                    pv_value_col=pv_value_col,
                    wind_time_col=wind_time_col,
                    wind_value_col=wind_value_col,
                    scenario_grid=scenario_grid,
                    bess_params=bess_params,
                    policy_params=policy_params,
                    performance_params=PerformanceParams(warn_if_scenarios_exceed=int(warn_threshold)),
                    cleaning_params=DataCleaningParams(),
                    config_metadata={
                        "bess_calendar_life_years": bess_calendar_life,
                    },
                ),
                progress_callback=update_progress,
            )
            progress_text.caption(
                f"计算完成：{technical_result.scenario_count}/{technical_result.scenario_count}"
            )

            study_result = StudyResult.from_technical(technical_result)
            st.session_state["study_result"] = study_result
            st.session_state["batch_result"] = technical_result.batch_result
            st.session_state["config_snapshot"] = technical_result.config_snapshot
            st.session_state.pop("download_payloads", None)
            st.session_state["_simulation_notice"] = "测算完成。"
            st.rerun()
        except DataValidationError as exc:
            st.error(str(exc))
        except Exception as exc:  # noqa: BLE001 - UI should show friendly text
            st.error(f"测算失败：{exc}")

    batch_result = st.session_state.get("batch_result")
    if not batch_result:
        return

    for warning in batch_result.warnings[:10]:
        st.warning(warning)
    if not batch_result.errors.empty:
        st.error(f"{len(batch_result.errors)} 个方案计算失败，已在错误表中记录。")
        st.dataframe(batch_result.errors, use_container_width=True)

    summary = batch_result.summary
    if summary.empty:
        st.warning("没有成功生成方案结果。")
        return

    summary = _add_scenario_type(summary)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("总方案数", batch_result.scenario_count)
    c2.metric("达标方案数", int(summary["pass_policy"].sum()))
    c3.metric("最高绿电占比", f"{summary['green_load_rate'].max():.1%}")
    c4.metric("最低弃电率", f"{summary['curtail_rate'].min():.1%}")
    c5.metric("最低下网比例", f"{summary['grid_import_rate'].min():.1%}")

    with st.expander("高级：结果表、筛选与字段复核", expanded=False):
        st.caption("下载、图表包和报告集中在“图表下载和报告生成”页面；这里仅保留复核用筛选表。")
        only_passed = st.checkbox("只看达标方案", value=False)
        scheme_types = st.multiselect(
            "方案类型筛选（与达标筛选为 AND 关系）",
            sorted(summary["方案类型"].dropna().unique()),
            default=[],
        )
        sort_label = st.selectbox(
            "排序方式",
            ["绿电占比从高到低", "弃电率从低到高", "自发自用率从高到低", "上网比例从低到高", "储能容量从小到大"],
        )
        display = _apply_filters(summary, only_passed, scheme_types, sort_label)
        max_display_rows = st.number_input("结果表最多显示行数", min_value=50, max_value=5000, value=200, step=50)
        st.caption(f"当前筛选结果 {len(display)} 条，表格显示前 {min(len(display), int(max_display_rows))} 条。")
        st.dataframe(_format_summary_for_display(display.head(int(max_display_rows))), use_container_width=True)
        _display_mapping_expander(st, list(display.columns), "方案汇总字段对应关系")

        scenario_ids = list(batch_result.hourly_details.keys())
        selected = st.selectbox("选择方案查看逐小时字段", scenario_ids)
        if selected:
            _display_mapping_expander(
                st,
                list(batch_result.hourly_details[selected].columns),
                "逐小时明细字段对应关系",
            )

    st.info("方案仿真已完成。下一步请进入“经济性测算”设置经济参数并生成推荐所需的经济结果。")
    if st.button("进入经济性测算", key="technical_go_economy"):
        _go_to_workflow_page(st, "经济性测算")


def main() -> None:
    import streamlit as st

    st.set_page_config(page_title="绿电直连风光储方案策划平台", layout="wide")
    _inject_workbench_style(st)
    workflow_page = _render_workflow_navigation(st)
    _render_project_status_bar(st, workflow_page)

    if workflow_page == "欢迎页":
        _render_welcome_page(st)
        return

    if workflow_page in {"经济性测算", "方案推荐及图表概览", "图表下载和报告生成"}:
        batch_result = st.session_state.get("batch_result")
        if not batch_result:
            _render_missing_step(st, "方案仿真", "请先完成方案仿真，后续页面会读取方案汇总和逐小时明细。")
            return
        summary = _summary_from_batch_result(batch_result)
        if summary.empty:
            st.warning("没有成功生成方案结果，请回到方案仿真页检查输入数据和方案范围。")
            return
        if workflow_page == "经济性测算":
            _render_economy_v1(
                st,
                summary,
                bess_calendar_life_years=_get_bess_calendar_life_years(st),
                render_recommendation=False,
            )
        elif workflow_page == "方案推荐及图表概览":
            _render_recommendation_analysis_page(st, batch_result, summary)
        else:
            _render_exports_and_reports_page(st, batch_result, summary)
        return

    _render_simulation_page(st)


if __name__ == "__main__":
    main()
