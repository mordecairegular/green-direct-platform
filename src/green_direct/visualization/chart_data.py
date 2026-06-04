"""Data adaptation utilities for chart builders."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd


SUMMARY_ALIASES = {
    "scenario_id": ["scenario_id"],
    "pv_capacity": ["pv_capacity"],
    "wind_capacity": ["wind_capacity"],
    "bess_power": ["bess_power"],
    "bess_energy": ["bess_energy", "battery_energy_capacity"],
    "self_use_rate": ["self_use_rate", "renewable_self_consumption_rate"],
    "green_load_rate": ["green_load_rate", "green_power_share"],
    "export_rate": ["export_rate", "grid_export_rate"],
    "curtail_rate": ["curtail_rate", "curtailment_rate"],
    "total_load_energy": ["total_load_energy"],
    "total_renewable_generation": ["total_renewable_generation", "renewable_available_energy"],
    "direct_self_use_energy": ["direct_self_use_energy", "renewable_direct_to_load_energy"],
    "bess_discharge_to_load": ["bess_discharge_to_load", "battery_discharge_to_load_energy"],
    "self_use_energy": ["self_use_energy", "renewable_self_consumed_energy"],
    "grid_import_energy": ["grid_import_energy"],
    "grid_export_energy": ["grid_export_energy"],
    "curtail_energy": ["curtail_energy", "curtailment_energy"],
    "bess_charge_energy": ["bess_charge_energy", "battery_charge_energy"],
    "bess_loss_energy": ["bess_loss_energy", "battery_loss_energy"],
    "annual_equivalent_cycles": ["annual_equivalent_cycles", "battery_equivalent_cycles"],
    "pass_policy": ["pass_policy", "is_feasible"],
    "fail_reasons": ["fail_reasons", "failure_reasons"],
}

HOURLY_ALIASES = {
    "scenario_id": ["scenario_id"],
    "timestamp": ["timestamp"],
    "hour_index": ["hour_index"],
    "load_power": ["load_power"],
    "pv_power": ["pv_power", "pv_raw_power"],
    "wind_power": ["wind_power", "wind_raw_power"],
    "pv_generation_power": ["pv_generation_power", "pv_positive_power"],
    "wind_generation_power": ["wind_generation_power", "wind_positive_power"],
    "renewable_generation_power": ["renewable_generation_power", "renewable_positive_power"],
    "pv_station_use_power": ["pv_station_use_power"],
    "wind_station_use_power": ["wind_station_use_power"],
    "station_use_power": ["station_use_power"],
    "renewable_power": ["renewable_power", "renewable_net_power"],
    "direct_self_use_power": ["direct_self_use_power", "renewable_to_load_power"],
    "bess_charge_power": ["bess_charge_power", "battery_charge_power"],
    "bess_discharge_power": ["bess_discharge_power", "battery_discharge_power", "battery_discharge_to_load_power"],
    "grid_import_power": ["grid_import_power"],
    "grid_export_power": ["grid_export_power"],
    "curtail_power": ["curtail_power", "curtailment_power"],
    "exchange_import_shortfall_power": ["exchange_import_shortfall_power", "grid_import_shortage_power"],
    "soc_start": ["soc_start"],
    "soc_end": ["soc_end", "battery_soc"],
    "bess_energy_end": ["bess_energy_end", "battery_energy"],
}

SEASON_MONTHS = {
    "春季": [3, 4, 5],
    "夏季": [6, 7, 8],
    "秋季": [9, 10, 11],
    "冬季": [12, 1, 2],
}

TYPICAL_DAY_FEATURES = [
    "load_power",
    "pv_generation_power",
    "wind_generation_power",
    "renewable_power",
    "bess_charge_power",
    "bess_discharge_power",
    "grid_import_power",
    "grid_export_power",
    "curtail_power",
    "soc_end",
]


@dataclass
class AdaptedData:
    data: pd.DataFrame
    warnings: list[str]


@dataclass
class TypicalDaySelection:
    day: pd.DataFrame
    label: str
    method: str
    score: float | None = None


def _copy_aliases(df: pd.DataFrame, aliases: dict[str, list[str]]) -> AdaptedData:
    result = df.copy()
    warnings: list[str] = []
    for standard, candidates in aliases.items():
        if standard in result.columns:
            continue
        for candidate in candidates:
            if candidate in result.columns:
                result[standard] = result[candidate]
                break
    return AdaptedData(result, warnings)


def adapt_summary(summary: pd.DataFrame) -> AdaptedData:
    return _copy_aliases(summary, SUMMARY_ALIASES)


def adapt_hourly(hourly: pd.DataFrame) -> AdaptedData:
    adapted = _copy_aliases(hourly, HOURLY_ALIASES)
    result = adapted.data
    warnings = adapted.warnings
    if "timestamp" in result.columns:
        timestamp = pd.to_datetime(result["timestamp"], errors="coerce")
        result["timestamp"] = timestamp
        result["date"] = timestamp.dt.date
        result["month"] = timestamp.dt.month
        result["day_of_year"] = timestamp.dt.dayofyear
        result["hour"] = timestamp.dt.hour
    else:
        warnings.append("逐小时数据缺少 timestamp，日期类图表将不可用。")
    if "grid_exchange_power" not in result.columns:
        if {"grid_export_power", "grid_import_power"}.issubset(result.columns):
            result["grid_exchange_power"] = result["grid_export_power"] - result["grid_import_power"]
        else:
            warnings.append("逐小时数据缺少 grid_export_power 或 grid_import_power，无法生成净交换功率。")
    if "surplus_renewable_power" not in result.columns:
        required = {"bess_charge_power", "grid_export_power", "curtail_power"}
        if required.issubset(result.columns):
            result["surplus_renewable_power"] = (
                result["bess_charge_power"] + result["grid_export_power"] + result["curtail_power"]
            )
    return AdaptedData(result, warnings)


def missing_columns(df: pd.DataFrame, required: Iterable[str]) -> list[str]:
    return [column for column in required if column not in df.columns]


def filter_scenario(summary: pd.DataFrame, scenario_id: str) -> pd.DataFrame:
    if "scenario_id" not in summary.columns:
        return pd.DataFrame()
    return summary[summary["scenario_id"].astype(str) == str(scenario_id)].copy()


def filter_hourly(hourly: pd.DataFrame, scenario_id: str | None = None) -> pd.DataFrame:
    if scenario_id is None or "scenario_id" not in hourly.columns:
        return hourly.copy()
    return hourly[hourly["scenario_id"].astype(str) == str(scenario_id)].copy()


def _format_mmdd(value) -> str:
    return pd.Timestamp(value).strftime("%m/%d")


def _prepare_time_fields(hourly: pd.DataFrame) -> pd.DataFrame:
    data = hourly.copy()
    if "timestamp" in data.columns:
        timestamp = pd.to_datetime(data["timestamp"], errors="coerce")
        data["timestamp"] = timestamp
        data["date"] = timestamp.dt.date
        data["month"] = timestamp.dt.month
        data["hour"] = timestamp.dt.hour
    elif "date" in data.columns:
        data["date"] = pd.to_datetime(data["date"], errors="coerce").dt.date
    return data


def _complete_day_frame(group: pd.DataFrame) -> pd.DataFrame:
    if "hour" in group.columns:
        day = group.dropna(subset=["hour"]).copy()
        day["hour"] = pd.to_numeric(day["hour"], errors="coerce")
        day = day.dropna(subset=["hour"]).drop_duplicates(subset=["hour"]).sort_values("hour")
        if set(day["hour"].astype(int)) >= set(range(24)):
            return day[day["hour"].astype(int).between(0, 23)].head(24).copy()
        return pd.DataFrame()
    return group.head(24).copy() if len(group) >= 24 else pd.DataFrame()


def _fallback_day(data: pd.DataFrame, method: str) -> TypicalDaySelection:
    if "date" in data.columns and data["date"].notna().any():
        date_value = data["date"].dropna().iloc[0]
        day = data[data["date"] == date_value].head(24).copy()
        return TypicalDaySelection(day=day, label=_format_mmdd(date_value), method=method, score=None)
    return TypicalDaySelection(day=data.head(24).copy(), label="前 24 小时", method=method, score=None)


def select_typical_season_day(
    hourly: pd.DataFrame,
    season: str,
    feature_fields: Iterable[str] | None = None,
) -> TypicalDaySelection:
    """Select a real 24-hour day closest to the seasonal average profile."""

    data = _prepare_time_fields(hourly)
    if data.empty:
        return TypicalDaySelection(day=data.copy(), label="无数据", method="没有可用逐小时数据。", score=None)
    if not {"date", "month"}.issubset(data.columns):
        return _fallback_day(data, "缺少 timestamp，退回前 24 小时作为示例日。")

    season_months = SEASON_MONTHS.get(season, list(range(1, 13)))
    season_data = data[data["month"].isin(season_months)].dropna(subset=["date"]).copy()
    if season_data.empty:
        season_data = data.dropna(subset=["date"]).copy()
    if season_data.empty:
        return _fallback_day(data, "没有可解析日期，退回前 24 小时作为示例日。")

    requested_fields = list(feature_fields or TYPICAL_DAY_FEATURES)
    fields = [field for field in requested_fields if field in season_data.columns]
    if not fields:
        return _fallback_day(season_data, "缺少典型日特征字段，退回该季节首个可用日期。")

    vectors: list[list[float]] = []
    dates: list[object] = []
    day_frames: dict[object, pd.DataFrame] = {}
    for date_value, group in season_data.groupby("date", sort=True):
        day = _complete_day_frame(group)
        if len(day) != 24:
            continue
        vector: list[float] = []
        for field in fields:
            values = pd.to_numeric(day[field], errors="coerce").fillna(0.0).astype(float)
            vector.extend(values.tolist())
        vectors.append(vector)
        dates.append(date_value)
        day_frames[date_value] = day

    if not vectors:
        return _fallback_day(season_data, "该季节没有完整 24 小时日期，退回首个可用日期。")

    matrix = pd.DataFrame(vectors, index=pd.Index(dates, name="date"), dtype=float)
    column_std = matrix.std(axis=0, ddof=0).replace(0, 1).fillna(1)
    normalized = (matrix - matrix.mean(axis=0)) / column_std
    centroid = normalized.mean(axis=0)
    distances = ((normalized - centroid) ** 2).mean(axis=1)
    selected_date = distances.idxmin()
    method = (
        "季节中心日法：在该季节所有完整 24 小时日期中，按负荷、风光、储能、电网、弃电、SOC 等"
        "已有逐小时字段标准化后，选择离季节平均曲线最近的真实日期。"
    )
    return TypicalDaySelection(
        day=day_frames[selected_date].copy(),
        label=_format_mmdd(selected_date),
        method=method,
        score=float(distances.loc[selected_date]),
    )


def select_day(hourly: pd.DataFrame, mode: str = "首日", selected_date=None) -> tuple[pd.DataFrame, str]:
    if "date" not in hourly.columns:
        return hourly.head(24).copy(), "前 24 小时"
    if selected_date is not None:
        date_value = pd.to_datetime(selected_date).date()
    elif mode == "最大负荷日" and "load_power" in hourly.columns:
        date_value = hourly.groupby("date")["load_power"].sum().idxmax()
    elif mode == "最大弃电日" and "curtail_power" in hourly.columns:
        date_value = hourly.groupby("date")["curtail_power"].sum().idxmax()
    elif mode == "最大下网日" and "grid_import_power" in hourly.columns:
        date_value = hourly.groupby("date")["grid_import_power"].sum().idxmax()
    elif mode == "SOC 最低日" and "soc_end" in hourly.columns:
        date_value = hourly.loc[hourly["soc_end"].idxmin(), "date"]
    elif mode == "SOC 最高日" and "soc_end" in hourly.columns:
        date_value = hourly.loc[hourly["soc_end"].idxmax(), "date"]
    else:
        date_value = hourly["date"].dropna().iloc[0]
    day = hourly[hourly["date"] == date_value].copy()
    return day, str(date_value)
