"""Command-line entry points for Green Direct operations."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import getpass
import os
from pathlib import Path
import sys
from typing import Sequence
from uuid import uuid4

from green_direct.models.pilot_backend import AuditAction, AuditLog, Job, JobStatus, User
from green_direct.services import (
    LocalJobStore,
    LocalPilotAdminService,
    LocalPilotAuth,
    LocalPilotRegistry,
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
    return _PilotServiceBundle(
        registry=registry,
        job_store=job_store,
        result_store=result_store,
        auth=auth,
        admin=admin,
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


def _format_dt(value: datetime | None) -> str:
    return value.isoformat() if value is not None else ""


def _format_job_progress(job: Job) -> str:
    if job.progress_total:
        return f"{job.progress_current}/{job.progress_total}"
    if job.progress_current:
        return str(job.progress_current)
    return ""


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
    print(
        "project_id\tstudy_id\tjob_id\tjob_type\tstatus\trequested_by\t"
        "progress\tworker_id\tqueued_at\tstarted_at\tfinished_at\tlast_heartbeat_at\tstale"
    )
    for job in jobs:
        stale = ""
        if stale_after_seconds is not None:
            stale = "yes" if job.is_stale(now=now, stale_after_seconds=stale_after_seconds) else "no"
        print(
            f"{job.project_id}\t{job.study_id}\t{job.job_id}\t{job.job_type.value}\t"
            f"{job.status.value}\t{job.requested_by_user_id}\t{_format_job_progress(job)}\t"
            f"{job.worker_id or ''}\t{_format_dt(job.queued_at)}\t{_format_dt(job.started_at)}\t"
            f"{_format_dt(job.finished_at)}\t{_format_dt(job.last_heartbeat_at)}\t{stale}"
        )
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
