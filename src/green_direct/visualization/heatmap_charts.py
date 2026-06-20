"""Heatmap chart builders."""

from __future__ import annotations

import pandas as pd
import plotly.express as px

from green_direct.visualization.chart_contracts import ChartResult, missing_fields_result
from green_direct.visualization.chart_data import adapt_hourly, missing_columns
from green_direct.visualization.style import HEATMAP_COLORSCALE

BASIS = "本图基于 hourly_detail 已有字段透视生成，不重新计算调度、SOC、上网或弃电。"

VALUE_FIELD_LABELS = {
    "grid_import_power": "电网下网功率",
    "grid_export_power": "新能源上网功率",
    "curtail_power": "弃电功率",
    "load_power": "负荷功率",
    "renewable_power": "新能源净可用功率",
    "soc_end": "储能 SOC",
}


def build_heatmap_chart(hourly: pd.DataFrame, value_field: str = "grid_import_power") -> ChartResult:
    data = adapt_hourly(hourly).data
    required = ["day_of_year", "hour", value_field]
    missing = missing_columns(data, required)
    if missing:
        return missing_fields_result("S04", "年度热力图", missing)
    matrix = data.pivot_table(index="hour", columns="day_of_year", values=value_field, aggfunc="mean")
    value_label = VALUE_FIELD_LABELS.get(value_field, value_field)
    fig = px.imshow(
        matrix,
        aspect="auto",
        origin="lower",
        labels={"x": "年内日序", "y": "小时", "color": value_label},
        title=f"年度热力图：{value_label}",
        color_continuous_scale=HEATMAP_COLORSCALE,
        template="plotly_white",
    )
    color_format = ".1%" if value_field in {"soc_end", "soc_start", "final_soc"} else ",.2f"
    fig.update_coloraxes(colorbar_tickformat=color_format, colorbar_title=value_label)
    fig.update_layout(height=500)
    return ChartResult(
        chart_id="S04",
        chart_name="年度热力图",
        figure=fig,
        data=matrix.reset_index(),
        meta={
            "unit": "万千瓦或 SOC",
            "fields_used": required,
            "aggregation_method": "day_of_year × hour 透视，均值聚合",
            "calculation_basis": BASIS,
            "export_ready": True,
        },
    )
