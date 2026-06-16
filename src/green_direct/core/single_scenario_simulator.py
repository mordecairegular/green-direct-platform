"""Single scenario simulator."""

from __future__ import annotations

import numpy as np
import pandas as pd

from green_direct.core.bess_dispatch import (
    DispatchStrategy,
    dispatch_hour_values_with_limits,
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

HOURLY_NUMERIC_LEDGER_COLUMNS = [
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

_SHARED_EMPTY_HOURLY_DETAIL = pd.DataFrame(columns=HOURLY_LEDGER_COLUMNS)


def _empty_hourly_detail(*, shared: bool) -> pd.DataFrame:
    if shared:
        return _SHARED_EMPTY_HOURLY_DETAIL
    return pd.DataFrame(columns=HOURLY_LEDGER_COLUMNS)


def _zero_close_hourly_arrays(data: dict[str, object]) -> None:
    """Normalize tiny float artifacts before pandas DataFrame construction."""

    for column in HOURLY_NUMERIC_LEDGER_COLUMNS:
        values = data[column]
        if isinstance(values, np.ndarray) and np.issubdtype(values.dtype, np.floating):
            values[np.isclose(values, 0.0)] = 0.0


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


def _run_no_bess_summary_only(
    *,
    load_values: np.ndarray,
    pv_pu_values: np.ndarray,
    wind_pu_values: np.ndarray,
    scenario: Scenario,
    bess: BessParams,
    policy: PolicyParams,
    dt_hours: float,
    dt_inverse: float,
    annual_export_cap: float | None,
    export_limit_energy: float,
    exchange_limit_energy: float,
    total_renewable_generation: float,
) -> dict[str, object]:
    """Vectorized summary-only path for scenarios with no SOC state."""

    values = _no_bess_dispatch_arrays(
        load_values=load_values,
        pv_pu_values=pv_pu_values,
        wind_pu_values=wind_pu_values,
        pv_capacity=scenario.pv_capacity,
        wind_capacity=scenario.wind_capacity,
        policy=policy,
        dt_hours=dt_hours,
        annual_export_cap=annual_export_cap,
        export_limit_energy=export_limit_energy,
        exchange_limit_energy=exchange_limit_energy,
    )

    return calculate_summary_from_values(
        scenario,
        bess,
        policy,
        total_load_energy=float(values["load_energy"].sum()),
        total_renewable_generation=total_renewable_generation,
        pv_station_use_energy=float(values["pv_station_use_power"].sum() * dt_hours),
        wind_station_use_energy=float(values["wind_station_use_power"].sum() * dt_hours),
        direct_self_use_energy=float(values["direct_self_use"].sum()),
        bess_discharge_to_load=0.0,
        grid_import_energy=float(values["grid_import"].sum()),
        grid_export_energy=float(values["grid_export"].sum()),
        curtail_energy=float(values["curtail"].sum()),
        curtail_due_to_export_cap_energy=float(values["curtail_due_to_export_cap"].sum()),
        curtail_due_to_exchange_limit_energy=float(values["curtail_due_to_exchange_limit"].sum()),
        exchange_import_shortfall_energy=float(values["exchange_import_shortfall"].sum()),
        bess_charge_energy=0.0,
        final_bess_energy=0.0,
        initial_bess_energy=0.0,
        max_grid_import_power=(
            float(values["grid_import"].max() * dt_inverse) if len(values["grid_import"]) else 0.0
        ),
        max_grid_export_power=(
            float(values["grid_export"].max() * dt_inverse) if len(values["grid_export"]) else 0.0
        ),
        final_soc=0.0,
    )


def _no_bess_dispatch_arrays(
    *,
    load_values: np.ndarray,
    pv_pu_values: np.ndarray,
    wind_pu_values: np.ndarray,
    pv_capacity: float,
    wind_capacity: float,
    policy: PolicyParams,
    dt_hours: float,
    annual_export_cap: float | None,
    export_limit_energy: float,
    exchange_limit_energy: float,
) -> dict[str, np.ndarray]:
    """Return no-BESS dispatch arrays for summary and ledger construction."""

    pv_power_values = pv_pu_values * pv_capacity
    wind_power_values = wind_pu_values * wind_capacity
    pv_generation_values = np.maximum(pv_power_values, 0.0)
    wind_generation_values = np.maximum(wind_power_values, 0.0)
    renewable_generation_values = pv_generation_values + wind_generation_values
    pv_station_use_values = np.maximum(-pv_power_values, 0.0)
    wind_station_use_values = np.maximum(-wind_power_values, 0.0)
    station_use_values = pv_station_use_values + wind_station_use_values
    net_renewable_values = renewable_generation_values - station_use_values
    renewable_power_values = np.maximum(net_renewable_values, 0.0)
    station_use_deficit_values = np.maximum(-net_renewable_values, 0.0)

    load_energy_values = load_values * dt_hours
    dispatch_load_energy_values = (load_values + station_use_deficit_values) * dt_hours
    renewable_energy_values = renewable_power_values * dt_hours
    surplus_mask = renewable_energy_values >= dispatch_load_energy_values
    surplus_values = np.where(surplus_mask, renewable_energy_values - dispatch_load_energy_values, 0.0)
    deficit_values = np.where(surplus_mask, 0.0, dispatch_load_energy_values - renewable_energy_values)
    direct_self_use_values = np.where(surplus_mask, dispatch_load_energy_values, renewable_energy_values)

    export_limit = min(export_limit_energy, exchange_limit_energy)
    if policy.allow_export:
        export_before_cap_values = np.where(surplus_mask, np.minimum(surplus_values, export_limit), 0.0)
    else:
        export_before_cap_values = np.zeros_like(surplus_values)
    if annual_export_cap is None:
        grid_export_values = export_before_cap_values
    else:
        cumulative_export_before = np.cumsum(export_before_cap_values) - export_before_cap_values
        remaining_export_cap = np.maximum(annual_export_cap - cumulative_export_before, 0.0)
        grid_export_values = np.minimum(export_before_cap_values, remaining_export_cap)

    grid_import_values = np.minimum(deficit_values, exchange_limit_energy)
    curtail_values = surplus_values - grid_export_values
    curtail_due_to_export_cap_values = np.maximum(export_before_cap_values - grid_export_values, 0.0)
    curtail_due_to_exchange_limit_values = np.where(
        surplus_mask,
        np.maximum(surplus_values - np.minimum(surplus_values, exchange_limit_energy), 0.0),
        0.0,
    )
    exchange_import_shortfall_values = deficit_values - grid_import_values

    return {
        "load_energy": load_energy_values,
        "pv_power": pv_power_values,
        "wind_power": wind_power_values,
        "pv_generation_power": pv_generation_values,
        "wind_generation_power": wind_generation_values,
        "renewable_generation_power": renewable_generation_values,
        "pv_station_use_power": pv_station_use_values,
        "wind_station_use_power": wind_station_use_values,
        "station_use_power": station_use_values,
        "renewable_power": renewable_power_values,
        "direct_self_use": direct_self_use_values,
        "grid_import": grid_import_values,
        "grid_export": grid_export_values,
        "curtail": curtail_values,
        "curtail_due_to_export_cap": curtail_due_to_export_cap_values,
        "curtail_due_to_exchange_limit": curtail_due_to_exchange_limit_values,
        "exchange_import_shortfall": exchange_import_shortfall_values,
        "surplus": surplus_values,
        "surplus_mask": surplus_mask,
        "renewable_energy": renewable_energy_values,
    }


def _no_bess_hour_case_values(values: dict[str, np.ndarray]) -> np.ndarray:
    hour_case_values = np.full(len(values["load_energy"]), "GEN_SHORT_GRID_IMPORT", dtype=object)
    surplus_mask = values["surplus_mask"].astype(bool)
    balanced_mask = surplus_mask & (np.abs(values["surplus"]) <= 1e-12)
    direct_export_mask = surplus_mask & ~balanced_mask & (values["grid_export"] > 0) & (values["curtail"] == 0)
    surplus_curtail_mask = surplus_mask & ~balanced_mask & ~direct_export_mask
    no_renewable_mask = ~surplus_mask & (values["renewable_energy"] == 0)

    hour_case_values[balanced_mask] = "GEN_BALANCED"
    hour_case_values[direct_export_mask] = "GEN_SURPLUS_DIRECT_EXPORT"
    hour_case_values[surplus_curtail_mask] = "GEN_SURPLUS_CURTAIL"
    hour_case_values[no_renewable_mask] = "NO_RENEWABLE_GRID_IMPORT"
    return hour_case_values


def _run_no_bess_hourly_detail(
    *,
    timestamps: np.ndarray,
    load_values: np.ndarray,
    pv_pu_values: np.ndarray,
    wind_pu_values: np.ndarray,
    scenario: Scenario,
    policy: PolicyParams,
    dt_hours: float,
    dt_inverse: float,
    annual_export_cap: float | None,
    export_limit_energy: float,
    exchange_limit_energy: float,
) -> pd.DataFrame:
    """Vectorized hourly ledger path for scenarios with no SOC state."""

    values = _no_bess_dispatch_arrays(
        load_values=load_values,
        pv_pu_values=pv_pu_values,
        wind_pu_values=wind_pu_values,
        pv_capacity=scenario.pv_capacity,
        wind_capacity=scenario.wind_capacity,
        policy=policy,
        dt_hours=dt_hours,
        annual_export_cap=annual_export_cap,
        export_limit_energy=export_limit_energy,
        exchange_limit_energy=exchange_limit_energy,
    )
    n = len(load_values)
    data: dict[str, object] = {
        "scenario_id": np.full(n, scenario.scenario_id, dtype=object),
        "timestamp": timestamps,
        "hour_index": np.arange(n),
        "load_power": load_values.copy(),
        "pv_power": values["pv_power"],
        "wind_power": values["wind_power"],
        "pv_generation_power": values["pv_generation_power"],
        "wind_generation_power": values["wind_generation_power"],
        "renewable_generation_power": values["renewable_generation_power"],
        "pv_station_use_power": values["pv_station_use_power"],
        "wind_station_use_power": values["wind_station_use_power"],
        "station_use_power": values["station_use_power"],
        "renewable_power": values["renewable_power"],
        "direct_self_use_power": values["direct_self_use"] * dt_inverse,
        "bess_charge_power": np.zeros(n),
        "bess_discharge_power": np.zeros(n),
        "grid_import_power": values["grid_import"] * dt_inverse,
        "grid_export_power": values["grid_export"] * dt_inverse,
        "curtail_power": values["curtail"] * dt_inverse,
        "curtail_due_to_export_cap_power": values["curtail_due_to_export_cap"] * dt_inverse,
        "curtail_due_to_exchange_limit_power": values["curtail_due_to_exchange_limit"] * dt_inverse,
        "exchange_import_shortfall_power": values["exchange_import_shortfall"] * dt_inverse,
        "soc_start": np.zeros(n),
        "soc_end": np.zeros(n),
        "bess_energy_start": np.zeros(n),
        "bess_energy_end": np.zeros(n),
        "hour_case": _no_bess_hour_case_values(values),
    }
    _zero_close_hourly_arrays(data)
    return pd.DataFrame(data, columns=HOURLY_LEDGER_COLUMNS)


def run_single_scenario(
    curves: pd.DataFrame,
    scenario: Scenario,
    *,
    bess_params: BessParams | None = None,
    policy_params: PolicyParams | None = None,
    strategy: DispatchStrategy | str | None = DispatchStrategy.GRID_CONNECTED_RENEWABLE_FIRST_GREEDY,
    dt_hours: float = 1.0,
    retain_hourly_detail: bool = True,
    collect_diagnostics: bool = True,
    _share_empty_hourly_detail: bool = False,
) -> ScenarioResult:
    """Run hourly energy-balance simulation for one scenario."""

    bess = bess_params or BessParams()
    policy = policy_params or PolicyParams()
    dispatch_strategy = normalize_dispatch_strategy(strategy)
    if dispatch_strategy is not DispatchStrategy.GRID_CONNECTED_RENEWABLE_FIRST_GREEDY:
        raise ValueError(f"Unsupported dispatch strategy: {dispatch_strategy.value}")
    _validate_inputs(curves, scenario, bess, dt_hours)
    diagnostics = (
        collect_single_scenario_input_diagnostics(
            curves,
            scenario,
            bess,
            policy,
            dt_hours=dt_hours,
            strategy=dispatch_strategy,
        )
        if collect_diagnostics
        else InputDiagnostics()
    )

    pv_capacity = scenario.pv_capacity
    wind_capacity = scenario.wind_capacity
    bess_power = scenario.bess_power
    scenario_bess_energy = scenario.bess_energy
    has_bess = scenario_bess_energy > 0 and bess_power > 0
    dt_inverse = 1.0 / dt_hours
    allow_export = policy.allow_export
    export_limit_energy = (
        float("inf") if policy.export_power_max is None else max(policy.export_power_max * dt_hours, 0.0)
    )
    exchange_limit_energy = (
        float("inf")
        if policy.grid_exchange_power_limit is None
        else max(policy.grid_exchange_power_limit * dt_hours, 0.0)
    )
    bess_power_energy_limit = bess_power * dt_hours
    bess_soc_min_energy = bess.soc_min * scenario_bess_energy
    bess_soc_max_energy = bess.soc_max * scenario_bess_energy
    eta_charge = bess.eta_charge
    eta_discharge = bess.eta_discharge

    if has_bess:
        bess_energy = bess.soc_initial * scenario_bess_energy
        soc = bess.soc_initial
    else:
        bess_energy = 0.0
        soc = 0.0
    initial_bess_energy = bess_energy

    n = len(curves)
    timestamps = curves["timestamp"].to_numpy()
    load_values = curves["load_power"].to_numpy(dtype=float)
    pv_pu_values = curves["pv_pu"].to_numpy(dtype=float)
    wind_pu_values = curves["wind_pu"].to_numpy(dtype=float)
    total_renewable_generation = float(
        (
            pv_capacity * np.maximum(pv_pu_values, 0.0).sum()
            + wind_capacity * np.maximum(wind_pu_values, 0.0).sum()
        )
        * dt_hours
    )
    annual_export_cap = (
        total_renewable_generation * policy.export_rate_max
        if policy.export_control_mode == "annual_cap_runtime"
        else None
    )
    if not has_bess and not retain_hourly_detail:
        summary = _run_no_bess_summary_only(
            load_values=load_values,
            pv_pu_values=pv_pu_values,
            wind_pu_values=wind_pu_values,
            scenario=scenario,
            bess=bess,
            policy=policy,
            dt_hours=dt_hours,
            dt_inverse=dt_inverse,
            annual_export_cap=annual_export_cap,
            export_limit_energy=export_limit_energy,
            exchange_limit_energy=exchange_limit_energy,
            total_renewable_generation=total_renewable_generation,
        )
        summary["dispatch_strategy"] = dispatch_strategy.value
        return ScenarioResult(
            summary=summary,
            hourly_detail=_empty_hourly_detail(shared=_share_empty_hourly_detail),
            warnings=[],
            diagnostics=diagnostics,
        )

    if not has_bess and retain_hourly_detail:
        hourly = _run_no_bess_hourly_detail(
            timestamps=timestamps,
            load_values=load_values,
            pv_pu_values=pv_pu_values,
            wind_pu_values=wind_pu_values,
            scenario=scenario,
            policy=policy,
            dt_hours=dt_hours,
            dt_inverse=dt_inverse,
            annual_export_cap=annual_export_cap,
            export_limit_energy=export_limit_energy,
            exchange_limit_energy=exchange_limit_energy,
        )
        summary = calculate_summary(
            hourly,
            scenario,
            bess,
            policy,
            initial_bess_energy=initial_bess_energy,
            dt_hours=dt_hours,
        )
        summary["dispatch_strategy"] = dispatch_strategy.value
        return ScenarioResult(summary=summary, hourly_detail=hourly, warnings=[], diagnostics=diagnostics)

    cumulative_export = 0.0
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
        pv_power = pv_pu_values[idx] * pv_capacity
        wind_power = wind_pu_values[idx] * wind_capacity
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

        (
            direct_self_use,
            step_bess_charge,
            step_bess_discharge,
            step_grid_import,
            step_grid_export,
            step_curtail,
            step_curtail_due_to_export_cap,
            step_curtail_due_to_exchange_limit,
            step_exchange_import_shortfall,
            step_bess_energy_end,
            step_hour_case,
        ) = dispatch_hour_values_with_limits(
            load_energy=dispatch_load_energy,
            renewable_energy=renewable_energy,
            has_bess=has_bess,
            bess_power_energy_limit=bess_power_energy_limit,
            bess_energy_start=bess_energy_start,
            bess_soc_min_energy=bess_soc_min_energy,
            bess_soc_max_energy=bess_soc_max_energy,
            eta_charge=eta_charge,
            eta_discharge=eta_discharge,
            allow_export=allow_export,
            export_limit_energy=export_limit_energy,
            remaining_export_cap=remaining_cap,
            exchange_limit_energy=exchange_limit_energy,
        )
        bess_energy = step_bess_energy_end
        if has_bess:
            soc = bess_energy / scenario_bess_energy
            soc = min(max(soc, bess.soc_min - 1e-12), bess.soc_max + 1e-12)
        else:
            soc = 0.0
        cumulative_export += step_grid_export

        if data is None:
            total_load_energy += load_energy
            pv_station_use_energy += pv_station_use_power * dt_hours
            wind_station_use_energy += wind_station_use_power * dt_hours
            direct_self_use_energy += direct_self_use
            bess_discharge_to_load += step_bess_discharge
            grid_import_energy += step_grid_import
            grid_export_energy += step_grid_export
            curtail_energy += step_curtail
            curtail_due_to_export_cap_energy += step_curtail_due_to_export_cap
            curtail_due_to_exchange_limit_energy += step_curtail_due_to_exchange_limit
            exchange_import_shortfall_energy += step_exchange_import_shortfall
            bess_charge_energy += step_bess_charge
            max_grid_import_power = max(max_grid_import_power, step_grid_import * dt_inverse)
            max_grid_export_power = max(max_grid_export_power, step_grid_export * dt_inverse)

        if data is not None:
            data["pv_power"][idx] = pv_power
            data["wind_power"][idx] = wind_power
            data["pv_generation_power"][idx] = pv_generation_power
            data["wind_generation_power"][idx] = wind_generation_power
            data["renewable_generation_power"][idx] = renewable_generation_power
            data["pv_station_use_power"][idx] = pv_station_use_power
            data["wind_station_use_power"][idx] = wind_station_use_power
            data["station_use_power"][idx] = station_use_power
            data["renewable_power"][idx] = renewable_energy * dt_inverse
            data["direct_self_use_power"][idx] = direct_self_use * dt_inverse
            data["bess_charge_power"][idx] = step_bess_charge * dt_inverse
            data["bess_discharge_power"][idx] = step_bess_discharge * dt_inverse
            data["grid_import_power"][idx] = step_grid_import * dt_inverse
            data["grid_export_power"][idx] = step_grid_export * dt_inverse
            data["curtail_power"][idx] = step_curtail * dt_inverse
            data["curtail_due_to_export_cap_power"][idx] = step_curtail_due_to_export_cap * dt_inverse
            data["curtail_due_to_exchange_limit_power"][idx] = step_curtail_due_to_exchange_limit * dt_inverse
            data["exchange_import_shortfall_power"][idx] = step_exchange_import_shortfall * dt_inverse
            data["soc_start"][idx] = soc_start
            data["soc_end"][idx] = soc
            data["bess_energy_start"][idx] = bess_energy_start
            data["bess_energy_end"][idx] = bess_energy
            data["hour_case"][idx] = step_hour_case

    if data is not None:
        _zero_close_hourly_arrays(data)
        hourly = pd.DataFrame(data, columns=HOURLY_LEDGER_COLUMNS)
        summary = calculate_summary(
            hourly,
            scenario,
            bess,
            policy,
            initial_bess_energy=initial_bess_energy,
            dt_hours=dt_hours,
        )
    else:
        hourly = _empty_hourly_detail(shared=_share_empty_hourly_detail)
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
