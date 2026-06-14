"""Economic input models for V1 annual cash-flow evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class OtherOperatingRevenueItem:
    """User-entered other operating revenue item.

    Amounts are in 万元/year. Negative values are treated as revenue offsets
    or operating cash outflows and do not create input VAT in V1.
    """

    name: str
    amount_with_vat: float
    vat_rate: float = 0.13
    active_rule: str = "every_year"
    specific_years: tuple[int, ...] = field(default_factory=tuple)

    def is_active(self, operation_year: int) -> bool:
        if self.active_rule == "every_year":
            return True
        if self.active_rule == "first_20_years":
            return operation_year <= 20
        if self.active_rule == "first_25_years":
            return operation_year <= 25
        if self.active_rule == "specific_years":
            return operation_year in set(self.specific_years)
        return False


@dataclass(frozen=True)
class AvoidedGridPurchaseParams:
    """Inputs for avoided grid-purchase savings in the single-entity view.

    Prices use yuan/kWh. Scenario energy uses the project unit 万kWh, so
    energy * price naturally gives 万元.
    """

    net_avoided_grid_cost_price: float | None = None
    energy_market_price_with_vat: float = 0.0
    line_loss_price_with_vat: float = 0.0
    system_operation_fee_with_vat: float = 0.0
    transmission_distribution_tariff_with_vat: float = 0.0
    gov_fund_surcharge: float = 0.0
    green_direct_retained_transmission_distribution_tariff_with_vat: float = 0.0
    green_direct_retained_gov_fund_surcharge: float = 0.0
    grid_purchase_vat_rate: float = 0.13
    environmental_value_per_kwh: float = 0.0


@dataclass(frozen=True)
class EconomicParams:
    """V1 simplified annual project cash-flow parameters.

    Project technical capacities use the existing project units:
    万千瓦 for power and 万千瓦时 for energy. Economic outputs are 万元.
    """

    operation_years: int = 25
    wind_capex_per_kw_with_vat: float = 5000.0
    pv_capex_per_kw_with_vat: float = 2800.0
    bess_capex_per_kwh_with_vat: float = 900.0
    dedicated_connection_line_investment_with_vat: float = 0.0
    other_fixed_asset_investment_with_vat: float = 0.0
    construction_input_vat_rate: float = 0.10
    construction_input_vat_deductible: bool = True

    wind_om_cost_per_kw_year: float = 50.0
    pv_om_cost_per_kw_year: float = 25.0
    bess_om_cost_per_kw_year: float = 18.0
    other_operating_cost_with_vat: float = 0.0

    grid_export_price_with_vat: float = 0.25
    self_use_price_with_vat: float = 0.40
    output_vat_rate: float = 0.13
    other_operating_revenues: tuple[OtherOperatingRevenueItem, ...] = field(default_factory=tuple)

    bess_replacement_cost_ratio: float = 0.50
    bess_replacement_input_vat_rate: float = 0.13
    bess_replacement_input_vat_deductible: bool = True
    bess_cycle_life: float = 6000.0
    bess_calendar_life_years: float = 15.0

    urban_maintenance_tax_rate: float = 0.05
    education_surcharge_rate: float = 0.03
    local_education_surcharge_rate: float = 0.02
    income_tax_rate: float = 0.25
    loss_carryforward_years: int = 5
    discount_rate: float = 0.06
