"""Local password and session service for the internal pilot.

This adapter is intentionally small: it gives the Streamlit login page and
future admin screens a testable authentication contract without changing the
`User` domain model or pretending to be enterprise IAM.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets
from pathlib import Path
from uuid import uuid4

from green_direct.models.pilot_backend import AuditAction, AuditLog, User
from green_direct.services.local_store_utils import read_json, validate_path_segment, write_json
from green_direct.services.pilot_registry import LocalPilotRegistry
from green_direct.services.result_store import LocalResultStore

PASSWORD_HASH_ALGORITHM = "pbkdf2_sha256"
PASSWORD_HASH_ITERATIONS = 310_000
MIN_PASSWORD_LENGTH = 8


class PilotAuthError(PermissionError):
    """Raised when local pilot authentication fails."""


@dataclass(frozen=True)
class PilotLoginSession:
    """Session data returned to the caller after a successful login."""

    session_id: str
    user_id: str
    token: str
    expires_at: datetime


@dataclass(frozen=True)
class PilotSessionRecord:
    """Persisted session metadata without the raw bearer token."""

    session_id: str
    user_id: str
    token_hash: str
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    def is_active(self, *, now: datetime | None = None) -> bool:
        reference = _utcnow() if now is None else _ensure_aware(now, "now")
        return not self.is_revoked and self.expires_at > reference


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_aware(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware.")
    return value


def _parse_datetime(value: str | None) -> datetime | None:
    return None if value is None else datetime.fromisoformat(value)


def _hash_password(password: str, *, salt_hex: str, iterations: int = PASSWORD_HASH_ITERATIONS) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt_hex),
        iterations,
    ).hex()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _session_from_json(data: dict) -> PilotSessionRecord:
    return PilotSessionRecord(
        session_id=data["session_id"],
        user_id=data["user_id"],
        token_hash=data["token_hash"],
        created_at=datetime.fromisoformat(data["created_at"]),
        expires_at=datetime.fromisoformat(data["expires_at"]),
        revoked_at=_parse_datetime(data.get("revoked_at")),
    )


class LocalPilotAuth:
    """Local credential and session adapter for controlled internal pilots."""

    def __init__(
        self,
        root: str | Path,
        *,
        registry: LocalPilotRegistry,
        result_store: LocalResultStore | None = None,
        session_ttl_hours: int = 12,
    ) -> None:
        if int(session_ttl_hours) <= 0:
            raise ValueError("session_ttl_hours must be positive.")
        self.root = Path(root).resolve()
        self.registry = registry
        self.result_store = result_store
        self.session_ttl = timedelta(hours=int(session_ttl_hours))

    def _credential_dir(self) -> Path:
        return self.root / "auth" / "credentials"

    def _credential_path(self, user_id: str) -> Path:
        return self._credential_dir() / f"{validate_path_segment(user_id, 'user_id')}.json"

    def _session_dir(self) -> Path:
        return self.root / "auth" / "sessions"

    def _session_path(self, session_id: str) -> Path:
        return self._session_dir() / f"{validate_path_segment(session_id, 'session_id')}.json"

    def _audit_login(self, *, actor_user_id: str, success: bool, login_name: str, reason: str | None = None) -> None:
        if self.result_store is None:
            return
        self.result_store.append_audit_log(
            AuditLog(
                event_id=f"audit_{uuid4().hex[:16]}",
                actor_user_id=actor_user_id,
                action=AuditAction.LOGIN,
                metadata={
                    "login_name": login_name,
                    "success": success,
                    **({"reason": reason} if reason else {}),
                },
            )
        )

    def _load_user_by_login_name(self, login_name: str) -> User | None:
        normalized = str(login_name).strip().casefold()
        if not normalized:
            return None
        for user in self.registry.list_users():
            if user.login_name.strip().casefold() == normalized:
                return user
        return None

    def set_password(self, *, user_id: str, password: str, now: datetime | None = None) -> None:
        """Create or replace one user's local password hash."""

        user = self.registry.load_user(user_id)
        if not user.is_active:
            raise PilotAuthError(f"User is disabled: {user_id}")
        if len(password) < MIN_PASSWORD_LENGTH:
            raise ValueError(f"password must be at least {MIN_PASSWORD_LENGTH} characters.")
        timestamp = _utcnow() if now is None else _ensure_aware(now, "now")
        salt_hex = secrets.token_hex(16)
        write_json(
            self._credential_path(user.user_id),
            {
                "user_id": user.user_id,
                "algorithm": PASSWORD_HASH_ALGORITHM,
                "iterations": PASSWORD_HASH_ITERATIONS,
                "salt": salt_hex,
                "password_hash": _hash_password(password, salt_hex=salt_hex),
                "updated_at": timestamp,
            },
        )

    def authenticate(self, *, login_name: str, password: str) -> User:
        """Verify credentials and return the active user."""

        user = self._load_user_by_login_name(login_name)
        if user is None:
            self._audit_login(actor_user_id="anonymous", success=False, login_name=login_name, reason="unknown_user")
            raise PilotAuthError("Invalid login credentials.")
        if not user.is_active:
            self._audit_login(actor_user_id=user.user_id, success=False, login_name=login_name, reason="disabled_user")
            raise PilotAuthError(f"User is disabled: {user.user_id}")
        path = self._credential_path(user.user_id)
        if not path.exists():
            self._audit_login(actor_user_id=user.user_id, success=False, login_name=login_name, reason="no_password")
            raise PilotAuthError("Invalid login credentials.")
        credential = read_json(path)
        if credential.get("algorithm") != PASSWORD_HASH_ALGORITHM:
            raise PilotAuthError("Unsupported password hash algorithm.")
        expected = str(credential["password_hash"])
        actual = _hash_password(
            password,
            salt_hex=str(credential["salt"]),
            iterations=int(credential.get("iterations", PASSWORD_HASH_ITERATIONS)),
        )
        if not hmac.compare_digest(expected, actual):
            self._audit_login(actor_user_id=user.user_id, success=False, login_name=login_name, reason="bad_password")
            raise PilotAuthError("Invalid login credentials.")
        return user

    def login(self, *, login_name: str, password: str, now: datetime | None = None) -> PilotLoginSession:
        """Authenticate and create one bearer-token session."""

        timestamp = _utcnow() if now is None else _ensure_aware(now, "now")
        user = self.authenticate(login_name=login_name, password=password)
        token = secrets.token_urlsafe(32)
        session = PilotLoginSession(
            session_id=f"sess_{uuid4().hex[:16]}",
            user_id=user.user_id,
            token=token,
            expires_at=timestamp + self.session_ttl,
        )
        record = PilotSessionRecord(
            session_id=session.session_id,
            user_id=session.user_id,
            token_hash=_hash_token(token),
            created_at=timestamp,
            expires_at=session.expires_at,
        )
        self._write_session(record)
        self._audit_login(actor_user_id=user.user_id, success=True, login_name=login_name)
        return session

    def _write_session(self, record: PilotSessionRecord) -> PilotSessionRecord:
        write_json(
            self._session_path(record.session_id),
            {
                "session_id": record.session_id,
                "user_id": record.user_id,
                "token_hash": record.token_hash,
                "created_at": record.created_at,
                "expires_at": record.expires_at,
                "revoked_at": record.revoked_at,
            },
        )
        return record

    def load_session_record(self, session_id: str) -> PilotSessionRecord:
        """Load persisted session metadata without validating the token."""

        return _session_from_json(read_json(self._session_path(session_id)))

    def require_session(self, *, session_id: str, token: str, now: datetime | None = None) -> User:
        """Validate a bearer-token session and return the active user."""

        reference = _utcnow() if now is None else _ensure_aware(now, "now")
        record = self.load_session_record(session_id)
        if record.is_revoked:
            raise PilotAuthError("Session has been revoked.")
        if record.expires_at <= reference:
            raise PilotAuthError("Session has expired.")
        if not hmac.compare_digest(record.token_hash, _hash_token(token)):
            raise PilotAuthError("Invalid session token.")
        user = self.registry.load_user(record.user_id)
        if not user.is_active:
            raise PilotAuthError(f"User is disabled: {user.user_id}")
        return user

    def revoke_session(self, session_id: str, *, now: datetime | None = None) -> PilotSessionRecord:
        """Revoke one local login session."""

        timestamp = _utcnow() if now is None else _ensure_aware(now, "now")
        record = self.load_session_record(session_id)
        if record.revoked_at is not None:
            return record
        revoked = PilotSessionRecord(
            session_id=record.session_id,
            user_id=record.user_id,
            token_hash=record.token_hash,
            created_at=record.created_at,
            expires_at=record.expires_at,
            revoked_at=timestamp,
        )
        return self._write_session(revoked)

    def list_user_sessions(
        self,
        user_id: str,
        *,
        active_only: bool = False,
        now: datetime | None = None,
    ) -> list[PilotSessionRecord]:
        """List persisted sessions for one user."""

        safe_user_id = validate_path_segment(user_id, "user_id")
        directory = self._session_dir()
        if not directory.exists():
            return []
        records = [
            _session_from_json(read_json(path))
            for path in sorted(directory.glob("*.json"))
        ]
        records = [record for record in records if record.user_id == safe_user_id]
        if active_only:
            reference = _utcnow() if now is None else _ensure_aware(now, "now")
            return [record for record in records if record.is_active(now=reference)]
        return records
