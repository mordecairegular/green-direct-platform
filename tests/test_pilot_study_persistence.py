import pandas as pd
import pytest

from green_direct.batch.batch_runner import BatchResult
from green_direct.models.diagnostics import InputDiagnostics
from green_direct.models.pilot_backend import (
    ArtifactKind,
    AuditAction,
    JobStatus,
    Project,
    ProjectRole,
    User,
)
from green_direct.services import (
    LocalJobStore,
    LocalPilotRegistry,
    LocalResultStore,
    PilotAccessError,
    PilotAccessService,
    persist_technical_study_result,
    technical_input_fingerprint,
)
from green_direct.services.study_runner import TechnicalStudyResult


def _access_service(tmp_path) -> PilotAccessService:
    return PilotAccessService(
        registry=LocalPilotRegistry(tmp_path),
        job_store=LocalJobStore(tmp_path),
        result_store=LocalResultStore(tmp_path),
    )


def _technical_result(study_id: str = "study_1") -> TechnicalStudyResult:
    summary = pd.DataFrame(
        [
            {
                "scenario_id": "S0001",
                "pv_capacity": 5.0,
                "wind_capacity": 2.0,
                "bess_power": 1.0,
                "green_load_rate": 0.42,
            }
        ]
    )
    return TechnicalStudyResult(
        study_id=study_id,
        batch_result=BatchResult(
            summary=summary,
            hourly_details={},
            errors=pd.DataFrame(),
            warnings=[],
            scenario_count=1,
        ),
        input_diagnostics=InputDiagnostics(),
        config_snapshot={
            "study_id": study_id,
            "scenario_grid": {"pv_capacity": {"start": 5, "end": 5, "step": 1}},
            "detail_retention": {"retain_hourly_details": False},
        },
    )


def test_persist_technical_study_result_writes_job_artifacts_and_record(tmp_path):
    service = _access_service(tmp_path)
    service.registry.save_user(User("admin", "admin@example.local", "Admin"))
    project = service.create_project(
        actor_user_id="admin",
        project=Project("project_1", "Internal pilot project"),
    )
    technical_result = _technical_result()

    persisted = persist_technical_study_result(
        access_service=service,
        actor_user_id="admin",
        project_id=project.project_id,
        technical_result=technical_result,
    )

    loaded_job = service.job_store.load_job(project.project_id, "study_1", persisted.job.job_id)
    summary_artifact = service.result_store.load_artifact(project.project_id, "study_1", "technical_summary")
    config_artifact = service.result_store.load_artifact(project.project_id, "study_1", "config_snapshot")
    result_record = service.result_store.load_result_record(project.project_id, "study_1", "technical_result")

    assert loaded_job.status == JobStatus.SUCCEEDED
    assert loaded_job.input_fingerprint == technical_input_fingerprint(technical_result)
    assert summary_artifact.kind == ArtifactKind.TECHNICAL_SUMMARY
    assert config_artifact.kind == ArtifactKind.CONFIG_SNAPSHOT
    assert service.result_store.read_artifact_payload(summary_artifact).decode("utf-8").startswith("scenario_id")
    assert '"study_id": "study_1"' in service.result_store.read_artifact_payload(config_artifact).decode("utf-8")
    assert result_record.created_by_job_id == persisted.job.job_id
    assert result_record.technical_summary_artifact_id == "technical_summary"
    assert any(
        event.action == AuditAction.SUBMIT_JOB
        for event in service.result_store.read_audit_log(project.project_id)
    )
    assert any(
        event.action == AuditAction.COMPLETE_JOB
        for event in service.result_store.read_audit_log(project.project_id)
    )


def test_persist_technical_study_result_rejects_viewer(tmp_path):
    service = _access_service(tmp_path)
    service.registry.save_user(User("admin", "admin@example.local", "Admin"))
    service.registry.save_user(User("viewer", "viewer@example.local", "Viewer"))
    project = service.create_project(
        actor_user_id="admin",
        project=Project("project_1", "Internal pilot project"),
    )
    service.grant_project_role(
        actor_user_id="admin",
        project_id=project.project_id,
        user_id="viewer",
        role=ProjectRole.VIEWER,
    )

    with pytest.raises(PilotAccessError, match="cannot submit jobs"):
        persist_technical_study_result(
            access_service=service,
            actor_user_id="viewer",
            project_id=project.project_id,
            technical_result=_technical_result(),
        )

    assert service.job_store.list_project_jobs(project.project_id) == []
