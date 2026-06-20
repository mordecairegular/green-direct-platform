"""CSV curve readers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

import pandas as pd

from green_direct.io.validators import (
    DataValidationError,
    clean_pu_values,
    parse_timestamp_column,
    validate_aligned_curves,
    validate_load_values,
    validate_required_columns,
    validate_supported_length,
)
from green_direct.models.diagnostics import InputDiagnostics
from green_direct.models.params import DataCleaningParams, TimeParams

SUPPORTED_ENCODINGS = ("utf-8", "utf-8-sig", "gbk", "gb18030")


@dataclass
class CurveData:
    """A normalized single input curve."""

    data: pd.DataFrame
    warnings: list[str]
    encoding: str
    diagnostics: InputDiagnostics | None = None


@dataclass
class CurveSet:
    """Aligned load, PV, and wind curves."""

    data: pd.DataFrame
    warnings: list[str]
    encodings: dict[str, str]
    diagnostics: InputDiagnostics | None = None


def _read_bytes(source: str | Path | BinaryIO | bytes) -> bytes:
    if isinstance(source, bytes):
        return source
    if isinstance(source, (str, Path)):
        return Path(source).read_bytes()
    if hasattr(source, "seek"):
        source.seek(0)
    content = source.read()
    if isinstance(content, str):
        return content.encode("utf-8")
    return content


def read_csv_auto_encoding(source: str | Path | BinaryIO | bytes) -> tuple[pd.DataFrame, str]:
    """Read a CSV by trying the encodings required by DATA_SCHEMA.md."""

    raw = _read_bytes(source)
    last_error: Exception | None = None
    for encoding in SUPPORTED_ENCODINGS:
        try:
            from io import BytesIO

            return pd.read_csv(BytesIO(raw), encoding=encoding), encoding
        except UnicodeDecodeError as exc:
            last_error = exc
    raise DataValidationError("CSV 文件编码无法识别，请转换为 UTF-8、UTF-8-SIG、GBK 或 GB18030。") from last_error


def read_load_curve(
    source: str | Path | BinaryIO | bytes,
    time_col: str | None = None,
    value_col: str | None = None,
    *,
    validate_length: bool = True,
    time_params: TimeParams | None = None,
) -> CurveData:
    df, encoding = read_csv_auto_encoding(source)
    if time_col is None:
        time_col = df.columns[0]
    if value_col is None:
        value_col = df.columns[1]
    validate_required_columns(df, [time_col, value_col])
    timestamp = parse_timestamp_column(df, time_col)
    value = validate_load_values(df[value_col])
    normalized = pd.DataFrame({"timestamp": timestamp, "load_power": value})
    if validate_length:
        validate_supported_length(len(normalized), time_params)
    return CurveData(normalized, [], encoding, InputDiagnostics())


def read_pu_curve(
    source: str | Path | BinaryIO | bytes,
    time_col: str | None = None,
    value_col: str | None = None,
    curve_name: str = "",
    *,
    validate_length: bool = True,
    cleaning: DataCleaningParams | None = None,
    time_params: TimeParams | None = None,
) -> CurveData:
    df, encoding = read_csv_auto_encoding(source)
    if time_col is None:
        time_col = df.columns[0]
    if value_col is None:
        value_col = df.columns[1]
    validate_required_columns(df, [time_col, value_col])
    timestamp = parse_timestamp_column(df, time_col)
    value, warnings = clean_pu_values(df[value_col], curve_name, cleaning)
    column = "pv_pu" if curve_name == "光伏" else "wind_pu"
    normalized = pd.DataFrame({"timestamp": timestamp, column: value})
    if validate_length:
        validate_supported_length(len(normalized), time_params)
    diagnostics = InputDiagnostics.from_warning_messages(warnings, source="curve_cleaning", code="PU_CURVE_WARNING")
    return CurveData(normalized, warnings, encoding, diagnostics)


def read_curve_set(
    load_source: str | Path | BinaryIO | bytes,
    pv_source: str | Path | BinaryIO | bytes,
    wind_source: str | Path | BinaryIO | bytes,
    *,
    load_time_col: str | None = None,
    load_value_col: str | None = None,
    pv_time_col: str | None = None,
    pv_value_col: str | None = None,
    wind_time_col: str | None = None,
    wind_value_col: str | None = None,
    validate_length: bool = True,
    cleaning: DataCleaningParams | None = None,
    time_params: TimeParams | None = None,
) -> CurveSet:
    load = read_load_curve(
        load_source,
        load_time_col,
        load_value_col,
        validate_length=validate_length,
        time_params=time_params,
    )
    pv = read_pu_curve(
        pv_source,
        pv_time_col,
        pv_value_col,
        "光伏",
        validate_length=validate_length,
        cleaning=cleaning,
        time_params=time_params,
    )
    wind = read_pu_curve(
        wind_source,
        wind_time_col,
        wind_value_col,
        "风电",
        validate_length=validate_length,
        cleaning=cleaning,
        time_params=time_params,
    )

    validate_aligned_curves(load.data, pv.data, wind.data)
    merged = load.data.copy()
    merged["pv_pu"] = pv.data["pv_pu"].to_numpy()
    merged["wind_pu"] = wind.data["wind_pu"].to_numpy()
    warnings = [*load.warnings, *pv.warnings, *wind.warnings]
    encodings = {"load": load.encoding, "pv": pv.encoding, "wind": wind.encoding}
    diagnostics = InputDiagnostics()
    for item in (load.diagnostics, pv.diagnostics, wind.diagnostics):
        if item is not None:
            diagnostics.extend(item)
    return CurveSet(merged, warnings, encodings, diagnostics)


def convert_raw_power_to_pu(power: pd.Series, base_capacity: float) -> pd.Series:
    """Convert a raw power curve into a per-unit curve."""

    if base_capacity <= 0:
        raise DataValidationError("基准装机容量必须大于 0。")
    return pd.to_numeric(power, errors="raise").astype(float) / base_capacity
