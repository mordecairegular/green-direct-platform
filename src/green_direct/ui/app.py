"""Streamlit app for V0.1 technical batch simulation."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import replace
import html
import hashlib
from io import BytesIO
from numbers import Number
import os
from pathlib import Path
import pickle
import re
import sys
import time
from tempfile import TemporaryDirectory
import uuid
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
    read_price_curve,
)
from green_direct.export.csv_exporter import export_hourly_details_zip
from green_direct.export.excel_exporter import export_summary_excel
from green_direct.io.read_curves import read_csv_auto_encoding
from green_direct.io.validators import DataValidationError
from green_direct.models.params import BessParams, DataCleaningParams, PerformanceParams, PolicyParams
from green_direct.models.pilot_backend import Job, Project, ProjectMembership, ProjectRole, StudyResultRecord, User
from green_direct.recommendation import (
    ENGINEERING_VIEW_LABELS,
    SINGLE_ENTITY_VIEW_LABELS,
)
from green_direct.services import (
    LocalJobStore,
    LocalPilotAuth,
    LocalPilotRegistry,
    LocalResultStore,
    LocalPilotAdminService,
    PilotAccessError,
    PilotAccessService,
    PilotAdminError,
    PilotAuthError,
    RecommendationInputSnapshot,
    StudyResult,
    TechnicalStudyInput,
    build_recommendation_study,
    persist_economic_study_result,
    persist_recommendation_study_result,
    persist_technical_study_result,
    recommendation_result_fingerprint,
    run_economic_study,
    run_technical_study,
)
from green_direct.ui.field_labels import FIELD_LABELS, format_display_frame, localize_columns, mapping_frame
from green_direct.visualization.chart_data import adapt_hourly, select_day as select_operating_day, select_typical_season_day
from green_direct.visualization.export_charts import (
    DOCX_A4_PORTRAIT_PROFILE,
    charts_to_png_bytes_batch,
    chart_to_html_bytes,
    chart_to_meta_markdown,
    chart_to_png_bytes,
)
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
    build_full_year_operation_chart,
    build_grid_exchange_chart,
    build_monthly_load_source_chart,
    build_monthly_renewable_flow_chart,
    build_policy_bar_chart,
    build_soc_chart,
)
from green_direct.visualization.style import CHART_COLORS


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
PRICE_CURVE_FILE_KEYWORDS = [
    "下网电价",
    "电价曲线",
    "价格曲线",
    "购电价格",
    "购电电价",
    "电费",
    "电价",
    "price_curve",
    "price-curve",
    "price",
    "tariff",
]
TECHNICAL_CURVE_FILE_SUFFIXES = {".csv"}
WORKFLOW_PAGES = ["欢迎页", "方案仿真", "经济性测算", "方案推荐", "图表概览", "图表下载和报告生成"]
WORKFLOW_PAGE_KEY = "workflow_page"
WORKFLOW_PAGE_TARGET_KEY = "_workflow_page_target"
PROJECT_PRICE_CURVE_DATA_KEY = "project_price_curve_data"
PROJECT_PRICE_CURVE_META_KEY = "project_price_curve_meta"
PROJECT_PRICE_CURVE_NOTICE_KEY = "_project_price_curve_notice"
PROJECT_PRICE_CURVE_SESSION_UPLOAD_KEY = "_project_price_curve_uploaded_current_session"
RUNTIME_STATE_DIR = PROJECT_ROOT / ".runtime"
LATEST_SESSION_SNAPSHOT_PATH = RUNTIME_STATE_DIR / "latest_session_snapshot.pkl"
RUNTIME_SNAPSHOT_ENV = "GREEN_DIRECT_ENABLE_RUNTIME_SNAPSHOT"
PILOT_AUTH_ENV = "GREEN_DIRECT_ENABLE_PILOT_AUTH"
PILOT_STORE_DIR_ENV = "GREEN_DIRECT_PILOT_STORE_DIR"
PILOT_DEFAULT_STORE_DIR = RUNTIME_STATE_DIR / "pilot_store"
PILOT_SESSION_ID_KEY = "_pilot_auth_session_id"
PILOT_SESSION_TOKEN_KEY = "_pilot_auth_session_token"
PILOT_USER_ID_KEY = "_pilot_auth_user_id"
PILOT_USER_DISPLAY_KEY = "_pilot_auth_user_display"
PILOT_LOGIN_NAME_KEY = "_pilot_auth_login_name"
PILOT_IS_PLATFORM_ADMIN_KEY = "_pilot_auth_is_platform_admin"
PILOT_LOGIN_NOTICE_KEY = "_pilot_auth_notice"
PILOT_ADMIN_NOTICE_KEY = "_pilot_admin_notice"
PILOT_ACTIVE_PROJECT_ID_KEY = "_pilot_active_project_id"
PILOT_ACTIVE_PROJECT_NAME_KEY = "_pilot_active_project_name"
PILOT_ACTIVE_PROJECT_ROLE_KEY = "_pilot_active_project_role"
PILOT_PROJECT_NOTICE_KEY = "_pilot_project_notice"
PILOT_RESULT_STORE_NOTICE_KEY = "_pilot_result_store_notice"
PILOT_RECOMMENDATION_STORE_SIGNATURE_KEY = "_pilot_recommendation_store_signature"
PLATFORM_ADMIN_PAGE = "平台管理"
CHART_PNG_DOCX_SESSION_ID_KEY = "_chart_png_docx_session_id"
_CHART_PNG_DOCX_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="green-direct-png")
_CHART_PNG_DOCX_JOBS: dict[str, dict[str, object]] = {}
RUNTIME_SNAPSHOT_KEYS = [
    "study_result",
    "batch_result",
    "config_snapshot",
    "economy_v1_result",
    "single_entity_economy_result",
    "recommendation_v1_inputs",
    "curve_metric_snapshot",
]
PILOT_AUTH_SESSION_KEYS = (
    PILOT_SESSION_ID_KEY,
    PILOT_SESSION_TOKEN_KEY,
    PILOT_USER_ID_KEY,
    PILOT_USER_DISPLAY_KEY,
    PILOT_LOGIN_NAME_KEY,
    PILOT_IS_PLATFORM_ADMIN_KEY,
    PILOT_ACTIVE_PROJECT_ID_KEY,
    PILOT_ACTIVE_PROJECT_NAME_KEY,
    PILOT_ACTIVE_PROJECT_ROLE_KEY,
)
PILOT_AUTH_WORK_STATE_KEYS = tuple(
    dict.fromkeys(
        [
            *RUNTIME_SNAPSHOT_KEYS,
            PROJECT_PRICE_CURVE_DATA_KEY,
            PROJECT_PRICE_CURVE_META_KEY,
            PROJECT_PRICE_CURVE_NOTICE_KEY,
            PROJECT_PRICE_CURVE_SESSION_UPLOAD_KEY,
            PILOT_RESULT_STORE_NOTICE_KEY,
            PILOT_RECOMMENDATION_STORE_SIGNATURE_KEY,
            "download_payloads",
            "chart_png_docx_export",
            "chart_png_docx_export_error",
            "chart_png_docx_active_signature",
            "export_report_scenario",
        ]
    )
)
WORKFLOW_PAGE_ALIASES = {
    "项目启动": "欢迎页",
    "项目启动台": "欢迎页",
    "技术仿真": "方案仿真",
    "经济性评价": "经济性测算",
    "推荐方案与详细分析": "方案推荐",
    "方案推荐与图表概览": "方案推荐",
    "方案推荐及图表概览": "方案推荐",
    "图表分析": "图表概览",
    "图表与报告": "图表下载和报告生成",
}
WORKFLOW_PAGE_META = {
    "欢迎页": {
        "index": "01",
        "title": "项目启动台",
        "nav_title": "项目启动",
        "subtitle": "查看项目准备度、下一步建议、推荐状态和交付准备情况。",
    },
    "方案仿真": {
        "index": "02",
        "title": "方案仿真",
        "nav_title": "方案仿真",
        "subtitle": "上传曲线、配置候选方案池和政策约束，生成技术仿真结果。",
    },
    "经济性测算": {
        "index": "03",
        "title": "经济性测算",
        "nav_title": "经济测算",
        "subtitle": "读取技术结果，输入经济参数并计算已实现的经济性视角。",
    },
    "方案推荐": {
        "index": "04",
        "title": "方案推荐",
        "nav_title": "方案推荐",
        "subtitle": "展示推荐席位、容量配置、关键指标、推荐理由和风险提示。",
    },
    "图表概览": {
        "index": "05",
        "title": "图表概览",
        "nav_title": "图表概览",
        "subtitle": "围绕推荐组合和当前代表方案展示关键图表与逐小时曲线。",
    },
    "图表下载和报告生成": {
        "index": "06",
        "title": "图表下载和报告生成",
        "nav_title": "下载报告",
        "subtitle": "集中导出复核数据、图表包和简版说明报告。",
    },
}
SIMULATION_WIDGET_STATE_KEYS = [
    "simulation_use_sample_data",
    "simulation_pv_capacity_start",
    "simulation_pv_capacity_end",
    "simulation_pv_capacity_step",
    "simulation_wind_capacity_start",
    "simulation_wind_capacity_end",
    "simulation_wind_capacity_step",
    "simulation_bess_power_start",
    "simulation_bess_power_end",
    "simulation_bess_power_step",
    "simulation_include_no_bess",
    "simulation_bess_duration_text",
    "simulation_scenario_pool_mode",
    "simulation_exact_pv_capacity",
    "simulation_exact_wind_capacity",
    "simulation_exact_bess_power",
    "simulation_exact_bess_energy",
    "simulation_warn_threshold",
    "simulation_parallel_workers",
    "simulation_large_run_hourly_detail_limit",
    "simulation_allow_export",
    "simulation_enforce_export_cap",
    "simulation_self_use_rate_min",
    "simulation_green_load_rate_min",
    "simulation_export_rate_max",
    "simulation_limit_exchange_power",
    "simulation_grid_exchange_power_limit",
    "simulation_soc_initial",
    "simulation_soc_min",
    "simulation_soc_max",
    "simulation_bess_calendar_life",
    "simulation_eta_charge",
    "simulation_eta_discharge",
    "simulation_cycle_life",
    "simulation_load_time_col",
    "simulation_load_value_col",
    "simulation_pv_time_col",
    "simulation_pv_value_col",
    "simulation_wind_time_col",
    "simulation_wind_value_col",
]
DEFAULT_LARGE_RUN_HOURLY_DETAIL_LIMIT = 20

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
    display: block !important;
    height: 0 !important;
    min-height: 0 !important;
    overflow: visible !important;
    background: transparent !important;
}
[data-testid="stHeader"] > div {
    height: 0 !important;
    min-height: 0 !important;
    overflow: visible !important;
}
#MainMenu,
[data-testid="stToolbar"],
[data-testid="stDecoration"],
[data-testid="stStatusWidget"] {
    display: none !important;
}
.block-container {
    padding-top: 0.2rem;
    padding-bottom: 1.4rem;
    padding-left: 1.35rem;
    padding-right: 1.35rem;
    max-width: none;
}
[data-testid="stSidebar"][aria-expanded="true"] {
    background: var(--gd-navy);
    min-width: 248px !important;
    max-width: 248px !important;
    width: 248px !important;
}
[data-testid="stSidebar"][aria-expanded="true"] > div {
    background: var(--gd-navy);
    border-right: 1px solid rgba(255, 255, 255, 0.08);
    min-width: 248px !important;
    max-width: 248px !important;
    width: 248px !important;
}
[data-testid="stSidebar"][aria-expanded="false"] {
    transform: none !important;
    min-width: 48px !important;
    width: 48px !important;
    max-width: 48px !important;
    background: var(--gd-navy) !important;
    overflow: visible !important;
}
[data-testid="stSidebar"][aria-expanded="false"] > div {
    min-width: 48px !important;
    width: 48px !important;
    max-width: 48px !important;
    background: var(--gd-navy) !important;
    overflow: hidden !important;
}
[data-testid="stSidebar"][aria-expanded="false"] [data-testid="stSidebarUserContent"] {
    display: none !important;
}
[data-testid="stSidebar"][aria-expanded="false"] [data-testid="stSidebarHeader"] {
    width: 48px !important;
    min-width: 48px !important;
    padding: 0 !important;
    justify-content: center !important;
}
[data-testid="stSidebar"][aria-expanded="false"] [data-testid="stSidebarCollapseButton"] {
    position: fixed !important;
    top: 12px !important;
    left: 8px !important;
    width: 34px !important;
    height: 34px !important;
    z-index: 999999 !important;
}
[data-testid="stSidebar"][aria-expanded="false"] [data-testid="stSidebarCollapseButton"] button {
    width: 34px !important;
    height: 34px !important;
    min-width: 34px !important;
    min-height: 34px !important;
    border-radius: 7px !important;
    background: rgba(255, 255, 255, 0.08) !important;
    color: #ffffff !important;
    border: 1px solid rgba(255, 255, 255, 0.22) !important;
}
[data-testid="stSidebarCollapseButton"],
[data-testid="stSidebarCollapseButton"] *,
[data-testid="stSidebarCollapsedControl"],
[data-testid="stSidebarCollapsedControl"] * {
    visibility: visible !important;
    opacity: 1 !important;
    pointer-events: auto !important;
}
button[data-testid="stExpandSidebarButton"] {
    visibility: visible !important;
    opacity: 1 !important;
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    position: fixed !important;
    top: 12px !important;
    left: 12px !important;
    width: 34px !important;
    height: 34px !important;
    min-width: 34px !important;
    min-height: 34px !important;
    z-index: 999999 !important;
    border-radius: 7px !important;
    background: var(--gd-navy) !important;
    color: #ffffff !important;
    border: 1px solid rgba(255, 255, 255, 0.24) !important;
}
button[data-testid="stExpandSidebarButton"] * {
    visibility: visible !important;
    color: #ffffff !important;
}
[data-testid="stSidebar"] * {
    color: #e6eef8;
}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
    color: #b9c7da;
}
[data-testid="stSidebar"] [data-testid="stElementContainer"],
[data-testid="stSidebar"] div[data-testid="stButton"],
[data-testid="stSidebar"] [data-testid="stTooltipIcon"],
[data-testid="stSidebar"] [data-testid="stTooltipHoverTarget"] {
    width: 100% !important;
    max-width: 100% !important;
}
[data-testid="stSidebar"] .stButton > button {
    width: 100%;
    height: 46px;
    min-height: 46px;
    max-height: 46px;
    justify-content: flex-start;
    color: #dbeafe !important;
    background: rgba(255, 255, 255, 0.055);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 7px;
    padding: 8px 11px;
    font-weight: 680;
    line-height: 1.18;
    white-space: nowrap;
    overflow: hidden;
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
    width: 100%;
    box-sizing: border-box;
    height: 46px;
    min-height: 46px;
    max-height: 46px;
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
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
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
    height: 46px !important;
    min-height: 46px !important;
    max-height: 46px !important;
    justify-content: flex-start !important;
    color: #dbeafe !important;
    background: rgba(255, 255, 255, 0.055) !important;
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    border-radius: 7px !important;
    padding: 8px 11px !important;
    font-weight: 680 !important;
    line-height: 1.18 !important;
    white-space: nowrap !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
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
[data-baseweb="tag"] {
    background: #eaf2ff !important;
    border: 1px solid #c9dcf5 !important;
    color: #0b2b52 !important;
}
[data-baseweb="tag"] span,
[data-baseweb="tag"] svg {
    color: #0b2b52 !important;
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
.gd-sidebar-metrics {
    margin-top: 12px;
    padding: 12px;
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 8px;
    background: rgba(255, 255, 255, 0.055);
}
.gd-sidebar-metrics-title {
    color: #ffffff;
    font-size: 13px;
    font-weight: 740;
    margin-bottom: 8px;
}
.gd-sidebar-metric-row {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 10px;
    align-items: baseline;
    font-size: 12px;
    margin: 6px 0;
}
.gd-sidebar-metric-row span {
    color: #b9c7da;
}
.gd-sidebar-metric-row strong {
    color: #ffffff;
    font-size: 13px;
    font-weight: 760;
}
.gd-sidebar-metrics-note {
    color: #9fb0c7;
    font-size: 11px;
    line-height: 1.35;
    margin-top: 8px;
}
.gd-topbar {
    display: grid;
    grid-template-columns: minmax(0, 1.2fr) minmax(0, 0.8fr) minmax(0, 1.8fr) minmax(0, 0.9fr) minmax(0, 1fr);
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
    overflow-wrap: anywhere;
}
.gd-step-lights {
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
    margin-top: 5px;
}
.gd-step-light {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    min-height: 22px;
    padding: 2px 7px;
    border-radius: 999px;
    color: #475467;
    background: #f3f6fa;
    font-size: 11px;
    white-space: nowrap;
}
.gd-step-light::before {
    content: "";
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: #98a2b3;
}
.gd-step-light.gd-step-ok::before {
    background: #16a34a;
}
.gd-step-light.gd-step-active {
    color: #0b2b52;
    background: #eaf2ff;
}
.gd-step-light.gd-step-active::before {
    background: #2474c7;
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
.gd-launch-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
    gap: 12px;
    margin: 10px 0 14px 0;
}
.gd-launch-card,
.gd-launch-panel {
    background: #ffffff;
    border: 1px solid var(--gd-line);
    border-radius: 8px;
    padding: 13px 15px;
}
.gd-launch-card h3,
.gd-launch-panel h3 {
    color: var(--gd-text);
    font-size: 16px;
    font-weight: 740;
    margin: 0 0 10px 0;
}
.gd-launch-metrics {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px 14px;
}
.gd-launch-metric span {
    display: block;
    color: var(--gd-muted);
    font-size: 12px;
    margin-bottom: 3px;
}
.gd-launch-metric strong {
    color: var(--gd-text);
    font-size: 16px;
    overflow-wrap: anywhere;
}
.gd-launch-panels {
    display: grid;
    grid-template-columns: minmax(0, 1.1fr) minmax(0, 0.9fr);
    gap: 12px;
    margin-top: 8px;
}
.gd-launch-row {
    display: grid;
    grid-template-columns: minmax(120px, 0.55fr) minmax(0, 1fr) auto;
    gap: 12px;
    align-items: center;
    border-top: 1px solid #edf2f7;
    padding: 9px 0;
    color: #344054;
    font-size: 13px;
}
.gd-launch-row:first-of-type {
    border-top: 0;
}
.gd-boundary-table {
    width: 100%;
    border-collapse: collapse;
    color: #344054;
    font-size: 13px;
}
.gd-boundary-table th,
.gd-boundary-table td {
    border-bottom: 1px solid #edf2f7;
    padding: 9px 8px;
    text-align: left;
    vertical-align: top;
}
.gd-boundary-table th {
    color: var(--gd-muted);
    background: #fbfdff;
    font-weight: 650;
}
.gd-economy-overview {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 12px;
    margin: 10px 0 12px 0;
}
.gd-economy-card {
    background: #ffffff;
    border: 1px solid var(--gd-line);
    border-radius: 8px;
    padding: 12px 14px;
}
.gd-economy-card h3 {
    color: var(--gd-text);
    font-size: 15px;
    font-weight: 740;
    margin: 0 0 9px 0;
}
.gd-economy-note {
    color: var(--gd-muted);
    font-size: 12px;
    line-height: 1.45;
    margin-top: 8px;
}
.gd-economy-strip {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 8px;
    margin: 8px 0 8px 0;
}
.gd-economy-strip-item {
    border: 1px solid #dce6f2;
    border-radius: 7px;
    background: #ffffff;
    padding: 8px 10px;
}
.gd-economy-strip-item span {
    display: block;
    color: var(--gd-muted);
    font-size: 11px;
    line-height: 1.2;
    margin-bottom: 3px;
}
.gd-economy-strip-item strong {
    display: block;
    color: var(--gd-text);
    font-size: 14px;
    line-height: 1.2;
}
.gd-economy-card-title {
    color: var(--gd-text);
    font-size: 15px;
    font-weight: 760;
    line-height: 1.22;
    margin: 0 0 8px 0;
}
.gd-economy-card-subtitle {
    color: var(--gd-muted);
    font-size: 12px;
    line-height: 1.35;
    margin: -2px 0 8px 0;
}
[data-testid="stForm"] {
    border: 0 !important;
    padding: 0 !important;
    background: transparent !important;
}
@media (max-width: 900px) {
    .gd-launch-panels {
        grid-template-columns: 1fr;
    }
    .gd-launch-row {
        grid-template-columns: 1fr;
        gap: 4px;
    }
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
.gd-landed-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
    gap: 10px;
    margin: 8px 0 12px 0;
}
.gd-landed-card {
    border: 1px solid #dfe8f2;
    border-radius: 8px;
    background: #ffffff;
    padding: 11px 12px;
}
.gd-landed-card h4 {
    color: var(--gd-text);
    font-size: 15px;
    margin: 0 0 2px 0;
}
.gd-landed-card .gd-landed-capacity {
    color: #667085;
    font-size: 11px;
    min-height: 17px;
}
.gd-landed-main {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
    margin: 9px 0 8px 0;
}
.gd-landed-main div {
    border-top: 1px solid #edf2f7;
    padding-top: 6px;
}
.gd-landed-main span,
.gd-landed-mini span {
    display: block;
    color: var(--gd-muted);
    font-size: 11px;
}
.gd-landed-main strong {
    color: var(--gd-text);
    font-size: 17px;
}
.gd-landed-mini {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 7px;
}
.gd-landed-mini strong {
    color: var(--gd-text);
    font-size: 13px;
    overflow-wrap: anywhere;
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
.gd-scenario-chip-row {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin: 10px 0 4px 0;
}
.gd-scenario-chip {
    border: 1px solid #dbe7f3;
    background: #f8fbff;
    border-radius: 8px;
    padding: 7px 10px;
    color: #42526b;
    font-size: 12px;
    line-height: 1.35;
}
.gd-scenario-chip strong {
    color: #0f1f33;
    font-size: 13px;
}
.gd-scenario-chip-active {
    border-color: #95c5ff;
    background: #edf6ff;
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
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 6px;
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
.gd-sim-file-card strong > span:first-child {
    display: inline;
    color: var(--gd-text);
    font-size: 13px;
    line-height: 1.2;
    margin-top: 0;
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
.gd-info-dot {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 18px;
    height: 18px;
    border-radius: 50%;
    border: 1px solid #b7c5d8;
    color: #36506f;
    background: #ffffff;
    font-size: 12px;
    font-weight: 760;
    cursor: help;
    flex: 0 0 auto;
    margin-top: 0 !important;
}
.gd-economy-section-title {
    color: var(--gd-text);
    font-size: 17px;
    font-weight: 760;
    line-height: 1.25;
    margin: 6px 0 4px 0;
}
.gd-economy-subsection-title {
    color: var(--gd-text);
    font-size: 14px;
    font-weight: 740;
    line-height: 1.25;
    margin: 3px 0 3px 0;
}
.gd-economy-compact-note {
    color: var(--gd-muted);
    font-size: 12px;
    line-height: 1.35;
    margin: -2px 0 6px 0;
}
[data-testid="stTextInput"] {
    margin-bottom: 0.05rem;
}
[data-testid="stNumberInput"] {
    margin-bottom: 0.05rem;
}
[data-testid="stTextInput"] label,
[data-testid="stNumberInput"] label,
[data-testid="stSelectbox"] label {
    padding-bottom: 0.15rem;
}
[data-testid="stTextInput"] label p,
[data-testid="stNumberInput"] label p,
[data-testid="stSelectbox"] label p {
    font-size: 0.86rem;
    line-height: 1.25;
}
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input {
    min-height: 34px !important;
    height: 34px !important;
    padding: 0.25rem 0.62rem !important;
    font-size: 0.95rem !important;
}
[data-testid="stNumberInput"] button {
    min-height: 34px !important;
    height: 34px !important;
}
@media (max-width: 720px) {
    .gd-topbar {
        grid-template-columns: 1fr;
    }
    .gd-rec-grid {
        grid-template-columns: 1fr;
    }
    .gd-rec-metrics,
    .gd-download-handoff,
    .gd-landed-grid,
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


def _install_html_render_compat(st) -> None:
    """Route raw HTML/CSS snippets through st.html when the Streamlit version supports it."""

    html_renderer = getattr(st, "html", None)
    if not callable(html_renderer) or getattr(st, "_gd_html_render_compat", False):
        return

    original_markdown = st.markdown

    def markdown_compat(body, unsafe_allow_html=False, *args, **kwargs):
        if unsafe_allow_html and not args and set(kwargs).issubset({"width"}):
            html_kwargs = {"width": kwargs["width"]} if "width" in kwargs else {}
            return html_renderer(body, **html_kwargs)
        return original_markdown(body, unsafe_allow_html=unsafe_allow_html, *args, **kwargs)

    st.markdown = markdown_compat
    st._gd_html_render_compat = True

    try:
        from streamlit.delta_generator import DeltaGenerator
    except Exception:  # pragma: no cover - defensive compatibility for unusual Streamlit builds
        return

    if getattr(DeltaGenerator, "_gd_html_render_compat", False):
        return

    original_delta_markdown = DeltaGenerator.markdown

    def delta_markdown_compat(self, body, unsafe_allow_html=False, *args, **kwargs):
        if unsafe_allow_html and not args and set(kwargs).issubset({"width"}):
            delta_html = getattr(self, "html", None)
            if callable(delta_html):
                html_kwargs = {"width": kwargs["width"]} if "width" in kwargs else {}
                return delta_html(body, **html_kwargs)
        return original_delta_markdown(self, body, unsafe_allow_html=unsafe_allow_html, *args, **kwargs)

    DeltaGenerator.markdown = delta_markdown_compat
    DeltaGenerator._gd_html_render_compat = True


def _inject_workbench_style(st) -> None:
    st.markdown(WORKBENCH_CSS, unsafe_allow_html=True)


def _preserve_widget_state(st, keys: list[str]) -> None:
    # Streamlit may clear widget keys when their page is not rendered; touching them keeps form values across workflow pages.
    for key in keys:
        if key in st.session_state:
            st.session_state[_stored_widget_key(key)] = st.session_state[key]
            st.session_state[key] = st.session_state[key]


def _stored_widget_key(key: str) -> str:
    return f"{key}__stored_value"


def _stored_widget_value(st, key: str | None, default):
    if not key:
        return default
    store_key = _stored_widget_key(key)
    if store_key in st.session_state:
        return st.session_state[store_key]
    if key in st.session_state:
        return st.session_state[key]
    return default


def _sync_stored_widget_value(st, key: str) -> None:
    st.session_state[_stored_widget_key(key)] = st.session_state.get(key)


def _store_widget_value(st, key: str | None, value):
    if key:
        st.session_state[_stored_widget_key(key)] = value
    return value


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


def _curve_metric_snapshot(
    curve_name: str,
    df: pd.DataFrame | None,
    time_col: str | None,
    value_col: str | None,
) -> dict[str, object] | None:
    if df is None or value_col is None or value_col not in df.columns:
        return None

    values = pd.to_numeric(df[value_col], errors="coerce").dropna()
    if values.empty:
        return None

    total = float(values.sum())
    if curve_name == "负荷":
        label = "负荷电量"
        value = total / 10000
        unit = "亿kWh"
        digits = 2
    elif curve_name == "光伏":
        label = "光伏利用小时"
        value = total
        unit = "h"
        digits = 0
    elif curve_name == "风电":
        label = "风电利用小时"
        value = total
        unit = "h"
        digits = 0
    else:
        label = f"{curve_name}累计"
        value = total
        unit = ""
        digits = 2

    time_range = None
    if time_col and time_col in df.columns:
        timestamps = pd.to_datetime(df[time_col], errors="coerce").dropna()
        if not timestamps.empty:
            time_range = f"{timestamps.min():%Y-%m-%d} ~ {timestamps.max():%Y-%m-%d}"

    return {
        "curve": curve_name,
        "label": label,
        "value": value,
        "unit": unit,
        "digits": digits,
        "points": int(len(values)),
        "total_points": int(len(df)),
        "time_range": time_range,
    }


def _format_curve_metric_value(metric: dict[str, object] | None) -> str:
    if not metric:
        return "待识别"
    value = metric.get("value")
    digits = int(metric.get("digits", 2))
    unit = str(metric.get("unit", ""))
    return f"{_compact_number(value, digits)} {unit}".strip()


def _curve_metric_tooltip(metric: dict[str, object] | None) -> str | None:
    if not metric:
        return None
    lines = [
        f"{metric.get('curve')}曲线基本情况",
        f"{metric.get('label')}：{_format_curve_metric_value(metric)}",
        f"有效点数：{metric.get('points'):,} / {metric.get('total_points'):,}",
    ]
    if metric.get("time_range"):
        lines.append(f"时间范围：{metric['time_range']}")
    return "\n".join(lines)


def _remember_curve_metrics(st, metrics: dict[str, dict[str, object] | None]) -> None:
    available = {key: value for key, value in metrics.items() if value}
    if available:
        st.session_state["curve_metric_snapshot"] = available
    else:
        st.session_state.pop("curve_metric_snapshot", None)


def _render_sidebar_curve_metrics(st) -> None:
    metrics = st.session_state.get("curve_metric_snapshot") or {}
    rows = []
    for curve_name in ["负荷", "光伏", "风电"]:
        metric = metrics.get(curve_name)
        label = metric.get("label") if metric else {
            "负荷": "负荷电量",
            "光伏": "光伏利用小时",
            "风电": "风电利用小时",
        }[curve_name]
        rows.append(
            '<div class="gd-sidebar-metric-row">'
            f"<span>{_safe_html_text(label)}</span>"
            f"<strong>{_safe_html_text(_format_curve_metric_value(metric))}</strong>"
            "</div>"
        )
    st.markdown(
        f"""
        <div class="gd-sidebar-metrics">
          <div class="gd-sidebar-metrics-title">导入曲线</div>
          {''.join(rows)}
          <div class="gd-sidebar-metrics-note">负荷电量单位：亿kWh；风光利用小时单位：h。只读曲线预览，不回写计算链路。</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


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


