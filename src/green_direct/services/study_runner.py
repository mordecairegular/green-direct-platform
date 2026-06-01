"""Service-layer orchestration for study-level economy and recommendation runs."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from green_direct.economy import (
    AvoidedGridPurchaseParams,
    EconomicParams,
    evaluate_batch_economy,
    evaluate_batch_single_entity_pre_tax_economy,
)
from green_direct.recommendation import (
    RecommendationParams,
    build_recommendation_result,
)


@dataclass(frozen=True)
class RecommendationInputSnapshot:
    """Inputs needed to rebuild Recommendation V1 from a saved economy run."""

    economic_params: EconomicParams
    load_side_avoided_charge_price: float
    green_power_settlement_price_with_vat: float
    environmental_value_per_kwh: float = 0.0
    min_power_side_acceptable_firr: float | None = 0.07

    def to_session_dict(self) -> dict:
        return {
            "economic_params": self.economic_params,
            "load_side_avoided_charge_price": self.load_side_avoided_charge_price,
            "green_power_settlement_price_with_vat": self.green_power_settlement_price_with_vat,
            "environmental_value_per_kwh": self.environmental_value_per_kwh,
            "min_power_side_acceptable_firr": self.min_power_side_acceptable_firr,
        }

    def to_recommendation_params(
        self,
        *,
        single_entity_view: str = "firr",
        engineering_view: str = "min_investment",
    ) -> RecommendationParams:
        return RecommendationParams(
            load_side_avoided_charge_price=self.load_side_avoided_charge_price,
            green_power_settlement_price_with_vat=self.green_power_settlement_price_with_vat,
            environmental_value_per_kwh=self.environmental_value_per_kwh,
            min_power_side_acceptable_firr=self.min_power_side_acceptable_firr,
            single_entity_view=single_entity_view,
            engineering_view=engineering_view,
        )


@dataclass(frozen=True)
class EconomicStudyResult:
    """All outputs produced by one economy run."""

    power_summary: pd.DataFrame
    power_annual_cashflows: dict[str, pd.DataFrame]
    single_entity_summary: pd.DataFrame
    single_entity_annual_cashflows: dict[str, pd.DataFrame]
    recommendation_inputs: RecommendationInputSnapshot


@dataclass(frozen=True)
class RecommendationStudyResult:
    """Recommendation portfolio plus diagnostic detail tables."""

    portfolio: pd.DataFrame
    load_side_detail: pd.DataFrame


def run_economic_study(
    summary: pd.DataFrame,
    *,
    economic_params: EconomicParams,
    avoided_grid_params: AvoidedGridPurchaseParams,
    load_side_avoided_charge_price: float,
    green_power_settlement_price_with_vat: float,
    environmental_value_per_kwh: float = 0.0,
    min_power_side_acceptable_firr: float | None = 0.07,
) -> EconomicStudyResult:
    """Run all currently implemented economy views for a technical summary."""

    power_summary, power_annual_cashflows = evaluate_batch_economy(summary, economic_params)
    single_entity_summary, single_entity_annual_cashflows = evaluate_batch_single_entity_pre_tax_economy(
        summary,
        avoided_grid_params=avoided_grid_params,
        params=economic_params,
    )
    return EconomicStudyResult(
        power_summary=power_summary,
        power_annual_cashflows=power_annual_cashflows,
        single_entity_summary=single_entity_summary,
        single_entity_annual_cashflows=single_entity_annual_cashflows,
        recommendation_inputs=RecommendationInputSnapshot(
            economic_params=economic_params,
            load_side_avoided_charge_price=load_side_avoided_charge_price,
            green_power_settlement_price_with_vat=green_power_settlement_price_with_vat,
            environmental_value_per_kwh=environmental_value_per_kwh,
            min_power_side_acceptable_firr=min_power_side_acceptable_firr,
        ),
    )


def build_recommendation_study(
    summary: pd.DataFrame,
    power_economy_summary: pd.DataFrame,
    recommendation_inputs: RecommendationInputSnapshot,
    *,
    single_entity_summary: pd.DataFrame | None = None,
    single_entity_view: str = "firr",
    engineering_view: str = "min_investment",
) -> RecommendationStudyResult:
    """Build Recommendation V1 outputs from technical and economy summaries."""

    portfolio, load_side_detail = build_recommendation_result(
        summary,
        power_economy_summary,
        recommendation_inputs.to_recommendation_params(
            single_entity_view=single_entity_view,
            engineering_view=engineering_view,
        ),
        single_entity_summary=single_entity_summary,
        economic_params=recommendation_inputs.economic_params,
    )
    return RecommendationStudyResult(
        portfolio=portfolio,
        load_side_detail=load_side_detail,
    )
