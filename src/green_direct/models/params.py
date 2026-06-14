"""Parameter models used by the V0.1 technical simulator."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DataCleaningParams:
    """Rules for cleaning PV and wind per-unit curves."""

    allow_negative_pu: bool = True
    allow_small_negative_pu: bool = True
    small_negative_tolerance: float = -0.001
    clip_small_negative_to_zero: bool = False
    allow_pu_greater_than_one: bool = True
    clip_pu_greater_than_one: bool = False


@dataclass(frozen=True)
class BessParams:
    """BESS operation parameters."""

    soc_initial: float = 0.5
    soc_min: float = 0.1
    soc_max: float = 0.9
    eta_charge: float = 0.95
    eta_discharge: float = 0.95
    cycle_life: float = 6000.0


@dataclass(frozen=True)
class PolicyParams:
    """Policy threshold parameters for technical screening."""

    self_use_rate_min: float = 0.60
    green_load_rate_min: float = 0.30
    export_rate_max: float = 0.20
    allow_export: bool = True
    export_power_max: float | None = None
    grid_exchange_power_limit: float | None = None
    export_control_mode: str = "annual_cap_runtime"


@dataclass(frozen=True)
class TimeParams:
    """Time step and supported annual row counts."""

    dt_hours: float = 1.0
    supported_hours: tuple[int, int] = (8760, 8784)


@dataclass(frozen=True)
class PerformanceParams:
    """Batch runner performance guardrails."""

    warn_if_scenarios_exceed: int = 5000
    parallel_workers: int = 1
