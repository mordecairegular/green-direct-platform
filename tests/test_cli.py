from datetime import datetime, timezone

import pytest

from green_direct.cli import build_parser, main
from green_direct.models.pilot_backend import (
    ArtifactKind,
    ArtifactRetentionPolicy,
    AuditAction,
    AuditLog,
    Job,
    JobStatus,
    JobType,
    ProjectRole,
)
from green_direct.services import LocalJobStore, LocalPilotAuth, LocalPilotRegistry, LocalResultStore


def _store_arg(tmp_path):
    return ["--store-dir", str(tmp_path)]


def test_cli_pilot_admin_bootstrap_create_reset_disable_user(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ADMIN_PASSWORD", "admin-password")
    monkeypatch.setenv("ANALYST_PASSWORD", "analyst-password")
    monkeypatch.setenv("RESET_PASSWORD", "reset-password")

    assert main(
        [
            "pilot-admin",
            "bootstrap",
            *_store_arg(tmp_path),
            "--user-id",
            "admin",
            "--login-name",
            "admin@example.local",
            "--display-name",
            "Admin",
            "--password-env",
            "ADMIN_PASSWORD",
        ]
    ) == 0
    assert "Bootstrapped platform admin: admin" in capsys.readouterr().out

    assert main(
        [
            "pilot-admin",
            "create-user",
            *_store_arg(tmp_path),
            "--actor-user-id",
            "admin",
            "--user-id",
            "analyst",
            "--login-name",
            "analyst@example.local",
            "--display-name",
            "Analyst",
            "--password-env",
            "ANALYST_PASSWORD",
        ]
    ) == 0

    assert main(
        [
            "pilot-admin",
            "reset-password",
            *_store_arg(tmp_path),
            "--actor-user-id",
            "admin",
            "--user-id",
            "analyst",
            "--password-env",
            "RESET_PASSWORD",
        ]
    ) == 0

    auth = LocalPilotAuth(
        tmp_path,
        registry=LocalPilotRegistry(tmp_path),
        result_store=LocalResultStore(tmp_path),
    )
    assert auth.login(login_name="analyst@example.local", password="reset-password").user_id == "analyst"

    assert main(
        [
            "pilot-admin",
            "list-users",
            *_store_arg(tmp_path),
            "--actor-user-id",
            "admin",
        ]
    ) == 0
    output = capsys.readouterr().out
    assert "admin@example.local" in output
    assert "analyst@example.local" in output
    assert "reset-password" not in output

    assert main(
        [
            "pilot-admin",
            "disable-user",
            *_store_arg(tmp_path),
            "--actor-user-id",
            "admin",
            "--user-id",
            "analyst",
        ]
    ) == 0
    assert LocalPilotRegistry(tmp_path).load_user("analyst").is_active is False


def test_cli_pilot_admin_grant_revoke_and_list_sessions(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ADMIN_PASSWORD", "admin-password")
    monkeypatch.setenv("OPS_PASSWORD", "ops-password")
    main(
        [
            "pilot-admin",
            "bootstrap",
            *_store_arg(tmp_path),
            "--user-id",
            "admin",
            "--login-name",
            "admin@example.local",
            "--display-name",
            "Admin",
            "--password-env",
            "ADMIN_PASSWORD",
        ]
    )
    main(
        [
            "pilot-admin",
            "create-user",
            *_store_arg(tmp_path),
            "--actor-user-id",
            "admin",
            "--user-id",
            "ops",
            "--login-name",
            "ops@example.local",
            "--display-name",
            "Ops",
            "--password-env",
            "OPS_PASSWORD",
        ]
    )

    assert main(
        [
            "pilot-admin",
            "grant-platform-admin",
            *_store_arg(tmp_path),
            "--actor-user-id",
            "admin",
            "--user-id",
            "ops",
        ]
    ) == 0
    assert LocalPilotRegistry(tmp_path).load_user("ops").is_platform_admin is True

    auth = LocalPilotAuth(
        tmp_path,
        registry=LocalPilotRegistry(tmp_path),
        result_store=LocalResultStore(tmp_path),
    )
    auth.login(login_name="ops@example.local", password="ops-password")
    assert main(
        [
            "pilot-admin",
            "list-sessions",
            *_store_arg(tmp_path),
            "--actor-user-id",
            "admin",
            "--user-id",
            "ops",
        ]
    ) == 0
    assert "ops" in capsys.readouterr().out

    assert main(
        [
            "pilot-admin",
            "revoke-platform-admin",
            *_store_arg(tmp_path),
            "--actor-user-id",
            "admin",
            "--user-id",
            "ops",
        ]
    ) == 0
    assert LocalPilotRegistry(tmp_path).load_user("ops").is_platform_admin is False


def test_cli_pilot_admin_lists_audit_events(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ADMIN_PASSWORD", "admin-password")
    assert main(
        [
            "pilot-admin",
            "bootstrap",
            *_store_arg(tmp_path),
            "--user-id",
            "admin",
            "--login-name",
            "admin@example.local",
            "--display-name",
            "Admin",
            "--password-env",
            "ADMIN_PASSWORD",
        ]
    ) == 0
    capsys.readouterr()

    store = LocalResultStore(tmp_path)
    store.append_audit_log(
        AuditLog(
            event_id="event_global",
            actor_user_id="admin",
            action=AuditAction.UPDATE_USER,
            target_type="user",
            target_id="analyst",
            metadata={"source": "test"},
            created_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        )
    )
    store.append_audit_log(
        AuditLog(
            event_id="event_project",
            actor_user_id="admin",
            action=AuditAction.UPDATE_MEMBERSHIP,
            project_id="project_1",
            target_type="project_membership",
            target_id="member_1",
            metadata={"role": "analyst"},
            created_at=datetime(2020, 1, 2, tzinfo=timezone.utc),
        )
    )

    assert main(
        [
            "pilot-admin",
            "list-audit-events",
            *_store_arg(tmp_path),
            "--actor-user-id",
            "admin",
            "--action",
            "update_user",
            "--oldest-first",
        ]
    ) == 0
    global_output = capsys.readouterr().out
    assert "created_at\taction\tactor_user_id\tproject_id\tstudy_id\tjob_id\ttarget_type\ttarget_id\tmetadata" in global_output
    assert "2020-01-01T00:00:00+00:00\tupdate_user\tadmin\t\t\t\tuser\tanalyst\t{\"source\":\"test\"}" in global_output
    assert "project_1" not in global_output

    assert main(
        [
            "pilot-admin",
            "list-audit-events",
            *_store_arg(tmp_path),
            "--actor-user-id",
            "admin",
            "--project-id",
            "project_1",
            "--action",
            "update_membership",
            "--limit",
            "1",
        ]
    ) == 0
    project_output = capsys.readouterr().out
    assert "project_1" in project_output
    assert "{\"role\":\"analyst\"}" in project_output
    assert "update_user" not in project_output
    assert "{\"source\":\"test\"}" not in project_output

    assert main(
        [
            "pilot-admin",
            "list-audit-events",
            *_store_arg(tmp_path),
            "--actor-user-id",
            "admin",
            "--limit",
            "0",
        ]
    ) == 1
    assert "--limit must be positive." in capsys.readouterr().err


def test_cli_pilot_admin_manages_project_memberships(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ADMIN_PASSWORD", "admin-password")
    assert main(
        [
            "pilot-admin",
            "bootstrap",
            *_store_arg(tmp_path),
            "--user-id",
            "admin",
            "--login-name",
            "admin@example.local",
            "--display-name",
            "Admin",
            "--password-env",
            "ADMIN_PASSWORD",
        ]
    ) == 0
    assert main(
        [
            "pilot-admin",
            "create-user",
            *_store_arg(tmp_path),
            "--actor-user-id",
            "admin",
            "--user-id",
            "analyst",
            "--login-name",
            "analyst@example.local",
            "--display-name",
            "Analyst",
        ]
    ) == 0
    capsys.readouterr()

    registry = LocalPilotRegistry(tmp_path)
    assert main(
        [
            "pilot-admin",
            "create-project",
            *_store_arg(tmp_path),
            "--actor-user-id",
            "admin",
            "--project-id",
            "project_1",
            "--name",
            "Pilot Project",
            "--owner-user-id",
            "analyst",
        ]
    ) == 0
    assert "Created project: project_1" in capsys.readouterr().out
    owner_membership = registry.get_project_membership("project_1", "analyst")
    assert owner_membership is not None
    assert owner_membership.role == ProjectRole.ADMIN

    assert main(
        [
            "pilot-admin",
            "list-projects",
            *_store_arg(tmp_path),
            "--actor-user-id",
            "admin",
        ]
    ) == 0
    project_output = capsys.readouterr().out
    assert "project_id\tname\tstatus\tcreated_by\tcreated_at" in project_output
    assert "project_1\tPilot Project\tactive\tanalyst" in project_output

    assert main(
        [
            "pilot-admin",
            "grant-project-role",
            *_store_arg(tmp_path),
            "--actor-user-id",
            "admin",
            "--project-id",
            "project_1",
            "--user-id",
            "analyst",
            "--role",
            "analyst",
            "--cannot-export-artifacts",
        ]
    ) == 0
    assert "Granted project role: project_1\tanalyst\tanalyst" in capsys.readouterr().out

    membership = registry.get_project_membership("project_1", "analyst")
    assert membership is not None
    assert membership.role == ProjectRole.ANALYST
    assert membership.can_export_artifacts is False

    assert main(
        [
            "pilot-admin",
            "list-project-members",
            *_store_arg(tmp_path),
            "--actor-user-id",
            "admin",
            "--project-id",
            "project_1",
        ]
    ) == 0
    member_output = capsys.readouterr().out
    assert "membership_id\tproject_id\tuser_id\trole\tstatus\tcan_export\tcreated_at" in member_output
    assert "project_1\tanalyst\tanalyst\tactive\tcan_export=no" in member_output

    assert main(
        [
            "pilot-admin",
            "disable-project-member",
            *_store_arg(tmp_path),
            "--actor-user-id",
            "admin",
            "--project-id",
            "project_1",
            "--user-id",
            "analyst",
        ]
    ) == 0
    assert "Disabled project member: project_1\tanalyst" in capsys.readouterr().out
    disabled = registry.get_project_membership("project_1", "analyst")
    assert disabled is not None
    assert disabled.is_active is False

    audit_events = LocalResultStore(tmp_path).read_audit_log("project_1")
    assert [event.action for event in audit_events] == [
        AuditAction.CREATE_PROJECT,
        AuditAction.UPDATE_MEMBERSHIP,
        AuditAction.UPDATE_MEMBERSHIP,
    ]

    assert main(
        [
            "pilot-admin",
            "archive-project",
            *_store_arg(tmp_path),
            "--actor-user-id",
            "admin",
            "--project-id",
            "project_1",
        ]
    ) == 0
    assert "Archived project: project_1" in capsys.readouterr().out
    assert registry.load_project("project_1").status.value == "archived"


def test_cli_pilot_admin_lists_jobs_with_filters_and_stale_marker(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ADMIN_PASSWORD", "admin-password")
    assert main(
        [
            "pilot-admin",
            "bootstrap",
            *_store_arg(tmp_path),
            "--user-id",
            "admin",
            "--login-name",
            "admin@example.local",
            "--display-name",
            "Admin",
            "--password-env",
            "ADMIN_PASSWORD",
        ]
    ) == 0
    capsys.readouterr()

    job_store = LocalJobStore(tmp_path)
    job_store.submit_job(
        Job(
            job_id="job_queued",
            project_id="project_1",
            study_id="study_1",
            requested_by_user_id="analyst",
            job_type=JobType.TECHNICAL_STUDY,
            queued_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        )
    )
    job_store.submit_job(
        Job(
            job_id="job_running",
            project_id="project_1",
            study_id="study_1",
            requested_by_user_id="analyst",
            job_type=JobType.ECONOMIC_STUDY,
            queued_at=datetime(2020, 1, 2, tzinfo=timezone.utc),
        )
    )
    job_store.submit_job(
        Job(
            job_id="job_other_project",
            project_id="project_2",
            study_id="study_1",
            requested_by_user_id="analyst",
            job_type=JobType.REPORT_EXPORT,
            queued_at=datetime(2020, 1, 3, tzinfo=timezone.utc),
        )
    )
    job_store.start_job(
        "project_1",
        "study_1",
        "job_running",
        started_at=datetime(2020, 1, 2, 1, tzinfo=timezone.utc),
        worker_id="worker_1",
    )

    assert main(
        [
            "pilot-admin",
            "list-jobs",
            *_store_arg(tmp_path),
            "--actor-user-id",
            "admin",
            "--project-id",
            "project_1",
            "--status",
            "running",
            "--stale-after-minutes",
            "60",
        ]
    ) == 0

    output = capsys.readouterr().out
    assert "project_id\tstudy_id\tjob_id\tjob_type\tstatus" in output
    assert "project_1\tstudy_1\tjob_running\teconomic_study\trunning" in output
    assert "\tworker_1\t" in output
    assert output.rstrip().endswith("\tyes")
    assert "job_queued" not in output
    assert "job_other_project" not in output


def test_cli_pilot_admin_claims_next_job_for_worker(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ADMIN_PASSWORD", "admin-password")
    assert main(
        [
            "pilot-admin",
            "bootstrap",
            *_store_arg(tmp_path),
            "--user-id",
            "admin",
            "--login-name",
            "admin@example.local",
            "--display-name",
            "Admin",
            "--password-env",
            "ADMIN_PASSWORD",
        ]
    ) == 0
    assert main(
        [
            "pilot-admin",
            "create-project",
            *_store_arg(tmp_path),
            "--actor-user-id",
            "admin",
            "--project-id",
            "project_active",
            "--name",
            "Active Project",
        ]
    ) == 0
    assert main(
        [
            "pilot-admin",
            "create-project",
            *_store_arg(tmp_path),
            "--actor-user-id",
            "admin",
            "--project-id",
            "project_archived",
            "--name",
            "Archived Project",
        ]
    ) == 0
    assert main(
        [
            "pilot-admin",
            "archive-project",
            *_store_arg(tmp_path),
            "--actor-user-id",
            "admin",
            "--project-id",
            "project_archived",
        ]
    ) == 0
    capsys.readouterr()

    job_store = LocalJobStore(tmp_path)
    job_store.submit_job(
        Job(
            job_id="job_archived",
            project_id="project_archived",
            study_id="study_1",
            requested_by_user_id="admin",
            job_type=JobType.TECHNICAL_STUDY,
            queued_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        )
    )
    job_store.submit_job(
        Job(
            job_id="job_economic",
            project_id="project_active",
            study_id="study_1",
            requested_by_user_id="admin",
            job_type=JobType.ECONOMIC_STUDY,
            queued_at=datetime(2020, 1, 2, tzinfo=timezone.utc),
        )
    )
    job_store.submit_job(
        Job(
            job_id="job_technical",
            project_id="project_active",
            study_id="study_1",
            requested_by_user_id="admin",
            job_type=JobType.TECHNICAL_STUDY,
            queued_at=datetime(2020, 1, 3, tzinfo=timezone.utc),
        )
    )

    assert main(
        [
            "pilot-admin",
            "claim-next-job",
            *_store_arg(tmp_path),
            "--actor-user-id",
            "admin",
            "--worker-id",
            "worker_1",
            "--job-type",
            "technical_study",
        ]
    ) == 0
    output = capsys.readouterr().out
    assert "project_id\tstudy_id\tjob_id\tjob_type\tstatus" in output
    assert "project_active\tstudy_1\tjob_technical\ttechnical_study\trunning" in output
    assert "\tworker_1\t" in output
    assert job_store.load_job("project_active", "study_1", "job_technical").status == JobStatus.RUNNING
    assert job_store.load_job("project_archived", "study_1", "job_archived").status == JobStatus.QUEUED
    assert job_store.load_job("project_active", "study_1", "job_economic").status == JobStatus.QUEUED

    assert main(
        [
            "pilot-admin",
            "heartbeat-job",
            *_store_arg(tmp_path),
            "--actor-user-id",
            "admin",
            "--worker-id",
            "worker_1",
            "--project-id",
            "project_active",
            "--study-id",
            "study_1",
            "--job-id",
            "job_technical",
            "--current",
            "2",
            "--total",
            "5",
            "--message",
            "running block 2/5",
        ]
    ) == 0
    heartbeat_output = capsys.readouterr().out
    assert "project_active\tstudy_1\tjob_technical\ttechnical_study\trunning" in heartbeat_output
    assert "\t2/5\t0\tworker_1\t" in heartbeat_output
    updated = job_store.load_job("project_active", "study_1", "job_technical")
    assert updated.progress_current == 2
    assert updated.progress_total == 5
    assert updated.progress_message == "running block 2/5"
    assert updated.last_heartbeat_at is not None

    assert main(
        [
            "pilot-admin",
            "complete-worker-job",
            *_store_arg(tmp_path),
            "--actor-user-id",
            "admin",
            "--worker-id",
            "worker_1",
            "--project-id",
            "project_active",
            "--study-id",
            "study_1",
            "--job-id",
            "job_technical",
        ]
    ) == 0
    complete_output = capsys.readouterr().out
    assert "project_active\tstudy_1\tjob_technical\ttechnical_study\tsucceeded" in complete_output
    assert job_store.load_job("project_active", "study_1", "job_technical").status == JobStatus.SUCCEEDED

    assert main(
        [
            "pilot-admin",
            "claim-next-job",
            *_store_arg(tmp_path),
            "--actor-user-id",
            "admin",
            "--worker-id",
            "worker_2",
            "--job-type",
            "economic_study",
        ]
    ) == 0
    assert "project_active\tstudy_1\tjob_economic\teconomic_study\trunning" in capsys.readouterr().out
    assert main(
        [
            "pilot-admin",
            "fail-worker-job",
            *_store_arg(tmp_path),
            "--actor-user-id",
            "admin",
            "--worker-id",
            "worker_2",
            "--project-id",
            "project_active",
            "--study-id",
            "study_1",
            "--job-id",
            "job_economic",
            "--error-message",
            "sanitized worker failure",
        ]
    ) == 0
    fail_output = capsys.readouterr().out
    assert "project_active\tstudy_1\tjob_economic\teconomic_study\tfailed" in fail_output
    failed = job_store.load_job("project_active", "study_1", "job_economic")
    assert failed.status == JobStatus.FAILED
    assert failed.error_message == "sanitized worker failure"
    audit_events = LocalResultStore(tmp_path).read_audit_log("project_active")
    assert any(
        event.action == AuditAction.COMPLETE_JOB
        and event.job_id == "job_technical"
        and event.metadata["status"] == "succeeded"
        and event.metadata["worker_id"] == "worker_1"
        for event in audit_events
    )
    assert any(
        event.action == AuditAction.COMPLETE_JOB
        and event.job_id == "job_economic"
        and event.metadata["status"] == "failed"
        and event.metadata["worker_id"] == "worker_2"
        for event in audit_events
    )

    assert main(
        [
            "pilot-admin",
            "claim-next-job",
            *_store_arg(tmp_path),
            "--actor-user-id",
            "admin",
            "--worker-id",
            "worker_2",
            "--job-type",
            "report_export",
        ]
    ) == 0
    assert "No queued job matched." in capsys.readouterr().out


def test_cli_errors_return_nonzero_and_do_not_create_user(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ADMIN_PASSWORD", "admin-password")
    main(
        [
            "pilot-admin",
            "bootstrap",
            *_store_arg(tmp_path),
            "--user-id",
            "admin",
            "--login-name",
            "admin@example.local",
            "--display-name",
            "Admin",
            "--password-env",
            "ADMIN_PASSWORD",
        ]
    )

    code = main(
        [
            "pilot-admin",
            "create-user",
            *_store_arg(tmp_path),
            "--actor-user-id",
            "missing-admin",
            "--user-id",
            "viewer",
            "--login-name",
            "viewer@example.local",
            "--display-name",
            "Viewer",
        ]
    )

    assert code == 1
    assert "Error:" in capsys.readouterr().err
    assert LocalPilotRegistry(tmp_path).list_users()[0].user_id == "admin"


def test_cli_pilot_admin_purges_expired_artifacts_and_audits(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ADMIN_PASSWORD", "admin-password")
    assert main(
        [
            "pilot-admin",
            "bootstrap",
            *_store_arg(tmp_path),
            "--user-id",
            "admin",
            "--login-name",
            "admin@example.local",
            "--display-name",
            "Admin",
            "--password-env",
            "ADMIN_PASSWORD",
        ]
    ) == 0
    capsys.readouterr()

    store = LocalResultStore(tmp_path)
    artifact = store.store_artifact(
        artifact_id="hourly_detail_s0001",
        project_id="project_1",
        study_id="study_1",
        job_id="job_1",
        kind=ArtifactKind.HOURLY_DETAIL,
        payload=b"hourly-detail",
        filename="hourly_s0001.csv",
        retention_policy=ArtifactRetentionPolicy.EXPIRE,
        expires_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )

    assert main(
        [
            "pilot-admin",
            "purge-expired-artifacts",
            *_store_arg(tmp_path),
            "--actor-user-id",
            "admin",
        ]
    ) == 0

    output = capsys.readouterr().out
    assert "Purged expired artifact payloads: 1" in output
    assert "project_1\tstudy_1\thourly_detail_s0001" in output

    purged = store.load_artifact("project_1", "study_1", artifact.artifact_id)
    assert purged.purged_at is not None
    assert not purged.is_payload_available
    with pytest.raises(FileNotFoundError, match="payload has been purged"):
        store.read_artifact_payload(purged)

    audit_events = store.read_audit_log("project_1")
    assert len(audit_events) == 1
    assert audit_events[0].actor_user_id == "admin"
    assert audit_events[0].action == AuditAction.DELETE_ARTIFACT
    assert audit_events[0].target_type == "artifact_payload"
    assert audit_events[0].target_id == "hourly_detail_s0001"
    assert audit_events[0].metadata["retention_policy"] == ArtifactRetentionPolicy.EXPIRE.value


def test_cli_pilot_admin_fails_stale_running_jobs_and_audits(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ADMIN_PASSWORD", "admin-password")
    assert main(
        [
            "pilot-admin",
            "bootstrap",
            *_store_arg(tmp_path),
            "--user-id",
            "admin",
            "--login-name",
            "admin@example.local",
            "--display-name",
            "Admin",
            "--password-env",
            "ADMIN_PASSWORD",
        ]
    ) == 0
    capsys.readouterr()

    job_store = LocalJobStore(tmp_path)
    job_store.submit_job(
        Job(
            job_id="job_stale",
            project_id="project_1",
            study_id="study_1",
            requested_by_user_id="analyst",
            job_type=JobType.TECHNICAL_STUDY,
            queued_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        )
    )
    job_store.start_job(
        "project_1",
        "study_1",
        "job_stale",
        started_at=datetime(2020, 1, 1, 1, tzinfo=timezone.utc),
        worker_id="worker_1",
    )

    assert main(
        [
            "pilot-admin",
            "fail-stale-jobs",
            *_store_arg(tmp_path),
            "--actor-user-id",
            "admin",
            "--stale-after-minutes",
            "60",
        ]
    ) == 0

    output = capsys.readouterr().out
    assert "Marked stale running jobs failed: 1" in output
    assert "project_1\tstudy_1\tjob_stale" in output

    failed = job_store.load_job("project_1", "study_1", "job_stale")
    assert failed.status == JobStatus.FAILED
    assert failed.finished_at is not None
    assert failed.error_message == "Marked failed by pilot-admin fail-stale-jobs after 60 minutes without heartbeat."

    audit_events = LocalResultStore(tmp_path).read_audit_log("project_1")
    assert len(audit_events) == 1
    assert audit_events[0].action == AuditAction.COMPLETE_JOB
    assert audit_events[0].metadata["reason"] == "stale_running_job"
    assert audit_events[0].metadata["status"] == JobStatus.FAILED.value
    assert audit_events[0].metadata["stale_after_seconds"] == 3600
    assert audit_events[0].metadata["worker_id"] == "worker_1"


def test_cli_exposes_green_direct_console_script():
    parser = build_parser()
    parsed = parser.parse_args(
        [
            "pilot-admin",
            "fail-worker-job",
            "--actor-user-id",
            "admin",
            "--worker-id",
            "worker_1",
            "--project-id",
            "project_1",
            "--study-id",
            "study_1",
            "--job-id",
            "job_1",
            "--error-message",
            "sanitized failure",
        ]
    )

    assert parsed.command == "pilot-admin"
    assert parsed.pilot_admin_command == "fail-worker-job"


def test_cli_exposes_run_worker_once_command():
    parser = build_parser()
    parsed = parser.parse_args(
        [
            "pilot-admin",
            "run-worker-once",
            "--actor-user-id",
            "admin",
            "--worker-id",
            "worker_1",
            "--project-id",
            "project_1",
            "--job-type",
            "technical_study",
        ]
    )

    assert parsed.command == "pilot-admin"
    assert parsed.pilot_admin_command == "run-worker-once"
    assert parsed.worker_id == "worker_1"
    assert parsed.job_type == ["technical_study"]


def test_cli_exposes_run_worker_loop_command():
    parser = build_parser()
    parsed = parser.parse_args(
        [
            "pilot-admin",
            "run-worker-loop",
            "--actor-user-id",
            "admin",
            "--worker-id",
            "worker_1",
            "--project-id",
            "project_1",
            "--job-type",
            "technical_study",
            "--poll-interval-seconds",
            "0.5",
            "--max-jobs",
            "3",
            "--idle-exit-after",
            "2",
        ]
    )

    assert parsed.command == "pilot-admin"
    assert parsed.pilot_admin_command == "run-worker-loop"
    assert parsed.worker_id == "worker_1"
    assert parsed.job_type == ["technical_study"]
    assert parsed.poll_interval_seconds == 0.5
    assert parsed.max_jobs == 3
    assert parsed.idle_exit_after == 2
