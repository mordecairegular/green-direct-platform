from datetime import datetime, timezone

import pytest

from green_direct.models.pilot_backend import (
    ArtifactKind,
    AuditAction,
    AuditLog,
    JobType,
    StudyResultRecord,
)
from green_direct.services import LocalResultStore


def _dt(hour: int) -> datetime:
    return datetime(2026, 6, 15, hour, tzinfo=timezone.utc)


def test_result_store_writes_and_reads_project_scoped_artifact(tmp_path):
    store = LocalResultStore(tmp_path)

    artifact = store.store_artifact(
        artifact_id="technical_summary",
        project_id="project_1",
        study_id="study_1",
        job_id="job_1",
        kind=ArtifactKind.TECHNICAL_SUMMARY,
        payload="scenario_id,total_load_energy\nS0001,100\n",
        filename="summary.csv",
        content_type="text/csv",
    )
    loaded = store.load_artifact("project_1", "study_1", "technical_summary")

    assert loaded.artifact_id == artifact.artifact_id
    assert loaded.project_id == "project_1"
    assert loaded.study_id == "study_1"
    assert loaded.kind == ArtifactKind.TECHNICAL_SUMMARY
    assert loaded.sha256 == artifact.sha256
    assert loaded.size_bytes == len("scenario_id,total_load_energy\nS0001,100\n".encode("utf-8"))
    assert loaded.storage_uri.endswith("/project_1/study_1/artifacts/technical_summary/summary.csv")
    assert store.read_artifact_payload(loaded).decode("utf-8").startswith("scenario_id")


def test_result_store_blocks_path_traversal_segments(tmp_path):
    store = LocalResultStore(tmp_path)

    with pytest.raises(ValueError, match="project_id contains unsafe path characters"):
        store.store_artifact(
            artifact_id="artifact_1",
            project_id="../project_1",
            study_id="study_1",
            job_id="job_1",
            kind=ArtifactKind.REPORT,
            payload=b"payload",
            filename="report.md",
        )

    with pytest.raises(ValueError, match="filename contains unsafe path characters"):
        store.store_artifact(
            artifact_id="artifact_1",
            project_id="project_1",
            study_id="study_1",
            job_id="job_1",
            kind=ArtifactKind.REPORT,
            payload=b"payload",
            filename="../report.md",
        )


def test_result_store_prevents_accidental_artifact_overwrite(tmp_path):
    store = LocalResultStore(tmp_path)
    kwargs = {
        "artifact_id": "report",
        "project_id": "project_1",
        "study_id": "study_1",
        "job_id": "job_1",
        "kind": ArtifactKind.REPORT,
        "payload": b"first",
        "filename": "report.md",
    }

    first = store.store_artifact(**kwargs)
    with pytest.raises(FileExistsError):
        store.store_artifact(**{**kwargs, "payload": b"second"})

    overwritten = store.store_artifact(**{**kwargs, "payload": b"second", "overwrite": True})
    assert first.sha256 != overwritten.sha256
    assert store.read_artifact_payload(overwritten) == b"second"


def test_result_store_round_trips_result_record(tmp_path):
    store = LocalResultStore(tmp_path)
    record = StudyResultRecord(
        result_id="result_1",
        project_id="project_1",
        study_id="study_1",
        created_by_job_id="job_1",
        technical_summary_artifact_id="technical_summary",
        recommendation_artifact_id="recommendation",
        hourly_detail_artifact_ids={"S0001": "hourly_s0001"},
        report_artifact_ids={"markdown": "brief_report"},
        created_at=_dt(1),
    )

    store.save_result_record(record)
    loaded = store.load_result_record("project_1", "study_1", "result_1")

    assert loaded == record

    with pytest.raises(FileExistsError):
        store.save_result_record(record)


def test_result_store_lists_project_and_study_result_records_newest_first(tmp_path):
    store = LocalResultStore(tmp_path)
    older = StudyResultRecord(
        result_id="technical_result",
        project_id="project_1",
        study_id="study_1",
        created_by_job_id="job_1",
        technical_summary_artifact_id="technical_summary",
        created_at=_dt(1),
    )
    newer = StudyResultRecord(
        result_id="economy_result_job_2",
        project_id="project_1",
        study_id="study_1",
        created_by_job_id="job_2",
        economy_summary_artifact_id="economy_summary_job_2",
        created_at=_dt(2),
    )
    other_study = StudyResultRecord(
        result_id="recommendation_result_job_3",
        project_id="project_1",
        study_id="study_2",
        created_by_job_id="job_3",
        recommendation_artifact_id="recommendation_job_3",
        created_at=_dt(3),
    )
    other_project = StudyResultRecord(
        result_id="result_other",
        project_id="project_2",
        study_id="study_1",
        created_by_job_id="job_4",
        created_at=_dt(4),
    )

    for record in [older, newer, other_study, other_project]:
        store.save_result_record(record)

    assert [record.result_id for record in store.list_study_result_records("project_1", "study_1")] == [
        "economy_result_job_2",
        "technical_result",
    ]
    assert [record.result_id for record in store.list_project_result_records("project_1")] == [
        "recommendation_result_job_3",
        "economy_result_job_2",
        "technical_result",
    ]
    assert store.list_project_result_records("project_missing") == []


def test_result_store_appends_project_and_global_audit_logs(tmp_path):
    store = LocalResultStore(tmp_path)
    project_event = AuditLog(
        event_id="event_project",
        actor_user_id="user_1",
        action=AuditAction.SUBMIT_JOB,
        project_id="project_1",
        study_id="study_1",
        job_id="job_1",
        metadata={"job_type": JobType.TECHNICAL_STUDY.value},
        created_at=_dt(2),
    )
    global_event = AuditLog(
        event_id="event_global",
        actor_user_id="admin_1",
        action=AuditAction.CREATE_USER,
        target_type="user",
        target_id="user_2",
        created_at=_dt(3),
    )

    store.append_audit_log(project_event)
    store.append_audit_log(global_event)

    assert store.read_audit_log("project_1") == [project_event]
    assert store.read_audit_log() == [global_event]
    assert store.read_audit_log("project_2") == []
