"""Local file-backed registry for internal pilot users and projects.

This registry is a small account/project metadata adapter. It deliberately
does not store passwords or implement authentication. Future login providers
can map their subject IDs to these `User` records.
"""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path

from green_direct.models.pilot_backend import (
    MembershipStatus,
    Project,
    ProjectMembership,
    ProjectRole,
    ProjectStatus,
    User,
    UserStatus,
)
from green_direct.services.local_store_utils import read_json, validate_path_segment, write_json


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _user_from_json(data: dict) -> User:
    return User(
        user_id=data["user_id"],
        login_name=data["login_name"],
        display_name=data["display_name"],
        status=data.get("status", UserStatus.ACTIVE.value),
        is_platform_admin=bool(data.get("is_platform_admin", False)),
        created_at=_parse_datetime(data["created_at"]),
    )


def _project_from_json(data: dict) -> Project:
    return Project(
        project_id=data["project_id"],
        name=data["name"],
        status=data.get("status", ProjectStatus.ACTIVE.value),
        created_by_user_id=data.get("created_by_user_id"),
        created_at=_parse_datetime(data["created_at"]),
    )


def _membership_from_json(data: dict) -> ProjectMembership:
    return ProjectMembership(
        membership_id=data["membership_id"],
        project_id=data["project_id"],
        user_id=data["user_id"],
        role=data["role"],
        status=data.get("status", MembershipStatus.ACTIVE.value),
        can_export_artifacts=bool(data.get("can_export_artifacts", True)),
        created_at=_parse_datetime(data["created_at"]),
    )


class LocalPilotRegistry:
    """Local JSON registry for pilot users, projects, and memberships."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

    def _users_dir(self) -> Path:
        return self.root / "registry" / "users"

    def _user_path(self, user_id: str) -> Path:
        return self._users_dir() / f"{validate_path_segment(user_id, 'user_id')}.json"

    def _projects_dir(self) -> Path:
        return self.root / "registry" / "projects"

    def _project_dir(self, project_id: str) -> Path:
        return self._projects_dir() / validate_path_segment(project_id, "project_id")

    def _project_path(self, project_id: str) -> Path:
        return self._project_dir(project_id) / "project.json"

    def _memberships_dir(self, project_id: str) -> Path:
        return self._project_dir(project_id) / "memberships"

    def _membership_path(self, project_id: str, membership_id: str) -> Path:
        return self._memberships_dir(project_id) / f"{validate_path_segment(membership_id, 'membership_id')}.json"

    def _default_membership_id(self, project_id: str, user_id: str) -> str:
        safe_project_id = validate_path_segment(project_id, "project_id")
        safe_user_id = validate_path_segment(user_id, "user_id")
        return f"{safe_project_id}__{safe_user_id}"

    def save_user(self, user: User, *, overwrite: bool = False) -> User:
        path = self._user_path(user.user_id)
        if path.exists() and not overwrite:
            raise FileExistsError(f"User already exists: {user.user_id}")
        write_json(path, asdict(user))
        return user

    def load_user(self, user_id: str) -> User:
        return _user_from_json(read_json(self._user_path(user_id)))

    def list_users(self) -> list[User]:
        directory = self._users_dir()
        if not directory.exists():
            return []
        return [_user_from_json(read_json(path)) for path in sorted(directory.glob("*.json"))]

    def disable_user(self, user_id: str) -> User:
        user = self.load_user(user_id)
        disabled = replace(user, status=UserStatus.DISABLED)
        return self.save_user(disabled, overwrite=True)

    def save_project(self, project: Project, *, overwrite: bool = False) -> Project:
        path = self._project_path(project.project_id)
        if path.exists() and not overwrite:
            raise FileExistsError(f"Project already exists: {project.project_id}")
        write_json(path, asdict(project))
        return project

    def load_project(self, project_id: str) -> Project:
        return _project_from_json(read_json(self._project_path(project_id)))

    def list_projects(self) -> list[Project]:
        directory = self._projects_dir()
        if not directory.exists():
            return []
        return [
            _project_from_json(read_json(path))
            for path in sorted(directory.glob("*/project.json"))
        ]

    def archive_project(self, project_id: str) -> Project:
        project = self.load_project(project_id)
        archived = replace(project, status=ProjectStatus.ARCHIVED)
        return self.save_project(archived, overwrite=True)

    def save_membership(
        self,
        membership: ProjectMembership,
        *,
        overwrite: bool = False,
    ) -> ProjectMembership:
        self.load_project(membership.project_id)
        self.load_user(membership.user_id)
        path = self._membership_path(membership.project_id, membership.membership_id)
        if path.exists() and not overwrite:
            raise FileExistsError(f"Project membership already exists: {membership.membership_id}")
        write_json(path, asdict(membership))
        return membership

    def load_membership(self, project_id: str, membership_id: str) -> ProjectMembership:
        return _membership_from_json(read_json(self._membership_path(project_id, membership_id)))

    def list_project_memberships(self, project_id: str, *, active_only: bool = False) -> list[ProjectMembership]:
        self.load_project(project_id)
        directory = self._memberships_dir(project_id)
        if not directory.exists():
            return []
        memberships = [
            _membership_from_json(read_json(path))
            for path in sorted(directory.glob("*.json"))
        ]
        if active_only:
            return [membership for membership in memberships if membership.is_active]
        return memberships

    def get_project_membership(self, project_id: str, user_id: str) -> ProjectMembership | None:
        for membership in self.list_project_memberships(project_id):
            if membership.user_id == user_id:
                return membership
        return None

    def grant_project_role(
        self,
        *,
        project_id: str,
        user_id: str,
        role: ProjectRole | str,
        can_export_artifacts: bool | None = None,
    ) -> ProjectMembership:
        self.load_project(project_id)
        self.load_user(user_id)
        existing = self.get_project_membership(project_id, user_id)
        next_can_export = True if existing is None else existing.can_export_artifacts
        if can_export_artifacts is not None:
            next_can_export = bool(can_export_artifacts)
        if existing is None:
            membership = ProjectMembership(
                membership_id=self._default_membership_id(project_id, user_id),
                project_id=project_id,
                user_id=user_id,
                role=role,
                can_export_artifacts=next_can_export,
            )
        else:
            membership = replace(
                existing,
                role=ProjectRole(role),
                status=MembershipStatus.ACTIVE,
                can_export_artifacts=next_can_export,
            )
        return self.save_membership(membership, overwrite=existing is not None)

    def disable_membership(self, project_id: str, user_id: str) -> ProjectMembership:
        membership = self.get_project_membership(project_id, user_id)
        if membership is None:
            raise FileNotFoundError(f"No project membership for user: {user_id}")
        disabled = replace(membership, status=MembershipStatus.DISABLED)
        return self.save_membership(disabled, overwrite=True)
