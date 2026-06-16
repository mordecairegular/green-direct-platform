from datetime import datetime, timezone

import pytest

from green_direct.models.pilot_backend import (
    ArtifactKind,
    AuditAction,
    Job,
    JobStatus,
    JobType,
    Project,
    ProjectRole,
    StudyResultRecord,
    User,
)
from green_direct.services import (
    LocalJobStore,
    LocalPilotRegistry,
    LocalResultStore,
    PilotAccessError,
    PilotAccessService,
)


def _service(tmp_path):
    registry = LocalPilotRegistry(tmp_path)
    job_store = LocalJobStore(tmp_path)
    result_store = LocalResultStore(tmp_path)
    return PilotAccessService(
        registry=registry,
        job_store=job_store,
        result_store=result_store,
    )


def _dt(hour: int) -> datetime:
    return datetime(2026, 6, 15, hour, tzinfo=timezone.utc)


def _seed_users(service: PilotAccessService) -> None:
    service.registry.save_user(User("admin", "admin@example.local", "Admin"))
    service.registry.save_user(User("analyst", "analyst@example.local", "Analyst"))
    service.registry.save_user(User("viewer", "viewer@example.local", "Viewer"))
    service.registry.save_user(User("outsider", "outsider@example.local", "Outsider"))


def _create_project_with_members(service: PilotAccessService) -> Project:
    _seed_users(service)
    project = service.create_project(
        actor_user_id="admin",
        project=Project("project_1", "Internal pilot project"),
    )
    service.grant_project_role(
        actor_user_id="admin",
        project_id=project.project_id,
        user_id="analyst",
        role=ProjectRole.ANALYST,
    )
    service.grant_project_role(
        actor_user_id="admin",
        project_id=project.project_id,
        user_id="viewer",
        role=ProjectRole.VIEWER,
    )
    return project


def _job(job_id: str, *, requested_by_user_id: str = "analyst") -> Job:
    return Job(
        job_id=job_id,
        project_id="project_1",
        study_id="study_1",
        requested_by_user_id=requested_by_user_id,
        job_type=JobType.TECHNICAL_STUDY,
    )


def test_create_project_grants_creator_admin_and_writes_audit(tmp_path):
    service = _service(tmp_path)
    service.registry.save_user(User("admin", "admin@example.local", "Admin"))

    project = service.create_project(
        actor_user_id="admin",
        project=Project("project_1", "Internal pilot project"),
    )

    membership = service.registry.get_project_membership(project.project_id, "admin")
    assert project.created_by_user_id == "admin"
    assert membership is not None
    assert membership.role == ProjectRole.ADMIN
    audit = service.result_store.read_audit_log("project_1")
    assert [event.action for event in audit] == [AuditAction.CREATE_PROJECT]


def test_accessible_projects_are_limited_to_active_memberships(tmp_path):
    service = _service(tmp_path)
    _seed_users(service)
    first = service.create_project(
        actor_user_id="admin",
        project=Project("project_1", "Internal pilot project"),
    )
    second = service.create_project(
        actor_user_id="analyst",
        project=Project("project_2", "Analyst private project"),
    )

    service.grant_project_role(
        actor_user_id="admin",
        project_id=first.project_id,
        user_id="analyst",
        role=ProjectRole.VIEWER,
    )
    service.archive_project(actor_user_id="analyst", project_id=second.project_id)

    active_visible = service.list_accessible_projects(actor_user_id="analyst")
    all_visible = service.list_accessible_projects(actor_user_id="analyst", include_archived=True)

    assert [(project.project_id, membership.role) for project, membership in active_visible] == [
        ("project_1", ProjectRole.VIEWER)
    ]
    assert [project.project_id for project, _membership in all_visible] == ["project_1", "project_2"]
    assert service.list_accessible_projects(actor_user_id="outsider") == []


