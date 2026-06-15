"""Single scenario simulator."""

from __future__ import annotations

import numpy as np
import pandas as pd

from green_direct.core.bess_dispatch import (
    DispatchStrategy,
    dispatch_hour_with_strategy,
    normalize_dispatch_strategy,
)
from green_direct.core.metrics import calculate_summary, calculate_summary_from_values
from green_direct.models.diagnostics import DiagnosticSeverity, InputDiagnostics
from green_direct.models.params import BessParams, PolicyParams
from green_direct.models.results import ScenarioResult
from green_direct.models.scenario import Scenario


# V0.1 physical HourlyEnergyLedger implementation.
#
# The hourly_detail DataFrame is the technical simulation's hourly fact table.
# Policy, economy, chart, and report layers should read these fields instead of
# recomputing core dispatch, SOC, grid exchange, export, or curtailment logic.
HOURLY_LEDGER_COLUMNS = [
    "scenario_id",
    "timestamp",
    "hour_index",
    "load_power",
    "pv_power",
    "wind_power",
    "pv_generation_power",
    "wind_generation_power",
    "renewable_generation_power",
    "pv_station_use_power",
    "wind_station_use_power",
    "station_use_power",
    "renewable_power",
    "direct_self_use_power",
    "bess_charge_power",
    "bess_discharge_power",
    "grid_import_power",
    "grid_export_power",
    "curtail_power",
    "curtail_due_to_export_cap_power",
    "curtail_due_to_exchange_limit_power",
    "exchange_import_shortfall_power",
    "soc_start",
    "soc_end",
    "bess_energy_start",
    "bess_energy_end",
    "hour_case",
]

# Backward-compatible alias for existing export/tests/downstream imports.
HOURLY_COLUMNS = HOURLY_LEDGER_COLUMNS


def collect_single_scenario_input_diagnostics(
    curves: pd.DataFrame,
    scenario: Scenario,
    bess_params: BessParams,
    policy_params: PolicyParams,
    *,
    dt_hours: float,
    strategy: DispatchStrategy | str | None,
) -> InputDiagnostics:
    diagnostics = InputDiagnostics()
    required = {"timestamp", "load_power", "pv_pu", "wind_pu"}
    missing = required - set(curves.columns)
    if missing:
        diagnostics.add(
            DiagnosticSeverity.ERROR,
            "single_scenario_input",
            "MISSING_CURVE_COLUMNS",
            f"Missing required curve columns: {', '.join(sorted(missing))}",
            location="curves",
        )
    if dt_hours <= 0:
        diagnostics.add(
            DiagnosticSeverity.ERROR,
            "single_scenario_input",
            "INVALID_DT_HOURS",
            "dt_hours must be greater than 0.",
            location="dt_hours",
        )
    for name in ["pv_capacity", "wind_capacity", "bess_power", "bess_energy"]:
        if getattr(scenario, name) < 0:
            diagnostics.add(
                DiagnosticSeverity.ERROR,
                "single_scenario_input",
                "NEGATIVE_SCENARIO_CAPACITY",
                f"{name} cannot be negative.",
                location=name,
            )
    if not (0 <= bess_params.soc_min <= bess_params.soc_initial <= bess_params.soc_max <= 1):
        diagnostics.add(
            DiagnosticSeverity.ERROR,
            "single_scenario_input",
            "INVALID_SOC_PARAMETERS",
            "SOC parameters must satisfy 0 <= soc_min <= soc_initial <= soc_max <= 1.",
            location="bess_params",
        )
    if bess_params.eta_charge <= 0 or bess_params.eta_discharge <= 0:
        diagnostics.add(
            DiagnosticSeverity.ERROR,
            "single_scenario_input",
            "INVALID_BESS_EFFICIENCY",
            "BESS charge and discharge efficiencies must be greater than 0.",
            location="bess_params",
        )
    if not (0 <= policy_params.export_rate_max <= 1):
        diagnostics.add(
            DiagnosticSeverity.WARNING,
            "policy_params",
            "EXPORT_RATE_MAX_OUT_OF_NORMAL_RANGE",
            "export_rate_max should normally be between 0 and 1.",
            location="policy_params.export_rate_max",
        )
    if policy_params.grid_exchange_power_limit is not None and policy_params.grid_exchange_power_limit < 0:
        diagnostics.add(
            DiagnosticSeverity.WARNING,
            "policy_params",
            "NEGATIVE_GRID_EXCHANGE_POWER_LIMIT",
            "grid_exchange_power_limit is negative; dispatch clamps usable limits to no less than 0.",
            location="policy_params.grid_exchange_power_limit",
        )
    if policy_params.export_control_mode not in {"annual_cap_runtime", "post_check"}:
        diagnostics.add(
            DiagnosticSeverity.WARNING,
            "policy_params",
            "UNKNOWN_EXPORT_CONTROL_MODE",
            "Unknown export_control_mode; V0.1 explicitly supports annual_cap_runtime and post_check.",
            location="policy_params.export_control_mode",
        )
    normalized_strategy = normalize_dispatch_strategy(strategy)
    diagnostics.add(
        DiagnosticSeverity.INFO,
        "dispatch",
        "DISPATCH_STRATEGY_SELECTED",
        f"dispatch_strategy={normalized_strategy.value}",
        location="strategy",
    )
    return diagnostics
