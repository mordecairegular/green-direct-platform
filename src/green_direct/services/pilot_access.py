"""Permission-checked pilot backend service facade.

This service composes the local pilot registry, job store, and result store.
It keeps project membership checks and audit logging outside Streamlit pages so
future admin screens or database-backed adapters can reuse the same contract.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Iterable
from uuid import uuid4

from green_direct.models.pilot_backend import (
    AuditAction,
    AuditLog,
    Job,
    JobArtifact,
    JobStatus,
    Project,
    ProjectMembership,
    ProjectRole,
    ProjectStatus,
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
    ) -> ProjectMembership:
        """Grant or update a project role after checking admin membership."""

        self.require_project_admin(actor_user_id=actor_user_id, project_id=project_id)
        target = self._active_user(user_id)
        membership = self.registry.grant_project_role(
            project_id=project_id,
            user_id=target.user_id,
            role=role,
        )
        self._audit(
            actor_user_id=actor_user_id,
            action=AuditAction.UPDATE_MEMBERSHIP,
            project_id=project_id,
            target_type="project_membership",
            target_id=membership.membership_id,
            metadata={"user_id": target.user_id, "role": membership.role.value, "status": membership.status.value},
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
            metadata={"user_id": user_id, "role": disabled.role.value, "status": disabled.status.value},
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

    def load_artifact(self, *, actor_user_id: str, project_id: str, study_id: str, artifact_id: str) -> JobArtifact:
        """Load an artifact index visible to an active project member."""

        self.require_project_view(actor_user_id=actor_user_id, project_id=project_id)
        return self.result_store.load_artifact(project_id, study_id, artifact_id)

    def read_artifact_payload(self, *, actor_user_id: str, artifact: JobArtifact) -> bytes:
        """Read artifact bytes and audit the download action."""

        self.require_project_view(actor_user_id=actor_user_id, project_id=artifact.project_id)
        payload = self.result_store.read_artifact_payload(artifact)
        self._audit(
            actor_user_id=actor_user_id,
            action=AuditAction.DOWNLOAD_ARTIFACT,
            project_id=artifact.project_id,
            study_id=artifact.study_id,
            job_id=artifact.job_id,
            target_type="artifact",
            target_id=artifact.artifact_id,
            metadata={"kind": artifact.kind.value, "size_bytes": artifact.size_bytes},
        )
        return payload