def test_project_admin_can_grant_and_disable_membership(tmp_path):
    service = _service(tmp_path)
    project = _create_project_with_members(service)

    updated = service.grant_project_role(
        actor_user_id="admin",
        project_id=project.project_id,
        user_id="viewer",
        role=ProjectRole.ANALYST,
    )
    disabled = service.disable_project_membership(
        actor_user_id="admin",
        project_id=project.project_id,
        user_id="viewer",
    )

    assert updated.can_submit_jobs()
    assert not disabled.is_active
    assert [event.action for event in service.result_store.read_audit_log(project.project_id)].count(
        AuditAction.UPDATE_MEMBERSHIP
    ) >= 2


def test_non_admin_cannot_manage_memberships(tmp_path):
    service = _service(tmp_path)
    _create_project_with_members(service)

    with pytest.raises(PilotAccessError, match="cannot manage"):
        service.grant_project_role(
            actor_user_id="analyst",
            project_id="project_1",
            user_id="outsider",
            role=ProjectRole.VIEWER,
        )


def test_analyst_can_submit_and_view_job_but_viewer_cannot_submit(tmp_path):
    service = _service(tmp_path)
    _create_project_with_members(service)

    submitted = service.submit_job(actor_user_id="analyst", job=_job("job_1"))

    assert submitted.status == JobStatus.QUEUED
    assert service.list_project_jobs(actor_user_id="viewer", project_id="project_1") == [submitted]
    with pytest.raises(PilotAccessError, match="cannot submit jobs"):
        service.submit_job(actor_user_id="viewer", job=_job("job_2", requested_by_user_id="viewer"))
    assert any(
        event.action == AuditAction.SUBMIT_JOB
        for event in service.result_store.read_audit_log("project_1")
    )


def test_submit_job_validates_input_artifact_refs_and_audits_them(tmp_path):
    service = _service(tmp_path)
    _create_project_with_members(service)
    service.result_store.store_artifact(
        artifact_id="technical_summary",
        project_id="project_1",
        study_id="study_1",
        job_id="job_source",
        kind=ArtifactKind.TECHNICAL_SUMMARY,
        payload="scenario_id\nS0001\n",
        filename="technical_summary.csv",
        content_type="text/csv",
    )
    job = Job(
        job_id="job_economy",
        project_id="project_1",
        study_id="study_1",
        requested_by_user_id="analyst",
        job_type=JobType.ECONOMIC_STUDY,
        input_artifact_ids={"technical_summary": "technical_summary"},
    )

    submitted = service.submit_job(actor_user_id="analyst", job=job)

    assert submitted.input_artifact_ids == {"technical_summary": "technical_summary"}
    audit_events = service.result_store.read_audit_log("project_1")
    assert any(
        event.action == AuditAction.SUBMIT_JOB
        and event.job_id == "job_economy"
        and event.metadata["input_artifact_ids"] == {"technical_summary": "technical_summary"}
        for event in audit_events
    )

    with pytest.raises(FileNotFoundError):
        service.submit_job(
            actor_user_id="analyst",
            job=Job(
                job_id="job_bad_input",
                project_id="project_1",
                study_id="study_1",
                requested_by_user_id="analyst",
                job_type=JobType.ECONOMIC_STUDY,
                input_artifact_ids={"technical_summary": "missing_summary"},
            ),
        )


def test_non_member_and_disabled_user_are_rejected(tmp_path):
    service = _service(tmp_path)
    _create_project_with_members(service)

    with pytest.raises(PilotAccessError, match="no active membership"):
        service.list_project_jobs(actor_user_id="outsider", project_id="project_1")

    service.registry.disable_user("analyst")
    with pytest.raises(PilotAccessError, match="User is disabled"):
        service.submit_job(actor_user_id="analyst", job=_job("job_1"))


def test_archived_project_blocks_new_jobs_but_still_allows_view(tmp_path):
    service = _service(tmp_path)
    _create_project_with_members(service)
    submitted = service.submit_job(actor_user_id="analyst", job=_job("job_1"))

    service.archive_project(actor_user_id="admin", project_id="project_1")

    assert service.list_project_jobs(actor_user_id="viewer", project_id="project_1") == [submitted]
    with pytest.raises(PilotAccessError, match="Project is not active"):
        service.submit_job(actor_user_id="analyst", job=_job("job_2"))


