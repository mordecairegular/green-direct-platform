"""Trusted worker executor for internal pilot queued jobs.

This module is intentionally small: it turns the existing JobStore primitives
into one executable slice without introducing a distributed queue yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import json
from typing import Iterable

import pandas as pd

from green_direct.models.params import (
    BessParams,
    DataCleaningParams,
    PerformanceParams,
    PolicyParams,
    TimeParams,
)
from green_direct.models.pilot_backend import ArtifactKind, Job, JobArtifact, JobStatus, JobType
from green_direct.services.pilot_access import PilotAccessService
from green_direct.services.pilot_study_persistence import persist_hourly_detail_artifact
from green_direct.services.study_runner import TechnicalStudyInput, run_hourly_detail_for_scenario


@dataclass(frozen=True)
class PilotWorkerExecutionResult:
    """Outcome from one trusted worker execution attempt."""

    job: Job
    artifact: JobArtifact | None = None
    message: str = ""

    @property
    def succeeded(self) -> bool:
        return self.job.status == JobStatus.SUCCEEDED


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