def _validate_inputs(curves: pd.DataFrame, scenario: Scenario, bess_params: BessParams, dt_hours: float) -> None:
    required = {"timestamp", "load_power", "pv_pu", "wind_pu"}
    missing = required - set(curves.columns)
    if missing:
        raise ValueError(f"Missing required curve columns: {', '.join(sorted(missing))}")
    if dt_hours <= 0:
        raise ValueError("dt_hours must be greater than 0.")
    for name in ["pv_capacity", "wind_capacity", "bess_power", "bess_energy"]:
        if getattr(scenario, name) < 0:
            raise ValueError(f"{name} cannot be negative.")
    if not (0 <= bess_params.soc_min <= bess_params.soc_initial <= bess_params.soc_max <= 1):
        raise ValueError("SOC parameters must satisfy 0 <= soc_min <= soc_initial <= soc_max <= 1.")
    if bess_params.eta_charge <= 0 or bess_params.eta_discharge <= 0:
        raise ValueError("BESS charge and discharge efficiencies must be greater than 0.")
def run_single_scenario(
    curves: pd.DataFrame,
    scenario: Scenario,
    *,
    bess_params: BessParams | None = None,
    policy_params: PolicyParams | None = None,
    strategy: DispatchStrategy | str | None = DispatchStrategy.GRID_CONNECTED_RENEWABLE_FIRST_GREEDY,
    dt_hours: float = 1.0,
    retain_hourly_detail: bool = True,
) -> ScenarioResult:
    """Run hourly energy-balance simulation for one scenario."""

    bess = bess_params or BessParams()
    policy = policy_params or PolicyParams()
    dispatch_strategy = normalize_dispatch_strategy(strategy)
    _validate_inputs(curves, scenario, bess, dt_hours)
    diagnostics = collect_single_scenario_input_diagnostics(
        curves,
        scenario,
        bess,
        policy,
        dt_hours=dt_hours,
        strategy=dispatch_strategy,
    )

    if scenario.bess_energy > 0 and scenario.bess_power > 0:
        bess_energy = bess.soc_initial * scenario.bess_energy
        soc = bess.soc_initial
    else:
        bess_energy = 0.0
        soc = 0.0
    initial_bess_energy = bess_energy

    pv_raw_power = curves["pv_pu"] * scenario.pv_capacity
    wind_raw_power = curves["wind_pu"] * scenario.wind_capacity
    total_renewable_generation = float((pv_raw_power.clip(lower=0) + wind_raw_power.clip(lower=0)).sum() * dt_hours)
    annual_export_cap = (
        total_renewable_generation * policy.export_rate_max
        if policy.export_control_mode == "annual_cap_runtime"
        else None
    )
    cumulative_export = 0.0
    n = len(curves)
    timestamps = curves["timestamp"].to_numpy()
    load_values = curves["load_power"].to_numpy(dtype=float)
    pv_pu_values = curves["pv_pu"].to_numpy(dtype=float)
    wind_pu_values = curves["wind_pu"].to_numpy(dtype=float)
    data: dict[str, object] | None = None
    if retain_hourly_detail:
        data = {
            "scenario_id": np.full(n, scenario.scenario_id, dtype=object),
            "timestamp": timestamps,
            "hour_index": np.arange(n),
            "load_power": load_values.copy(),
            "pv_power": np.zeros(n),
            "wind_power": np.zeros(n),
            "pv_generation_power": np.zeros(n),
            "wind_generation_power": np.zeros(n),
            "renewable_generation_power": np.zeros(n),
            "pv_station_use_power": np.zeros(n),
            "wind_station_use_power": np.zeros(n),
            "station_use_power": np.zeros(n),
            "renewable_power": np.zeros(n),
            "direct_self_use_power": np.zeros(n),
            "bess_charge_power": np.zeros(n),
            "bess_discharge_power": np.zeros(n),
            "grid_import_power": np.zeros(n),
            "grid_export_power": np.zeros(n),
            "curtail_power": np.zeros(n),
            "curtail_due_to_export_cap_power": np.zeros(n),
            "curtail_due_to_exchange_limit_power": np.zeros(n),
            "exchange_import_shortfall_power": np.zeros(n),
            "soc_start": np.zeros(n),
            "soc_end": np.zeros(n),
            "bess_energy_start": np.zeros(n),
            "bess_energy_end": np.zeros(n),
            "hour_case": np.empty(n, dtype=object),
        }

    total_load_energy = 0.0
    pv_station_use_energy = 0.0
    wind_station_use_energy = 0.0
    direct_self_use_energy = 0.0
    bess_discharge_to_load = 0.0
    grid_import_energy = 0.0
    grid_export_energy = 0.0
    curtail_energy = 0.0
    curtail_due_to_export_cap_energy = 0.0
    curtail_due_to_exchange_limit_energy = 0.0
    exchange_import_shortfall_energy = 0.0
    bess_charge_energy = 0.0
    max_grid_import_power = 0.0
    max_grid_export_power = 0.0

    for idx in range(n):
        load_power = load_values[idx]
        pv_power = pv_pu_values[idx] * scenario.pv_capacity
        wind_power = wind_pu_values[idx] * scenario.wind_capacity
        pv_generation_power = max(pv_power, 0.0)
        wind_generation_power = max(wind_power, 0.0)
        renewable_generation_power = pv_generation_power + wind_generation_power
        pv_station_use_power = max(-pv_power, 0.0)
        wind_station_use_power = max(-wind_power, 0.0)
        station_use_power = pv_station_use_power + wind_station_use_power
        net_renewable_power = renewable_generation_power - station_use_power
        renewable_power = max(net_renewable_power, 0.0)
        station_use_deficit_power = max(-net_renewable_power, 0.0)
        load_energy = load_power * dt_hours
        renewable_energy = renewable_power * dt_hours
        dispatch_load_energy = (load_power + station_use_deficit_power) * dt_hours
        soc_start = soc
        bess_energy_start = bess_energy
        remaining_cap = None
        if annual_export_cap is not None:
            remaining_cap = annual_export_cap - cumulative_export

        step = dispatch_hour_with_strategy(
            strategy=dispatch_strategy,
            load_energy=dispatch_load_energy,
            renewable_energy=renewable_energy,
            bess_power=scenario.bess_power,
            bess_energy=scenario.bess_energy,
            bess_energy_start=bess_energy_start,
            bess_params=bess,
            dt_hours=dt_hours,
            allow_export=policy.allow_export,
            export_power_max=policy.export_power_max,
            remaining_export_cap=remaining_cap,
            grid_exchange_power_limit=policy.grid_exchange_power_limit,
        )
        bess_energy = step.bess_energy_end
        if scenario.bess_energy > 0 and scenario.bess_power > 0:
            soc = bess_energy / scenario.bess_energy
            soc = min(max(soc, bess.soc_min - 1e-12), bess.soc_max + 1e-12)
        else:
            soc = 0.0
        cumulative_export += step.grid_export

        if data is None:
            total_load_energy += load_energy
            pv_station_use_energy += pv_station_use_power * dt_hours
            wind_station_use_energy += wind_station_use_power * dt_hours
            direct_self_use_energy += step.direct_self_use
            bess_discharge_to_load += step.bess_discharge
            grid_import_energy += step.grid_import
            grid_export_energy += step.grid_export
            curtail_energy += step.curtail
            curtail_due_to_export_cap_energy += step.curtail_due_to_export_cap
            curtail_due_to_exchange_limit_energy += step.curtail_due_to_exchange_limit
            exchange_import_shortfall_energy += step.exchange_import_shortfall
            bess_charge_energy += step.bess_charge
            max_grid_import_power = max(max_grid_import_power, step.grid_import / dt_hours)
            max_grid_export_power = max(max_grid_export_power, step.grid_export / dt_hours)

        if data is not None:
            data["pv_power"][idx] = pv_power
            data["wind_power"][idx] = wind_power
            data["pv_generation_power"][idx] = pv_generation_power
            data["wind_generation_power"][idx] = wind_generation_power
            data["renewable_generation_power"][idx] = renewable_generation_power
            data["pv_station_use_power"][idx] = pv_station_use_power
            data["wind_station_use_power"][idx] = wind_station_use_power
            data["station_use_power"][idx] = station_use_power
            data["renewable_power"][idx] = renewable_energy / dt_hours
            data["direct_self_use_power"][idx] = step.direct_self_use / dt_hours
            data["bess_charge_power"][idx] = step.bess_charge / dt_hours
            data["bess_discharge_power"][idx] = step.bess_discharge / dt_hours
            data["grid_import_power"][idx] = step.grid_import / dt_hours
            data["grid_export_power"][idx] = step.grid_export / dt_hours
            data["curtail_power"][idx] = step.curtail / dt_hours
            data["curtail_due_to_export_cap_power"][idx] = step.curtail_due_to_export_cap / dt_hours
            data["curtail_due_to_exchange_limit_power"][idx] = step.curtail_due_to_exchange_limit / dt_hours
            data["exchange_import_shortfall_power"][idx] = step.exchange_import_shortfall / dt_hours
            data["soc_start"][idx] = soc_start
            data["soc_end"][idx] = soc
            data["bess_energy_start"][idx] = bess_energy_start
            data["bess_energy_end"][idx] = bess_energy
            data["hour_case"][idx] = step.hour_case

    if data is not None:
        hourly = pd.DataFrame(data, columns=HOURLY_LEDGER_COLUMNS)
        if not hourly.empty:
            numeric_columns = [
                "load_power",
                "pv_power",
                "wind_power",
                "pv_generation_power",
                "wind_generation_power",
                "renewable_generation_power",
                "pv_station_use_power",
                "wind_station_use_power",
                "station_use_power",
                "renewable_power",
                "direct_self_use_power",
                "bess_charge_power",
                "bess_discharge_power",
                "grid_import_power",
                "grid_export_power",
                "curtail_power",
                "curtail_due_to_export_cap_power",
                "curtail_due_to_exchange_limit_power",
                "exchange_import_shortfall_power",
                "soc_start",
                "soc_end",
                "bess_energy_start",
                "bess_energy_end",
            ]
            hourly[numeric_columns] = hourly[numeric_columns].replace({-0.0: 0.0})
            hourly[numeric_columns] = hourly[numeric_columns].mask(np.isclose(hourly[numeric_columns], 0), 0.0)

        summary = calculate_summary(
            hourly,
            scenario,
            bess,
            policy,
            initial_bess_energy=initial_bess_energy,
            dt_hours=dt_hours,
        )
    else:
        hourly = pd.DataFrame(columns=HOURLY_LEDGER_COLUMNS)
        summary = calculate_summary_from_values(
            scenario,
            bess,
            policy,
            total_load_energy=total_load_energy,
            total_renewable_generation=total_renewable_generation,
            pv_station_use_energy=pv_station_use_energy,
            wind_station_use_energy=wind_station_use_energy,
            direct_self_use_energy=direct_self_use_energy,
            bess_discharge_to_load=bess_discharge_to_load,
            grid_import_energy=grid_import_energy,
            grid_export_energy=grid_export_energy,
            curtail_energy=curtail_energy,
            curtail_due_to_export_cap_energy=curtail_due_to_export_cap_energy,
            curtail_due_to_exchange_limit_energy=curtail_due_to_exchange_limit_energy,
            exchange_import_shortfall_energy=exchange_import_shortfall_energy,
            bess_charge_energy=bess_charge_energy,
            final_bess_energy=bess_energy,
            initial_bess_energy=initial_bess_energy,
            max_grid_import_power=max_grid_import_power,
            max_grid_export_power=max_grid_export_power,
            final_soc=soc,
        )
    summary["dispatch_strategy"] = dispatch_strategy.value
    return ScenarioResult(summary=summary, hourly_detail=hourly, warnings=[], diagnostics=diagnostics)
