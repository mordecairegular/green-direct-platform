"""Shared visual styling for interactive and exported charts."""

from __future__ import annotations

CHART_COLORS = {
    "pv": "#f4c20d",
    "wind": "#58c7df",
    "renewable": "#58c7df",
    "renewable_direct": "#469585",
    "bess": "#56c596",
    "bess_discharge": "#56c596",
    "bess_charge": "#7bdcb5",
    "grid_import": "#94a3b8",
    "grid_export": "#2563eb",
    "curtail": "#ef7d22",
    "loss": "#9aa4b2",
    "station_use": "#cbd5e1",
    "load": "#111827",
    "soc": "#4a9d8f",
    "threshold": "#d2603a",
    "actual": "#2e7d72",
    "muted": "#6b7280",
    "line": "#111827",
    "accent": "#e9b400",
}

CHART_COLOR_SEQUENCE = [
    CHART_COLORS["wind"],
    CHART_COLORS["pv"],
    CHART_COLORS["bess"],
    CHART_COLORS["grid_import"],
    CHART_COLORS["grid_export"],
    CHART_COLORS["curtail"],
    CHART_COLORS["loss"],
    CHART_COLORS["actual"],
]

MONTHLY_LOAD_SOURCE_COLORS = {
    "新能源直供": CHART_COLORS["renewable_direct"],
    "储能放电": CHART_COLORS["bess_discharge"],
    "电网下网": CHART_COLORS["grid_import"],
}

MONTHLY_RENEWABLE_FLOW_COLORS = {
    "直供负荷": CHART_COLORS["renewable_direct"],
    "充入储能": CHART_COLORS["bess_charge"],
    "上网": CHART_COLORS["grid_export"],
    "弃电": CHART_COLORS["curtail"],
    "站用电": CHART_COLORS["station_use"],
}

RENEWABLE_FLOW_COLORS = {
    "自发自用": CHART_COLORS["renewable_direct"],
    "上网": CHART_COLORS["grid_export"],
    "弃电": CHART_COLORS["curtail"],
    "储能损耗": CHART_COLORS["loss"],
}

POLICY_METRIC_COLORS = {
    "自发自用率": CHART_COLORS["renewable_direct"],
    "绿电占用电比例": CHART_COLORS["bess_discharge"],
    "上网比例": CHART_COLORS["grid_export"],
}

CAPACITY_COLORS = {
    "光伏容量": CHART_COLORS["pv"],
    "风电容量": CHART_COLORS["wind"],
    "储能功率": CHART_COLORS["bess_discharge"],
    "储能容量": "#7c3aed",
}

HEATMAP_COLORSCALE = [
    [0.0, "#f8fafc"],
    [0.20, "#dbeafe"],
    [0.45, "#7dd3fc"],
    [0.70, "#0ea5e9"],
    [1.0, "#1e3a8a"],
]
