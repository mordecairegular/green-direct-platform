"""Report the current controlled public beta launch status.

This script is intentionally read-only. It does not push to GitHub, create
Render services, or change Cloudflare settings. Use ``--check-remote`` to add
network-backed dry-run checks before asking the project owner for a real push.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import zipfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
LOCAL_TRIAL_ZIP = ROOT / "release" / "GreenDirectLocalTrial_20260617.zip"


def _run(command: list[str], *, timeout_seconds: int = 120) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "status": "pass" if completed.returncode == 0 else "fail",
    }


def _zip_status(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "status": "fail",
            "path": str(path.relative_to(ROOT)),
            "message": "local trial ZIP is missing",
        }

    contains_venv = False
    build_info = ""
    with zipfile.ZipFile(path) as archive:
        for entry in archive.namelist():
            normalized = entry.replace("\\", "/")
            if normalized.startswith(".venv/") or "/.venv/" in normalized:
                contains_venv = True
            if normalized == "BUILD_INFO.txt":
                build_info = archive.read(entry).decode("utf-8-sig", errors="replace")

    return {
        "status": "fail" if contains_venv else "pass",
        "path": str(path.relative_to(ROOT)),
        "size_bytes": path.stat().st_size,
        "size_mb": round(path.stat().st_size / (1024 * 1024), 2),
        "contains_venv": contains_venv,
        "build_info": build_info.strip(),
        "message": "local trial ZIP is ready" if not contains_venv else "local trial ZIP contains .venv",
    }


def build_report(*, check_remote: bool) -> dict[str, Any]:
    preflight_static = _run(
        [sys.executable, "scripts/preflight_internal_pilot_deploy.py", "--summary"],
        timeout_seconds=180,
    )
    report: dict[str, Any] = {
        "status": "not_ready",
        "latest_commit": _run(["git", "log", "-1", "--oneline"]),
        "branch": _run(["git", "status", "--short", "--branch"]),
        "remote": _run(["git", "remote", "-v"]),
        "static_preflight": preflight_static,
        "local_trial_zip": _zip_status(LOCAL_TRIAL_ZIP),
        "remote_checks_enabled": check_remote,
        "remote_dry_run": None,
        "git_sync": None,
        "github_private": None,
        "blockers": [],
        "next_actions": [],
    }

    blockers: list[str] = []
    if preflight_static["returncode"] != 0:
        blockers.append("Static deployment preflight is failing.")
    if report["local_trial_zip"]["status"] != "pass":
        blockers.append("Local trial ZIP is missing or contains packaged .venv state.")

    if check_remote:
        report["remote_dry_run"] = _run(["git", "push", "--dry-run", "origin", "codex/UI"])
        report["git_sync"] = _run(
            [sys.executable, "scripts/preflight_internal_pilot_deploy.py", "--require-git-sync", "--summary"],
            timeout_seconds=180,
        )
        report["github_private"] = _run(
            [
                sys.executable,
                "scripts/preflight_internal_pilot_deploy.py",
                "--require-github-private",
                "--summary",
            ],
            timeout_seconds=180,
        )
        if report["remote_dry_run"]["returncode"] != 0:
            blockers.append("GitHub dry-run push failed.")
        if report["git_sync"]["returncode"] != 0:
            blockers.append("Branch is not synchronized with GitHub; real push is still required.")
        if report["github_private"]["returncode"] != 0:
            blockers.append("GitHub Private visibility is not automatically verified.")
    else:
        blockers.append("Remote gates were not checked; rerun with --check-remote before Render deploy.")

    if blockers:
        report["blockers"] = blockers
        report["next_actions"] = [
            "If continuing public Route A, get owner approval and run git push origin codex/UI.",
            "After push, rerun this script with --check-remote.",
            "Install/login gh or manually confirm the GitHub repository is Private.",
        ]
    else:
        report["status"] = "ready_for_render_handoff"
        report["next_actions"] = [
            "Wait for GitHub Actions Internal Pilot Quality Gate to pass.",
            "Follow docs/PUBLIC_BETA_OWNER_GO_LIVE_STEPS.md for Render and Cloudflare setup.",
        ]

    return report


def _status_line(result: dict[str, Any] | None) -> str:
    if result is None:
        return "NOT CHECKED"
    return str(result.get("status", "unknown")).upper()


def render_text(report: dict[str, Any]) -> str:
    lines = [
        f"Public beta status: {report['status'].upper()}",
        f"Latest commit: {report['latest_commit']['stdout'] or 'unknown'}",
        f"Branch: {report['branch']['stdout'] or 'unknown'}",
        f"Static preflight: {_status_line(report['static_preflight'])}",
        (
            "Local trial ZIP: "
            f"{report['local_trial_zip']['status'].upper()} "
            f"({report['local_trial_zip'].get('path', 'missing')}, "
            f"{report['local_trial_zip'].get('size_mb', 'n/a')} MB)"
        ),
        f"Remote dry-run: {_status_line(report['remote_dry_run'])}",
        f"Git sync gate: {_status_line(report['git_sync'])}",
        f"GitHub private gate: {_status_line(report['github_private'])}",
    ]
    if report["blockers"]:
        lines.append("")
        lines.append("Blockers:")
        lines.extend(f"- {item}" for item in report["blockers"])
    if report["next_actions"]:
        lines.append("")
        lines.append("Next actions:")
        lines.extend(f"- {item}" for item in report["next_actions"])
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-remote", action="store_true", help="Run dry-run push and remote-dependent gates.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_report(check_remote=args.check_remote)
    if args.json:
        print(json.dumps(report, ensure_ascii=True, indent=2))
    else:
        print(render_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
