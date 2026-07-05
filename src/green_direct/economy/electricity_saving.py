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
    """Return the cash price avoided before stripping deductible VAT.

    In fixed net-price mode this returns the same user-entered value for
    same-entity auxiliary display. Load-side tradable-benefit ranking should
    pass an explicit load-side avoided charge price through RecommendationParams.
    """

    validate_avoided_grid_purchase_params(params)
    if params.net_avoided_grid_cost_price is not None:
        return float(params.net_avoided_grid_cost_price)
    return (
        calc_grid_purchase_taxable_price_with_vat(params)
        + params.gov_fund_surcharge
        - calc_green_direct_retained_cash_fee(params)
    )


def build_avoided_grid_purchase_params_from_landed_price(
    *,
    down_grid_landed_price_with_vat: float,
    line_loss_price_with_vat: float = 0.0,
    system_operation_fee_with_vat: float = 0.0,
    transmission_distribution_tariff_with_vat: float = 0.0,
    gov_fund_surcharge: float = 0.0,
    grid_purchase_vat_rate: float = 0.13,
    green_direct_retained_transmission_distribution_tariff_with_vat: float | None = None,
    green_direct_retained_gov_fund_surcharge: float | None = None,
    environmental_value_per_kwh: float = 0.0,
) -> AvoidedGridPurchaseParams:
    """Build avoided-purchase inputs from bill-facing tariff items.

    ``down_grid_landed_price_with_vat`` is the customer-facing electricity bill
    energy price. The market/energy component is derived as the residual after
    subtracting the bill items users can usually read directly.
    """

    bill_items = [
        ("down_grid_landed_price_with_vat", down_grid_landed_price_with_vat),
        ("line_loss_price_with_vat", line_loss_price_with_vat),
        ("system_operation_fee_with_vat", system_operation_fee_with_vat),
        ("transmission_distribution_tariff_with_vat", transmission_distribution_tariff_with_vat),
        ("gov_fund_surcharge", gov_fund_surcharge),
    ]
    for name, value in bill_items:
        if float(value) < 0:
            raise ValueError(f"{name} must be non-negative.")
    retained_td = (
        float(transmission_distribution_tariff_with_vat)
        if green_direct_retained_transmission_distribution_tariff_with_vat is None
        else float(green_direct_retained_transmission_distribution_tariff_with_vat)
    )
    retained_fund = (
        float(gov_fund_surcharge)
        if green_direct_retained_gov_fund_surcharge is None
        else float(green_direct_retained_gov_fund_surcharge)
    )
    energy_market_price_with_vat = (
        float(down_grid_landed_price_with_vat)
        - float(line_loss_price_with_vat)
        - float(system_operation_fee_with_vat)
        - float(transmission_distribution_tariff_with_vat)
        - float(gov_fund_surcharge)
    )
    if energy_market_price_with_vat < -1e-9:
        raise ValueError(
            "down_grid_landed_price_with_vat must be greater than or equal to the sum of bill components."
        )
    return AvoidedGridPurchaseParams(
        net_avoided_grid_cost_price=None,
        energy_market_price_with_vat=max(0.0, energy_market_price_with_vat),
        line_loss_price_with_vat=float(line_loss_price_with_vat),
        system_operation_fee_with_vat=float(system_operation_fee_with_vat),
        transmission_distribution_tariff_with_vat=float(transmission_distribution_tariff_with_vat),
        gov_fund_surcharge=float(gov_fund_surcharge),
        green_direct_retained_transmission_distribution_tariff_with_vat=retained_td,
        green_direct_retained_gov_fund_surcharge=retained_fund,
        grid_purchase_vat_rate=float(grid_purchase_vat_rate),
        environmental_value_per_kwh=float(environmental_value_per_kwh),
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
