"""Preflight checks for controlled public beta deployment.

The script verifies repository deployment artifacts before the app is pushed to
GitHub/Render for mobile-network colleague trials. By default it performs only
fast static checks. Use ``--run-smoke`` to also start Streamlit briefly via the
smoke script.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from green_direct.services import run_pilot_store_doctor  # noqa: E402


REQUIRED_FILES = (
    ".dockerignore",
    ".github/workflows/internal-pilot-quality.yml",
    ".env.example",
    "Dockerfile",
    "README_DEPLOY.md",
    "SECURITY.md",
    "docker-compose.yml",
    "render.yaml",
    "requirements-runtime.txt",
    "docs/INTERNAL_PILOT_DEPLOYMENT_RUNBOOK.md",
    "docs/MANAGED_PUBLIC_BETA_DEPLOYMENT.md",
    "docs/MOBILE_NETWORK_TRIAL_CHECKLIST.md",
    "docs/PUBLIC_BETA_OWNER_GO_LIVE_STEPS.md",
    "docs/PUBLIC_BETA_FIRST_LAUNCH_PLAYBOOK.md",
    "docs/PUBLIC_BETA_DEPLOYMENT_AUDIT.md",
    "scripts/backup_pilot_store.ps1",
    "scripts/restore_pilot_store.ps1",
    "scripts/smoke_streamlit_app.py",
)

DOCKERIGNORE_REQUIRED_PATTERNS = (
    ".env",
    ".env.*",
    "!.env.example",
    ".github/",
    ".runtime/",
    ".venv/",
    "outputs/",
    "output/",
    "archive/",
    "tests/",
    "docs/",
    "notes/",
    "*.log",
)

RENDER_REQUIRED_ENV = {
    "GREEN_DIRECT_ENABLE_PILOT_AUTH": "1",
    "GREEN_DIRECT_ENABLE_RUNTIME_SNAPSHOT": "0",
    "GREEN_DIRECT_PILOT_STORE_DIR": "/data/pilot_store",
    "GREEN_DIRECT_MAX_UPLOAD_MB": "20",
    "GREEN_DIRECT_MAX_SCENARIOS_PER_RUN": "20000",
    "GREEN_DIRECT_DEFAULT_PARALLEL_WORKERS": "1",
    "GREEN_DIRECT_ECONOMY_CASHFLOW_RETENTION_THRESHOLD": "1000",
    "GREEN_DIRECT_ECONOMY_RETAINED_CASHFLOW_LIMIT": "20",
    "STREAMLIT_SERVER_ADDRESS": "0.0.0.0",
    "STREAMLIT_SERVER_PORT": "8503",
    "STREAMLIT_SERVER_HEADLESS": "true",
    "STREAMLIT_BROWSER_GATHER_USAGE_STATS": "false",
    "PYTHONPATH": "/app/src",
    "PORT": "8503",
    "BROWSER_PATH": "/usr/bin/chromium",
}
COMPOSE_REQUIRED_WEB_ENV = {
    "GREEN_DIRECT_ENABLE_PILOT_AUTH": "1",
    "GREEN_DIRECT_ENABLE_RUNTIME_SNAPSHOT": "0",
    "GREEN_DIRECT_PILOT_STORE_DIR": "/data/pilot_store",
    "GREEN_DIRECT_MAX_UPLOAD_MB": "${GREEN_DIRECT_MAX_UPLOAD_MB:-20}",
    "GREEN_DIRECT_MAX_SCENARIOS_PER_RUN": "${GREEN_DIRECT_MAX_SCENARIOS_PER_RUN:-20000}",
    "GREEN_DIRECT_DEFAULT_PARALLEL_WORKERS": "${GREEN_DIRECT_DEFAULT_PARALLEL_WORKERS:-1}",
    "GREEN_DIRECT_ECONOMY_CASHFLOW_RETENTION_THRESHOLD": "${GREEN_DIRECT_ECONOMY_CASHFLOW_RETENTION_THRESHOLD:-1000}",
    "GREEN_DIRECT_ECONOMY_RETAINED_CASHFLOW_LIMIT": "${GREEN_DIRECT_ECONOMY_RETAINED_CASHFLOW_LIMIT:-20}",
    "BROWSER_PATH": "/usr/bin/chromium",
    "STREAMLIT_SERVER_ADDRESS": "0.0.0.0",
    "STREAMLIT_SERVER_PORT": "8503",
    "STREAMLIT_SERVER_HEADLESS": "true",
    "STREAMLIT_BROWSER_GATHER_USAGE_STATS": "false",
    "PYTHONPATH": "/app/src",
    "PORT": "8503",
}
COMPOSE_REQUIRED_WORKER_ENV = {
    "GREEN_DIRECT_ENABLE_PILOT_AUTH": "1",
    "GREEN_DIRECT_ENABLE_RUNTIME_SNAPSHOT": "0",
    "GREEN_DIRECT_PILOT_STORE_DIR": "/data/pilot_store",
    "BROWSER_PATH": "/usr/bin/chromium",
    "PYTHONPATH": "/app/src",
}
RENDER_REQUIRED_BRANCH = "codex/UI"
MAX_TRACKED_FILE_BYTES = 95 * 1024 * 1024
GIT_ALLOWED_TRACKED_PATHS = {
    "outputs/.gitkeep",
}
GIT_LOCAL_STATE_SEGMENTS = {
    ".runtime",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}
GIT_LOCAL_STATE_PREFIXES = (
    "build/",
    "dist/",
    "release/",
    "pilot_store/",
    "backups/",
)
GIT_SECRET_PAYLOAD_SUFFIXES = (
    ".pkl",
    ".pickle",
    ".db",
    ".sqlite",
    ".sqlite3",
    ".db-journal",
    ".log",
    ".zip",
    ".7z",
    ".tar",
    ".tar.gz",
)


def _check(condition: bool, checks: list[dict[str, str]], name: str, message: str) -> None:
    checks.append({"name": name, "status": "pass" if condition else "fail", "message": message})


def _record(checks: list[dict[str, str]], name: str, status: str, message: str) -> None:
    checks.append({"name": name, "status": status, "message": message})


def _load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _runtime_requirement_lines(path: Path) -> set[str]:
    if not path.exists():
        return set()
    requirements: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        value = line.split("#", 1)[0].strip()
        if value:
            requirements.add(value)
    return requirements


def _pyproject_dependency_lines(path: Path) -> set[str]:
    if not path.exists():
        return set()
    dependencies: set[str] = set()
    in_dependencies = False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("dependencies"):
            in_dependencies = True
            continue
        if in_dependencies:
            if line == "]":
                break
            value = line.rstrip(",").strip().strip('"').strip("'")
            if value:
                dependencies.add(value)
    return dependencies


def _required_file_checks(checks: list[dict[str, str]]) -> None:
    for relative in REQUIRED_FILES:
        path = ROOT / relative
        _check(path.exists(), checks, f"file:{relative}", f"required file exists: {relative}")


def _dockerignore_checks(checks: list[dict[str, str]]) -> None:
    path = ROOT / ".dockerignore"
    if not path.exists():
        _check(False, checks, "dockerignore:exists", ".dockerignore is missing")
        return
    lines = set(path.read_text(encoding="utf-8").splitlines())
    for pattern in DOCKERIGNORE_REQUIRED_PATTERNS:
        _check(pattern in lines, checks, f"dockerignore:{pattern}", f".dockerignore includes {pattern}")


def _dockerfile_checks(checks: list[dict[str, str]]) -> None:
    path = ROOT / "Dockerfile"
    if not path.exists():
        _check(False, checks, "dockerfile:exists", "Dockerfile is missing")
        return
    text = path.read_text(encoding="utf-8")
    expected = (
        "GREEN_DIRECT_ENABLE_PILOT_AUTH=1",
        "GREEN_DIRECT_ENABLE_RUNTIME_SNAPSHOT=0",
        "GREEN_DIRECT_PILOT_STORE_DIR=/data/pilot_store",
        "GREEN_DIRECT_MAX_SCENARIOS_PER_RUN=20000",
        "GREEN_DIRECT_DEFAULT_PARALLEL_WORKERS=1",
        "GREEN_DIRECT_ECONOMY_CASHFLOW_RETENTION_THRESHOLD=1000",
        "GREEN_DIRECT_ECONOMY_RETAINED_CASHFLOW_LIMIT=20",
        "BROWSER_PATH=/usr/bin/chromium",
        "PORT=8503",
        "COPY requirements-runtime.txt ./",
        "pip install --no-cache-dir -r requirements-runtime.txt",
        "USER appuser",
        "_stcore/health",
        "--server.port=${PORT",
        "--server.maxUploadSize=${STREAMLIT_SERVER_MAX_UPLOAD_SIZE:-${GREEN_DIRECT_MAX_UPLOAD_MB:-20}}",
    )
    for needle in expected:
        _check(needle in text, checks, f"dockerfile:{needle}", f"Dockerfile contains {needle}")


def _runtime_dependency_checks(checks: list[dict[str, str]]) -> None:
    runtime_requirements = _runtime_requirement_lines(ROOT / "requirements-runtime.txt")
    project_dependencies = _pyproject_dependency_lines(ROOT / "pyproject.toml")
    missing_from_runtime = sorted(project_dependencies - runtime_requirements)
    extra_runtime = sorted(runtime_requirements - project_dependencies)
    _record(
        checks,
        "runtime-deps:pyproject-sync",
        "pass" if not missing_from_runtime and not extra_runtime else "fail",
        (
            "requirements-runtime.txt matches pyproject project dependencies"
            if not missing_from_runtime and not extra_runtime
            else (
                "runtime dependency mismatch; "
                f"missing_from_runtime={missing_from_runtime}; extra_runtime={extra_runtime}"
            )
        ),
    )


def _compose_checks(checks: list[dict[str, str]]) -> None:
    try:
        compose = _load_yaml(ROOT / "docker-compose.yml")
        service = compose["services"]["green-direct"]
        environment = service["environment"]
    except Exception as exc:  # noqa: BLE001 - report preflight parse failure
        _check(False, checks, "compose:parse", f"docker-compose.yml parse failed: {exc}")
        return

    for key, expected in COMPOSE_REQUIRED_WEB_ENV.items():
        _check(environment.get(key) == expected, checks, f"compose:env:{key}", f"{key} defaults to {expected}")
    _check(
        "green_direct_pilot_store:/data/pilot_store" in service.get("volumes", []),
        checks,
        "compose:volume",
        "compose mounts green_direct_pilot_store at /data/pilot_store",
    )
    _check(
        compose.get("volumes", {}).get("green_direct_pilot_store", {}).get("name") == "green_direct_pilot_store",
        checks,
        "compose:volume-name",
        "compose declares named pilot store volume",
    )

    worker = compose.get("services", {}).get("green-direct-worker", {})
    worker_environment = worker.get("environment", {})
    for key, expected in COMPOSE_REQUIRED_WORKER_ENV.items():
        _check(
            worker_environment.get(key) == expected,
            checks,
            f"compose:worker-env:{key}",
            f"worker {key} defaults to {expected}",
        )
    worker_command = " ".join(str(part) for part in worker.get("command", []))
    _check(
        "technical_study" in worker_command and "economic_study" in worker_command,
        checks,
        "compose:worker-job-types",
        "worker loop polls technical_study and economic_study jobs",
    )


def _render_checks(checks: list[dict[str, str]]) -> None:
    try:
        render = _load_yaml(ROOT / "render.yaml")
        service = render["services"][0]
    except Exception as exc:  # noqa: BLE001 - report preflight parse failure
        _check(False, checks, "render:parse", f"render.yaml parse failed: {exc}")
        return

    _check(service.get("runtime") == "docker", checks, "render:runtime", "Render service uses Docker runtime")
    _check(
        service.get("branch") == RENDER_REQUIRED_BRANCH,
        checks,
        "render:branch",
        f"Render service deploys the pilot branch {RENDER_REQUIRED_BRANCH}",
    )
    _check(service.get("dockerfilePath") == "./Dockerfile", checks, "render:dockerfile", "Render uses root Dockerfile")
    _check(service.get("healthCheckPath") == "/_stcore/health", checks, "render:health", "Render health path is Streamlit health")
    _check(service.get("numInstances") == 1, checks, "render:instances", "Render pilot service stays single-instance")
    _check(
        service.get("autoDeployTrigger") == "checksPass",
        checks,
        "render:auto-deploy",
        "Render deploys only after linked GitHub checks pass",
    )
    disk = service.get("disk") or {}
    _check(disk.get("name") == "green-direct-pilot-store", checks, "render:disk-name", "Render persistent disk has the pilot store name")
    _check(disk.get("mountPath") == "/data", checks, "render:disk", "Render persistent disk mounts at /data")
    try:
        disk_size_gb = int(disk.get("sizeGB"))
    except (TypeError, ValueError):
        disk_size_gb = 0
    _check(disk_size_gb >= 10, checks, "render:disk-size", "Render persistent disk is at least 10 GB")
    env = {item["key"]: str(item["value"]) for item in service.get("envVars", [])}
    for key, expected in RENDER_REQUIRED_ENV.items():
        _check(env.get(key) == expected, checks, f"render:env:{key}", f"{key} defaults to {expected}")


def _run_smoke(timeout_seconds: int, checks: list[dict[str, str]]) -> None:
    command = [
        sys.executable,
        str(ROOT / "scripts" / "smoke_streamlit_app.py"),
        "--timeout-seconds",
        str(timeout_seconds),
    ]
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    ok = completed.returncode == 0 and "streamlit-smoke-ok" in completed.stdout
    message = "Streamlit smoke passed" if ok else (completed.stdout + completed.stderr)[-1000:]
    _check(ok, checks, "smoke:streamlit", message)


def _pilot_store_doctor_checks(store_dir: str, checks: list[dict[str, str]]) -> None:
    result = run_pilot_store_doctor(store_dir)
    _record(
        checks,
        "pilot-store:doctor",
        result.status,
        f"pilot store doctor {result.status}: {result.store_dir}",
    )
    for check in result.checks:
        name = check.name.removeprefix("store:")
        _record(checks, f"pilot-store:{name}", check.status, check.message)


def _git_output(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _github_repo_slug_from_remote(remote_url: str) -> str | None:
    value = remote_url.strip()
    if value.startswith("https://github.com/"):
        slug = value.removeprefix("https://github.com/")
    elif value.startswith("git@github.com:"):
        slug = value.removeprefix("git@github.com:")
    else:
        return None
    if slug.endswith(".git"):
        slug = slug[:-4]
    parts = [part for part in slug.split("/") if part]
    if len(parts) != 2:
        return None
    return "/".join(parts)


def _tracked_paths() -> tuple[list[str], str | None]:
    result = _git_output(["ls-files", "-z"])
    if result.returncode != 0:
        return [], result.stderr.strip() or "git ls-files failed"
    paths = [path for path in result.stdout.split("\0") if path]
    return paths, None


def _is_private_env_file(path: str) -> bool:
    name = Path(path).name
    return name == ".env" or (name.startswith(".env.") and name != ".env.example")


def _is_local_state_path(path: str) -> bool:
    if path in GIT_ALLOWED_TRACKED_PATHS:
        return False
    normalized = path.replace("\\", "/")
    parts = normalized.split("/")
    return any(part in GIT_LOCAL_STATE_SEGMENTS for part in parts) or any(
        normalized.startswith(prefix) for prefix in GIT_LOCAL_STATE_PREFIXES
    )


def _is_secret_payload_path(path: str) -> bool:
    if path in GIT_ALLOWED_TRACKED_PATHS:
        return False
    lower = path.lower()
    return any(lower.endswith(suffix) for suffix in GIT_SECRET_PAYLOAD_SUFFIXES)


def _format_path_sample(paths: list[str]) -> str:
    sample = ", ".join(paths[:5])
    if len(paths) > 5:
        sample += f", ... (+{len(paths) - 5} more)"
    return sample


def _git_tracked_safety_checks(checks: list[dict[str, str]]) -> None:
    paths, error = _tracked_paths()
    if error is not None:
        _check(False, checks, "git-tracked:list", error)
        return
    _check(True, checks, "git-tracked:list", f"tracked file count={len(paths)}")

    private_env_files = sorted(path for path in paths if _is_private_env_file(path))
    _record(
        checks,
        "git-tracked:env-files",
        "fail" if private_env_files else "pass",
        (
            f"tracked private env files found: {_format_path_sample(private_env_files)}"
            if private_env_files
            else "no tracked private .env files"
        ),
    )

    local_state_paths = sorted(path for path in paths if _is_local_state_path(path))
    _record(
        checks,
        "git-tracked:local-state",
        "fail" if local_state_paths else "pass",
        (
            f"tracked local runtime/build state found: {_format_path_sample(local_state_paths)}"
            if local_state_paths
            else "no tracked local runtime, build, cache, pilot store, or backup paths"
        ),
    )

    secret_payload_paths = sorted(path for path in paths if _is_secret_payload_path(path))
    _record(
        checks,
        "git-tracked:secret-payloads",
        "fail" if secret_payload_paths else "pass",
        (
            f"tracked binary/runtime payloads found: {_format_path_sample(secret_payload_paths)}"
            if secret_payload_paths
            else "no tracked pickle, database, log, or archive payload files"
        ),
    )

    oversize_paths: list[str] = []
    for path in paths:
        local_path = ROOT / path
        if local_path.exists() and local_path.is_file() and local_path.stat().st_size > MAX_TRACKED_FILE_BYTES:
            oversize_paths.append(path)
    _record(
        checks,
        "git-tracked:size",
        "fail" if oversize_paths else "pass",
        (
            f"tracked files exceed GitHub 100 MiB hard limit guardrail: {_format_path_sample(sorted(oversize_paths))}"
            if oversize_paths
            else "no tracked files exceed the 95 MiB GitHub push guardrail"
        ),
    )


def _configured_render_branch() -> str:
    render = _load_yaml(ROOT / "render.yaml")
    service = render["services"][0]
    return str(service.get("branch", "")).strip()


def _git_sync_checks(checks: list[dict[str, str]]) -> None:
    try:
        render_branch = _configured_render_branch()
    except Exception as exc:  # noqa: BLE001 - report preflight parse failure
        _check(False, checks, "git:render-branch", f"cannot read render.yaml branch: {exc}")
        return
    _check(bool(render_branch), checks, "git:render-branch", f"render.yaml branch is {render_branch}")

    current_branch = _git_output(["branch", "--show-current"])
    if current_branch.returncode != 0:
        _check(False, checks, "git:branch", f"git branch failed: {current_branch.stderr.strip()}")
        return
    current_branch_name = current_branch.stdout.strip()
    _record(
        checks,
        "git:branch",
        "pass" if current_branch_name == render_branch else "fail",
        (
            f"current branch matches render.yaml branch {render_branch}"
            if current_branch_name == render_branch
            else f"current branch is {current_branch_name or '<detached>'}, but render.yaml deploys {render_branch}"
        ),
    )

    status = _git_output(["status", "--porcelain"])
    if status.returncode != 0:
        _check(False, checks, "git:status", f"git status failed: {status.stderr.strip()}")
        return
    is_clean = status.stdout.strip() == ""
    _record(
        checks,
        "git:clean",
        "pass" if is_clean else "fail",
        "working tree is clean" if is_clean else "working tree has uncommitted changes; commit or stash before deploy",
    )

    upstream = _git_output(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    if upstream.returncode != 0:
        _check(False, checks, "git:upstream", "current branch has no upstream; push/set upstream before Render deploy")
        return
    upstream_name = upstream.stdout.strip()
    _check(bool(upstream_name), checks, "git:upstream", f"current branch tracks {upstream_name}")
    expected_upstream_suffix = f"/{render_branch}"
    _record(
        checks,
        "git:upstream-branch",
        "pass" if upstream_name.endswith(expected_upstream_suffix) else "fail",
        (
            f"upstream branch matches render.yaml branch {render_branch}"
            if upstream_name.endswith(expected_upstream_suffix)
            else f"upstream is {upstream_name}, but render.yaml deploys {render_branch}"
        ),
    )

    counts = _git_output(["rev-list", "--left-right", "--count", "@{u}...HEAD"])
    if counts.returncode != 0:
        _check(False, checks, "git:sync", f"git rev-list failed: {counts.stderr.strip()}")
        return
    parts = counts.stdout.split()
    if len(parts) != 2:
        _check(False, checks, "git:sync", f"unexpected ahead/behind output: {counts.stdout.strip()}")
        return
    behind_count, ahead_count = (int(parts[0]), int(parts[1]))
    is_synced = ahead_count == 0 and behind_count == 0
    _record(
        checks,
        "git:sync",
        "pass" if is_synced else "fail",
        (
            f"branch is synchronized with upstream (ahead={ahead_count}, behind={behind_count})"
            if is_synced
            else f"branch is not synchronized with upstream (ahead={ahead_count}, behind={behind_count}); push/pull before Render deploy"
        ),
    )


def _github_private_checks(checks: list[dict[str, str]]) -> None:
    origin = _git_output(["config", "--get", "remote.origin.url"])
    if origin.returncode != 0 or not origin.stdout.strip():
        _check(False, checks, "github:origin", "remote.origin.url is not configured")
        return
    remote_url = origin.stdout.strip()
    repo_slug = _github_repo_slug_from_remote(remote_url)
    _record(
        checks,
        "github:origin",
        "pass" if repo_slug is not None else "fail",
        (
            f"origin points to GitHub repository {repo_slug}"
            if repo_slug is not None
            else f"origin is not a supported GitHub URL: {remote_url}"
        ),
    )
    if repo_slug is None:
        return

    try:
        completed = subprocess.run(
            ["gh", "repo", "view", repo_slug, "--json", "visibility", "--jq", ".visibility"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        _check(
            False,
            checks,
            "github:visibility",
            "GitHub CLI `gh` is required for --require-github-private; install gh or verify repository privacy manually",
        )
        return

    visibility = completed.stdout.strip().upper()
    _record(
        checks,
        "github:visibility",
        "pass" if completed.returncode == 0 and visibility == "PRIVATE" else "fail",
        (
            f"GitHub repository {repo_slug} visibility is PRIVATE"
            if completed.returncode == 0 and visibility == "PRIVATE"
            else (
                f"could not read GitHub repository visibility for {repo_slug}: {completed.stderr.strip()}"
                if completed.returncode != 0
                else f"GitHub repository {repo_slug} visibility is {visibility or '<empty>'}; use a private repository for pilot deploy"
            )
        ),
    )


def _next_action_for_failed_check(check: dict[str, str]) -> str:
    name = check["name"]
    if name == "git:clean":
        return "Commit, stash, or intentionally discard local changes before a deploy."
    if name == "git:sync":
        return "Synchronize the deploy branch with GitHub, usually `git push origin codex/UI` after review."
    if name in {"git:branch", "git:upstream-branch", "render:branch"}:
        return "Align the current branch, upstream branch, and render.yaml branch before importing in Render."
    if name == "github:visibility":
        return "Install/login GitHub CLI and rerun, or manually confirm the GitHub repository is Private."
    if name == "github:origin":
        return "Point remote.origin.url at the private GitHub repository that Render will import."
    if name.startswith("pilot-store:"):
        return "Fix the pilot store path or metadata, then rerun doctor before bootstrap/deploy."
    if name == "smoke:streamlit":
        return "Inspect the smoke output and Streamlit startup logs before publishing a link."
    if name.startswith("git-tracked:"):
        return "Remove local runtime, secret, backup, database, log, archive, or oversized files from Git tracking."
    if name.startswith("render:"):
        return "Fix render.yaml so Render imports the intended Docker Web Service and persistent disk settings."
    if name.startswith("compose:") or name.startswith("dockerfile:") or name.startswith("runtime-deps:"):
        return "Fix the container runtime configuration, then rerun deployment preflight."
    if name.startswith("file:") or name.startswith("dockerignore:"):
        return "Restore the required deployment file or .dockerignore guardrail before publishing."
    return "Review this failed check and rerun preflight after fixing it."


def _readiness_summary(payload: dict[str, Any]) -> str:
    checks = payload["checks"]
    failed = [check for check in checks if check["status"] != "pass"]
    lines = [
        f"Deployment readiness: {payload['status'].upper()}",
        f"Checks: {len(checks) - len(failed)} passed, {len(failed)} failed",
    ]
    if not failed:
        lines.extend(
            [
                "",
                "Static deployment checks passed.",
                "Before Render deploy, also run:",
                "- python scripts\\preflight_internal_pilot_deploy.py --require-git-sync --summary",
                "- python scripts\\preflight_internal_pilot_deploy.py --require-github-private --summary",
                "Then follow docs\\PUBLIC_BETA_OWNER_GO_LIVE_STEPS.md for the short owner runbook,",
                "or docs\\PUBLIC_BETA_FIRST_LAUNCH_PLAYBOOK.md for the full GitHub/Render/Cloudflare playbook.",
            ]
        )
        return "\n".join(lines)

    lines.append("")
    lines.append("Failed checks:")
    for check in failed:
        lines.append(f"- {check['name']}: {check['message']}")
    lines.append("")
    lines.append("Next actions:")
    seen_actions: set[str] = set()
    for check in failed:
        action = _next_action_for_failed_check(check)
        if action in seen_actions:
            continue
        seen_actions.add(action)
        lines.append(f"- {action}")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-smoke", action="store_true", help="Start Streamlit and check health.")
    parser.add_argument(
        "--require-git-sync",
        action="store_true",
        help="Fail if the working tree is dirty or the current branch is not synchronized with its upstream.",
    )
    parser.add_argument(
        "--require-github-private",
        action="store_true",
        help="Fail unless remote.origin points to a GitHub repository whose gh-reported visibility is PRIVATE.",
    )
    parser.add_argument("--smoke-timeout-seconds", type=int, default=80)
    parser.add_argument(
        "--pilot-store-dir",
        help="Run pilot store doctor checks against this directory. Omit to skip runtime store checks.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument("--summary", action="store_true", help="Print a concise human-readable readiness summary.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    checks: list[dict[str, str]] = []
    _required_file_checks(checks)
    _dockerignore_checks(checks)
    _dockerfile_checks(checks)
    _runtime_dependency_checks(checks)
    _compose_checks(checks)
    _render_checks(checks)
    _git_tracked_safety_checks(checks)
    if args.require_git_sync:
        _git_sync_checks(checks)
    if args.require_github_private:
        _github_private_checks(checks)
    if args.pilot_store_dir:
        _pilot_store_doctor_checks(args.pilot_store_dir, checks)
    if args.run_smoke:
        _run_smoke(args.smoke_timeout_seconds, checks)

    failed = [check for check in checks if check["status"] != "pass"]
    payload = {"status": "pass" if not failed else "fail", "failed_count": len(failed), "checks": checks}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif args.summary:
        print(_readiness_summary(payload))
    else:
        for check in checks:
            print(f"[{check['status']}] {check['name']} - {check['message']}")
        print(f"preflight-{payload['status']} failed_count={payload['failed_count']}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
