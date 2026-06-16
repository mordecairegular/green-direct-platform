from __future__ import annotations

from io import BytesIO

import pandas as pd

from green_direct.models.params import PolicyParams
from green_direct.models.pilot_backend import ArtifactKind, AuditAction, JobStatus, JobType, Project, User
from green_direct.services import (
    LocalJobStore,
    LocalPilotRegistry,
    LocalResultStore,
    PilotAccessService,
    TechnicalStudyInput,
    execute_next_worker_job,
    persist_technical_study_result,
    queue_job_with_input_artifact,
    run_technical_study,
)


def _access_service(tmp_path) -> PilotAccessService:
    return PilotAccessService(
        registry=LocalPilotRegistry(tmp_path),
        job_store=LocalJobStore(tmp_path),
        result_store=LocalResultStore(tmp_path),
    )


def _curve_csv(values: list[float], column: str) -> bytes:
    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=len(values), freq="h"),
            column: values,
        }
    )
    return frame.to_csv(index=False).encode("utf-8")


def _small_technical_input(*, retain_hourly_details: bool = False) -> TechnicalStudyInput:
    return TechnicalStudyInput(
        load_source=_curve_csv([10.0, 10.0], "load"),
        pv_source=_curve_csv([1.0, 0.0], "pv"),
        wind_source=_curve_csv([0.0, 1.0], "wind"),
        load_time_col="timestamp",
        load_value_col="load",
        pv_time_col="timestamp",
        pv_value_col="pv",
        wind_time_col="timestamp",
        wind_value_col="wind",
        scenario_grid={
            "pv_capacity": {"start": 0, "end": 1, "step": 1},
            "wind_capacity": {"start": 0, "end": 1, "step": 1},
            "bess_power": {"start": 0, "end": 0, "step": 1},
            "bess_duration_hours": [0],
        },
        policy_params=PolicyParams(allow_export=False),
        validate_length=False,
        retain_hourly_details=retain_hourly_details,
    )


def _project_with_admin(service: PilotAccessService) -> Project:
    service.registry.save_user(User("admin", "admin@example.local", "Admin", is_platform_admin=True))
    return service.create_project(
        actor_user_id="admin",
        project=Project("project_1", "Internal pilot project"),
    )


def test_worker_executes_hourly_detail_job_from_input_artifacts(tmp_path):
    service = _access_service(tmp_path)
    project = _project_with_admin(service)
    summary_only_input = _small_technical_input(retain_hourly_details=False)
    technical = run_technical_study(summary_only_input, study_id="study_1")
    full = run_technical_study(_small_technical_input(retain_hourly_details=True), study_id="study_full")
    selected_id = str(technical.summary["scenario_id"].iloc[-1])
    persist_technical_study_result(
        access_service=service,
        actor_user_id="admin",
        project_id=project.project_id,
        technical_result=technical,
        technical_input=summary_only_input,
    )
    queue_job_with_input_artifact(
        access_service=service,
        actor_user_id="admin",
        project_id=project.project_id,
        study_id="study_1",
        job_type=JobType.TECHNICAL_STUDY,
        payload={
            "task": "hourly_detail",
            "scenario_id": selected_id,
            "technical_result_id": "technical_result",
            "retention_days": 30,
        },
        input_artifact_ids={
            "technical_summary": "technical_summary",
            "config_snapshot": "config_snapshot",
            "input_curve_load": "input_curve_load",
            "input_curve_pv": "input_curve_pv",
            "input_curve_wind": "input_curve_wind",
        },
        job_id="job_hourly_detail_worker",
        progress_total=1,
        progress_message="hourly detail queued",
    )

    result = execute_next_worker_job(
        access_service=service,
        actor_user_id="admin",
        worker_id="worker_1",
        job_types=[JobType.TECHNICAL_STUDY],
    )

    assert result is not None
    assert result.succeeded
    assert result.job.job_id == "job_hourly_detail_worker"
    assert result.job.status == JobStatus.SUCCEEDED
    assert result.job.progress_current == 1
    assert result.job.progress_total == 1
    assert result.artifact is not None
    assert result.artifact.kind == ArtifactKind.HOURLY_DETAIL
    assert result.artifact.job_id == "job_hourly_detail_worker"
    record = service.result_store.load_result_record(project.project_id, "study_1", "technical_result")
    assert record.hourly_detail_artifact_ids == {selected_id: f"hourly_detail_{selected_id}"}
    payload = service.result_store.read_artifact_payload(result.artifact)
    hourly_detail = pd.read_csv(BytesIO(payload))
    hourly_detail["timestamp"] = pd.to_datetime(hourly_detail["timestamp"])
    pd.testing.assert_frame_equal(
        hourly_detail.reset_index(drop=True),
        full.hourly_details[selected_id].reset_index(drop=True),
        check_dtype=False,
    )
    audit_events = service.result_store.read_audit_log(project.project_id)
    assert any(
        event.action == AuditAction.STORE_ARTIFACT
        and event.job_id == "job_hourly_detail_worker"
        and event.target_id == f"hourly_detail_{selected_id}"
        for event in audit_events
    )
    assert any(
        event.action == AuditAction.COMPLETE_JOB
        and event.job_id == "job_hourly_detail_worker"
        and event.metadata["status"] == "succeeded"
        and event.metadata["worker_id"] == "worker_1"
        for event in audit_events
    )


def test_worker_marks_unsupported_job_failed(tmp_path):
    service = _access_service(tmp_path)
    project = _project_with_admin(service)
    queue_job_with_input_artifact(
        access_service=service,
        actor_user_id="admin",
        project_id=project.project_id,
        study_id="study_1",
        job_type=JobType.ECONOMIC_STUDY,
        payload={"task": "economy"},
        job_id="job_unsupported",
    )

    result = execute_next_worker_job(
        access_service=service,
        actor_user_id="admin",
        worker_id="worker_1",
        job_types=[JobType.ECONOMIC_STUDY],
    )

    assert result is not None
    assert not result.succeeded
    assert result.job.status == JobStatus.FAILED
    assert "Unsupported worker job type: economic_study" in str(result.job.error_message)