def test_platform_admin_can_list_jobs_across_projects_for_operations(tmp_path):
    service = _service(tmp_path)
    service.registry.save_user(User("ops", "ops@example.local", "Ops", is_platform_admin=True))
    service.registry.save_user(User("analyst", "analyst@example.local", "Analyst"))
    project = service.create_project(
        actor_user_id="ops",
        project=Project("project_1", "Internal pilot project"),
    )
    service.grant_project_role(
        actor_user_id="ops",
        project_id=project.project_id,
        user_id="analyst",
        role=ProjectRole.ANALYST,
    )
    service.submit_job(actor_user_id="analyst", job=_job("job_1"))

    jobs = service.list_jobs_for_platform_admin(actor_user_id="ops", statuses=[JobStatus.QUEUED])

    assert [job.job_id for job in jobs] == ["job_1"]
    with pytest.raises(PilotAccessError, match="platform operations"):
        service.list_jobs_for_platform_admin(actor_user_id="analyst", statuses=[JobStatus.QUEUED])


def test_platform_admin_can_fail_stale_running_jobs_with_audit(tmp_path):
    service = _service(tmp_path)
    service.registry.save_user(User("ops", "ops@example.local", "Ops", is_platform_admin=True))
    service.registry.save_user(User("analyst", "analyst@example.local", "Analyst"))
    project = service.create_project(
        actor_user_id="ops",
        project=Project("project_1", "Internal pilot project"),
    )
    service.grant_project_role(
        actor_user_id="ops",
        project_id=project.project_id,
        user_id="analyst",
        role=ProjectRole.ANALYST,
    )
    service.submit_job(actor_user_id="analyst", job=_job("job_stale"))
    service.job_store.start_job(
        "project_1",
        "study_1",
        "job_stale",
        started_at=_dt(1),
        worker_id="worker_1",
    )

    failed = service.fail_stale_running_jobs_for_platform_admin(
        actor_user_id="ops",
        stale_after_seconds=3600,
        now=_dt(3),
    )

    assert [job.job_id for job in failed] == ["job_stale"]
    assert failed[0].status == JobStatus.FAILED
    audit_events = service.result_store.read_audit_log("project_1")
    assert any(
        event.action == AuditAction.COMPLETE_JOB
        and event.job_id == "job_stale"
        and event.metadata["reason"] == "stale_running_job"
        and event.metadata["worker_id"] == "worker_1"
        for event in audit_events
    )
    with pytest.raises(PilotAccessError, match="platform operations"):
        service.fail_stale_running_jobs_for_platform_admin(
            actor_user_id="analyst",
            stale_after_seconds=3600,
            now=_dt(4),
        )


def test_cancel_job_allows_owner_or_admin_only(tmp_path):
    service = _service(tmp_path)
    _create_project_with_members(service)
    service.submit_job(actor_user_id="analyst", job=_job("job_1"))
    service.registry.save_user(User("analyst_2", "analyst2@example.local", "Analyst 2"))
    service.grant_project_role(
        actor_user_id="admin",
        project_id="project_1",
        user_id="analyst_2",
        role=ProjectRole.ANALYST,
    )

    with pytest.raises(PilotAccessError, match="cancel another user's job"):
        service.cancel_job(actor_user_id="analyst_2", project_id="project_1", study_id="study_1", job_id="job_1")

    canceled = service.cancel_job(actor_user_id="admin", project_id="project_1", study_id="study_1", job_id="job_1")
    assert canceled.status == JobStatus.CANCELED
    assert any(
        event.action == AuditAction.CANCEL_JOB
        for event in service.result_store.read_audit_log("project_1")
    )


