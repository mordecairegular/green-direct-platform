"""Persistence helpers for project-scoped pilot study results."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from uuid import uuid4

from green_direct.models.pilot_backend import (
    ArtifactKind,
    Job,
    JobArtifact,
    JobType,
    StudyResultRecord,
)
from green_direct.services.local_store_utils import json_value
from green_direct.services.pilot_access import PilotAccessService
from green_direct.services.study_runner import TechnicalStudyResult


@dataclass(frozen=True)
class PersistedTechnicalStudy:
    """Project-scoped persistence refs for one completed technical study."""

    job: Job
    technical_summary_artifact: JobArtifact
    config_snapshot_artifact: JobArtifact
    result_record: StudyResultRecord
    input_fingerprint: str


def technical_input_fingerprint(technical_result: TechnicalStudyResult) -> str:
    """Build a stable fingerprint from the technical study config snapshot."""

    payload = json.dumps(
        json_value(technical_result.config_snapshot),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _technical_summary_csv(technical_result: TechnicalStudyResult) -> str:
    return technical_result.summary.to_csv(index=False)


def _config_snapshot_json(technical_result: TechnicalStudyResult) -> str:
    return json.dumps(
        json_value(technical_result.config_snapshot),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )


def persist_technical_study_result(
    *,
    access_service: PilotAccessService,
    actor_user_id: str,
    project_id: str,
    technical_result: TechnicalStudyResult,
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
            payload=_config_snapshot_json(technical_result),
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
    )
