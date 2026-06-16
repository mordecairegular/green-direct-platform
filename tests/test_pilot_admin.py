from datetime import datetime, timezone

import pytest

from green_direct.models.pilot_backend import AuditAction, AuditLog, Project, ProjectRole, User, UserStatus
from green_direct.services import (
    LocalPilotAdminService,
    LocalPilotAuth,
    LocalPilotRegistry,
    LocalResultStore,
    PilotAdminError,
    PilotAuthError,
)


def _admin_service(tmp_path):
    registry = LocalPilotRegistry(tmp_path)
    result_store = LocalResultStore(tmp_path)
    auth = LocalPilotAuth(tmp_path, registry=registry, result_store=result_store)
    return LocalPilotAdminService(
        registry=registry,
        auth=auth,
        result_store=result_store,
    )


def test_bootstrap_platform_admin_creates_first_admin_with_password_and_audit(tmp_path):
    service = _admin_service(tmp_path)

    admin = service.bootstrap_platform_admin(
        user=User("admin", "admin@example.local", "Admin"),
        password="admin-password",
    )

    assert admin.is_platform_admin is True
    assert service.registry.load_user("admin").is_platform_admin is True
    assert service.auth.login(login_name="admin@example.local", password="admin-password").user_id == "admin"
    events = service.result_store.read_audit_log()
    assert [event.action for event in events] == [AuditAction.CREATE_USER, AuditAction.LOGIN]
    assert events[0].actor_user_id == "system"
    assert events[0].metadata["bootstrap"] is True


def test_bootstrap_is_allowed_only_once(tmp_path):
    service = _admin_service(tmp_path)
    service.bootstrap_platform_admin(user=User("admin", "admin@example.local", "Admin"), password="admin-password")

    with pytest.raises(PilotAdminError, match="already exists"):
        service.bootstrap_platform_admin(
            user=User("admin_2", "admin2@example.local", "Admin 2"),
            password="admin-password",
        )


def test_platform_admin_can_create_user_and_reset_password(tmp_path):
    service = _admin_service(tmp_path)
    service.bootstrap_platform_admin(user=User("admin", "admin@example.local", "Admin"), password="admin-password")

    user = service.create_user(
        actor_user_id="admin",
        user=User("analyst", "analyst@example.local", "Analyst"),
        initial_password="analyst-password",
    )
    service.set_user_password(actor_user_id="admin", user_id="analyst", password="new-password")

    assert user.is_platform_admin is False
    assert service.auth.login(login_name="analyst@example.local", password="new-password").user_id == "analyst"
    with pytest.raises(PilotAuthError, match="Invalid login credentials"):
        service.auth.login(login_name="analyst@example.local", password="analyst-password")
    actions = [event.action for event in service.result_store.read_audit_log()]
    assert actions.count(AuditAction.CREATE_USER) == 2
    assert AuditAction.UPDATE_USER in actions


def test_non_platform_admin_cannot_manage_accounts(tmp_path):
    service = _admin_service(tmp_path)
    service.bootstrap_platform_admin(user=User("admin", "admin@example.local", "Admin"), password="admin-password")
    service.create_user(
        actor_user_id="admin",
        user=User("analyst", "analyst@example.local", "Analyst"),
        initial_password="analyst-password",
    )

    with pytest.raises(PilotAdminError, match="cannot manage platform accounts"):
        service.create_user(
            actor_user_id="analyst",
            user=User("viewer", "viewer@example.local", "Viewer"),
            initial_password="viewer-password",
        )


def test_platform_admin_can_grant_platform_admin_flag(tmp_path):
    service = _admin_service(tmp_path)
    service.bootstrap_platform_admin(user=User("admin", "admin@example.local", "Admin"), password="admin-password")
    service.create_user(actor_user_id="admin", user=User("ops", "ops@example.local", "Ops"))

    promoted = service.set_platform_admin(actor_user_id="admin", user_id="ops", is_platform_admin=True)

    assert promoted.is_platform_admin is True
    assert service.registry.load_user("ops").is_platform_admin is True
    assert any(
        event.action == AuditAction.UPDATE_USER and event.metadata.get("is_platform_admin") is True
        for event in service.result_store.read_audit_log()
    )


