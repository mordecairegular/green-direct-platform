import pandas as pd
import plotly.graph_objects as go

from green_direct.visualization.chart_contracts import ChartResult, missing_fields_result
from green_direct.visualization.export_charts import ChartImageExportProfile, chart_to_png_bytes


def test_chart_result_contract():
    result = ChartResult(
        chart_id="T01",
        chart_name="测试图表",
        figure=None,
        data=pd.DataFrame({"a": [1]}),
        meta={"calculation_basis": "仅测试"},
        warnings=[],
    )

    assert result.chart_id == "T01"
    assert result.note == "仅测试"


def test_missing_fields_result_does_not_crash():
    result = missing_fields_result("T02", "缺字段图表", ["x", "y"])

    assert result.figure is None
    assert result.warnings
    assert "x, y" in result.warnings[0]


def test_chart_image_export_profile_uses_report_heights():
    profile = ChartImageExportProfile()

    typical = ChartResult("S03_summer", "典型日", go.Figure(), pd.DataFrame())
    heatmap = ChartResult("S04", "热力图", go.Figure(), pd.DataFrame())
    monthly = ChartResult("S05", "月度", go.Figure(), pd.DataFrame())
    full_year = ChartResult("S10", "全年", go.Figure(), pd.DataFrame())
    multi = ChartResult("M02", "多方案", go.Figure(), pd.DataFrame())
    other = ChartResult("S02", "政策", go.Figure(), pd.DataFrame())

    assert profile.height_for(typical) == 1300
    assert profile.height_for(heatmap) == 1000
    assert profile.height_for(monthly) == 900
    assert profile.height_for(full_year) == 1000
    assert profile.height_for(multi) == 900
    assert profile.height_for(other) == 900


def test_chart_to_png_bytes_copies_figure_before_report_layout(monkeypatch):
    original = go.Figure(data=[go.Bar(x=["a"], y=[1])])
    original.update_layout(height=420, width=640, title="原网页图")
    result = ChartResult("S03_spring", "典型日", original, pd.DataFrame())
    seen = {}

    def fake_to_image(self, *, format, width, height, scale):
        seen["layout_width"] = self.layout.width
        seen["layout_height"] = self.layout.height
        seen["format"] = format
        seen["width"] = width
        seen["height"] = height
        seen["scale"] = scale
        return b"fake-png"

    monkeypatch.setattr(go.Figure, "to_image", fake_to_image)

    content = chart_to_png_bytes(result)

    assert content == b"fake-png"
    assert seen == {
        "layout_width": 1800,
        "layout_height": 1300,
        "format": "png",
        "width": 1800,
        "height": 1300,
        "scale": 1.0,
    }
    assert original.layout.width == 640
    assert original.layout.height == 420
