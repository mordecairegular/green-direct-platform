"""Command-line entry points for Green Direct operations."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
import getpass
import os
from pathlib import Path
import sys
from typing import Sequence
from uuid import uuid4

from green_direct.models.pilot_backend import (
    AuditAction,
    AuditLog,
    Job,
    JobStatus,
    JobType,
    Project,
    ProjectMembership,
    ProjectRole,
    User,
)
from green_direct.services import (
    LocalJobStore,
    LocalPilotAdminService,
    LocalPilotAuth,
    LocalPilotRegistry,
    PilotAccessService,
    LocalResultStore,
)

DEFAULT_PILOT_STORE_DIR = Path(".runtime") / "pilot_store"


@dataclass(frozen=True)
class _PilotServiceBundle:
    registry: LocalPilotRegistry
    job_store: LocalJobStore
    result_store: LocalResultStore
    auth: LocalPilotAuth
    admin: LocalPilotAdminService
    access: PilotAccessService


def _pilot_services(store_dir: str | Path) -> _PilotServiceBundle:
    root = Path(store_dir).resolve()
    registry = LocalPilotRegistry(root)
    job_store = LocalJobStore(root)
    result_store = LocalResultStore(root)
    auth = LocalPilotAuth(root, registry=registry, result_store=result_store)
    admin = LocalPilotAdminService(
        registry=registry,
        auth=auth,
        result_store=result_store,
    )
    access = PilotAccessService(
        registry=registry,
        job_store=job_store,
        result_store=result_store,
    )
    return _PilotServiceBundle(
        registry=registry,
        job_store=job_store,
        result_store=result_store,
        auth=auth,
        admin=admin,
        access=access,
    )


def _password_from_args(args: argparse.Namespace, *, required: bool) -> str | None:
    password = getattr(args, "password", None)
    password_env = getattr(args, "password_env", None)
    if password and password_env:
        raise ValueError("Use either --password or --password-env, not both.")
    if password_env:
        if password_env not in os.environ:
            raise ValueError(f"Environment variable is not set: {password_env}")
        password = os.environ[password_env]
    if password is None and required:
        password = getpass.getpass("Password: ")
    return password


def _print_user(user: User) -> None:
    status = user.status.value
    admin = "yes" if user.is_platform_admin else "no"
    print(f"{user.user_id}\t{user.login_name}\t{user.display_name}\t{status}\tplatform_admin={admin}")


def _print_project(project: Project) -> None:
    created_by = project.created_by_user_id or ""
    print(
        f"{project.project_id}\t{project.name}\t{project.status.value}\t"
        f"{created_by}\t{project.created_at.isoformat()}"
    )


def _print_project_membership(membership: ProjectMembership) -> None:
    export = "yes" if membership.can_export_artifacts else "no"
    print(
        f"{membership.membership_id}\t{membership.project_id}\t{membership.user_id}\t"
        f"{membership.role.value}\t{membership.status.value}\tcan_export={export}\t"
        f"{membership.created_at.isoformat()}"
    )


def _cmd_bootstrap(args: argparse.Namespace) -> int:
    password = _password_from_args(args, required=True)
    services = _pilot_services(args.store_dir)
    user = services.admin.bootstrap_platform_admin(
        user=User(args.user_id, args.login_name, args.display_name),
        password=str(password),
    )
    print(f"Bootstrapped platform admin: {user.user_id}")
    return 0


def _cmd_create_user(args: argparse.Namespace) -> int:
    password = _password_from_args(args, required=False)
    services = _pilot_services(args.store_dir)
    user = services.admin.create_user(
        actor_user_id=args.actor_user_id,
        user=User(
            args.user_id,
            args.login_name,
            args.display_name,
            is_platform_admin=bool(args.platform_admin),
        ),
        initial_password=password,
    )
    print(f"Created user: {user.user_id}")
    return 0


def _cmd_reset_password(args: argparse.Namespace) -> int:
    password = _password_from_args(args, required=True)
    services = _pilot_services(args.store_dir)
    services.admin.set_user_password(
        actor_user_id=args.actor_user_id,
        user_id=args.user_id,
        password=str(password),
    )
    print(f"Password reset for user: {args.user_id}")
    return 0


def _cmd_disable_user(args: argparse.Namespace) -> int:
    services = _pilot_services(args.store_dir)
    user = services.admin.disable_user(
        actor_user_id=args.actor_user_id,
        user_id=args.user_id,
    )
    print(f"Disabled user: {user.user_id}")
    return 0


def _cmd_set_platform_admin(args: argparse.Namespace) -> int:
    services = _pilot_services(args.store_dir)
    user = services.admin.set_platform_admin(
        actor_user_id=args.actor_user_id,
        user_id=args.user_id,
        is_platform_admin=bool(args.enabled),
    )
    state = "granted" if user.is_platform_admin else "revoked"
    print(f"Platform admin {state}: {user.user_id}")
    return 0


def _cmd_list_users(args: argparse.Namespace) -> int:
    services = _pilot_services(args.store_dir)
    users = services.admin.list_users(
        actor_user_id=args.actor_user_id,
        active_only=bool(args.active_only),
    )
    print("user_id\tlogin_name\tdisplay_name\tstatus\tplatform_admin")
    for user in users:
        _print_user(user)
    return 0


def _cmd_list_sessions(args: argparse.Namespace) -> int:
    services = _pilot_services(args.store_dir)
    services.admin.list_users(actor_user_id=args.actor_user_id)
    sessions = services.auth.list_user_sessions(
        args.user_id,
        active_only=bool(args.active_only),
    )
    print("session_id\tuser_id\texpires_at\trevoked")
    for session in sessions:
        revoked = "yes" if session.is_revoked else "no"
        print(f"{session.session_id}\t{session.user_id}\t{session.expires_at.isoformat()}\t{revoked}")
    return 0


def _cmd_list_projects(args: argparse.Namespace) -> int:
    services = _pilot_services(args.store_dir)
    projects = services.admin.list_projects(
        actor_user_id=args.actor_user_id,
        active_only=bool(args.active_only),
    )
    print("project_id\tname\tstatus\tcreated_by\tcreated_at")
    for project in projects:
        _print_project(project)
    return 0


def _cmd_create_project(args: argparse.Namespace) -> int:
    services = _pilot_services(args.store_dir)
    project = services.admin.create_project(
        actor_user_id=args.actor_user_id,
        project=Project(
            args.project_id,
            args.name,
            created_by_user_id=args.owner_user_id,
        ),
        owner_user_id=args.owner_user_id,
    )
    print(f"Created project: {project.project_id}")
    return 0


def _cmd_archive_project(args: argparse.Namespace) -> int:
    services = _pilot_services(args.store_dir)
    project = services.admin.archive_project(
        actor_user_id=args.actor_user_id,
        project_id=args.project_id,
    )
    print(f"Archived project: {project.project_id}")
    return 0


def _cmd_list_project_members(args: argparse.Namespace) -> int:
    services = _pilot_services(args.store_dir)
    memberships = services.admin.list_project_memberships(
        actor_user_id=args.actor_user_id,
        project_id=args.project_id,
        active_only=bool(args.active_only),
    )
    print("membership_id\tproject_id\tuser_id\trole\tstatus\tcan_export\tcreated_at")
    for membership in memberships:
        _print_project_membership(membership)
    return 0


def _export_permission_from_args(args: argparse.Namespace) -> bool | None:
    if getattr(args, "can_export_artifacts", False):
        return True
    if getattr(args, "cannot_export_artifacts", False):
        return False
    return None


def _cmd_grant_project_role(args: argparse.Namespace) -> int:
    services = _pilot_services(args.store_dir)
    membership = services.admin.grant_project_role(
        actor_user_id=args.actor_user_id,
        project_id=args.project_id,
        user_id=args.user_id,
        role=args.role,
        can_export_artifacts=_export_permission_from_args(args),
    )
    print(f"Granted project role: {membership.project_id}\t{membership.user_id}\t{membership.role.value}")
    return 0


def _cmd_disable_project_member(args: argparse.Namespace) -> int:
    services = _pilot_services(args.store_dir)
    membership = services.admin.disable_project_membership(
        actor_user_id=args.actor_user_id,
        project_id=args.project_id,
        user_id=args.user_id,
    )
    print(f"Disabled project member: {membership.project_id}\t{membership.user_id}")
    return 0


def _format_dt(value: datetime | None) -> str:
    return value.isoformat() if value is not None else ""


def _format_job_progress(job: Job) -> str:
    if job.progress_total:
        return f"{job.progress_current}/{job.progress_total}"
    if job.progress_current:
        return str(job.progress_current)
    return ""


def _print_job_header(*, include_stale: bool = True) -> None:
    header = (
        "project_id\tstudy_id\tjob_id\tjob_type\tstatus\trequested_by\t"
        "progress\tinput_artifacts\tworker_id\tqueued_at\tstarted_at\tfinished_at\tlast_heartbeat_at"
    )
    if include_stale:
        header += "\tstale"
    print(header)


def _print_job_row(job: Job, *, stale: str | None = None) -> None:
    row = (
        f"{job.project_id}\t{job.study_id}\t{job.job_id}\t{job.job_type.value}\t"
        f"{job.status.value}\t{job.requested_by_user_id}\t{_format_job_progress(job)}\t"
        f"{len(job.input_artifact_ids)}\t{job.worker_id or ''}\t"
        f"{_format_dt(job.queued_at)}\t{_format_dt(job.started_at)}\t"
        f"{_format_dt(job.finished_at)}\t{_format_dt(job.last_heartbeat_at)}"
    )
    if stale is not None:
        row += f"\t{stale}"
    print(row)


def _format_audit_metadata(event: AuditLog) -> str:
    return json.dumps(event.metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _cmd_list_audit_events(args: argparse.Namespace) -> int:
    services = _pilot_services(args.store_dir)
    services.admin.list_users(actor_user_id=args.actor_user_id)
    if args.limit < 1:
        raise ValueError("--limit must be positive.")
    actions = set(getattr(args, "action", None) or [])
    events = services.result_store.read_audit_log(args.project_id)
    if actions:
        events = [event for event in events if event.action.value in actions]
    events = sorted(
        events,
        key=lambda event: (event.created_at, event.event_id),
        reverse=not bool(args.oldest_first),
    )
    events = events[: args.limit]
    print("created_at\taction\tactor_user_id\tproject_id\tstudy_id\tjob_id\ttarget_type\ttarget_id\tmetadata")
    for event in events:
        print(
            f"{event.created_at.isoformat()}\t{event.action.value}\t{event.actor_user_id}\t"
            f"{event.project_id or ''}\t{event.study_id or ''}\t{event.job_id or ''}\t"
            f"{event.target_type or ''}\t{event.target_id or ''}\t{_format_audit_metadata(event)}"
        )
    return 0


def _cmd_list_jobs(args: argparse.Namespace) -> int:
    services = _pilot_services(args.store_dir)
    services.admin.list_users(actor_user_id=args.actor_user_id)
    statuses = getattr(args, "status", None)
    stale_after_minutes = getattr(args, "stale_after_minutes", None)
    stale_after_seconds = None if stale_after_minutes is None else int(stale_after_minutes) * 60
    if stale_after_seconds is not None and stale_after_seconds < 0:
        raise ValueError("--stale-after-minutes must be non-negative.")
    now = datetime.now(timezone.utc)
    jobs = services.job_store.list_jobs(
        project_id=args.project_id,
        statuses=statuses,
    )
    _print_job_header(include_stale=True)
    for job in jobs:
        stale = ""
        if stale_after_seconds is not None:
            stale = "yes" if job.is_stale(now=now, stale_after_seconds=stale_after_seconds) else "no"
        _print_job_row(job, stale=stale)
    return 0


def _cmd_claim_next_job(args: argparse.Namespace) -> int:
    services = _pilot_services(args.store_dir)
    claimed = services.access.claim_next_job_for_worker(
        actor_user_id=args.actor_user_id,
        worker_id=args.worker_id,
        project_id=args.project_id,
        job_types=getattr(args, "job_type", None),
        claimed_at=datetime.now(timezone.utc),
    )
    if claimed is None:
        print("No queued job matched.")
        return 0
    _print_job_header(include_stale=False)
    _print_job_row(claimed)
    return 0


def _cmd_heartbeat_job(args: argparse.Namespace) -> int:
    services = _pilot_services(args.store_dir)
    updated = services.access.update_worker_job_progress(
        actor_user_id=args.actor_user_id,
        worker_id=args.worker_id,
        project_id=args.project_id,
        study_id=args.study_id,
        job_id=args.job_id,
        current=args.current,
        total=args.total,
        message=args.message,
        heartbeat_at=datetime.now(timezone.utc),
    )
    _print_job_header(include_stale=False)
    _print_job_row(updated)
    return 0


def _cmd_complete_worker_job(args: argparse.Namespace) -> int:
    services = _pilot_services(args.store_dir)
    completed = services.access.succeed_worker_job(
        actor_user_id=args.actor_user_id,
        worker_id=args.worker_id,
        project_id=args.project_id,
        study_id=args.study_id,
        job_id=args.job_id,
        finished_at=datetime.now(timezone.utc),
    )
    _print_job_header(include_stale=False)
    _print_job_row(completed)
    return 0


def _cmd_fail_worker_job(args: argparse.Namespace) -> int:
    services = _pilot_services(args.store_dir)
    failed = services.access.fail_worker_job(
        actor_user_id=args.actor_user_id,
        worker_id=args.worker_id,
        project_id=args.project_id,
        study_id=args.study_id,
        job_id=args.job_id,
        error_message=args.error_message,
        finished_at=datetime.now(timezone.utc),
    )
    _print_job_header(include_stale=False)
    _print_job_row(failed)
    return 0


def _cmd_purge_expired_artifacts(args: argparse.Namespace) -> int:
    services = _pilot_services(args.store_dir)
    services.admin.list_users(actor_user_id=args.actor_user_id)
    now = datetime.now(timezone.utc)
    purged = services.result_store.purge_expired_artifacts(now=now)
    for artifact in purged:
        services.result_store.append_audit_log(
            AuditLog(
                event_id=f"artifact-purge-{uuid4().hex}",
                actor_user_id=args.actor_user_id,
                action=AuditAction.DELETE_ARTIFACT,
                project_id=artifact.project_id,
                study_id=artifact.study_id,
                job_id=artifact.job_id,
                target_type="artifact_payload",
                target_id=artifact.artifact_id,
                metadata={
                    "retention_policy": artifact.retention_policy.value,
                    "expires_at": artifact.expires_at.isoformat() if artifact.expires_at else None,
                    "purged_at": artifact.purged_at.isoformat() if artifact.purged_at else None,
                },
                created_at=now,
            )
        )
    print(f"Purged expired artifact payloads: {len(purged)}")
    for artifact in purged:
        print(f"{artifact.project_id}\t{artifact.study_id}\t{artifact.artifact_id}\t{artifact.purged_at.isoformat()}")
    return 0


def _cmd_fail_stale_jobs(args: argparse.Namespace) -> int:
    services = _pilot_services(args.store_dir)
    services.admin.list_users(actor_user_id=args.actor_user_id)
    now = datetime.now(timezone.utc)
    stale_after_seconds = int(args.stale_after_minutes) * 60
    if stale_after_seconds < 0:
        raise ValueError("--stale-after-minutes must be non-negative.")
    message = (
        "Marked failed by pilot-admin fail-stale-jobs after "
        f"{args.stale_after_minutes} minutes without heartbeat."
    )
    failed = services.job_store.fail_stale_running_jobs(
        now=now,
        stale_after_seconds=stale_after_seconds,
        error_message=message,
        project_id=args.project_id,
    )
    for job in failed:
        services.result_store.append_audit_log(
            AuditLog(
                event_id=f"stale-job-fail-{uuid4().hex}",
                actor_user_id=args.actor_user_id,
                action=AuditAction.COMPLETE_JOB,
                project_id=job.project_id,
                study_id=job.study_id,
                job_id=job.job_id,
                target_type="job",
                target_id=job.job_id,
                metadata={
                    "status": job.status.value,
                    "reason": "stale_running_job",
                    "stale_after_seconds": stale_after_seconds,
                    "worker_id": job.worker_id,
                    "last_heartbeat_at": (
                        job.last_heartbeat_at.isoformat() if job.last_heartbeat_at else None
                    ),
                    "error_message": job.error_message,
                },
                created_at=now,
            )
        )
    print(f"Marked stale running jobs failed: {len(failed)}")
    for job in failed:
        finished_at = job.finished_at.isoformat() if job.finished_at else ""
        print(f"{job.project_id}\t{job.study_id}\t{job.job_id}\t{finished_at}")
    return 0


def _add_common_store_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--store-dir",
        default=str(DEFAULT_PILOT_STORE_DIR),
        help=f"Pilot backend local store directory. Default: {DEFAULT_PILOT_STORE_DIR}",
    )


def _add_actor_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--actor-user-id", required=True, help="Platform admin user id performing this operation.")


def _add_password_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--password", help="Password value. Prefer --password-env for shared machines.")
    parser.add_argument("--password-env", help="Environment variable containing the password.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="green-direct")
    subparsers = parser.add_subparsers(dest="command")

    pilot_admin = subparsers.add_parser("pilot-admin", help="Internal pilot account administration.")
    pilot_admin_sub = pilot_admin.add_subparsers(dest="pilot_admin_command")

    bootstrap = pilot_admin_sub.add_parser("bootstrap", help="Create the first platform admin.")
    _add_common_store_arg(bootstrap)
    bootstrap.add_argument("--user-id", required=True)
    bootstrap.add_argument("--login-name", required=True)
    bootstrap.add_argument("--display-name", required=True)
    _add_password_args(bootstrap)
    bootstrap.set_defaults(func=_cmd_bootstrap)

    create_user = pilot_admin_sub.add_parser("create-user", help="Create a user.")
    _add_common_store_arg(create_user)
    _add_actor_arg(create_user)
    create_user.add_argument("--user-id", required=True)
    create_user.add_argument("--login-name", required=True)
    create_user.add_argument("--display-name", required=True)
    create_user.add_argument("--platform-admin", action="store_true", help="Create the user as a platform admin.")
    _add_password_args(create_user)
    create_user.set_defaults(func=_cmd_create_user)

    reset_password = pilot_admin_sub.add_parser("reset-password", help="Reset a local pilot user password.")
    _add_common_store_arg(reset_password)
    _add_actor_arg(reset_password)
    reset_password.add_argument("--user-id", required=True)
    _add_password_args(reset_password)
    reset_password.set_defaults(func=_cmd_reset_password)

    disable_user = pilot_admin_sub.add_parser("disable-user", help="Disable a user and revoke active sessions.")
    _add_common_store_arg(disable_user)
    _add_actor_arg(disable_user)
    disable_user.add_argument("--user-id", required=True)
    disable_user.set_defaults(func=_cmd_disable_user)

    grant_admin = pilot_admin_sub.add_parser("grant-platform-admin", help="Grant platform-admin status.")
    _add_common_store_arg(grant_admin)
    _add_actor_arg(grant_admin)
    grant_admin.add_argument("--user-id", required=True)
    grant_admin.set_defaults(func=_cmd_set_platform_admin, enabled=True)

    revoke_admin = pilot_admin_sub.add_parser("revoke-platform-admin", help="Revoke platform-admin status.")
    _add_common_store_arg(revoke_admin)
    _add_actor_arg(revoke_admin)
    revoke_admin.add_argument("--user-id", required=True)
    revoke_admin.set_defaults(func=_cmd_set_platform_admin, enabled=False)

    list_users = pilot_admin_sub.add_parser("list-users", help="List users.")
    _add_common_store_arg(list_users)
    _add_actor_arg(list_users)
    list_users.add_argument("--active-only", action="store_true")
    list_users.set_defaults(func=_cmd_list_users)

    list_sessions = pilot_admin_sub.add_parser("list-sessions", help="List sessions for one user.")
    _add_common_store_arg(list_sessions)
    _add_actor_arg(list_sessions)
    list_sessions.add_argument("--user-id", required=True)
    list_sessions.add_argument("--active-only", action="store_true")
    list_sessions.set_defaults(func=_cmd_list_sessions)

    list_audit_events = pilot_admin_sub.add_parser(
        "list-audit-events",
        help="List global or project-scoped audit events.",
    )
    _add_common_store_arg(list_audit_events)
    _add_actor_arg(list_audit_events)
    list_audit_events.add_argument("--project-id", help="Read a project-scoped audit log. Omit for global audit.")
    list_audit_events.add_argument(
        "--action",
        action="append",
        choices=[action.value for action in AuditAction],
        help="Filter by audit action. May be provided multiple times.",
    )
    list_audit_events.add_argument("--limit", type=int, default=50, help="Maximum events to print. Default: 50.")
    list_audit_events.add_argument("--oldest-first", action="store_true", help="Print oldest events first.")
    list_audit_events.set_defaults(func=_cmd_list_audit_events)

    list_projects = pilot_admin_sub.add_parser("list-projects", help="List projects.")
    _add_common_store_arg(list_projects)
    _add_actor_arg(list_projects)
    list_projects.add_argument("--active-only", action="store_true")
    list_projects.set_defaults(func=_cmd_list_projects)

    create_project = pilot_admin_sub.add_parser("create-project", help="Create a project.")
    _add_common_store_arg(create_project)
    _add_actor_arg(create_project)
    create_project.add_argument("--project-id", required=True)
    create_project.add_argument("--name", required=True)
    create_project.add_argument(
        "--owner-user-id",
        help="Initial project admin user id. Defaults to the actor user id.",
    )
    create_project.set_defaults(func=_cmd_create_project)

    archive_project = pilot_admin_sub.add_parser("archive-project", help="Archive a project.")
    _add_common_store_arg(archive_project)
    _add_actor_arg(archive_project)
    archive_project.add_argument("--project-id", required=True)
    archive_project.set_defaults(func=_cmd_archive_project)

    list_project_members = pilot_admin_sub.add_parser(
        "list-project-members",
        help="List project memberships.",
    )
    _add_common_store_arg(list_project_members)
    _add_actor_arg(list_project_members)
    list_project_members.add_argument("--project-id", required=True)
    list_project_members.add_argument("--active-only", action="store_true")
    list_project_members.set_defaults(func=_cmd_list_project_members)

    grant_project_role = pilot_admin_sub.add_parser(
        "grant-project-role",
        help="Grant or update a project role for one user.",
    )
    _add_common_store_arg(grant_project_role)
    _add_actor_arg(grant_project_role)
    grant_project_role.add_argument("--project-id", required=True)
    grant_project_role.add_argument("--user-id", required=True)
    grant_project_role.add_argument("--role", required=True, choices=[role.value for role in ProjectRole])
    export_group = grant_project_role.add_mutually_exclusive_group()
    export_group.add_argument("--can-export-artifacts", action="store_true")
    export_group.add_argument("--cannot-export-artifacts", action="store_true")
    grant_project_role.set_defaults(func=_cmd_grant_project_role)

    disable_project_member = pilot_admin_sub.add_parser(
        "disable-project-member",
        help="Disable one project membership.",
    )
    _add_common_store_arg(disable_project_member)
    _add_actor_arg(disable_project_member)
    disable_project_member.add_argument("--project-id", required=True)
    disable_project_member.add_argument("--user-id", required=True)
    disable_project_member.set_defaults(func=_cmd_disable_project_member)

    list_jobs = pilot_admin_sub.add_parser("list-jobs", help="List project job metadata for operations.")
    _add_common_store_arg(list_jobs)
    _add_actor_arg(list_jobs)
    list_jobs.add_argument("--project-id", help="Limit output to one project.")
    list_jobs.add_argument(
        "--status",
        action="append",
        choices=[status.value for status in JobStatus],
        help="Filter by job status. May be provided multiple times.",
    )
    list_jobs.add_argument(
        "--stale-after-minutes",
        type=int,
        help="Mark running jobs as stale in the output if older than this heartbeat threshold.",
    )
    list_jobs.set_defaults(func=_cmd_list_jobs)

    claim_next_job = pilot_admin_sub.add_parser(
        "claim-next-job",
        help="Claim the oldest queued job for a trusted worker.",
    )
    _add_common_store_arg(claim_next_job)
    _add_actor_arg(claim_next_job)
    claim_next_job.add_argument("--worker-id", required=True, help="Worker id to assign to the claimed job.")
    claim_next_job.add_argument("--project-id", help="Limit claiming to one active project.")
    claim_next_job.add_argument(
        "--job-type",
        action="append",
        choices=[job_type.value for job_type in JobType],
        help="Filter by job type. May be provided multiple times.",
    )
    claim_next_job.set_defaults(func=_cmd_claim_next_job)

    heartbeat_job = pilot_admin_sub.add_parser(
        "heartbeat-job",
        help="Update heartbeat and optional progress for a claimed running job.",
    )
    _add_common_store_arg(heartbeat_job)
    _add_actor_arg(heartbeat_job)
    heartbeat_job.add_argument("--worker-id", required=True, help="Worker id assigned to the running job.")
    heartbeat_job.add_argument("--project-id", required=True)
    heartbeat_job.add_argument("--study-id", required=True)
    heartbeat_job.add_argument("--job-id", required=True)
    heartbeat_job.add_argument("--current", type=int, help="Current progress counter. Omit to keep existing value.")
    heartbeat_job.add_argument("--total", type=int, help="Total progress counter. Omit to keep existing value.")
    heartbeat_job.add_argument("--message", help="Progress message. Omit to keep existing value.")
    heartbeat_job.set_defaults(func=_cmd_heartbeat_job)

    complete_worker_job = pilot_admin_sub.add_parser(
        "complete-worker-job",
        help="Mark a claimed running worker job as succeeded.",
    )
    _add_common_store_arg(complete_worker_job)
    _add_actor_arg(complete_worker_job)
    complete_worker_job.add_argument("--worker-id", required=True, help="Worker id assigned to the running job.")
    complete_worker_job.add_argument("--project-id", required=True)
    complete_worker_job.add_argument("--study-id", required=True)
    complete_worker_job.add_argument("--job-id", required=True)
    complete_worker_job.set_defaults(func=_cmd_complete_worker_job)

    fail_worker_job = pilot_admin_sub.add_parser(
        "fail-worker-job",
        help="Mark a claimed running worker job as failed.",
    )
    _add_common_store_arg(fail_worker_job)
    _add_actor_arg(fail_worker_job)
    fail_worker_job.add_argument("--worker-id", required=True, help="Worker id assigned to the running job.")
    fail_worker_job.add_argument("--project-id", required=True)
    fail_worker_job.add_argument("--study-id", required=True)
    fail_worker_job.add_argument("--job-id", required=True)
    fail_worker_job.add_argument("--error-message", required=True, help="Sanitized worker failure message.")
    fail_worker_job.set_defaults(func=_cmd_fail_worker_job)

    purge_artifacts = pilot_admin_sub.add_parser(
        "purge-expired-artifacts",
        help="Purge expired artifact payloads while keeping metadata.",
    )
    _add_common_store_arg(purge_artifacts)
    _add_actor_arg(purge_artifacts)
    purge_artifacts.set_defaults(func=_cmd_purge_expired_artifacts)

    fail_stale_jobs = pilot_admin_sub.add_parser(
        "fail-stale-jobs",
        help="Mark running jobs failed when their heartbeat is older than the configured timeout.",
    )
    _add_common_store_arg(fail_stale_jobs)
    _add_actor_arg(fail_stale_jobs)
    fail_stale_jobs.add_argument(
        "--stale-after-minutes",
        type=int,
        default=60,
        help="Timeout in minutes since last heartbeat or start time. Default: 60.",
    )
    fail_stale_jobs.add_argument("--project-id", help="Limit cleanup to one project.")
    fail_stale_jobs.set_defaults(func=_cmd_fail_stale_jobs)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 0
    try:
        return int(args.func(args))
    except Exception as exc:  # noqa: BLE001 - CLI should return a clear operational error
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
