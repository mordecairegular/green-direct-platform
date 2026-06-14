"""Persistence-neutral models for the internal multi-user pilot backend.

These models define account, project, job, artifact, and audit boundaries.
They do not introduce authentication, a database, or a task queue by
themselves; those runtime concerns can be added in later slices.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _require_text(value: str, field_name: str) -> None:
    if not str(value).strip():
        raise ValueError(f"{field_name} must not be empty.")


def _require_non_negative(value: int, field_name: str) -> None:
    if int(value) < 0:
        raise ValueError(f"{field_name} must be non-negative.")


def _coerce_enum(value: Any, enum_type: type[Enum], field_name: str) -> Enum:
    try:
        return enum_type(value)
    except ValueError as exc:
        valid_values = ", ".join(member.value for member in enum_type)
        raise ValueError(f"{field_name} must be one of: {valid_values}.") from exc


def _ensure_aware(value: datetime | None, field_name: str) -> None:
    if value is not None and value.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware.")


class UserStatus(str, Enum):
    ACTIVE = "active"
    DISABLED = "disabled"


class ProjectStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class ProjectRole(str, Enum):
    ADMIN = "admin"
    ANALYST = "analyst"
    VIEWER = "viewer"


class MembershipStatus(str, Enum):
    ACTIVE = "active"
    DISABLED = "disabled"


class JobType(str, Enum):
    TECHNICAL_STUDY = "technical_study"
    ECONOMIC_STUDY = "economic_study"
    RECOMMENDATION = "recommendation"
    CHART_EXPORT = "chart_export"
    REPORT_EXPORT = "report_export"


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"


class ArtifactKind(str, Enum):
    INPUT_CURVE = "input_curve"
    TECHNICAL_SUMMARY = "technical_summary"
    HOURLY_DETAIL = "hourly_detail"
    ECONOMY_SUMMARY = "economy_summary"
    ANNUAL_CASHFLOW = "annual_cashflow"
    RECOMMENDATION_PORTFOLIO = "recommendation_portfolio"
    CHART_PACKAGE = "chart_package"
    REPORT = "report"


class AuditAction(str, Enum):
    LOGIN = "login"
    CREATE_USER = "create_user"
    UPDATE_USER = "update_user"
    CREATE_PROJECT = "create_project"
    UPDATE_MEMBERSHIP = "update_membership"
    UPLOAD_INPUT = "upload_input"
    SUBMIT_JOB = "submit_job"
    COMPLETE_JOB = "complete_job"
    DOWNLOAD_ARTIFACT = "download_artifact"
    DELETE_ARTIFACT = "delete_artifact"


@dataclass(frozen=True)
class User:
    """Internal pilot user.

    Passwords and identity-provider credentials intentionally stay outside
    this domain model. Store only provider subject IDs or login names here.
    """

    user_id: str
    login_name: str
    display_name: str
    status: UserStatus | str = UserStatus.ACTIVE
    created_at: datetime = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        _require_text(self.user_id, "user_id")
        _require_text(self.login_name, "login_name")
        _require_text(self.display_name, "display_name")
        _ensure_aware(self.created_at, "created_at")
        object.__setattr__(self, "status", _coerce_enum(self.status, UserStatus, "status"))

    @property
    def is_active(self) -> bool:
        return self.status == UserStatus.ACTIVE


@dataclass(frozen=True)
class Project:
    """A project workspace that owns studies, jobs, and stored artifacts."""

    project_id: str
    name: str
    status: ProjectStatus | str = ProjectStatus.ACTIVE
    created_by_user_id: str | None = None
    created_at: datetime = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        _require_text(self.project_id, "project_id")
        _require_text(self.name, "name")
        _ensure_aware(self.created_at, "created_at")
        object.__setattr__(self, "status", _coerce_enum(self.status, ProjectStatus, "status"))


@dataclass(frozen=True)
class ProjectMembership:
    """Role assignment for one user in one project."""

    membership_id: str
    project_id: str
    user_id: str
    role: ProjectRole | str
    status: MembershipStatus | str = MembershipStatus.ACTIVE
    created_at: datetime = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        _require_text(self.membership_id, "membership_id")
        _require_text(self.project_id, "project_id")
        _require_text(self.user_id, "user_id")
        _ensure_aware(self.created_at, "created_at")
        object.__setattr__(self, "role", _coerce_enum(self.role, ProjectRole, "role"))
        object.__setattr__(self, "status", _coerce_enum(self.status, MembershipStatus, "status"))

    @property
    def is_active(self) -> bool:
        return self.status == MembershipStatus.ACTIVE

    def can_view_project(self) -> bool:
        return self.is_active

    def can_submit_jobs(self) -> bool:
        return self.is_active and self.role in {ProjectRole.ADMIN, ProjectRole.ANALYST}

    def can_manage_project(self) -> bool:
        return self.is_active and self.role == ProjectRole.ADMIN


@dataclass(frozen=True)
class ProjectStudy:
    """One immutable input snapshot under a project."""

    study_id: str
    project_id: str
    created_by_user_id: str
    input_fingerprint: str
    config_snapshot_ref: str | None = None
    created_at: datetime = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        _require_text(self.study_id, "study_id")
        _require_text(self.project_id, "project_id")
        _require_text(self.created_by_user_id, "created_by_user_id")
        _require_text(self.input_fingerprint, "input_fingerprint")
        _ensure_aware(self.created_at, "created_at")


_TERMINAL_JOB_STATUSES = {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELED}


@dataclass(frozen=True)
class Job:
    """Background task boundary for technical, economy, recommendation, or export work."""

    job_id: str
    project_id: str
    study_id: str
    requested_by_user_id: str
    job_type: JobType | str
    status: JobStatus | str = JobStatus.QUEUED
    input_fingerprint: str | None = None
    queued_at: datetime = field(default_factory=_utcnow)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.job_id, "job_id")
        _require_text(self.project_id, "project_id")
        _require_text(self.study_id, "study_id")
        _require_text(self.requested_by_user_id, "requested_by_user_id")
        _ensure_aware(self.queued_at, "queued_at")
        _ensure_aware(self.started_at, "started_at")
        _ensure_aware(self.finished_at, "finished_at")
        object.__setattr__(self, "job_type", _coerce_enum(self.job_type, JobType, "job_type"))
        object.__setattr__(self, "status", _coerce_enum(self.status, JobStatus, "status"))

    @property
    def is_terminal(self) -> bool:
        return self.status in _TERMINAL_JOB_STATUSES

    def start(self, *, started_at: datetime | None = None) -> "Job":
        if self.status != JobStatus.QUEUED:
            raise ValueError("Only queued jobs can be started.")
        timestamp = started_at or _utcnow()
        _ensure_aware(timestamp, "started_at")
        return replace(self, status=JobStatus.RUNNING, started_at=timestamp, error_message=None)

    def succeed(self, *, finished_at: datetime | None = None) -> "Job":
        if self.status != JobStatus.RUNNING:
            raise ValueError("Only running jobs can succeed.")
        timestamp = finished_at or _utcnow()
        _ensure_aware(timestamp, "finished_at")
        return replace(self, status=JobStatus.SUCCEEDED, finished_at=timestamp, error_message=None)

    def fail(self, error_message: str, *, finished_at: datetime | None = None) -> "Job":
        if self.status != JobStatus.RUNNING:
            raise ValueError("Only running jobs can fail.")
        _require_text(error_message, "error_message")
        timestamp = finished_at or _utcnow()
        _ensure_aware(timestamp, "finished_at")
        return replace(self, status=JobStatus.FAILED, finished_at=timestamp, error_message=error_message)

    def cancel(self, *, finished_at: datetime | None = None) -> "Job":
        if self.is_terminal:
            raise ValueError("Terminal jobs cannot be canceled.")
        timestamp = finished_at or _utcnow()
        _ensure_aware(timestamp, "finished_at")
        return replace(self, status=JobStatus.CANCELED, finished_at=timestamp)


@dataclass(frozen=True)
class JobArtifact:
    """Artifact reference produced by a job and owned by one project/study."""

    artifact_id: str
    project_id: str
    study_id: str
    job_id: str
    kind: ArtifactKind | str
    storage_uri: str
    content_type: str = "application/octet-stream"
    sha256: str | None = None
    size_bytes: int = 0
    created_at: datetime = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        _require_text(self.artifact_id, "artifact_id")
        _require_text(self.project_id, "project_id")
        _require_text(self.study_id, "study_id")
        _require_text(self.job_id, "job_id")
        _require_text(self.storage_uri, "storage_uri")
        _require_text(self.content_type, "content_type")
        _require_non_negative(self.size_bytes, "size_bytes")
        _ensure_aware(self.created_at, "created_at")
        object.__setattr__(self, "kind", _coerce_enum(self.kind, ArtifactKind, "kind"))


@dataclass(frozen=True)
class StudyResultRecord:
    """Index record for result artifacts stored outside Streamlit session_state."""

    result_id: str
    project_id: str
    study_id: str
    created_by_job_id: str
    technical_summary_artifact_id: str | None = None
    economy_summary_artifact_id: str | None = None
    single_entity_summary_artifact_id: str | None = None
    recommendation_artifact_id: str | None = None
    hourly_detail_artifact_ids: Mapping[str, str] = field(default_factory=dict)
    report_artifact_ids: Mapping[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        _require_text(self.result_id, "result_id")
        _require_text(self.project_id, "project_id")
        _require_text(self.study_id, "study_id")
        _require_text(self.created_by_job_id, "created_by_job_id")
        _ensure_aware(self.created_at, "created_at")
        object.__setattr__(self, "hourly_detail_artifact_ids", dict(self.hourly_detail_artifact_ids))
        object.__setattr__(self, "report_artifact_ids", dict(self.report_artifact_ids))


@dataclass(frozen=True)
class AuditLog:
    """Append-only audit event for pilot operations."""

    event_id: str
    actor_user_id: str
    action: AuditAction | str
    project_id: str | None = None
    study_id: str | None = None
    job_id: str | None = None
    target_type: str | None = None
    target_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        _require_text(self.event_id, "event_id")
        _require_text(self.actor_user_id, "actor_user_id")
        _ensure_aware(self.created_at, "created_at")
        object.__setattr__(self, "action", _coerce_enum(self.action, AuditAction, "action"))
        object.__setattr__(self, "metadata", dict(self.metadata))
