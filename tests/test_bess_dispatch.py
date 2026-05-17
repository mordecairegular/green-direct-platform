import pytest

from green_direct.core.bess_dispatch import dispatch_hour
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
