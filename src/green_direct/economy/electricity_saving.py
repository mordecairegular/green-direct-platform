"""Avoided grid-purchase saving helpers."""

from __future__ import annotations

from green_direct.economy.economic_inputs import AvoidedGridPurchaseParams


def _validate_rate(name: str, value: float) -> None:
    if not 0 <= value <= 1:
        raise ValueError(f"{name} must be between 0 and 1.")


def validate_avoided_grid_purchase_params(params: AvoidedGridPurchaseParams) -> None:
    """Validate fixed-price avoided grid-purchase inputs."""

    if params.net_avoided_grid_cost_price is not None and params.net_avoided_grid_cost_price < 0:
        raise ValueError("net_avoided_grid_cost_price must be non-negative.")
    if params.energy_market_price_with_vat < 0:
        raise ValueError("energy_market_price_with_vat must be non-negative.")
    if params.line_loss_price_with_vat < 0:
        raise ValueError("line_loss_price_with_vat must be non-negative.")
    if params.system_operation_fee_with_vat < 0:
        raise ValueError("system_operation_fee_with_vat must be non-negative.")
    if params.transmission_distribution_tariff_with_vat < 0:
        raise ValueError("transmission_distribution_tariff_with_vat must be non-negative.")
    if params.gov_fund_surcharge < 0:
        raise ValueError("gov_fund_surcharge must be non-negative.")
    if params.green_direct_retained_transmission_distribution_tariff_with_vat < 0:
        raise ValueError(
            "green_direct_retained_transmission_distribution_tariff_with_vat must be non-negative."
        )
    if params.green_direct_retained_gov_fund_surcharge < 0:
        raise ValueError("green_direct_retained_gov_fund_surcharge must be non-negative.")
    if params.environmental_value_per_kwh < 0:
        raise ValueError("environmental_value_per_kwh must be non-negative.")
    _validate_rate("grid_purchase_vat_rate", params.grid_purchase_vat_rate)


def calc_grid_purchase_taxable_price_with_vat(params: AvoidedGridPurchaseParams) -> float:
    """Return VAT-inclusive bill components subject to price-tax separation."""

    validate_avoided_grid_purchase_params(params)
    return (
        params.energy_market_price_with_vat
        + params.line_loss_price_with_vat
        + params.system_operation_fee_with_vat
        + params.transmission_distribution_tariff_with_vat
    )


def calc_green_direct_retained_taxable_fee_with_vat(params: AvoidedGridPurchaseParams) -> float:
    """Return VAT-inclusive fees still paid for self-used green power."""

    validate_avoided_grid_purchase_params(params)
    return params.green_direct_retained_transmission_distribution_tariff_with_vat


def calc_green_direct_retained_cash_fee(params: AvoidedGridPurchaseParams) -> float:
    """Return cash fees still paid for self-used green power."""

    validate_avoided_grid_purchase_params(params)
    return (
        calc_green_direct_retained_taxable_fee_with_vat(params)
        + params.green_direct_retained_gov_fund_surcharge
    )


def calc_net_avoided_grid_cost_price(params: AvoidedGridPurchaseParams) -> float:
    """Return the pre-tax economic value of each avoided kWh of grid purchase."""

    validate_avoided_grid_purchase_params(params)
    if params.net_avoided_grid_cost_price is not None:
        return float(params.net_avoided_grid_cost_price)
    taxable_price_with_vat = calc_grid_purchase_taxable_price_with_vat(params)
    retained_taxable_fee_with_vat = calc_green_direct_retained_taxable_fee_with_vat(params)
    return (
        (taxable_price_with_vat - retained_taxable_fee_with_vat)
        / (1 + params.grid_purchase_vat_rate)
        + params.gov_fund_surcharge
        - params.green_direct_retained_gov_fund_surcharge
    )


def calc_avoided_grid_purchase_cash_price(params: AvoidedGridPurchaseParams) -> float:
    """Return the cash price avoided before stripping deductible VAT."""

    validate_avoided_grid_purchase_params(params)
    if params.net_avoided_grid_cost_price is not None:
        return float(params.net_avoided_grid_cost_price)
    return (
        calc_grid_purchase_taxable_price_with_vat(params)
        + params.gov_fund_surcharge
        - calc_green_direct_retained_cash_fee(params)
    )


def calc_self_use_saving(self_use_energy: float, params: AvoidedGridPurchaseParams) -> float:
    """Return annual self-use saving in 万元."""

    return float(self_use_energy) * calc_net_avoided_grid_cost_price(params)


def calc_environmental_value(self_use_energy: float, params: AvoidedGridPurchaseParams) -> float:
    """Return scalar environmental value in 万元."""

    validate_avoided_grid_purchase_params(params)
    return float(self_use_energy) * params.environmental_value_per_kwh


def calc_export_revenue_without_vat(
    grid_export_energy: float,
    grid_export_price_with_vat: float,
    output_vat_rate: float,
) -> float:
    """Return export revenue without output VAT in 万元."""

    _validate_rate("output_vat_rate", float(output_vat_rate))
    if grid_export_price_with_vat < 0:
        raise ValueError("grid_export_price_with_vat must be non-negative.")
    if grid_export_energy < 0:
        raise ValueError("grid_export_energy must be non-negative.")
    return float(grid_export_energy) * float(grid_export_price_with_vat) / (1 + float(output_vat_rate))
