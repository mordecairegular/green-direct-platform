"""Local file-backed ResultStore for the internal pilot.

This is a small persistence adapter for artifacts, result indexes, and audit
events. It is intentionally independent from Streamlit session state and can
be replaced by SQLite/Postgres or object storage in later slices.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from enum import Enum
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

from green_direct.models.pilot_backend import (
    ArtifactKind,
    AuditLog,
    JobArtifact,
    StudyResultRecord,
)


_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def _validate_segment(value: str, field_name: str) -> str:
    text = str(value)
    if not _SAFE_SEGMENT.fullmatch(text):
        raise ValueError(f"{field_name} contains unsafe path characters.")
    return text


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_value(nested) for key, nested in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_json_value(payload), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


class LocalResultStore:
    """Project/study-scoped local artifact and result index store."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

    def _project_dir(self, project_id: str) -> Path:
        return self.root / "projects" / _validate_segment(project_id, "project_id")

    def _study_dir(self, project_id: str, study_id: str) -> Path:
        return self._project_dir(project_id) / "studies" / _validate_segment(study_id, "study_id")

    def _artifact_dir(self, project_id: str, study_id: str, artifact_id: str) -> Path:
        return (
            self._study_dir(project_id, study_id)
            / "artifacts"
            / _validate_segment(artifact_id, "artifact_id")
        )

    def _result_path(self, project_id: str, study_id: str, result_id: str) -> Path:
        return (
            self._study_dir(project_id, study_id)
            / "results"
            / f"{_validate_segment(result_id, 'result_id')}.json"
        )

    def store_artifact(
        self,
        *,
        artifact_id: str,
        project_id: str,
        study_id: str,
        job_id: str,
        kind: ArtifactKind | str,
        payload: bytes | str,
        filename: str,
        content_type: str = "application/octet-stream",
        overwrite: bool = False,
    ) -> JobArtifact:
        """Write an artifact payload and return its immutable index record."""

        safe_filename = _validate_segment(filename, "filename")
        artifact_dir = self._artifact_dir(project_id, study_id, artifact_id)
        payload_path = artifact_dir / safe_filename
        metadata_path = artifact_dir / "artifact.json"
        if (payload_path.exists() or metadata_path.exists()) and not overwrite:
            raise FileExistsError(f"Artifact already exists: {artifact_id}")

        data = payload.encode("utf-8") if isinstance(payload, str) else bytes(payload)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        payload_path.write_bytes(data)
        digest = hashlib.sha256(data).hexdigest()
        storage_uri = (
            f"local-result-store://{_validate_segment(project_id, 'project_id')}/"
            f"{_validate_segment(study_id, 'study_id')}/artifacts/"
            f"{_validate_segment(artifact_id, 'artifact_id')}/{safe_filename}"
        )
        artifact = JobArtifact(
            artifact_id=artifact_id,
            project_id=project_id,
            study_id=study_id,
            job_id=job_id,
            kind=kind,
            storage_uri=storage_uri,
            content_type=content_type,
            sha256=digest,
            size_bytes=len(data),
        )
        _write_json(metadata_path, asdict(artifact))
        return artifact

    def load_artifact(self, project_id: str, study_id: str, artifact_id: str) -> JobArtifact:
        """Load an artifact index record without reading its binary payload."""

        metadata_path = self._artifact_dir(project_id, study_id, artifact_id) / "artifact.json"
        data = _read_json(metadata_path)
        return JobArtifact(
            artifact_id=data["artifact_id"],
            project_id=data["project_id"],
            study_id=data["study_id"],
            job_id=data["job_id"],
            kind=data["kind"],
            storage_uri=data["storage_uri"],
            content_type=data["content_type"],
            sha256=data.get("sha256"),
            size_bytes=int(data.get("size_bytes", 0)),
            created_at=datetime.fromisoformat(data["created_at"]),
        )

    def read_artifact_payload(self, artifact: JobArtifact) -> bytes:
        """Read payload bytes for a previously stored artifact record."""

        artifact_dir = self._artifact_dir(artifact.project_id, artifact.study_id, artifact.artifact_id)
        filename = artifact.storage_uri.rsplit("/", 1)[-1]
        payload = (artifact_dir / _validate_segment(filename, "filename")).read_bytes()
        if artifact.sha256 and hashlib.sha256(payload).hexdigest() != artifact.sha256:
            raise ValueError("Artifact checksum mismatch.")
        return payload

    def save_result_record(self, record: StudyResultRecord, *, overwrite: bool = False) -> StudyResultRecord:
        """Persist a study result index."""

        path = self._result_path(record.project_id, record.study_id, record.result_id)
        if path.exists() and not overwrite:
            raise FileExistsError(f"Result record already exists: {record.result_id}")
        _write_json(path, asdict(record))
        return record

    def load_result_record(self, project_id: str, study_id: str, result_id: str) -> StudyResultRecord:
        """Load a study result index."""

        data = _read_json(self._result_path(project_id, study_id, result_id))
        return StudyResultRecord(
            result_id=data["result_id"],
            project_id=data["project_id"],
            study_id=data["study_id"],
            created_by_job_id=data["created_by_job_id"],
            technical_summary_artifact_id=data.get("technical_summary_artifact_id"),
            economy_summary_artifact_id=data.get("economy_summary_artifact_id"),
            single_entity_summary_artifact_id=data.get("single_entity_summary_artifact_id"),
            recommendation_artifact_id=data.get("recommendation_artifact_id"),
            hourly_detail_artifact_ids=data.get("hourly_detail_artifact_ids") or {},
            report_artifact_ids=data.get("report_artifact_ids") or {},
            created_at=datetime.fromisoformat(data["created_at"]),
        )

    def append_audit_log(self, event: AuditLog) -> AuditLog:
        """Append one audit event as JSONL."""

        if event.project_id is None:
            path = self.root / "audit" / "global.jsonl"
        else:
            path = self._project_dir(event.project_id) / "audit.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(_json_value(asdict(event)), ensure_ascii=False, sort_keys=True))
            handle.write("\n")
        return event

    def read_audit_log(self, project_id: str | None = None) -> list[AuditLog]:
        """Read global or project-scoped audit events."""

        path = self.root / "audit" / "global.jsonl" if project_id is None else self._project_dir(project_id) / "audit.jsonl"
        if not path.exists():
            return []
        events: list[AuditLog] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            data = json.loads(line)
            events.append(
                AuditLog(
                    event_id=data["event_id"],
                    actor_user_id=data["actor_user_id"],
                    action=data["action"],
                    project_id=data.get("project_id"),
                    study_id=data.get("study_id"),
                    job_id=data.get("job_id"),
                    target_type=data.get("target_type"),
                    target_id=data.get("target_id"),
                    metadata=data.get("metadata") or {},
                    created_at=datetime.fromisoformat(data["created_at"]),
                )
            )
        return events
