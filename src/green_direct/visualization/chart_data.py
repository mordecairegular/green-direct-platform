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


@dataclass
class AdaptedData:
    data: pd.DataFrame
    warnings: list[str]


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
