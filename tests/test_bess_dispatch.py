from dataclasses import astuple

import pytest

from green_direct.core.bess_dispatch import (
    dispatch_bess_hour_summary_values_with_limits,
    dispatch_bess_hour_values_with_limits,
    dispatch_hour,
    dispatch_hour_values_with_limits,
    dispatch_hour_with_limits,
)
from green_direct.models.params import BessParams


def test_charge_limited_by_power():
    step = dispatch_hour(
        load_energy=10,
        renewable_energy=20,
        bess_power=3,
        bess_energy=10,
        bess_energy_start=5,
        bess_params=BessParams(soc_initial=0.5, soc_min=0.1, soc_max=0.9, eta_charge=1.0),
        dt_hours=1,
        allow_export=False,
        export_power_max=None,
    )

    assert step.bess_charge == 3
    assert step.curtail == 7
    assert step.bess_energy_end == 8


def test_charge_limited_by_capacity():
    step = dispatch_hour(
        load_energy=10,
        renewable_energy=20,
        bess_power=10,
        bess_energy=10,
        bess_energy_start=8.5,
        bess_params=BessParams(soc_initial=0.85, soc_min=0.1, soc_max=0.9, eta_charge=1.0),
        dt_hours=1,
        allow_export=False,
        export_power_max=None,
    )

    assert step.bess_charge == pytest.approx(0.5)
    assert step.curtail == pytest.approx(9.5)
    assert step.bess_energy_end == pytest.approx(9)


def test_discharge_limited_by_power():
    step = dispatch_hour(
        load_energy=20,
        renewable_energy=10,
        bess_power=3,
        bess_energy=10,
        bess_energy_start=9,
        bess_params=BessParams(soc_initial=0.9, soc_min=0.1, soc_max=0.9, eta_discharge=1.0),
        dt_hours=1,
        allow_export=True,
        export_power_max=None,
    )

    assert step.bess_discharge == 3
    assert step.grid_import == 7
    assert step.bess_energy_end == 6


def test_discharge_limited_by_capacity():
    step = dispatch_hour(
        load_energy=20,
        renewable_energy=10,
        bess_power=10,
        bess_energy=10,
        bess_energy_start=1.5,
        bess_params=BessParams(soc_initial=0.15, soc_min=0.1, soc_max=0.9, eta_discharge=1.0),
        dt_hours=1,
        allow_export=True,
        export_power_max=None,
    )

    assert step.bess_discharge == pytest.approx(0.5)
    assert step.grid_import == pytest.approx(9.5)
    assert step.bess_energy_end == pytest.approx(1)


def test_no_simultaneous_charge_and_discharge():
    charge_step = dispatch_hour(
        load_energy=10,
        renewable_energy=20,
        bess_power=10,
        bess_energy=10,
        bess_energy_start=5,
        bess_params=BessParams(),
        dt_hours=1,
        allow_export=True,
        export_power_max=None,
    )
    discharge_step = dispatch_hour(
        load_energy=20,
        renewable_energy=10,
        bess_power=10,
        bess_energy=10,
        bess_energy_start=5,
        bess_params=BessParams(),
        dt_hours=1,
        allow_export=True,
        export_power_max=None,
    )

    assert not (charge_step.bess_charge > 0 and charge_step.bess_discharge > 0)
    assert not (discharge_step.bess_charge > 0 and discharge_step.bess_discharge > 0)


def test_exchange_limit_curtails_export():
    step = dispatch_hour(
        load_energy=10,
        renewable_energy=30,
        bess_power=0,
        bess_energy=0,
        bess_energy_start=0,
        bess_params=BessParams(),
        dt_hours=1,
        allow_export=True,
        export_power_max=None,
        grid_exchange_power_limit=5,
    )

    assert step.grid_export == 5
    assert step.curtail == 15
    assert step.curtail_due_to_exchange_limit == 15


def test_exchange_limit_caps_import_and_records_shortfall():
    step = dispatch_hour(
        load_energy=20,
        renewable_energy=0,
        bess_power=0,
        bess_energy=0,
        bess_energy_start=0,
        bess_params=BessParams(),
        dt_hours=1,
        allow_export=True,
        export_power_max=None,
        grid_exchange_power_limit=8,
    )

    assert step.grid_import == 8
    assert step.exchange_import_shortfall == 12


