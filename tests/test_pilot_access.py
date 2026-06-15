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