def _step_lights(current_page: str, statuses: list[tuple[str, bool]]) -> str:
    items = []
    for label, done in statuses:
        classes = ["gd-step-light"]
        if done:
            classes.append("gd-step-ok")
        if label == current_page:
            classes.append("gd-step-active")
        items.append(f'<span class="{" ".join(classes)}">{_safe_html_text(label)}</span>')
    return f'<div class="gd-step-lights">{"".join(items)}</div>'


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
    recommendation_ready = _workflow_step_done(st, "方案推荐")
    chart_ready = _workflow_step_done(st, "图表概览")
    page_meta = WORKFLOW_PAGE_META.get(current_page, WORKFLOW_PAGE_META["欢迎页"])
    data_range, data_range_detail = _data_range_status(batch_result)
    step_status_html = _step_lights(
        current_page,
        [
            ("方案仿真", bool(batch_result)),
            ("经济性测算", economy_done),
            ("方案推荐", recommendation_ready),
            ("图表概览", chart_ready),
            ("图表下载和报告生成", bool(batch_result)),
        ],
    )

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
            "流程状态",
            step_status_html,
        ),
        _topbar_cell(
            "方案池",
            f"{scenario_count} 个 / {passed_count} 达标",
            "推荐和图表围绕代表方案",
        ),
        _topbar_cell(
            "数据时间",
            _safe_html_text(data_range),
            data_range_detail,
        ),
    ]
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


def _boolean_input(
    st,
    label: str,
    *,
    value: bool = False,
    help: str | None = None,
    key: str | None = None,
    disabled: bool = False,
    sync_on_change: bool = True,
) -> bool:
    current_value = bool(_stored_widget_value(st, key, value))
    on_change = _sync_stored_widget_value if key and sync_on_change else None
    args = (st, key) if key and sync_on_change else None
    toggle = getattr(st, "toggle", None)
    if callable(toggle):
        result = bool(toggle(label, value=current_value, help=help, key=key, on_change=on_change, args=args, disabled=disabled))
    else:
        result = bool(st.checkbox(label, value=current_value, help=help, key=key, on_change=on_change, args=args, disabled=disabled))
    return bool(_store_widget_value(st, key, result))


def _curve_display_tooltip(
    curve_name: str,
    df: pd.DataFrame | None,
    time_col: str | None,
    value_col: str | None,
) -> str | None:
    return _curve_metric_tooltip(_curve_metric_snapshot(curve_name, df, time_col, value_col))


def _render_curve_overview_cards(
    st,
    curve_files: dict[str, object],
    curve_columns: dict[str, tuple[str | None, str | None]],
    curve_tooltips: dict[str, str | None] | None = None,
) -> None:
    cards: list[str] = []
    curve_tooltips = curve_tooltips or {}
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
        tooltip = curve_tooltips.get(curve_name)
        info_html = (
            f'<span class="gd-info-dot" title="{_safe_html_text(tooltip)}">i</span>'
            if tooltip
            else ""
        )
        cards.append(
            f'<div class="gd-sim-file-card {"gd-ready" if ready else ""}">'
            f"<strong><span>{_safe_html_text(curve_name)}</span>{info_html}</strong>"
            f"<span>{_safe_html_text(file_name)}</span>"
            f"<span>{_safe_html_text(detail)}</span>"
            "</div>"
        )
    st.markdown(f'<div class="gd-sim-file-grid">{"".join(cards)}</div>', unsafe_allow_html=True)


def _truthy_env(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "local"}


def _runtime_snapshot_enabled() -> bool:
    if _pilot_auth_enabled():
        return False
    return _truthy_env(os.environ.get(RUNTIME_SNAPSHOT_ENV))


def _pilot_auth_enabled() -> bool:
    return _truthy_env(os.environ.get(PILOT_AUTH_ENV))


def _pilot_store_dir() -> Path:
    configured = os.environ.get(PILOT_STORE_DIR_ENV)
    return Path(configured).expanduser().resolve() if configured else PILOT_DEFAULT_STORE_DIR.resolve()


def _pilot_auth_service() -> LocalPilotAuth:
    root = _pilot_store_dir()
    registry = LocalPilotRegistry(root)
    result_store = LocalResultStore(root)
    return LocalPilotAuth(root, registry=registry, result_store=result_store)


def _pilot_admin_service() -> LocalPilotAdminService:
    root = _pilot_store_dir()
    registry = LocalPilotRegistry(root)
    result_store = LocalResultStore(root)
    auth = LocalPilotAuth(root, registry=registry, result_store=result_store)
    return LocalPilotAdminService(registry=registry, auth=auth, result_store=result_store)


def _pilot_access_service() -> PilotAccessService:
    root = _pilot_store_dir()
    registry = LocalPilotRegistry(root)
    job_store = LocalJobStore(root)
    result_store = LocalResultStore(root)
    return PilotAccessService(registry=registry, job_store=job_store, result_store=result_store)


def _current_pilot_user_id(st) -> str | None:
    user_id = st.session_state.get(PILOT_USER_ID_KEY)
    return str(user_id) if user_id else None


def _current_pilot_user_is_platform_admin(st) -> bool:
    return bool(st.session_state.get(PILOT_IS_PLATFORM_ADMIN_KEY))


def _clear_pilot_work_state(st) -> None:
    for key in PILOT_AUTH_WORK_STATE_KEYS:
        st.session_state.pop(key, None)
    st.session_state[WORKFLOW_PAGE_KEY] = WORKFLOW_PAGES[0]


def _clear_pilot_session(st, *, clear_work_state: bool) -> None:
    for key in PILOT_AUTH_SESSION_KEYS:
        st.session_state.pop(key, None)
    if clear_work_state:
        _clear_pilot_work_state(st)


def _pilot_authenticated_user(st):
    session_id = st.session_state.get(PILOT_SESSION_ID_KEY)
    token = st.session_state.get(PILOT_SESSION_TOKEN_KEY)
    if not session_id or not token:
        return None
    try:
        user = _pilot_auth_service().require_session(session_id=str(session_id), token=str(token))
    except (PilotAuthError, FileNotFoundError, ValueError):
        _clear_pilot_session(st, clear_work_state=True)
        st.session_state[PILOT_LOGIN_NOTICE_KEY] = "登录状态已失效，请重新登录。"
        return None
    st.session_state[PILOT_USER_ID_KEY] = user.user_id
    st.session_state[PILOT_USER_DISPLAY_KEY] = user.display_name
    st.session_state[PILOT_LOGIN_NAME_KEY] = user.login_name
    st.session_state[PILOT_IS_PLATFORM_ADMIN_KEY] = bool(user.is_platform_admin)
    return user


def _render_pilot_login_page(st) -> None:
    st.markdown("## 内部试用登录")
    st.caption("当前部署已启用账号门禁。请使用管理员通过 pilot-admin 创建的账号登录。")

    notice = st.session_state.pop(PILOT_LOGIN_NOTICE_KEY, None)
    if notice:
        st.warning(notice)

    with st.form("pilot_login_form"):
        login_name = st.text_input("账号 / 邮箱", key="pilot_login_name_input")
        password = st.text_input("密码", type="password", key="pilot_login_password_input")
        submitted = st.form_submit_button("登录", type="primary")

    if not submitted:
        st.info(
            "如果还没有账号，请先在部署机器上使用 "
            "`green-direct pilot-admin bootstrap` 或 "
            "`PYTHONPATH=src python -m green_direct.cli pilot-admin bootstrap` 创建首个平台管理员。"
        )
        return

    if not str(login_name).strip() or not str(password):
        st.error("请输入账号和密码。")
        return

    try:
        session = _pilot_auth_service().login(login_name=str(login_name).strip(), password=str(password))
    except PilotAuthError:
        st.error("账号或密码不正确，或账号已停用。")
        return
    except FileNotFoundError:
        st.error("未找到内部试用账号数据。请先使用 pilot-admin bootstrap 创建首个平台管理员。")
        return

    _clear_pilot_work_state(st)
    st.session_state[PILOT_SESSION_ID_KEY] = session.session_id
    st.session_state[PILOT_SESSION_TOKEN_KEY] = session.token
    st.session_state[PILOT_USER_ID_KEY] = session.user_id
    st.session_state[PILOT_IS_PLATFORM_ADMIN_KEY] = False
    st.session_state[PILOT_LOGIN_NOTICE_KEY] = "登录成功。"
    st.rerun()


def _render_pilot_account_sidebar(st, user) -> None:
    with st.sidebar:
        st.markdown("---")
        st.caption("内部试用账号")
        st.write(f"{user.display_name}（{user.login_name}）")
        if user.is_platform_admin:
            st.caption("平台管理员")
        if st.button("退出登录", key="pilot_logout"):
            session_id = st.session_state.get(PILOT_SESSION_ID_KEY)
            if session_id:
                try:
                    _pilot_auth_service().revoke_session(str(session_id))
                except Exception:  # noqa: BLE001 - logout should still clear local UI state
                    pass
            _clear_pilot_session(st, clear_work_state=True)
            st.session_state[PILOT_LOGIN_NOTICE_KEY] = "已退出登录。"
            st.rerun()


def _ensure_pilot_authenticated(st) -> bool:
    if not _pilot_auth_enabled():
        return True
    user = _pilot_authenticated_user(st)
    if user is None:
        _render_pilot_login_page(st)
        return False
    _render_pilot_account_sidebar(st, user)
    return True


def _current_pilot_project_id(st) -> str | None:
    project_id = st.session_state.get(PILOT_ACTIVE_PROJECT_ID_KEY)
    return str(project_id) if project_id else None


def _clear_pilot_project_context(st, *, clear_work_state: bool) -> None:
    for key in (
        PILOT_ACTIVE_PROJECT_ID_KEY,
        PILOT_ACTIVE_PROJECT_NAME_KEY,
        PILOT_ACTIVE_PROJECT_ROLE_KEY,
    ):
        st.session_state.pop(key, None)
    if clear_work_state:
        _clear_pilot_work_state(st)


def _activate_pilot_project(
    st,
    *,
    project: Project,
    membership: ProjectMembership,
    clear_work_state: bool,
) -> None:
    previous_project_id = _current_pilot_project_id(st)
    previous_role = st.session_state.get(PILOT_ACTIVE_PROJECT_ROLE_KEY)
    st.session_state[PILOT_ACTIVE_PROJECT_ID_KEY] = project.project_id
    st.session_state[PILOT_ACTIVE_PROJECT_NAME_KEY] = project.name
    st.session_state[PILOT_ACTIVE_PROJECT_ROLE_KEY] = membership.role.value
    if clear_work_state and previous_project_id and previous_project_id != project.project_id:
        _clear_pilot_work_state(st)
    elif previous_role and previous_role != membership.role.value:
        _clear_pilot_work_state(st)


def _current_pilot_project_can_submit_jobs(st) -> bool:
    if not _pilot_auth_enabled():
        return True
    return st.session_state.get(PILOT_ACTIVE_PROJECT_ROLE_KEY) in {
        ProjectRole.ADMIN.value,
        ProjectRole.ANALYST.value,
    }


def _render_pilot_project_submit_permission_block(st) -> None:
    st.markdown("## 当前项目为只读权限")
    st.warning("你的项目角色当前不能发起新的技术仿真或经济性测算。请联系项目管理员或平台管理员调整为 admin / analyst 后再运行计算。")


def _study_result_with_pilot_refs(study_result: StudyResult, persisted) -> StudyResult:
    refs = {
        **study_result.result_store_refs,
        "project_id": persisted.job.project_id,
        "technical_job_id": persisted.job.job_id,
        "technical_result_id": persisted.result_record.result_id,
        "technical_summary_artifact_id": persisted.technical_summary_artifact.artifact_id,
        "config_snapshot_artifact_id": persisted.config_snapshot_artifact.artifact_id,
    }
    return replace(study_result, result_store_refs=refs)


def _study_result_with_pilot_economy_refs(study_result: StudyResult, persisted) -> StudyResult:
    refs = {
        **study_result.result_store_refs,
        "project_id": persisted.job.project_id,
        "economy_job_id": persisted.job.job_id,
        "economy_result_id": persisted.result_record.result_id,
        "power_economy_summary_artifact_id": persisted.power_summary_artifact.artifact_id,
        "single_entity_summary_artifact_id": persisted.single_entity_summary_artifact.artifact_id,
        "economy_input_fingerprint": persisted.input_fingerprint,
    }
    return replace(study_result, result_store_refs=refs)


def _study_result_with_pilot_recommendation_refs(study_result: StudyResult, persisted) -> StudyResult:
    refs = {
        **study_result.result_store_refs,
        "project_id": persisted.job.project_id,
        "recommendation_job_id": persisted.job.job_id,
        "recommendation_result_id": persisted.result_record.result_id,
        "recommendation_portfolio_artifact_id": persisted.portfolio_artifact.artifact_id,
        "recommendation_load_side_detail_artifact_id": persisted.load_side_detail_artifact.artifact_id,
        "recommendation_input_fingerprint": persisted.input_fingerprint,
    }
    return replace(study_result, result_store_refs=refs)


def _current_pilot_study_id(st) -> str | None:
    study_result = st.session_state.get("study_result")
    if isinstance(study_result, StudyResult):
        return study_result.study_id
    snapshot = st.session_state.get("config_snapshot")
    if isinstance(snapshot, dict) and snapshot.get("study_id"):
        return str(snapshot["study_id"])
    return None


def _persist_pilot_technical_result_if_enabled(st, technical_result) -> object | None:
    if not _pilot_auth_enabled():
        return None
    actor_user_id = _current_pilot_user_id(st)
    project_id = _current_pilot_project_id(st)
    if not actor_user_id or not project_id:
        return None
    try:
        persisted = persist_technical_study_result(
            access_service=_pilot_access_service(),
            actor_user_id=actor_user_id,
            project_id=project_id,
            technical_result=technical_result,
        )
    except Exception as exc:  # noqa: BLE001 - persistence failure should not discard the computed study
        if isinstance(exc, (PilotAccessError, FileExistsError, FileNotFoundError, ValueError, OSError)):
            st.session_state[PILOT_RESULT_STORE_NOTICE_KEY] = f"项目结果保存失败：{exc}"
            return None
        raise
    st.session_state[PILOT_RESULT_STORE_NOTICE_KEY] = (
        f"已写入项目结果存储：Job {persisted.job.job_id} / Result {persisted.result_record.result_id}"
    )
    return persisted


def _persist_pilot_economic_result_if_enabled(st, economic_result) -> object | None:
    if not _pilot_auth_enabled():
        return None
    actor_user_id = _current_pilot_user_id(st)
    project_id = _current_pilot_project_id(st)
    study_id = _current_pilot_study_id(st)
    if not actor_user_id or not project_id or not study_id:
        return None
    try:
        persisted = persist_economic_study_result(
            access_service=_pilot_access_service(),
            actor_user_id=actor_user_id,
            project_id=project_id,
            study_id=study_id,
            economic_result=economic_result,
        )
    except Exception as exc:  # noqa: BLE001 - persistence failure should not discard the computed study
        if isinstance(exc, (PilotAccessError, FileExistsError, FileNotFoundError, ValueError, OSError)):
            st.session_state[PILOT_RESULT_STORE_NOTICE_KEY] = f"项目经济结果保存失败：{exc}"
            return None
        raise
    st.session_state[PILOT_RESULT_STORE_NOTICE_KEY] = (
        f"已写入项目经济结果存储：Job {persisted.job.job_id} / Result {persisted.result_record.result_id}"
    )
    return persisted


def _persist_pilot_recommendation_result_if_enabled(st, recommendation_result) -> object | None:
    if not _pilot_auth_enabled():
        return None
    signature = recommendation_result_fingerprint(recommendation_result)
    if st.session_state.get(PILOT_RECOMMENDATION_STORE_SIGNATURE_KEY) == signature:
        return None
    actor_user_id = _current_pilot_user_id(st)
    project_id = _current_pilot_project_id(st)
    study_id = _current_pilot_study_id(st)
    if not actor_user_id or not project_id or not study_id:
        return None
    try:
        persisted = persist_recommendation_study_result(
            access_service=_pilot_access_service(),
            actor_user_id=actor_user_id,
            project_id=project_id,
            study_id=study_id,
            recommendation_result=recommendation_result,
        )
    except Exception as exc:  # noqa: BLE001 - persistence failure should not discard the computed study
        if isinstance(exc, (PilotAccessError, FileExistsError, FileNotFoundError, ValueError, OSError)):
            st.session_state[PILOT_RESULT_STORE_NOTICE_KEY] = f"项目推荐结果保存失败：{exc}"
            return None
        raise
    st.session_state[PILOT_RECOMMENDATION_STORE_SIGNATURE_KEY] = signature
    st.session_state[PILOT_RESULT_STORE_NOTICE_KEY] = (
        f"已写入项目推荐结果存储：Job {persisted.job.job_id} / Result {persisted.result_record.result_id}"
    )
    return persisted


