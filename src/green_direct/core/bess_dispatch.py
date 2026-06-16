"""BESS dispatch helpers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from green_direct.models.params import BessParams


class DispatchStrategy(str, Enum):
    GRID_CONNECTED_RENEWABLE_FIRST_GREEDY = "GRID_CONNECTED_RENEWABLE_FIRST_GREEDY"


@dataclass(frozen=True)
class DispatchStep:
    direct_self_use: float
    bess_charge: float
    bess_discharge: float
    grid_import: float
    grid_export: float
    curtail: float
    curtail_due_to_export_cap: float
    curtail_due_to_exchange_limit: float
    exchange_import_shortfall: float
    bess_energy_end: float
    hour_case: str


DispatchStepValues = tuple[float, float, float, float, float, float, float, float, float, float, str]


def _has_bess(bess_power: float, bess_energy: float) -> bool:
    return bess_power > 0 and bess_energy > 0


def dispatch_bess_hour_values_with_limits(
    *,
    load_energy: float,
    renewable_energy: float,
    bess_power_energy_limit: float,
    bess_energy_start: float,
    bess_soc_min_energy: float,
    bess_soc_max_energy: float,
    eta_charge: float,
    eta_discharge: float,
    allow_export: bool,
    export_limit_energy: float,
    exchange_limit_energy: float,
    has_exchange_limit: bool | None = None,
    remaining_export_cap: float | None = None,
) -> DispatchStepValues:
    """Dispatch one BESS time step with precomputed scenario limits."""

    if has_exchange_limit is None:
        has_exchange_limit = exchange_limit_energy != float("inf")

    if renewable_energy >= load_energy:
        direct_self_use = load_energy
        surplus = renewable_energy - load_energy
        charge_space_input = max((bess_soc_max_energy - bess_energy_start) / eta_charge, 0.0)
        bess_charge = min(surplus, bess_power_energy_limit, charge_space_input)
        bess_energy_end = bess_energy_start + bess_charge * eta_charge

        surplus_after_charge = surplus - bess_charge
        export_limit = min(export_limit_energy, exchange_limit_energy) if has_exchange_limit else export_limit_energy
        export_before_annual_cap = min(surplus_after_charge, export_limit) if allow_export else 0.0
        if remaining_export_cap is not None:
            grid_export = min(export_before_annual_cap, max(remaining_export_cap, 0.0))
        else:
            grid_export = export_before_annual_cap
        curtail = surplus_after_charge - grid_export
        curtail_due_to_export_cap = max(export_before_annual_cap - grid_export, 0.0)
        curtail_due_to_exchange_limit = (
            max(surplus_after_charge - min(surplus_after_charge, exchange_limit_energy), 0.0)
            if has_exchange_limit
            else 0.0
        )
        grid_import = 0.0
        exchange_import_shortfall = 0.0
        bess_discharge = 0.0

        if abs(surplus) <= 1e-12:
            hour_case = "GEN_BALANCED"
        elif bess_charge > 0 and grid_export > 0 and curtail > 0:
            hour_case = "GEN_SURPLUS_CHARGE_EXPORT_CURTAIL"
        elif bess_charge > 0 and grid_export > 0:
            hour_case = "GEN_SURPLUS_CHARGE_EXPORT"
        elif bess_charge > 0:
            hour_case = "GEN_SURPLUS_CHARGE_BESS"
        elif grid_export > 0 and curtail == 0:
            hour_case = "GEN_SURPLUS_DIRECT_EXPORT"
        else:
            hour_case = "GEN_SURPLUS_CURTAIL"
    else:
        direct_self_use = renewable_energy
        deficit = load_energy - renewable_energy
        available_discharge = max((bess_energy_start - bess_soc_min_energy) * eta_discharge, 0.0)
        bess_discharge = min(deficit, bess_power_energy_limit, available_discharge)
        bess_energy_end = bess_energy_start - bess_discharge / eta_discharge

        raw_grid_import = deficit - bess_discharge
        if has_exchange_limit:
            grid_import = min(raw_grid_import, exchange_limit_energy)
            exchange_import_shortfall = raw_grid_import - grid_import
        else:
            grid_import = raw_grid_import
            exchange_import_shortfall = 0.0
        grid_export = 0.0
        curtail = 0.0
        curtail_due_to_export_cap = 0.0
        curtail_due_to_exchange_limit = 0.0
        bess_charge = 0.0
        if renewable_energy == 0 and bess_discharge == 0:
            hour_case = "NO_RENEWABLE_GRID_IMPORT"
        elif bess_discharge > 0 and grid_import > 0:
            hour_case = "GEN_SHORT_BESS_DISCHARGE_AND_GRID_IMPORT"
        elif bess_discharge > 0:
            hour_case = "GEN_SHORT_BESS_DISCHARGE"
        else:
            hour_case = "GEN_SHORT_GRID_IMPORT"

    return (
        max(direct_self_use, 0.0),
        max(bess_charge, 0.0),
        max(bess_discharge, 0.0),
        max(grid_import, 0.0),
        max(grid_export, 0.0),
        max(curtail, 0.0),
        max(curtail_due_to_export_cap, 0.0),
        max(curtail_due_to_exchange_limit, 0.0),
        max(exchange_import_shortfall, 0.0),
        max(bess_energy_end, 0.0),
        hour_case,
    )


def dispatch_hour_values_with_limits(
    *,
    load_energy: float,
    renewable_energy: float,
    has_bess: bool,
    bess_power_energy_limit: float,
    bess_energy_start: float,
    bess_soc_min_energy: float,
    bess_soc_max_energy: float,
    eta_charge: float,
    eta_discharge: float,
    allow_export: bool,
    export_limit_energy: float,
    exchange_limit_energy: float,
    remaining_export_cap: float | None = None,
) -> DispatchStepValues:
    """Dispatch one time step and return raw values without allocating a dataclass."""

    if has_bess:
        return dispatch_bess_hour_values_with_limits(
            load_energy=load_energy,
            renewable_energy=renewable_energy,
            bess_power_energy_limit=bess_power_energy_limit,
            bess_energy_start=bess_energy_start,
            bess_soc_min_energy=bess_soc_min_energy,
            bess_soc_max_energy=bess_soc_max_energy,
            eta_charge=eta_charge,
            eta_discharge=eta_discharge,
            allow_export=allow_export,
            export_limit_energy=export_limit_energy,
            exchange_limit_energy=exchange_limit_energy,
            has_exchange_limit=exchange_limit_energy != float("inf"),
            remaining_export_cap=remaining_export_cap,
        )

    bess_energy_start = 0.0

    if renewable_energy >= load_energy:
        direct_self_use = load_energy
        surplus = renewable_energy - load_energy
        bess_charge = 0.0
        bess_energy_end = 0.0

        surplus_after_charge = surplus - bess_charge
        export_limit = min(export_limit_energy, exchange_limit_energy)
        export_before_annual_cap = min(surplus_after_charge, export_limit) if allow_export else 0.0
        if remaining_export_cap is not None:
            grid_export = min(export_before_annual_cap, max(remaining_export_cap, 0.0))
        else:
            grid_export = export_before_annual_cap
        curtail = surplus_after_charge - grid_export
        curtail_due_to_export_cap = max(export_before_annual_cap - grid_export, 0.0)
        curtail_due_to_exchange_limit = max(surplus_after_charge - min(surplus_after_charge, exchange_limit_energy), 0.0)
        grid_import = 0.0
        exchange_import_shortfall = 0.0
        bess_discharge = 0.0

        if abs(surplus) <= 1e-12:
            hour_case = "GEN_BALANCED"
        elif bess_charge > 0 and grid_export > 0 and curtail > 0:
            hour_case = "GEN_SURPLUS_CHARGE_EXPORT_CURTAIL"
        elif bess_charge > 0 and grid_export > 0:
            hour_case = "GEN_SURPLUS_CHARGE_EXPORT"
        elif bess_charge > 0:
            hour_case = "GEN_SURPLUS_CHARGE_BESS"
        elif grid_export > 0 and curtail == 0:
            hour_case = "GEN_SURPLUS_DIRECT_EXPORT"
        else:
            hour_case = "GEN_SURPLUS_CURTAIL"
    else:
        direct_self_use = renewable_energy
        deficit = load_energy - renewable_energy
        bess_discharge = 0.0
        bess_energy_end = 0.0

        raw_grid_import = deficit - bess_discharge
        grid_import = min(raw_grid_import, exchange_limit_energy)
        exchange_import_shortfall = raw_grid_import - grid_import
        grid_export = 0.0
        curtail = 0.0
        curtail_due_to_export_cap = 0.0
        curtail_due_to_exchange_limit = 0.0
        bess_charge = 0.0
        if renewable_energy == 0 and bess_discharge == 0:
            hour_case = "NO_RENEWABLE_GRID_IMPORT"
        elif bess_discharge > 0 and grid_import > 0:
            hour_case = "GEN_SHORT_BESS_DISCHARGE_AND_GRID_IMPORT"
        elif bess_discharge > 0:
            hour_case = "GEN_SHORT_BESS_DISCHARGE"
        else:
            hour_case = "GEN_SHORT_GRID_IMPORT"

    return (
        max(direct_self_use, 0.0),
        max(bess_charge, 0.0),
        max(bess_discharge, 0.0),
        max(grid_import, 0.0),
        max(grid_export, 0.0),
        max(curtail, 0.0),
        max(curtail_due_to_export_cap, 0.0),
        max(curtail_due_to_exchange_limit, 0.0),
        max(exchange_import_shortfall, 0.0),
        max(bess_energy_end, 0.0),
        hour_case,
    )


def dispatch_hour_with_limits(
    *,
    load_energy: float,
    renewable_energy: float,
    has_bess: bool,
    bess_power_energy_limit: float,
    bess_energy_start: float,
    bess_soc_min_energy: float,
    bess_soc_max_energy: float,
    eta_charge: float,
    eta_discharge: float,
    allow_export: bool,
    export_limit_energy: float,
    exchange_limit_energy: float,
    remaining_export_cap: float | None = None,
) -> DispatchStep:
    """Dispatch one time step with scenario-level limits precomputed."""

    return DispatchStep(
        *dispatch_hour_values_with_limits(
            load_energy=load_energy,
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
            exchange_limit_energy=exchange_limit_energy,
            remaining_export_cap=remaining_export_cap,
        )
    )


def dispatch_hour(
    *,
    load_energy: float,
    renewable_energy: float,
    bess_power: float,
    bess_energy: float,
    bess_energy_start: float,
    bess_params: BessParams,
    dt_hours: float,
    allow_export: bool,
    export_power_max: float | None,
    remaining_export_cap: float | None = None,
    grid_exchange_power_limit: float | None = None,
) -> DispatchStep:
    """Dispatch one time step using the greedy rules in ALGORITHM_SPEC.md."""

    has_bess = _has_bess(bess_power, bess_energy)
    export_power_limit = float("inf") if export_power_max is None else max(export_power_max * dt_hours, 0.0)
    exchange_limit_energy = (
        float("inf") if grid_exchange_power_limit is None else max(grid_exchange_power_limit * dt_hours, 0.0)
    )
    return dispatch_hour_with_limits(
        load_energy=load_energy,
        renewable_energy=renewable_energy,
        has_bess=has_bess,
        bess_power_energy_limit=bess_power * dt_hours,
        bess_energy_start=bess_energy_start,
        bess_soc_min_energy=bess_params.soc_min * bess_energy,
        bess_soc_max_energy=bess_params.soc_max * bess_energy,
        eta_charge=bess_params.eta_charge,
        eta_discharge=bess_params.eta_discharge,
        allow_export=allow_export,
        export_limit_energy=export_power_limit,
        exchange_limit_energy=exchange_limit_energy,
        remaining_export_cap=remaining_export_cap,
    )


def normalize_dispatch_strategy(strategy: DispatchStrategy | str | None) -> DispatchStrategy:
    if strategy is None:
        return DispatchStrategy.GRID_CONNECTED_RENEWABLE_FIRST_GREEDY
    if isinstance(strategy, DispatchStrategy):
        return strategy
    try:
        return DispatchStrategy(strategy)
    except ValueError as exc:
        supported = ", ".join(item.value for item in DispatchStrategy)
        raise ValueError(f"Unsupported dispatch strategy: {strategy}. Supported strategies: {supported}") from exc


def dispatch_hour_with_strategy(
    *,
    strategy: DispatchStrategy | str | None = None,
    load_energy: float,
    renewable_energy: float,
    bess_power: float,
    bess_energy: float,
    bess_energy_start: float,
    bess_params: BessParams,
    dt_hours: float,
    allow_export: bool,
    export_power_max: float | None,
    remaining_export_cap: float | None = None,
    grid_exchange_power_limit: float | None = None,
) -> DispatchStep:
    normalized = normalize_dispatch_strategy(strategy)
    if normalized is DispatchStrategy.GRID_CONNECTED_RENEWABLE_FIRST_GREEDY:
        return dispatch_hour(
            load_energy=load_energy,
            renewable_energy=renewable_energy,
            bess_power=bess_power,
            bess_energy=bess_energy,
            bess_energy_start=bess_energy_start,
            bess_params=bess_params,
            dt_hours=dt_hours,
            allow_export=allow_export,
            export_power_max=export_power_max,
            remaining_export_cap=remaining_export_cap,
            grid_exchange_power_limit=grid_exchange_power_limit,
        )
    raise ValueError(f"Unsupported dispatch strategy: {normalized.value}")
