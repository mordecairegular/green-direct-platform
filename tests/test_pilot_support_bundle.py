from datetime import datetime, timezone
import json

from green_direct.cli import build_parser, main
from green_direct.models.pilot_backend import (
    ArtifactKind,
    AuditAction,
    AuditLog,
    Job,
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
    build_pilot_support_bundle,
)


def _dt(hour: int) -> datetime:
    return datetime(2026, 6, 17, hour, tzinfo=timezone.utc)


def _seed_store(tmp_path):
    registry = LocalPilotRegistry(tmp_path)
    job_store = LocalJobStore(tmp_path)
    result_store = LocalResultStore(tmp_path)

    registry.save_user(
        User(
            "admin",
            "admin-secret@example.local",
            "Sensitive Admin Name",
            is_platform_admin=True,
            created_at=_dt(1),
        )
    )
    registry.save_user(
        User(
            "analyst",
            "analyst-secret@example.local",
            "Sensitive Analyst Name",
            created_at=_dt(2),
        )
    )
    registry.save_project(
        Project(
            "project_1",
            "Sensitive Project Name",
            created_by_user_id="admin",
            created_at=_dt(3),
        )
    )
    registry.grant_project_role(
        project_id="project_1",
        user_id="admin",
        role=ProjectRole.ADMIN,
        can_export_artifacts=True,
    )
    registry.grant_project_role(
        project_id="project_1",
        user_id="analyst",
        role=ProjectRole.ANALYST,
        can_export_artifacts=False,
    )

    result_store.store_artifact(
        artifact_id="input_curve_load",
        project_id="project_1",
        study_id="study_1",
        job_id="job_1",
        kind=ArtifactKind.INPUT_CURVE,
        payload="secret payload from uploaded curve",
        filename="sensitive_customer_curve.csv",
        content_type="text/csv",
    )
    result_store.save_result_record(
        StudyResultRecord(
            result_id="result_1",
            project_id="project_1",
            study_id="study_1",
            created_by_job_id="job_1",
            technical_summary_artifact_id="input_curve_load",
            label="Sensitive result label",
            created_at=_dt(4),
        )
    )

    job_store.submit_job(
        Job(
            job_id="job_1",
            project_id="project_1",
            study_id="study_1",
            requested_by_user_id="analyst",
            job_type=JobType.TECHNICAL_STUDY,
            input_artifact_ids={"curve": "input_curve_load"},
            queued_at=_dt(5),
        )
    )
    job_store.start_job(
        "project_1",
        "study_1",
        "job_1",
        started_at=_dt(6),
        worker_id="worker_1",
    )
    job_store.fail_job(
        "project_1",
        "study_1",
        "job_1",
        "secret worker traceback with customer filename",
        finished_at=_dt(7),
    )

    result_store.append_audit_log(
        AuditLog(
            event_id="event_global",
            actor_user_id="admin",
            action=AuditAction.UPDATE_USER,
            target_type="user",
            target_id="analyst",
            metadata={"login_name": "analyst-secret@example.local"},
            created_at=_dt(8),
        )
    )
    result_store.append_audit_log(
        AuditLog(
            event_id="event_project",
            actor_user_id="analyst",
            action=AuditAction.UPLOAD_INPUT,
            project_id="project_1",
            study_id="study_1",
            job_id="job_1",
            target_type="artifact",
            target_id="input_curve_load",
            metadata={
                "file_name": "sensitive_customer_curve.csv",
                "project_name": "Sensitive Project Name",
            },
            created_at=_dt(9),
        )
    )

    return registry, job_store, result_store


def test_support_bundle_summarizes_store_without_sensitive_values(tmp_path):
    _seed_store(tmp_path)

    bundle = build_pilot_support_bundle(
        tmp_path,
        project_id="project_1",
        recent_limit=10,
        generated_at=_dt(10),
    )
    text = json.dumps(bundle, ensure_ascii=False, sort_keys=True)

    assert bundle["generated_at"] == "2026-06-17T10:00:00+00:00"
    assert bundle["project_id"] == "project_1"
    assert bundle["doctor"]["status"] == "pass"
    assert bundle["counts"]["users"] == 2
    assert bundle["counts"]["projects"] == 1
    assert bundle["counts"]["memberships"] == 2
    assert bundle["counts"]["jobs"] == 1
    assert bundle["counts"]["artifacts"] == 1
    assert bundle["users"] == {"by_status": {"active": 2}, "platform_admin_count": 1}
    assert bundle["jobs"]["by_status"] == {"failed": 1}
    assert bundle["jobs"]["recent"][0]["error_message_present"] is True
    assert bundle["jobs"]["recent"][0]["input_artifact_keys"] == ["curve"]
    assert bundle["artifacts"]["by_kind"] == {"input_curve": 1}
    assert bundle["artifacts"]["records"][0]["sha256_prefix"]
    assert bundle["results"]["records"][0]["has_technical_summary"] is True
    assert bundle["audit"]["recent"][0]["metadata_keys"] == ["file_name", "project_name"]

    assert "admin-secret@example.local" not in text
    assert "analyst-secret@example.local" not in text
    assert "Sensitive Admin Name" not in text
    assert "Sensitive Analyst Name" not in text
    assert "Sensitive Project Name" not in text
    assert "Sensitive result label" not in text
    assert "secret payload from uploaded curve" not in text
    assert "secret worker traceback" not in text
    assert "sensitive_customer_curve.csv" not in text
    assert "local-result-store://" not in text
    assert str(tmp_path.resolve()) not in text


def test_support_bundle_global_scope_includes_global_and_project_audit(tmp_path):
    _seed_store(tmp_path)

    bundle = build_pilot_support_bundle(tmp_path, recent_limit=10, generated_at=_dt(10))

    assert bundle["audit"]["scope"] == "global_and_projects"
    assert [event["action"] for event in bundle["audit"]["recent"]] == ["upload_input", "update_user"]
    assert bundle["counts"]["recent_audit_events"] == 2


def test_cli_writes_support_bundle_for_platform_admin(tmp_path, capsys):
    _seed_store(tmp_path)
    output_path = tmp_path / "support" / "bundle.json"

    assert main(
        [
            "pilot-admin",
            "support-bundle",
            "--store-dir",
            str(tmp_path),
            "--actor-user-id",
            "admin",
            "--project-id",
            "project_1",
            "--limit",
            "5",
            "--output",
            str(output_path),
        ]
    ) == 0

    assert "Support bundle written:" in capsys.readouterr().out
    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert data["project_id"] == "project_1"
    assert data["recent_limit"] == 5
    assert "Sensitive Project Name" not in output_path.read_text(encoding="utf-8")

    assert main(
        [
            "pilot-admin",
            "support-bundle",
            "--store-dir",
            str(tmp_path),
            "--actor-user-id",
            "analyst",
        ]
    ) == 1
    assert "User cannot manage platform accounts." in capsys.readouterr().err


def test_cli_exposes_support_bundle_command():
    parser = build_parser()
    parsed = parser.parse_args(
        [
            "pilot-admin",
            "support-bundle",
            "--actor-user-id",
            "admin",
            "--project-id",
            "project_1",
            "--limit",
            "25",
        ]
    )

    assert parsed.command == "pilot-admin"
    assert parsed.pilot_admin_command == "support-bundle"
    assert parsed.project_id == "project_1"
    assert parsed.limit == 25
