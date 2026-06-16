from datetime import datetime, timezone

import pytest

from green_direct.models.pilot_backend import (
    ArtifactKind,
    ArtifactRetentionPolicy,
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
    assert viewer.can_download_artifacts()

    assert not disabled.can_view_project()
    assert not disabled.can_submit_jobs()
    assert not disabled.can_manage_project()
    assert not disabled.can_download_artifacts()


def test_membership_export_permission_is_independent_from_project_role():
    no_export_analyst = ProjectMembership(
        "m_no_export",
        "p1",
        "u2",
        ProjectRole.ANALYST,
        can_export_artifacts=False,
    )

    assert no_export_analyst.can_view_project()
    assert no_export_analyst.can_submit_jobs()
    assert not no_export_analyst.can_download_artifacts()


def test_user_platform_admin_flag_defaults_false():
    regular = User("user_regular", "regular@example.local", "Regular")
    admin = User("user_admin", "admin@example.local", "Admin", is_platform_admin=True)

    assert regular.is_platform_admin is False
    assert admin.is_platform_admin is True


def test_job_lifecycle_keeps_project_scope_and_blocks_invalid_transitions():
    source_map = {"config": "config_snapshot"}
    job = Job(
        job_id="job_1",
        project_id="project_1",
        study_id="study_1",
        requested_by_user_id="user_1",
        job_type=JobType.TECHNICAL_STUDY,
        input_artifact_ids=source_map,
        queued_at=_dt(1),
    )

    running = job.start(started_at=_dt(2))
    succeeded = running.succeed(finished_at=_dt(3))
    source_map["config"] = "mutated"

    assert running.status == JobStatus.RUNNING
    assert running.project_id == "project_1"
    assert running.input_artifact_ids == {"config": "config_snapshot"}
    assert succeeded.status == JobStatus.SUCCEEDED
    assert succeeded.is_terminal
    assert succeeded.started_at == _dt(2)
    assert succeeded.finished_at == _dt(3)

    with pytest.raises(ValueError, match="Only running jobs can fail"):
        succeeded.fail("should not be accepted")

    with pytest.raises(ValueError, match="Terminal jobs cannot be canceled"):
        succeeded.cancel()


def test_job_input_artifact_ids_require_non_empty_keys_and_values():
    assert Job(
        job_id="job_inputs",
        project_id="project_1",
        study_id="study_1",
        requested_by_user_id="user_1",
        job_type=JobType.ECONOMIC_STUDY,
        input_artifact_ids={" technical_summary ": " technical_summary_artifact "},
    ).input_artifact_ids == {"technical_summary": "technical_summary_artifact"}

    with pytest.raises(ValueError, match="input_artifact_ids key must not be empty"):
        Job(
            job_id="job_bad_key",
            project_id="project_1",
            study_id="study_1",
            requested_by_user_id="user_1",
            job_type=JobType.ECONOMIC_STUDY,
            input_artifact_ids={"": "technical_summary_artifact"},
        )

    with pytest.raises(ValueError, match="input_artifact_ids\\[technical_summary\\] must not be empty"):
        Job(
            job_id="job_bad_value",
            project_id="project_1",
            study_id="study_1",
            requested_by_user_id="user_1",
            job_type=JobType.ECONOMIC_STUDY,
            input_artifact_ids={"technical_summary": ""},
        )


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


def test_job_progress_requires_non_negative_counts_and_blocks_terminal_updates():
    job = Job(
        job_id="job_progress",
        project_id="project_1",
        study_id="study_1",
        requested_by_user_id="user_1",
        job_type=JobType.TECHNICAL_STUDY,
    )

    progressed = job.update_progress(current=2, total=5, message="batch simulation")
    assert progressed.progress_current == 2
    assert progressed.progress_total == 5
    assert progressed.progress_message == "batch simulation"

    with pytest.raises(ValueError, match="progress_current must not exceed progress_total"):
        job.update_progress(current=6, total=5)

    with pytest.raises(ValueError, match="Terminal jobs cannot update progress"):
        job.cancel(finished_at=_dt(6)).update_progress(current=1, total=5)


def test_job_worker_heartbeat_and_stale_detection():
    job = Job(
        job_id="job_worker",
        project_id="project_1",
        study_id="study_1",
        requested_by_user_id="user_1",
        job_type=JobType.TECHNICAL_STUDY,
    )

    running = job.start(started_at=_dt(2), worker_id="worker_1")
    progressed = running.update_progress(
        current=1,
        total=3,
        message="batch 1",
        heartbeat_at=_dt(3),
    )

    assert running.worker_id == "worker_1"
    assert running.last_heartbeat_at == _dt(2)
    assert progressed.worker_id == "worker_1"
    assert progressed.last_heartbeat_at == _dt(3)
    assert not progressed.is_stale(now=_dt(4), stale_after_seconds=7200)
    assert progressed.is_stale(now=_dt(4), stale_after_seconds=3600)
    assert progressed.succeed(finished_at=_dt(5)).is_stale(now=_dt(6), stale_after_seconds=1) is False

    with pytest.raises(ValueError, match="last_heartbeat_at must be timezone-aware"):
        Job(
            job_id="job_bad_heartbeat",
            project_id="project_1",
            study_id="study_1",
            requested_by_user_id="user_1",
            job_type=JobType.TECHNICAL_STUDY,
            last_heartbeat_at=datetime(2026, 6, 15, 1),
        )


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
        annual_cashflow_artifact_ids={"power": "artifact_cashflow"},
        hourly_detail_artifact_ids={"S0001": "artifact_hourly_s0001"},
        report_artifact_ids={"brief": "artifact_report"},
    )

    assert project.project_id == study.project_id == artifact.project_id == record.project_id
    assert record.annual_cashflow_artifact_ids["power"] == "artifact_cashflow"
    assert record.hourly_detail_artifact_ids["S0001"] == "artifact_hourly_s0001"
    assert record.report_artifact_ids["brief"] == "artifact_report"


