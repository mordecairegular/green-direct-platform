"""Trusted worker executor for internal pilot queued jobs.

This module is intentionally small: it turns the existing JobStore primitives
into one executable slice without introducing a distributed queue yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import json
import time
from typing import Callable
from typing import Iterable

import pandas as pd

from green_direct.economy import AvoidedGridPurchaseParams, EconomicParams, OtherOperatingRevenueItem
from green_direct.models.params import (
    BessParams,
    DataCleaningParams,
    PerformanceParams,
    PolicyParams,
    TimeParams,
)
from green_direct.models.pilot_backend import ArtifactKind, Job, JobArtifact, JobStatus, JobType
from green_direct.services.pilot_access import PilotAccessService
from green_direct.services.pilot_study_persistence import (
    persist_annual_cashflow_artifact,
    persist_hourly_detail_artifact,
)
from green_direct.services.study_runner import (
    RecommendationInputSnapshot,
    TechnicalStudyInput,
    run_economic_study,
    run_hourly_detail_for_scenario,
)


@dataclass(frozen=True)
class PilotWorkerExecutionResult:
    """Outcome from one trusted worker execution attempt."""

    job: Job
    artifact: JobArtifact | None = None
    message: str = ""

    @property
    def succeeded(self) -> bool:
        return self.job.status == JobStatus.SUCCEEDED


@dataclass(frozen=True)
class PilotWorkerLoopResult:
    """Summary from a trusted worker polling loop."""

    jobs_executed: int
    succeeded_jobs: int
    failed_jobs: int
    idle_polls: int
    stopped_reason: str
    last_result: PilotWorkerExecutionResult | None = None


def _sanitize_worker_error(exc: Exception) -> str:
    message = str(exc).replace("\r", " ").replace("\n", " ").strip()
    if not message:
        message = type(exc).__name__
    return message[:500]


def _read_artifact_payload(
    access_service: PilotAccessService,
    *,
    job: Job,
    artifact_id: str,
    expected_kind: ArtifactKind,
) -> bytes:
    artifact = access_service.result_store.load_artifact(job.project_id, job.study_id, artifact_id)
    if artifact.kind != expected_kind:
        raise ValueError(
            f"Artifact {artifact_id} must be {expected_kind.value}, got {artifact.kind.value}."
        )
    return access_service.result_store.read_artifact_payload(artifact)


def _job_input_artifact_id(job: Job, key: str, *, default: str | None = None) -> str:
    artifact_id = job.input_artifact_ids.get(key) or default
    if not artifact_id:
        raise ValueError(f"Job is missing required input artifact: {key}.")
    return artifact_id


def _load_job_payload(access_service: PilotAccessService, *, job: Job) -> dict:
    artifact_id = _job_input_artifact_id(job, "job_payload")
    payload = _read_artifact_payload(
        access_service,
        job=job,
        artifact_id=artifact_id,
        expected_kind=ArtifactKind.JOB_INPUT,
    )
    data = json.loads(payload.decode("utf-8"))
    if not isinstance(data, dict) or not data:
        raise ValueError("Job payload must be a non-empty JSON object.")
    return data


def _load_json_artifact(
    access_service: PilotAccessService,
    *,
    job: Job,
    artifact_key: str,
    expected_kind: ArtifactKind,
    default_artifact_id: str | None = None,
) -> dict:
    artifact_id = _job_input_artifact_id(job, artifact_key, default=default_artifact_id)
    payload = _read_artifact_payload(
        access_service,
        job=job,
        artifact_id=artifact_id,
        expected_kind=expected_kind,
    )
    data = json.loads(payload.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Artifact {artifact_id} must contain a JSON object.")
    return data


def _load_csv_artifact(
    access_service: PilotAccessService,
    *,
    job: Job,
    artifact_key: str,
    expected_kind: ArtifactKind,
    default_artifact_id: str | None = None,
) -> pd.DataFrame:
    artifact_id = _job_input_artifact_id(job, artifact_key, default=default_artifact_id)
    payload = _read_artifact_payload(
        access_service,
        job=job,
        artifact_id=artifact_id,
        expected_kind=expected_kind,
    )
    return pd.read_csv(BytesIO(payload))


def _optional_csv_artifact(
    access_service: PilotAccessService,
    *,
    job: Job,
    artifact_key: str,
    expected_kind: ArtifactKind,
) -> pd.DataFrame:
    artifact_id = job.input_artifact_ids.get(artifact_key)
    if not artifact_id:
        return pd.DataFrame()
    return _load_csv_artifact(
        access_service,
        job=job,
        artifact_key=artifact_key,
        expected_kind=expected_kind,
    )


def _dataclass_snapshot_kwargs(model_cls, raw: object) -> dict[str, object]:
    if not isinstance(raw, dict):
        return {}
    field_names = set(getattr(model_cls, "__dataclass_fields__", {}))
    return {str(key): value for key, value in raw.items() if str(key) in field_names}


def _coerce_supported_hours(raw: object) -> tuple[int, ...]:
    if isinstance(raw, (list, tuple)) and raw:
        try:
            return tuple(int(value) for value in raw)
        except (TypeError, ValueError):
            return TimeParams().supported_hours
    return TimeParams().supported_hours


def _curve_columns_from_config_snapshot(config_snapshot: dict) -> dict[str, tuple[str, str]]:
    raw_columns = config_snapshot.get("curve_columns")
    if not isinstance(raw_columns, dict):
        raise ValueError("config_snapshot is missing curve_columns.")
    curve_columns: dict[str, tuple[str, str]] = {}
    for curve_key in ("load", "pv", "wind"):
        raw_curve = raw_columns.get(curve_key)
        if not isinstance(raw_curve, dict):
            raise ValueError(f"config_snapshot is missing curve_columns.{curve_key}.")
        time_col = raw_curve.get("time_col")
        value_col = raw_curve.get("value_col")
        if not time_col or not value_col:
            raise ValueError(f"config_snapshot curve_columns.{curve_key} is incomplete.")
        curve_columns[curve_key] = (str(time_col), str(value_col))
    return curve_columns


def _curve_artifact_id(job: Job, config_snapshot: dict, curve_key: str) -> str:
    direct = (
        job.input_artifact_ids.get(f"input_curve_{curve_key}")
        or job.input_artifact_ids.get(curve_key)
    )
    if direct:
        return direct
    config_input_ids = config_snapshot.get("input_artifact_ids")
    if isinstance(config_input_ids, dict):
        configured = (
            config_input_ids.get(curve_key)
            or config_input_ids.get(f"input_curve_{curve_key}")
        )
        if configured:
            return str(configured)
    raise ValueError(f"Job is missing input curve artifact for {curve_key}.")


def _technical_input_from_artifacts(
    access_service: PilotAccessService,
    *,
    job: Job,
    config_snapshot: dict,
) -> TechnicalStudyInput:
    curve_columns = _curve_columns_from_config_snapshot(config_snapshot)
    payloads: dict[str, bytes] = {}
    for curve_key in ("load", "pv", "wind"):
        payloads[curve_key] = _read_artifact_payload(
            access_service,
            job=job,
            artifact_id=_curve_artifact_id(job, config_snapshot, curve_key),
            expected_kind=ArtifactKind.INPUT_CURVE,
        )

    raw_time = config_snapshot.get("time")
    time_config = raw_time if isinstance(raw_time, dict) else {}
    dt_hours = float(time_config.get("dt_hours", 1.0))
    supported_hours = _coerce_supported_hours(time_config.get("supported_hours"))
    validate_length = bool(time_config.get("validate_length", True))
    scenario_grid = config_snapshot.get("scenario_grid")
    if not isinstance(scenario_grid, dict):
        scenario_grid = {}

    return TechnicalStudyInput(
        load_source=payloads["load"],
        pv_source=payloads["pv"],
        wind_source=payloads["wind"],
        load_time_col=curve_columns["load"][0],
        load_value_col=curve_columns["load"][1],
        pv_time_col=curve_columns["pv"][0],
        pv_value_col=curve_columns["pv"][1],
        wind_time_col=curve_columns["wind"][0],
        wind_value_col=curve_columns["wind"][1],
        scenario_grid=dict(scenario_grid),
        bess_params=BessParams(**_dataclass_snapshot_kwargs(BessParams, config_snapshot.get("bess"))),
        policy_params=PolicyParams(**_dataclass_snapshot_kwargs(PolicyParams, config_snapshot.get("policy"))),
        performance_params=PerformanceParams(
            **_dataclass_snapshot_kwargs(PerformanceParams, config_snapshot.get("performance"))
        ),
        cleaning_params=DataCleaningParams(
            **_dataclass_snapshot_kwargs(DataCleaningParams, config_snapshot.get("cleaning"))
        ),
        time_params=TimeParams(dt_hours=dt_hours, supported_hours=supported_hours),
        dt_hours=dt_hours,
        validate_length=validate_length,
        retain_hourly_details=False,
        hourly_detail_scenario_ids=(),
        config_metadata={
            "restored_from_input_artifacts": True,
            "restored_study_id": job.study_id,
        },
    )


def _required_text(payload: dict, key: str) -> str:
    value = str(payload.get(key, "")).strip()
    if not value:
        raise ValueError(f"Job payload is missing required field: {key}.")
    return value


def _economic_params_from_payload(data: dict) -> EconomicParams:
    params_data = data.get("economic_params") or {}
    if not isinstance(params_data, dict):
        raise ValueError("recommendation_inputs is missing economic_params.")
    params_data = dict(params_data)
    raw_revenues = params_data.get("other_operating_revenues", ())
    if raw_revenues is None:
        params_data["other_operating_revenues"] = ()
    elif isinstance(raw_revenues, (list, tuple)):
        revenues: list[OtherOperatingRevenueItem] = []
        for item in raw_revenues:
            if isinstance(item, OtherOperatingRevenueItem):
                revenues.append(item)
                continue
            if not isinstance(item, dict):
                raise ValueError("other_operating_revenues must contain objects.")
            revenue_data = dict(item)
            specific_years = revenue_data.get("specific_years", ())
            if specific_years is None:
                revenue_data["specific_years"] = ()
            elif isinstance(specific_years, (list, tuple)):
                revenue_data["specific_years"] = tuple(int(year) for year in specific_years)
            else:
                raise ValueError("other_operating_revenues specific_years must be a list.")
            revenues.append(OtherOperatingRevenueItem(**revenue_data))
        params_data["other_operating_revenues"] = tuple(revenues)
    else:
        raise ValueError("other_operating_revenues must be a list.")
    return EconomicParams(**params_data)


def _recommendation_input_snapshot_from_artifact(
    access_service: PilotAccessService,
    *,
    job: Job,
) -> RecommendationInputSnapshot:
    payload = _read_artifact_payload(
        access_service,
        job=job,
        artifact_id=_job_input_artifact_id(job, "recommendation_inputs"),
        expected_kind=ArtifactKind.RECOMMENDATION_INPUT,
    )
    data = json.loads(payload.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("recommendation_inputs artifact must contain a JSON object.")
    avoided_grid_data = data.get("avoided_grid_params")
    if avoided_grid_data is None:
        avoided_grid_data = {
            "net_avoided_grid_cost_price": data.get("load_side_avoided_charge_price", 0.0)
        }
    if not isinstance(avoided_grid_data, dict):
        raise ValueError("recommendation_inputs.avoided_grid_params must be an object.")
    min_firr = data.get("min_power_side_acceptable_firr")
    return RecommendationInputSnapshot(
        economic_params=_economic_params_from_payload(data),
        avoided_grid_params=AvoidedGridPurchaseParams(**dict(avoided_grid_data)),
        load_side_avoided_charge_price=float(data["load_side_avoided_charge_price"]),
        green_power_settlement_price_with_vat=float(data["green_power_settlement_price_with_vat"]),
        environmental_value_per_kwh=float(data.get("environmental_value_per_kwh", 0.0)),
        min_power_side_acceptable_firr=None if min_firr is None else float(min_firr),
    )


def _assert_supported_economy_price_mode(power_summary: pd.DataFrame, scenario_id: str) -> None:
    if power_summary.empty or "price_mode" not in power_summary.columns or "scenario_id" not in power_summary.columns:
        return
    rows = power_summary[power_summary["scenario_id"].astype(str) == str(scenario_id)]
    if rows.empty:
        return
    price_modes = {str(value) for value in rows["price_mode"].dropna().tolist()}
    if "hourly_curve" in price_modes:
        raise ValueError("annual_cashflow worker does not yet support hourly_curve economy results.")


def _execute_hourly_detail_job(
    *,
    access_service: PilotAccessService,
    actor_user_id: str,
    worker_id: str,
    job: Job,
) -> PilotWorkerExecutionResult:
    payload = _load_job_payload(access_service, job=job)
    if str(payload.get("task", "")).strip() != "hourly_detail":
        raise ValueError("technical_study worker currently supports task=hourly_detail only.")
    scenario_id = _required_text(payload, "scenario_id")
    technical_result_id = str(payload.get("technical_result_id") or payload.get("result_id") or "technical_result")
    retention_days = int(payload.get("retention_days", 30))

    access_service.update_worker_job_progress(
        actor_user_id=actor_user_id,
        worker_id=worker_id,
        project_id=job.project_id,
        study_id=job.study_id,
        job_id=job.job_id,
        current=0,
        total=1,
        message="loading hourly detail inputs",
    )
    summary = _load_csv_artifact(
        access_service,
        job=job,
        artifact_key="technical_summary",
        expected_kind=ArtifactKind.TECHNICAL_SUMMARY,
        default_artifact_id="technical_summary",
    )
    config_snapshot = _load_json_artifact(
        access_service,
        job=job,
        artifact_key="config_snapshot",
        expected_kind=ArtifactKind.CONFIG_SNAPSHOT,
        default_artifact_id="config_snapshot",
    )
    inputs = _technical_input_from_artifacts(access_service, job=job, config_snapshot=config_snapshot)

    access_service.update_worker_job_progress(
        actor_user_id=actor_user_id,
        worker_id=worker_id,
        project_id=job.project_id,
        study_id=job.study_id,
        job_id=job.job_id,
        current=0,
        total=1,
        message="running hourly detail simulation",
    )
    scenario_result = run_hourly_detail_for_scenario(inputs, scenario_id=scenario_id, summary=summary)
    if scenario_result.hourly_detail.empty:
        raise ValueError(f"Scenario {scenario_id} did not produce hourly detail.")

    persisted = persist_hourly_detail_artifact(
        access_service=access_service,
        actor_user_id=job.requested_by_user_id,
        project_id=job.project_id,
        study_id=job.study_id,
        scenario_id=scenario_id,
        hourly_detail=scenario_result.hourly_detail,
        technical_result_id=technical_result_id,
        retention_days=retention_days,
        artifact_job_id=job.job_id,
    )
    access_service.update_worker_job_progress(
        actor_user_id=actor_user_id,
        worker_id=worker_id,
        project_id=job.project_id,
        study_id=job.study_id,
        job_id=job.job_id,
        current=1,
        total=1,
        message="hourly detail artifact ready",
    )
    completed = access_service.succeed_worker_job(
        actor_user_id=actor_user_id,
        worker_id=worker_id,
        project_id=job.project_id,
        study_id=job.study_id,
        job_id=job.job_id,
    )
    return PilotWorkerExecutionResult(
        job=completed,
        artifact=persisted.artifact,
        message=f"Stored hourly detail artifact: {persisted.artifact.artifact_id}",
    )


def _execute_annual_cashflow_job(
    *,
    access_service: PilotAccessService,
    actor_user_id: str,
    worker_id: str,
    job: Job,
) -> PilotWorkerExecutionResult:
    payload = _load_job_payload(access_service, job=job)
    if str(payload.get("task", "")).strip() != "annual_cashflow":
        raise ValueError("economic_study worker currently supports task=annual_cashflow only.")
    scenario_id = _required_text(payload, "scenario_id")
    economy_result_id = _required_text(payload, "economy_result_id")
    perspective = str(payload.get("perspective") or "both").strip()
    if perspective not in {"both", "power", "single_entity"}:
        raise ValueError("perspective must be 'both', 'power', or 'single_entity'.")
    retention_days = int(payload.get("retention_days", 30))

    access_service.update_worker_job_progress(
        actor_user_id=actor_user_id,
        worker_id=worker_id,
        project_id=job.project_id,
        study_id=job.study_id,
        job_id=job.job_id,
        current=0,
        total=2,
        message="loading annual cashflow inputs",
    )
    technical_summary = _load_csv_artifact(
        access_service,
        job=job,
        artifact_key="technical_summary",
        expected_kind=ArtifactKind.TECHNICAL_SUMMARY,
        default_artifact_id="technical_summary",
    )
    if "scenario_id" not in technical_summary.columns:
        raise ValueError("technical_summary is missing scenario_id.")
    selected_summary = technical_summary[technical_summary["scenario_id"].astype(str) == str(scenario_id)]
    if selected_summary.empty:
        raise ValueError(f"Scenario {scenario_id} not found in technical_summary.")
    power_summary = _optional_csv_artifact(
        access_service,
        job=job,
        artifact_key="power_economy_summary",
        expected_kind=ArtifactKind.ECONOMY_SUMMARY,
    )
    _assert_supported_economy_price_mode(power_summary, scenario_id)
    recommendation_inputs = _recommendation_input_snapshot_from_artifact(access_service, job=job)

    access_service.update_worker_job_progress(
        actor_user_id=actor_user_id,
        worker_id=worker_id,
        project_id=job.project_id,
        study_id=job.study_id,
        job_id=job.job_id,
        current=1,
        total=2,
        message="running annual cashflow evaluation",
    )
    economic_result = run_economic_study(
        selected_summary.copy(),
        economic_params=recommendation_inputs.economic_params,
        avoided_grid_params=recommendation_inputs.avoided_grid_params,
        load_side_avoided_charge_price=recommendation_inputs.load_side_avoided_charge_price,
        green_power_settlement_price_with_vat=recommendation_inputs.green_power_settlement_price_with_vat,
        environmental_value_per_kwh=recommendation_inputs.environmental_value_per_kwh,
        min_power_side_acceptable_firr=recommendation_inputs.min_power_side_acceptable_firr,
        retain_annual_cashflows=False,
        annual_cashflow_scenario_ids=[scenario_id],
    )

    stored_artifacts: list[JobArtifact] = []
    if perspective in {"both", "power"}:
        annual = economic_result.power_annual_cashflows.get(str(scenario_id))
        if annual is None or annual.empty:
            raise ValueError(f"Power-side annual cashflow was not generated for {scenario_id}.")
        persisted = persist_annual_cashflow_artifact(
            access_service=access_service,
            actor_user_id=job.requested_by_user_id,
            project_id=job.project_id,
            study_id=job.study_id,
            scenario_id=scenario_id,
            perspective="power",
            annual_cashflow=annual,
            economy_result_id=economy_result_id,
            retention_days=retention_days,
            artifact_job_id=job.job_id,
        )
        stored_artifacts.append(persisted.artifact)
    if perspective in {"both", "single_entity"}:
        annual = economic_result.single_entity_annual_cashflows.get(str(scenario_id))
        if annual is None or annual.empty:
            raise ValueError(f"Single-entity annual cashflow was not generated for {scenario_id}.")
        persisted = persist_annual_cashflow_artifact(
            access_service=access_service,
            actor_user_id=job.requested_by_user_id,
            project_id=job.project_id,
            study_id=job.study_id,
            scenario_id=scenario_id,
            perspective="single_entity",
            annual_cashflow=annual,
            economy_result_id=economy_result_id,
            retention_days=retention_days,
            artifact_job_id=job.job_id,
        )
        stored_artifacts.append(persisted.artifact)

    access_service.update_worker_job_progress(
        actor_user_id=actor_user_id,
        worker_id=worker_id,
        project_id=job.project_id,
        study_id=job.study_id,
        job_id=job.job_id,
        current=2,
        total=2,
        message="annual cashflow artifact ready",
    )
    completed = access_service.succeed_worker_job(
        actor_user_id=actor_user_id,
        worker_id=worker_id,
        project_id=job.project_id,
        study_id=job.study_id,
        job_id=job.job_id,
    )
    artifact_ids = ", ".join(artifact.artifact_id for artifact in stored_artifacts)
    return PilotWorkerExecutionResult(
        job=completed,
        artifact=stored_artifacts[-1] if stored_artifacts else None,
        message=f"Stored annual cashflow artifact(s): {artifact_ids}",
    )


def execute_claimed_worker_job(
    *,
    access_service: PilotAccessService,
    actor_user_id: str,
    worker_id: str,
    job: Job,
) -> PilotWorkerExecutionResult:
    """Execute one already-claimed running job for the trusted worker."""

    if job.status != JobStatus.RUNNING:
        raise ValueError("Worker can execute only a running claimed job.")
    if job.worker_id != worker_id:
        raise ValueError("Job is assigned to another worker.")
    if job.job_type == JobType.TECHNICAL_STUDY:
        return _execute_hourly_detail_job(
            access_service=access_service,
            actor_user_id=actor_user_id,
            worker_id=worker_id,
            job=job,
        )
    if job.job_type == JobType.ECONOMIC_STUDY:
        return _execute_annual_cashflow_job(
            access_service=access_service,
            actor_user_id=actor_user_id,
            worker_id=worker_id,
            job=job,
        )
    raise ValueError(f"Unsupported worker job type: {job.job_type.value}.")


def execute_next_worker_job(
    *,
    access_service: PilotAccessService,
    actor_user_id: str,
    worker_id: str,
    project_id: str | None = None,
    job_types: Iterable[JobType | str] | None = None,
) -> PilotWorkerExecutionResult | None:
    """Claim and execute one queued job.

    The function marks unsupported or invalid jobs failed with a sanitized error
    message, so a one-shot worker command can report the final job state.
    """

    claimed = access_service.claim_next_job_for_worker(
        actor_user_id=actor_user_id,
        worker_id=worker_id,
        project_id=project_id,
        job_types=job_types,
    )
    if claimed is None:
        return None
    try:
        return execute_claimed_worker_job(
            access_service=access_service,
            actor_user_id=actor_user_id,
            worker_id=worker_id,
            job=claimed,
        )
    except Exception as exc:  # noqa: BLE001 - worker must persist terminal state
        failed = access_service.fail_worker_job(
            actor_user_id=actor_user_id,
            worker_id=worker_id,
            project_id=claimed.project_id,
            study_id=claimed.study_id,
            job_id=claimed.job_id,
            error_message=_sanitize_worker_error(exc),
        )
        return PilotWorkerExecutionResult(
            job=failed,
            artifact=None,
            message=f"Worker job failed: {failed.error_message}",
        )


def execute_worker_loop(
    *,
    access_service: PilotAccessService,
    actor_user_id: str,
    worker_id: str,
    project_id: str | None = None,
    job_types: Iterable[JobType | str] | None = None,
    poll_interval_seconds: float = 5.0,
    max_jobs: int | None = None,
    idle_exit_after: int | None = None,
    sleep: Callable[[float], None] = time.sleep,
    on_result: Callable[[PilotWorkerExecutionResult], None] | None = None,
) -> PilotWorkerLoopResult:
    """Poll for supported queued jobs until a stop condition is reached.

    By default this is a daemon-style loop. Tests and one-shot operational
    scripts can provide max_jobs or idle_exit_after to make it finite.
    """

    if poll_interval_seconds < 0:
        raise ValueError("poll_interval_seconds must be non-negative.")
    if max_jobs is not None and max_jobs <= 0:
        raise ValueError("max_jobs must be positive when provided.")
    if idle_exit_after is not None and idle_exit_after <= 0:
        raise ValueError("idle_exit_after must be positive when provided.")

    jobs_executed = 0
    succeeded_jobs = 0
    failed_jobs = 0
    idle_polls = 0
    last_result: PilotWorkerExecutionResult | None = None
    job_type_filter = tuple(job_types) if job_types is not None else None

    while True:
        if max_jobs is not None and jobs_executed >= max_jobs:
            return PilotWorkerLoopResult(
                jobs_executed=jobs_executed,
                succeeded_jobs=succeeded_jobs,
                failed_jobs=failed_jobs,
                idle_polls=idle_polls,
                stopped_reason="max_jobs",
                last_result=last_result,
            )

        result = execute_next_worker_job(
            access_service=access_service,
            actor_user_id=actor_user_id,
            worker_id=worker_id,
            project_id=project_id,
            job_types=job_type_filter,
        )
        if result is None:
            idle_polls += 1
            if idle_exit_after is not None and idle_polls >= idle_exit_after:
                return PilotWorkerLoopResult(
                    jobs_executed=jobs_executed,
                    succeeded_jobs=succeeded_jobs,
                    failed_jobs=failed_jobs,
                    idle_polls=idle_polls,
                    stopped_reason="idle_exit_after",
                    last_result=last_result,
                )
            sleep(poll_interval_seconds)
            continue

        jobs_executed += 1
        last_result = result
        idle_polls = 0
        if result.succeeded:
            succeeded_jobs += 1
        else:
            failed_jobs += 1
        if on_result is not None:
            on_result(result)
