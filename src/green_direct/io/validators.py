"""Input data validators."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from green_direct.models.params import DataCleaningParams, TimeParams


class DataValidationError(ValueError):
    """Raised when input data cannot be used for simulation."""


@dataclass
class ValidationWarnings:
    """Collect non-fatal validation warnings."""

    messages: list[str] = field(default_factory=list)

    def add(self, message: str) -> None:
        self.messages.append(message)

    def extend(self, messages: list[str]) -> None:
        self.messages.extend(messages)


def validate_required_columns(df: pd.DataFrame, columns: list[str]) -> None:
    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise DataValidationError(f"缺少必要列: {', '.join(missing)}")


def parse_timestamp_column(df: pd.DataFrame, time_col: str) -> pd.Series:
    validate_required_columns(df, [time_col])
    parsed = pd.to_datetime(df[time_col], errors="coerce")
    bad_mask = parsed.isna()
    if bad_mask.any():
        first_bad = int(np.flatnonzero(bad_mask.to_numpy())[0])
        raise DataValidationError(f"时间列无法解析，请检查第 {first_bad + 1} 行附近的时间戳。")
    return parsed


def validate_supported_length(length: int, time_params: TimeParams | None = None) -> None:
    params = time_params or TimeParams()
    if length not in params.supported_hours:
        supported = " / ".join(str(item) for item in params.supported_hours)
        raise DataValidationError(f"时间序列行数为 {length}，仅支持 {supported} 行。")


def validate_load_values(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    if numeric.isna().any():
        first_bad = int(np.flatnonzero(numeric.isna().to_numpy())[0])
        raise DataValidationError(f"负荷列存在空值或非数字，请检查第 {first_bad + 1} 行。")
    if (numeric < 0).any():
        first_bad = int(np.flatnonzero((numeric < 0).to_numpy())[0])
        raise DataValidationError(f"负荷值不能小于 0，请检查第 {first_bad + 1} 行。")
    return numeric.astype(float)


def clean_pu_values(
    values: pd.Series,
    curve_name: str,
    cleaning: DataCleaningParams | None = None,
) -> tuple[pd.Series, list[str]]:
    params = cleaning or DataCleaningParams()
    numeric = pd.to_numeric(values, errors="coerce")
    if numeric.isna().any():
        first_bad = int(np.flatnonzero(numeric.isna().to_numpy())[0])
        raise DataValidationError(f"{curve_name}曲线存在空值或非数字，请检查第 {first_bad + 1} 行。")

    numeric = numeric.astype(float).copy()
    warnings: list[str] = []

    negative_mask = numeric < 0
    if negative_mask.any():
        if params.clip_small_negative_to_zero:
            obvious_negative = numeric < params.small_negative_tolerance
            if obvious_negative.any() and not params.allow_negative_pu:
                first_bad = int(np.flatnonzero(obvious_negative.to_numpy())[0])
                raise DataValidationError(
                    f"{curve_name}曲线存在明显负值，小于允许阈值 "
                    f"{params.small_negative_tolerance}，请检查第 {first_bad + 1} 行。"
                )
            numeric.loc[negative_mask & ~obvious_negative] = 0.0
            warnings.append(f"{curve_name}曲线存在微小负值，已按配置截断为 0。")
        elif not params.allow_negative_pu:
            first_bad = int(np.flatnonzero(negative_mask.to_numpy())[0])
            raise DataValidationError(f"{curve_name}曲线存在负值，请检查第 {first_bad + 1} 行。")
        else:
            count = int(negative_mask.sum())
            warnings.append(f"{curve_name}曲线存在负值，共 {count} 个点，将按站用电参与计算。")

    greater_than_one = numeric > 1
    if greater_than_one.any():
        if not params.allow_pu_greater_than_one:
            first_bad = int(np.flatnonzero(greater_than_one.to_numpy())[0])
            raise DataValidationError(f"{curve_name}曲线存在大于 1 的值，请检查第 {first_bad + 1} 行。")
        warnings.append(f"{curve_name}曲线存在大于 1 的标幺值，请确认是否符合数据口径。")
        if params.clip_pu_greater_than_one:
            numeric.loc[greater_than_one] = 1.0
            warnings.append(f"{curve_name}曲线大于 1 的值已按配置截断为 1。")

    return numeric, warnings


def validate_aligned_curves(load: pd.DataFrame, pv: pd.DataFrame, wind: pd.DataFrame) -> None:
    lengths = {"负荷": len(load), "光伏": len(pv), "风电": len(wind)}
    if len(set(lengths.values())) != 1:
        detail = ", ".join(f"{name} {length}" for name, length in lengths.items())
        raise DataValidationError(f"三条曲线行数不一致: {detail}。")

    load_time = load["timestamp"].reset_index(drop=True)
    pv_time = pv["timestamp"].reset_index(drop=True)
    wind_time = wind["timestamp"].reset_index(drop=True)
    mismatch = (load_time != pv_time) | (load_time != wind_time)
    if mismatch.any():
        first_bad = int(np.flatnonzero(mismatch.to_numpy())[0])
        raise DataValidationError(f"三条曲线的时间列不一致，请检查第 {first_bad + 1} 行附近的时间戳。")