def _pilot_project_option_label(option: tuple[Project, ProjectMembership]) -> str:
    project, membership = option
    return f"{project.name} ({project.project_id}, {membership.role.value})"


def _render_create_project_form(st, *, actor_user_id: str, form_key: str) -> None:
    with st.form(form_key):
        project_id = st.text_input(
            "项目 ID",
            key=f"{form_key}_project_id",
            help="建议使用英文、数字、下划线或短横线，例如 pilot_project_01。",
        )
        project_name = st.text_input("项目名称", key=f"{form_key}_project_name")
        submitted = st.form_submit_button("创建项目", type="primary")

    if not submitted:
        return

    try:
        project = _pilot_access_service().create_project(
            actor_user_id=actor_user_id,
            project=Project(
                str(project_id).strip(),
                str(project_name).strip(),
                created_by_user_id=actor_user_id,
            ),
        )
        membership = _pilot_access_service().registry.get_project_membership(project.project_id, actor_user_id)
        if membership is None:
            raise PilotAccessError("Project was created but membership was not initialized.")
        _activate_pilot_project(st, project=project, membership=membership, clear_work_state=True)
        st.session_state[PILOT_PROJECT_NOTICE_KEY] = f"已创建并进入项目：{project.name}"
        st.rerun()
    except Exception as exc:  # noqa: BLE001 - form errors should be visible
        if isinstance(exc, (PilotAccessError, FileExistsError, FileNotFoundError, ValueError)):
            st.error(str(exc))
        else:
            raise exc


def _render_pilot_project_sidebar(
    st,
    *,
    actor_user_id: str,
    visible_projects: list[tuple[Project, ProjectMembership]],
) -> None:
    with st.sidebar:
        st.markdown("---")
        st.caption("项目工作区")
        if visible_projects:
            project_ids = [project.project_id for project, _membership in visible_projects]
            active_project_id = _current_pilot_project_id(st)
            active_index = project_ids.index(active_project_id) if active_project_id in project_ids else 0
            selected_project_id = st.selectbox(
                "当前项目",
                project_ids,
                index=active_index,
                format_func=lambda project_id: _pilot_project_option_label(
                    visible_projects[project_ids.index(project_id)]
                ),
                key="pilot_active_project_select",
            )
            selected_project, selected_membership = visible_projects[project_ids.index(selected_project_id)]
            if selected_project_id != active_project_id:
                _activate_pilot_project(
                    st,
                    project=selected_project,
                    membership=selected_membership,
                    clear_work_state=True,
                )
                st.session_state[PILOT_PROJECT_NOTICE_KEY] = f"已切换到项目：{selected_project.name}"
                st.rerun()
            st.caption(f"当前角色：{selected_membership.role.value}")
            with st.expander("新建项目"):
                _render_create_project_form(
                    st,
                    actor_user_id=actor_user_id,
                    form_key="pilot_sidebar_create_project_form",
                )
        else:
            st.info("当前账号尚未加入项目。")


def _pilot_datetime_text(value) -> str:
    return value.strftime("%Y-%m-%d %H:%M") if value else "-"


def _pilot_job_history_frame(jobs: list[Job], *, limit: int = 8) -> pd.DataFrame:
    sorted_jobs = sorted(jobs, key=lambda job: (job.queued_at, job.study_id, job.job_id), reverse=True)
    rows = []
    for job in sorted_jobs[:limit]:
        progress = f"{job.progress_current}/{job.progress_total}" if job.progress_total else str(job.progress_current)
        rows.append(
            {
                "job_id": job.job_id,
                "study_id": job.study_id,
                "类型": job.job_type.value,
                "状态": job.status.value,
                "进度": progress,
                "发起人": job.requested_by_user_id,
                "开始": _pilot_datetime_text(job.started_at),
                "完成": _pilot_datetime_text(job.finished_at),
                "说明": job.error_message or job.progress_message or "",
            }
        )
    return pd.DataFrame(rows)


def _pilot_result_record_kind(record: StudyResultRecord) -> str:
    if record.recommendation_artifact_id:
        return "recommendation"
    if record.economy_summary_artifact_id or record.single_entity_summary_artifact_id:
        return "economy"
    if record.technical_summary_artifact_id:
        return "technical"
    if record.report_artifact_ids:
        return "report"
    if record.hourly_detail_artifact_ids:
        return "hourly_detail"
    return "result"


def _pilot_result_artifact_count(record: StudyResultRecord) -> int:
    artifact_ids = [
        record.technical_summary_artifact_id,
        record.economy_summary_artifact_id,
        record.single_entity_summary_artifact_id,
        record.recommendation_artifact_id,
    ]
    direct_artifact_count = sum(1 for artifact_id in artifact_ids if artifact_id)
    return direct_artifact_count + len(record.hourly_detail_artifact_ids) + len(record.report_artifact_ids)


def _pilot_result_history_frame(records: list[StudyResultRecord], *, limit: int = 8) -> pd.DataFrame:
    sorted_records = sorted(
        records,
        key=lambda record: (record.created_at, record.study_id, record.result_id),
        reverse=True,
    )
    rows = []
    for record in sorted_records[:limit]:
        rows.append(
            {
                "result_id": record.result_id,
                "study_id": record.study_id,
                "类型": _pilot_result_record_kind(record),
                "产物数": _pilot_result_artifact_count(record),
                "来源 Job": record.created_by_job_id,
                "保存时间": _pilot_datetime_text(record.created_at),
            }
        )
    return pd.DataFrame(rows)


def _render_pilot_project_activity(st) -> None:
    if not _pilot_auth_enabled():
        return
    actor_user_id = _current_pilot_user_id(st)
    project_id = _current_pilot_project_id(st)
    if not actor_user_id or not project_id:
        return
    try:
        access = _pilot_access_service()
        jobs = access.list_project_jobs(actor_user_id=actor_user_id, project_id=project_id)
        records = access.list_project_result_records(actor_user_id=actor_user_id, project_id=project_id)
    except Exception as exc:  # noqa: BLE001 - project activity should not block the main workflow
        if isinstance(exc, (PilotAccessError, FileNotFoundError, ValueError, OSError)):
            st.warning(f"项目任务与结果暂不可读：{exc}")
            return
        raise

    st.markdown("### 项目任务与结果")
    col1, col2 = st.columns(2)
    col1.metric("已登记任务", len(jobs))
    col2.metric("已保存结果", len(records))
    left, right = st.columns(2)
    with left:
        st.caption("最近任务")
        jobs_frame = _pilot_job_history_frame(jobs)
        if jobs_frame.empty:
            st.info("当前项目还没有任务记录。")
        else:
            st.dataframe(jobs_frame, width="stretch", hide_index=True)
    with right:
        st.caption("最近结果索引")
        results_frame = _pilot_result_history_frame(records)
        if results_frame.empty:
            st.info("当前项目还没有保存结果。")
        else:
            st.dataframe(results_frame, width="stretch", hide_index=True)


def _ensure_pilot_project_selected(st) -> bool:
    if not _pilot_auth_enabled():
        return True

    actor_user_id = _current_pilot_user_id(st)
    if not actor_user_id:
        st.warning("登录状态缺少用户信息，请重新登录。")
        return False

    try:
        visible_projects = _pilot_access_service().list_accessible_projects(actor_user_id=actor_user_id)
    except Exception as exc:  # noqa: BLE001 - permission/storage errors should be visible
        if isinstance(exc, (PilotAccessError, FileNotFoundError, ValueError)):
            st.error(str(exc))
            return False
        raise exc

    active_project_id = _current_pilot_project_id(st)
    visible_by_id = {project.project_id: (project, membership) for project, membership in visible_projects}
    if active_project_id in visible_by_id:
        project, membership = visible_by_id[active_project_id]
        _activate_pilot_project(st, project=project, membership=membership, clear_work_state=False)
    elif visible_projects:
        if active_project_id:
            _clear_pilot_project_context(st, clear_work_state=True)
        project, membership = visible_projects[0]
        _activate_pilot_project(st, project=project, membership=membership, clear_work_state=False)
    else:
        _clear_pilot_project_context(st, clear_work_state=True)

    _render_pilot_project_sidebar(st, actor_user_id=actor_user_id, visible_projects=visible_projects)

    notice = st.session_state.pop(PILOT_PROJECT_NOTICE_KEY, None)
    if notice:
        st.success(notice)

    if _current_pilot_project_id(st):
        return True

    st.markdown("## 项目工作区")
    st.caption("内部试用部署已启用账号和项目边界。请先创建或加入一个项目，再开始方案仿真。")
    st.info("当前账号尚未加入任何有效项目。你可以先创建一个项目；平台管理员也可以在后台把你加入已有项目。")
    _render_create_project_form(st, actor_user_id=actor_user_id, form_key="pilot_main_create_project_form")
    return False


def _platform_admin_user_frame(users: list[User]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "用户 ID": user.user_id,
                "登录名": user.login_name,
                "显示名称": user.display_name,
                "状态": user.status.value,
                "平台管理员": "是" if user.is_platform_admin else "否",
                "创建时间": user.created_at.isoformat(),
            }
            for user in users
        ]
    )


def _platform_admin_session_frame(sessions) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "session_id": session.session_id,
                "user_id": session.user_id,
                "expires_at": session.expires_at.isoformat(),
                "revoked": "是" if session.is_revoked else "否",
            }
            for session in sessions
        ]
    )


def _platform_admin_project_frame(projects: list[Project]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "项目 ID": project.project_id,
                "项目名称": project.name,
                "状态": project.status.value,
                "创建人": project.created_by_user_id or "",
                "创建时间": project.created_at.isoformat(),
            }
            for project in projects
        ]
    )


def _platform_admin_membership_frame(
    memberships: list[ProjectMembership],
    users_by_id: dict[str, User],
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "membership_id": membership.membership_id,
                "用户 ID": membership.user_id,
                "显示名称": users_by_id.get(membership.user_id).display_name
                if membership.user_id in users_by_id
                else "",
                "角色": membership.role.value,
                "状态": membership.status.value,
                "创建时间": membership.created_at.isoformat(),
            }
            for membership in memberships
        ]
    )


def _handle_platform_admin_error(st, exc: Exception) -> None:
    if isinstance(exc, (PilotAdminError, PilotAccessError, PilotAuthError, FileExistsError, FileNotFoundError, ValueError)):
        st.error(str(exc))
    else:
        raise exc


def _render_platform_admin_page(st) -> None:
    if not _pilot_auth_enabled() or not _current_pilot_user_is_platform_admin(st):
        st.warning("当前账号没有平台管理权限。")
        return

    actor_user_id = _current_pilot_user_id(st)
    if not actor_user_id:
        st.warning("登录状态缺少用户信息，请重新登录。")
        return

    admin_service = _pilot_admin_service()
    try:
        users = admin_service.list_users(actor_user_id=actor_user_id)
        projects = admin_service.list_projects(actor_user_id=actor_user_id)
    except Exception as exc:  # noqa: BLE001 - render permission/storage errors as page feedback
        _handle_platform_admin_error(st, exc)
        return

    st.markdown("## 平台管理")
    st.caption("用于内部试用的本地账号管理。当前仍不是正式企业身份系统。")
    notice = st.session_state.pop(PILOT_ADMIN_NOTICE_KEY, None)
    if notice:
        st.success(notice)

    users_by_id = {user.user_id: user for user in users}
    user_ids = list(users_by_id)
    active_user_ids = [user.user_id for user in users if user.is_active]
    project_ids = [project.project_id for project in projects]
    active_count = sum(1 for user in users if user.is_active)
    admin_count = sum(1 for user in users if user.is_active and user.is_platform_admin)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("账号数", len(users))
    c2.metric("活跃账号", active_count)
    c3.metric("活跃平台管理员", admin_count)
    c4.metric("项目数", len(projects))

    st.dataframe(_platform_admin_user_frame(users), width="stretch", hide_index=True)

    create_tab, password_tab, status_tab, project_tab, session_tab = st.tabs(
        ["创建账号", "重置密码", "权限和停用", "项目和成员", "会话"]
    )

    with create_tab:
        with st.form("pilot_admin_create_user_form"):
            user_id = st.text_input("用户 ID", key="pilot_admin_create_user_id")
            login_name = st.text_input("登录名 / 邮箱", key="pilot_admin_create_login_name")
            display_name = st.text_input("显示名称", key="pilot_admin_create_display_name")
            initial_password = st.text_input("初始密码", type="password", key="pilot_admin_create_password")
            is_platform_admin = st.checkbox("设为平台管理员", key="pilot_admin_create_is_admin")
            submitted = st.form_submit_button("创建用户", type="primary")
        if submitted:
            try:
                if not initial_password:
                    raise ValueError("初始密码不能为空。")
                created = admin_service.create_user(
                    actor_user_id=actor_user_id,
                    user=User(
                        str(user_id).strip(),
                        str(login_name).strip(),
                        str(display_name).strip(),
                        is_platform_admin=bool(is_platform_admin),
                    ),
                    initial_password=str(initial_password),
                )
                st.session_state[PILOT_ADMIN_NOTICE_KEY] = f"已创建用户：{created.user_id}"
                st.rerun()
            except Exception as exc:  # noqa: BLE001 - form errors should be visible
                _handle_platform_admin_error(st, exc)

    with password_tab:
        if not user_ids:
            st.info("暂无用户。")
        else:
            with st.form("pilot_admin_reset_password_form"):
                reset_user_id = st.selectbox("选择用户", user_ids, key="pilot_admin_reset_user_id")
                new_password = st.text_input("新密码", type="password", key="pilot_admin_reset_password")
                reset_submitted = st.form_submit_button("重置密码", type="primary")
            if reset_submitted:
                try:
                    if not new_password:
                        raise ValueError("新密码不能为空。")
                    admin_service.set_user_password(
                        actor_user_id=actor_user_id,
                        user_id=str(reset_user_id),
                        password=str(new_password),
                    )
                    st.session_state[PILOT_ADMIN_NOTICE_KEY] = f"已重置密码：{reset_user_id}"
                    st.rerun()
                except Exception as exc:  # noqa: BLE001 - form errors should be visible
                    _handle_platform_admin_error(st, exc)

    with status_tab:
        if not user_ids:
            st.info("暂无用户。")
        else:
            selected_user_id = st.selectbox("选择账号", user_ids, key="pilot_admin_status_user_id")
            selected_user = users_by_id[selected_user_id]
            st.caption(
                f"{selected_user.display_name} / {selected_user.login_name} / "
                f"{selected_user.status.value} / 平台管理员={'是' if selected_user.is_platform_admin else '否'}"
            )
            grant_col, revoke_col, disable_col = st.columns(3)
            with grant_col:
                if st.button("授予平台管理员", key="pilot_admin_grant_admin", disabled=selected_user.is_platform_admin):
                    try:
                        admin_service.set_platform_admin(
                            actor_user_id=actor_user_id,
                            user_id=selected_user_id,
                            is_platform_admin=True,
                        )
                        st.session_state[PILOT_ADMIN_NOTICE_KEY] = f"已授予平台管理员：{selected_user_id}"
                        st.rerun()
                    except Exception as exc:  # noqa: BLE001
                        _handle_platform_admin_error(st, exc)
            with revoke_col:
                if st.button("撤销平台管理员", key="pilot_admin_revoke_admin", disabled=not selected_user.is_platform_admin):
                    try:
                        admin_service.set_platform_admin(
                            actor_user_id=actor_user_id,
                            user_id=selected_user_id,
                            is_platform_admin=False,
                        )
                        st.session_state[PILOT_ADMIN_NOTICE_KEY] = f"已撤销平台管理员：{selected_user_id}"
                        st.rerun()
                    except Exception as exc:  # noqa: BLE001
                        _handle_platform_admin_error(st, exc)
            with disable_col:
                if st.button("停用账号", key="pilot_admin_disable_user", disabled=not selected_user.is_active):
                    try:
                        admin_service.disable_user(actor_user_id=actor_user_id, user_id=selected_user_id)
                        if selected_user_id == actor_user_id:
                            _clear_pilot_session(st, clear_work_state=True)
                            st.session_state[PILOT_LOGIN_NOTICE_KEY] = "当前账号已停用，请使用其他账号登录。"
                        else:
                            st.session_state[PILOT_ADMIN_NOTICE_KEY] = f"已停用账号：{selected_user_id}"
                        st.rerun()
                    except Exception as exc:  # noqa: BLE001
                        _handle_platform_admin_error(st, exc)

    with project_tab:
        if projects:
            st.dataframe(_platform_admin_project_frame(projects), width="stretch", hide_index=True)
        else:
            st.info("暂无项目。用户可以在登录后先创建项目，平台管理员再在此分配成员。")

        if not projects or not active_user_ids:
            if not active_user_ids:
                st.info("暂无可加入项目的活跃用户。")
        else:
            selected_project_id = st.selectbox("选择项目", project_ids, key="pilot_admin_project_id")
            try:
                memberships = admin_service.list_project_memberships(
                    actor_user_id=actor_user_id,
                    project_id=str(selected_project_id),
                )
            except Exception as exc:  # noqa: BLE001
                _handle_platform_admin_error(st, exc)
                memberships = []

            if memberships:
                st.dataframe(
                    _platform_admin_membership_frame(memberships, users_by_id),
                    width="stretch",
                    hide_index=True,
                )
            else:
                st.info("该项目暂无成员。")

            with st.form("pilot_admin_project_member_form"):
                member_user_id = st.selectbox("成员账号", active_user_ids, key="pilot_admin_project_member_user_id")
                role_value = st.selectbox(
                    "项目角色",
                    [role.value for role in ProjectRole],
                    key="pilot_admin_project_member_role",
                )
                grant_submitted = st.form_submit_button("保存项目成员", type="primary")
            if grant_submitted:
                try:
                    membership = admin_service.grant_project_role(
                        actor_user_id=actor_user_id,
                        project_id=str(selected_project_id),
                        user_id=str(member_user_id),
                        role=str(role_value),
                    )
                    st.session_state[PILOT_ADMIN_NOTICE_KEY] = (
                        f"已更新项目成员：{membership.user_id} / {membership.role.value}"
                    )
                    st.rerun()
                except Exception as exc:  # noqa: BLE001
                    _handle_platform_admin_error(st, exc)

            active_memberships = [membership for membership in memberships if membership.is_active]
            if active_memberships:
                disable_user_id = st.selectbox(
                    "移出项目成员",
                    [membership.user_id for membership in active_memberships],
                    key="pilot_admin_project_disable_user_id",
                )
                if st.button("禁用项目成员关系", key="pilot_admin_project_disable_membership"):
                    try:
                        disabled = admin_service.disable_project_membership(
                            actor_user_id=actor_user_id,
                            project_id=str(selected_project_id),
                            user_id=str(disable_user_id),
                        )
                        st.session_state[PILOT_ADMIN_NOTICE_KEY] = f"已禁用项目成员关系：{disabled.user_id}"
                        st.rerun()
                    except Exception as exc:  # noqa: BLE001
                        _handle_platform_admin_error(st, exc)

    with session_tab:
        if not user_ids:
            st.info("暂无用户。")
        else:
            session_user_id = st.selectbox("查看用户", user_ids, key="pilot_admin_session_user_id")
            active_only = st.checkbox("只看有效会话", value=True, key="pilot_admin_session_active_only")
            try:
                sessions = _pilot_auth_service().list_user_sessions(str(session_user_id), active_only=bool(active_only))
            except Exception as exc:  # noqa: BLE001
                _handle_platform_admin_error(st, exc)
                sessions = []
            if sessions:
                st.dataframe(_platform_admin_session_frame(sessions), width="stretch", hide_index=True)
            else:
                st.info("该用户暂无会话记录。")


def _chart_png_docx_session_id(st) -> str:
    session_id = st.session_state.get(CHART_PNG_DOCX_SESSION_ID_KEY)
    if not session_id:
        session_id = uuid.uuid4().hex
        st.session_state[CHART_PNG_DOCX_SESSION_ID_KEY] = session_id
    return str(session_id)


def _clear_chart_export_cache(st) -> None:
    session_id = st.session_state.get(CHART_PNG_DOCX_SESSION_ID_KEY)
    active_signature = st.session_state.get("chart_png_docx_active_signature")
    if session_id and active_signature:
        job = _CHART_PNG_DOCX_JOBS.pop(
            _chart_png_docx_job_key(str(active_signature), session_id=str(session_id)),
            None,
        )
        future = job.get("future") if isinstance(job, dict) else None
        if isinstance(future, Future) and not future.done():
            future.cancel()
    for key in [
        "chart_png_docx_export",
        "chart_png_docx_export_error",
        "chart_png_docx_active_signature",
    ]:
        st.session_state.pop(key, None)


def _clear_economy_outputs(st) -> None:
    for key in [
        "economy_v1_result",
        "single_entity_economy_result",
        "recommendation_v1_inputs",
        "recommendation_v1_result",
        "download_payloads",
    ]:
        st.session_state.pop(key, None)
    study_result = st.session_state.get("study_result")
    if isinstance(study_result, StudyResult) and study_result.technical_result is not None:
        st.session_state["study_result"] = StudyResult.from_technical(study_result.technical_result)


def _save_runtime_snapshot(st) -> None:
    if not _runtime_snapshot_enabled():
        return
    snapshot = {key: st.session_state[key] for key in RUNTIME_SNAPSHOT_KEYS if key in st.session_state}
    if not snapshot:
        return
    RUNTIME_STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = LATEST_SESSION_SNAPSHOT_PATH.with_suffix(".tmp")
    with tmp_path.open("wb") as handle:
        pickle.dump(snapshot, handle, protocol=pickle.HIGHEST_PROTOCOL)
    tmp_path.replace(LATEST_SESSION_SNAPSHOT_PATH)


def _load_runtime_snapshot() -> dict:
    if not _runtime_snapshot_enabled():
        return {}
    if not LATEST_SESSION_SNAPSHOT_PATH.exists():
        return {}
    try:
        with LATEST_SESSION_SNAPSHOT_PATH.open("rb") as handle:
            snapshot = pickle.load(handle)
    except Exception:  # noqa: BLE001 - corrupted local snapshot should not block app startup
        return {}
    return snapshot if isinstance(snapshot, dict) else {}


def _restore_runtime_snapshot_if_needed(st) -> bool:
    if not _runtime_snapshot_enabled():
        return False
    if st.session_state.get("batch_result"):
        return False
    snapshot = _load_runtime_snapshot()
    if not snapshot or "batch_result" not in snapshot:
        return False
    for key, value in snapshot.items():
        if key in RUNTIME_SNAPSHOT_KEYS and key not in st.session_state:
            st.session_state[key] = value
    st.session_state["_runtime_restore_notice"] = "已从项目本地快照恢复最近一次测算结果。"
    return True


