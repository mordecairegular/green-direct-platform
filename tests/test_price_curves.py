from pathlib import Path

import pandas as pd
import pytest

from green_direct.economy import AvoidedGridPurchaseParams, EconomicParams, read_price_curve
from green_direct.economy.price_curves import (
    PriceCurveValidationError,
    align_price_curve_to_hourly,
    apply_price_curve_to_summary,
    build_effective_hourly_prices,
)
from green_direct.io.read_curves import read_csv_auto_encoding


def _price_curve_csv(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False).encode("utf-8-sig")


def test_down_grid_template_contains_only_raw_bill_inputs_plus_audit_labels():
    frame, _ = read_csv_auto_encoding(
        Path("docs/templates/price_curves/price_curve_template_down_grid.csv").read_bytes()
    )

    assert frame.columns.tolist() == [
        "timestamp",
        "hour_index",
        "energy_market_price_with_vat",
        "line_loss_price_with_vat",
        "system_operation_fee_with_vat",
        "transmission_distribution_tariff_with_vat",
        "gov_fund_surcharge",
        "month",
        "peak_valley",
    ]


def test_down_grid_template_maps_bill_columns_and_tax_treatment():
    price_curve = read_price_curve("samples/price_curve_template_down_grid.csv")
    effective = build_effective_hourly_prices(
        price_curve.data.head(1),
        economic_params=EconomicParams(),
        avoided_grid_params=AvoidedGridPurchaseParams(
            net_avoided_grid_cost_price=None,
            grid_purchase_vat_rate=0.13,
        ),
        load_side_avoided_charge_price=0.50,
        green_power_settlement_price_with_vat=0.40,
        environmental_value_per_kwh=0.0,
    )

    assert len(price_curve.data) == 8784
    assert price_curve.matched_columns["energy_market_price_with_vat"] == "energy_market_price_with_vat"
    assert price_curve.matched_columns["gov_fund_surcharge"] == "gov_fund_surcharge"
    assert "month" not in price_curve.matched_columns
    assert "peak_valley" not in price_curve.matched_columns
    first = effective.iloc[0]
    first_curve = price_curve.data.iloc[0]
    expected_down_grid_landed = (
        first_curve["energy_market_price_with_vat"]
        + first_curve["line_loss_price_with_vat"]
        + first_curve["system_operation_fee_with_vat"]
        + first_curve["transmission_distribution_tariff_with_vat"]
        + first_curve["gov_fund_surcharge"]
    )
    expected_green_self_use_landed = (
        0.40
        + first_curve["transmission_distribution_tariff_with_vat"]
        + first_curve["gov_fund_surcharge"]
    )
    # Government fund is not stripped for VAT. T&D and government fund default
    # to retained fees when retained columns are absent, matching current UI口径.
    assert first["load_side_avoided_charge_price"] == pytest.approx(0.30872 + 0.027 + 0.05)
    assert first["net_avoided_grid_cost_price"] == pytest.approx((0.30872 + 0.027 + 0.05) / 1.13)
    assert first["down_grid_landed_price_with_vat"] == pytest.approx(expected_down_grid_landed)
    assert first["green_self_use_landed_price_with_vat"] == pytest.approx(expected_green_self_use_landed)