def test_cannot_remove_last_active_platform_admin(tmp_path):
    service = _admin_service(tmp_path)
    service.bootstrap_platform_admin(user=User("admin", "admin@example.local", "Admin"), password="admin-password")

    with pytest.raises(PilotAdminError, match="last active platform admin"):
        service.set_platform_admin(actor_user_id="admin", user_id="admin", is_platform_admin=False)
    with pytest.raises(PilotAdminError, match="last active platform admin"):
        service.disable_user(actor_user_id="admin", user_id="admin")

    service.create_user(
        actor_user_id="admin",
        user=User("ops", "ops@example.local", "Ops", is_platform_admin=True),
        initial_password="ops-password",
    )
    disabled = service.disable_user(actor_user_id="ops", user_id="admin")
    assert disabled.status == UserStatus.DISABLED


def test_disable_user_revokes_active_sessions_and_audits(tmp_path):
    service = _admin_service(tmp_path)
    service.bootstrap_platform_admin(user=User("admin", "admin@example.local", "Admin"), password="admin-password")
    service.create_user(
        actor_user_id="admin",
        user=User("analyst", "analyst@example.local", "Analyst"),
        initial_password="analyst-password",
    )
    session = service.auth.login(login_name="analyst@example.local", password="analyst-password")

    disabled = service.disable_user(actor_user_id="admin", user_id="analyst")

    assert disabled.status == UserStatus.DISABLED
    with pytest.raises(PilotAuthError, match="Session has been revoked"):
        service.auth.require_session(session_id=session.session_id, token=session.token)
    assert any(
        event.action == AuditAction.UPDATE_USER and event.metadata.get("revoked_sessions") == 1
        for event in service.result_store.read_audit_log()
    )


def test_platform_admin_can_reactivate_disabled_user_and_audit(tmp_path):
    service = _admin_service(tmp_path)
    service.bootstrap_platform_admin(user=User("admin", "admin@example.local", "Admin"), password="admin-password")
    service.create_user(
        actor_user_id="admin",
        user=User("analyst", "analyst@example.local", "Analyst"),
        initial_password="analyst-password",
    )
    service.disable_user(actor_user_id="admin", user_id="analyst")

    enabled = service.enable_user(actor_user_id="admin", user_id="analyst")

    assert enabled.status == UserStatus.ACTIVE
    assert service.auth.login(login_name="analyst@example.local", password="analyst-password").user_id == "analyst"
    assert any(
        event.action == AuditAction.UPDATE_USER
        and event.target_id == "analyst"
        and event.metadata.get("status") == UserStatus.ACTIVE.value
        for event in service.result_store.read_audit_log()
    )


def test_platform_admin_can_manage_project_memberships_without_project_admin_role(tmp_path):
    service = _admin_service(tmp_path)
    service.bootstrap_platform_admin(user=User("platform_admin", "admin@example.local", "Admin"), password="admin-password")
    service.create_user(actor_user_id="platform_admin", user=User("owner", "owner@example.local", "Owner"))
    service.create_user(actor_user_id="platform_admin", user=User("analyst", "analyst@example.local", "Analyst"))
    service.registry.save_project(Project("project_1", "Internal pilot project", created_by_user_id="owner"))

    membership = service.grant_project_role(
        actor_user_id="platform_admin",
        project_id="project_1",
        user_id="analyst",
        role=ProjectRole.ANALYST,
        can_export_artifacts=False,
    )
    disabled = service.disable_project_membership(
        actor_user_id="platform_admin",
        project_id="project_1",
        user_id="analyst",
    )

    assert membership.role == ProjectRole.ANALYST
    assert not membership.can_download_artifacts()
    assert not disabled.is_active
    assert [(project.project_id, project.name) for project in service.list_projects(actor_user_id="platform_admin")] == [
        ("project_1", "Internal pilot project")
    ]
    assert any(
        event.action == AuditAction.UPDATE_MEMBERSHIP
        and event.metadata.get("platform_admin_override") is True
        and event.metadata.get("can_export_artifacts") is False
        for event in service.result_store.read_audit_log("project_1")
    )