def test_job_lifecycle_updates_require_owner_or_project_admin_and_are_audited(tmp_path):
    service = _service(tmp_path)
    _create_project_with_members(service)
    service.submit_job(actor_user_id="analyst", job=_job("job_1"))
    service.registry.save_user(User("analyst_2", "analyst2@example.local", "Analyst 2"))
    service.grant_project_role(
        actor_user_id="admin",
        project_id="project_1",
        user_id="analyst_2",
        role=ProjectRole.ANALYST,
    )

    with pytest.raises(PilotAccessError, match="update another user's job"):
        service.start_job(actor_user_id="analyst_2", project_id="project_1", study_id="study_1", job_id="job_1")

    running = service.start_job(actor_user_id="analyst", project_id="project_1", study_id="study_1", job_id="job_1")
    progress = service.update_job_progress(
        actor_user_id="analyst",
        project_id="project_1",
        study_id="study_1",
        job_id="job_1",
        current=1,
        total=2,
        message="running technical study",
    )
    succeeded = service.succeed_job(actor_user_id="admin", project_id="project_1", study_id="study_1", job_id="job_1")

    assert running.status == JobStatus.RUNNING
    assert progress.progress_message == "running technical study"
    assert succeeded.status == JobStatus.SUCCEEDED
    assert any(
        event.action == AuditAction.COMPLETE_JOB and event.metadata.get("status") == "succeeded"
        for event in service.result_store.read_audit_log("project_1")
    )


def test_platform_admin_claims_next_worker_job_and_skips_archived_projects(tmp_path):
    service = _service(tmp_path)
    service.registry.save_user(
        User("platform_admin", "platform-admin@example.local", "Platform Admin", is_platform_admin=True)
    )
    service.registry.save_user(User("analyst", "analyst@example.local", "Analyst"))
    active_project = service.create_project(
        actor_user_id="platform_admin",
        project=Project("project_active", "Active project"),
    )
    archived_project = service.create_project(
        actor_user_id="platform_admin",
        project=Project("project_archived", "Archived project"),
    )
    service.registry.grant_project_role(
        project_id=active_project.project_id,
        user_id="analyst",
        role=ProjectRole.ANALYST,
    )
    service.job_store.submit_job(
        Job(
            job_id="job_archived",
            project_id=archived_project.project_id,
            study_id="study_1",
            requested_by_user_id="platform_admin",
            job_type=JobType.TECHNICAL_STUDY,
        )
    )
    service.job_store.submit_job(
        Job(
            job_id="job_active",
            project_id=active_project.project_id,
            study_id="study_1",
            requested_by_user_id="analyst",
            job_type=JobType.TECHNICAL_STUDY,
        )
    )
    service.archive_project(actor_user_id="platform_admin", project_id=archived_project.project_id)

    with pytest.raises(PilotAccessError, match="platform operations"):
        service.claim_next_job_for_worker(actor_user_id="analyst", worker_id="worker_1")

    claimed = service.claim_next_job_for_worker(
        actor_user_id="platform_admin",
        worker_id="worker_1",
        job_types=[JobType.TECHNICAL_STUDY],
    )

    assert claimed is not None
    assert claimed.job_id == "job_active"
    assert claimed.project_id == "project_active"
    assert claimed.status == JobStatus.RUNNING
    assert claimed.worker_id == "worker_1"
    assert service.job_store.load_job("project_archived", "study_1", "job_archived").status == JobStatus.QUEUED