def _project_price_curve_data(st):
    if PROJECT_PRICE_CURVE_DATA_KEY in st.session_state and not st.session_state.get(PROJECT_PRICE_CURVE_SESSION_UPLOAD_KEY):
        return None
    return st.session_state.get(PROJECT_PRICE_CURVE_DATA_KEY)


def _project_price_curve_meta(st) -> dict:
    if PROJECT_PRICE_CURVE_DATA_KEY in st.session_state and not st.session_state.get(PROJECT_PRICE_CURVE_SESSION_UPLOAD_KEY):
        return {}
    return st.session_state.get(PROJECT_PRICE_CURVE_META_KEY, {})


def _remember_project_price_curve(st, price_curve_data, source_name: str | None, signature: str | None = None) -> None:
    existing_meta = _project_price_curve_meta(st)
    field_count = len(
        [
            field
            for field in price_curve_data.matched_columns
            if field not in {"timestamp", "hour_index"}
        ]
    )
    meta = {
        "source_name": source_name or "已上传文件",
        "row_count": len(price_curve_data.data),
        "field_count": field_count,
        "signature": signature,
    }
    st.session_state[PROJECT_PRICE_CURVE_DATA_KEY] = price_curve_data
    st.session_state[PROJECT_PRICE_CURVE_META_KEY] = meta
    st.session_state[PROJECT_PRICE_CURVE_SESSION_UPLOAD_KEY] = True
    if meta != existing_meta:
        _clear_economy_outputs(st)
        st.session_state[PROJECT_PRICE_CURVE_NOTICE_KEY] = "已更新项目级下网电价曲线，旧经济性测算结果已清空，请重新计算。"


def _clear_project_price_curve(st) -> dict:
    meta = dict(_project_price_curve_meta(st))
    had_curve = st.session_state.pop(PROJECT_PRICE_CURVE_DATA_KEY, None) is not None
    st.session_state.pop(PROJECT_PRICE_CURVE_META_KEY, None)
    st.session_state.pop(PROJECT_PRICE_CURVE_NOTICE_KEY, None)
    st.session_state.pop(PROJECT_PRICE_CURVE_SESSION_UPLOAD_KEY, None)
    if had_curve:
        _clear_economy_outputs(st)
    return meta


def _clear_unconfirmed_project_price_curve(st) -> bool:
    if PROJECT_PRICE_CURVE_DATA_KEY not in st.session_state:
        return False
    if st.session_state.get(PROJECT_PRICE_CURVE_SESSION_UPLOAD_KEY):
        return False
    meta = _clear_project_price_curve(st)
    return True


def _hourly_detail_row_counts(hourly_details: dict[str, pd.DataFrame] | None) -> set[int]:
    if not hourly_details:
        return set()
    return {len(hourly) for hourly in hourly_details.values() if hourly is not None}


def _format_row_counts(row_counts: set[int]) -> str:
    if not row_counts:
        return "-"
    return " / ".join(f"{row_count:,}" for row_count in sorted(row_counts))


def _discard_incompatible_project_price_curve(
    st,
    hourly_details: dict[str, pd.DataFrame] | None,
) -> str | None:
    price_curve_data = _project_price_curve_data(st)
    if price_curve_data is None:
        return None
    hourly_row_counts = _hourly_detail_row_counts(hourly_details)
    if not hourly_row_counts or hourly_row_counts == {len(price_curve_data.data)}:
        return None

    meta = _clear_project_price_curve(st)
    price_curve_rows = int(meta.get("row_count", len(price_curve_data.data)))
    return (
        f"已清除旧项目级下网电价曲线：曲线 {price_curve_rows:,} 行，"
        f"与当前逐小时明细 {_format_row_counts(hourly_row_counts)} 行不一致。"
        "本次经济性测算将切回固定价/网页组价模式。"
    )


def _clear_project_price_curve_for_partial_hourly_retention(st, detail_retention_plan: dict) -> str | None:
    if detail_retention_plan.get("retain_hourly_details", True):
        return None
    if _project_price_curve_data(st) is None:
        return None
    _clear_project_price_curve(st)
    retained_ids = detail_retention_plan.get("hourly_detail_scenario_ids") or ()
    retained_text = f"仅保留 {len(retained_ids)} 个方案逐小时明细" if retained_ids else "未保留逐小时明细"
    return (
        f"已清除项目级下网电价曲线：价格曲线经济性需要全部候选方案逐小时明细，"
        f"本次大批量模式{retained_text}，经济性测算将切回固定价/网页组价模式。"
    )


def _price_curve_status_text(st) -> str:
    price_curve_data = _project_price_curve_data(st)
    if price_curve_data is None:
        return "未上传下网电价曲线"
    meta = _project_price_curve_meta(st)
    return (
        f"{meta.get('source_name', '已上传文件')}，"
        f"{int(meta.get('row_count', len(price_curve_data.data))):,} 行，"
        f"识别 {int(meta.get('field_count', 0))} 个价格字段"
    )


def _render_project_price_curve_status(st, *, active_label: str = "已上传项目级下网电价曲线") -> None:
    price_curve_data = _project_price_curve_data(st)
    if price_curve_data is None:
        st.info("未上传下网电价曲线。经济性测算将使用网页端固定外部购电净成本或电费清单组价。")
        return
    st.success(f"{active_label}：{_price_curve_status_text(st)}。后续经济性测算使用该曲线。")
    if price_curve_data.warnings:
        for warning in price_curve_data.warnings:
            st.warning(warning)


