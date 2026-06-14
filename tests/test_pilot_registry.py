from datetime import datetime, timezone

import pytest

from green_direct.models.pilot_backend import (
    MembershipStatus,
    Project,
    ProjectMembership,
    ProjectRole,
    ProjectStatus,
    User,
    UserStatus,
)
from green_direct.services import LocalPilotRegistry


def _dt(hour: int) -> datetime:
    return datetime(2026, 6, 15, hour, tzinfo=timezone.utc)


def test_registry_saves_lists_and_disables_users(tmp_path):
    registry = LocalPilotRegistry(tmp_path)
    analyst = User("user_analyst", "analyst@example.local", "Analyst", created_at=_dt(1))
    viewer = User("user_viewer", "viewer@example.local", "Viewer", created_at=_dt(2))

    registry.save_user(viewer)
    registry.save_user(analyst)

    assert [user.user_id for user in registry.list_users()] == ["user_analyst", "user_viewer"]
    assert registry.load_user("user_analyst") == analyst

    disabled = registry.disable_user("user_analyst")
    assert disabled.status == UserStatus.DISABLED
    assert not registry.load_user("user_analyst").is_active

    with pytest.raises(FileExistsError):
        registry.save_user(viewer)


def test_registry_saves_lists_and_archives_projects(tmp_path):
    registry = LocalPilotRegistry(tmp_path)
    registry.save_user(User("admin", "admin@example.local", "Admin"))
    project = Project("project_1", "Internal pilot project", created_by_user_id="admin", created_at=_dt(1))

    registry.save_project(project)

    assert registry.load_project("project_1") == project
    assert registry.list_projects() == [project]

    archived = registry.archive_project("project_1")
    assert archived.status == ProjectStatus.ARCHIVED
    assert registry.load_project("project_1").status == ProjectStatus.ARCHIVED

    with pytest.raises(FileExistsError):
        registry.save_project(project)


def test_registry_grants_updates_and_disables_project_membership(tmp_path):
    registry = LocalPilotRegistry(tmp_path)
    registry.save_user(User("admin", "admin@example.local", "Admin"))
    registry.save_user(User("analyst", "analyst@example.local", "Analyst"))
    registry.save_project(Project("project_1", "Internal pilot project", created_by_user_id="admin"))

    membership = registry.grant_project_role(
        project_id="project_1",
        user_id="analyst",
        role=ProjectRole.ANALYST,
    )

    assert membership.membership_id == "project_1__analyst"
    assert membership.can_submit_jobs()
    assert registry.get_project_membership("project_1", "analyst") == membership

    updated = registry.grant_project_role(project_id="project_1", user_id="analyst", role="viewer")
    assert updated.membership_id == membership.membership_id
    assert updated.role == ProjectRole.VIEWER
    assert not updated.can_submit_jobs()

    disabled = registry.disable_membership("project_1", "analyst")
    assert disabled.status == MembershipStatus.DISABLED
    assert registry.list_project_memberships("project_1", active_only=True) == []


def test_registry_save_membership_requires_existing_user_and_project(tmp_path):
    registry = LocalPilotRegistry(tmp_path)
    membership = ProjectMembership("membership_1", "missing_project", "missing_user", ProjectRole.ANALYST)

    with pytest.raises(FileNotFoundError):
        registry.save_membership(membership)

    registry.save_project(Project("project_1", "Internal pilot project"))
    with pytest.raises(FileNotFoundError):
        registry.save_membership(
            ProjectMembership("membership_1", "project_1", "missing_user", ProjectRole.ANALYST)
        )


def test_registry_rejects_unsafe_ids(tmp_path):
    registry = LocalPilotRegistry(tmp_path)

    with pytest.raises(ValueError, match="user_id contains unsafe path characters"):
        registry.save_user(User("../user", "user@example.local", "User"))

    with pytest.raises(ValueError, match="project_id contains unsafe path characters"):
        registry.save_project(Project("project/1", "Unsafe"))


def test_registry_missing_membership_disable_is_explicit(tmp_path):
    registry = LocalPilotRegistry(tmp_path)
    registry.save_user(User("admin", "admin@example.local", "Admin"))
    registry.save_project(Project("project_1", "Internal pilot project", created_by_user_id="admin"))

    with pytest.raises(FileNotFoundError, match="No project membership"):
        registry.disable_membership("project_1", "admin")
