"""Chart export helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
import os
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

from green_direct.visualization.chart_contracts import ChartResult
from green_direct.visualization.style import CHART_COLOR_SEQUENCE


@dataclass(frozen=True)
class ChartImageExportProfile:
    """Static image sizing rules for report-ready chart export."""

    name: str = "A4 纵向 Word 正文"
    width_px: int = 1800
    default_height_px: int = 900
    insert_width_cm: float = 16.0
    scale: float = 1.0
    height_by_chart_id: dict[str, int] = field(
        default_factory=lambda: {
            "S03": 1300,
            "S04": 1000,
            "S07": 1000,
            "S09": 1000,
            "S10": 1000,
            "S05": 900,
            "S06": 900,
            "M": 900,
        }
    )

    def height_for(self, result: ChartResult) -> int:
        chart_id = str(result.chart_id)
        for prefix, height in self.height_by_chart_id.items():
            if chart_id.startswith(prefix):
                return height
        return self.default_height_px


DOCX_A4_PORTRAIT_PROFILE = ChartImageExportProfile()


def _set_default_browser_path_for_kaleido() -> None:
    """Give Kaleido a browser hint on Windows when Chrome/Edge is installed."""

    if os.environ.get("BROWSER_PATH"):
        return

    candidates = [
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Microsoft/Edge/Application/msedge.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            os.environ["BROWSER_PATH"] = str(candidate)
            return


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


def _prepare_png_figure(
    result: ChartResult,
    profile: ChartImageExportProfile,
) -> tuple[go.Figure, int]:
    if result.figure is None:
        raise ValueError("图表未生成，无法导出 PNG。")
    figure = go.Figure(result.figure)
    height_px = profile.height_for(result)
    figure.update_layout(
        width=profile.width_px,
        height=height_px,
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        template="plotly_white",
        colorway=CHART_COLOR_SEQUENCE,
        font=dict(family="Arial, sans-serif", size=22, color="#172033"),
        title=dict(font=dict(size=28)),
        legend=dict(font=dict(size=20)),
        margin=dict(l=90, r=70, t=110, b=90),
    )
    return figure, height_px


def chart_to_png_bytes(
    result: ChartResult,
    profile: ChartImageExportProfile = DOCX_A4_PORTRAIT_PROFILE,
) -> bytes:
    """Export a report-sized PNG without mutating the interactive figure."""

    figure, height_px = _prepare_png_figure(result, profile)
    _set_default_browser_path_for_kaleido()
    return figure.to_image(
        format="png",
        width=profile.width_px,
        height=height_px,
        scale=profile.scale,
    )


def charts_to_png_bytes_batch(
    results: list[ChartResult],
    profile: ChartImageExportProfile = DOCX_A4_PORTRAIT_PROFILE,
) -> list[bytes]:
    """Export many report-sized PNGs through Plotly's batch image writer."""

    if not results:
        return []
    figures: list[go.Figure] = []
    heights: list[int] = []
    with TemporaryDirectory() as tmp_dir:
        output_paths = []
        for index, result in enumerate(results):
            figure, height_px = _prepare_png_figure(result, profile)
            figures.append(figure)
            heights.append(height_px)
            output_paths.append(Path(tmp_dir) / f"chart_{index:03d}.png")
        _set_default_browser_path_for_kaleido()
        pio.write_images(
            fig=figures,
            file=output_paths,
            format="png",
            width=profile.width_px,
            height=heights,
            scale=profile.scale,
        )
        return [path.read_bytes() for path in output_paths]


def try_chart_to_png_bytes(result: ChartResult) -> tuple[bytes | None, str | None]:
    if result.figure is None:
        return None, "图表未生成，无法导出 PNG。"
    try:
        return chart_to_png_bytes(result), None
    except Exception as exc:  # noqa: BLE001 - dependency availability varies by environment
        return None, f"PNG 导出需要可用的 kaleido/浏览器环境，当前未能导出：{exc}"
