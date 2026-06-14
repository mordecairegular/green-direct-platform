from datetime import datetime, timezone

import pytest

from green_direct.models.pilot_backend import (
    ArtifactKind,
    AuditAction,
    AuditLog,
    Job,
    JobArtifact,
    JobStatus,
    JobType,
    Project,
    ProjectMembership,
    ProjectRole,
    ProjectStudy,
    StudyResultRecord,
    User,
)


def _dt(hour: int) -> datetime:
    return datetime(2026, 6, 15, hour, tzinfo=timezone.utc)


def test_membership_permissions_distinguish_admin_analyst_and_viewer():
    admin = ProjectMembership("m_admin", "p1", "u1", ProjectRole.ADMIN)
    analyst = ProjectMembership("m_analyst", "p1", "u2", "analyst")
    viewer = ProjectMembership("m_viewer", "p1", "u3", ProjectRole.VIEWER)
    disabled = ProjectMembership("m_disabled", "p1", "u4", ProjectRole.ADMIN, status="disabled")

    assert admin.can_view_project()
    assert admin.can_submit_jobs()
    assert admin.can_manage_project()

    assert analyst.can_view_project()
    assert analyst.can_submit_jobs()
    assert not analyst.can_manage_project()

    assert viewer.can_view_project()
    assert not viewer.can_submit_jobs()
    assert not viewer.can_manage_project()

    assert not disabled.can_view_project()
    assert not disabled.can_submit_jobs()
    assert not disabled.can_manage_project()


def test_job_lifecycle_keeps_project_scope_and_blocks_invalid_transitions():
    job = Job(
        job_id="job_1",
        project_id="project_1",
        study_id="study_1",
        requested_by_user_id="user_1",
        job_type=JobType.TECHNICAL_STUDY,
        queued_at=_dt(1),
    )

    running = job.start(started_at=_dt(2))
    succeeded = running.succeed(finished_at=_dt(3))

    assert running.status == JobStatus.RUNNING
    assert running.project_id == "project_1"
    assert succeeded.status == JobStatus.SUCCEEDED
    assert succeeded.is_terminal
    assert succeeded.started_at == _dt(2)
    assert succeeded.finished_at == _dt(3)

    with pytest.raises(ValueError, match="Only running jobs can fail"):
        succeeded.fail("should not be accepted")

    with pytest.raises(ValueError, match="Terminal jobs cannot be canceled"):
        succeeded.cancel()


def test_failed_job_requires_error_message():
    running = Job(
        job_id="job_2",
        project_id="project_1",
        study_id="study_1",
        requested_by_user_id="user_1",
        job_type="economic_study",
    ).start(started_at=_dt(4))

    failed = running.fail("price curve missing", finished_at=_dt(5))

    assert failed.status == JobStatus.FAILED
    assert failed.error_message == "price curve missing"
    assert failed.is_terminal

    with pytest.raises(ValueError, match="error_message must not be empty"):
        running.fail("")


def test_project_study_artifact_and_result_record_preserve_project_boundary():
    user = User("user_1", "analyst@example.local", "Analyst")
    project = Project("project_1", "Internal pilot project", created_by_user_id=user.user_id)
    study = ProjectStudy(
        "study_1",
        project.project_id,
        user.user_id,
        input_fingerprint="load-pv-wind-policy-fingerprint",
        config_snapshot_ref="store://project_1/study_1/config.json",
    )
    artifact = JobArtifact(
        artifact_id="artifact_summary",
        project_id=project.project_id,
        study_id=study.study_id,
        job_id="job_1",
        kind=ArtifactKind.TECHNICAL_SUMMARY,
        storage_uri="store://project_1/study_1/technical_summary.parquet",
        content_type="application/parquet",
        sha256="abc123",
        size_bytes=2048,
    )
    record = StudyResultRecord(
        result_id="result_1",
        project_id=project.project_id,
        study_id=study.study_id,
        created_by_job_id=artifact.job_id,
        technical_summary_artifact_id=artifact.artifact_id,
        hourly_detail_artifact_ids={"S0001": "artifact_hourly_s0001"},
        report_artifact_ids={"brief": "artifact_report"},
    )

    assert project.project_id == study.project_id == artifact.project_id == record.project_id
    assert record.hourly_detail_artifact_ids["S0001"] == "artifact_hourly_s0001"
    assert record.report_artifact_ids["brief"] == "artifact_report"


def test_artifact_rejects_negative_size_and_empty_storage_uri():
    with pytest.raises(ValueError, match="size_bytes must be non-negative"):
        JobArtifact(
            "artifact_bad",
            "project_1",
            "study_1",
            "job_1",
            ArtifactKind.REPORT,
            "store://report.docx",
            size_bytes=-1,
        )

    with pytest.raises(ValueError, match="storage_uri must not be empty"):
        JobArtifact("artifact_bad", "project_1", "study_1", "job_1", ArtifactKind.REPORT, "")


def test_audit_log_is_append_only_event_shape_with_metadata_copy():
    metadata = {"file_name": "load.csv", "rows": 8784}
    event = AuditLog(
        event_id="event_1",
        actor_user_id="user_1",
        action=AuditAction.UPLOAD_INPUT,
        project_id="project_1",
        study_id="study_1",
        target_type="input_curve",
        target_id="artifact_load",
        metadata=metadata,
        created_at=_dt(6),
    )
    metadata["rows"] = 1

    assert event.action == AuditAction.UPLOAD_INPUT
    assert event.project_id == "project_1"
    assert event.metadata["rows"] == 8784


def test_models_require_timezone_aware_datetimes():
    with pytest.raises(ValueError, match="queued_at must be timezone-aware"):
        Job(
            job_id="job_bad",
            project_id="project_1",
            study_id="study_1",
            requested_by_user_id="user_1",
            job_type=JobType.REPORT_EXPORT,
            queued_at=datetime(2026, 6, 15, 1),
        )
