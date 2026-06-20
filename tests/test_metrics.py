from green_direct.core.metrics import evaluate_policy, safe_divide
from green_direct.models.params import PolicyParams


def test_safe_divide_zero_denominator():
    assert safe_divide(1, 0) == 0


def test_policy_failure_reason_for_self_use_rate():
    passed, reasons = evaluate_policy(
        self_use_rate=0.59,
        green_load_rate=0.31,
        export_rate=0.10,
        grid_export_energy=1,
        max_grid_export_power=1,
        exchange_import_shortfall_energy=0,
        policy=PolicyParams(),
    )

    assert passed is False
    assert "自发自用率不足" in reasons
