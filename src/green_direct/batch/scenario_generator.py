"""Scenario grid generation."""

from __future__ import annotations

from collections.abc import Iterator
import math
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


def _range_value_count(spec: RangeSpec) -> int:
    if spec.step <= 0:
        raise ValueError("容量范围步长必须大于 0。")
    if spec.end < spec.start:
        raise ValueError("容量范围结束值不能小于起始值。")
    tolerance = spec.step * 1e-9
    return int(math.floor((spec.end - spec.start + tolerance) / spec.step)) + 1


def _rounded_range_value(spec: RangeSpec, index: int) -> float:
    return round(spec.start + spec.step * index, 10)


def _first_range_index_ge(spec: RangeSpec, total: int, threshold: float) -> int:
    low = 0
    high = total
    while low < high:
        mid = (low + high) // 2
        if _rounded_range_value(spec, mid) >= threshold:
            high = mid
        else:
            low = mid + 1
    return low


def _first_range_index_gt(spec: RangeSpec, total: int, threshold: float) -> int:
    low = 0
    high = total
    while low < high:
        mid = (low + high) // 2
        if _rounded_range_value(spec, mid) > threshold:
            high = mid
        else:
            low = mid + 1
    return low


def _range_sign_counts(spec: RangeSpec) -> tuple[int, int, int]:
    """Return (negative, zero, positive) counts for values_from_range(spec)."""

    total = _range_value_count(spec)
    first_zero_or_positive = _first_range_index_ge(spec, total, 0.0)
    first_positive = _first_range_index_gt(spec, total, 0.0)
    negative_count = first_zero_or_positive
    zero_count = first_positive - first_zero_or_positive
    positive_count = total - first_positive
    return negative_count, zero_count, positive_count


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


def _bess_power_duration_pair_count(grid: ScenarioGrid) -> int:
    negative_power_count, zero_power_count, positive_power_count = _range_sign_counts(grid.bess_power)
    duration_zero_count = 0
    duration_positive_count = 0
    for duration in grid.bess_duration_hours:
        if duration < 0:
            raise ValueError("储能时长不能小于 0。")
        if duration == 0:
            duration_zero_count += 1
        else:
            duration_positive_count += 1
    return (
        negative_power_count * (duration_zero_count + duration_positive_count)
        + zero_power_count * duration_zero_count
        + positive_power_count * duration_positive_count
    )


def count_scenarios(raw_grid: dict | ScenarioGrid) -> int:
    """Count candidate scenarios without materialising Scenario objects."""

    grid = parse_scenario_grid(raw_grid)
    pv_negative, pv_zero, pv_positive = _range_sign_counts(grid.pv_capacity)
    wind_negative, wind_zero, wind_positive = _range_sign_counts(grid.wind_capacity)
    pv_total = pv_negative + pv_zero + pv_positive
    wind_total = wind_negative + wind_zero + wind_positive
    renewable_pair_count = pv_total * wind_total - (pv_negative + pv_zero) * (wind_negative + wind_zero)
    return renewable_pair_count * _bess_power_duration_pair_count(grid)


def generate_scenarios(raw_grid: dict | ScenarioGrid, *, scenario_prefix: str = "S") -> list[Scenario]:
    return list(iter_scenarios(raw_grid, scenario_prefix=scenario_prefix))


def iter_scenarios(raw_grid: dict | ScenarioGrid, *, scenario_prefix: str = "S") -> Iterator[Scenario]:
    grid = parse_scenario_grid(raw_grid)
    pv_values = values_from_range(grid.pv_capacity)
    wind_values = values_from_range(grid.wind_capacity)
    bess_pairs = _bess_power_duration_pairs(grid)
    index = 1
    for pv_capacity in pv_values:
        for wind_capacity in wind_values:
            if pv_capacity <= 0 and wind_capacity <= 0:
                continue
            for bess_power, duration in bess_pairs:
                bess_energy = bess_power * duration
                yield Scenario(
                    scenario_id=f"{scenario_prefix}{index:04d}",
                    pv_capacity=pv_capacity,
                    wind_capacity=wind_capacity,
                    bess_power=bess_power,
                    bess_energy=bess_energy,
                )
                index += 1