def test_platform_admin_updates_worker_job_progress_only_for_assigned_worker(tmp_path):
    service = _service(tmp_path)
    service.registry.save_user(
        User("platform_admin", "platform-admin@example.local", "Platform Admin", is_platform_admin=True)
    )
    project = service.create_project(
        actor_user_id="platform_admin",
        project=Project("project_1", "Active project"),
    )
    service.job_store.submit_job(
        Job(
            job_id="job_1",
            project_id=project.project_id,
            study_id="study_1",
            requested_by_user_id="platform_admin",
            job_type=JobType.TECHNICAL_STUDY,
        )
    )
    claimed = service.claim_next_job_for_worker(
        actor_user_id="platform_admin",
        worker_id="worker_1",
        project_id=project.project_id,
    )
    assert claimed is not None

    with pytest.raises(PilotAccessError, match="assigned to another worker"):
        service.update_worker_job_progress(
            actor_user_id="platform_admin",
            worker_id="worker_2",
            project_id=project.project_id,
            study_id="study_1",
            job_id="job_1",
            current=1,
        )

    updated = service.update_worker_job_progress(
        actor_user_id="platform_admin",
        worker_id="worker_1",
        project_id=project.project_id,
        study_id="study_1",
        job_id="job_1",
        current=2,
        total=5,
        message="running block 2/5",
    )

    assert updated.status == JobStatus.RUNNING
    assert updated.progress_current == 2
    assert updated.progress_total == 5
    assert updated.progress_message == "running block 2/5"
    assert updated.worker_id == "worker_1"
    assert updated.last_heartbeat_at is not None


def test_platform_admin_completes_or_fails_worker_jobs_and_audits(tmp_path):
    service = _service(tmp_path)
    service.registry.save_user(
        User("platform_admin", "platform-admin@example.local", "Platform Admin", is_platform_admin=True)
    )
    project = service.create_project(
        actor_user_id="platform_admin",
        project=Project("project_1", "Active project"),
    )
    service.job_store.submit_job(
        Job(
            job_id="job_success",
            project_id=project.project_id,
            study_id="study_1",
            requested_by_user_id="platform_admin",
            job_type=JobType.TECHNICAL_STUDY,
        )
    )
    service.job_store.submit_job(
        Job(
            job_id="job_failed",
            project_id=project.project_id,
            study_id="study_1",
            requested_by_user_id="platform_admin",
            job_type=JobType.ECONOMIC_STUDY,
        )
    )

    service.claim_next_job_for_worker(
        actor_user_id="platform_admin",
        worker_id="worker_1",
        project_id=project.project_id,
        job_types=[JobType.TECHNICAL_STUDY],
    )
    with pytest.raises(PilotAccessError, match="assigned to another worker"):
        service.succeed_worker_job(
            actor_user_id="platform_admin",
            worker_id="worker_2",
            project_id=project.project_id,
            study_id="study_1",
            job_id="job_success",
        )
    succeeded = service.succeed_worker_job(
        actor_user_id="platform_admin",
        worker_id="worker_1",
        project_id=project.project_id,
        study_id="study_1",
        job_id="job_success",
    )

    service.claim_next_job_for_worker(
        actor_user_id="platform_admin",
        worker_id="worker_2",
        project_id=project.project_id,
        job_types=[JobType.ECONOMIC_STUDY],
    )
    failed = service.fail_worker_job(
        actor_user_id="platform_admin",
        worker_id="worker_2",
        project_id=project.project_id,
        study_id="study_1",
        job_id="job_failed",
        error_message="sanitized worker failure",
    )

    assert succeeded.status == JobStatus.SUCCEEDED
    assert failed.status == JobStatus.FAILED
    assert failed.error_message == "sanitized worker failure"
    audit_events = service.result_store.read_audit_log(project.project_id)
    assert any(
        event.action == AuditAction.COMPLETE_JOB
        and event.job_id == "job_success"
        and event.metadata == {"status": "succeeded", "worker_id": "worker_1"}
        for event in audit_events
    )
    assert any(
        event.action == AuditAction.COMPLETE_JOB
        and event.job_id == "job_failed"
        and event.metadata["status"] == "failed"
        and event.metadata["worker_id"] == "worker_2"
        and event.metadata["error_message"] == "sanitized worker failure"
        for event in audit_events
    )


