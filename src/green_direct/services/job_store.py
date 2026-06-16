"""Local file-backed JobStore for the internal pilot.

This adapter persists background job metadata by project and study. It is a
small bridge toward queued technical/economy/recommendation/export work, not a
worker process or distributed task queue by itself.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Iterable

from green_direct.models.pilot_backend import Job, JobStatus, JobType
from green_direct.services.local_store_utils import (
    read_json,
    validate_path_segment,
    write_json,
)


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)


def _job_from_json(data: dict) -> Job:
    return Job(
        job_id=data["job_id"],
        project_id=data["project_id"],
        study_id=data["study_id"],
        requested_by_user_id=data["requested_by_user_id"],
        job_type=data["job_type"],
        status=data.get("status", JobStatus.QUEUED.value),
        input_fingerprint=data.get("input_fingerprint"),
        input_artifact_ids=data.get("input_artifact_ids") or {},
        queued_at=datetime.fromisoformat(data["queued_at"]),
        started_at=_parse_datetime(data.get("started_at")),
        finished_at=_parse_datetime(data.get("finished_at")),
        error_message=data.get("error_message"),
        progress_current=int(data.get("progress_current", 0)),
        progress_total=int(data.get("progress_total", 0)),
        progress_message=data.get("progress_message"),
        worker_id=data.get("worker_id"),
        last_heartbeat_at=_parse_datetime(data.get("last_heartbeat_at")),
    )


def _status_filter(statuses: Iterable[JobStatus | str] | None) -> set[JobStatus] | None:
    if statuses is None:
        return None
    return {JobStatus(status) for status in statuses}


def _job_type_filter(job_types: Iterable[JobType | str] | None) -> set[JobType] | None:
    if job_types is None:
        return None
    return {JobType(job_type) for job_type in job_types}


class LocalJobStore:
    """Project/study-scoped local job metadata store."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

    def _project_dir(self, project_id: str) -> Path:
        return self.root / "projects" / validate_path_segment(project_id, "project_id")

    def _study_dir(self, project_id: str, study_id: str) -> Path:
        return self._project_dir(project_id) / "studies" / validate_path_segment(study_id, "study_id")

    def _jobs_dir(self, project_id: str, study_id: str) -> Path:
        return self._study_dir(project_id, study_id) / "jobs"

    def _job_path(self, project_id: str, study_id: str, job_id: str) -> Path:
        return self._jobs_dir(project_id, study_id) / f"{validate_path_segment(job_id, 'job_id')}.json"

    def _save_job(self, job: Job, *, overwrite: bool = True) -> Job:
        path = self._job_path(job.project_id, job.study_id, job.job_id)
        if path.exists() and not overwrite:
            raise FileExistsError(f"Job already exists: {job.job_id}")
        write_json(path, asdict(job))
        return job

    def _all_jobs(self, *, statuses: Iterable[JobStatus | str] | None = None) -> list[Job]:
        accepted_statuses = _status_filter(statuses)
        projects_dir = self.root / "projects"
        if not projects_dir.exists():
            return []
        jobs = [
            _job_from_json(read_json(path))
            for path in sorted(projects_dir.glob("*/studies/*/jobs/*.json"))
        ]
        if accepted_statuses is not None:
            jobs = [job for job in jobs if job.status in accepted_statuses]
        return sorted(jobs, key=lambda job: (job.queued_at, job.project_id, job.study_id, job.job_id))

    def submit_job(self, job: Job, *, overwrite: bool = False) -> Job:
        """Persist a queued job request."""

        if job.status != JobStatus.QUEUED:
            raise ValueError("Only queued jobs can be submitted.")
        return self._save_job(job, overwrite=overwrite)

    def load_job(self, project_id: str, study_id: str, job_id: str) -> Job:
        """Load one job by project, study, and job id."""

        return _job_from_json(read_json(self._job_path(project_id, study_id, job_id)))

    def list_study_jobs(
        self,
        project_id: str,
        study_id: str,
        *,
        statuses: Iterable[JobStatus | str] | None = None,
    ) -> list[Job]:
        """List jobs under one study, sorted by queued time then job id."""

        accepted_statuses = _status_filter(statuses)
        directory = self._jobs_dir(project_id, study_id)
        if not directory.exists():
            return []
        jobs = [_job_from_json(read_json(path)) for path in sorted(directory.glob("*.json"))]
        if accepted_statuses is not None:
            jobs = [job for job in jobs if job.status in accepted_statuses]
        return sorted(jobs, key=lambda job: (job.queued_at, job.job_id))

    def list_project_jobs(
        self,
        project_id: str,
        *,
        statuses: Iterable[JobStatus | str] | None = None,
    ) -> list[Job]:
        """List jobs under every study in one project."""

        accepted_statuses = _status_filter(statuses)
        project_dir = self._project_dir(project_id)
        if not project_dir.exists():
            return []
        jobs = [
            _job_from_json(read_json(path))
            for path in sorted(project_dir.glob("studies/*/jobs/*.json"))
        ]
        if accepted_statuses is not None:
            jobs = [job for job in jobs if job.status in accepted_statuses]
        return sorted(jobs, key=lambda job: (job.queued_at, job.study_id, job.job_id))

    def list_jobs(
        self,
        *,
        project_id: str | None = None,
        statuses: Iterable[JobStatus | str] | None = None,
    ) -> list[Job]:
        """List jobs across the local store, optionally scoped to one project."""

        if project_id is not None:
            return self.list_project_jobs(project_id, statuses=statuses)
        return self._all_jobs(statuses=statuses)

    def claim_next_queued_job(
        self,
        *,
        worker_id: str,
        project_id: str | None = None,
        job_types: Iterable[JobType | str] | None = None,
        claimed_at: datetime | None = None,
    ) -> Job | None:
        """Start the oldest queued job matching the filters and assign it to a worker.

        This local-file adapter re-loads a candidate before starting it, which
        avoids claiming jobs that were already canceled or completed by another
        code path. It is still not a cross-process queue lock.
        """

        accepted_types = _job_type_filter(job_types)
        queued_jobs = self.list_jobs(project_id=project_id, statuses=[JobStatus.QUEUED])
        for candidate in queued_jobs:
            if accepted_types is not None and candidate.job_type not in accepted_types:
                continue
            try:
                return self.start_job(
                    candidate.project_id,
                    candidate.study_id,
                    candidate.job_id,
                    started_at=claimed_at,
                    worker_id=worker_id,
                )
            except ValueError:
                continue
        return None

    def start_job(
        self,
        project_id: str,
        study_id: str,
        job_id: str,
        *,
        started_at: datetime | None = None,
        worker_id: str | None = None,
    ) -> Job:
        """Transition a queued job to running."""

        job = self.load_job(project_id, study_id, job_id).start(
            started_at=started_at,
            worker_id=worker_id,
        )
        return self._save_job(job)

    def update_job_progress(
        self,
        project_id: str,
        study_id: str,
        job_id: str,
        *,
        current: int,
        total: int | None = None,
        message: str | None = None,
        worker_id: str | None = None,
        heartbeat_at: datetime | None = None,
    ) -> Job:
        """Persist progress counters for a queued or running job."""

        job = self.load_job(project_id, study_id, job_id).update_progress(
            current=current,
            total=total,
            message=message,
            worker_id=worker_id,
            heartbeat_at=heartbeat_at,
        )
        return self._save_job(job)

    def succeed_job(
        self,
        project_id: str,
        study_id: str,
        job_id: str,
        *,
        finished_at: datetime | None = None,
    ) -> Job:
        """Transition a running job to succeeded."""

        job = self.load_job(project_id, study_id, job_id).succeed(finished_at=finished_at)
        return self._save_job(job)

    def fail_job(
        self,
        project_id: str,
        study_id: str,
        job_id: str,
        error_message: str,
        *,
        finished_at: datetime | None = None,
    ) -> Job:
        """Transition a running job to failed."""

        job = self.load_job(project_id, study_id, job_id).fail(error_message, finished_at=finished_at)
        return self._save_job(job)

    def cancel_job(
        self,
        project_id: str,
        study_id: str,
        job_id: str,
        *,
        finished_at: datetime | None = None,
    ) -> Job:
        """Cancel a queued or running job."""

        job = self.load_job(project_id, study_id, job_id).cancel(finished_at=finished_at)
        return self._save_job(job)

    def list_stale_running_jobs(
        self,
        *,
        now: datetime,
        stale_after_seconds: int,
        project_id: str | None = None,
    ) -> list[Job]:
        """List running jobs whose heartbeat or start time is older than the threshold."""

        jobs = (
            self.list_project_jobs(project_id, statuses=[JobStatus.RUNNING])
            if project_id is not None
            else self._all_jobs(statuses=[JobStatus.RUNNING])
        )
        return [
            job
            for job in jobs
            if job.is_stale(now=now, stale_after_seconds=stale_after_seconds)
        ]

    def fail_stale_running_jobs(
        self,
        *,
        now: datetime,
        stale_after_seconds: int,
        error_message: str = "Marked failed because no heartbeat was received within the configured timeout.",
        project_id: str | None = None,
    ) -> list[Job]:
        """Mark stale running jobs failed and return the updated job records."""

        failed: list[Job] = []
        for stale_job in self.list_stale_running_jobs(
            now=now,
            stale_after_seconds=stale_after_seconds,
            project_id=project_id,
        ):
            current = self.load_job(stale_job.project_id, stale_job.study_id, stale_job.job_id)
            if not current.is_stale(now=now, stale_after_seconds=stale_after_seconds):
                continue
            failed.append(
                self.fail_job(
                    current.project_id,
                    current.study_id,
                    current.job_id,
                    error_message,
                    finished_at=now,
                )
            )
        return failed
