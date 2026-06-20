"""Contracts shared by chart builders and UI."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd


@dataclass
class ChartResult:
    """Unified chart result returned by every visualization builder."""

    chart_id: str
    chart_name: str
    figure: Any
    data: pd.DataFrame
    meta: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def note(self) -> str:
        return str(
            self.meta.get(
                "calculation_basis",
                "本图基于已有测算结果绘制，图表模块仅做展示性聚合，不重新计算储能调度、上网或弃电逻辑。",
            )
        )


def missing_fields_result(chart_id: str, chart_name: str, missing: list[str]) -> ChartResult:
    """Return a non-crashing result for charts that cannot be built."""

    warning = f"无法生成“{chart_name}”，缺少字段：{', '.join(missing)}。"
    return ChartResult(
        chart_id=chart_id,
        chart_name=chart_name,
        figure=None,
        data=pd.DataFrame(),
        meta={
            "fields_used": [],
            "warnings": [warning],
            "export_ready": False,
            "calculation_basis": "字段不足，未生成图表；图表模块不会为补字段而重算核心调度结果。",
        },
        warnings=[warning],
    )
