from io import BytesIO

import pandas as pd
import pytest

from green_direct.io.read_curves import read_curve_set, read_load_curve, read_pu_curve
from green_direct.io.validators import DataValidationError
from green_direct.models.diagnostics import DiagnosticSeverity
from green_direct.models.params import DataCleaningParams


def _csv_bytes(rows=8760, value_col="负荷", value=1.0, encoding="utf-8"):
    timestamps = pd.date_range("2020-01-01", periods=rows, freq="h")
    df = pd.DataFrame({"时间": timestamps.astype(str), value_col: value})
    return df.to_csv(index=False).encode(encoding)


def test_read_load_curve_utf8_and_supported_length():
    curve = read_load_curve(BytesIO(_csv_bytes()), "时间", "负荷")

    assert len(curve.data) == 8760
    assert list(curve.data.columns) == ["timestamp", "load_power"]
    assert curve.encoding == "utf-8"


def test_read_load_curve_supports_8784_rows():
    curve = read_load_curve(BytesIO(_csv_bytes(rows=8784)), "时间", "负荷")

    assert len(curve.data) == 8784


def test_read_gbk_csv():
    curve = read_load_curve(BytesIO(_csv_bytes(encoding="gbk")), "时间", "负荷")

    assert curve.encoding == "gbk"
    assert curve.data["load_power"].iloc[0] == 1.0


def test_reject_unsupported_length():
    with pytest.raises(DataValidationError, match="仅支持"):
        read_load_curve(BytesIO(_csv_bytes(rows=8759)), "时间", "负荷")


def test_reject_negative_load():
    data = _csv_bytes(value=-1.0)

    with pytest.raises(DataValidationError, match="负荷值不能小于 0"):
        read_load_curve(BytesIO(data), "时间", "负荷")


def test_negative_pu_is_allowed_by_default_and_warns():
    data = _csv_bytes(value_col="光伏", value=-0.0005)

    curve = read_pu_curve(BytesIO(data), "时间", "光伏", "光伏")

    assert curve.data["pv_pu"].iloc[0] == -0.0005
    assert any("站用电" in item for item in curve.warnings)


def test_can_clip_small_negative_pu_when_explicitly_configured():
    data = _csv_bytes(value_col="光伏", value=-0.0005)

    curve = read_pu_curve(
        BytesIO(data),
        "时间",
        "光伏",
        "光伏",
        cleaning=DataCleaningParams(allow_small_negative_pu=True, clip_small_negative_to_zero=True),
    )
    assert curve.data["pv_pu"].max() == 0
    assert curve.warnings


def test_reject_negative_pu_when_configured():
    data = _csv_bytes(value_col="光伏", value=-0.01)

    with pytest.raises(DataValidationError, match="存在负值"):
        read_pu_curve(
            BytesIO(data),
            "时间",
            "光伏",
            "光伏",
            cleaning=DataCleaningParams(allow_negative_pu=False),
        )


def test_pu_greater_than_one_warns_but_allowed():
    data = _csv_bytes(value_col="风电", value=1.2)

    curve = read_pu_curve(BytesIO(data), "时间", "风电", "风电")

    assert curve.data["wind_pu"].iloc[0] == 1.2
    assert any("大于 1" in item for item in curve.warnings)


def test_curve_set_requires_same_length():
    load = _csv_bytes(rows=8760, value_col="负荷", value=1.0)
    pv = _csv_bytes(rows=8784, value_col="光伏", value=0.5)
    wind = _csv_bytes(rows=8760, value_col="风电", value=0.5)

    with pytest.raises(DataValidationError, match="行数不一致|仅支持"):
        read_curve_set(
            BytesIO(load),
            BytesIO(pv),
            BytesIO(wind),
            load_time_col="时间",
            load_value_col="负荷",
            pv_time_col="时间",
            pv_value_col="光伏",
            wind_time_col="时间",
            wind_value_col="风电",
        )


def test_curve_set_requires_aligned_timestamps():
    load = pd.DataFrame(
        {"时间": pd.date_range("2020-01-01", periods=8760, freq="h").astype(str), "负荷": 1}
    )
    pv = pd.DataFrame(
        {"时间": pd.date_range("2020-01-01 01:00", periods=8760, freq="h").astype(str), "光伏": 0.5}
    )
    wind = pd.DataFrame(
        {"时间": pd.date_range("2020-01-01", periods=8760, freq="h").astype(str), "风电": 0.5}
    )

    with pytest.raises(DataValidationError, match="时间列不一致"):
        read_curve_set(
            BytesIO(load.to_csv(index=False).encode("utf-8")),
            BytesIO(pv.to_csv(index=False).encode("utf-8")),
            BytesIO(wind.to_csv(index=False).encode("utf-8")),
            load_time_col="时间",
            load_value_col="负荷",
            pv_time_col="时间",
            pv_value_col="光伏",
            wind_time_col="时间",
            wind_value_col="风电",
        )


def test_read_curve_set_success():
    result = read_curve_set(
        BytesIO(_csv_bytes(value_col="负荷", value=10)),
        BytesIO(_csv_bytes(value_col="光伏", value=0.3)),
        BytesIO(_csv_bytes(value_col="风电", value=0.4)),
        load_time_col="时间",
        load_value_col="负荷",
        pv_time_col="时间",
        pv_value_col="光伏",
        wind_time_col="时间",
        wind_value_col="风电",
    )

    assert list(result.data.columns) == ["timestamp", "load_power", "pv_pu", "wind_pu"]
    assert result.data["load_power"].sum() == 87600


def test_pu_curve_warning_is_also_recorded_as_diagnostic():
    timestamps = pd.date_range("2020-01-01", periods=8760, freq="h")
    df = pd.DataFrame({"time": timestamps.astype(str), "pv": -0.0005})
    data = df.to_csv(index=False).encode("utf-8")

    curve = read_pu_curve(BytesIO(data), "time", "pv", "鍏変紡")

    assert curve.warnings
    assert curve.diagnostics is not None
    assert curve.diagnostics.items[0].severity is DiagnosticSeverity.WARNING
    assert curve.diagnostics.items[0].code == "PU_CURVE_WARNING"
