from datetime import datetime, timezone

import pytest

from green_direct.models.pilot_backend import Job, JobStatus, JobType
from green_direct.services import LocalJobStore


def _dt(hour: int) -> datetime:
    return datetime(2026, 6, 15, hour, tzinfo=timezone.utc)


def _job(
    job_id: str,
    *,
    project_id: str = "project_1",
    study_id: str = "study_1",
    job_type: JobType | str = JobType.TECHNICAL_STUDY,
    queued_at: datetime | None = None,
) -> Job:
    return Job(
        job_id=job_id,
        project_id=project_id,
        study_id=study_id,
        requested_by_user_id="user_1",
        job_type=job_type,
        queued_at=queued_at or _dt(1),
    )


def test_job_store_submits_loads_and_lists_project_scoped_jobs(tmp_path):
    store = LocalJobStore(tmp_path)
    first = _job("job_1", queued_at=_dt(2))
    second = _job("job_2", study_id="study_2", job_type="economic_study", queued_at=_dt(1))

    store.submit_job(first)
    store.submit_job(second)

    assert store.load_job("project_1", "study_1", "job_1") == first
    assert store.list_study_jobs("project_1", "study_1") == [first]
    assert [job.job_id for job in store.list_project_jobs("project_1")] == ["job_2", "job_1"]
    assert store.list_project_jobs("project_missing") == []


def test_job_store_prevents_duplicate_submit_unless_overwrite(tmp_path):
    store = LocalJobStore(tmp_path)
    first = _job("job_1", queued_at=_dt(1))
    replacement = _job("job_1", job_type=JobType.RECOMMENDATION, queued_at=_dt(2))

    store.submit_job(first)
    with pytest.raises(FileExistsError):
        store.submit_job(replacement)

    store.submit_job(replacement, overwrite=True)
    assert store.load_job("project_1", "study_1", "job_1") == replacement


def test_job_store_persists_running_success_and_progress(tmp_path):
    store = LocalJobStore(tmp_path)
    store.submit_job(_job("job_1"))

    running = store.start_job("project_1", "study_1", "job_1", started_at=_dt(2))
    progress = store.update_job_progress(
        "project_1",
        "study_1",
        "job_1",
        current=3,
        total=10,
        message="technical simulation",
    )
    succeeded = store.succeed_job("project_1", "study_1", "job_1", finished_at=_dt(3))

    assert running.status == JobStatus.RUNNING
    assert progress.progress_current == 3
    assert progress.progress_total == 10
    assert progress.progress_message == "technical simulation"
    assert succeeded.status == JobStatus.SUCCEEDED
    assert store.load_job("project_1", "study_1", "job_1").finished_at == _dt(3)

    with pytest.raises(ValueError, match="Terminal jobs cannot be canceled"):
        store.cancel_job("project_1", "study_1", "job_1")


def test_job_store_persists_failure_and_cancel(tmp_path):
    store = LocalJobStore(tmp_path)
    store.submit_job(_job("job_failed"))
    store.submit_job(_job("job_canceled"))

    store.start_job("project_1", "study_1", "job_failed", started_at=_dt(2))
    failed = store.fail_job(
        "project_1",
        "study_1",
        "job_failed",
        "load curve missing",
        finished_at=_dt(3),
    )
    canceled = store.cancel_job("project_1", "study_1", "job_canceled", finished_at=_dt(4))

    assert failed.status == JobStatus.FAILED
    assert failed.error_message == "load curve missing"
    assert canceled.status == JobStatus.CANCELED
    assert canceled.finished_at == _dt(4)


def test_job_store_filters_by_status(tmp_path):
    store = LocalJobStore(tmp_path)
    store.submit_job(_job("job_queued", queued_at=_dt(1)))
    store.submit_job(_job("job_succeeded", queued_at=_dt(2)))
    store.start_job("project_1", "study_1", "job_succeeded", started_at=_dt(3))
    store.succeed_job("project_1", "study_1", "job_succeeded", finished_at=_dt(4))

    assert [job.job_id for job in store.list_project_jobs("project_1", statuses=["queued"])] == ["job_queued"]
    assert [
        job.job_id
        for job in store.list_study_jobs("project_1", "study_1", statuses=[JobStatus.SUCCEEDED])
    ] == ["job_succeeded"]


def test_job_store_rejects_invalid_progress_and_unsafe_paths(tmp_path):
    store = LocalJobStore(tmp_path)
    store.submit_job(_job("job_1"))

    with pytest.raises(ValueError, match="progress_current must not exceed progress_total"):
        store.update_job_progress("project_1", "study_1", "job_1", current=11, total=10)

    with pytest.raises(ValueError, match="project_id contains unsafe path characters"):
        store.submit_job(_job("job_2", project_id="../project_1"))

    with pytest.raises(ValueError, match="job_id contains unsafe path characters"):
        store.submit_job(_job("../job_2"))


def test_job_store_only_submits_queued_jobs(tmp_path):
    store = LocalJobStore(tmp_path)
    running = _job("job_1").start(started_at=_dt(2))

    with pytest.raises(ValueError, match="Only queued jobs can be submitted"):
        store.submit_job(running)
