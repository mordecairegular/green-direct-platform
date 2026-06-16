"""Permission-checked pilot backend service facade.

This service composes the local pilot registry, job store, and result store.
It keeps project membership checks and audit logging outside Streamlit pages so
future admin screens or database-backed adapters can reuse the same contract.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Iterable
from uuid import uuid4

from green_direct.models.pilot_backend import (
    AuditAction,
    AuditLog,
    Job,
    JobArtifact,
    JobStatus,
    JobType,
    Project,
    ProjectMembership,
    ProjectRole,
    ProjectStatus,
    StudyResultRecord,
    User,
)
from green_direct.services.job_store import LocalJobStore
from green_direct.services.pilot_registry import LocalPilotRegistry
from green_direct.services.result_store import LocalResultStore


class PilotAccessError(PermissionError):
    """Raised when a pilot user cannot perform a project operation."""


class PilotAccessService:
    """Small permission and audit facade for the internal pilot backend."""

    def __init__(
        self,
        *,
        registry: LocalPilotRegistry,
        job_store: LocalJobStore,
        result_store: LocalResultStore,
    ) -> None:
        self.registry = registry
        self.job_store = job_store
        self.result_store = result_store

    def _event_id(self) -> str:
        return f"audit_{uuid4().hex[:16]}"

    def _active_user(self, user_id: str) -> User:
        user = self.registry.load_user(user_id)
        if not user.is_active:
            raise PilotAccessError(f"User is disabled: {user_id}")
        return user

    def _platform_admin(self, user_id: str) -> User:
        user = self._active_user(user_id)
        if not user.is_platform_admin:
            raise PilotAccessError("User cannot manage platform operations.")
        return user

    def _project(self, project_id: str, *, require_active: bool) -> Project:
        project = self.registry.load_project(project_id)
        if require_active and project.status != ProjectStatus.ACTIVE:
            raise PilotAccessError(f"Project is not active: {project_id}")
        return project

    def _membership(self, project_id: str, user_id: str, *, require_active_project: bool) -> ProjectMembership:
        self._active_user(user_id)
        self._project(project_id, require_active=require_active_project)
        membership = self.registry.get_project_membership(project_id, user_id)
        if membership is None or not membership.is_active:
            raise PilotAccessError(f"User has no active membership in project: {project_id}")
        return membership

    def require_project_view(self, *, actor_user_id: str, project_id: str) -> ProjectMembership:
        membership = self._membership(project_id, actor_user_id, require_active_project=False)
        if not membership.can_view_project():
            raise PilotAccessError("User cannot view this project.")
        return membership

    def require_project_job_submit(self, *, actor_user_id: str, project_id: str) -> ProjectMembership:
        membership = self._membership(project_id, actor_user_id, require_active_project=True)
        if not membership.can_submit_jobs():
            raise PilotAccessError("User cannot submit jobs for this project.")
        return membership

    def require_project_admin(self, *, actor_user_id: str, project_id: str) -> ProjectMembership:
        membership = self._membership(project_id, actor_user_id, require_active_project=True)
        if not membership.can_manage_project():
            raise PilotAccessError("User cannot manage this project.")
        return membership

    def require_project_export(self, *, actor_user_id: str, project_id: str) -> ProjectMembership:
        membership = self._membership(project_id, actor_user_id, require_active_project=False)
        if not membership.can_download_artifacts():
            raise PilotAccessError("User cannot export or download artifacts for this project.")
        return membership

    def _audit(
        self,
        *,
        actor_user_id: str,
        action: AuditAction,
        project_id: str | None = None,
        study_id: str | None = None,
        job_id: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        metadata: dict | None = None,
    ) -> AuditLog:
        event = AuditLog(
            event_id=self._event_id(),
            actor_user_id=actor_user_id,
            action=action,
            project_id=project_id,
            study_id=study_id,
            job_id=job_id,
            target_type=target_type,
            target_id=target_id,
            metadata=metadata or {},
        )
        return self.result_store.append_audit_log(event)

    def create_project(self, *, actor_user_id: str, project: Project) -> Project:
        """Create a project and make the creator project admin."""

        actor = self._active_user(actor_user_id)
        project_to_save = project
        if project.created_by_user_id is None:
            project_to_save = replace(project, created_by_user_id=actor.user_id)
        elif project.created_by_user_id != actor.user_id:
            raise PilotAccessError("Project creator must match the actor user.")

        saved = self.registry.save_project(project_to_save)
        self.registry.grant_project_role(
            project_id=saved.project_id,
            user_id=actor.user_id,
            role=ProjectRole.ADMIN,
        )
        self._audit(
            actor_user_id=actor.user_id,
            action=AuditAction.CREATE_PROJECT,
            project_id=saved.project_id,
            target_type="project",
            target_id=saved.project_id,
            metadata={"name": saved.name},
        )
        return saved

    def list_accessible_projects(
        self,
        *,
        actor_user_id: str,
        include_archived: bool = False,
    ) -> list[tuple[Project, ProjectMembership]]:
        """List projects where the actor has an active membership."""

        self._active_user(actor_user_id)
        visible: list[tuple[Project, ProjectMembership]] = []
        for project in self.registry.list_projects():
            if not include_archived and project.status != ProjectStatus.ACTIVE:
                continue
            membership = self.registry.get_project_membership(project.project_id, actor_user_id)
            if membership is not None and membership.can_view_project():
                visible.append((project, membership))
        return visible

    def archive_project(self, *, actor_user_id: str, project_id: str) -> Project:
        """Archive a project after checking admin membership."""

        self.require_project_admin(actor_user_id=actor_user_id, project_id=project_id)
        archived = self.registry.archive_project(project_id)
        self._audit(
            actor_user_id=actor_user_id,
            action=AuditAction.UPDATE_PROJECT,
            project_id=project_id,
            target_type="project",
            target_id=project_id,
            metadata={"status": archived.status.value},
        )
        return archived

    def grant_project_role(
        self,
        *,
        actor_user_id: str,
        project_id: str,
        user_id: str,
        role: ProjectRole | str,
        can_export_artifacts: bool | None = None,
    ) -> ProjectMembership:
        """Grant or update a project role after checking admin membership."""

        self.require_project_admin(actor_user_id=actor_user_id, project_id=project_id)
        target = self._active_user(user_id)
        membership = self.registry.grant_project_role(
            project_id=project_id,
            user_id=target.user_id,
            role=role,
            can_export_artifacts=can_export_artifacts,
        )
        self._audit(
            actor_user_id=actor_user_id,
            action=AuditAction.UPDATE_MEMBERSHIP,
            project_id=project_id,
            target_type="project_membership",
            target_id=membership.membership_id,
            metadata={
                "user_id": target.user_id,
                "role": membership.role.value,
                "status": membership.status.value,
                "can_export_artifacts": membership.can_export_artifacts,
            },
        )
        return membership

    def disable_project_membership(
        self,
        *,
        actor_user_id: str,
        project_id: str,
        user_id: str,
    ) -> ProjectMembership:
        """Disable one project membership after checking admin membership."""

        self.require_project_admin(actor_user_id=actor_user_id, project_id=project_id)
        disabled = self.registry.disable_membership(project_id, user_id)
        self._audit(
            actor_user_id=actor_user_id,
            action=AuditAction.UPDATE_MEMBERSHIP,
            project_id=project_id,
            target_type="project_membership",
            target_id=disabled.membership_id,
            metadata={
                "user_id": user_id,
                "role": disabled.role.value,
                "status": disabled.status.value,
                "can_export_artifacts": disabled.can_export_artifacts,
            },
        )
        return disabled

    def submit_job(self, *, actor_user_id: str, job: Job, overwrite: bool = False) -> Job:
        """Submit a queued job if the actor can run work in the project."""

        if job.requested_by_user_id != actor_user_id:
            raise PilotAccessError("Job requester must match the actor user.")
        self.require_project_job_submit(actor_user_id=actor_user_id, project_id=job.project_id)
        saved = self.job_store.submit_job(job, overwrite=overwrite)
        self._audit(
            actor_user_id=actor_user_id,
            action=AuditAction.SUBMIT_JOB,
            project_id=job.project_id,
            study_id=job.study_id,
            job_id=job.job_id,
            target_type="job",
            target_id=job.job_id,
            metadata={"job_type": job.job_type.value, "status": job.status.value},
        )
        return saved

    def list_project_jobs(
        self,
        *,
        actor_user_id: str,
        project_id: str,
        statuses: Iterable[JobStatus | str] | None = None,
    ) -> list[Job]:
        """List project jobs visible to an active project member."""

        self.require_project_view(actor_user_id=actor_user_id, project_id=project_id)
        return self.job_store.list_project_jobs(project_id, statuses=statuses)

    def load_job(self, *, actor_user_id: str, project_id: str, study_id: str, job_id: str) -> Job:
        """Load a job visible to an active project member."""

        self.require_project_view(actor_user_id=actor_user_id, project_id=project_id)
        return self.job_store.load_job(project_id, study_id, job_id)

    def list_project_result_records(self, *, actor_user_id: str, project_id: str) -> list[StudyResultRecord]:
        """List stored result indexes visible to an active project member."""

        self.require_project_view(actor_user_id=actor_user_id, project_id=project_id)
        return self.result_store.list_project_result_records(project_id)

    def list_study_result_records(
        self,
        *,
        actor_user_id: str,
        project_id: str,
        study_id: str,
    ) -> list[StudyResultRecord]:
        """List stored result indexes for one study visible to an active project member."""

        self.require_project_view(actor_user_id=actor_user_id, project_id=project_id)
        return self.result_store.list_study_result_records(project_id, study_id)

    def delete_result_record(
        self,
        *,
        actor_user_id: str,
        project_id: str,
        study_id: str,
        result_id: str,
    ) -> StudyResultRecord:
        """Soft-delete a result index after checking project admin permission."""

        self.require_project_admin(actor_user_id=actor_user_id, project_id=project_id)
        deleted = self.result_store.soft_delete_result_record(
            project_id,
            study_id,
            result_id,
            deleted_by_user_id=actor_user_id,
        )
        self._audit(
            actor_user_id=actor_user_id,
            action=AuditAction.DELETE_RESULT_RECORD,
            project_id=project_id,
            study_id=study_id,
            job_id=deleted.created_by_job_id,
            target_type="result_record",
            target_id=result_id,
            metadata={
                "created_by_job_id": deleted.created_by_job_id,
                "deleted_at": deleted.deleted_at.isoformat() if deleted.deleted_at else None,
            },
        )
        return deleted

    def mark_result_record(
        self,
        *,
        actor_user_id: str,
        project_id: str,
        study_id: str,
        result_id: str,
        is_pinned: bool,
        label: str | None = None,
    ) -> StudyResultRecord:
        """Pin or unpin a result index after checking project admin permission."""

        self.require_project_admin(actor_user_id=actor_user_id, project_id=project_id)
        marked = self.result_store.mark_result_record(
            project_id,
            study_id,
            result_id,
            is_pinned=is_pinned,
            marked_by_user_id=actor_user_id,
            label=label,
        )
        self._audit(
            actor_user_id=actor_user_id,
            action=AuditAction.UPDATE_RESULT_RECORD,
            project_id=project_id,
            study_id=study_id,
            job_id=marked.created_by_job_id,
            target_type="result_record",
            target_id=result_id,
            metadata={
                "is_pinned": marked.is_pinned,
                "label": marked.label,
                "pinned_at": marked.pinned_at.isoformat() if marked.pinned_at else None,
            },
        )
        return marked

    def cancel_job(self, *, actor_user_id: str, project_id: str, study_id: str, job_id: str) -> Job:
        """Cancel a queued/running job; analysts may cancel only their own jobs."""

        membership = self.require_project_job_submit(actor_user_id=actor_user_id, project_id=project_id)
        job = self.job_store.load_job(project_id, study_id, job_id)
        if job.requested_by_user_id != actor_user_id and not membership.can_manage_project():
            raise PilotAccessError("Only project admins can cancel another user's job.")
        canceled = self.job_store.cancel_job(project_id, study_id, job_id)
        self._audit(
            actor_user_id=actor_user_id,
            action=AuditAction.CANCEL_JOB,
            project_id=project_id,
            study_id=study_id,
            job_id=job_id,
            target_type="job",
            target_id=job_id,
            metadata={"status": canceled.status.value},
        )
        return canceled

    def _job_mutation_membership(self, *, actor_user_id: str, job: Job) -> ProjectMembership:
        membership = self.require_project_job_submit(actor_user_id=actor_user_id, project_id=job.project_id)
        if job.requested_by_user_id != actor_user_id and not membership.can_manage_project():
            raise PilotAccessError("Only project admins can update another user's job.")
        return membership

    def start_job(
        self,
        *,
        actor_user_id: str,
        project_id: str,
        study_id: str,
        job_id: str,
        worker_id: str | None = None,
    ) -> Job:
        """Start a queued job after checking owner/admin permission."""

        job = self.job_store.load_job(project_id, study_id, job_id)
        self._job_mutation_membership(actor_user_id=actor_user_id, job=job)
        return self.job_store.start_job(project_id, study_id, job_id, worker_id=worker_id)

    def claim_next_job_for_worker(
        self,
        *,
        actor_user_id: str,
        worker_id: str,
        project_id: str | None = None,
        job_types: Iterable[JobType | str] | None = None,
        claimed_at: datetime | None = None,
    ) -> Job | None:
        """Claim the oldest queued job for a trusted worker process.

        This is a server-side queue primitive for the internal pilot. It is
        intentionally platform-admin guarded and skips archived projects; it is
        not a public user action or a durable distributed queue lock.
        """

        self._platform_admin(actor_user_id)
        accepted_types = (
            {JobType(job_type) for job_type in job_types}
            if job_types is not None
            else None
        )
        if project_id is not None:
            self._project(project_id, require_active=True)
            return self.job_store.claim_next_queued_job(
                worker_id=worker_id,
                project_id=project_id,
                job_types=accepted_types,
                claimed_at=claimed_at,
            )

        active_project_ids = {
            project.project_id
            for project in self.registry.list_projects()
            if project.status == ProjectStatus.ACTIVE
        }
        for candidate in self.job_store.list_jobs(statuses=[JobStatus.QUEUED]):
            if candidate.project_id not in active_project_ids:
                continue
            if accepted_types is not None and candidate.job_type not in accepted_types:
                continue
            try:
                return self.job_store.start_job(
                    candidate.project_id,
                    candidate.study_id,
                    candidate.job_id,
                    started_at=claimed_at,
                    worker_id=worker_id,
                )
            except ValueError:
                continue
        return None

    def _running_worker_job(
        self,
        *,
        actor_user_id: str,
        worker_id: str,
        project_id: str,
        study_id: str,
        job_id: str,
    ) -> Job:
        self._platform_admin(actor_user_id)
        job = self.job_store.load_job(project_id, study_id, job_id)
        if job.status != JobStatus.RUNNING:
            raise PilotAccessError("Worker can only update running jobs.")
        if job.worker_id != worker_id:
            raise PilotAccessError("Job is assigned to another worker.")
        return job

    def update_worker_job_progress(
        self,
        *,
        actor_user_id: str,
        worker_id: str,
        project_id: str,
        study_id: str,
        job_id: str,
        current: int | None = None,
        total: int | None = None,
        message: str | None = None,
        heartbeat_at: datetime | None = None,
    ) -> Job:
        """Update progress and heartbeat for a running job owned by a trusted worker."""

        job = self._running_worker_job(
            actor_user_id=actor_user_id,
            worker_id=worker_id,
            project_id=project_id,
            study_id=study_id,
            job_id=job_id,
        )
        return self.job_store.update_job_progress(
            project_id,
            study_id,
            job_id,
            current=job.progress_current if current is None else current,
            total=total,
            message=job.progress_message if message is None else message,
            worker_id=worker_id,
            heartbeat_at=heartbeat_at or datetime.now(timezone.utc),
        )

    def succeed_worker_job(
        self,
        *,
        actor_user_id: str,
        worker_id: str,
        project_id: str,
        study_id: str,
        job_id: str,
        finished_at: datetime | None = None,
    ) -> Job:
        """Mark a trusted worker's running job as succeeded and audit completion."""

        self._running_worker_job(
            actor_user_id=actor_user_id,
            worker_id=worker_id,
            project_id=project_id,
            study_id=study_id,
            job_id=job_id,
        )
        succeeded = self.job_store.succeed_job(project_id, study_id, job_id, finished_at=finished_at)
        self._audit(
            actor_user_id=actor_user_id,
            action=AuditAction.COMPLETE_JOB,
            project_id=project_id,
            study_id=study_id,
            job_id=job_id,
            target_type="job",
            target_id=job_id,
            metadata={"status": succeeded.status.value, "worker_id": worker_id},
        )
        return succeeded

    def fail_worker_job(
        self,
        *,
        actor_user_id: str,
        worker_id: str,
        project_id: str,
        study_id: str,
        job_id: str,
        error_message: str,
        finished_at: datetime | None = None,
    ) -> Job:
        """Mark a trusted worker's running job as failed and audit completion."""

        self._running_worker_job(
            actor_user_id=actor_user_id,
            worker_id=worker_id,
            project_id=project_id,
            study_id=study_id,
            job_id=job_id,
        )
        failed = self.job_store.fail_job(project_id, study_id, job_id, error_message, finished_at=finished_at)
        self._audit(
            actor_user_id=actor_user_id,
            action=AuditAction.COMPLETE_JOB,
            project_id=project_id,
            study_id=study_id,
            job_id=job_id,
            target_type="job",
            target_id=job_id,
            metadata={
                "status": failed.status.value,
                "worker_id": worker_id,
                "error_message": failed.error_message,
            },
        )
        return failed

    def update_job_progress(
        self,
        *,
        actor_user_id: str,
        project_id: str,
        study_id: str,
        job_id: str,
        current: int,
        total: int | None = None,
        message: str | None = None,
        worker_id: str | None = None,
        heartbeat_at: datetime | None = None,
    ) -> Job:
        """Persist job progress after checking owner/admin permission."""

        job = self.job_store.load_job(project_id, study_id, job_id)
        self._job_mutation_membership(actor_user_id=actor_user_id, job=job)
        return self.job_store.update_job_progress(
            project_id,
            study_id,
            job_id,
            current=current,
            total=total,
            message=message,
            worker_id=worker_id,
            heartbeat_at=heartbeat_at,
        )

    def succeed_job(self, *, actor_user_id: str, project_id: str, study_id: str, job_id: str) -> Job:
        """Mark a running job as succeeded and audit completion."""

        job = self.job_store.load_job(project_id, study_id, job_id)
        self._job_mutation_membership(actor_user_id=actor_user_id, job=job)
        succeeded = self.job_store.succeed_job(project_id, study_id, job_id)
        self._audit(
            actor_user_id=actor_user_id,
            action=AuditAction.COMPLETE_JOB,
            project_id=project_id,
            study_id=study_id,
            job_id=job_id,
            target_type="job",
            target_id=job_id,
            metadata={"status": succeeded.status.value},
        )
        return succeeded

    def fail_job(
        self,
        *,
        actor_user_id: str,
        project_id: str,
        study_id: str,
        job_id: str,
        error_message: str,
    ) -> Job:
        """Mark a running job as failed and audit completion."""

        job = self.job_store.load_job(project_id, study_id, job_id)
        self._job_mutation_membership(actor_user_id=actor_user_id, job=job)
        failed = self.job_store.fail_job(project_id, study_id, job_id, error_message)
        self._audit(
            actor_user_id=actor_user_id,
            action=AuditAction.COMPLETE_JOB,
            project_id=project_id,
            study_id=study_id,
            job_id=job_id,
            target_type="job",
            target_id=job_id,
            metadata={"status": failed.status.value, "error_message": failed.error_message},
        )
        return failed

    def load_artifact(self, *, actor_user_id: str, project_id: str, study_id: str, artifact_id: str) -> JobArtifact:
        """Load an artifact index visible to an active project member."""

        self.require_project_view(actor_user_id=actor_user_id, project_id=project_id)
        return self.result_store.load_artifact(project_id, study_id, artifact_id)

    def read_artifact_payload(self, *, actor_user_id: str, artifact: JobArtifact) -> bytes:
        """Read artifact bytes and audit the download action."""

        try:
            self.require_project_export(actor_user_id=actor_user_id, project_id=artifact.project_id)
        except PilotAccessError as exc:
            self._audit(
                actor_user_id=actor_user_id,
                action=AuditAction.DOWNLOAD_ARTIFACT,
                project_id=artifact.project_id,
                study_id=artifact.study_id,
                job_id=artifact.job_id,
                target_type="artifact",
                target_id=artifact.artifact_id,
                metadata={
                    "kind": artifact.kind.value,
                    "size_bytes": artifact.size_bytes,
                    "success": False,
                    "reason": str(exc),
                },
            )
            raise
        payload = self.result_store.read_artifact_payload(artifact)
        self._audit(
            actor_user_id=actor_user_id,
            action=AuditAction.DOWNLOAD_ARTIFACT,
            project_id=artifact.project_id,
            study_id=artifact.study_id,
            job_id=artifact.job_id,
            target_type="artifact",
            target_id=artifact.artifact_id,
            metadata={"kind": artifact.kind.value, "size_bytes": artifact.size_bytes, "success": True},
        )
        return payload

    def record_transient_export_download(
        self,
        *,
        actor_user_id: str,
        project_id: str,
        study_id: str | None,
        export_key: str,
        file_name: str,
        content_type: str,
        size_bytes: int | None = None,
        metadata: dict | None = None,
    ) -> AuditLog:
        """Audit an in-memory export download that is not yet a stored artifact."""

        event_metadata = {
            **(metadata or {}),
            "export_key": str(export_key),
            "file_name": str(file_name),
            "content_type": str(content_type),
        }
        if size_bytes is not None:
            event_metadata["size_bytes"] = int(size_bytes)
        try:
            self.require_project_export(actor_user_id=actor_user_id, project_id=project_id)
        except PilotAccessError as exc:
            self._audit(
                actor_user_id=actor_user_id,
                action=AuditAction.DOWNLOAD_ARTIFACT,
                project_id=project_id,
                study_id=study_id,
                target_type="transient_export",
                target_id=str(export_key),
                metadata={
                    **event_metadata,
                    "success": False,
                    "reason": str(exc),
                },
            )
            raise
        return self._audit(
            actor_user_id=actor_user_id,
            action=AuditAction.DOWNLOAD_ARTIFACT,
            project_id=project_id,
            study_id=study_id,
            target_type="transient_export",
            target_id=str(export_key),
            metadata={**event_metadata, "success": True},
        )

    def read_artifact_payload_for_view(self, *, actor_user_id: str, artifact: JobArtifact) -> bytes:
        """Read artifact bytes for in-app viewing without granting file download rights."""

        try:
            self.require_project_view(actor_user_id=actor_user_id, project_id=artifact.project_id)
        except PilotAccessError as exc:
            self._audit(
                actor_user_id=actor_user_id,
                action=AuditAction.VIEW_ARTIFACT,
                project_id=artifact.project_id,
                study_id=artifact.study_id,
                job_id=artifact.job_id,
                target_type="artifact",
                target_id=artifact.artifact_id,
                metadata={
                    "kind": artifact.kind.value,
                    "size_bytes": artifact.size_bytes,
                    "success": False,
                    "reason": str(exc),
                },
            )
            raise
        try:
            payload = self.result_store.read_artifact_payload(artifact)
        except Exception as exc:
            self._audit(
                actor_user_id=actor_user_id,
                action=AuditAction.VIEW_ARTIFACT,
                project_id=artifact.project_id,
                study_id=artifact.study_id,
                job_id=artifact.job_id,
                target_type="artifact",
                target_id=artifact.artifact_id,
                metadata={
                    "kind": artifact.kind.value,
                    "size_bytes": artifact.size_bytes,
                    "success": False,
                    "reason": str(exc),
                },
            )
            raise
        self._audit(
            actor_user_id=actor_user_id,
            action=AuditAction.VIEW_ARTIFACT,
            project_id=artifact.project_id,
            study_id=artifact.study_id,
            job_id=artifact.job_id,
            target_type="artifact",
            target_id=artifact.artifact_id,
            metadata={"kind": artifact.kind.value, "size_bytes": artifact.size_bytes, "success": True},
        )
        return payload