def _render_simulation_kpis(st, scenario_count: int | None, scenario_grid: dict | None, duration_text: str) -> None:
    count_text = "-" if scenario_count is None else f"{scenario_count:,}"
    if scenario_grid:
        pv_text = _scenario_range_text(scenario_grid["pv_capacity"])
        wind_text = _scenario_range_text(scenario_grid["wind_capacity"])
    else:
        pv_text = "-"
        wind_text = "-"
    st.markdown(
        f"""
        <div class="gd-sim-kpis">
          <div class="gd-sim-kpi"><span>当前表单方案数</span><strong>{_safe_html_text(count_text)}</strong></div>
          <div class="gd-sim-kpi"><span>光伏 / 风电配置</span><strong>{_safe_html_text(pv_text)} / {_safe_html_text(wind_text)}</strong></div>
          <div class="gd-sim-kpi"><span>储能时长</span><strong>{_safe_html_text(duration_text)}</strong></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _scenario_range_text(range_spec: dict) -> str:
    start = float(range_spec["start"])
    end = float(range_spec["end"])
    if start == end:
        return _compact_number(start)
    return f"{_compact_number(start)}-{_compact_number(end)}"


def _exact_range(value: float) -> dict:
    normalized = float(value)
    return {"start": normalized, "end": normalized, "step": max(abs(normalized), 1.0)}


def _single_scenario_grid_from_exact(
    *,
    pv_capacity: float,
    wind_capacity: float,
    bess_power: float,
    bess_energy: float,
) -> tuple[dict | None, list[str]]:
    pv_capacity = float(pv_capacity)
    wind_capacity = float(wind_capacity)
    bess_power = float(bess_power)
    bess_energy = float(bess_energy)

    errors: list[str] = []
    for label, value in [
        ("光伏容量", pv_capacity),
        ("风电容量", wind_capacity),
        ("储能功率", bess_power),
        ("储能容量", bess_energy),
    ]:
        if value < 0:
            errors.append(f"{label}不能小于 0。")
    if pv_capacity <= 0 and wind_capacity <= 0:
        errors.append("指定单方案至少需要配置光伏或风电容量；纯储能/无绿电来源不进入候选方案池。")

    if bess_power <= 0:
        if bess_energy > 0:
            errors.append("储能功率为 0 时，储能容量也应为 0。")
        bess_duration = 0.0
    elif bess_energy <= 0:
        errors.append("储能功率大于 0 时，储能容量也需要大于 0。")
        bess_duration = 0.0
    else:
        bess_duration = round(bess_energy / bess_power, 10)

    if errors:
        return None, errors

    return (
        {
            "pv_capacity": _exact_range(pv_capacity),
            "wind_capacity": _exact_range(wind_capacity),
            "bess_power": _exact_range(bess_power),
            "bess_duration_hours": [bess_duration],
        },
        [],
    )


def _sequential_scenario_ids(limit: int, *, scenario_count: int | None = None) -> tuple[str, ...]:
    if limit <= 0:
        return ()
    capped = min(int(limit), int(scenario_count)) if scenario_count is not None else int(limit)
    return tuple(f"S{index:04d}" for index in range(1, max(0, capped) + 1))


def _technical_detail_retention_plan(
    scenario_count: int | None,
    *,
    threshold: int,
    large_run_hourly_detail_limit: int,
) -> dict:
    """Return the UI retention plan for one technical simulation run."""

    if scenario_count is None or int(scenario_count) <= int(threshold):
        return {
            "mode": "full",
            "retain_hourly_details": True,
            "hourly_detail_scenario_ids": (),
            "message": "小规模测算将保留全部方案逐小时明细。",
        }

    retained_ids = _sequential_scenario_ids(large_run_hourly_detail_limit, scenario_count=scenario_count)
    if retained_ids:
        message = (
            f"大批量模式：本次先保留全部方案汇总，并仅常驻前 {len(retained_ids)} 个方案的逐小时明细；"
            "如需查看其他方案逐小时曲线，请缩小方案范围或使用指定单方案复核。"
        )
    else:
        message = "大批量模式：本次只常驻方案汇总，不保存逐小时明细；如需图表和报告，请缩小范围或使用指定单方案复核。"
    return {
        "mode": "summary_first",
        "retain_hourly_details": False,
        "hourly_detail_scenario_ids": retained_ids,
        "message": message,
    }


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


LANDED_PRICE_FIELDS = [
    "load_landed_price_before_green_with_vat",
    "load_landed_price_after_green_with_vat",
    "load_landed_price_delta_with_vat",
    "green_power_settlement_price_with_vat_effective",
    "green_self_use_landed_price_with_vat_effective",
    "weighted_down_grid_landed_price_with_vat",
    "down_grid_energy_for_landed_price",
    "self_use_energy_for_landed_price",
    "total_load_energy_for_landed_price",
]


def _format_price_value(value, *, signed: bool = False) -> str:
    if not _is_present(value):
        return "-"
    numeric = float(value)
    sign = "+" if signed and numeric >= 0 else ""
    return f"{sign}{numeric:.3f} 元/kWh"


def _ratio_from_energy(row: pd.Series, numerator_field: str, denominator_field: str) -> float | None:
    numerator = row.get(numerator_field)
    denominator = row.get(denominator_field)
    if not _is_present(numerator) or not _is_present(denominator):
        return None
    denominator_value = float(denominator)
    if denominator_value <= 0:
        return None
    return float(numerator) / denominator_value


def _landed_rate(row: pd.Series, field: str, numerator_field: str) -> float | None:
    value = row.get(field)
    if _is_present(value):
        return float(value)
    return _ratio_from_energy(row, numerator_field, "total_load_energy_for_landed_price")


def _landed_price_frame(
    frame: pd.DataFrame | None,
    *,
    scenario_ids: list[str] | None = None,
    limit: int = 4,
) -> pd.DataFrame:
    if frame is None or frame.empty or "scenario_id" not in frame.columns:
        return pd.DataFrame()
    if not {"load_landed_price_before_green_with_vat", "load_landed_price_after_green_with_vat"}.issubset(frame.columns):
        return pd.DataFrame()
    data = frame.copy()
    data["scenario_id"] = data["scenario_id"].astype(str)
    data = data.drop_duplicates("scenario_id")
    if scenario_ids:
        ordered_ids = [str(item) for item in scenario_ids]
        data = data[data["scenario_id"].isin(ordered_ids)].copy()
        order = {scenario_id: index for index, scenario_id in enumerate(ordered_ids)}
        data["_landed_order"] = data["scenario_id"].map(order).fillna(len(order))
        data = data.sort_values("_landed_order").drop(columns=["_landed_order"])
    return data.head(limit)


def _render_landed_price_cards(
    st,
    frame: pd.DataFrame | None,
    *,
    title: str,
    description: str,
    scenario_ids: list[str] | None = None,
    limit: int = 4,
) -> None:
    data = _landed_price_frame(frame, scenario_ids=scenario_ids, limit=limit)
    if data.empty:
        return
    st.markdown(f"#### {title}")
    st.caption(description)
    cards: list[str] = []
    for _, row in data.iterrows():
        scenario_id = str(row.get("scenario_id", "-"))
        green_load_rate = _landed_rate(row, "green_load_rate", "self_use_energy_for_landed_price")
        grid_import_rate = _landed_rate(row, "grid_import_rate", "down_grid_energy_for_landed_price")
        capacity = (
            _capacity_config_text(row)
            if {"pv_capacity", "wind_capacity", "bess_power", "bess_energy"}.issubset(row.index)
            else ""
        )
        mini_metrics = [
            ("绿电占比", _format_report_value(green_load_rate, rate=True) if green_load_rate is not None else "-"),
            ("绿电结算价", _format_price_value(row.get("green_power_settlement_price_with_vat_effective"))),
            ("绿电后绿电到户", _format_price_value(row.get("green_self_use_landed_price_with_vat_effective"))),
            ("下网加权价", _format_price_value(row.get("weighted_down_grid_landed_price_with_vat"))),
            ("下网比例", _format_report_value(grid_import_rate, rate=True) if grid_import_rate is not None else "-"),
            ("后-前", _format_price_value(row.get("load_landed_price_delta_with_vat"), signed=True)),
        ]
        mini_html = "".join(
            (
                '<div>'
                f"<span>{_safe_html_text(label)}</span>"
                f"<strong>{_safe_html_text(value)}</strong>"
                "</div>"
            )
            for label, value in mini_metrics
        )
        cards.append(
            '<div class="gd-landed-card">'
            f"<h4>{_safe_html_text(scenario_id)}</h4>"
            f'<div class="gd-landed-capacity">{_safe_html_text(capacity)}</div>'
            '<div class="gd-landed-main">'
            f'<div><span>绿电前综合到户价</span><strong>{_safe_html_text(_format_price_value(row.get("load_landed_price_before_green_with_vat")))}</strong></div>'
            f'<div><span>绿电后综合到户价</span><strong>{_safe_html_text(_format_price_value(row.get("load_landed_price_after_green_with_vat")))}</strong></div>'
            "</div>"
            f'<div class="gd-landed-mini">{mini_html}</div>'
            "</div>"
        )
    st.markdown(f'<div class="gd-landed-grid">{"".join(cards)}</div>', unsafe_allow_html=True)


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
                _recommendation_metric("绿电前到户价", row.get("load_landed_price_before_green_with_vat"), digits=3),
                _recommendation_metric("绿电后到户价", row.get("load_landed_price_after_green_with_vat"), digits=3),
                _recommendation_metric("绿电结算价", row.get("green_power_settlement_price_with_vat_effective"), digits=3),
                _recommendation_metric("下网加权价", row.get("weighted_down_grid_landed_price_with_vat"), digits=3),
                _recommendation_metric("下网比例", row.get("grid_import_rate"), rate=True),
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
        "load_landed_price_before_green_with_vat",
        "load_landed_price_after_green_with_vat",
        "load_landed_price_delta_with_vat",
        "green_power_settlement_price_with_vat_effective",
        "weighted_down_grid_landed_price_with_vat",
        "grid_import_rate",
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
            width="stretch",
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
                width="stretch",
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
            if _match_price_curve_from_filename(path.name):
                continue
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


def _match_price_curve_from_filename(filename: str) -> bool:
    normalized = filename.lower()
    return any(keyword.lower() in normalized for keyword in PRICE_CURVE_FILE_KEYWORDS)


def _is_supported_technical_curve_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in TECHNICAL_CURVE_FILE_SUFFIXES


def _auto_assign_curve_files(files) -> tuple[dict[str, object], object | None, list[str]]:
    assigned: dict[str, object] = {}
    price_curve_file: object | None = None
    messages: list[str] = []
    for uploaded_file in files or []:
        filename = getattr(uploaded_file, "name", "")
        if _match_price_curve_from_filename(filename):
            if price_curve_file is None:
                price_curve_file = uploaded_file
            else:
                selected_name = getattr(price_curve_file, "name", "已选文件")
                messages.append(f"下网电价曲线匹配到多个文件，已使用 `{selected_name}`，忽略 `{filename}`。")
            continue

        curve_name = _match_curve_from_filename(filename)
        if curve_name is None:
            messages.append(f"未能识别文件 `{filename}`，请使用单独上传入口；若为下网电价曲线，文件名建议包含“电价/价格/下网/price”。")
            continue
        if not _is_supported_technical_curve_file(filename):
            messages.append(f"技术曲线 `{filename}` 当前仅支持 CSV，未纳入负荷/光伏/风电输入。")
            continue
        if curve_name in assigned:
            messages.append(f"`{curve_name}`匹配到多个文件，已使用 `{assigned[curve_name].name}`，忽略 `{filename}`。")
            continue
        assigned[curve_name] = uploaded_file
    return assigned, price_curve_file, messages


def _read_uploaded_price_curve(uploaded_file):
    raw = uploaded_file.getvalue()
    source = BytesIO(raw)
    source.name = getattr(uploaded_file, "name", "uploaded_price_curve")
    return read_price_curve(source), raw


def _remember_uploaded_price_curve(st, uploaded_file, *, context_label: str = "电价曲线") -> None:
    try:
        price_curve_data, raw_price_curve = _read_uploaded_price_curve(uploaded_file)
    except ValueError as exc:
        st.error(f"{context_label}无法使用：{exc}")
        return
    _remember_project_price_curve(
        st,
        price_curve_data,
        getattr(uploaded_file, "name", None),
        hashlib.sha256(raw_price_curve).hexdigest(),
    )


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
    key: str | None = None,
):
    if df is None:
        return None
    columns = list(df.columns)
    if guessed in columns:
        if show_guess_caption:
            st.caption(f"{label}：已自动识别为 `{guessed}`")
        return guessed
    stored = _stored_widget_value(st, key, columns[0])
    index = columns.index(stored) if stored in columns else 0
    selected = st.selectbox(
        label,
        columns,
        index=index,
        key=key,
        on_change=_sync_stored_widget_value if key else None,
        args=(st, key) if key else None,
    )
    return _store_widget_value(st, key, selected)


def _range_inputs(
    st,
    label: str,
    defaults: tuple[float, float, float],
    *,
    key_prefix: str | None = None,
) -> dict:
    c1, c2, c3 = st.columns(3)
    start_key = f"{key_prefix}_start" if key_prefix else None
    end_key = f"{key_prefix}_end" if key_prefix else None
    step_key = f"{key_prefix}_step" if key_prefix else None
    start = c1.number_input(
        f"{label}起始",
        value=float(_stored_widget_value(st, start_key, defaults[0])),
        min_value=0.0,
        step=1.0,
        key=start_key,
        on_change=_sync_stored_widget_value if start_key else None,
        args=(st, start_key) if start_key else None,
    )
    end = c2.number_input(
        f"{label}结束",
        value=float(_stored_widget_value(st, end_key, defaults[1])),
        min_value=0.0,
        step=1.0,
        key=end_key,
        on_change=_sync_stored_widget_value if end_key else None,
        args=(st, end_key) if end_key else None,
    )
    step = c3.number_input(
        f"{label}步长",
        value=float(_stored_widget_value(st, step_key, defaults[2])),
        min_value=0.000001,
        step=1.0,
        key=step_key,
        on_change=_sync_stored_widget_value if step_key else None,
        args=(st, step_key) if step_key else None,
    )
    _store_widget_value(st, start_key, start)
    _store_widget_value(st, end_key, end)
    _store_widget_value(st, step_key, step)
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
    disabled: bool = False,
    key: str | None = None,
    state_st=None,
) -> float:
    state_st = state_st or st
    stored_value = _stored_widget_value(state_st, key, value)
    raw = st.text_input(
        label,
        value=_trim_number(float(stored_value)) if _is_present(stored_value) else "",
        help=help,
        disabled=disabled,
        key=key,
    )
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
    _store_widget_value(state_st, key, parsed)
    return parsed


def _coerce_float(value, default: float) -> float:
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return float(default)


def _economy_float_input(
    root_st,
    container,
    label: str,
    value: float,
    *,
    key: str,
    quick_step: float | None = None,
    min_value: float | None = None,
    max_value: float | None = None,
    help: str | None = None,
    disabled: bool = False,
) -> float:
    stored_value = _coerce_float(_stored_widget_value(root_st, key, value), value)
    if key in root_st.session_state:
        root_st.session_state[key] = _coerce_float(root_st.session_state[key], stored_value)
    step = abs(float(quick_step)) if quick_step else 1.0
    parsed = container.number_input(
        label,
        value=float(stored_value),
        min_value=min_value,
        max_value=max_value,
        step=step,
        help=help,
        disabled=disabled,
        key=key,
    )
    return float(_store_widget_value(root_st, key, parsed))


def _percent_text_input(
    st,
    label: str,
    value_percent: float,
    *,
    min_value: float = 0.0,
    max_value: float = 100.0,
    help: str | None = None,
    disabled: bool = False,
    key: str | None = None,
    state_st=None,
) -> float:
    return _float_text_input(
        st,
        label,
        value_percent,
        min_value=min_value,
        max_value=max_value,
        help=help,
        disabled=disabled,
        key=key,
        state_st=state_st,
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
        st.dataframe(mapping_frame(columns), width="stretch", hide_index=True)


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
        for column in [
            "scenario_id",
            "方案类型",
            "pv_capacity",
            "wind_capacity",
            "bess_power",
            "bess_energy",
            "green_load_rate",
            "grid_import_rate",
            "self_use_energy",
            "grid_import_energy",
            "total_load_energy",
        ]
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


def _merge_landed_price_context(summary: pd.DataFrame, economy_summary: pd.DataFrame | None) -> pd.DataFrame:
    if (
        summary.empty
        or economy_summary is None
        or economy_summary.empty
        or "scenario_id" not in summary.columns
        or "scenario_id" not in economy_summary.columns
    ):
        return summary
    data = summary.copy()
    data["scenario_id"] = data["scenario_id"].astype(str)
    economy = economy_summary.copy()
    economy["scenario_id"] = economy["scenario_id"].astype(str)
    extra_columns = [
        column
        for column in ["scenario_id", "price_mode", *LANDED_PRICE_FIELDS]
        if column in economy.columns and (column == "scenario_id" or column not in data.columns)
    ]
    if extra_columns == ["scenario_id"]:
        return data
    return data.merge(economy[extra_columns].drop_duplicates("scenario_id"), on="scenario_id", how="left")


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
    persisted_recommendation_result = _persist_pilot_recommendation_result_if_enabled(st, recommendation_result)
    study_result = st.session_state.get("study_result")
    if isinstance(study_result, StudyResult):
        next_study_result = study_result.with_recommendation_result(recommendation_result)
        if persisted_recommendation_result is not None:
            next_study_result = _study_result_with_pilot_recommendation_refs(
                next_study_result,
                persisted_recommendation_result,
            )
        st.session_state["study_result"] = next_study_result
    store_notice = st.session_state.pop(PILOT_RESULT_STORE_NOTICE_KEY, "")
    if store_notice:
        st.info(store_notice)
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
        st.dataframe(status_df, width="stretch", hide_index=True)
        for item in statuses:
            st.caption(
                f"{item['曲线']}：{item['小时数']} 小时，"
                f"{item['开始时间']} 至 {item['结束时间']}。"
            )
            if item["大于1点"]:
                st.warning(f"{item['曲线']}标幺值曲线存在数值大于 1 的情况，共 {item['大于1点']} 个点。")
            if item["负值点"]:
                st.info(f"{item['曲线']}曲线存在负值，共 {item['负值点']} 个点，将按站用电参与计算。")


def _render_economy_task_overview(st, summary: pd.DataFrame, *, using_project_price_curve: bool) -> bool:
    economy_result = st.session_state.get("economy_v1_result")
    single_entity_result = st.session_state.get("single_entity_economy_result")
    economy_summary = economy_result.get("summary", pd.DataFrame()) if economy_result else pd.DataFrame()
    single_entity_summary = (
        single_entity_result.get("summary", pd.DataFrame())
        if single_entity_result
        else pd.DataFrame()
    )
    economy_done = not economy_summary.empty
    scenario_count = len(summary) if isinstance(summary, pd.DataFrame) else 0
    passed_count = int(summary["pass_policy"].sum()) if not summary.empty and "pass_policy" in summary.columns else 0
    price_mode = (
        str(economy_result.get("price_mode", "项目级曲线" if using_project_price_curve else "固定价"))
        if economy_result
        else ("项目级曲线" if using_project_price_curve else "固定价/网页组价")
    )
    recommendation_inputs_ready = "recommendation_v1_inputs" in st.session_state
    status_items = [
        ("方案池", f"{passed_count} 个达标 / {scenario_count} 个"),
        ("价格口径", price_mode),
        ("经济结果", "已完成" if economy_done else "待计算"),
        ("推荐输入", "已保存" if recommendation_inputs_ready else "待生成"),
        ("电源 FIRR", _best_scenario_id_by(economy_summary, "firr")),
        ("同体 FIRR", _best_scenario_id_by(single_entity_summary, "single_entity_firr_pre_tax")),
    ]
    strip_html = "".join(
        f'<div class="gd-economy-strip-item"><span>{_safe_html_text(label)}</span><strong>{_safe_html_text(value)}</strong></div>'
        for label, value in status_items
    )
    st.markdown(f'<div class="gd-economy-strip">{strip_html}</div>', unsafe_allow_html=True)

    c1, c2, _ = st.columns([1.0, 1.0, 4.0])
    if c1.button("返回方案仿真", key="economy_back_to_simulation"):
        _go_to_workflow_page(st, "方案仿真")
    if c2.button("查看方案推荐", disabled=not economy_done, key="economy_go_recommendation"):
        _go_to_workflow_page(st, "方案推荐")
    return False


def _render_economy_card_heading(st, title: str, subtitle: str | None = None) -> None:
    subtitle_html = (
        f'<div class="gd-economy-card-subtitle">{_safe_html_text(subtitle)}</div>'
        if subtitle
        else ""
    )
    st.markdown(
        f'<div class="gd-economy-card-title">{_safe_html_text(title)}</div>{subtitle_html}',
        unsafe_allow_html=True,
    )


def _render_economy_v1(
    st,
    summary: pd.DataFrame,
    bess_calendar_life_years: float = 15.0,
    *,
    hourly_details: dict[str, pd.DataFrame] | None = None,
    dt_hours: float = 1.0,
    render_recommendation: bool = True,
) -> None:
    _render_page_heading(st, "经济性测算", "经济性测算仅读取方案汇总结果，不重新计算逐小时调度。")
    economy_notice = st.session_state.pop("_economy_notice", None)
    if economy_notice:
        st.success(economy_notice)
    price_curve_reset_notice = _discard_incompatible_project_price_curve(st, hourly_details)
    if price_curve_reset_notice:
        st.warning(price_curve_reset_notice)
        _save_runtime_snapshot(st)
    project_price_curve_data = _project_price_curve_data(st)
    using_project_price_curve = project_price_curve_data is not None
    if using_project_price_curve:
        st.info("本次使用已上传的项目级下网电价曲线；固定下网价格和电费组价不会覆盖曲线结果。")
        _render_project_price_curve_status(st, active_label="已上传下网电价曲线")
    else:
        st.info("当前未上传项目级下网电价曲线，经济性测算将按固定价/网页组价模式执行。")

    run_economy_top_clicked = _render_economy_task_overview(
        st,
        summary,
        using_project_price_curve=using_project_price_curve,
    )

    with st.form("economy_v1_params_form", clear_on_submit=False):
        submit_col, _ = st.columns([1.15, 4.85])
        run_economy_form_top_clicked = submit_col.form_submit_button(
            "计算经济性 V1",
            type="primary",
            disabled=summary.empty,
        )
        row1_left, row1_right = st.columns([0.72, 1.28], gap="small")
        with row1_left.container(border=True):
            _render_economy_card_heading(st, "运行口径")
            c1, c2 = st.columns(2, gap="small")
            operation_years = int(
                c1.number_input(
                    "运营期（年）",
                    value=int(_stored_widget_value(st, "economy_operation_years", 25)),
                    min_value=1,
                    max_value=40,
                    step=1,
                    key="economy_operation_years",
                )
            )
            _store_widget_value(st, "economy_operation_years", operation_years)
            discount_rate = _percent_text_input(c2, "折现率（%）", 6, min_value=-99, max_value=100)
            min_power_side_acceptable_firr = _optional_percent_text_input(
                st,
                "电源侧最低可接受 FIRR（%）",
                7,
                min_value=0,
                max_value=100,
                help="用于负荷侧可成交收益席位筛选。留空时，该席位不参与默认排序。",
            )

        with row1_right.container(border=True):
            _render_economy_card_heading(st, "建设投资")
            c1, c2, c3 = st.columns(3, gap="small")
            wind_capex = _economy_float_input(
                st,
                c1,
                "风电单位造价（元/kW，含税）",
                5000,
                key="economy_wind_capex",
                quick_step=100,
                min_value=0.0,
            )
            pv_capex = _economy_float_input(
                st,
                c2,
                "光伏单位造价（元/kW，含税）",
                2800,
                key="economy_pv_capex",
                quick_step=100,
                min_value=0.0,
                help="需与光伏标幺曲线容量基准匹配；直流侧曲线填直流侧造价，交流侧曲线填交流侧造价。",
            )
            bess_capex = _economy_float_input(
                st,
                c3,
                "储能单位造价（元/kWh，含税）",
                900,
                key="economy_bess_capex",
                quick_step=100,
                min_value=0.0,
            )
            c1, c2, c3 = st.columns([1.1, 1.1, 0.8], gap="small")
            dedicated_connection_line = _float_text_input(c1, "送出线路投资（万元，含税）", 0, min_value=0.0)
            other_fixed_asset = _float_text_input(c2, "其他固定资产投资（万元，含税）", 0, min_value=0.0)
            construction_vat_rate = _percent_text_input(c3, "进项税率（%）", 10)

        row2_left, row2_right = st.columns([0.9, 1.1], gap="small")
        with row2_left.container(border=True):
            _render_economy_card_heading(st, "运维成本")
            c1, c2, c3 = st.columns(3, gap="small")
            wind_om = _economy_float_input(
                st,
                c1,
                "风电运维（元/kW/年）",
                50,
                key="economy_wind_om",
                quick_step=1,
                min_value=0.0,
            )
            pv_om = _economy_float_input(
                st,
                c2,
                "光伏运维（元/kW/年）",
                25,
                key="economy_pv_om",
                quick_step=1,
                min_value=0.0,
            )
            bess_om = _economy_float_input(
                st,
                c3,
                "储能运维（元/kW/年）",
                18,
                key="economy_bess_om",
                quick_step=1,
                min_value=0.0,
            )
            other_operating_cost = _float_text_input(st, "其他运行成本（万元/年）", 0, min_value=0.0)

        with row2_right.container(border=True):
            _render_economy_card_heading(st, "收入和税金")
            c1, c2, c3, c4 = st.columns(4, gap="small")
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
                "外部购电净成本（元/kWh）",
                0.50,
                min_value=0.0,
                help=(
                    "用于同一主体口径估算每 1 kWh 自发自用绿电替代外部购电带来的税前净节费。"
                    "简化模式下直接使用本输入值；组价模式公式：外部购电净成本单价="
                    "原外部购网电电量类成本单价-绿电直连自发自用仍需缴纳费用单价。"
                    "不等同于负荷侧比较绿电结算价时使用的到户电能量全价。"
                ),
                disabled=using_project_price_curve,
            )
            environmental_value = _float_text_input(c4, "环境价值（元/kWh）", 0, min_value=0.0)
            c1, c2, c3 = st.columns(3, gap="small")
            output_vat_rate = _percent_text_input(c1, "销项税率（%）", 13)
            income_tax_rate = _percent_text_input(c2, "企业所得税率（%）", 25)
            urban_area = c3.selectbox("城建税地区", ["县城、镇 5%", "市区 7%", "其他 1%"])
            urban_tax_rate = {"市区 7%": 0.07, "县城、镇 5%": 0.05, "其他 1%": 0.01}[urban_area]

        row3_left, row3_right = st.columns([1.08, 0.92], gap="small")
        with row3_left.container(border=True):
            _render_economy_card_heading(
                st,
                "到户电价展示",
                "仅用于展示绿电接入前后综合到户价，不等同于同一主体净节费单价。",
            )
            c1, c2, c3 = st.columns(3, gap="small")
            fixed_down_grid_landed_price = _float_text_input(
                c1,
                "下网到户价（元/kWh）",
                0.55,
                min_value=0.0,
                disabled=using_project_price_curve,
                help="无逐时下网电价曲线时，绿电前综合到户价直接使用该值；绿电后按下网电量和自发自用绿电量加权。",
            )
            green_self_use_td_fee = _float_text_input(
                c2,
                "绿电仍缴输配（元/kWh）",
                0.15,
                min_value=0.0,
                disabled=using_project_price_curve,
                help="无逐时下网电价曲线时，用于自发自用绿电的到户综合价展示：绿电结算价 + 输配电价 + 政府基金及附加。",
            )
            green_self_use_gov_fee = _float_text_input(
                c3,
                "绿电仍缴基金（元/kWh）",
                0.03,
                min_value=0.0,
                disabled=using_project_price_curve,
            )
            fixed_green_self_use_extra_fee = green_self_use_td_fee + green_self_use_gov_fee

        with row3_right.container(border=True):
            _render_economy_card_heading(st, "高级参数")
            with st.expander("储能更换", expanded=False):
                st.markdown(
                    '<div class="gd-economy-compact-note">按日历寿命和循环寿命先到者触发更换。</div>',
                    unsafe_allow_html=True,
                )
                c1, c2 = st.columns(2, gap="small")
                replacement_ratio = _percent_text_input(c1, "更换投资比例（%）", 50)
                replacement_vat_rate = _percent_text_input(c2, "更换进项税率（%）", 13)
            replacement_calendar_life = float(bess_calendar_life_years)

            with st.expander("其他经营收入", expanded=False):
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
                    width="stretch",
                    key="economy_other_revenue_editor",
                )
                st.session_state["economy_other_revenue_df"] = other_revenue_df

            with st.expander("电费清单组价", expanded=False):
                if using_project_price_curve:
                    st.caption("当前使用已上传的逐时下网电价曲线；本节固定组价参数不会覆盖曲线结果。")
                    _store_widget_value(st, "economy_use_grid_price_build_up", False)
                    _store_widget_value(st, "economy_override_load_side_avoided_charge", False)
                    st.session_state["economy_use_grid_price_build_up"] = False
                    st.session_state["economy_override_load_side_avoided_charge"] = False
                use_grid_price_build_up = _boolean_input(
                    st,
                    "按电费清单组价覆盖外部购电净成本和负荷侧可减少费用",
                    value=False,
                    help="默认使用上方固定值；勾选后按电费清单中的电量电费项目分别推导同一主体净成本口径和负荷侧现金口径。",
                    key="economy_use_grid_price_build_up",
                    disabled=using_project_price_curve,
                    sync_on_change=False,
                )
                if using_project_price_curve:
                    use_grid_price_build_up = False
                if use_grid_price_build_up:
                    c1, c2 = st.columns(2, gap="small")
                    energy_market_price = _float_text_input(c1, "电能量/市场购电价（元/kWh）", 0.40, min_value=0.0)
                    line_loss_price = _float_text_input(c2, "线损费用（元/kWh）", 0, min_value=0.0)
                    c1, c2 = st.columns(2, gap="small")
                    system_operation_fee = _float_text_input(c1, "系统运行费（元/kWh）", 0, min_value=0.0)
                    transmission_distribution_tariff = _float_text_input(c2, "输配电价（元/kWh）", 0.15, min_value=0.0)
                    c1, c2 = st.columns(2, gap="small")
                    gov_fund_surcharge = _float_text_input(c1, "政府性基金及附加（元/kWh）", 0.03, min_value=0.0, help="按无增值税电量附加处理。")
                    grid_purchase_vat_rate = _percent_text_input(c2, "电网购电增值税率（%）", 13)
                    c1, c2 = st.columns(2, gap="small")
                    retained_transmission_distribution_tariff = _float_text_input(
                        c1,
                        "绿电仍缴输配（元/kWh）",
                        transmission_distribution_tariff,
                        min_value=0.0,
                    )
                    retained_gov_fund_surcharge = _float_text_input(
                        c2,
                        "绿电仍缴基金（元/kWh）",
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
                override_load_side_avoided_charge = _boolean_input(
                    st,
                    "单独覆盖负荷侧可减少购网费用单价",
                    value=False,
                    help=(
                        "默认由上方固定价或电费清单组价内部推导；只有负荷侧账单口径与同一主体净节费口径明显不同时才需要覆盖。"
                    ),
                    key="economy_override_load_side_avoided_charge",
                    disabled=using_project_price_curve,
                    sync_on_change=False,
                )
                if using_project_price_curve:
                    override_load_side_avoided_charge = False
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
                price_curve_data = project_price_curve_data
                if using_project_price_curve:
                    st.caption("本次使用下网电价曲线；固定价/组价仅在无曲线时生效。")
                else:
                    st.caption("未上传项目级下网电价曲线时使用固定价或本页电费清单组价。")

        run_economy_form_bottom_clicked = st.form_submit_button(
            "计算经济性 V1（当前已实现视角）",
            type="primary",
            disabled=summary.empty,
        )
    run_economy_form_clicked = run_economy_form_top_clicked or run_economy_form_bottom_clicked

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

    if run_economy_top_clicked or run_economy_form_clicked:
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
                    price_curve=price_curve_data,
                    hourly_details=hourly_details,
                    dt_hours=dt_hours,
                    fixed_down_grid_landed_price_with_vat=fixed_down_grid_landed_price,
                    fixed_green_self_use_extra_fee_with_vat=fixed_green_self_use_extra_fee,
                )
            persisted_economy_result = _persist_pilot_economic_result_if_enabled(st, economic_study_result)
            st.session_state["economy_v1_result"] = {
                "summary": economic_study_result.power_summary,
                "annual_cashflows": economic_study_result.power_annual_cashflows,
                "price_mode": economic_study_result.price_mode,
                "price_curve_summary": economic_study_result.price_curve_summary,
                "price_curve_diagnostics": economic_study_result.price_curve_diagnostics,
                "landed_price_summary": economic_study_result.landed_price_summary,
            }
            st.session_state["single_entity_economy_result"] = {
                "summary": economic_study_result.single_entity_summary,
                "annual_cashflows": economic_study_result.single_entity_annual_cashflows,
            }
            st.session_state["recommendation_v1_inputs"] = economic_study_result.recommendation_inputs.to_session_dict()
            study_result = st.session_state.get("study_result")
            if isinstance(study_result, StudyResult):
                next_study_result = study_result.with_economic_result(economic_study_result)
                if persisted_economy_result is not None:
                    next_study_result = _study_result_with_pilot_economy_refs(next_study_result, persisted_economy_result)
                st.session_state["study_result"] = next_study_result
            st.session_state.pop("download_payloads", None)
            store_notice = st.session_state.pop(PILOT_RESULT_STORE_NOTICE_KEY, "")
            st.session_state["_economy_notice"] = f"经济性 V1 已计算，推荐页和导出页已可读取经济性结果。{store_notice}"
            _save_runtime_snapshot(st)
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
        price_curve_diagnostics = economy_result.get("price_curve_diagnostics")
        price_curve_warnings = (
            price_curve_diagnostics.warnings_as_messages()
            if price_curve_diagnostics is not None and hasattr(price_curve_diagnostics, "warnings_as_messages")
            else []
        )
        if price_curve_warnings:
            with st.expander("价格曲线对齐诊断", expanded=True):
                for warning in price_curve_warnings:
                    st.warning(warning)
        if not economic_summary.empty:
            display_economic_summary = _merge_result_context(economic_summary, summary)
            display_columns = [
                "scenario_id",
                "方案类型",
                "pv_capacity",
                "wind_capacity",
                "bess_energy",
                "price_mode",
                "load_landed_price_before_green_with_vat",
                "load_landed_price_after_green_with_vat",
                "load_landed_price_delta_with_vat",
                "green_power_settlement_price_with_vat_effective",
                "green_self_use_landed_price_with_vat_effective",
                "weighted_down_grid_landed_price_with_vat",
                "grid_import_rate",
                "green_power_settlement_price_with_vat",
                "grid_export_price_with_vat",
                "fnpv",
                "firr",
                "firr_status",
                "static_payback_year",
                "dynamic_payback_year",
                "construction_cash_outflow",
                "dedicated_connection_line_investment_with_vat",
                "annual_operating_revenue_with_vat",
                "annual_operating_cost_with_vat",
                "load_side_avoided_charge_price_effective",
                "bess_replacement_operation_year",
                "bess_replacement_operation_years",
                "bess_replacement_count",
            ]
            display_columns = [column for column in display_columns if column in display_economic_summary.columns]
            st.success("电源侧经济性 V1 已计算。技术方案汇总表仍保持纯技术指标；下载请前往“图表下载和报告生成”。")
            _render_landed_price_cards(
                st,
                display_economic_summary,
                title="负荷到户电价对比",
                description="按本次经济性输入展示绿电接入前后综合到户价；曲线模式按逐时下网电价加权，固定价模式按页面固定到户价计算。",
                limit=4,
            )

            with st.expander("高级：电源侧经济性汇总复核表", expanded=False):
                st.dataframe(
                    localize_columns(format_display_frame(display_economic_summary[display_columns])),
                    width="stretch",
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
                "load_landed_price_before_green_with_vat",
                "load_landed_price_after_green_with_vat",
                "load_landed_price_delta_with_vat",
                "green_power_settlement_price_with_vat_effective",
                "green_self_use_landed_price_with_vat_effective",
                "weighted_down_grid_landed_price_with_vat",
                "grid_import_rate",
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
                    width="stretch",
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
    if normalized == PLATFORM_ADMIN_PAGE and _current_pilot_user_is_platform_admin(st):
        st.session_state[WORKFLOW_PAGE_KEY] = normalized
        return normalized
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
    if page in {"方案推荐", "图表概览"}:
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
              <div class="gd-brand-subtitle">仿真 · 经济 · 推荐 · 图表 · 导出</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        for workflow_item in WORKFLOW_PAGES:
            meta = WORKFLOW_PAGE_META[workflow_item]
            nav_title = meta.get("nav_title", meta["title"])
            if workflow_item == page:
                st.markdown(
                    f"""
                    <div class="gd-nav-item gd-nav-active">
                      <div class="gd-nav-index">{_safe_html_text(meta["index"])}</div>
                      <div class="gd-nav-title">{_safe_html_text(nav_title)}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            elif st.button(
                f"{meta['index']}  {nav_title}",
                key=f"workflow_nav_{meta['index']}",
                help=meta["subtitle"],
            ):
                _go_to_workflow_page(st, workflow_item)
        if _current_pilot_user_is_platform_admin(st):
            if page == PLATFORM_ADMIN_PAGE:
                st.markdown(
                    """
                    <div class="gd-nav-item gd-nav-active">
                      <div class="gd-nav-index">Admin</div>
                      <div class="gd-nav-title">平台管理</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            elif st.button("Admin  平台管理", key="workflow_nav_platform_admin", help="管理内部试用账号、密码、权限和会话"):
                _go_to_workflow_page(st, PLATFORM_ADMIN_PAGE)
        batch_result = st.session_state.get("batch_result")
        economy_result = st.session_state.get("economy_v1_result")
        economy_done = bool(economy_result and not economy_result.get("summary", pd.DataFrame()).empty)
        st.markdown(
            f"""
            <div class="gd-sidebar-status">
              <div class="gd-sidebar-status-row"><span>方案仿真</span><strong>{'已完成' if batch_result else '未完成'}</strong></div>
              <div class="gd-sidebar-status-row"><span>经济测算</span><strong>{'已完成' if economy_done else '未完成'}</strong></div>
              <div class="gd-sidebar-status-row"><span>推荐方案</span><strong>{'可查看' if _workflow_step_done(st, '方案推荐') else '待结果'}</strong></div>
              <div class="gd-sidebar-status-row"><span>图表概览</span><strong>{'可查看' if _workflow_step_done(st, '图表概览') else '待结果'}</strong></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        _render_sidebar_curve_metrics(st)
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


def _launch_metric(label: str, value: str) -> str:
    return (
        '<div class="gd-launch-metric">'
        f"<span>{_safe_html_text(label)}</span>"
        f"<strong>{_safe_html_text(value)}</strong>"
        "</div>"
    )


def _launch_card(title: str, metrics: list[tuple[str, str]]) -> str:
    return (
        '<div class="gd-launch-card">'
        f"<h3>{_safe_html_text(title)}</h3>"
        f'<div class="gd-launch-metrics">{"".join(_launch_metric(label, value) for label, value in metrics)}</div>'
        "</div>"
    )


def _best_scenario_id_by(summary: pd.DataFrame, column: str, *, ascending: bool = False) -> str:
    if summary.empty or "scenario_id" not in summary.columns or column not in summary.columns:
        return "-"
    values = pd.to_numeric(summary[column], errors="coerce")
    valid = summary.loc[values.notna()].copy()
    if valid.empty:
        return "-"
    valid["_sort_value"] = pd.to_numeric(valid[column], errors="coerce")
    row = valid.sort_values("_sort_value", ascending=ascending).iloc[0]
    return str(row.get("scenario_id", "-"))


def _launch_next_steps(
    *,
    batch_result,
    economy_done: bool,
    recommendation_ready: bool,
    chart_ready: bool,
    has_price_curve: bool,
) -> list[tuple[str, str, str, str]]:
    if not batch_result:
        return [
            ("1. 完成方案仿真", "先上传或启用 Demo 曲线，确认候选方案池和政策约束。", "待开始", "pending"),
            ("2. 计算经济性", "技术方案生成后再输入经济参数。", "等待仿真", "pending"),
            ("3. 查看推荐组合", "推荐页会读取技术和经济结果，不展示全量枚举大表。", "等待结果", "pending"),
        ]
    if not economy_done:
        price_hint = "已上传下网电价曲线" if has_price_curve else "未上传下网电价曲线，将按固定价模式计算"
        return [
            ("1. 复核输入和方案池", "技术仿真已完成，可在 02 页查看达标数量和曲线状态。", "已完成", "ok"),
            ("2. 计算经济性", f"{price_hint}；下一步生成推荐排序所需经济结果。", "推荐", "warn"),
            ("3. 准备推荐组合", "经济性完成后会生成同一主体、电源侧、负荷侧和工程代表席位。", "等待经济", "pending"),
        ]
    if not recommendation_ready or not chart_ready:
        return [
            ("1. 查看推荐组合", "已有经济性结果，可生成代表方案卡片和推荐理由。", "可进入", "ok"),
            ("2. 复核图表", "图表页围绕推荐组合和用户指定方案，不默认展示全量枚举。", "可进入", "ok"),
            ("3. 准备交付包", "默认报告方案会优先使用推荐组合中的有效方案。", "待复核", "pending"),
        ]
    return [
        ("1. 复核推荐组合", "确认默认报告方案、风险提示和可成交收益席位。", "可进入", "ok"),
        ("2. 图表复核", "检查关键指标、容量配置、典型日和关键运行日。", "可进入", "ok"),
        ("3. 交付导出", "导出技术包、经济包、图表包和简版报告。", "推荐", "ok"),
    ]


def _render_welcome_page(st) -> None:
    _render_page_heading(
        st,
        "欢迎页",
        "首页不再只是欢迎文字，而是项目启动台：看准备度、下一步、推荐状态和交付准备。",
    )

    batch_result = st.session_state.get("batch_result")
    economy_result = st.session_state.get("economy_v1_result")
    summary = _summary_from_batch_result(batch_result) if batch_result else pd.DataFrame()
    economy_done = bool(economy_result and not economy_result.get("summary", pd.DataFrame()).empty)
    economy_summary_for_launch = economy_result.get("summary", pd.DataFrame()) if economy_done else pd.DataFrame()
    recommendation_ready = _workflow_step_done(st, "方案推荐")
    chart_ready = _workflow_step_done(st, "图表概览")
    has_price_curve = _project_price_curve_data(st) is not None
    price_curve_meta = _project_price_curve_meta(st)
    scenario_count = int(getattr(batch_result, "scenario_count", 0)) if batch_result else 0
    passed_count = int(summary["pass_policy"].sum()) if not summary.empty and "pass_policy" in summary.columns else 0
    metrics = st.session_state.get("curve_metric_snapshot") or {}
    load_metric = _format_curve_metric_value(metrics.get("负荷"))
    pv_metric = _format_curve_metric_value(metrics.get("光伏"))
    wind_metric = _format_curve_metric_value(metrics.get("风电"))

    recommendation_result = None
    if economy_done and not summary.empty:
        _, recommendation_result, _ = _build_recommendation_result_for_display(st, summary)
    default_report_id = _first_report_scenario_id(summary, recommendation_result)

    cards = [
        _launch_card(
            "输入准备",
            [
                ("负荷曲线", load_metric),
                ("光伏 / 风电", f"{pv_metric} / {wind_metric}"),
                ("下网电价", "已上传" if has_price_curve else "未上传"),
                ("数据时间", _data_range_status(batch_result)[1] if batch_result else "待仿真"),
            ],
        ),
        _launch_card(
            "候选方案池",
            [
                ("总方案", f"{scenario_count}"),
                ("政策达标", f"{passed_count}"),
                ("最高绿电占比", _format_report_value(summary["green_load_rate"].max(), rate=True) if not summary.empty and "green_load_rate" in summary.columns else "-"),
                ("最低弃电率", _format_report_value(summary["curtail_rate"].min(), rate=True) if not summary.empty and "curtail_rate" in summary.columns else "-"),
            ],
        ),
        _launch_card(
            "推荐状态",
            [
                ("默认报告方案", default_report_id or "-"),
                ("推荐席位", "可查看" if recommendation_ready else "待经济结果"),
                ("经济测算", "已完成" if economy_done else "待开始"),
                ("低投资方案", _best_scenario_id_by(economy_summary_for_launch, "construction_cash_outflow", ascending=True)),
            ],
        ),
        _launch_card(
            "交付准备",
            [
                ("技术包", "可导出" if batch_result else "待仿真"),
                ("经济包", "可导出" if economy_done else "待测算"),
                ("图表包", "可准备" if chart_ready else "待推荐"),
                ("报告", "可生成" if batch_result else "待结果"),
            ],
        ),
    ]
    st.markdown(f'<div class="gd-launch-grid">{"".join(cards)}</div>', unsafe_allow_html=True)
    _render_pilot_project_activity(st)

    next_rows = []
    for title, copy, status, state in _launch_next_steps(
        batch_result=batch_result,
        economy_done=economy_done,
        recommendation_ready=recommendation_ready,
        chart_ready=chart_ready,
        has_price_curve=has_price_curve,
    ):
        next_rows.append(
            '<div class="gd-launch-row">'
            f"<strong>{_safe_html_text(title)}</strong>"
            f"<span>{_safe_html_text(copy)}</span>"
            f"{_status_pill(status, state)}"
            "</div>"
        )
    price_source = (
        f"{price_curve_meta.get('source_name', '项目级曲线')} · {price_curve_meta.get('row_count', '-')} 行"
        if has_price_curve
        else "未上传项目级下网电价曲线；经济性会使用网页端固定价/组价模式"
    )
    boundary_rows = [
        ("项目模式", "并网绿电直连", "柴油/离网可靠性后续作为显式资产和模式接入。"),
        ("储能策略", "仅由富余新能源充电", "不允许电网充电，不允许储能放电上网。"),
        ("推荐口径", "经济 V1 + 技术约束", "经济和推荐只读取技术结果，不反向改变逐小时调度。"),
        ("电价来源", price_source, "下网曲线只影响经济性和推荐排序。"),
        ("导出范围", "代表方案优先", "全量枚举留在高级复核和导出，不作为主入口。"),
    ]
    boundary_html = "".join(
        "<tr>"
        f"<td>{_safe_html_text(label)}</td>"
        f"<td>{_safe_html_text(value)}</td>"
        f"<td>{_safe_html_text(note)}</td>"
        "</tr>"
        for label, value, note in boundary_rows
    )
    st.markdown(
        f"""
        <div class="gd-launch-panels">
          <div class="gd-launch-panel">
            <h3>下一步建议</h3>
            {''.join(next_rows)}
          </div>
          <div class="gd-launch-panel">
            <h3>项目边界</h3>
            <table class="gd-boundary-table">
              <thead><tr><th>边界项</th><th>当前值</th><th>说明</th></tr></thead>
              <tbody>{boundary_html}</tbody>
            </table>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    c1, c2, c3 = st.columns([0.9, 0.9, 3.0])
    if c1.button("开始方案仿真", type="primary", key="welcome_start_technical"):
        _go_to_workflow_page(st, "方案仿真")
    if c2.button("查看推荐组合", disabled=not economy_done, key="welcome_go_recommendation"):
        _go_to_workflow_page(st, "方案推荐")
    if c3.button("进入交付导出", disabled=not batch_result, key="welcome_go_exports"):
        _go_to_workflow_page(st, "图表下载和报告生成")


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


def _portfolio_scenario_ids(recommendation_result, valid_ids: list[str]) -> list[str]:
    valid_set = set(valid_ids)
    portfolio = getattr(recommendation_result, "portfolio", None)
    if not isinstance(portfolio, pd.DataFrame) or portfolio.empty or "scenario_id" not in portfolio.columns:
        return []
    return [
        scenario_id
        for scenario_id in dict.fromkeys(portfolio["scenario_id"].dropna().astype(str).tolist())
        if scenario_id in valid_set
    ]


def _scenario_label_lookup(summary: pd.DataFrame) -> dict[str, str]:
    labels: dict[str, str] = {}
    if summary.empty or "scenario_id" not in summary.columns:
        return labels
    for _, row in summary.iterrows():
        scenario_id = str(row["scenario_id"])
        labels[scenario_id] = f"{scenario_id} | {_capacity_config_text(row)}"
    return labels


def _scenario_capacity_lookup(summary: pd.DataFrame) -> dict[str, str]:
    if summary.empty or "scenario_id" not in summary.columns:
        return {}
    return {
        str(row["scenario_id"]): _capacity_config_text(row)
        for _, row in summary.iterrows()
    }


def _render_scenario_chip_row(st, summary: pd.DataFrame, scenario_ids: list[str], *, active_id: str | None = None) -> None:
    if not scenario_ids:
        return
    capacity_lookup = _scenario_capacity_lookup(summary)
    chips = []
    for scenario_id in dict.fromkeys(str(item) for item in scenario_ids):
        capacity = capacity_lookup.get(scenario_id, "配置待识别")
        class_name = "gd-scenario-chip gd-scenario-chip-active" if active_id and scenario_id == str(active_id) else "gd-scenario-chip"
        chips.append(
            f'<div class="{class_name}"><strong>{_safe_html_text(scenario_id)}</strong><br>{_safe_html_text(capacity)}</div>'
        )
    st.markdown(f'<div class="gd-scenario-chip-row">{"".join(chips)}</div>', unsafe_allow_html=True)


def _render_scenario_quick_select_buttons(
    st,
    summary: pd.DataFrame,
    scenario_ids: list[str],
    *,
    active_id: str | None,
    state_key: str,
    key_prefix: str,
    pending_state_key: str | None = None,
) -> None:
    unique_ids = list(dict.fromkeys(str(item) for item in scenario_ids))
    if not unique_ids:
        return
    capacity_lookup = _scenario_capacity_lookup(summary)
    st.caption("点击方案卡片即可切换下方详细图表；下拉框仍可选择全部已计算方案。")
    for start in range(0, len(unique_ids), 3):
        row_ids = unique_ids[start : start + 3]
        columns = st.columns(len(row_ids))
        for column, scenario_id in zip(columns, row_ids):
            capacity = capacity_lookup.get(scenario_id, "配置待识别")
            label = f"{scenario_id}\n{capacity}"
            button_type = "primary" if active_id and scenario_id == str(active_id) else "secondary"
            if column.button(
                label,
                key=f"{key_prefix}_{scenario_id}",
                type=button_type,
                width="stretch",
            ):
                st.session_state[pending_state_key or state_key] = scenario_id
                if hasattr(st, "rerun"):
                    st.rerun()


def _clean_multiselect_state(st, key: str, valid_options: list[str], default: list[str]) -> list[str]:
    valid_set = set(valid_options)
    current = st.session_state.get(key, None)
    if isinstance(current, (list, tuple, set)):
        cleaned = [str(item) for item in current if str(item) in valid_set]
    elif current is None:
        cleaned = [item for item in default if item in valid_set]
    else:
        cleaned = [str(current)] if str(current) in valid_set else []
    st.session_state[key] = cleaned
    return cleaned


def _render_chart_scenario_picker(st, summary: pd.DataFrame, recommendation_result) -> pd.DataFrame:
    valid_ids = _valid_scenario_ids(summary)
    if not valid_ids:
        return pd.DataFrame()

    recommended_ids = _portfolio_scenario_ids(recommendation_result, valid_ids)
    if not recommended_ids:
        fallback_id = _first_report_scenario_id(summary, recommendation_result)
        recommended_ids = [fallback_id] if fallback_id else []

    label_lookup = _scenario_label_lookup(summary)
    default_recommended = recommended_ids[: min(4, len(recommended_ids))]
    _clean_multiselect_state(
        st,
        "chart_overview_recommended_ids",
        recommended_ids,
        default_recommended,
    )
    _clean_multiselect_state(st, "chart_overview_pinned_ids", valid_ids, [])

    with st.container(border=True):
        _render_section_intro(
            st,
            "Scenario Set",
            "方案组合选择",
            "默认纳入推荐席位；也可以从全部已计算方案中加入任意方案参与上方对比。",
        )
        left, right = st.columns(2)
        recommended_selected = left.multiselect(
            "推荐方案",
            options=recommended_ids,
            format_func=lambda scenario_id: label_lookup.get(str(scenario_id), str(scenario_id)),
            key="chart_overview_recommended_ids",
            help="来自方案推荐页面的推荐席位；可取消或多选。",
        )
        pinned_selected = right.multiselect(
            "从全部方案加入",
            options=valid_ids,
            format_func=lambda scenario_id: label_lookup.get(str(scenario_id), str(scenario_id)),
            key="chart_overview_pinned_ids",
            help="可检索并加入任一已计算方案；这里只影响图表对比，不修改推荐结果。",
        )

    selected_ids = [str(item) for item in [*recommended_selected, *pinned_selected]]
    selected_ids = list(dict.fromkeys([item for item in selected_ids if item in set(valid_ids)]))
    if not selected_ids:
        return pd.DataFrame()
    _render_scenario_chip_row(st, summary, selected_ids)
    comparison = summary[summary["scenario_id"].astype(str).isin(selected_ids)].copy()
    order = {scenario_id: index for index, scenario_id in enumerate(selected_ids)}
    comparison["_display_order"] = comparison["scenario_id"].astype(str).map(order).fillna(len(order))
    return comparison.sort_values("_display_order").drop(columns=["_display_order"])


def _policy_thresholds_from_state(st) -> dict[str, float]:
    return {
        "green_load_rate": float(_stored_widget_value(st, "simulation_green_load_rate_min", 0.30)),
        "self_use_rate": float(_stored_widget_value(st, "simulation_self_use_rate_min", 0.60)),
        "export_rate": float(_stored_widget_value(st, "simulation_export_rate_max", 0.20)),
    }


def _build_compact_policy_comparison_figure(comparison: pd.DataFrame, thresholds: dict[str, float] | None = None):
    thresholds = thresholds or {
        "green_load_rate": 0.30,
        "self_use_rate": 0.60,
        "export_rate": 0.20,
        "curtail_rate": 0.0,
    }
    thresholds.setdefault("curtail_rate", 0.0)
    required = ["scenario_id", "green_load_rate", "self_use_rate", "curtail_rate", "export_rate"]
    missing = [column for column in required if column not in comparison.columns]
    if comparison.empty or missing:
        return None, missing

    metrics = [
        ("green_load_rate", f"绿电占比≥{thresholds['green_load_rate']:.0%}", "min", "达标余量", "缺口"),
        ("self_use_rate", f"自发自用率≥{thresholds['self_use_rate']:.0%}", "min", "达标余量", "缺口"),
        ("curtail_rate", "弃电率 低优", "max", "低弃电余量", "低弃电偏离"),
        ("export_rate", f"上网比例≤{thresholds['export_rate']:.0%}", "max", "达标余量", "缺口"),
    ]
    labels: list[str] = []
    matrix: list[list[float]] = []
    text_matrix: list[list[str]] = []
    custom_matrix: list[list[str]] = []
    for _, row in comparison.iterrows():
        scenario_id = str(row["scenario_id"])
        labels.append(scenario_id)
        scenario_detail = _scenario_status_text(comparison, scenario_id)
        row_margins: list[float] = []
        row_text: list[str] = []
        row_custom: list[str] = []
        for column, _, direction, ok_label, risk_label in metrics:
            actual = float(pd.to_numeric(pd.Series([row[column]]), errors="coerce").fillna(0.0).iloc[0])
            threshold = float(thresholds[column])
            margin = actual - threshold if direction == "min" else threshold - actual
            row_margins.append(margin)
            row_text.append(f"{actual:.1%}<br>{margin:+.1%}")
            row_custom.append(f"{scenario_detail}<br>{ok_label if margin >= 0 else risk_label}")
        matrix.append(row_margins)
        text_matrix.append(row_text)
        custom_matrix.append(row_custom)
    max_abs = max(0.05, max(abs(value) for row in matrix for value in row))
    fig = go.Figure(
        data=[
            go.Heatmap(
                z=matrix,
                x=[label for _, label, _, _, _ in metrics],
                y=labels,
                text=text_matrix,
                customdata=custom_matrix,
                texttemplate="%{text}",
                hovertemplate="%{customdata}<br>%{x}: %{z:+.1%}<extra></extra>",
                zmid=0,
                zmin=-max_abs,
                zmax=max_abs,
                colorscale=[
                    [0.0, "#dc2626"],
                    [0.48, "#fee2e2"],
                    [0.50, "#ffffff"],
                    [0.52, "#dcfce7"],
                    [1.0, "#16a34a"],
                ],
                colorbar=dict(title="余量"),
            )
        ]
    )
    fig.update_layout(
        height=max(300, 84 + 46 * len(labels)),
        margin=dict(l=72, r=20, t=42, b=36),
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        font=dict(family="Arial, sans-serif", size=12, color="#172033"),
    )
    fig.update_xaxes(side="top", tickangle=0, automargin=True)
    return fig, []


def _build_capacity_comparison_figure(comparison: pd.DataFrame):
    required = ["scenario_id", "pv_capacity", "wind_capacity", "bess_power", "bess_energy"]
    missing = [column for column in required if column not in comparison.columns]
    if comparison.empty or missing:
        return None, missing

    metrics = [
        ("pv_capacity", "光伏<br>万kW"),
        ("wind_capacity", "风电<br>万kW"),
        ("bess_power", "储能功率<br>万kW"),
        ("bess_energy", "储能容量<br>万kWh"),
    ]
    labels: list[str] = []
    raw_matrix: list[list[float]] = []
    custom_matrix: list[list[str]] = []
    for _, row in comparison.iterrows():
        scenario_id = str(row["scenario_id"])
        labels.append(scenario_id)
        scenario_detail = _scenario_status_text(comparison, scenario_id)
        custom_matrix.append([scenario_detail for _ in metrics])
        raw_matrix.append(
            [
                float(pd.to_numeric(pd.Series([row[column]]), errors="coerce").fillna(0.0).iloc[0])
                for column, _ in metrics
            ]
        )
    raw_frame = pd.DataFrame(raw_matrix, columns=[column for column, _ in metrics])
    normalized = raw_frame.copy()
    for column in normalized.columns:
        max_value = float(normalized[column].max())
        normalized[column] = normalized[column] / max_value if max_value > 0 else 0.0
    text_matrix = [
        [_compact_number(value, 1) for value in row]
        for row in raw_matrix
    ]
    fig = go.Figure(
        data=[
            go.Heatmap(
                z=normalized.to_numpy().tolist(),
                x=[label for _, label in metrics],
                y=labels,
                text=text_matrix,
                customdata=custom_matrix,
                texttemplate="%{text}",
                hovertemplate="%{customdata}<br>%{x}: %{text}<br>相对规模 %{z:.0%}<extra></extra>",
                zmin=0,
                zmax=1,
                colorscale=[
                    [0.0, "#f8fafc"],
                    [0.45, "#d9eaff"],
                    [1.0, "#7fb2f0"],
                ],
                colorbar=dict(title="相对规模"),
            )
        ]
    )
    fig.update_layout(
        height=max(300, 84 + 46 * len(labels)),
        margin=dict(l=72, r=20, t=42, b=36),
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        font=dict(family="Arial, sans-serif", size=12, color="#172033"),
    )
    fig.update_xaxes(side="top", tickangle=0, automargin=True)
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
    add_power_trace(["grid_import_power"], "下网功率", CHART_COLORS["grid_import"], dash="dash")
    add_power_trace(["grid_export_power"], "上网功率", CHART_COLORS["grid_export"], dash="dot")
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
                line=dict(color=CHART_COLORS["soc"], width=2, dash="dash"),
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


def _render_recommendation_dashboard_overview(
    st,
    batch_result,
    summary: pd.DataFrame,
    recommendation_result,
    *,
    comparison: pd.DataFrame | None = None,
    policy_thresholds: dict[str, float] | None = None,
) -> None:
    if comparison is None:
        comparison = _representative_summary_for_dashboard(summary, recommendation_result)
    st.markdown(
        """
        <div class="gd-dashboard-bar">
          <div>
            <div class="gd-dashboard-title">方案组合核心对比</div>
            <div class="gd-dashboard-subtitle">主视图对比推荐与指定方案；典型日曲线放入高级复核，不再作为首屏主图。</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if comparison is None or comparison.empty:
        st.info("请选择至少一个推荐方案或指定方案。")
        return

    _render_landed_price_cards(
        st,
        comparison,
        title="方案组到户电价对比",
        description="展示当前图表组合中各方案的绿电接入前后综合到户价、绿电结算价、下网加权价和下网比例。",
        scenario_ids=comparison["scenario_id"].astype(str).tolist(),
        limit=len(comparison),
    )

    left, right = st.columns(2)
    with left:
        with st.container(border=True):
            st.markdown(
                """
             <div class="gd-chart-panel-head">
               <div>
                 <div class="gd-chart-panel-title">政策底线余量矩阵</div>
                 <div class="gd-chart-panel-note">绿电、自用和上网比例对照约束；弃电率作为低优运行指标纳入复核。</div>
               </div>
                 <div class="gd-chart-panel-tag">政策关系</div>
             </div>
             """,
                unsafe_allow_html=True,
            )
            fig, missing = _build_compact_policy_comparison_figure(comparison, policy_thresholds)
            if fig is None:
                st.info(f"缺少字段，暂不能生成代表方案对比图：{', '.join(missing) if missing else '无代表方案'}")
            else:
                st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    with right:
        with st.container(border=True):
            st.markdown(
                """
             <div class="gd-chart-panel-head">
               <div>
                 <div class="gd-chart-panel-title">容量配置结构矩阵</div>
                 <div class="gd-chart-panel-note">用柔和色阶比较配置结构，格内保留真实容量值，避免混单位柱状图误导。</div>
               </div>
                 <div class="gd-chart-panel-tag">配置结构</div>
             </div>
             """,
                unsafe_allow_html=True,
            )
            fig, missing = _build_capacity_comparison_figure(comparison)
            if fig is None:
                st.info(f"缺少字段，暂不能生成容量配置对比图：{', '.join(missing) if missing else '无代表方案'}")
            else:
                st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


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


def _build_recommendation_result_for_display(st, summary: pd.DataFrame):
    economy_result = st.session_state.get("economy_v1_result")
    single_entity_result = st.session_state.get("single_entity_economy_result")
    recommendation_inputs = st.session_state.get("recommendation_v1_inputs")
    if not economy_result or economy_result.get("summary", pd.DataFrame()).empty:
        return economy_result, None, "请先完成经济性测算，再生成推荐席位和代表方案图表。"
    if not recommendation_inputs:
        return economy_result, None, "请重新运行一次经济性测算，以保存推荐席位所需的价格和门槛参数。"

    recommendation_single_entity_summary = (
        single_entity_result["summary"]
        if single_entity_result and not single_entity_result["summary"].empty
        else None
    )
    try:
        recommendation_result = build_recommendation_study(
            summary,
            economy_result["summary"],
            RecommendationInputSnapshot(**recommendation_inputs),
            single_entity_summary=recommendation_single_entity_summary,
        )
    except Exception as exc:  # noqa: BLE001 - UI should stay readable if recommendation data is incomplete
        return economy_result, None, f"推荐结果暂不可用：{exc}"
    return economy_result, recommendation_result, None


def _render_recommendation_analysis_page(st, batch_result, summary: pd.DataFrame) -> None:
    _render_page_heading(
        st,
        "方案推荐",
        "集中展示推荐席位、容量配置、推荐理由和风险提示；图表已拆到独立模块。",
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
    _render_recommendation_detail_tables(st, recommendation_result)
    if st.button("进入图表概览", type="primary", key="recommendation_go_chart_overview"):
        _go_to_workflow_page(st, "图表概览")
    _render_recommendation_bottom_status(st, batch_result, summary, recommendation_result)


def _render_chart_overview_page(st, batch_result, summary: pd.DataFrame) -> None:
    _render_page_heading(
        st,
        "图表概览",
        "先自由组合推荐方案和指定方案，再横向对比核心指标与容量配置；下载报告集中在最后一页。",
    )

    economy_result, recommendation_result, error_message = _build_recommendation_result_for_display(st, summary)
    if error_message:
        _render_missing_step(st, "经济性测算", error_message)
        return

    chart_summary = _merge_landed_price_context(summary, economy_result.get("summary") if economy_result else None)
    comparison = _render_chart_scenario_picker(st, chart_summary, recommendation_result)
    _render_recommendation_dashboard_overview(
        st,
        batch_result,
        chart_summary,
        recommendation_result,
        comparison=comparison,
        policy_thresholds=_policy_thresholds_from_state(st),
    )
    selected_ids = comparison["scenario_id"].astype(str).tolist() if comparison is not None and not comparison.empty else []
    valid_ids = _valid_scenario_ids(chart_summary)
    if valid_ids:
        label_lookup = _scenario_label_lookup(chart_summary)
        default_detail_id = selected_ids[0] if selected_ids else valid_ids[0]
        detail_key = "chart_overview_active_detail_scenario"
        pending_detail_key = "_chart_overview_pending_detail_scenario"
        pending_detail_id = st.session_state.pop(pending_detail_key, None)
        if pending_detail_id is not None and str(pending_detail_id) in set(valid_ids):
            st.session_state[detail_key] = str(pending_detail_id)
        if str(st.session_state.get(detail_key, default_detail_id)) not in set(valid_ids):
            st.session_state[detail_key] = default_detail_id
        default_index = valid_ids.index(str(st.session_state.get(detail_key, default_detail_id)))
        _render_section_intro(
            st,
            "Detail Review",
            "详细图表复核",
            "默认查看推荐组合中的方案；也可从全部已计算方案中切换，下面图表均读取所选方案逐小时台账。",
        )
        active_detail_id = st.selectbox(
            "详细图表方案（全部已计算方案）",
            options=valid_ids,
            index=default_index,
            format_func=lambda scenario_id: label_lookup.get(str(scenario_id), str(scenario_id)),
            key="chart_overview_active_detail_scenario",
            help="可选择任一已计算方案；不要求先加入上方对比组合。",
        )
        detail_ids = list(dict.fromkeys([*selected_ids, str(active_detail_id)]))
        _render_scenario_quick_select_buttons(
            st,
            chart_summary,
            detail_ids,
            active_id=str(active_detail_id),
            state_key=detail_key,
            key_prefix="chart_overview_detail_scenario_button",
            pending_state_key=pending_detail_key,
        )
        render_chart_analysis(
            st,
            batch_result,
            chart_summary,
            economy_result=economy_result,
            recommendation_portfolio=recommendation_result.portfolio if recommendation_result else None,
            selected_scenario_ids=detail_ids,
            active_scenario_id=str(active_detail_id),
            show_overview=False,
            show_selector=False,
            show_hero=False,
        )
    else:
        st.info("当前没有可用于详细图表复核的方案。")
    _render_recommendation_bottom_status(st, batch_result, chart_summary, recommendation_result)


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
            "- 若要复核某张图，请用本页导出的逐小时 CSV 按图表 meta 中记录的选中日期过滤。",
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
    chart_items, warnings, comparison_summary = _build_chart_export_items(
        summary,
        selected_scenario_id,
        hourly,
        comparison_summary=comparison_summary,
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
                "- 四季典型日图表使用季节中心日法；文件名不嵌入日期，选中日期记录在 meta 中。\n"
                "- 24H 典型日、关键运行日和全年曲线与网页端运行时序图使用同一套显示口径。\n"
                "- HTML 用于交互复核；如需插入 Word，请使用同页的 PNG 图片包。\n"
            ).encode("utf-8-sig"),
        )
    return output.getvalue()


def _build_chart_export_items(
    summary: pd.DataFrame,
    selected_scenario_id: str,
    hourly: pd.DataFrame,
    comparison_summary: pd.DataFrame | None = None,
):
    selected_summary = _row_for_scenario(summary, selected_scenario_id)
    comparison_summary = comparison_summary if comparison_summary is not None and not comparison_summary.empty else summary
    chart_items = []
    warnings: list[str] = []
    season_export_keys = {"春季": "spring", "夏季": "summer", "秋季": "autumn", "冬季": "winter"}
    key_day_export_keys = {
        "最大负荷日": "max_load",
        "最大弃电日": "max_curtail",
        "最大下网日": "max_grid_import",
        "SOC 最低日": "soc_low",
        "SOC 最高日": "soc_high",
    }

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
        result = build_daily_balance_chart(
            hourly,
            selected_date=selected_date.iloc[0],
            title=f"24H 典型日运行策略 · {season}",
            chart_name=f"{season}典型日运行策略图",
        )
        result.chart_id = f"S03_{season_key}"
        result.chart_name = f"{season}典型日运行策略图"
        result.meta["typical_day_label"] = selection.label
        result.meta["typical_day_season"] = season
        result.meta["typical_day_method"] = selection.method
        chart_items.append((f"typical_{season_key}", result))

    adapted_hourly = adapt_hourly(hourly).data
    for mode, key in key_day_export_keys.items():
        day, label = select_operating_day(adapted_hourly, mode=mode)
        if day.empty or "timestamp" not in day.columns:
            warnings.append(f"{mode}未生成：缺少可用逐小时日期。")
            continue
        selected_date = pd.to_datetime(day["timestamp"], errors="coerce").dropna().dt.date
        if selected_date.empty:
            warnings.append(f"{mode}未生成：无法解析选中日期。")
            continue
        result = build_daily_balance_chart(
            hourly,
            selected_date=selected_date.iloc[0],
            title=f"24H 关键运行日 · {mode}",
            chart_name=f"关键运行日运行策略图（{mode}）",
        )
        result.chart_id = f"S03_key_{key}"
        result.chart_name = f"关键运行日运行策略图（{mode}）"
        result.meta["key_day_label"] = label
        result.meta["key_day_mode"] = mode
        result.meta["key_day_method"] = "按逐小时台账对应指标排序选取真实 24 小时日期。"
        chart_items.append((f"key_day_{key}", result))

    chart_items.extend(
        [
            ("full_year_operation", build_full_year_operation_chart(hourly)),
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

    return chart_items, warnings, comparison_summary


def _build_chart_png_docx_zip(
    summary: pd.DataFrame,
    selected_scenario_id: str,
    hourly: pd.DataFrame,
    comparison_summary: pd.DataFrame | None = None,
    progress_callback=None,
) -> tuple[bytes, list[str]]:
    output = BytesIO()
    profile = DOCX_A4_PORTRAIT_PROFILE
    chart_items, warnings, comparison_summary = _build_chart_export_items(
        summary,
        selected_scenario_id,
        hourly,
        comparison_summary=comparison_summary,
    )
    manifest_columns = [
        "file_name",
        "chart_id",
        "chart_name",
        "width_px",
        "height_px",
        "suggested_insert_width_cm",
        "note",
    ]
    manifest_rows = []
    render_plan = []
    for base_name, result in chart_items:
        if result.figure is None:
            warnings.extend(result.warnings)
            continue
        prefix = _safe_export_name(f"{base_name}_{result.chart_id}")
        render_plan.append(
            {
                "result": result,
                "prefix": prefix,
                "file_name": f"{prefix}.png",
                "height_px": profile.height_for(result),
            }
        )
    exportable_total = len(render_plan)
    completed = 0
    if progress_callback:
        progress_callback(0, exportable_total, "启动批量 PNG 渲染环境")

    batch_png_bytes: list[bytes | None] = [None] * exportable_total
    if render_plan:
        try:
            batch_png_bytes = charts_to_png_bytes_batch(
                [item["result"] for item in render_plan],
                profile=profile,
            )
        except Exception as exc:  # noqa: BLE001 - keep a per-chart fallback for local browser variance
            warnings.append(f"批量 PNG 渲染失败，已自动改为逐张渲染：{exc}")
            batch_png_bytes = [None] * exportable_total

    with ZipFile(output, mode="w", compression=ZIP_DEFLATED) as archive:
        exported = 0
        for index, item in enumerate(render_plan):
            result = item["result"]
            prefix = item["prefix"]
            file_name = item["file_name"]
            height_px = item["height_px"]
            try:
                png_bytes = batch_png_bytes[index]
                if png_bytes is None:
                    png_bytes = chart_to_png_bytes(result, profile=profile)
                archive.writestr(file_name, png_bytes)
            except Exception as exc:  # noqa: BLE001 - static image dependencies vary by machine
                warnings.append(f"{result.chart_name} PNG 导出失败：{exc}")
                completed += 1
                if progress_callback:
                    progress_callback(completed, exportable_total, result.chart_name)
                continue
            archive.writestr(f"{prefix}_meta.md", chart_to_meta_markdown(result).encode("utf-8-sig"))
            manifest_rows.append(
                {
                    "file_name": file_name,
                    "chart_id": result.chart_id,
                    "chart_name": result.chart_name,
                    "width_px": profile.width_px,
                    "height_px": height_px,
                    "suggested_insert_width_cm": profile.insert_width_cm,
                    "note": result.note,
                }
            )
            exported += 1
            completed += 1
            if progress_callback:
                progress_callback(completed, exportable_total, result.chart_name)

        manifest = pd.DataFrame(manifest_rows, columns=manifest_columns)
        archive.writestr("chart_manifest.csv", manifest.to_csv(index=False).encode("utf-8-sig"))
        if warnings:
            archive.writestr("warnings.txt", "\n".join(warnings).encode("utf-8-sig"))
        archive.writestr(
            "README.md",
            (
                "# Word 友好 PNG 图表包说明\n\n"
                f"- 方案编号：`{selected_scenario_id}`\n"
                f"- 多方案对比范围：{len(comparison_summary)} 个方案（推荐组合 + 当前报告方案）。\n"
                f"- 图片版式：{profile.name}，建议在 Word 中按 {profile.insert_width_cm:g} cm 宽度插入。\n"
                f"- PNG 画布宽度：{profile.width_px}px；典型日图 1300px 高，全年/热力图 1000px 高，月度/多方案图 900px 高。\n"
                f"- 已导出 PNG 数量：{exported}\n"
                "- PNG 图表只读消费方案汇总和逐小时明细，不重新计算调度。\n"
                "- 24H 典型日、关键运行日和全年曲线与网页端运行时序图使用同一套颜色和显示口径。\n"
                "- 季节典型日文件名不嵌入日期；真实选中日期写入每张图的 meta。\n"
                "- HTML 包继续用于交互复核；本包用于复制或插入 docx 报告。\n"
                "- 若缺少 `kaleido` 或可用 Chrome/Chromium，PNG 可能生成失败，失败原因写入 warnings.txt。\n"
            ).encode("utf-8-sig"),
        )
    return output.getvalue(), warnings


def _dataframe_content_signature(frame: pd.DataFrame | None) -> str:
    if frame is None:
        return "none"
    digest = hashlib.sha1()
    digest.update(f"{len(frame)}|{len(frame.columns)}".encode("utf-8"))
    digest.update("\x1f".join(str(column) for column in frame.columns).encode("utf-8", errors="replace"))
    if frame.empty:
        return digest.hexdigest()[:16]
    try:
        row_hash = pd.util.hash_pandas_object(frame, index=True).to_numpy(dtype="uint64", copy=False)
        digest.update(row_hash.tobytes())
    except Exception:  # noqa: BLE001 - fall back to stable CSV text for unusual extension dtypes
        digest.update(frame.to_csv(index=True).encode("utf-8", errors="replace"))
    return digest.hexdigest()[:16]


def _chart_png_docx_export_signature(
    selected_scenario_id: str,
    summary: pd.DataFrame,
    hourly: pd.DataFrame,
    comparison_summary: pd.DataFrame,
) -> str:
    comparison_ids = []
    if "scenario_id" in comparison_summary.columns:
        comparison_ids = comparison_summary["scenario_id"].astype(str).tolist()
    time_range = ""
    if "timestamp" in hourly.columns and not hourly.empty:
        timestamps = pd.to_datetime(hourly["timestamp"], errors="coerce").dropna()
        if not timestamps.empty:
            time_range = f"{timestamps.min().isoformat()}|{timestamps.max().isoformat()}"
    payload = "|".join(
        [
            str(selected_scenario_id),
            ",".join(comparison_ids),
            str(len(hourly)),
            str(len(comparison_summary)),
            time_range,
            _dataframe_content_signature(summary),
            _dataframe_content_signature(hourly),
            _dataframe_content_signature(comparison_summary),
            str(DOCX_A4_PORTRAIT_PROFILE.width_px),
            str(DOCX_A4_PORTRAIT_PROFILE.default_height_px),
            "chart_export_wysiwyg_v4",
        ]
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def _chart_png_docx_job_key(signature: str, *, session_id: str | None = None) -> str:
    return f"chart_png_docx:{session_id or 'global'}:{signature}"


def _submit_chart_png_docx_job(
    signature: str,
    summary: pd.DataFrame,
    selected_scenario_id: str,
    hourly: pd.DataFrame,
    comparison_summary: pd.DataFrame,
    *,
    session_id: str | None = None,
) -> dict[str, object]:
    job_key = _chart_png_docx_job_key(signature, session_id=session_id)
    existing = _CHART_PNG_DOCX_JOBS.get(job_key)
    if existing:
        future = existing.get("future")
        if isinstance(future, Future) and not future.done():
            return existing
        if isinstance(future, Future) and future.done():
            return existing
    progress = {"completed": 0, "total": 0, "message": "准备 PNG 渲染"}

    def progress_callback(completed: int, total: int, message: str) -> None:
        progress["completed"] = int(completed)
        progress["total"] = int(total)
        progress["message"] = str(message)

    future = _CHART_PNG_DOCX_EXECUTOR.submit(
        _build_chart_png_docx_zip,
        summary.copy(deep=True),
        selected_scenario_id,
        hourly.copy(deep=True),
        comparison_summary.copy(deep=True),
        progress_callback,
    )
    job = {
        "future": future,
        "signature": signature,
        "selected_scenario_id": selected_scenario_id,
        "file_name": f"chart_png_docx_{selected_scenario_id}.zip",
        "started_at": time.time(),
        "progress": progress,
    }
    _CHART_PNG_DOCX_JOBS[job_key] = job
    return job


def _poll_chart_png_docx_job(st, signature: str) -> dict[str, object] | None:
    session_id = st.session_state.get(CHART_PNG_DOCX_SESSION_ID_KEY)
    job_key = _chart_png_docx_job_key(signature, session_id=str(session_id) if session_id else None)
    job = _CHART_PNG_DOCX_JOBS.get(job_key)
    if not job:
        return None
    future = job.get("future")
    if not isinstance(future, Future):
        _CHART_PNG_DOCX_JOBS.pop(job_key, None)
        return None
    started_at = float(job.get("started_at", time.time()))
    if not future.done():
        return {"status": "running", "elapsed_s": time.time() - started_at, **job}
    try:
        chart_png_zip, png_warnings = future.result()
    except Exception as exc:  # noqa: BLE001 - background export errors should become user-visible
        _CHART_PNG_DOCX_JOBS.pop(job_key, None)
        st.session_state["chart_png_docx_export_error"] = str(exc)
        return {"status": "failed", "elapsed_s": time.time() - started_at, "error": str(exc)}
    _CHART_PNG_DOCX_JOBS.pop(job_key, None)
    st.session_state["chart_png_docx_export"] = {
        "signature": signature,
        "data": chart_png_zip,
        "warnings": png_warnings,
        "file_name": str(job.get("file_name") or f"chart_png_docx_{job.get('selected_scenario_id', 'selected')}.zip"),
        "duration_s": time.time() - started_at,
    }
    st.session_state.pop("chart_png_docx_export_error", None)
    _save_runtime_snapshot(st)
    return {"status": "complete", "elapsed_s": time.time() - started_at, **job}


def _render_chart_png_docx_export_panel(
    st,
    summary: pd.DataFrame,
    selected_id: str,
    hourly: pd.DataFrame,
    comparison_summary: pd.DataFrame,
) -> None:
    png_session_id = _chart_png_docx_session_id(st)
    png_signature = _chart_png_docx_export_signature(selected_id, summary, hourly, comparison_summary)

    def render_status() -> None:
        job_status = _poll_chart_png_docx_job(st, png_signature)
        png_cached = st.session_state.get("chart_png_docx_export")
        png_ready = bool(png_cached and png_cached.get("signature") == png_signature)
        png_running = bool(job_status and job_status.get("status") == "running")
        active_signature = st.session_state.get("chart_png_docx_active_signature")

        if png_cached and not png_ready:
            st.caption("导出方案或对比范围已变化，需要重新生成 PNG ZIP。")
        if job_status and job_status.get("status") == "complete":
            st.session_state.pop("chart_png_docx_active_signature", None)
            st.success(f"PNG ZIP 已生成，用时 {float(job_status.get('elapsed_s', 0)):.0f} 秒。")
            png_cached = st.session_state.get("chart_png_docx_export")
            png_ready = bool(png_cached and png_cached.get("signature") == png_signature)
        if job_status and job_status.get("status") == "failed":
            st.session_state.pop("chart_png_docx_active_signature", None)
            st.error(f"PNG ZIP 生成失败：{job_status.get('error')}")
        elif st.session_state.get("chart_png_docx_export_error") and not png_running:
            st.error(f"PNG ZIP 生成失败：{st.session_state['chart_png_docx_export_error']}")

        button_label = "重新生成 PNG ZIP" if png_ready else "生成 Word 友好 PNG ZIP"
        start_clicked = st.button(
            button_label,
            key="export_generate_chart_png_docx",
            width="stretch",
            type="primary" if not png_ready else "secondary",
            disabled=png_running,
        )
        if start_clicked:
            st.session_state.pop("chart_png_docx_export_error", None)
            job_status = {
                "status": "running",
                **_submit_chart_png_docx_job(
                    png_signature,
                    summary,
                    selected_id,
                    hourly,
                    comparison_summary,
                    session_id=png_session_id,
                ),
            }
            st.session_state["chart_png_docx_active_signature"] = png_signature
            png_running = True
            png_ready = False
            active_signature = png_signature

        if png_running:
            elapsed = float(job_status.get("elapsed_s", 0))
            progress = job_status.get("progress") if isinstance(job_status, dict) else None
            progress = progress if isinstance(progress, dict) else {}
            completed = int(progress.get("completed") or 0)
            total = int(progress.get("total") or 0)
            message = str(progress.get("message") or "正在渲染 PNG 图片")
            if total > 0:
                ratio = min(1.0, max(0.0, completed / total))
                st.progress(ratio, text=f"{message} · {completed}/{total} · {elapsed:.0f} 秒")
            else:
                st.progress(0.05, text=f"{message} · {elapsed:.0f} 秒")
            st.caption("可以切换到其他页面继续操作；回到本页会继续显示状态和下载入口。")
        elif active_signature == png_signature and not png_ready and not job_status:
            st.warning("未找到正在运行的 PNG 任务，可能是服务刚刚重启；请重新生成。")
            st.session_state.pop("chart_png_docx_active_signature", None)

        if png_ready and png_cached:
            png_warnings = png_cached.get("warnings", [])
            if png_warnings:
                st.warning("部分 PNG 未能导出；可先下载 HTML ZIP 复核，或检查 Kaleido 与 Chrome/Chromium 环境。")
            st.download_button(
                "下载 Word 友好 PNG ZIP",
                data=png_cached["data"],
                file_name=png_cached["file_name"],
                mime="application/zip",
                key="export_selected_chart_png_docx_zip",
                help="包含适合 A4 纵向 Word 正文插图的 PNG、每图 meta、chart_manifest.csv 和 README。",
                on_click="ignore",
            )

    fragment = getattr(st, "fragment", None)
    if callable(fragment):
        fragment(run_every="2s")(render_status)()
    else:
        render_status()


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
                  <span>交互式 HTML 用于网页复核；PNG 图片包按 A4 Word 正文比例生成，便于插入 docx。</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
            comparison_summary = _comparison_summary_from_portfolio(
                summary,
                selected_id,
                recommendation_result_for_export.portfolio if recommendation_result_for_export else None,
            )
            _render_chart_png_docx_export_panel(st, summary, selected_id, hourly, comparison_summary)
            if st.checkbox("准备所选方案图表 HTML ZIP", value=False, key="export_prepare_chart_html"):
                with st.spinner("正在生成图表 HTML ZIP..."):
                    chart_zip = _build_chart_html_zip(summary, selected_id, hourly, comparison_summary=comparison_summary)
                st.download_button(
                    "下载所选方案图表 HTML ZIP",
                    data=chart_zip,
                    file_name=f"chart_html_{selected_id}.zip",
                    mime="application/zip",
                    key="export_selected_chart_html_zip",
                    help="包含四季典型日、关键运行日、全年曲线、SOC、电网交换、月度流向、热力图和多方案对比图；每张图附带 meta 说明。",
                )
            st.markdown(
                '<div class="gd-export-note">PNG 静态图导出依赖 kaleido 和可用 Chrome/Chromium；HTML ZIP 不依赖该静态图环境。</div>',
                unsafe_allow_html=True,
            )

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
    parallel_workers = 1
    large_run_hourly_detail_limit = DEFAULT_LARGE_RUN_HOURLY_DETAIL_LIMIT
    grid_exchange_power_limit = None
    duration_text = str(_stored_widget_value(st, "simulation_bess_duration_text", "2,4"))
    exact_pv_capacity = None
    exact_wind_capacity = None
    exact_bess_power = None
    exact_bess_energy = None

    data_col, scenario_col, policy_col = st.columns([0.9, 1.22, 1.0])

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
                "批量上传项目曲线文件",
                type=["csv", "xlsx", "xlsm"],
                accept_multiple_files=True,
                help=(
                    "一次选择负荷、光伏、风电 CSV，并可同时加入下网电价曲线 CSV/XLSX；"
                    "技术曲线文件名包含 load、pv/solar、wind 或中文关键词时自动识别，"
                    "电价曲线文件名建议包含“电价/价格/下网/price”。"
                ),
                key="simulation_batch_curve_csv",
            )
            assigned_files, batch_price_curve_file, assign_messages = _auto_assign_curve_files(batch_files)
            for message in assign_messages:
                st.warning(message)
            if batch_price_curve_file is not None:
                _remember_uploaded_price_curve(st, batch_price_curve_file, context_label="批量导入中的电价曲线")

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
                    st, "负荷时间列", load_df, load_time_guess, show_guess_caption=False, key="simulation_load_time_col"
                )
                load_value_col = _column_selector(
                    st, "负荷数值列", load_df, load_value_guess, show_guess_caption=False, key="simulation_load_value_col"
                )
                pv_time_col = _column_selector(
                    st, "光伏时间列", pv_df, pv_time_guess, show_guess_caption=False, key="simulation_pv_time_col"
                )
                pv_value_col = _column_selector(
                    st, "光伏数值列", pv_df, pv_value_guess, show_guess_caption=False, key="simulation_pv_value_col"
                )
                wind_time_col = _column_selector(
                    st, "风电时间列", wind_df, wind_time_guess, show_guess_caption=False, key="simulation_wind_time_col"
                )
                wind_value_col = _column_selector(
                    st, "风电数值列", wind_df, wind_value_guess, show_guess_caption=False, key="simulation_wind_value_col"
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
                st.dataframe(pd.DataFrame(review_rows), width="stretch", hide_index=True)

            curve_metrics = {
                "负荷": _curve_metric_snapshot("负荷", load_df, load_time_col, load_value_col),
                "光伏": _curve_metric_snapshot("光伏", pv_df, pv_time_col, pv_value_col),
                "风电": _curve_metric_snapshot("风电", wind_df, wind_time_col, wind_value_col),
            }
            _remember_curve_metrics(st, curve_metrics)
            with st.expander("曲线识别摘要", expanded=False):
                _render_curve_overview_cards(
                    st,
                    {"负荷": load_file, "光伏": pv_file, "风电": wind_file},
                    {
                        "负荷": (load_time_col, load_value_col),
                        "光伏": (pv_time_col, pv_value_col),
                        "风电": (wind_time_col, wind_value_col),
                    },
                    {
                        "负荷": _curve_metric_tooltip(curve_metrics["负荷"]),
                        "光伏": _curve_metric_tooltip(curve_metrics["光伏"]),
                        "风电": _curve_metric_tooltip(curve_metrics["风电"]),
                    },
                )
            notice = st.session_state.pop(PROJECT_PRICE_CURVE_NOTICE_KEY, None)
            if notice:
                st.success(notice)
            price_curve_upload = None
            with st.expander("可选：下网电价曲线", expanded=False):
                price_curve_upload = st.file_uploader(
                    "上传下网电价曲线（CSV / XLSX）",
                    type=["csv", "xlsx", "xlsm"],
                    key="simulation_price_curve_upload",
                    help="可选经济性输入，只影响经济性测算和推荐排序，不改变技术仿真。未上传时使用固定价/网页组价模式。",
                )
                if price_curve_upload is not None:
                    _remember_uploaded_price_curve(st, price_curve_upload)
                if _project_price_curve_data(st) is not None:
                    _render_project_price_curve_status(st)

    with scenario_col:
        with st.container(border=True):
            _render_section_intro(
                st,
                "Scenario Pool",
                "候选方案池",
                "支持容量范围遍历，也支持单方案配置；两种方式都走同一条技术仿真链路。",
            )
            scenario_mode_options = ["容量范围遍历", "指定单方案"]
            stored_scenario_mode = str(_stored_widget_value(st, "simulation_scenario_pool_mode", scenario_mode_options[0]))
            if stored_scenario_mode not in scenario_mode_options:
                stored_scenario_mode = scenario_mode_options[0]
            scenario_mode = st.radio(
                "方案生成方式",
                scenario_mode_options,
                index=scenario_mode_options.index(stored_scenario_mode),
                horizontal=True,
                key="simulation_scenario_pool_mode",
                on_change=_sync_stored_widget_value,
                args=(st, "simulation_scenario_pool_mode"),
            )
            _store_widget_value(st, "simulation_scenario_pool_mode", scenario_mode)

            with st.expander("高级：枚举性能提醒", expanded=False):
                perf_cols = st.columns(3)
                warn_threshold = int(
                    perf_cols[0].number_input(
                        "方案数提醒阈值",
                        value=int(_stored_widget_value(st, "simulation_warn_threshold", 5000)),
                        min_value=1,
                        step=100,
                        key="simulation_warn_threshold",
                        on_change=_sync_stored_widget_value,
                        args=(st, "simulation_warn_threshold"),
                    )
                )
                parallel_workers = int(
                    perf_cols[1].number_input(
                        "并行计算进程数",
                        value=int(_stored_widget_value(st, "simulation_parallel_workers", 1)),
                        min_value=1,
                        max_value=8,
                        step=1,
                        help="默认 1 为串行。设置为 2-8 时会并行执行单方案技术仿真；小方案可能因多进程启动开销不一定更快。",
                        key="simulation_parallel_workers",
                        on_change=_sync_stored_widget_value,
                        args=(st, "simulation_parallel_workers"),
                    )
                )
                large_run_hourly_detail_limit = int(
                    perf_cols[2].number_input(
                        "大批量保留明细数",
                        value=int(
                            _stored_widget_value(
                                st,
                                "simulation_large_run_hourly_detail_limit",
                                DEFAULT_LARGE_RUN_HOURLY_DETAIL_LIMIT,
                            )
                        ),
                        min_value=0,
                        max_value=500,
                        step=5,
                        help="方案数超过提醒阈值时，只常驻保存前 N 个方案的逐小时明细，其余方案先只保留汇总。",
                        key="simulation_large_run_hourly_detail_limit",
                        on_change=_sync_stored_widget_value,
                        args=(st, "simulation_large_run_hourly_detail_limit"),
                    )
                )
                st.caption(
                    "指定单方案可绕开大规模遍历；范围遍历较慢时，优先缩小步长/范围。"
                    "进程数大于 1 时只并行技术仿真，不改变调度口径。"
                    "大批量明细保留只影响结果常驻内存，不改变计算本身。"
                )

            if scenario_mode == "指定单方案":
                exact_row_1 = st.columns(2, gap="small")
                exact_pv_capacity = exact_row_1[0].number_input(
                    "光伏容量（万kW）",
                    value=float(_stored_widget_value(st, "simulation_exact_pv_capacity", 5.0)),
                    min_value=0.0,
                    step=1.0,
                    key="simulation_exact_pv_capacity",
                    on_change=_sync_stored_widget_value,
                    args=(st, "simulation_exact_pv_capacity"),
                )
                exact_wind_capacity = exact_row_1[1].number_input(
                    "风电容量（万kW）",
                    value=float(_stored_widget_value(st, "simulation_exact_wind_capacity", 5.0)),
                    min_value=0.0,
                    step=1.0,
                    key="simulation_exact_wind_capacity",
                    on_change=_sync_stored_widget_value,
                    args=(st, "simulation_exact_wind_capacity"),
                )

                exact_row_2 = st.columns(2, gap="small")
                exact_bess_power = exact_row_2[0].number_input(
                    "储能功率（万kW）",
                    value=float(_stored_widget_value(st, "simulation_exact_bess_power", 0.0)),
                    min_value=0.0,
                    step=1.0,
                    key="simulation_exact_bess_power",
                    on_change=_sync_stored_widget_value,
                    args=(st, "simulation_exact_bess_power"),
                )
                exact_bess_energy = exact_row_2[1].number_input(
                    "储能容量（万kWh）",
                    value=float(_stored_widget_value(st, "simulation_exact_bess_energy", 0.0)),
                    min_value=0.0,
                    step=1.0,
                    key="simulation_exact_bess_energy",
                    on_change=_sync_stored_widget_value,
                    args=(st, "simulation_exact_bess_energy"),
                )
                scenario_grid, scenario_errors = _single_scenario_grid_from_exact(
                    pv_capacity=exact_pv_capacity,
                    wind_capacity=exact_wind_capacity,
                    bess_power=exact_bess_power,
                    bess_energy=exact_bess_energy,
                )
                for error in scenario_errors:
                    st.error(error)
                if scenario_grid is not None:
                    try:
                        scenario_count = estimate_scenario_count(scenario_grid)
                        duration_display = f"{_compact_number(scenario_grid['bess_duration_hours'][0])} 小时"
                        _render_simulation_kpis(st, scenario_count, scenario_grid, duration_display)
                    except Exception as exc:  # noqa: BLE001 - UI should show friendly text
                        st.error(f"指定方案设置有误：{exc}")
                        scenario_grid = None
            else:
                pv_range = _range_inputs(st, "光伏容量", (0, 30, 5), key_prefix="simulation_pv_capacity")
                wind_range = _range_inputs(st, "风电容量", (0, 30, 5), key_prefix="simulation_wind_capacity")
                bess_power_range = _range_inputs(st, "储能功率", (0, 10, 2), key_prefix="simulation_bess_power")
                include_no_bess = _boolean_input(
                    st,
                    "包含无储能方案",
                    value=True,
                    help="保留无储能基准方案，便于比较储能增益。",
                    key="simulation_include_no_bess",
                )
                duration_text = st.text_input(
                    "储能时长选项（小时）",
                    value=duration_text,
                    help="多个时长用英文逗号分隔；勾选无储能时会自动加入 0 小时。",
                    key="simulation_bess_duration_text",
                    on_change=_sync_stored_widget_value,
                    args=(st, "simulation_bess_duration_text"),
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
                value=float(_stored_widget_value(st, "simulation_self_use_rate_min", 0.60)),
                min_value=0.0,
                max_value=1.0,
                step=0.01,
                help="方案筛选指标，内部按小数保存。",
                key="simulation_self_use_rate_min",
                on_change=_sync_stored_widget_value,
                args=(st, "simulation_self_use_rate_min"),
            )
            green_load_rate_min = st.number_input(
                "绿电占用电比例下限",
                value=float(_stored_widget_value(st, "simulation_green_load_rate_min", 0.30)),
                min_value=0.0,
                max_value=1.0,
                step=0.01,
                help="方案筛选指标，内部按小数保存。",
                key="simulation_green_load_rate_min",
                on_change=_sync_stored_widget_value,
                args=(st, "simulation_green_load_rate_min"),
            )
            export_rate_max = st.number_input(
                "上网比例上限",
                value=float(_stored_widget_value(st, "simulation_export_rate_max", 0.20)),
                min_value=0.0,
                max_value=1.0,
                step=0.01,
                help="方案筛选指标，内部按小数保存。",
                key="simulation_export_rate_max",
                on_change=_sync_stored_widget_value,
                args=(st, "simulation_export_rate_max"),
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
                        value=float(_stored_widget_value(st, "simulation_grid_exchange_power_limit", 10.0)),
                        min_value=0.0,
                        step=1.0,
                        key="simulation_grid_exchange_power_limit",
                        on_change=_sync_stored_widget_value,
                        args=(st, "simulation_grid_exchange_power_limit"),
                    )

    with st.expander("专业参数：储能 SOC、效率与寿命", expanded=False):
        soc_cols = st.columns(4)
        soc_initial = soc_cols[0].number_input(
            "初始 SOC",
            value=float(_stored_widget_value(st, "simulation_soc_initial", 0.5)),
            min_value=0.0,
            max_value=1.0,
            step=0.05,
            key="simulation_soc_initial",
            on_change=_sync_stored_widget_value,
            args=(st, "simulation_soc_initial"),
        )
        soc_min = soc_cols[1].number_input(
            "最小 SOC",
            value=float(_stored_widget_value(st, "simulation_soc_min", 0.1)),
            min_value=0.0,
            max_value=1.0,
            step=0.05,
            key="simulation_soc_min",
            on_change=_sync_stored_widget_value,
            args=(st, "simulation_soc_min"),
        )
        soc_max = soc_cols[2].number_input(
            "最大 SOC",
            value=float(_stored_widget_value(st, "simulation_soc_max", 0.9)),
            min_value=0.0,
            max_value=1.0,
            step=0.05,
            key="simulation_soc_max",
            on_change=_sync_stored_widget_value,
            args=(st, "simulation_soc_max"),
        )
        bess_calendar_life = soc_cols[3].number_input(
            "电池日历寿命（年）",
            value=float(_stored_widget_value(st, "simulation_bess_calendar_life", 15.0)),
            min_value=1.0,
            max_value=40.0,
            step=1.0,
            help="当前不参与小时调度，只在经济性测算中与循环寿命共同决定储能更换年份。",
            key="simulation_bess_calendar_life",
            on_change=_sync_stored_widget_value,
            args=(st, "simulation_bess_calendar_life"),
        )
        eff_cols = st.columns(3)
        eta_charge = eff_cols[0].number_input(
            "充电效率",
            value=float(_stored_widget_value(st, "simulation_eta_charge", 0.95)),
            min_value=0.000001,
            max_value=1.0,
            step=0.01,
            key="simulation_eta_charge",
            on_change=_sync_stored_widget_value,
            args=(st, "simulation_eta_charge"),
        )
        eta_discharge = eff_cols[1].number_input(
            "放电效率",
            value=float(_stored_widget_value(st, "simulation_eta_discharge", 0.95)),
            min_value=0.000001,
            max_value=1.0,
            step=0.01,
            key="simulation_eta_discharge",
            on_change=_sync_stored_widget_value,
            args=(st, "simulation_eta_discharge"),
        )
        cycle_life = eff_cols[2].number_input(
            "循环寿命",
            value=float(_stored_widget_value(st, "simulation_cycle_life", 6000.0)),
            min_value=0.0,
            step=100.0,
            key="simulation_cycle_life",
            on_change=_sync_stored_widget_value,
            args=(st, "simulation_cycle_life"),
        )

    for key, value in [
        ("simulation_bess_duration_text", duration_text),
        ("simulation_scenario_pool_mode", scenario_mode),
        ("simulation_exact_pv_capacity", exact_pv_capacity),
        ("simulation_exact_wind_capacity", exact_wind_capacity),
        ("simulation_exact_bess_power", exact_bess_power),
        ("simulation_exact_bess_energy", exact_bess_energy),
        ("simulation_warn_threshold", warn_threshold),
        ("simulation_parallel_workers", parallel_workers),
        ("simulation_large_run_hourly_detail_limit", large_run_hourly_detail_limit),
        ("simulation_self_use_rate_min", self_use_rate_min),
        ("simulation_green_load_rate_min", green_load_rate_min),
        ("simulation_export_rate_max", export_rate_max),
        ("simulation_grid_exchange_power_limit", grid_exchange_power_limit),
        ("simulation_soc_initial", soc_initial),
        ("simulation_soc_min", soc_min),
        ("simulation_soc_max", soc_max),
        ("simulation_bess_calendar_life", bess_calendar_life),
        ("simulation_eta_charge", eta_charge),
        ("simulation_eta_discharge", eta_discharge),
        ("simulation_cycle_life", cycle_life),
    ]:
        if value is not None:
            _store_widget_value(st, key, value)

    detail_retention_plan = _technical_detail_retention_plan(
        scenario_count,
        threshold=int(warn_threshold),
        large_run_hourly_detail_limit=int(large_run_hourly_detail_limit),
    )
    if scenario_count is not None and scenario_grid is not None and detail_retention_plan["mode"] == "summary_first":
        st.warning(
            f"本次配置将生成 {scenario_count:,} 个方案，可能计算较慢。{detail_retention_plan['message']}"
        )

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
            demo_detail_retention_plan = _technical_detail_retention_plan(
                estimate_scenario_count(demo_grid),
                threshold=int(warn_threshold),
                large_run_hourly_detail_limit=int(large_run_hourly_detail_limit),
            )
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
                        performance_params=PerformanceParams(
                            warn_if_scenarios_exceed=int(warn_threshold),
                            parallel_workers=int(parallel_workers),
                        ),
                        cleaning_params=DataCleaningParams(),
                        retain_hourly_details=bool(demo_detail_retention_plan["retain_hourly_details"]),
                        hourly_detail_scenario_ids=tuple(demo_detail_retention_plan["hourly_detail_scenario_ids"]),
                        config_metadata={
                            "bess_calendar_life_years": 15.0,
                            "demo": True,
                            "ui_detail_retention_mode": demo_detail_retention_plan["mode"],
                            "ui_detail_retention_message": demo_detail_retention_plan["message"],
                        },
                    ),
                )
            persisted_result = _persist_pilot_technical_result_if_enabled(st, technical_result)
            study_result = StudyResult.from_technical(technical_result)
            if persisted_result is not None:
                study_result = _study_result_with_pilot_refs(study_result, persisted_result)
            st.session_state["study_result"] = study_result
            st.session_state["batch_result"] = technical_result.batch_result
            st.session_state["config_snapshot"] = technical_result.config_snapshot
            _clear_project_price_curve(st)
            _clear_chart_export_cache(st)
            price_curve_reset_notice = _clear_project_price_curve_for_partial_hourly_retention(
                st,
                demo_detail_retention_plan,
            ) or _discard_incompatible_project_price_curve(st, technical_result.batch_result.hourly_details)
            _clear_economy_outputs(st)
            st.session_state["_simulation_force_sample_data"] = True
            demo_retention_notice = (
                "" if demo_detail_retention_plan["mode"] == "full" else demo_detail_retention_plan["message"]
            )
            store_notice = st.session_state.pop(PILOT_RESULT_STORE_NOTICE_KEY, "")
            st.session_state["_simulation_notice"] = (
                f"Demo 结果已生成，可继续做经济测算、方案推荐和图表概览。{demo_retention_notice}{store_notice}"
                if not price_curve_reset_notice
                else f"Demo 结果已生成，可继续做经济测算、方案推荐和图表概览。{demo_retention_notice}{price_curve_reset_notice}{store_notice}"
            )
            _save_runtime_snapshot(st)
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
                    performance_params=PerformanceParams(
                        warn_if_scenarios_exceed=int(warn_threshold),
                        parallel_workers=int(parallel_workers),
                    ),
                    cleaning_params=DataCleaningParams(),
                    retain_hourly_details=bool(detail_retention_plan["retain_hourly_details"]),
                    hourly_detail_scenario_ids=tuple(detail_retention_plan["hourly_detail_scenario_ids"]),
                    config_metadata={
                        "bess_calendar_life_years": bess_calendar_life,
                        "ui_detail_retention_mode": detail_retention_plan["mode"],
                        "ui_detail_retention_message": detail_retention_plan["message"],
                    },
                ),
                progress_callback=update_progress,
            )
            progress_text.caption(
                f"计算完成：{technical_result.scenario_count}/{technical_result.scenario_count}"
            )

            persisted_result = _persist_pilot_technical_result_if_enabled(st, technical_result)
            study_result = StudyResult.from_technical(technical_result)
            if persisted_result is not None:
                study_result = _study_result_with_pilot_refs(study_result, persisted_result)
            st.session_state["study_result"] = study_result
            st.session_state["batch_result"] = technical_result.batch_result
            st.session_state["config_snapshot"] = technical_result.config_snapshot
            if batch_price_curve_file is None and price_curve_upload is None:
                _clear_project_price_curve(st)
            _clear_chart_export_cache(st)
            price_curve_reset_notice = _clear_project_price_curve_for_partial_hourly_retention(
                st,
                detail_retention_plan,
            ) or _discard_incompatible_project_price_curve(st, technical_result.batch_result.hourly_details)
            _clear_economy_outputs(st)
            retention_notice = "" if detail_retention_plan["mode"] == "full" else detail_retention_plan["message"]
            store_notice = st.session_state.pop(PILOT_RESULT_STORE_NOTICE_KEY, "")
            st.session_state["_simulation_notice"] = (
                f"测算完成。{retention_notice}{store_notice}"
                if not price_curve_reset_notice
                else f"测算完成。{retention_notice}{price_curve_reset_notice}{store_notice}"
            )
            _save_runtime_snapshot(st)
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
        st.dataframe(batch_result.errors, width="stretch")

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
        only_passed = st.checkbox("只看达标方案", value=False, key="simulation_result_only_passed")
        scheme_types = st.multiselect(
            "方案类型筛选（与达标筛选为 AND 关系）",
            sorted(summary["方案类型"].dropna().unique()),
            default=[],
            key="simulation_result_scheme_types",
        )
        sort_label = st.selectbox(
            "排序方式",
            ["绿电占比从高到低", "弃电率从低到高", "自发自用率从高到低", "上网比例从低到高", "储能容量从小到大"],
            key="simulation_result_sort_label",
        )
        display = _apply_filters(summary, only_passed, scheme_types, sort_label)
        max_display_rows = st.number_input(
            "结果表最多显示行数",
            min_value=50,
            max_value=5000,
            value=200,
            step=50,
            key="simulation_result_max_display_rows",
        )
        st.caption(f"当前筛选结果 {len(display)} 条，表格显示前 {min(len(display), int(max_display_rows))} 条。")
        st.dataframe(_format_summary_for_display(display.head(int(max_display_rows))), width="stretch")
        _display_mapping_expander(st, list(display.columns), "方案汇总字段对应关系")

        scenario_ids = list(batch_result.hourly_details.keys())
        st.caption(f"当前常驻逐小时明细 {len(scenario_ids)} 个方案；大批量模式下可能只保留部分或不保留。")
        if scenario_ids:
            selected = st.selectbox("选择方案查看逐小时字段", scenario_ids, key="simulation_result_hourly_scenario")
            _display_mapping_expander(
                st,
                list(batch_result.hourly_details[selected].columns),
                "逐小时明细字段对应关系",
            )
        else:
            st.info("当前结果仅常驻方案汇总，未保留逐小时明细；如需图表、逐小时导出或价格曲线经济性，请缩小范围或使用指定单方案复核。")

    st.info("方案仿真已完成。下一步请进入“经济性测算”设置经济参数并生成推荐所需的经济结果。")
    if st.button("进入经济性测算", key="technical_go_economy"):
        _go_to_workflow_page(st, "经济性测算")


def main() -> None:
    import streamlit as st

    _install_html_render_compat(st)
    st.set_page_config(page_title="绿电直连风光储方案策划平台", layout="wide")
    _inject_workbench_style(st)
    if not _ensure_pilot_authenticated(st):
        return
    _restore_runtime_snapshot_if_needed(st)
    if _clear_unconfirmed_project_price_curve(st):
        _save_runtime_snapshot(st)
    workflow_page = _render_workflow_navigation(st)
    if workflow_page != "方案仿真":
        _preserve_widget_state(st, SIMULATION_WIDGET_STATE_KEYS)
    restore_notice = st.session_state.pop("_runtime_restore_notice", None)
    if restore_notice:
        st.info(f"{restore_notice} 如需完全重新开始，请回到方案仿真页重新测算。")

    if workflow_page == PLATFORM_ADMIN_PAGE:
        _render_platform_admin_page(st)
        return

    if not _ensure_pilot_project_selected(st):
        return

    if workflow_page == "欢迎页":
        _render_welcome_page(st)
        return

    if workflow_page in {"方案仿真", "经济性测算"} and not _current_pilot_project_can_submit_jobs(st):
        _render_pilot_project_submit_permission_block(st)
        return

    if workflow_page in {"经济性测算", "方案推荐", "图表概览", "图表下载和报告生成"}:
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
                hourly_details=batch_result.hourly_details,
                dt_hours=1.0,
                render_recommendation=False,
            )
        elif workflow_page == "方案推荐":
            _render_recommendation_analysis_page(st, batch_result, summary)
        elif workflow_page == "图表概览":
            _render_chart_overview_page(st, batch_result, summary)
        else:
            _render_exports_and_reports_page(st, batch_result, summary)
        return

    _render_simulation_page(st)


if __name__ == "__main__":
    main()
