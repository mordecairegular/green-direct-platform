"""Technical and policy metric calculations."""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

from green_direct.models.params import BessParams, PolicyParams
from green_direct.models.scenario import Scenario


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    if denominator == 0:
        return default
    return numerator / denominator


def evaluate_policy(
    *,
    self_use_rate: float,
    green_load_rate: float,
    export_rate: float,
    grid_export_energy: float,
    max_grid_export_power: float,
    exchange_import_shortfall_energy: float,
    policy: PolicyParams,
) -> tuple[bool, str]:
    reasons: list[str] = []
    tolerance = 1e-9
    if self_use_rate + tolerance < policy.self_use_rate_min:
        reasons.append("自发自用率不足")
    if green_load_rate + tolerance < policy.green_load_rate_min:
        reasons.append("绿电占用电比例不足")
    if export_rate - tolerance > policy.export_rate_max:
        reasons.append("上网比例超限")
    if not policy.allow_export and grid_export_energy > tolerance:
        reasons.append("不允许上网但出现上网")
    if policy.export_power_max is not None and max_grid_export_power - tolerance > policy.export_power_max:
        reasons.append("最大上网功率超限")
    if exchange_import_shortfall_energy > tolerance:
        reasons.append("电网交换功率限制导致下网缺口")
    return not reasons, "; ".join(reasons)


def calculate_summary(
    hourly: pd.DataFrame,
    scenario: Scenario,
    bess_params: BessParams,
    policy: PolicyParams,
    *,
    initial_bess_energy: float,
    dt_hours: float = 1.0,
) -> dict[str, Any]:
    total_load_energy = float(hourly["load_power"].sum() * dt_hours)
    renewable_generation_col = (
        "renewable_generation_power" if "renewable_generation_power" in hourly.columns else "renewable_power"
    )
    total_renewable_generation = float(hourly[renewable_generation_col].sum() * dt_hours)
    pv_station_use_energy = float(hourly["pv_station_use_power"].sum() * dt_hours) if "pv_station_use_power" in hourly else 0.0
    wind_station_use_energy = (
        float(hourly["wind_station_use_power"].sum() * dt_hours) if "wind_station_use_power" in hourly else 0.0
    )
    station_use_energy = pv_station_use_energy + wind_station_use_energy
    direct_self_use_energy = float(hourly["direct_self_use_power"].sum() * dt_hours)
    bess_discharge_to_load = float(hourly["bess_discharge_power"].sum() * dt_hours)
    self_use_energy = direct_self_use_energy + bess_discharge_to_load
    grid_import_energy = float(hourly["grid_import_power"].sum() * dt_hours)
    grid_import_rate = safe_divide(grid_import_energy, total_load_energy)
    grid_export_energy = float(hourly["grid_export_power"].sum() * dt_hours)
    curtail_energy = float(hourly["curtail_power"].sum() * dt_hours)
    curtail_due_to_export_cap_energy = float(hourly["curtail_due_to_export_cap_power"].sum() * dt_hours)
    curtail_due_to_exchange_limit_energy = (
        float(hourly["curtail_due_to_exchange_limit_power"].sum() * dt_hours)
        if "curtail_due_to_exchange_limit_power" in hourly
        else 0.0
    )
    exchange_import_shortfall_energy = (
        float(hourly["exchange_import_shortfall_power"].sum() * dt_hours)
        if "exchange_import_shortfall_power" in hourly
        else 0.0
    )
    bess_charge_energy = float(hourly["bess_charge_power"].sum() * dt_hours)
    final_bess_energy = float(hourly["bess_energy_end"].iloc[-1]) if len(hourly) else initial_bess_energy
    bess_loss_energy = bess_charge_energy - bess_discharge_to_load - (final_bess_energy - initial_bess_energy)
    if abs(bess_loss_energy) < 1e-9:
        bess_loss_energy = 0.0

    self_use_rate = safe_divide(self_use_energy, total_renewable_generation)
    green_load_rate = safe_divide(self_use_energy, total_load_energy)
    export_rate = safe_divide(grid_export_energy, total_renewable_generation)
    curtail_rate = safe_divide(curtail_energy, total_renewable_generation)
    export_cap_energy = total_renewable_generation * policy.export_rate_max
    annual_equivalent_cycles = safe_divide(bess_discharge_to_load, scenario.bess_energy)
    replacement_year = (
        bess_params.cycle_life / annual_equivalent_cycles if annual_equivalent_cycles > 0 else math.inf
    )
    max_grid_import_power = float(hourly["grid_import_power"].max()) if len(hourly) else 0.0
    max_grid_export_power = float(hourly["grid_export_power"].max()) if len(hourly) else 0.0
    final_soc = float(hourly["soc_end"].iloc[-1]) if len(hourly) else 0.0

    pass_policy, fail_reasons = evaluate_policy(
        self_use_rate=self_use_rate,
        green_load_rate=green_load_rate,
        export_rate=export_rate,
        grid_export_energy=grid_export_energy,
        max_grid_export_power=max_grid_export_power,
        exchange_import_shortfall_energy=exchange_import_shortfall_energy,
        policy=policy,
    )

    return {
        "scenario_id": scenario.scenario_id,
        "pv_capacity": scenario.pv_capacity,
        "wind_capacity": scenario.wind_capacity,
        "bess_power": scenario.bess_power,
        "bess_energy": scenario.bess_energy,
        "bess_duration": scenario.bess_duration,
        "bess_c_rate": scenario.bess_c_rate,
        "total_load_energy": total_load_energy,
        "total_renewable_generation": total_renewable_generation,
        "pv_station_use_energy": pv_station_use_energy,
        "wind_station_use_energy": wind_station_use_energy,
        "station_use_energy": station_use_energy,
        "direct_self_use_energy": direct_self_use_energy,
        "bess_discharge_to_load": bess_discharge_to_load,
        "self_use_energy": self_use_energy,
        "grid_import_energy": grid_import_energy,
        "grid_import_rate": grid_import_rate,
        "grid_export_energy": grid_export_energy,
        "export_cap_energy": export_cap_energy,
        "curtail_energy": curtail_energy,
        "curtail_due_to_export_cap_energy": curtail_due_to_export_cap_energy,
        "curtail_due_to_exchange_limit_energy": curtail_due_to_exchange_limit_energy,
        "exchange_import_shortfall_energy": exchange_import_shortfall_energy,
        "bess_charge_energy": bess_charge_energy,
        "bess_loss_energy": bess_loss_energy,
        "self_use_rate": self_use_rate,
        "green_load_rate": green_load_rate,
        "export_rate": export_rate,
        "curtail_rate": curtail_rate,
        "annual_equivalent_cycles": annual_equivalent_cycles,
        "replacement_year": replacement_year,
        "max_grid_import_power": max_grid_import_power,
        "max_grid_export_power": max_grid_export_power,
        "grid_exchange_power_limit": policy.grid_exchange_power_limit,
        "final_soc": final_soc,
        "export_control_mode": policy.export_control_mode,
        "pass_policy": pass_policy,
        "fail_reasons": fail_reasons,
    }