def test_artifact_payload_read_requires_project_view_and_is_audited(tmp_path):
    service = _service(tmp_path)
    _create_project_with_members(service)
    artifact = service.result_store.store_artifact(
        artifact_id="technical_summary",
        project_id="project_1",
        study_id="study_1",
        job_id="job_1",
        kind=ArtifactKind.TECHNICAL_SUMMARY,
        payload="scenario_id,total_load_energy\nS0001,100\n",
        filename="summary.csv",
        content_type="text/csv",
    )

    payload = service.read_artifact_payload(actor_user_id="viewer", artifact=artifact)

    assert payload.decode("utf-8").startswith("scenario_id")
    assert any(
        event.action == AuditAction.DOWNLOAD_ARTIFACT
        for event in service.result_store.read_audit_log("project_1")
    )
    with pytest.raises(PilotAccessError, match="no active membership"):
        service.read_artifact_payload(actor_user_id="outsider", artifact=artifact)


def test_artifact_payload_download_requires_export_permission_and_audits_denial(tmp_path):
    service = _service(tmp_path)
    _create_project_with_members(service)
    service.grant_project_role(
        actor_user_id="admin",
        project_id="project_1",
        user_id="analyst",
        role=ProjectRole.ANALYST,
        can_export_artifacts=False,
    )
    artifact = service.result_store.store_artifact(
        artifact_id="technical_summary",
        project_id="project_1",
        study_id="study_1",
        job_id="job_1",
        kind=ArtifactKind.TECHNICAL_SUMMARY,
        payload="scenario_id,total_load_energy\nS0001,100\n",
        filename="summary.csv",
        content_type="text/csv",
    )

    assert service.load_artifact(
        actor_user_id="analyst",
        project_id="project_1",
        study_id="study_1",
        artifact_id="technical_summary",
    ) == artifact
    with pytest.raises(PilotAccessError, match="cannot export"):
        service.read_artifact_payload(actor_user_id="analyst", artifact=artifact)

    denied_event = service.result_store.read_audit_log("project_1")[-1]
    assert denied_event.action == AuditAction.DOWNLOAD_ARTIFACT
    assert denied_event.metadata["success"] is False
    assert denied_event.metadata["reason"].startswith("User cannot export")


def test_transient_export_download_requires_permission_and_is_audited(tmp_path):
    service = _service(tmp_path)
    project = _create_project_with_members(service)

    event = service.record_transient_export_download(
        actor_user_id="viewer",
        project_id=project.project_id,
        study_id="study_1",
        export_key="simple_markdown_report",
        file_name="green_direct_report_S0001.md",
        content_type="text/markdown",
        size_bytes=128,
        metadata={"scenario_id": "S0001"},
    )

    assert event.action == AuditAction.DOWNLOAD_ARTIFACT
    assert event.target_type == "transient_export"
    assert event.target_id == "simple_markdown_report"
    assert event.metadata["success"] is True
    assert event.metadata["file_name"] == "green_direct_report_S0001.md"
    assert event.metadata["size_bytes"] == 128
    assert event.metadata["scenario_id"] == "S0001"

    service.grant_project_role(
        actor_user_id="admin",
        project_id=project.project_id,
        user_id="analyst",
        role=ProjectRole.ANALYST,
        can_export_artifacts=False,
    )
    with pytest.raises(PilotAccessError, match="cannot export"):
        service.record_transient_export_download(
            actor_user_id="analyst",
            project_id=project.project_id,
            study_id="study_1",
            export_key="technical_economy_summary_excel",
            file_name="green_direct_technical_economy_summary.xlsx",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            size_bytes=256,
        )

    denied_event = service.result_store.read_audit_log(project.project_id)[-1]
    assert denied_event.action == AuditAction.DOWNLOAD_ARTIFACT
    assert denied_event.target_type == "transient_export"
    assert denied_event.target_id == "technical_economy_summary_excel"
    assert denied_event.metadata["success"] is False
    assert denied_event.metadata["reason"].startswith("User cannot export")


