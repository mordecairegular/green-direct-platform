"""Service-layer orchestration for study-level technical, economy, and recommendation runs."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import BinaryIO, Callable, Iterable, Mapping, Any
from uuid import uuid4

import pandas as pd

from green_direct.batch.batch_runner import BatchResult, run_batch
from green_direct.core.single_scenario_simulator import run_single_scenario
from green_direct.economy import (
    AvoidedGridPurchaseParams,
    EconomicParams,
    PriceCurveData,
    apply_price_curve_to_summary,
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
from green_direct.models.results import ScenarioResult
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
    retain_hourly_details: bool = True
    hourly_detail_scenario_ids: tuple[str, ...] = field(default_factory=tuple)
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
        "cleaning": asdict(inputs.cleaning_params),
        "time": {
            "dt_hours": inputs.dt_hours,
            "supported_hours": inputs.time_params.supported_hours,
            "validate_length": inputs.validate_length,
        },
        "detail_retention": {
            "retain_hourly_details": inputs.retain_hourly_details,
            "hourly_detail_scenario_ids": list(inputs.hourly_detail_scenario_ids),
        },
        "curve_columns": {
            "load": {
                "time_col": inputs.load_time_col,
                "value_col": inputs.load_value_col,
            },
            "pv": {
                "time_col": inputs.pv_time_col,
                "value_col": inputs.pv_value_col,
            },
            "wind": {
                "time_col": inputs.wind_time_col,
                "value_col": inputs.wind_value_col,
            },
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
        retain_hourly_details=inputs.retain_hourly_details,
        hourly_detail_scenario_ids=inputs.hourly_detail_scenario_ids,
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


def scenario_from_summary_row(row: Mapping[str, Any] | pd.Series) -> Scenario:
    """Rebuild a Scenario from one technical summary row."""

    data = dict(row)
    required = ["scenario_id", "pv_capacity", "wind_capacity", "bess_power", "bess_energy"]
    missing = [column for column in required if column not in data]
    if missing:
        raise ValueError(f"Summary row is missing scenario columns: {', '.join(missing)}")
    return Scenario(
        scenario_id=str(data["scenario_id"]),
        pv_capacity=float(data["pv_capacity"]),
        wind_capacity=float(data["wind_capacity"]),
        bess_power=float(data["bess_power"]),
        bess_energy=float(data["bess_energy"]),
    )


def run_hourly_detail_for_scenario(
    inputs: TechnicalStudyInput,
    *,
    scenario_id: str,
    summary: pd.DataFrame,
) -> ScenarioResult:
    """Regenerate one selected scenario's hourly ledger from saved study inputs."""

    if summary.empty or "scenario_id" not in summary.columns:
        raise ValueError("Technical summary is empty or missing scenario_id.")
    matches = summary[summary["scenario_id"].astype(str) == str(scenario_id)]
    if matches.empty:
        raise ValueError(f"Scenario is not present in the technical summary: {scenario_id}")
    scenario = scenario_from_summary_row(matches.iloc[0])
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
    return run_single_scenario(
        curve_set.data,
        scenario,
        bess_params=inputs.bess_params,
        policy_params=inputs.policy_params,
        dt_hours=inputs.dt_hours,
        retain_hourly_detail=True,
    )