def test_precomputed_limit_dispatch_matches_public_dispatch():
    params = BessParams(soc_min=0.1, soc_max=0.9, eta_charge=0.95, eta_discharge=0.9)

    public = dispatch_hour(
        load_energy=10,
        renewable_energy=30,
        bess_power=5,
        bess_energy=20,
        bess_energy_start=8,
        bess_params=params,
        dt_hours=1,
        allow_export=True,
        export_power_max=6,
        remaining_export_cap=4,
        grid_exchange_power_limit=5,
    )
    precomputed = dispatch_hour_with_limits(
        load_energy=10,
        renewable_energy=30,
        has_bess=True,
        bess_power_energy_limit=5,
        bess_energy_start=8,
        bess_soc_min_energy=2,
        bess_soc_max_energy=18,
        eta_charge=0.95,
        eta_discharge=0.9,
        allow_export=True,
        export_limit_energy=6,
        exchange_limit_energy=5,
        remaining_export_cap=4,
    )

    assert precomputed == public


def test_precomputed_limit_values_match_dispatch_step():
    step = dispatch_hour_with_limits(
        load_energy=12,
        renewable_energy=30,
        has_bess=True,
        bess_power_energy_limit=4,
        bess_energy_start=7,
        bess_soc_min_energy=2,
        bess_soc_max_energy=18,
        eta_charge=0.95,
        eta_discharge=0.9,
        allow_export=True,
        export_limit_energy=6,
        exchange_limit_energy=5,
        remaining_export_cap=3,
    )
    values = dispatch_hour_values_with_limits(
        load_energy=12,
        renewable_energy=30,
        has_bess=True,
        bess_power_energy_limit=4,
        bess_energy_start=7,
        bess_soc_min_energy=2,
        bess_soc_max_energy=18,
        eta_charge=0.95,
        eta_discharge=0.9,
        allow_export=True,
        export_limit_energy=6,
        exchange_limit_energy=5,
        remaining_export_cap=3,
    )

    assert values == astuple(step)


def test_bess_specific_values_match_generic_bess_path():
    common = {
        "load_energy": 22,
        "renewable_energy": 10,
        "bess_power_energy_limit": 5,
        "bess_energy_start": 7,
        "bess_soc_min_energy": 2,
        "bess_soc_max_energy": 18,
        "eta_charge": 0.95,
        "eta_discharge": 0.9,
        "allow_export": True,
        "export_limit_energy": 6,
        "exchange_limit_energy": 5,
        "remaining_export_cap": 3,
    }

    assert dispatch_bess_hour_values_with_limits(**common) == dispatch_hour_values_with_limits(
        has_bess=True,
        **common,
    )


def test_bess_specific_no_exchange_limit_matches_infinite_exchange_limit():
    common = {
        "load_energy": 18,
        "renewable_energy": 35,
        "bess_power_energy_limit": 4,
        "bess_energy_start": 8,
        "bess_soc_min_energy": 2,
        "bess_soc_max_energy": 18,
        "eta_charge": 0.95,
        "eta_discharge": 0.9,
        "allow_export": True,
        "export_limit_energy": float("inf"),
        "exchange_limit_energy": float("inf"),
        "remaining_export_cap": 5,
    }

    explicit_no_limit = dispatch_bess_hour_values_with_limits(has_exchange_limit=False, **common)
    inferred_no_limit = dispatch_bess_hour_values_with_limits(**common)

    assert explicit_no_limit == inferred_no_limit
    assert explicit_no_limit[7] == 0.0
    assert explicit_no_limit[8] == 0.0


@pytest.mark.parametrize(
    "common",
    [
        {
            "load_energy": 18,
            "renewable_energy": 35,
            "bess_power_energy_limit": 4,
            "bess_energy_start": 8,
            "bess_soc_min_energy": 2,
            "bess_soc_max_energy": 18,
            "eta_charge": 0.95,
            "eta_discharge": 0.9,
            "allow_export": True,
            "export_limit_energy": 6,
            "exchange_limit_energy": 5,
            "has_exchange_limit": True,
            "remaining_export_cap": 4,
        },
        {
            "load_energy": 22,
            "renewable_energy": 10,
            "bess_power_energy_limit": 5,
            "bess_energy_start": 7,
            "bess_soc_min_energy": 2,
            "bess_soc_max_energy": 18,
            "eta_charge": 0.95,
            "eta_discharge": 0.9,
            "allow_export": True,
            "export_limit_energy": float("inf"),
            "exchange_limit_energy": float("inf"),
            "has_exchange_limit": False,
            "remaining_export_cap": None,
        },
    ],
)
def test_bess_summary_values_match_bess_values_without_hour_case(common):
    values = dispatch_bess_hour_values_with_limits(**common, clamp_outputs=False)
    summary_values = dispatch_bess_hour_summary_values_with_limits(**common)

    assert summary_values == values[:-1]
