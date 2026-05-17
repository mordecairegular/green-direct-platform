import pandas as pd

from green_direct.visualization.chart_contracts import ChartResult, missing_fields_result


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
