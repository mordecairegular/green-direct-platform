"""Persistence helpers for project-scoped pilot study results."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timedelta, timezone
import hashlib
from io import BytesIO
import json
from pathlib import Path
from typing import Mapping
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from green_direct.models.pilot_backend import (
    AuditAction,
    AuditLog,
    ArtifactRetentionPolicy,
    ArtifactKind,
    Job,
    JobArtifact,
    JobType,
    StudyResultRecord,
)
from green_direct.services.local_store_utils import json_value, validate_path_segment
from green_direct.services.pilot_access import PilotAccessService
from green_direct.services.study_runner import (
    EconomicStudyResult,
    RecommendationStudyResult,
    TechnicalStudyInput,
    TechnicalStudyResult,
)


@dataclass(frozen=True)
class PersistedTechnicalStudy:
    """Project-scoped persistence refs for one completed technical study."""

    job: Job
    technical_summary_artifact: JobArtifact
    config_snapshot_artifact: JobArtifact
    result_record: StudyResultRecord
    input_fingerprint: str
    input_curve_artifacts: dict[str, JobArtifact] = field(default_factory=dict)


@dataclass(frozen=True)
class PersistedEconomicStudy:
    """Project-scoped persistence refs for one completed economy study."""

    job: Job
    power_summary_artifact: JobArtifact
    single_entity_summary_artifact: JobArtifact
    recommendation_input_artifact: JobArtifact
    power_annual_cashflow_artifact: JobArtifact | None
    single_entity_annual_cashflow_artifact: JobArtifact | None
    result_record: StudyResultRecord
    input_fingerprint: str


@dataclass(frozen=True)
class PersistedRecommendationStudy:
    """Project-scoped persistence refs for one completed recommendation build."""

    job: Job
    portfolio_artifact: JobArtifact
    load_side_detail_artifact: JobArtifact
    result_record: StudyResultRecord
    input_fingerprint: str


@dataclass(frozen=True)
class PersistedHourlyDetailArtifact:
    """Project-scoped persistence refs for one on-demand hourly detail CSV."""

    scenario_id: str
    artifact: JobArtifact
    result_record: StudyResultRecord


@dataclass(frozen=True)
class PersistedExportArtifact:
    """Project-scoped persistence refs for one explicit report/chart export."""

    artifact_key: str
    job: Job
    artifact: JobArtifact
    result_record: StudyResultRecord
    input_fingerprint: str


@dataclass(frozen=True)
class QueuedJobWithInputArtifact:
    """Queued job plus the persisted JSON payload that a worker can read later."""

    job: Job
    input_artifact: JobArtifact
    input_fingerprint: str


def _stable_hash(payload: object) -> str:
    data = json.dumps(
        json_value(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _frame_records(frame) -> list[dict]:
    return frame.astype(object).where(frame.notna(), None).to_dict(orient="records")


def technical_input_fingerprint(technical_result: TechnicalStudyResult) -> str:
    """Build a stable fingerprint from the technical study config snapshot."""

    return _stable_hash(technical_result.config_snapshot)


def economic_input_fingerprint(economic_result: EconomicStudyResult) -> str:
    """Build a stable fingerprint from economy parameters and output shape."""

    inputs = economic_result.recommendation_inputs
    return _stable_hash(
        {
            "economic_params": asdict(inputs.economic_params),
            "load_side_avoided_charge_price": inputs.load_side_avoided_charge_price,
            "green_power_settlement_price_with_vat": inputs.green_power_settlement_price_with_vat,
            "environmental_value_per_kwh": inputs.environmental_value_per_kwh,
            "min_power_side_acceptable_firr": inputs.min_power_side_acceptable_firr,
            "price_mode": economic_result.price_mode,
            "power_summary_columns": list(economic_result.power_summary.columns),
            "single_entity_summary_columns": list(economic_result.single_entity_summary.columns),
            "power_summary_rows": len(economic_result.power_summary),
            "single_entity_summary_rows": len(economic_result.single_entity_summary),
        }
    )


def recommendation_result_fingerprint(recommendation_result: RecommendationStudyResult) -> str:
    """Build a stable fingerprint from recommendation tables."""

    return _stable_hash(
        {
            "portfolio": _frame_records(recommendation_result.portfolio),
            "load_side_detail": _frame_records(recommendation_result.load_side_detail),
        }
    )


def _technical_summary_csv(technical_result: TechnicalStudyResult) -> str:
    return technical_result.summary.to_csv(index=False)


def _config_snapshot_json(
    technical_result: TechnicalStudyResult,
    *,
    input_artifact_ids: dict[str, str] | None = None,
) -> str:
    config_snapshot = json_value(technical_result.config_snapshot)
    if input_artifact_ids:
        config_snapshot = {
            **config_snapshot,
            "input_artifact_ids": dict(sorted(input_artifact_ids.items())),
        }
    return json.dumps(
        config_snapshot,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )


def _frame_csv(frame) -> str:
    return frame.to_csv(index=False)


def _recommendation_inputs_json(economic_result: EconomicStudyResult) -> str:
    inputs = economic_result.recommendation_inputs
    payload = {
        "economic_params": asdict(inputs.economic_params),
        "load_side_avoided_charge_price": inputs.load_side_avoided_charge_price,
        "green_power_settlement_price_with_vat": inputs.green_power_settlement_price_with_vat,
        "environmental_value_per_kwh": inputs.environmental_value_per_kwh,
        "min_power_side_acceptable_firr": inputs.min_power_side_acceptable_firr,
    }
    return json.dumps(
        json_value(payload),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )


def _annual_cashflows_zip(cashflows: dict[str, object]) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        for scenario_id, frame in sorted(cashflows.items()):
            scenario_key = validate_path_segment(str(scenario_id), "scenario_id")
            archive.writestr(f"{scenario_key}.csv", _frame_csv(frame))
    return buffer.getvalue()


def _artifact_expiry(retention_days: int) -> tuple[ArtifactRetentionPolicy, datetime | None]:
    if int(retention_days) <= 0:
        return ArtifactRetentionPolicy.KEEP, None
    return ArtifactRetentionPolicy.EXPIRE, datetime.now(timezone.utc) + timedelta(days=int(retention_days))


def _hourly_detail_expiry(retention_days: int) -> tuple[ArtifactRetentionPolicy, datetime | None]:
    return _artifact_expiry(retention_days)


def _source_payload_bytes(source) -> bytes:
    if isinstance(source, bytes):
        return source
    if isinstance(source, bytearray):
        return bytes(source)
    if isinstance(source, (str, Path)):
        return Path(source).read_bytes()
    if hasattr(source, "getvalue"):
        value = source.getvalue()
        return value.encode("utf-8") if isinstance(value, str) else bytes(value)
    if hasattr(source, "read"):
        position = None
        if hasattr(source, "tell") and hasattr(source, "seek"):
            try:
                position = source.tell()
                source.seek(0)
            except (OSError, ValueError):
                position = None
        value = source.read()
        if position is not None:
            try:
                source.seek(position)
            except (OSError, ValueError):
                pass
        return value.encode("utf-8") if isinstance(value, str) else bytes(value)
    raise ValueError(f"Unsupported input curve source type: {type(source).__name__}")


def _input_curve_payloads(inputs: TechnicalStudyInput) -> dict[str, bytes]:
    return {
        "load": _source_payload_bytes(inputs.load_source),
        "pv": _source_payload_bytes(inputs.pv_source),
        "wind": _source_payload_bytes(inputs.wind_source),
    }


def _audit_stored_artifact(
    *,
    access_service: PilotAccessService,
    actor_user_id: str,
    artifact: JobArtifact,
    metadata: dict,
) -> None:
    access_service.result_store.append_audit_log(
        AuditLog(
            event_id=f"audit_{uuid4().hex[:16]}",
            actor_user_id=actor_user_id,
            action=AuditAction.STORE_ARTIFACT,
            project_id=artifact.project_id,
            study_id=artifact.study_id,
            job_id=artifact.job_id,
            target_type="artifact",
            target_id=artifact.artifact_id,
            metadata=metadata,
        )
    )


def queue_job_with_input_artifact(
    *,
    access_service: PilotAccessService,
    actor_user_id: str,
    project_id: str,
    study_id: str,
    job_type: JobType | str,
    payload: Mapping[str, object],
    input_artifact_ids: Mapping[str, str] | None = None,
    job_id: str | None = None,
    payload_input_key: str = "job_payload",
    retention_days: int = 30,
    progress_total: int = 0,
    progress_message: str | None = None,
) -> QueuedJobWithInputArtifact:
    """Persist a JSON job payload artifact, then submit a queued job referencing it.

    This creates the handoff contract for a future worker. It intentionally does
    not start or execute the job inside the Streamlit request process.
    """

    access_service.require_project_job_submit(actor_user_id=actor_user_id, project_id=project_id)
    job_type = JobType(job_type)
    safe_job_id = validate_path_segment(job_id or f"job_{uuid4().hex[:16]}", "job_id")
    payload_key = str(payload_input_key).strip()
    if not payload_key:
        raise ValueError("payload_input_key must not be empty.")
    payload_mapping = json_value(dict(payload))
    if not isinstance(payload_mapping, dict) or not payload_mapping:
        raise ValueError("payload must be a non-empty mapping.")

    external_input_ids = {
        str(key).strip(): str(value).strip()
        for key, value in dict(input_artifact_ids or {}).items()
    }
    if payload_key in external_input_ids:
        raise ValueError("payload_input_key conflicts with input_artifact_ids.")
    for key, artifact_id in external_input_ids.items():
        if not key:
            raise ValueError("input_artifact_ids key must not be empty.")
        if not artifact_id:
            raise ValueError(f"input_artifact_ids[{key}] must not be empty.")
        access_service.result_store.load_artifact(project_id, study_id, artifact_id)

    input_fingerprint = _stable_hash(
        {
            "job_type": job_type.value,
            "input_artifact_ids": dict(sorted(external_input_ids.items())),
            "payload": payload_mapping,
        }
    )
    payload_text = json.dumps(
        payload_mapping,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    artifact_id = f"job_input_{safe_job_id}"
    retention_policy, expires_at = _artifact_expiry(retention_days)
    artifact = access_service.result_store.store_artifact(
        artifact_id=artifact_id,
        project_id=project_id,
        study_id=study_id,
        job_id=safe_job_id,
        kind=ArtifactKind.JOB_INPUT,
        payload=payload_text,
        filename=f"{artifact_id}.json",
        content_type="application/json",
        retention_policy=retention_policy,
        expires_at=expires_at,
    )
    _audit_stored_artifact(
        access_service=access_service,
        actor_user_id=actor_user_id,
        artifact=artifact,
        metadata={
            "kind": artifact.kind.value,
            "job_type": job_type.value,
            "payload_input_key": payload_key,
            "retention_policy": artifact.retention_policy.value,
            "size_bytes": artifact.size_bytes,
            "referenced_input_artifact_ids": dict(sorted(external_input_ids.items())),
            "sha256": artifact.sha256,
        },
    )

    job = Job(
        job_id=safe_job_id,
        project_id=project_id,
        study_id=study_id,
        requested_by_user_id=actor_user_id,
        job_type=job_type,
        input_fingerprint=input_fingerprint,
        input_artifact_ids={
            payload_key: artifact.artifact_id,
            **external_input_ids,
        },
        progress_current=0,
        progress_total=progress_total,
        progress_message=progress_message or f"{job_type.value} queued",
    )
    submitted = access_service.submit_job(actor_user_id=actor_user_id, job=job)
    return QueuedJobWithInputArtifact(
        job=submitted,
        input_artifact=artifact,
        input_fingerprint=input_fingerprint,
    )


def persist_technical_study_result(
    *,
    access_service: PilotAccessService,
    actor_user_id: str,
    project_id: str,
    technical_result: TechnicalStudyResult,
    technical_input: TechnicalStudyInput | None = None,
    input_retention_days: int = 30,
) -> PersistedTechnicalStudy:
    """Persist one technical study summary under a project-scoped Job."""

    input_fingerprint = technical_input_fingerprint(technical_result)
    job = Job(
        job_id=f"job_{uuid4().hex[:16]}",
        project_id=project_id,
        study_id=technical_result.study_id,
        requested_by_user_id=actor_user_id,
        job_type=JobType.TECHNICAL_STUDY,
        input_fingerprint=input_fingerprint,
        progress_current=0,
        progress_total=max(int(technical_result.scenario_count), 0),
        progress_message="technical study queued",
    )
    submitted = access_service.submit_job(actor_user_id=actor_user_id, job=job)
    running = access_service.start_job(
        actor_user_id=actor_user_id,
        project_id=project_id,
        study_id=technical_result.study_id,
        job_id=submitted.job_id,
    )
    try:
        access_service.update_job_progress(
            actor_user_id=actor_user_id,
            project_id=project_id,
            study_id=technical_result.study_id,
            job_id=running.job_id,
            current=technical_result.scenario_count,
            total=technical_result.scenario_count,
            message="technical study result ready",
        )
        input_curve_artifacts: dict[str, JobArtifact] = {}
        input_artifact_ids: dict[str, str] = {}
        if technical_input is not None:
            retention_policy, expires_at = _hourly_detail_expiry(input_retention_days)
            for curve_key, payload in _input_curve_payloads(technical_input).items():
                artifact_id = f"input_curve_{curve_key}"
                artifact = access_service.result_store.store_artifact(
                    artifact_id=artifact_id,
                    project_id=project_id,
                    study_id=technical_result.study_id,
                    job_id=running.job_id,
                    kind=ArtifactKind.INPUT_CURVE,
                    payload=payload,
                    filename=f"{artifact_id}.csv",
                    content_type="text/csv",
                    retention_policy=retention_policy,
                    expires_at=expires_at,
                )
                _audit_stored_artifact(
                    access_service=access_service,
                    actor_user_id=actor_user_id,
                    artifact=artifact,
                    metadata={
                        "kind": artifact.kind.value,
                        "curve": curve_key,
                        "retention_policy": artifact.retention_policy.value,
                        "size_bytes": artifact.size_bytes,
                    },
                )
                input_curve_artifacts[curve_key] = artifact
                input_artifact_ids[curve_key] = artifact.artifact_id

        summary_artifact = access_service.result_store.store_artifact(
            artifact_id="technical_summary",
            project_id=project_id,
            study_id=technical_result.study_id,
            job_id=running.job_id,
            kind=ArtifactKind.TECHNICAL_SUMMARY,
            payload=_technical_summary_csv(technical_result),
            filename="technical_summary.csv",
            content_type="text/csv",
        )
        config_artifact = access_service.result_store.store_artifact(
            artifact_id="config_snapshot",
            project_id=project_id,
            study_id=technical_result.study_id,
            job_id=running.job_id,
            kind=ArtifactKind.CONFIG_SNAPSHOT,
            payload=_config_snapshot_json(technical_result, input_artifact_ids=input_artifact_ids),
            filename="config_snapshot.json",
            content_type="application/json",
        )
        record = access_service.result_store.save_result_record(
            StudyResultRecord(
                result_id="technical_result",
                project_id=project_id,
                study_id=technical_result.study_id,
                created_by_job_id=running.job_id,
                technical_summary_artifact_id=summary_artifact.artifact_id,
            )
        )
        succeeded = access_service.succeed_job(
            actor_user_id=actor_user_id,
            project_id=project_id,
            study_id=technical_result.study_id,
            job_id=running.job_id,
        )
    except Exception as exc:
        try:
            access_service.fail_job(
                actor_user_id=actor_user_id,
                project_id=project_id,
                study_id=technical_result.study_id,
                job_id=running.job_id,
                error_message=str(exc),
            )
        except Exception:
            pass
        raise

    return PersistedTechnicalStudy(
        job=succeeded,
        technical_summary_artifact=summary_artifact,
        config_snapshot_artifact=config_artifact,
        result_record=record,
        input_fingerprint=input_fingerprint,
        input_curve_artifacts=input_curve_artifacts,
    )


def persist_hourly_detail_artifact(
    *,
    access_service: PilotAccessService,
    actor_user_id: str,
    project_id: str,
    study_id: str,
    scenario_id: str,
    hourly_detail,
    technical_job_id: str | None = None,
    technical_result_id: str = "technical_result",
    retention_days: int = 30,
    artifact_job_id: str | None = None,
) -> PersistedHourlyDetailArtifact:
    """Persist one on-demand hourly detail CSV and attach it to the technical result index."""

    access_service.require_project_job_submit(actor_user_id=actor_user_id, project_id=project_id)
    scenario_key = str(scenario_id).strip()
    if not scenario_key:
        raise ValueError("scenario_id must not be empty.")
    if getattr(hourly_detail, "empty", False):
        raise ValueError("hourly_detail must not be empty.")

    try:
        record = access_service.result_store.load_result_record(
            project_id,
            study_id,
            technical_result_id,
        )
        job_id = record.created_by_job_id
    except FileNotFoundError:
        if not technical_job_id:
            raise FileNotFoundError(
                "Technical result record is required before storing hourly detail artifacts."
            )
        record = StudyResultRecord(
            result_id=technical_result_id,
            project_id=project_id,
            study_id=study_id,
            created_by_job_id=technical_job_id,
        )
        job_id = technical_job_id

    artifact_owner_job_id = artifact_job_id or job_id
    retention_policy, expires_at = _hourly_detail_expiry(retention_days)
    artifact_id = f"hourly_detail_{scenario_key}"
    artifact = access_service.result_store.store_artifact(
        artifact_id=artifact_id,
        project_id=project_id,
        study_id=study_id,
        job_id=artifact_owner_job_id,
        kind=ArtifactKind.HOURLY_DETAIL,
        payload=_frame_csv(hourly_detail),
        filename=f"{artifact_id}.csv",
        content_type="text/csv",
        retention_policy=retention_policy,
        expires_at=expires_at,
        overwrite=True,
    )
    next_record = replace(
        record,
        hourly_detail_artifact_ids={
            **record.hourly_detail_artifact_ids,
            scenario_key: artifact.artifact_id,
        },
    )
    saved_record = access_service.result_store.save_result_record(next_record, overwrite=True)
    access_service.result_store.append_audit_log(
        AuditLog(
            event_id=f"audit_{uuid4().hex[:16]}",
            actor_user_id=actor_user_id,
            action=AuditAction.STORE_ARTIFACT,
            project_id=project_id,
            study_id=study_id,
            job_id=artifact_owner_job_id,
            target_type="artifact",
            target_id=artifact.artifact_id,
            metadata={
                "kind": artifact.kind.value,
                "scenario_id": scenario_key,
                "retention_policy": artifact.retention_policy.value,
                "attached_result_id": technical_result_id,
            },
        )
    )

    return PersistedHourlyDetailArtifact(
        scenario_id=scenario_key,
        artifact=artifact,
        result_record=saved_record,
    )


def persist_export_artifact(
    *,
    access_service: PilotAccessService,
    actor_user_id: str,
    project_id: str,
    study_id: str,
    artifact_key: str,
    payload: bytes | str,
    filename: str,
    content_type: str,
    artifact_kind: ArtifactKind | str = ArtifactKind.REPORT,
    metadata: dict | None = None,
    retention_days: int = 7,
) -> PersistedExportArtifact:
    """Persist one user-requested chart/report export as a project-scoped artifact."""

    artifact_kind = ArtifactKind(artifact_kind)
    if artifact_kind not in {ArtifactKind.CHART_PACKAGE, ArtifactKind.REPORT}:
        raise ValueError("artifact_kind must be chart_package or report.")
    artifact_key = validate_path_segment(str(artifact_key).strip(), "artifact_key")
    safe_filename = validate_path_segment(str(filename).strip(), "filename")
    if not artifact_key:
        raise ValueError("artifact_key must not be empty.")
    payload_bytes = payload.encode("utf-8") if isinstance(payload, str) else bytes(payload)
    if not payload_bytes:
        raise ValueError("payload must not be empty.")

    metadata_payload = json_value(metadata or {})
    if not isinstance(metadata_payload, dict):
        raise ValueError("metadata must be a mapping.")
    payload_sha256 = hashlib.sha256(payload_bytes).hexdigest()
    input_fingerprint = _stable_hash(
        {
            "artifact_key": artifact_key,
            "artifact_kind": artifact_kind.value,
            "content_type": content_type,
            "filename": safe_filename,
            "metadata": metadata_payload,
            "payload_sha256": payload_sha256,
            "size_bytes": len(payload_bytes),
        }
    )
    job_type = JobType.CHART_EXPORT if artifact_kind == ArtifactKind.CHART_PACKAGE else JobType.REPORT_EXPORT
    job = Job(
        job_id=f"job_{uuid4().hex[:16]}",
        project_id=project_id,
        study_id=study_id,
        requested_by_user_id=actor_user_id,
        job_type=job_type,
        input_fingerprint=input_fingerprint,
        progress_current=0,
        progress_total=1,
        progress_message="export artifact queued",
    )
    submitted = access_service.submit_job(actor_user_id=actor_user_id, job=job)
    running = access_service.start_job(
        actor_user_id=actor_user_id,
        project_id=project_id,
        study_id=study_id,
        job_id=submitted.job_id,
    )
    artifact_id = f"{artifact_key}_{running.job_id}"
    result_id = f"export_result_{running.job_id}"
    retention_policy, expires_at = _artifact_expiry(retention_days)
    try:
        artifact = access_service.result_store.store_artifact(
            artifact_id=artifact_id,
            project_id=project_id,
            study_id=study_id,
            job_id=running.job_id,
            kind=artifact_kind,
            payload=payload_bytes,
            filename=safe_filename,
            content_type=content_type,
            retention_policy=retention_policy,
            expires_at=expires_at,
        )
        _audit_stored_artifact(
            access_service=access_service,
            actor_user_id=actor_user_id,
            artifact=artifact,
            metadata={
                **metadata_payload,
                "artifact_key": artifact_key,
                "job_type": job_type.value,
                "kind": artifact.kind.value,
                "retention_policy": artifact.retention_policy.value,
                "size_bytes": artifact.size_bytes,
                "sha256": artifact.sha256,
            },
        )
        access_service.update_job_progress(
            actor_user_id=actor_user_id,
            project_id=project_id,
            study_id=study_id,
            job_id=running.job_id,
            current=1,
            total=1,
            message="export artifact ready",
        )
        record = access_service.result_store.save_result_record(
            StudyResultRecord(
                result_id=result_id,
                project_id=project_id,
                study_id=study_id,
                created_by_job_id=running.job_id,
                report_artifact_ids={artifact_key: artifact.artifact_id},
            )
        )
        succeeded = access_service.succeed_job(
            actor_user_id=actor_user_id,
            project_id=project_id,
            study_id=study_id,
            job_id=running.job_id,
        )
    except Exception as exc:
        try:
            access_service.fail_job(
                actor_user_id=actor_user_id,
                project_id=project_id,
                study_id=study_id,
                job_id=running.job_id,
                error_message=str(exc),
            )
        except Exception:
            pass
        raise

    return PersistedExportArtifact(
        artifact_key=artifact_key,
        job=succeeded,
        artifact=artifact,
        result_record=record,
        input_fingerprint=input_fingerprint,
    )


def persist_economic_study_result(
    *,
    access_service: PilotAccessService,
    actor_user_id: str,
    project_id: str,
    study_id: str,
    economic_result: EconomicStudyResult,
) -> PersistedEconomicStudy:
    """Persist one economy study summary under a project-scoped Job."""

    input_fingerprint = economic_input_fingerprint(economic_result)
    cashflow_artifact_count = int(bool(economic_result.power_annual_cashflows)) + int(
        bool(economic_result.single_entity_annual_cashflows)
    )
    progress_total = 3 + cashflow_artifact_count
    job = Job(
        job_id=f"job_{uuid4().hex[:16]}",
        project_id=project_id,
        study_id=study_id,
        requested_by_user_id=actor_user_id,
        job_type=JobType.ECONOMIC_STUDY,
        input_fingerprint=input_fingerprint,
        progress_current=0,
        progress_total=progress_total,
        progress_message="economic study queued",
    )
    submitted = access_service.submit_job(actor_user_id=actor_user_id, job=job)
    running = access_service.start_job(
        actor_user_id=actor_user_id,
        project_id=project_id,
        study_id=study_id,
        job_id=submitted.job_id,
    )
    power_artifact_id = f"economy_summary_{running.job_id}"
    single_entity_artifact_id = f"single_entity_summary_{running.job_id}"
    recommendation_input_artifact_id = f"recommendation_inputs_{running.job_id}"
    power_cashflow_artifact_id = f"power_annual_cashflows_{running.job_id}"
    single_entity_cashflow_artifact_id = f"single_entity_annual_cashflows_{running.job_id}"
    result_id = f"economy_result_{running.job_id}"
    power_cashflow_artifact = None
    single_entity_cashflow_artifact = None
    annual_cashflow_artifact_ids: dict[str, str] = {}
    try:
        recommendation_input_artifact = access_service.result_store.store_artifact(
            artifact_id=recommendation_input_artifact_id,
            project_id=project_id,
            study_id=study_id,
            job_id=running.job_id,
            kind=ArtifactKind.RECOMMENDATION_INPUT,
            payload=_recommendation_inputs_json(economic_result),
            filename="recommendation_inputs.json",
            content_type="application/json",
        )
        access_service.update_job_progress(
            actor_user_id=actor_user_id,
            project_id=project_id,
            study_id=study_id,
            job_id=running.job_id,
            current=1,
            total=progress_total,
            message="recommendation input snapshot ready",
        )
        power_artifact = access_service.result_store.store_artifact(
            artifact_id=power_artifact_id,
            project_id=project_id,
            study_id=study_id,
            job_id=running.job_id,
            kind=ArtifactKind.ECONOMY_SUMMARY,
            payload=_frame_csv(economic_result.power_summary),
            filename="power_economy_summary.csv",
            content_type="text/csv",
        )
        access_service.update_job_progress(
            actor_user_id=actor_user_id,
            project_id=project_id,
            study_id=study_id,
            job_id=running.job_id,
            current=2,
            total=progress_total,
            message="power-side economy summary ready",
        )
        single_entity_artifact = access_service.result_store.store_artifact(
            artifact_id=single_entity_artifact_id,
            project_id=project_id,
            study_id=study_id,
            job_id=running.job_id,
            kind=ArtifactKind.ECONOMY_SUMMARY,
            payload=_frame_csv(economic_result.single_entity_summary),
            filename="single_entity_summary.csv",
            content_type="text/csv",
        )
        access_service.update_job_progress(
            actor_user_id=actor_user_id,
            project_id=project_id,
            study_id=study_id,
            job_id=running.job_id,
            current=3,
            total=progress_total,
            message="economy summaries ready",
        )
        progress_current = 3
        if economic_result.power_annual_cashflows:
            power_cashflow_artifact = access_service.result_store.store_artifact(
                artifact_id=power_cashflow_artifact_id,
                project_id=project_id,
                study_id=study_id,
                job_id=running.job_id,
                kind=ArtifactKind.ANNUAL_CASHFLOW,
                payload=_annual_cashflows_zip(economic_result.power_annual_cashflows),
                filename="power_annual_cashflows.zip",
                content_type="application/zip",
            )
            annual_cashflow_artifact_ids["power"] = power_cashflow_artifact.artifact_id
            progress_current += 1
            access_service.update_job_progress(
                actor_user_id=actor_user_id,
                project_id=project_id,
                study_id=study_id,
                job_id=running.job_id,
                current=progress_current,
                total=progress_total,
                message="power-side annual cashflows ready",
            )
        if economic_result.single_entity_annual_cashflows:
            single_entity_cashflow_artifact = access_service.result_store.store_artifact(
                artifact_id=single_entity_cashflow_artifact_id,
                project_id=project_id,
                study_id=study_id,
                job_id=running.job_id,
                kind=ArtifactKind.ANNUAL_CASHFLOW,
                payload=_annual_cashflows_zip(economic_result.single_entity_annual_cashflows),
                filename="single_entity_annual_cashflows.zip",
                content_type="application/zip",
            )
            annual_cashflow_artifact_ids["single_entity"] = single_entity_cashflow_artifact.artifact_id
            progress_current += 1
            access_service.update_job_progress(
                actor_user_id=actor_user_id,
                project_id=project_id,
                study_id=study_id,
                job_id=running.job_id,
                current=progress_current,
                total=progress_total,
                message="single-entity annual cashflows ready",
            )
        if progress_current == 3:
            access_service.update_job_progress(
                actor_user_id=actor_user_id,
                project_id=project_id,
                study_id=study_id,
                job_id=running.job_id,
                current=progress_current,
                total=progress_total,
                message="economic study result ready",
            )
        record = access_service.result_store.save_result_record(
            StudyResultRecord(
                result_id=result_id,
                project_id=project_id,
                study_id=study_id,
                created_by_job_id=running.job_id,
                economy_summary_artifact_id=power_artifact.artifact_id,
                single_entity_summary_artifact_id=single_entity_artifact.artifact_id,
                recommendation_input_artifact_id=recommendation_input_artifact.artifact_id,
                annual_cashflow_artifact_ids=annual_cashflow_artifact_ids,
            )
        )
        succeeded = access_service.succeed_job(
            actor_user_id=actor_user_id,
            project_id=project_id,
            study_id=study_id,
            job_id=running.job_id,
        )
    except Exception as exc:
        try:
            access_service.fail_job(
                actor_user_id=actor_user_id,
                project_id=project_id,
                study_id=study_id,
                job_id=running.job_id,
                error_message=str(exc),
            )
        except Exception:
            pass
        raise

    return PersistedEconomicStudy(
        job=succeeded,
        power_summary_artifact=power_artifact,
        single_entity_summary_artifact=single_entity_artifact,
        recommendation_input_artifact=recommendation_input_artifact,
        power_annual_cashflow_artifact=power_cashflow_artifact,
        single_entity_annual_cashflow_artifact=single_entity_cashflow_artifact,
        result_record=record,
        input_fingerprint=input_fingerprint,
    )


def persist_recommendation_study_result(
    *,
    access_service: PilotAccessService,
    actor_user_id: str,
    project_id: str,
    study_id: str,
    recommendation_result: RecommendationStudyResult,
) -> PersistedRecommendationStudy:
    """Persist one recommendation portfolio under a project-scoped Job."""

    input_fingerprint = recommendation_result_fingerprint(recommendation_result)
    job = Job(
        job_id=f"job_{uuid4().hex[:16]}",
        project_id=project_id,
        study_id=study_id,
        requested_by_user_id=actor_user_id,
        job_type=JobType.RECOMMENDATION,
        input_fingerprint=input_fingerprint,
        progress_current=0,
        progress_total=2,
        progress_message="recommendation build queued",
    )
    submitted = access_service.submit_job(actor_user_id=actor_user_id, job=job)
    running = access_service.start_job(
        actor_user_id=actor_user_id,
        project_id=project_id,
        study_id=study_id,
        job_id=submitted.job_id,
    )
    portfolio_artifact_id = f"recommendation_portfolio_{running.job_id}"
    detail_artifact_id = f"recommendation_load_side_detail_{running.job_id}"
    result_id = f"recommendation_result_{running.job_id}"
    try:
        portfolio_artifact = access_service.result_store.store_artifact(
            artifact_id=portfolio_artifact_id,
            project_id=project_id,
            study_id=study_id,
            job_id=running.job_id,
            kind=ArtifactKind.RECOMMENDATION_PORTFOLIO,
            payload=_frame_csv(recommendation_result.portfolio),
            filename="recommendation_portfolio.csv",
            content_type="text/csv",
        )
        detail_artifact = access_service.result_store.store_artifact(
            artifact_id=detail_artifact_id,
            project_id=project_id,
            study_id=study_id,
            job_id=running.job_id,
            kind=ArtifactKind.RECOMMENDATION_PORTFOLIO,
            payload=_frame_csv(recommendation_result.load_side_detail),
            filename="recommendation_load_side_detail.csv",
            content_type="text/csv",
        )
        access_service.update_job_progress(
            actor_user_id=actor_user_id,
            project_id=project_id,
            study_id=study_id,
            job_id=running.job_id,
            current=2,
            total=2,
            message="recommendation result ready",
        )
        record = access_service.result_store.save_result_record(
            StudyResultRecord(
                result_id=result_id,
                project_id=project_id,
                study_id=study_id,
                created_by_job_id=running.job_id,
                recommendation_artifact_id=portfolio_artifact.artifact_id,
                report_artifact_ids={"load_side_detail": detail_artifact.artifact_id},
            )
        )
        succeeded = access_service.succeed_job(
            actor_user_id=actor_user_id,
            project_id=project_id,
            study_id=study_id,
            job_id=running.job_id,
        )
    except Exception as exc:
        try:
            access_service.fail_job(
                actor_user_id=actor_user_id,
                project_id=project_id,
                study_id=study_id,
                job_id=running.job_id,
                error_message=str(exc),
            )
        except Exception:
            pass
        raise

    return PersistedRecommendationStudy(
        job=succeeded,
        portfolio_artifact=portfolio_artifact,
        load_side_detail_artifact=detail_artifact,
        result_record=record,
        input_fingerprint=input_fingerprint,
    )