def test_result_record_soft_delete_marker_is_consistent():
    deleted = StudyResultRecord(
        result_id="result_deleted",
        project_id="project_1",
        study_id="study_1",
        created_by_job_id="job_1",
        deleted_at=_dt(7),
        deleted_by_user_id="admin",
    )

    assert deleted.is_deleted
    assert deleted.deleted_by_user_id == "admin"

    with pytest.raises(ValueError, match="deleted_at and deleted_by_user_id"):
        StudyResultRecord(
            result_id="result_bad",
            project_id="project_1",
            study_id="study_1",
            created_by_job_id="job_1",
            deleted_at=_dt(7),
        )


def test_result_record_pinned_marker_is_consistent():
    pinned = StudyResultRecord(
        result_id="result_pinned",
        project_id="project_1",
        study_id="study_1",
        created_by_job_id="job_1",
        pinned_at=_dt(8),
        pinned_by_user_id="admin",
        label="  report candidate  ",
    )

    assert pinned.is_pinned
    assert pinned.pinned_by_user_id == "admin"
    assert pinned.label == "report candidate"

    with pytest.raises(ValueError, match="pinned_at and pinned_by_user_id"):
        StudyResultRecord(
            result_id="result_bad_pin",
            project_id="project_1",
            study_id="study_1",
            created_by_job_id="job_1",
            pinned_at=_dt(8),
        )


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


def test_artifact_retention_policy_controls_expiration():
    expiring = JobArtifact(
        "artifact_expiring",
        "project_1",
        "study_1",
        "job_1",
        ArtifactKind.HOURLY_DETAIL,
        "store://hourly.csv",
        retention_policy=ArtifactRetentionPolicy.EXPIRE,
        expires_at=_dt(3),
    )
    keep = JobArtifact(
        "artifact_keep",
        "project_1",
        "study_1",
        "job_1",
        ArtifactKind.TECHNICAL_SUMMARY,
        "store://summary.csv",
        retention_policy=ArtifactRetentionPolicy.KEEP,
        expires_at=_dt(1),
    )

    assert not expiring.is_expired(_dt(2))
    assert expiring.is_expired(_dt(3))
    assert not keep.is_expired(_dt(6))


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
