from datetime import datetime, timezone
import multiprocessing as mp

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
        input_artifact_ids={"config": f"config_{job_id}"},
        queued_at=queued_at or _dt(1),
    )


def _claim_job_in_process(root: str, worker_id: str, output_queue) -> None:
    try:
        store = LocalJobStore(root)
        claimed = store.claim_next_queued_job(
            worker_id=worker_id,
            claimed_at=_dt(4),
        )
        output_queue.put((worker_id, claimed.job_id if claimed is not None else None, None))
    except Exception as exc:  # pragma: no cover - surfaced through parent process assertion
        output_queue.put((worker_id, None, repr(exc)))


def test_job_store_submits_loads_and_lists_project_scoped_jobs(tmp_path):
    store = LocalJobStore(tmp_path)
    first = _job("job_1", queued_at=_dt(2))
    second = _job("job_2", study_id="study_2", job_type="economic_study", queued_at=_dt(1))

    store.submit_job(first)
    store.submit_job(second)

    assert store.load_job("project_1", "study_1", "job_1") == first
    assert store.load_job("project_1", "study_1", "job_1").input_artifact_ids == {
        "config": "config_job_1",
    }
    assert store.list_study_jobs("project_1", "study_1") == [first]
    assert [job.job_id for job in store.list_project_jobs("project_1")] == ["job_2", "job_1"]
    assert [job.job_id for job in store.list_jobs(project_id="project_1")] == ["job_2", "job_1"]
    assert [job.job_id for job in store.list_jobs()] == ["job_2", "job_1"]
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

    running = store.start_job(
        "project_1",
        "study_1",
        "job_1",
        started_at=_dt(2),
        worker_id="worker_1",
    )
    progress = store.update_job_progress(
        "project_1",
        "study_1",
        "job_1",
        current=3,
        total=10,
        message="technical simulation",
        heartbeat_at=_dt(2),
    )
    succeeded = store.succeed_job("project_1", "study_1", "job_1", finished_at=_dt(3))

    assert running.status == JobStatus.RUNNING
    assert running.worker_id == "worker_1"
    assert running.last_heartbeat_at == _dt(2)
    assert progress.progress_current == 3
    assert progress.progress_total == 10
    assert progress.progress_message == "technical simulation"
    assert progress.worker_id == "worker_1"
    assert progress.last_heartbeat_at == _dt(2)
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


def test_job_store_claims_oldest_queued_job_for_worker(tmp_path):
    store = LocalJobStore(tmp_path)
    store.submit_job(_job("job_economic", job_type=JobType.ECONOMIC_STUDY, queued_at=_dt(1)))
    store.submit_job(_job("job_technical", job_type=JobType.TECHNICAL_STUDY, queued_at=_dt(2)))
    store.submit_job(_job("job_later", job_type=JobType.TECHNICAL_STUDY, queued_at=_dt(3)))

    claimed = store.claim_next_queued_job(
        worker_id="worker_1",
        job_types=[JobType.TECHNICAL_STUDY],
        claimed_at=_dt(4),
    )

    assert claimed is not None
    assert claimed.job_id == "job_technical"
    assert claimed.status == JobStatus.RUNNING
    assert claimed.worker_id == "worker_1"
    assert claimed.started_at == _dt(4)
    assert claimed.last_heartbeat_at == _dt(4)
    assert store.load_job("project_1", "study_1", "job_economic").status == JobStatus.QUEUED
    assert store.load_job("project_1", "study_1", "job_later").status == JobStatus.QUEUED

    next_technical = store.claim_next_queued_job(
        worker_id="worker_2",
        project_id="project_1",
        job_types=["technical_study"],
        claimed_at=_dt(5),
    )
    assert next_technical is not None
    assert next_technical.job_id == "job_later"
    assert store.claim_next_queued_job(worker_id="worker_3", job_types=[JobType.REPORT_EXPORT]) is None


def test_job_store_concurrent_claim_has_single_winner(tmp_path):
    store = LocalJobStore(tmp_path)
    store.submit_job(_job("job_1"))
    ctx = mp.get_context("spawn")
    output_queue = ctx.Queue()
    processes = [
        ctx.Process(target=_claim_job_in_process, args=(str(tmp_path), f"worker_{idx}", output_queue))
        for idx in range(5)
    ]

    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=15)

    for process in processes:
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
        assert process.exitcode == 0

    results = [output_queue.get(timeout=5) for _ in processes]
    errors = [error for _, _, error in results if error is not None]
    winners = [(worker_id, job_id) for worker_id, job_id, error in results if error is None and job_id is not None]

    assert errors == []
    assert len(winners) == 1
    assert winners[0][1] == "job_1"
    claimed = store.load_job("project_1", "study_1", "job_1")
    assert claimed.status == JobStatus.RUNNING
    assert claimed.worker_id == winners[0][0]


def test_job_store_lists_and_fails_stale_running_jobs(tmp_path):
    store = LocalJobStore(tmp_path)
    store.submit_job(_job("job_stale", queued_at=_dt(1)))
    store.submit_job(_job("job_fresh", queued_at=_dt(2)))
    store.submit_job(_job("job_queued", queued_at=_dt(3)))
    store.submit_job(_job("job_succeeded", queued_at=_dt(4)))
    store.submit_job(_job("job_other", project_id="project_2", queued_at=_dt(5)))

    store.start_job("project_1", "study_1", "job_stale", started_at=_dt(5), worker_id="worker_1")
    store.update_job_progress(
        "project_1",
        "study_1",
        "job_stale",
        current=1,
        total=5,
        heartbeat_at=_dt(7),
    )
    store.start_job("project_1", "study_1", "job_fresh", started_at=_dt(8), worker_id="worker_2")
    store.update_job_progress(
        "project_1",
        "study_1",
        "job_fresh",
        current=1,
        total=5,
        heartbeat_at=_dt(9),
    )
    store.start_job("project_1", "study_1", "job_succeeded", started_at=_dt(2))
    store.succeed_job("project_1", "study_1", "job_succeeded", finished_at=_dt(3))
    store.start_job("project_2", "study_1", "job_other", started_at=_dt(6), worker_id="worker_3")

    stale_for_project = store.list_stale_running_jobs(
        now=_dt(10),
        stale_after_seconds=7200,
        project_id="project_1",
    )
    all_stale = store.list_stale_running_jobs(now=_dt(10), stale_after_seconds=7200)

    assert [job.job_id for job in stale_for_project] == ["job_stale"]
    assert {job.job_id for job in all_stale} == {"job_stale", "job_other"}

    failed = store.fail_stale_running_jobs(
        now=_dt(10),
        stale_after_seconds=7200,
        error_message="worker heartbeat timeout",
        project_id="project_1",
    )

    assert [job.job_id for job in failed] == ["job_stale"]
    assert failed[0].status == JobStatus.FAILED
    assert failed[0].finished_at == _dt(10)
    assert failed[0].error_message == "worker heartbeat timeout"
    assert failed[0].worker_id == "worker_1"
    assert store.load_job("project_1", "study_1", "job_fresh").status == JobStatus.RUNNING
    assert store.load_job("project_1", "study_1", "job_queued").status == JobStatus.QUEUED
    assert store.load_job("project_1", "study_1", "job_succeeded").status == JobStatus.SUCCEEDED
    assert store.load_job("project_2", "study_1", "job_other").status == JobStatus.RUNNING


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