def test_artifact_payload_view_does_not_require_export_permission(tmp_path):
    service = _service(tmp_path)
    _create_project_with_members(service)
    service.grant_project_role(
        actor_user_id="admin",
        project_id="project_1",
        user_id="analyst",
        role=ProjectRole.ANALYST,
        can_export_artifacts=False,
    )
    artifact = service.result_store.store_artifact(
        artifact_id="hourly_detail_S0001",
        project_id="project_1",
        study_id="study_1",
        job_id="job_1",
        kind=ArtifactKind.HOURLY_DETAIL,
        payload="scenario_id,hour_index,load_power\nS0001,0,1.0\n",
        filename="hourly_detail_S0001.csv",
        content_type="text/csv",
    )

    payload = service.read_artifact_payload_for_view(actor_user_id="analyst", artifact=artifact)

    assert b"load_power" in payload
    view_event = service.result_store.read_audit_log("project_1")[-1]
    assert view_event.action == AuditAction.VIEW_ARTIFACT
    assert view_event.metadata["success"] is True
    with pytest.raises(PilotAccessError, match="cannot export"):
        service.read_artifact_payload(actor_user_id="analyst", artifact=artifact)


def test_result_record_lists_require_project_view(tmp_path):
    service = _service(tmp_path)
    _create_project_with_members(service)
    record = service.result_store.save_result_record(
        StudyResultRecord(
            result_id="technical_result",
            project_id="project_1",
            study_id="study_1",
            created_by_job_id="job_1",
            technical_summary_artifact_id="technical_summary",
        )
    )

    assert service.list_project_result_records(actor_user_id="viewer", project_id="project_1") == [record]
    assert service.list_study_result_records(actor_user_id="viewer", project_id="project_1", study_id="study_1") == [
        record
    ]
    with pytest.raises(PilotAccessError, match="no active membership"):
        service.list_project_result_records(actor_user_id="outsider", project_id="project_1")


def test_result_record_delete_requires_project_admin_and_is_audited(tmp_path):
    service = _service(tmp_path)
    _create_project_with_members(service)
    record = service.result_store.save_result_record(
        StudyResultRecord(
            result_id="technical_result",
            project_id="project_1",
            study_id="study_1",
            created_by_job_id="job_1",
            technical_summary_artifact_id="technical_summary",
        )
    )

    with pytest.raises(PilotAccessError, match="cannot manage"):
        service.delete_result_record(
            actor_user_id="analyst",
            project_id="project_1",
            study_id="study_1",
            result_id=record.result_id,
        )

    deleted = service.delete_result_record(
        actor_user_id="admin",
        project_id="project_1",
        study_id="study_1",
        result_id=record.result_id,
    )

    assert deleted.is_deleted
    assert deleted.deleted_by_user_id == "admin"
    assert service.list_project_result_records(actor_user_id="viewer", project_id="project_1") == []
    audit = service.result_store.read_audit_log("project_1")[-1]
    assert audit.action == AuditAction.DELETE_RESULT_RECORD
    assert audit.target_type == "result_record"
    assert audit.target_id == record.result_id
    assert audit.metadata["created_by_job_id"] == "job_1"


def test_result_record_mark_requires_project_admin_and_is_audited(tmp_path):
    service = _service(tmp_path)
    _create_project_with_members(service)
    record = service.result_store.save_result_record(
        StudyResultRecord(
            result_id="technical_result",
            project_id="project_1",
            study_id="study_1",
            created_by_job_id="job_1",
            technical_summary_artifact_id="technical_summary",
        )
    )

    with pytest.raises(PilotAccessError, match="cannot manage"):
        service.mark_result_record(
            actor_user_id="analyst",
            project_id="project_1",
            study_id="study_1",
            result_id=record.result_id,
            is_pinned=True,
            label="report candidate",
        )

    marked = service.mark_result_record(
        actor_user_id="admin",
        project_id="project_1",
        study_id="study_1",
        result_id=record.result_id,
        is_pinned=True,
        label="report candidate",
    )

    assert marked.is_pinned
    assert marked.label == "report candidate"
    audit = service.result_store.read_audit_log("project_1")[-1]
    assert audit.action == AuditAction.UPDATE_RESULT_RECORD
    assert audit.target_type == "result_record"
    assert audit.target_id == record.result_id
    assert audit.metadata["is_pinned"] is True
    assert audit.metadata["label"] == "report candidate"