def test_platform_admin_can_create_and_archive_project(tmp_path):
    service = _admin_service(tmp_path)
    service.bootstrap_platform_admin(user=User("platform_admin", "admin@example.local", "Admin"), password="admin-password")
    service.create_user(actor_user_id="platform_admin", user=User("owner", "owner@example.local", "Owner"))

    project = service.create_project(
        actor_user_id="platform_admin",
        project=Project("project_1", "Internal pilot project"),
        owner_user_id="owner",
    )
    membership = service.registry.get_project_membership("project_1", "owner")
    archived = service.archive_project(actor_user_id="platform_admin", project_id="project_1")

    assert project.created_by_user_id == "owner"
    assert membership is not None
    assert membership.role == ProjectRole.ADMIN
    assert archived.status.value == "archived"

    events = service.result_store.read_audit_log("project_1")
    assert [event.action for event in events] == [AuditAction.CREATE_PROJECT, AuditAction.UPDATE_PROJECT]
    assert events[0].metadata["owner_user_id"] == "owner"
    assert events[1].metadata["status"] == "archived"

    with pytest.raises(PilotAdminError, match="archived project"):
        service.grant_project_role(
            actor_user_id="platform_admin",
            project_id="project_1",
            user_id="owner",
            role=ProjectRole.ADMIN,
        )


def test_platform_admin_can_list_audit_events_with_filters(tmp_path):
    service = _admin_service(tmp_path)
    service.bootstrap_platform_admin(user=User("admin", "admin@example.local", "Admin"), password="admin-password")
    service.create_user(actor_user_id="admin", user=User("analyst", "analyst@example.local", "Analyst"))
    service.result_store.append_audit_log(
        AuditLog(
            event_id="global_update_user",
            actor_user_id="admin",
            action=AuditAction.UPDATE_USER,
            metadata={"reason": "password"},
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
    )
    service.result_store.append_audit_log(
        AuditLog(
            event_id="project_create",
            actor_user_id="admin",
            action=AuditAction.CREATE_PROJECT,
            project_id="project_1",
            target_type="project",
            target_id="project_1",
            created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        )
    )
    service.result_store.append_audit_log(
        AuditLog(
            event_id="project_update",
            actor_user_id="admin",
            action=AuditAction.UPDATE_PROJECT,
            project_id="project_1",
            target_type="project",
            target_id="project_1",
            created_at=datetime(2026, 1, 3, tzinfo=timezone.utc),
        )
    )

    latest_project_events = service.list_audit_events(actor_user_id="admin", project_id="project_1", limit=1)
    oldest_project_events = service.list_audit_events(
        actor_user_id="admin",
        project_id="project_1",
        actions=[AuditAction.CREATE_PROJECT, "update_project"],
        limit=5,
        oldest_first=True,
    )
    update_events = service.list_audit_events(
        actor_user_id="admin",
        actions=[AuditAction.UPDATE_USER],
        limit=5,
    )

    assert [event.event_id for event in latest_project_events] == ["project_update"]
    assert [event.event_id for event in oldest_project_events] == ["project_create", "project_update"]
    assert [event.event_id for event in update_events] == ["global_update_user"]
    with pytest.raises(ValueError, match="limit must be positive"):
        service.list_audit_events(actor_user_id="admin", limit=0)
    with pytest.raises(PilotAdminError, match="cannot manage platform accounts"):
        service.list_audit_events(actor_user_id="analyst")


def test_create_user_rejects_duplicate_login_name(tmp_path):
    service = _admin_service(tmp_path)
    service.bootstrap_platform_admin(user=User("admin", "admin@example.local", "Admin"), password="admin-password")

    with pytest.raises(ValueError, match="login_name already exists"):
        service.create_user(
            actor_user_id="admin",
            user=User("admin_copy", "ADMIN@example.local", "Admin Copy"),
        )


def test_create_user_rejects_short_initial_password_before_saving_user(tmp_path):
    service = _admin_service(tmp_path)
    service.bootstrap_platform_admin(user=User("admin", "admin@example.local", "Admin"), password="admin-password")

    with pytest.raises(ValueError, match="at least 8 characters"):
        service.create_user(
            actor_user_id="admin",
            user=User("short_pw_user", "short@example.local", "Short Password"),
            initial_password="short",
        )

    with pytest.raises(FileNotFoundError):
        service.registry.load_user("short_pw_user")
