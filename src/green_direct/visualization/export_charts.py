"""Chart export helpers."""

from __future__ import annotations

from io import BytesIO

import pandas as pd

from green_direct.visualization.chart_contracts import ChartResult


def chart_to_html_bytes(result: ChartResult) -> bytes:
    if result.figure is None:
        return b""
    return result.figure.to_html(include_plotlyjs="cdn").encode("utf-8")


def chart_to_excel_bytes(result: ChartResult) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        result.data.to_excel(writer, sheet_name="chart_data", index=False)
        pd.DataFrame({"key": list(result.meta.keys()), "value": [str(v) for v in result.meta.values()]}).to_excel(
            writer,
            sheet_name="meta",
            index=False,
        )
        pd.DataFrame({"warning": result.warnings}).to_excel(writer, sheet_name="warnings", index=False)
    return output.getvalue()


def chart_to_meta_markdown(result: ChartResult) -> str:
    lines = [f"# {result.chart_name}", "", f"- chart_id: `{result.chart_id}`", f"- 口径: {result.note}"]
    fields = result.meta.get("fields_used", [])
    if fields:
        lines.append(f"- 使用字段: {', '.join(fields)}")
    if result.warnings:
        lines.append("")
        lines.append("## 提示")
        lines.extend(f"- {warning}" for warning in result.warnings)
    return "\n".join(lines) + "\n"


def try_chart_to_png_bytes(result: ChartResult) -> tuple[bytes | None, str | None]:
    if result.figure is None:
        return None, "图表未生成，无法导出 PNG。"
    try:
        return result.figure.to_image(format="png"), None
    except Exception as exc:  # noqa: BLE001 - dependency availability varies by environment
        return None, f"PNG 导出需要可用的 kaleido/浏览器环境，当前未能导出：{exc}"
