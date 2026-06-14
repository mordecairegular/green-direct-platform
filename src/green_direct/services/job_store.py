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

from green_direct.models.pilot_backend import Job, JobStatus
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
        queued_at=datetime.fromisoformat(data["queued_at"]),
        started_at=_parse_datetime(data.get("started_at")),
        finished_at=_parse_datetime(data.get("finished_at")),
        error_message=data.get("error_message"),
        progress_current=int(data.get("progress_current", 0)),
        progress_total=int(data.get("progress_total", 0)),
        progress_message=data.get("progress_message"),
    )


def _status_filter(statuses: Iterable[JobStatus | str] | None) -> set[JobStatus] | None:
    if statuses is None:
        return None
    return {JobStatus(status) for status in statuses}


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

    def start_job(
        self,
        project_id: str,
        study_id: str,
        job_id: str,
        *,
        started_at: datetime | None = None,
    ) -> Job:
        """Transition a queued job to running."""

        job = self.load_job(project_id, study_id, job_id).start(started_at=started_at)
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
    ) -> Job:
        """Persist progress counters for a queued or running job."""

        job = self.load_job(project_id, study_id, job_id).update_progress(
            current=current,
            total=total,
            message=message,
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
