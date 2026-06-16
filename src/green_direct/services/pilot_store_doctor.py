"""Runtime health checks for the local pilot store."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from uuid import uuid4

from green_direct.services.local_store_utils import local_store_lock, read_json, write_json


@dataclass(frozen=True)
class PilotStoreDoctorCheck:
    """One runtime check for a local pilot store."""

    name: str
    status: str
    message: str


@dataclass(frozen=True)
class PilotStoreDoctorResult:
    """Aggregated pilot store doctor result."""

    store_dir: str
    status: str
    checks: tuple[PilotStoreDoctorCheck, ...]

    def to_dict(self) -> dict:
        return {
            "store_dir": self.store_dir,
            "status": self.status,
            "checks": [asdict(check) for check in self.checks],
        }


def _check_store_directory(root: Path) -> PilotStoreDoctorCheck:
    try:
        if root.exists() and not root.is_dir():
            return PilotStoreDoctorCheck("store:directory", "fail", "store path exists but is not a directory")
        root.mkdir(parents=True, exist_ok=True)
        return PilotStoreDoctorCheck("store:directory", "pass", f"store directory is available: {root}")
    except Exception as exc:  # noqa: BLE001 - doctor should report operational failures
        return PilotStoreDoctorCheck("store:directory", "fail", str(exc))


def _check_json_roundtrip(root: Path) -> PilotStoreDoctorCheck:
    probe_dir = root / ".doctor"
    probe_path = probe_dir / f"probe_{uuid4().hex}.json"
    try:
        write_json(probe_path, {"value": "ok"})
        data = read_json(probe_path)
        if data != {"value": "ok"}:
            return PilotStoreDoctorCheck("store:json_roundtrip", "fail", "JSON roundtrip returned unexpected data")
        return PilotStoreDoctorCheck("store:json_roundtrip", "pass", "atomic JSON write/read roundtrip succeeded")
    except Exception as exc:  # noqa: BLE001 - doctor should report operational failures
        return PilotStoreDoctorCheck("store:json_roundtrip", "fail", str(exc))
    finally:
        probe_path.unlink(missing_ok=True)


def _check_payload_write(root: Path) -> PilotStoreDoctorCheck:
    probe_dir = root / ".doctor"
    payload_path = probe_dir / f"payload_{uuid4().hex}.bin"
    try:
        probe_dir.mkdir(parents=True, exist_ok=True)
        payload_path.write_bytes(b"green-direct-pilot-store")
        if payload_path.read_bytes() != b"green-direct-pilot-store":
            return PilotStoreDoctorCheck("store:payload_write", "fail", "payload roundtrip returned unexpected data")
        return PilotStoreDoctorCheck("store:payload_write", "pass", "payload write/read roundtrip succeeded")
    except Exception as exc:  # noqa: BLE001 - doctor should report operational failures
        return PilotStoreDoctorCheck("store:payload_write", "fail", str(exc))
    finally:
        payload_path.unlink(missing_ok=True)


def _check_lock(root: Path) -> PilotStoreDoctorCheck:
    try:
        with local_store_lock(root, name="doctor", timeout_seconds=1.0, poll_interval_seconds=0.01):
            try:
                with local_store_lock(root, name="doctor", timeout_seconds=0.01, poll_interval_seconds=0.001):
                    pass
            except TimeoutError:
                pass
            else:
                return PilotStoreDoctorCheck("store:lock", "fail", "same lock name was re-acquired while held")
        with local_store_lock(root, name="doctor", timeout_seconds=1.0, poll_interval_seconds=0.01):
            pass
        return PilotStoreDoctorCheck("store:lock", "pass", "cooperative file lock can acquire, block, and release")
    except Exception as exc:  # noqa: BLE001 - doctor should report operational failures
        return PilotStoreDoctorCheck("store:lock", "fail", str(exc))


def _json_metadata_paths(root: Path) -> list[Path]:
    patterns = (
        "registry/users/*.json",
        "registry/projects/*/project.json",
        "registry/projects/*/memberships/*.json",
        "auth/credentials/*.json",
        "auth/sessions/*.json",
        "projects/*/studies/*/jobs/*.json",
        "projects/*/studies/*/results/*.json",
        "projects/*/studies/*/artifacts/*/artifact.json",
    )
    paths: list[Path] = []
    for pattern in patterns:
        paths.extend(root.glob(pattern))
    return sorted(set(paths))


def _check_existing_json(root: Path) -> PilotStoreDoctorCheck:
    paths = _json_metadata_paths(root)
    try:
        for path in paths:
            read_json(path)
        return PilotStoreDoctorCheck("store:json_metadata", "pass", f"validated JSON metadata files: {len(paths)}")
    except Exception as exc:  # noqa: BLE001 - doctor should report operational failures
        return PilotStoreDoctorCheck("store:json_metadata", "fail", f"{path}: {exc}")


def _audit_log_paths(root: Path) -> list[Path]:
    paths = []
    global_path = root / "audit" / "global.jsonl"
    if global_path.exists():
        paths.append(global_path)
    paths.extend(root.glob("projects/*/audit.jsonl"))
    return sorted(set(paths))


def _check_audit_logs(root: Path) -> PilotStoreDoctorCheck:
    paths = _audit_log_paths(root)
    line_count = 0
    try:
        for path in paths:
            line_number = 0
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if not line.strip():
                    continue
                json.loads(line)
                line_count += 1
        return PilotStoreDoctorCheck("store:audit_jsonl", "pass", f"validated audit logs: {len(paths)} files, {line_count} events")
    except Exception as exc:  # noqa: BLE001 - doctor should report operational failures
        return PilotStoreDoctorCheck("store:audit_jsonl", "fail", f"{path}:{line_number}: {exc}")


def run_pilot_store_doctor(root: str | Path) -> PilotStoreDoctorResult:
    """Run deployment-time checks for the local pilot store."""

    store_dir = Path(root).resolve()
    checks = [
        _check_store_directory(store_dir),
        _check_json_roundtrip(store_dir),
        _check_payload_write(store_dir),
        _check_lock(store_dir),
        _check_existing_json(store_dir),
        _check_audit_logs(store_dir),
    ]
    status = "fail" if any(check.status == "fail" for check in checks) else "pass"
    return PilotStoreDoctorResult(
        store_dir=str(store_dir),
        status=status,
        checks=tuple(checks),
    )
