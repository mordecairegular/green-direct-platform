"""Heatmap chart builders."""

from __future__ import annotations

import pandas as pd
import plotly.express as px

from green_direct.visualization.chart_contracts import ChartResult, missing_fields_result
from green_direct.visualization.chart_data import adapt_hourly, missing_columns

BASIS = "本图基于 hourly_detail 已有字段透视生成，不重新计算调度、SOC、上网或弃电。"


def build_heatmap_chart(hourly: pd.DataFrame, value_field: str = "grid_import_power") -> ChartResult:
    data = adapt_hourly(hourly).data
    required = ["day_of_year", "hour", value_field]
    missing = missing_columns(data, required)
    if missing:
        return missing_fields_result("S04", "年度热力图", missing)
    matrix = data.pivot_table(index="hour", columns="day_of_year", values=value_field, aggfunc="mean")
    fig = px.imshow(
        matrix,
        aspect="auto",
        origin="lower",
        labels={"x": "年内日序", "y": "小时", "color": value_field},
        title=f"年度热力图：{value_field}",
    )
    color_format = ".1%" if value_field in {"soc_end", "soc_start", "final_soc"} else ",.2f"
    fig.update_coloraxes(colorbar_tickformat=color_format)
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
