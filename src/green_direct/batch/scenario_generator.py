"""Scenario grid generation."""

from __future__ import annotations

from dataclasses import dataclass

from green_direct.models.scenario import Scenario


@dataclass(frozen=True)
class RangeSpec:
    start: float
    end: float
    step: float


@dataclass(frozen=True)
class ScenarioGrid:
    pv_capacity: RangeSpec
    wind_capacity: RangeSpec
    bess_power: RangeSpec
    bess_duration_hours: list[float]


def values_from_range(spec: RangeSpec) -> list[float]:
    if spec.step <= 0:
        raise ValueError("容量范围步长必须大于 0。")
    if spec.end < spec.start:
        raise ValueError("容量范围结束值不能小于起始值。")
    values: list[float] = []
    current = spec.start
    tolerance = spec.step * 1e-9
    while current <= spec.end + tolerance:
        values.append(round(current, 10))
        current += spec.step
    return values


def parse_range_spec(raw: dict | RangeSpec) -> RangeSpec:
    if isinstance(raw, RangeSpec):
        return raw
    return RangeSpec(start=float(raw["start"]), end=float(raw["end"]), step=float(raw["step"]))


def parse_scenario_grid(raw: dict | ScenarioGrid) -> ScenarioGrid:
    if isinstance(raw, ScenarioGrid):
        return raw
    grid = raw.get("scenario_grid", raw)
    return ScenarioGrid(
        pv_capacity=parse_range_spec(grid["pv_capacity"]),
        wind_capacity=parse_range_spec(grid["wind_capacity"]),
        bess_power=parse_range_spec(grid["bess_power"]),
        bess_duration_hours=[float(item) for item in grid["bess_duration_hours"]],
    )


def _bess_power_duration_pairs(grid: ScenarioGrid) -> list[tuple[float, float]]:
    pairs: list[tuple[float, float]] = []
    durations = list(grid.bess_duration_hours)
    for duration in durations:
        if duration < 0:
            raise ValueError("储能时长不能小于 0。")
    for bess_power in values_from_range(grid.bess_power):
        for duration in durations:
            if bess_power == 0 and duration > 0:
                continue
            if bess_power > 0 and duration == 0:
                continue
            pairs.append((bess_power, duration))
    return pairs


def count_scenarios(raw_grid: dict | ScenarioGrid) -> int:
    """Count candidate scenarios without materialising Scenario objects."""

    grid = parse_scenario_grid(raw_grid)
    pv_values = values_from_range(grid.pv_capacity)
    wind_values = values_from_range(grid.wind_capacity)
    renewable_pair_count = sum(
        1
        for pv_capacity in pv_values
        for wind_capacity in wind_values
        if pv_capacity > 0 or wind_capacity > 0
    )
    return renewable_pair_count * len(_bess_power_duration_pairs(grid))


def generate_scenarios(raw_grid: dict | ScenarioGrid, *, scenario_prefix: str = "S") -> list[Scenario]:
    grid = parse_scenario_grid(raw_grid)
    pv_values = values_from_range(grid.pv_capacity)
    wind_values = values_from_range(grid.wind_capacity)
    bess_pairs = _bess_power_duration_pairs(grid)
    scenarios: list[Scenario] = []
    index = 1
    for pv_capacity in pv_values:
        for wind_capacity in wind_values:
            if pv_capacity <= 0 and wind_capacity <= 0:
                continue
            for bess_power, duration in bess_pairs:
                bess_energy = bess_power * duration
                scenarios.append(
                    Scenario(
                        scenario_id=f"{scenario_prefix}{index:04d}",
                        pv_capacity=pv_capacity,
                        wind_capacity=wind_capacity,
                        bess_power=bess_power,
                        bess_energy=bess_energy,
                    )
                )
                index += 1
    return scenarios
