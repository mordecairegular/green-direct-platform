from datetime import datetime, timedelta, timezone
import json

import pytest

from green_direct.models.pilot_backend import AuditAction, User
from green_direct.services import (
    LocalPilotAuth,
    LocalPilotRegistry,
    LocalResultStore,
    PilotAuthError,
)


def _utc(year: int, month: int = 1, day: int = 1, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


def _auth(tmp_path, *, session_ttl_hours: int = 12):
    registry = LocalPilotRegistry(tmp_path)
    result_store = LocalResultStore(tmp_path)
    registry.save_user(User("user_1", "user@example.local", "User One"))
    return LocalPilotAuth(
        tmp_path,
        registry=registry,
        result_store=result_store,
        session_ttl_hours=session_ttl_hours,
    )


def test_set_password_hashes_password_and_login_creates_audited_session(tmp_path):
    auth = _auth(tmp_path)
    now = _utc(2026, 6, 15, 8)

    auth.set_password(user_id="user_1", password="correct-horse", now=now)
    session = auth.login(login_name="USER@example.local", password="correct-horse", now=now)

    credential = json.loads((tmp_path / "auth" / "credentials" / "user_1.json").read_text(encoding="utf-8"))
    session_record = auth.load_session_record(session.session_id)
    events = auth.result_store.read_audit_log()

    assert credential["password_hash"] != "correct-horse"
    assert credential["salt"] not in {"", "correct-horse"}
    assert session.user_id == "user_1"
    assert session.token
    assert session.expires_at == now + timedelta(hours=12)
    assert session_record.token_hash != session.token
    assert [event.action for event in events] == [AuditAction.LOGIN]
    assert events[0].metadata["success"] is True


def test_authenticate_rejects_bad_password_and_audits_failure(tmp_path):
    auth = _auth(tmp_path)
    auth.set_password(user_id="user_1", password="correct-horse")

    with pytest.raises(PilotAuthError, match="Invalid login credentials"):
        auth.login(login_name="user@example.local", password="wrong-password")

    events = auth.result_store.read_audit_log()
    assert events[-1].actor_user_id == "user_1"
    assert events[-1].action == AuditAction.LOGIN
    assert events[-1].metadata["success"] is False
    assert events[-1].metadata["reason"] == "bad_password"


def test_disabled_user_cannot_set_password_login_or_use_existing_session(tmp_path):
    auth = _auth(tmp_path)
    auth.set_password(user_id="user_1", password="correct-horse")
    session = auth.login(login_name="user@example.local", password="correct-horse", now=_utc(2026))
    auth.registry.disable_user("user_1")

    with pytest.raises(PilotAuthError, match="User is disabled"):
        auth.set_password(user_id="user_1", password="new-password")
    with pytest.raises(PilotAuthError, match="User is disabled"):
        auth.login(login_name="user@example.local", password="correct-horse")
    with pytest.raises(PilotAuthError, match="User is disabled"):
        auth.require_session(session_id=session.session_id, token=session.token, now=_utc(2026, 1, 1, 1))


def test_session_validation_rejects_wrong_token_expired_and_revoked_sessions(tmp_path):
    auth = _auth(tmp_path, session_ttl_hours=1)
    auth.set_password(user_id="user_1", password="correct-horse")
    session = auth.login(login_name="user@example.local", password="correct-horse", now=_utc(2026))

    assert auth.require_session(
        session_id=session.session_id,
        token=session.token,
        now=_utc(2026, 1, 1, 0),
    ).user_id == "user_1"
    with pytest.raises(PilotAuthError, match="Invalid session token"):
        auth.require_session(session_id=session.session_id, token="wrong-token", now=_utc(2026, 1, 1, 0))
    with pytest.raises(PilotAuthError, match="Session has expired"):
        auth.require_session(session_id=session.session_id, token=session.token, now=_utc(2026, 1, 1, 2))

    second = auth.login(login_name="user@example.local", password="correct-horse", now=_utc(2026, 1, 1, 3))
    auth.revoke_session(second.session_id, now=_utc(2026, 1, 1, 4))
    with pytest.raises(PilotAuthError, match="Session has been revoked"):
        auth.require_session(session_id=second.session_id, token=second.token, now=_utc(2026, 1, 1, 4))


def test_list_user_sessions_filters_active_records(tmp_path):
    auth = _auth(tmp_path, session_ttl_hours=1)
    auth.set_password(user_id="user_1", password="correct-horse")
    expired = auth.login(login_name="user@example.local", password="correct-horse", now=_utc(2026, 1, 1, 0))
    active = auth.login(login_name="user@example.local", password="correct-horse", now=_utc(2026, 1, 1, 2))
    auth.revoke_session(active.session_id, now=_utc(2026, 1, 1, 2))
    fresh = auth.login(login_name="user@example.local", password="correct-horse", now=_utc(2026, 1, 1, 3))

    all_records = auth.list_user_sessions("user_1", now=_utc(2026, 1, 1, 3))
    active_records = auth.list_user_sessions("user_1", active_only=True, now=_utc(2026, 1, 1, 3))

    assert {record.session_id for record in all_records} == {
        expired.session_id,
        active.session_id,
        fresh.session_id,
    }
    assert [record.session_id for record in active_records] == [fresh.session_id]


def test_short_password_is_rejected(tmp_path):
    auth = _auth(tmp_path)

    with pytest.raises(ValueError, match="at least 8 characters"):
        auth.set_password(user_id="user_1", password="short")
