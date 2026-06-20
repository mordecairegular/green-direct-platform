"""Shared helpers for local file-backed pilot stores."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from enum import Enum
import json
import os
from pathlib import Path
import re
import time
from typing import Any, Mapping
from uuid import uuid4


_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def validate_path_segment(value: str, field_name: str) -> str:
    text = str(value)
    if not _SAFE_SEGMENT.fullmatch(text):
        raise ValueError(f"{field_name} contains unsafe path characters.")
    return text


def json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): json_value(nested) for key, nested in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    return value


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(json_value(payload), ensure_ascii=False, indent=2, sort_keys=True)
    tmp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with tmp_path.open("w", encoding="utf-8") as handle:
            handle.write(text)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        tmp_path.replace(path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


@contextmanager
def local_store_lock(
    root: str | Path,
    *,
    name: str,
    timeout_seconds: float = 10.0,
    stale_after_seconds: float = 300.0,
    poll_interval_seconds: float = 0.05,
):
    """Acquire a cooperative cross-process lock for a local file store.

    This intentionally stays small and dependency-free for the internal pilot
    adapter. It protects read-modify-write windows between local processes, but
    it is not a replacement for database transactions or a real queue backend.
    """

    if timeout_seconds < 0:
        raise ValueError("timeout_seconds must not be negative.")
    if poll_interval_seconds <= 0:
        raise ValueError("poll_interval_seconds must be positive.")

    root_path = Path(root).resolve()
    lock_name = validate_path_segment(name, "lock_name")
    locks_dir = root_path / ".locks"
    lock_dir = locks_dir / f"{lock_name}.lock"
    owner_path = lock_dir / "owner.json"
    locks_dir.mkdir(parents=True, exist_ok=True)

    deadline = time.monotonic() + timeout_seconds
    acquired = False
    while True:
        try:
            lock_dir.mkdir()
            owner = {
                "pid": os.getpid(),
                "lock_name": lock_name,
                "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            owner_path.write_text(json.dumps(owner, ensure_ascii=False, sort_keys=True), encoding="utf-8")
            acquired = True
            break
        except FileExistsError:
            if stale_after_seconds > 0:
                try:
                    age_seconds = time.time() - lock_dir.stat().st_mtime
                except FileNotFoundError:
                    continue
                if age_seconds > stale_after_seconds:
                    try:
                        owner_path.unlink(missing_ok=True)
                        lock_dir.rmdir()
                    except OSError:
                        pass
                    continue
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Timed out waiting for local store lock: {lock_name}")
            time.sleep(min(poll_interval_seconds, max(0.0, deadline - time.monotonic())))

    try:
        yield
    finally:
        if acquired:
            try:
                owner_path.unlink(missing_ok=True)
                lock_dir.rmdir()
            except OSError:
                pass
