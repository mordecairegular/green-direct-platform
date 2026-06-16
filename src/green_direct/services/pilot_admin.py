"""Platform-administration service for the internal pilot backend."""

from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

from green_direct.models.pilot_backend import (
    AuditAction,
    AuditLog,
    Project,
    ProjectMembership,
    ProjectRole,
    ProjectStatus,
    User,
    UserStatus,
)
from green_direct.services.pilot_auth import LocalPilotAuth, MIN_PASSWORD_LENGTH, PilotSessionRecord
from green_direct.services.pilot_registry import LocalPilotRegistry
from green_direct.services.result_store import LocalResultStore


class PilotAdminError(PermissionError):
    """Raised when a user cannot perform platform administration."""


class LocalPilotAdminService:
    """Account-management facade guarded by a platform-admin flag."""

    def __init__(
        self,
        *,
        registry: LocalPilotRegistry,
        auth: LocalPilotAuth,
        result_store: LocalResultStore,
    ) -> None:
        self.registry = registry
        self.auth = auth
        self.result_store = result_store

    def _event_id(self) -> str:
        return f"audit_{uuid4().hex[:16]}"

    def _audit(
        self,
        *,
        actor_user_id: str,
        action: AuditAction,
        target_user_id: str | None = None,
        project_id: str | None = None,
        target_type: str = "user",
        target_id: str | None = None,
        metadata: dict | None = None,
    ) -> AuditLog:
        return self.result_store.append_audit_log(
            AuditLog(
                event_id=self._event_id(),
                actor_user_id=actor_user_id,
                action=action,
                project_id=project_id,
                target_type=target_type,
                target_id=target_id or target_user_id,
                metadata=metadata or {},
            )
        )

    def _platform_admin(self, actor_user_id: str) -> User:
        actor = self.registry.load_user(actor_user_id)
        if not actor.is_active:
            raise PilotAdminError(f"User is disabled: {actor_user_id}")
        if not actor.is_platform_admin:
            raise PilotAdminError("User cannot manage platform accounts.")
        return actor

    def _ensure_unique_login_name(self, login_name: str, *, except_user_id: str | None = None) -> None:
        normalized = str(login_name).strip().casefold()
        for user in self.registry.list_users():
            if except_user_id is not None and user.user_id == except_user_id:
                continue
            if user.login_name.strip().casefold() == normalized:
                raise ValueError(f"login_name already exists: {login_name}")

    def _has_other_active_platform_admin(self, user_id: str) -> bool:
        return any(
            user.user_id != user_id and user.is_active and user.is_platform_admin
            for user in self.registry.list_users()
        )

    def _ensure_not_last_active_platform_admin(self, user: User) -> None:
        if user.is_active and user.is_platform_admin and not self._has_other_active_platform_admin(user.user_id):
            raise PilotAdminError("Cannot remove the last active platform admin.")

    def _validate_password_before_write(self, password: str | None) -> None:
        if password is not None and len(password) < MIN_PASSWORD_LENGTH:
            raise ValueError(f"password must be at least {MIN_PASSWORD_LENGTH} characters.")

    def bootstrap_platform_admin(self, *, user: User, password: str) -> User:
        """Create the first platform admin when no platform admin exists."""

        if any(existing.is_platform_admin for existing in self.registry.list_users()):
            raise PilotAdminError("A platform admin already exists.")
        self._ensure_unique_login_name(user.login_name)
        self._validate_password_before_write(password)
        admin = replace(user, status=UserStatus.ACTIVE, is_platform_admin=True)
        saved = self.registry.save_user(admin)
        self.auth.set_password(user_id=saved.user_id, password=password)
        self._audit(
            actor_user_id="system",
            action=AuditAction.CREATE_USER,
            target_user_id=saved.user_id,
            metadata={"bootstrap": True, "is_platform_admin": True},
        )
        return saved

    def create_user(
        self,
        *,
        actor_user_id: str,
        user: User,
        initial_password: str | None = None,
    ) -> User:
        """Create a user after checking platform-admin permission."""

        actor = self._platform_admin(actor_user_id)
        self._ensure_unique_login_name(user.login_name)
        self._validate_password_before_write(initial_password)
        saved = self.registry.save_user(user)
        if initial_password is not None:
            self.auth.set_password(user_id=saved.user_id, password=initial_password)
        self._audit(
            actor_user_id=actor.user_id,
            action=AuditAction.CREATE_USER,
            target_user_id=saved.user_id,
            metadata={
                "login_name": saved.login_name,
                "is_platform_admin": saved.is_platform_admin,
                "initial_password_set": initial_password is not None,
            },
        )
        return saved

    def set_user_password(self, *, actor_user_id: str, user_id: str, password: str) -> None:
        """Reset a user's local password after checking platform-admin permission."""

        actor = self._platform_admin(actor_user_id)
        self.auth.set_password(user_id=user_id, password=password)
        self._audit(
            actor_user_id=actor.user_id,
            action=AuditAction.UPDATE_USER,
            target_user_id=user_id,
            metadata={"password_reset": True},
        )

    def set_platform_admin(self, *, actor_user_id: str, user_id: str, is_platform_admin: bool) -> User:
        """Grant or revoke platform-admin status."""

        actor = self._platform_admin(actor_user_id)
        target = self.registry.load_user(user_id)
        if not is_platform_admin:
            self._ensure_not_last_active_platform_admin(target)
        updated = replace(target, is_platform_admin=bool(is_platform_admin))
        saved = self.registry.save_user(updated, overwrite=True)
        self._audit(
            actor_user_id=actor.user_id,
            action=AuditAction.UPDATE_USER,
            target_user_id=user_id,
            metadata={"is_platform_admin": saved.is_platform_admin},
        )
        return saved

    def disable_user(self, *, actor_user_id: str, user_id: str) -> User:
        """Disable a user and revoke active local sessions."""

        actor = self._platform_admin(actor_user_id)
        target = self.registry.load_user(user_id)
        self._ensure_not_last_active_platform_admin(target)
        disabled = self.registry.disable_user(user_id)
        revoked_count = 0
        for session in self.auth.list_user_sessions(user_id, active_only=True):
            self.auth.revoke_session(session.session_id)
            revoked_count += 1
        self._audit(
            actor_user_id=actor.user_id,
            action=AuditAction.UPDATE_USER,
            target_user_id=user_id,
            metadata={"status": disabled.status.value, "revoked_sessions": revoked_count},
        )
        return disabled

    def enable_user(self, *, actor_user_id: str, user_id: str) -> User:
        """Reactivate a disabled user after checking platform-admin permission."""

        actor = self._platform_admin(actor_user_id)
        enabled = self.registry.enable_user(user_id)
        self._audit(
            actor_user_id=actor.user_id,
            action=AuditAction.UPDATE_USER,
            target_user_id=user_id,
            metadata={"status": enabled.status.value},
        )
        return enabled

    def list_user_sessions(
        self,
        *,
        actor_user_id: str,
        user_id: str,
        active_only: bool = False,
    ) -> list[PilotSessionRecord]:
        """List one user's sessions after checking platform-admin permission."""

        self._platform_admin(actor_user_id)
        self.registry.load_user(user_id)
        return self.auth.list_user_sessions(user_id, active_only=active_only)

    def revoke_user_session(
        self,
        *,
        actor_user_id: str,
        user_id: str,
        session_id: str,
    ) -> PilotSessionRecord:
        """Revoke one user's local session after checking platform-admin permission."""

        actor = self._platform_admin(actor_user_id)
        self.registry.load_user(user_id)
        record = self.auth.load_session_record(session_id)
        if record.user_id != user_id:
            raise PilotAdminError(f"Session does not belong to user: {session_id}")
        revoked = self.auth.revoke_session(session_id)
        self._audit(
            actor_user_id=actor.user_id,
            action=AuditAction.UPDATE_USER,
            target_user_id=user_id,
            metadata={
                "session_revoked": True,
                "session_id": revoked.session_id,
                "already_revoked": record.is_revoked,
                "revoked_at": revoked.revoked_at.isoformat() if revoked.revoked_at is not None else None,
            },
        )
        return revoked

    def list_users(self, *, actor_user_id: str, active_only: bool = False) -> list[User]:
        """List users after checking platform-admin permission."""

        self._platform_admin(actor_user_id)
        users = self.registry.list_users()
        if active_only:
            return [user for user in users if user.is_active]
        return users

    def list_projects(
        self,
        *,
        actor_user_id: str,
        active_only: bool = False,
    ) -> list[Project]:
        """List projects after checking platform-admin permission."""

        self._platform_admin(actor_user_id)
        projects = self.registry.list_projects()
        if active_only:
            return [project for project in projects if project.status == ProjectStatus.ACTIVE]
        return projects

    def list_audit_events(
        self,
        *,
        actor_user_id: str,
        project_id: str | None = None,
        actions: list[AuditAction | str] | None = None,
        limit: int = 100,
        oldest_first: bool = False,
    ) -> list[AuditLog]:
        """List audit events for platform operations."""

        self._platform_admin(actor_user_id)
        if limit < 1:
            raise ValueError("limit must be positive.")
        accepted_actions = {AuditAction(action) for action in actions} if actions else None
        events = self.result_store.read_audit_log(project_id)
        if accepted_actions is not None:
            events = [event for event in events if event.action in accepted_actions]
        events = sorted(
            events,
            key=lambda event: (event.created_at, event.event_id),
            reverse=not oldest_first,
        )
        return events[:limit]

    def create_project(
        self,
        *,
        actor_user_id: str,
        project: Project,
        owner_user_id: str | None = None,
    ) -> Project:
        """Create a project after checking platform-admin permission."""

        actor = self._platform_admin(actor_user_id)
        owner_id = owner_user_id or project.created_by_user_id or actor.user_id
        owner = self.registry.load_user(owner_id)
        if not owner.is_active:
            raise PilotAdminError(f"Project owner is disabled: {owner_id}")
        project_to_save = replace(project, created_by_user_id=owner.user_id)
        saved = self.registry.save_project(project_to_save)
        self.registry.grant_project_role(
            project_id=saved.project_id,
            user_id=owner.user_id,
            role=ProjectRole.ADMIN,
        )
        self._audit(
            actor_user_id=actor.user_id,
            action=AuditAction.CREATE_PROJECT,
            project_id=saved.project_id,
            target_type="project",
            target_id=saved.project_id,
            metadata={
                "name": saved.name,
                "owner_user_id": owner.user_id,
                "platform_admin_override": True,
            },
        )
        return saved

    def archive_project(self, *, actor_user_id: str, project_id: str) -> Project:
        """Archive a project after checking platform-admin permission."""

        actor = self._platform_admin(actor_user_id)
        archived = self.registry.archive_project(project_id)
        self._audit(
            actor_user_id=actor.user_id,
            action=AuditAction.UPDATE_PROJECT,
            project_id=archived.project_id,
            target_type="project",
            target_id=archived.project_id,
            metadata={"status": archived.status.value, "platform_admin_override": True},
        )
        return archived

    def list_project_memberships(
        self,
        *,
        actor_user_id: str,
        project_id: str,
        active_only: bool = False,
    ) -> list[ProjectMembership]:
        """List project memberships after checking platform-admin permission."""

        self._platform_admin(actor_user_id)
        return self.registry.list_project_memberships(project_id, active_only=active_only)

    def grant_project_role(
        self,
        *,
        actor_user_id: str,
        project_id: str,
        user_id: str,
        role: ProjectRole | str,
        can_export_artifacts: bool | None = None,
    ) -> ProjectMembership:
        """Grant or update a project role after checking platform-admin permission."""

        actor = self._platform_admin(actor_user_id)
        project = self.registry.load_project(project_id)
        if project.status != ProjectStatus.ACTIVE:
            raise PilotAdminError("Cannot update memberships for an archived project.")
        target = self.registry.load_user(user_id)
        if not target.is_active:
            raise PilotAdminError(f"User is disabled: {user_id}")
        membership = self.registry.grant_project_role(
            project_id=project.project_id,
            user_id=target.user_id,
            role=role,
            can_export_artifacts=can_export_artifacts,
        )
        self._audit(
            actor_user_id=actor.user_id,
            action=AuditAction.UPDATE_MEMBERSHIP,
            project_id=project.project_id,
            target_type="project_membership",
            target_id=membership.membership_id,
            metadata={
                "user_id": target.user_id,
                "role": membership.role.value,
                "status": membership.status.value,
                "can_export_artifacts": membership.can_export_artifacts,
                "platform_admin_override": True,
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
        """Disable a project membership after checking platform-admin permission."""

        actor = self._platform_admin(actor_user_id)
        disabled = self.registry.disable_membership(project_id, user_id)
        self._audit(
            actor_user_id=actor.user_id,
            action=AuditAction.UPDATE_MEMBERSHIP,
            project_id=project_id,
            target_type="project_membership",
            target_id=disabled.membership_id,
            metadata={
                "user_id": user_id,
                "role": disabled.role.value,
                "status": disabled.status.value,
                "can_export_artifacts": disabled.can_export_artifacts,
                "platform_admin_override": True,
            },
        )
        return disabled
