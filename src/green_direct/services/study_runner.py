"""Service-layer orchestration for study-level technical, economy, and recommendation runs."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import BinaryIO, Callable, Mapping, Any
from uuid import uuid4

import pandas as pd

from green_direct.batch.batch_runner import BatchResult, run_batch
from green_direct.economy import (
    AvoidedGridPurchaseParams,
    EconomicParams,
    evaluate_batch_economy,
    evaluate_batch_single_entity_pre_tax_economy,
)
from green_direct.io.read_curves import read_curve_set
from green_direct.models.diagnostics import InputDiagnostics
from green_direct.models.params import (
    BessParams,
    DataCleaningParams,
    PerformanceParams,
    PolicyParams,
    TimeParams,
)
from green_direct.models.scenario import Scenario
from green_direct.recommendation import (
    RecommendationParams,
    build_recommendation_result,
)

CurveSource = str | Path | BinaryIO | bytes


@dataclass(frozen=True)
class TechnicalStudyInput:
    """Inputs collected by UI/CLI for one technical study run."""

    load_source: CurveSource
    pv_source: CurveSource
    wind_source: CurveSource
    load_time_col: str
    load_value_col: str
    pv_time_col: str
    pv_value_col: str
    wind_time_col: str
    wind_value_col: str
    scenario_grid: dict
    bess_params: BessParams = field(default_factory=BessParams)
    policy_params: PolicyParams = field(default_factory=PolicyParams)
    performance_params: PerformanceParams = field(default_factory=PerformanceParams)
    cleaning_params: DataCleaningParams = field(default_factory=DataCleaningParams)
    time_params: TimeParams = field(default_factory=TimeParams)
    dt_hours: float = 1.0
    validate_length: bool = True
    config_metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TechnicalStudyResult:
    """Technical outputs produced by the baseline Wind-PV-BESS simulation."""

    study_id: str
    batch_result: BatchResult
    input_diagnostics: InputDiagnostics
    config_snapshot: dict[str, Any]

    @property
    def summary(self) -> pd.DataFrame:
        return self.batch_result.summary

    @property
    def hourly_details(self) -> dict[str, pd.DataFrame]:
        return self.batch_result.hourly_details

    @property
    def errors(self) -> pd.DataFrame:
        return self.batch_result.errors

    @property
    def warnings(self) -> list[str]:
        return [*self.input_diagnostics.warnings_as_messages(), *self.batch_result.warnings]

    @property
    def scenario_count(self) -> int:
        return self.batch_result.scenario_count


@dataclass(frozen=True)
class StudyResult:
    """Top-level study result skeleton for UI, export, and future ResultStore usage."""

    study_id: str
    input_diagnostics: InputDiagnostics = field(default_factory=InputDiagnostics)
    technical_result: TechnicalStudyResult | None = None
    economic_result: "EconomicStudyResult | None" = None
    recommendation_result: "RecommendationStudyResult | None" = None
    config_snapshot: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    result_store_refs: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_technical(cls, technical_result: TechnicalStudyResult) -> "StudyResult":
        return cls(
            study_id=technical_result.study_id,
            input_diagnostics=technical_result.input_diagnostics,
            technical_result=technical_result,
            config_snapshot=technical_result.config_snapshot,
            warnings=technical_result.warnings,
        )

    def with_economic_result(self, economic_result: "EconomicStudyResult") -> "StudyResult":
        return replace(self, economic_result=economic_result)

    def with_recommendation_result(self, recommendation_result: "RecommendationStudyResult") -> "StudyResult":
        return replace(self, recommendation_result=recommendation_result)

    @property
    def batch_result(self) -> BatchResult | None:
        return self.technical_result.batch_result if self.technical_result is not None else None

    @property
    def summary(self) -> pd.DataFrame:
        if self.technical_result is None:
            return pd.DataFrame()
        return self.technical_result.summary


def _new_study_id() -> str:
    return f"study-{uuid4().hex[:12]}"


def _build_technical_config_snapshot(
    inputs: TechnicalStudyInput,
    *,
    study_id: str,
    curve_warnings: list[str],
    curve_encodings: dict[str, str],
) -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "study_id": study_id,
        "scenario_grid": inputs.scenario_grid,
        "bess": asdict(inputs.bess_params),
        "policy": asdict(inputs.policy_params),
        "performance": asdict(inputs.performance_params),
        "time": {
            "dt_hours": inputs.dt_hours,
            "supported_hours": inputs.time_params.supported_hours,
            "validate_length": inputs.validate_length,
        },
        "curve_encodings": curve_encodings,
        "warnings": curve_warnings,
    }
    snapshot.update(dict(inputs.config_metadata))
    return snapshot


def run_technical_study(
    inputs: TechnicalStudyInput,
    *,
    study_id: str | None = None,
    progress_callback: Callable[[int, int, Scenario], None] | None = None,
) -> TechnicalStudyResult:
    """Read curves and run the baseline technical batch simulation."""

    resolved_study_id = study_id or _new_study_id()
    curve_set = read_curve_set(
        inputs.load_source,
        inputs.pv_source,
        inputs.wind_source,
        load_time_col=inputs.load_time_col,
        load_value_col=inputs.load_value_col,
        pv_time_col=inputs.pv_time_col,
        pv_value_col=inputs.pv_value_col,
        wind_time_col=inputs.wind_time_col,
        wind_value_col=inputs.wind_value_col,
        validate_length=inputs.validate_length,
        cleaning=inputs.cleaning_params,
        time_params=inputs.time_params,
    )
    batch_result = run_batch(
        curve_set.data,
        inputs.scenario_grid,
        bess_params=inputs.bess_params,
        policy_params=inputs.policy_params,
        performance_params=inputs.performance_params,
        dt_hours=inputs.dt_hours,
        progress_callback=progress_callback,
    )
    input_diagnostics = curve_set.diagnostics or InputDiagnostics()
    config_snapshot = _build_technical_config_snapshot(
        inputs,
        study_id=resolved_study_id,
        curve_warnings=curve_set.warnings,
        curve_encodings=curve_set.encodings,
    )
    return TechnicalStudyResult(
        study_id=resolved_study_id,
        batch_result=batch_result,
        input_diagnostics=input_diagnostics,
        config_snapshot=config_snapshot,
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
