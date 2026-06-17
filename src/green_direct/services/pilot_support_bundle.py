"""Sanitized support bundle for first public-beta issue triage."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from green_direct.models.pilot_backend import Project
from green_direct.services.job_store import LocalJobStore
from green_direct.services.local_store_utils import read_json
from green_direct.services.pilot_registry import LocalPilotRegistry
from green_direct.services.pilot_store_doctor import run_pilot_store_doctor
from green_direct.services.result_store import LocalResultStore


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _counter(values: list[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def _metadata_paths(root: Path, all_pattern: str, project_pattern: str, *, project_id: str | None) -> list[Path]:
    if project_id is None:
        base = root / "projects"
        return sorted(base.glob(all_pattern)) if base.exists() else []
    base = root / "projects" / project_id
    return sorted(base.glob(project_pattern)) if base.exists() else []


def _redact_path(text: str, root: Path) -> str:
    redacted = text.replace(str(root), "<store_dir>")
    return redacted.replace(root.as_posix(), "<store_dir>")


def _doctor_summary(root: Path) -> dict[str, Any]:
    result = run_pilot_store_doctor(root)
    return {
        "status": result.status,
        "checks": [
            {
                "name": check.name,
                "status": check.status,
                "message": _redact_path(check.message, root),
            }
            for check in result.checks
        ],
    }


def _artifact_records(root: Path, *, project_id: str | None) -> list[dict[str, Any]]:
    paths = _metadata_paths(
        root,
        "*/studies/*/artifacts/*/artifact.json",
        "studies/*/artifacts/*/artifact.json",
        project_id=project_id,
    )
    records: list[dict[str, Any]] = []
    for path in paths:
        data = read_json(path)
        records.append(
            {
                "artifact_id": data.get("artifact_id"),
                "project_id": data.get("project_id"),
                "study_id": data.get("study_id"),
                "job_id": data.get("job_id"),
                "kind": data.get("kind"),
                "content_type": data.get("content_type"),
                "size_bytes": int(data.get("size_bytes", 0) or 0),
                "retention_policy": data.get("retention_policy"),
                "payload_available": data.get("purged_at") is None,
                "expires_at": data.get("expires_at"),
                "purged_at": data.get("purged_at"),
                "created_at": data.get("created_at"),
                "sha256_prefix": str(data.get("sha256") or "")[:12] or None,
            }
        )
    return sorted(
        records,
        key=lambda item: (str(item["project_id"]), str(item["study_id"]), str(item["artifact_id"])),
    )


def _result_records(root: Path, *, project_id: str | None) -> list[dict[str, Any]]:
    paths = _metadata_paths(
        root,
        "*/studies/*/results/*.json",
        "studies/*/results/*.json",
        project_id=project_id,
    )
    records: list[dict[str, Any]] = []
    for path in paths:
        data = read_json(path)
        records.append(
            {
                "result_id": data.get("result_id"),
                "project_id": data.get("project_id"),
                "study_id": data.get("study_id"),
                "created_by_job_id": data.get("created_by_job_id"),
                "has_technical_summary": bool(data.get("technical_summary_artifact_id")),
                "has_economy_summary": bool(data.get("economy_summary_artifact_id")),
                "has_single_entity_summary": bool(data.get("single_entity_summary_artifact_id")),
                "has_recommendation": bool(data.get("recommendation_artifact_id")),
                "annual_cashflow_artifact_count": len(data.get("annual_cashflow_artifact_ids") or {}),
                "hourly_detail_artifact_count": len(data.get("hourly_detail_artifact_ids") or {}),
                "report_artifact_count": len(data.get("report_artifact_ids") or {}),
                "is_deleted": bool(data.get("deleted_at")),
                "is_pinned": bool(data.get("pinned_at")),
                "created_at": data.get("created_at"),
            }
        )
    return sorted(
        records,
        key=lambda item: (str(item["project_id"]), str(item["study_id"]), str(item["result_id"])),
    )


def _audit_events(
    result_store: LocalResultStore,
    projects: list[Project],
    *,
    project_id: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    if project_id is None:
        events = result_store.read_audit_log(None)
        for project in projects:
            events.extend(result_store.read_audit_log(project.project_id))
    else:
        events = result_store.read_audit_log(project_id)
    events = sorted(events, key=lambda event: (event.created_at, event.event_id), reverse=True)[:limit]
    return [
        {
            "created_at": event.created_at.isoformat(),
            "action": event.action.value,
            "actor_user_id": event.actor_user_id,
            "project_id": event.project_id,
            "study_id": event.study_id,
            "job_id": event.job_id,
            "target_type": event.target_type,
            "target_id": event.target_id,
            "metadata_keys": sorted(str(key) for key in event.metadata.keys()),
        }
        for event in events
    ]


def build_pilot_support_bundle(
    root: str | Path,
    *,
    project_id: str | None = None,
    recent_limit: int = 50,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Return sanitized pilot-store metadata for public-beta issue triage.

    The bundle intentionally avoids artifact payloads, raw upload files,
    passwords, session tokens, login names, display names, project names,
    artifact storage URIs, result labels, and full audit metadata values.
    """

    if recent_limit < 1:
        raise ValueError("recent_limit must be positive.")

    store_dir = Path(root).resolve()
    registry = LocalPilotRegistry(store_dir)
    job_store = LocalJobStore(store_dir)
    result_store = LocalResultStore(store_dir)
    now = generated_at or datetime.now(timezone.utc)

    users = registry.list_users()
    projects = registry.list_projects()
    scoped_projects = [project for project in projects if project_id is None or project.project_id == project_id]
    jobs = job_store.list_jobs(project_id=project_id)
    artifacts = _artifact_records(store_dir, project_id=project_id)
    results = _result_records(store_dir, project_id=project_id)
    audit = _audit_events(result_store, projects, project_id=project_id, limit=recent_limit)

    memberships: list[dict[str, Any]] = []
    for project in scoped_projects:
        for membership in registry.list_project_memberships(project.project_id):
            memberships.append(
                {
                    "membership_id": membership.membership_id,
                    "project_id": membership.project_id,
                    "user_id": membership.user_id,
                    "role": membership.role.value,
                    "status": membership.status.value,
                    "can_export_artifacts": membership.can_export_artifacts,
                    "created_at": membership.created_at.isoformat(),
                }
            )
    memberships = sorted(memberships, key=lambda item: (item["project_id"], item["user_id"]))

    return {
        "generated_at": now.isoformat(),
        "store_dir_name": store_dir.name,
        "project_id": project_id,
        "recent_limit": recent_limit,
        "redaction": {
            "omitted": [
                "password_hashes",
                "session_tokens",
                "login_names",
                "display_names",
                "project_names",
                "artifact_payloads",
                "artifact_storage_uri",
                "result_labels",
                "audit_metadata_values",
                "absolute_store_path",
            ]
        },
        "doctor": _doctor_summary(store_dir),
        "counts": {
            "users": len(users),
            "projects": len(scoped_projects),
            "memberships": len(memberships),
            "jobs": len(jobs),
            "artifacts": len(artifacts),
            "results": len(results),
            "recent_audit_events": len(audit),
            "artifact_payload_size_bytes": sum(int(item["size_bytes"]) for item in artifacts),
        },
        "users": {
            "by_status": _counter([user.status.value for user in users]),
            "platform_admin_count": sum(1 for user in users if user.is_platform_admin),
        },
        "projects": [
            {
                "project_id": project.project_id,
                "status": project.status.value,
                "created_by_user_id": project.created_by_user_id,
                "created_at": project.created_at.isoformat(),
            }
            for project in scoped_projects
        ],
        "memberships": memberships,
        "jobs": {
            "by_status": _counter([job.status.value for job in jobs]),
            "by_type": _counter([job.job_type.value for job in jobs]),
            "recent": [
                {
                    "job_id": job.job_id,
                    "project_id": job.project_id,
                    "study_id": job.study_id,
                    "job_type": job.job_type.value,
                    "status": job.status.value,
                    "requested_by_user_id": job.requested_by_user_id,
                    "progress_current": job.progress_current,
                    "progress_total": job.progress_total,
                    "progress_message_present": bool(job.progress_message),
                    "worker_id": job.worker_id,
                    "queued_at": _iso(job.queued_at),
                    "started_at": _iso(job.started_at),
                    "finished_at": _iso(job.finished_at),
                    "last_heartbeat_at": _iso(job.last_heartbeat_at),
                    "error_message_present": bool(job.error_message),
                    "input_artifact_keys": sorted(job.input_artifact_ids.keys()),
                }
                for job in sorted(jobs, key=lambda item: (item.queued_at, item.job_id), reverse=True)[:recent_limit]
            ],
        },
        "artifacts": {
            "by_kind": _counter([str(item["kind"]) for item in artifacts]),
            "records": artifacts[:recent_limit],
        },
        "results": {
            "records": results[:recent_limit],
        },
        "audit": {
            "scope": "global_and_projects" if project_id is None else "project",
            "recent": audit,
        },
    }