@dataclass(frozen=True)
class RecommendationInputSnapshot:
    """Inputs needed to rebuild Recommendation V1 from a saved economy run."""

    economic_params: EconomicParams
    load_side_avoided_charge_price: float
    green_power_settlement_price_with_vat: float
    avoided_grid_params: AvoidedGridPurchaseParams = field(default_factory=AvoidedGridPurchaseParams)
    environmental_value_per_kwh: float = 0.0
    min_power_side_acceptable_firr: float | None = 0.07

    def to_session_dict(self) -> dict:
        return {
            "economic_params": self.economic_params,
            "load_side_avoided_charge_price": self.load_side_avoided_charge_price,
            "green_power_settlement_price_with_vat": self.green_power_settlement_price_with_vat,
            "avoided_grid_params": self.avoided_grid_params,
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
    price_mode: str = "fixed_price"
    price_curve_summary: pd.DataFrame = field(default_factory=pd.DataFrame)
    price_curve_diagnostics: InputDiagnostics = field(default_factory=InputDiagnostics)
    landed_price_summary: pd.DataFrame = field(default_factory=pd.DataFrame)


@dataclass(frozen=True)
class RecommendationStudyResult:
    """Recommendation portfolio plus diagnostic detail tables."""

    portfolio: pd.DataFrame
    load_side_detail: pd.DataFrame


def _numeric_summary_column(frame: pd.DataFrame, column: str, default: float = 0.0) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(default, index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce").fillna(default).astype(float)


def _safe_price_series(amount: pd.Series, energy: pd.Series, fallback: float) -> pd.Series:
    return pd.Series(
        [
            float(total_amount) / float(total_energy)
            if float(total_energy) > 0
            else float(fallback)
            for total_amount, total_energy in zip(amount, energy)
        ],
        index=energy.index,
        dtype=float,
    )


def _build_fixed_landed_price_summary(
    summary: pd.DataFrame,
    *,
    fixed_down_grid_landed_price_with_vat: float | None,
    fixed_green_self_use_extra_fee_with_vat: float | None,
    green_power_settlement_price_with_vat: float,
) -> pd.DataFrame:
    if fixed_down_grid_landed_price_with_vat is None:
        return pd.DataFrame()
    down_grid_price = float(fixed_down_grid_landed_price_with_vat)
    green_extra_fee = float(fixed_green_self_use_extra_fee_with_vat or 0.0)
    green_settlement_price = float(green_power_settlement_price_with_vat)
    if down_grid_price < 0:
        raise ValueError("fixed_down_grid_landed_price_with_vat must be non-negative.")
    if green_extra_fee < 0:
        raise ValueError("fixed_green_self_use_extra_fee_with_vat must be non-negative.")
    if green_settlement_price < 0:
        raise ValueError("green_power_settlement_price_with_vat must be non-negative.")

    data = summary.copy()
    if data.empty or "scenario_id" not in data.columns:
        return pd.DataFrame()
    data["scenario_id"] = data["scenario_id"].astype(str)
    total_load = _numeric_summary_column(data, "total_load_energy")
    grid_import = _numeric_summary_column(data, "grid_import_energy")
    self_use = _numeric_summary_column(data, "self_use_energy")
    green_self_use_landed_price = green_settlement_price + green_extra_fee

    before_cost = total_load * down_grid_price
    after_down_grid_cost = grid_import * down_grid_price
    after_self_use_cost = self_use * green_self_use_landed_price
    after_cost = after_down_grid_cost + after_self_use_cost
    before_price = _safe_price_series(before_cost, total_load, down_grid_price)
    after_price = _safe_price_series(after_cost, total_load, down_grid_price)
    return pd.DataFrame(
        {
            "scenario_id": data["scenario_id"],
            "price_mode": "fixed_price",
            "load_landed_price_before_green_with_vat": before_price,
            "load_landed_price_after_green_with_vat": after_price,
            "load_landed_price_delta_with_vat": after_price - before_price,
            "load_landed_cost_before_green_with_vat": before_cost,
            "load_landed_cost_after_green_with_vat": after_cost,
            "weighted_down_grid_landed_price_with_vat": down_grid_price,
            "green_power_settlement_price_with_vat_effective": green_settlement_price,
            "green_self_use_landed_price_with_vat_effective": green_self_use_landed_price,
            "down_grid_energy_for_landed_price": grid_import,
            "self_use_energy_for_landed_price": self_use,
            "total_load_energy_for_landed_price": total_load,
        }
    )


def _merge_extra_summary(base: pd.DataFrame, extra: pd.DataFrame) -> pd.DataFrame:
    if base.empty or extra.empty or "scenario_id" not in base.columns or "scenario_id" not in extra.columns:
        return base
    data = base.copy()
    data["scenario_id"] = data["scenario_id"].astype(str)
    extra_data = extra.copy()
    extra_data["scenario_id"] = extra_data["scenario_id"].astype(str)
    extra_columns = [
        column
        for column in extra_data.columns
        if column == "scenario_id" or column not in data.columns
    ]
    if extra_columns == ["scenario_id"]:
        return data
    return data.merge(extra_data[extra_columns], on="scenario_id", how="left")


def run_economic_study(
    summary: pd.DataFrame,
    *,
    economic_params: EconomicParams,
    avoided_grid_params: AvoidedGridPurchaseParams,
    load_side_avoided_charge_price: float,
    green_power_settlement_price_with_vat: float,
    environmental_value_per_kwh: float = 0.0,
    min_power_side_acceptable_firr: float | None = 0.07,
    price_curve: PriceCurveData | None = None,
    hourly_details: Mapping[str, pd.DataFrame] | None = None,
    dt_hours: float = 1.0,
    fixed_down_grid_landed_price_with_vat: float | None = None,
    fixed_green_self_use_extra_fee_with_vat: float | None = None,
    retain_annual_cashflows: bool = True,
    annual_cashflow_scenario_ids: Iterable[str] | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> EconomicStudyResult:
    """Run all currently implemented economy views for a technical summary."""

    evaluation_summary = summary
    scenario_total = len(evaluation_summary.index)
    phase_count = 3 if price_curve is not None else 2
    economy_total = max(1, scenario_total * phase_count)

    def _phase_progress(phase_name: str, offset: int) -> Callable[[int, int, str], None] | None:
        if progress_callback is None:
            return None

        def relay(done: int, total: int, scenario_id: str) -> None:
            progress_callback(
                min(economy_total, offset + done),
                economy_total,
                f"{phase_name} {done}/{total}：{scenario_id}",
            )

        return relay

    price_mode = "fixed_price"
    price_curve_summary = pd.DataFrame()
    landed_price_summary = pd.DataFrame()
    price_curve_diagnostics = InputDiagnostics()
    if price_curve is not None:
        if hourly_details is None:
            raise ValueError("启用价格曲线模式时必须提供逐小时明细，用于按方案聚合时段电价。")
        price_application = apply_price_curve_to_summary(
            summary,
            hourly_details,
            price_curve,
            economic_params=economic_params,
            avoided_grid_params=avoided_grid_params,
            load_side_avoided_charge_price=load_side_avoided_charge_price,
            green_power_settlement_price_with_vat=green_power_settlement_price_with_vat,
            environmental_value_per_kwh=environmental_value_per_kwh,
            dt_hours=dt_hours,
            progress_callback=_phase_progress("逐小时电价匹配", 0),
        )
        evaluation_summary = price_application.summary
        price_curve_summary = price_application.price_summary
        landed_price_summary = price_curve_summary
        price_curve_diagnostics = price_application.diagnostics
        price_mode = "hourly_curve"
    else:
        landed_price_summary = _build_fixed_landed_price_summary(
            summary,
            fixed_down_grid_landed_price_with_vat=fixed_down_grid_landed_price_with_vat,
            fixed_green_self_use_extra_fee_with_vat=fixed_green_self_use_extra_fee_with_vat,
            green_power_settlement_price_with_vat=green_power_settlement_price_with_vat,
        )

    power_summary, power_annual_cashflows = evaluate_batch_economy(
        evaluation_summary,
        economic_params,
        retain_annual_cashflows=retain_annual_cashflows,
        annual_cashflow_scenario_ids=annual_cashflow_scenario_ids,
        progress_callback=_phase_progress("电源侧经济性", scenario_total if price_curve is not None else 0),
    )
    power_summary = _merge_extra_summary(power_summary, landed_price_summary)
    single_entity_summary, single_entity_annual_cashflows = evaluate_batch_single_entity_pre_tax_economy(
        evaluation_summary,
        avoided_grid_params=avoided_grid_params,
        params=economic_params,
        retain_annual_cashflows=retain_annual_cashflows,
        annual_cashflow_scenario_ids=annual_cashflow_scenario_ids,
        progress_callback=_phase_progress("同一主体经济性", scenario_total * 2 if price_curve is not None else scenario_total),
    )
    single_entity_summary = _merge_extra_summary(single_entity_summary, landed_price_summary)
    return EconomicStudyResult(
        power_summary=power_summary,
        power_annual_cashflows=power_annual_cashflows,
        single_entity_summary=single_entity_summary,
        single_entity_annual_cashflows=single_entity_annual_cashflows,
        recommendation_inputs=RecommendationInputSnapshot(
            economic_params=economic_params,
            load_side_avoided_charge_price=load_side_avoided_charge_price,
            green_power_settlement_price_with_vat=green_power_settlement_price_with_vat,
            avoided_grid_params=avoided_grid_params,
            environmental_value_per_kwh=environmental_value_per_kwh,
            min_power_side_acceptable_firr=min_power_side_acceptable_firr,
        ),
        price_mode=price_mode,
        price_curve_summary=price_curve_summary,
        price_curve_diagnostics=price_curve_diagnostics,
        landed_price_summary=landed_price_summary,
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