def test_price_curve_can_override_green_direct_retained_fees_for_landed_price():
    hours = 8760
    raw = pd.DataFrame(
        {
            "hour_index": range(hours),
            "energy_market_price_with_vat": [0.40] * hours,
            "line_loss_price_with_vat": [0.01] * hours,
            "system_operation_fee_with_vat": [0.02] * hours,
            "transmission_distribution_tariff_with_vat": [0.15] * hours,
            "gov_fund_surcharge": [0.03] * hours,
            "green_direct_retained_transmission_distribution_tariff_with_vat": [0.04] * hours,
            "green_direct_retained_gov_fund_surcharge": [0.01] * hours,
        }
    )

    price_curve = read_price_curve(_price_curve_csv(raw))
    effective = build_effective_hourly_prices(
        price_curve.data.head(1),
        economic_params=EconomicParams(),
        avoided_grid_params=AvoidedGridPurchaseParams(
            net_avoided_grid_cost_price=None,
            grid_purchase_vat_rate=0.13,
        ),
        load_side_avoided_charge_price=0.50,
        green_power_settlement_price_with_vat=0.35,
        environmental_value_per_kwh=0.0,
    ).iloc[0]

    assert price_curve.matched_columns["green_direct_retained_transmission_distribution_tariff_with_vat"] == (
        "green_direct_retained_transmission_distribution_tariff_with_vat"
    )
    assert price_curve.matched_columns["green_direct_retained_gov_fund_surcharge"] == (
        "green_direct_retained_gov_fund_surcharge"
    )
    assert effective["down_grid_landed_price_with_vat"] == pytest.approx(0.40 + 0.01 + 0.02 + 0.15 + 0.03)
    assert effective["green_self_use_landed_price_with_vat"] == pytest.approx(0.35 + 0.04 + 0.01)
    assert effective["load_side_avoided_charge_price"] == pytest.approx(0.40 + 0.01 + 0.02 + 0.15 + 0.03 - 0.04 - 0.01)


def test_price_curve_zero_self_use_landed_fallback_uses_retained_fee_curve():
    hours = 8760
    price_curve = read_price_curve(
        _price_curve_csv(
            pd.DataFrame(
                {
                    "hour_index": range(hours),
                    "energy_market_price_with_vat": [0.40] * hours,
                    "transmission_distribution_tariff_with_vat": [0.15] * hours,
                    "gov_fund_surcharge": [0.03] * hours,
                    "green_direct_retained_transmission_distribution_tariff_with_vat": [0.04] * hours,
                    "green_direct_retained_gov_fund_surcharge": [0.01] * hours,
                }
            )
        )
    )
    summary = pd.DataFrame({"scenario_id": ["S_ZERO_SELF_USE"]})
    hourly = pd.DataFrame(
        {
            "hour_index": range(hours),
            "load_power": [0.0] * hours,
            "direct_self_use_power": [0.0] * hours,
            "bess_discharge_power": [0.0] * hours,
            "grid_import_power": [0.0] * hours,
            "grid_export_power": [0.0] * hours,
        }
    )
    hourly.loc[0, "load_power"] = 10.0
    hourly.loc[0, "grid_import_power"] = 10.0

    result = apply_price_curve_to_summary(
        summary,
        {"S_ZERO_SELF_USE": hourly},
        price_curve,
        economic_params=EconomicParams(),
        avoided_grid_params=AvoidedGridPurchaseParams(net_avoided_grid_cost_price=None),
        load_side_avoided_charge_price=0.50,
        green_power_settlement_price_with_vat=0.35,
    )

    row = result.price_summary.set_index("scenario_id").loc["S_ZERO_SELF_USE"]
    assert row["self_use_energy_for_landed_price"] == pytest.approx(0.0)
    assert row["green_self_use_landed_price_with_vat_effective"] == pytest.approx(0.35 + 0.04 + 0.01)


def test_price_curve_ignores_web_fixed_and_derived_columns():
    hours = 8760
    raw = pd.DataFrame(
        {
            "hour_index": range(hours),
            "energy_market_price_with_vat": [1.0] * hours,
            "green_power_settlement_price_with_vat": [9.0] * hours,
            "grid_export_price_with_vat": [9.0] * hours,
            "environmental_value_per_kwh": [9.0] * hours,
            "grid_purchase_vat_rate": [0.0] * hours,
            "load_side_avoided_charge_price": [9.0] * hours,
            "net_avoided_grid_cost_price": [9.0] * hours,
        }
    )

    price_curve = read_price_curve(_price_curve_csv(raw))
    effective = build_effective_hourly_prices(
        price_curve.data.head(1),
        economic_params=EconomicParams(grid_export_price_with_vat=0.30),
        avoided_grid_params=AvoidedGridPurchaseParams(
            net_avoided_grid_cost_price=None,
            grid_purchase_vat_rate=0.13,
        ),
        load_side_avoided_charge_price=0.50,
        green_power_settlement_price_with_vat=0.20,
        environmental_value_per_kwh=0.10,
    ).iloc[0]

    assert "green_power_settlement_price_with_vat" not in price_curve.matched_columns
    assert "grid_export_price_with_vat" not in price_curve.matched_columns
    assert "environmental_value_per_kwh" not in price_curve.matched_columns
    assert "grid_purchase_vat_rate" not in price_curve.matched_columns
    assert "load_side_avoided_charge_price" not in price_curve.matched_columns
    assert "net_avoided_grid_cost_price" not in price_curve.matched_columns
    assert effective["green_power_settlement_price_with_vat"] == pytest.approx(0.20)
    assert effective["grid_export_price_with_vat"] == pytest.approx(0.30)
    assert effective["environmental_value_per_kwh"] == pytest.approx(0.10)
    assert effective["load_side_avoided_charge_price"] == pytest.approx(1.0)
    assert effective["net_avoided_grid_cost_price"] == pytest.approx(1.0 / 1.13)


