"""Local file-backed ResultStore for the internal pilot.

This is a small persistence adapter for artifacts, result indexes, and audit
events. It is intentionally independent from Streamlit session state and can
be replaced by SQLite/Postgres or object storage in later slices.
"""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from green_direct.models.pilot_backend import (
    ArtifactRetentionPolicy,
    ArtifactKind,
    AuditLog,
    JobArtifact,
    StudyResultRecord,
)
from green_direct.services.local_store_utils import (
    json_value,
    read_json,
    validate_path_segment,
    write_json,
)


def _parse_optional_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class LocalResultStore:
    """Project/study-scoped local artifact and result index store."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

    def _project_dir(self, project_id: str) -> Path:
        return self.root / "projects" / validate_path_segment(project_id, "project_id")

    def _study_dir(self, project_id: str, study_id: str) -> Path:
        return self._project_dir(project_id) / "studies" / validate_path_segment(study_id, "study_id")

    def _artifact_dir(self, project_id: str, study_id: str, artifact_id: str) -> Path:
        return (
            self._study_dir(project_id, study_id)
            / "artifacts"
            / validate_path_segment(artifact_id, "artifact_id")
        )

    def _result_path(self, project_id: str, study_id: str, result_id: str) -> Path:
        return (
            self._study_dir(project_id, study_id)
            / "results"
            / f"{validate_path_segment(result_id, 'result_id')}.json"
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
        retention_policy: ArtifactRetentionPolicy | str = ArtifactRetentionPolicy.KEEP,
        expires_at: datetime | None = None,
        overwrite: bool = False,
    ) -> JobArtifact:
        """Write an artifact payload and return its immutable index record."""

        safe_filename = validate_path_segment(filename, "filename")
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
            f"local-result-store://{validate_path_segment(project_id, 'project_id')}/"
            f"{validate_path_segment(study_id, 'study_id')}/artifacts/"
            f"{validate_path_segment(artifact_id, 'artifact_id')}/{safe_filename}"
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
            retention_policy=retention_policy,
            expires_at=expires_at,
            purged_at=None,
        )
        write_json(metadata_path, asdict(artifact))
        return artifact

    def load_artifact(self, project_id: str, study_id: str, artifact_id: str) -> JobArtifact:
        """Load an artifact index record without reading its binary payload."""

        metadata_path = self._artifact_dir(project_id, study_id, artifact_id) / "artifact.json"
        data = read_json(metadata_path)
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
            retention_policy=data.get("retention_policy", ArtifactRetentionPolicy.KEEP.value),
            expires_at=_parse_optional_datetime(data.get("expires_at")),
            purged_at=_parse_optional_datetime(data.get("purged_at")),
            created_at=datetime.fromisoformat(data["created_at"]),
        )

    def read_artifact_payload(self, artifact: JobArtifact) -> bytes:
        """Read payload bytes for a previously stored artifact record."""

        if not artifact.is_payload_available:
            raise FileNotFoundError(f"Artifact payload has been purged: {artifact.artifact_id}")
        artifact_dir = self._artifact_dir(artifact.project_id, artifact.study_id, artifact.artifact_id)
        filename = artifact.storage_uri.rsplit("/", 1)[-1]
        payload = (artifact_dir / validate_path_segment(filename, "filename")).read_bytes()
        if artifact.sha256 and hashlib.sha256(payload).hexdigest() != artifact.sha256:
            raise ValueError("Artifact checksum mismatch.")
        return payload

    def purge_expired_artifacts(self, *, now: datetime) -> list[JobArtifact]:
        """Delete expired artifact payloads while keeping artifact metadata."""

        purged: list[JobArtifact] = []
        projects_dir = self.root / "projects"
        if not projects_dir.exists():
            return []
        for metadata_path in sorted(projects_dir.glob("*/studies/*/artifacts/*/artifact.json")):
            data = read_json(metadata_path)
            artifact = self.load_artifact(data["project_id"], data["study_id"], data["artifact_id"])
            if not artifact.is_payload_available or not artifact.is_expired(now):
                continue
            artifact_dir = self._artifact_dir(artifact.project_id, artifact.study_id, artifact.artifact_id)
            filename = validate_path_segment(artifact.storage_uri.rsplit("/", 1)[-1], "filename")
            payload_path = artifact_dir / filename
            if payload_path.exists():
                payload_path.unlink()
            purged_artifact = JobArtifact(
                artifact_id=artifact.artifact_id,
                project_id=artifact.project_id,
                study_id=artifact.study_id,
                job_id=artifact.job_id,
                kind=artifact.kind,
                storage_uri=artifact.storage_uri,
                content_type=artifact.content_type,
                sha256=artifact.sha256,
                size_bytes=artifact.size_bytes,
                retention_policy=artifact.retention_policy,
                expires_at=artifact.expires_at,
                purged_at=now,
                created_at=artifact.created_at,
            )
            write_json(metadata_path, asdict(purged_artifact))
            purged.append(purged_artifact)
        return purged

    def save_result_record(self, record: StudyResultRecord, *, overwrite: bool = False) -> StudyResultRecord:
        """Persist a study result index."""

        path = self._result_path(record.project_id, record.study_id, record.result_id)
        if path.exists() and not overwrite:
            raise FileExistsError(f"Result record already exists: {record.result_id}")
        write_json(path, asdict(record))
        return record

    def load_result_record(self, project_id: str, study_id: str, result_id: str) -> StudyResultRecord:
        """Load a study result index."""

        data = read_json(self._result_path(project_id, study_id, result_id))
        return self._result_record_from_json(data)

    def _result_record_from_json(self, data: dict) -> StudyResultRecord:
        return StudyResultRecord(
            result_id=data["result_id"],
            project_id=data["project_id"],
            study_id=data["study_id"],
            created_by_job_id=data["created_by_job_id"],
            technical_summary_artifact_id=data.get("technical_summary_artifact_id"),
            economy_summary_artifact_id=data.get("economy_summary_artifact_id"),
            single_entity_summary_artifact_id=data.get("single_entity_summary_artifact_id"),
            recommendation_input_artifact_id=data.get("recommendation_input_artifact_id"),
            recommendation_artifact_id=data.get("recommendation_artifact_id"),
            annual_cashflow_artifact_ids=data.get("annual_cashflow_artifact_ids") or {},
            hourly_detail_artifact_ids=data.get("hourly_detail_artifact_ids") or {},
            report_artifact_ids=data.get("report_artifact_ids") or {},
            created_at=datetime.fromisoformat(data["created_at"]),
            deleted_at=_parse_optional_datetime(data.get("deleted_at")),
            deleted_by_user_id=data.get("deleted_by_user_id"),
        )

    def soft_delete_result_record(
        self,
        project_id: str,
        study_id: str,
        result_id: str,
        *,
        deleted_by_user_id: str,
        deleted_at: datetime | None = None,
    ) -> StudyResultRecord:
        """Hide a result index from default lists without deleting payloads."""

        if not str(deleted_by_user_id).strip():
            raise ValueError("deleted_by_user_id must not be empty.")
        record = self.load_result_record(project_id, study_id, result_id)
        if record.is_deleted:
            return record
        deleted = replace(
            record,
            deleted_at=deleted_at or _utcnow(),
            deleted_by_user_id=str(deleted_by_user_id),
        )
        write_json(self._result_path(project_id, study_id, result_id), asdict(deleted))
        return deleted

    def list_study_result_records(
        self,
        project_id: str,
        study_id: str,
        *,
        include_deleted: bool = False,
    ) -> list[StudyResultRecord]:
        """List result indexes under one study, newest first."""

        results_dir = self._study_dir(project_id, study_id) / "results"
        if not results_dir.exists():
            return []
        records = [
            self._result_record_from_json(read_json(path))
            for path in sorted(results_dir.glob("*.json"))
        ]
        if not include_deleted:
            records = [record for record in records if not record.is_deleted]
        return sorted(records, key=lambda record: (record.created_at, record.result_id), reverse=True)

    def list_project_result_records(
        self,
        project_id: str,
        *,
        include_deleted: bool = False,
    ) -> list[StudyResultRecord]:
        """List result indexes under every study in one project, newest first."""

        project_dir = self._project_dir(project_id)
        if not project_dir.exists():
            return []
        records = [
            self._result_record_from_json(read_json(path))
            for path in sorted(project_dir.glob("studies/*/results/*.json"))
        ]
        if not include_deleted:
            records = [record for record in records if not record.is_deleted]
        return sorted(records, key=lambda record: (record.created_at, record.study_id, record.result_id), reverse=True)

    def append_audit_log(self, event: AuditLog) -> AuditLog:
        """Append one audit event as JSONL."""

        if event.project_id is None:
            path = self.root / "audit" / "global.jsonl"
        else:
            path = self._project_dir(event.project_id) / "audit.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(json_value(asdict(event)), ensure_ascii=False, sort_keys=True))
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
