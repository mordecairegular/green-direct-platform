"""Scenario models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Scenario:
    """Capacity configuration for one technical simulation scenario."""

    scenario_id: str
    pv_capacity: float
    wind_capacity: float
    bess_power: float
    bess_energy: float

    @property
    def bess_duration(self) -> float:
        if self.bess_power <= 0:
            return 0.0
        return self.bess_energy / self.bess_power

    @property
    def bess_c_rate(self) -> float:
        if self.bess_energy <= 0:
            return 0.0
        return self.bess_power / self.bess_energy