def test_price_curve_falls_back_to_row_order_when_year_timestamps_differ():
    hours = 8760
    price_curve = read_price_curve(
        _price_curve_csv(
            pd.DataFrame(
                {
                    "时间戳": pd.date_range("2025-01-01", periods=hours, freq="h"),
                    "电度电价(元/kWh)": [0.30] * hours,
                }
            )
        )
    )
    hourly = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=hours, freq="h"),
            "hour_index": range(hours),
        }
    )

    aligned, mode = align_price_curve_to_hourly(price_curve, hourly, diagnostics=price_curve.diagnostics)

    assert mode == "row_order"
    assert aligned["energy_market_price_with_vat"].iloc[0] == pytest.approx(0.30)
    assert any("时间戳与技术逐小时明细不完全一致" in message for message in price_curve.warnings)


def test_price_curve_template_uses_complete_hour_index_when_timestamps_differ():
    price_curve = read_price_curve("samples/price_curve_template_down_grid.csv")
    hourly = pd.DataFrame(
        {
            "timestamp": pd.date_range("2028-01-01", periods=8784, freq="h"),
            "hour_index": range(8784),
        }
    )

    aligned, mode = align_price_curve_to_hourly(price_curve, hourly, diagnostics=price_curve.diagnostics)

    assert mode == "hour_index"
    assert len(aligned) == 8784
    assert aligned["energy_market_price_with_vat"].iloc[7] == pytest.approx(0.70245)


def test_price_curve_with_partial_hour_index_can_use_row_order():
    hours = 8760
    raw = pd.DataFrame(
        {
            "timestamp": pd.date_range("2025-01-01", periods=hours, freq="h"),
            "hour_index": [0, 1, 2] + [None] * (hours - 3),
            "energy_market_price_with_vat": [0.30] * hours,
        }
    )
    raw.loc[7, "energy_market_price_with_vat"] = 0.70
    price_curve = read_price_curve(_price_curve_csv(raw))
    hourly = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=hours, freq="h"),
            "hour_index": range(hours),
        }
    )

    aligned, mode = align_price_curve_to_hourly(price_curve, hourly, diagnostics=price_curve.diagnostics)

    assert mode == "row_order"
    assert len(aligned) == hours
    assert aligned["energy_market_price_with_vat"].iloc[7] == pytest.approx(0.70)
    assert any("hour_index 缺失、重复或无法覆盖完整小时序号" in message for message in price_curve.warnings)


def test_price_curve_rejects_negative_prices_and_invalid_lengths():
    with pytest.raises(PriceCurveValidationError, match="当前仅支持 8760 或 8784 行"):
        read_price_curve(
            _price_curve_csv(
                pd.DataFrame(
                    {
                        "hour_index": [0],
                        "energy_market_price_with_vat": [-0.01],
                    }
                )
            )
        )

    frame = pd.DataFrame(
        {
            "hour_index": range(8760),
            "energy_market_price_with_vat": [0.30] * 8760,
        }
    )
    frame.loc[12, "energy_market_price_with_vat"] = -0.01
    with pytest.raises(PriceCurveValidationError, match="存在负值"):
        read_price_curve(_price_curve_csv(frame))
