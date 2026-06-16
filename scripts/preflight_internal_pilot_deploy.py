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


REQUIRED_FILES = (
    ".dockerignore",
    ".env.example",
    "Dockerfile",
    "README_DEPLOY.md",
    "SECURITY.md",
    "docker-compose.yml",
    "render.yaml",
    "requirements-runtime.txt",
    "docs/MANAGED_PUBLIC_BETA_DEPLOYMENT.md",
    "docs/MOBILE_NETWORK_TRIAL_CHECKLIST.md",
    "docs/PUBLIC_BETA_DEPLOYMENT_AUDIT.md",
    "scripts/smoke_streamlit_app.py",
)

DOCKERIGNORE_REQUIRED_PATTERNS = (
    ".env",
    ".env.*",
    "!.env.example",
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
    "PYTHONPATH": "/app/src",
}


def _check(condition: bool, checks: list[dict[str, str]], name: str, message: str) -> None:
    checks.append({"name": name, "status": "pass" if condition else "fail", "message": message})


def _load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


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
        "PORT=8503",
        "USER appuser",
        "_stcore/health",
        "--server.port=${PORT",
    )
    for needle in expected:
        _check(needle in text, checks, f"dockerfile:{needle}", f"Dockerfile contains {needle}")


def _compose_checks(checks: list[dict[str, str]]) -> None:
    try:
        compose = _load_yaml(ROOT / "docker-compose.yml")
        service = compose["services"]["green-direct"]
        environment = service["environment"]
    except Exception as exc:  # noqa: BLE001 - report preflight parse failure
        _check(False, checks, "compose:parse", f"docker-compose.yml parse failed: {exc}")
        return

    expected_env = {
        "GREEN_DIRECT_ENABLE_PILOT_AUTH": "1",
        "GREEN_DIRECT_ENABLE_RUNTIME_SNAPSHOT": "0",
        "GREEN_DIRECT_PILOT_STORE_DIR": "/data/pilot_store",
        "PORT": "8503",
    }
    for key, expected in expected_env.items():
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


def _render_checks(checks: list[dict[str, str]]) -> None:
    try:
        render = _load_yaml(ROOT / "render.yaml")
        service = render["services"][0]
    except Exception as exc:  # noqa: BLE001 - report preflight parse failure
        _check(False, checks, "render:parse", f"render.yaml parse failed: {exc}")
        return

    _check(service.get("runtime") == "docker", checks, "render:runtime", "Render service uses Docker runtime")
    _check(service.get("dockerfilePath") == "./Dockerfile", checks, "render:dockerfile", "Render uses root Dockerfile")
    _check(service.get("healthCheckPath") == "/_stcore/health", checks, "render:health", "Render health path is Streamlit health")
    disk = service.get("disk") or {}
    _check(disk.get("mountPath") == "/data", checks, "render:disk", "Render persistent disk mounts at /data")
    env = {item["key"]: str(item["value"]) for item in service.get("envVars", [])}
    for key, expected in RENDER_REQUIRED_ENV.items():
        _check(env.get(key) == expected, checks, f"render:env:{key}", f"{key} defaults to {expected}")
    _check(env.get("PORT") is not None, checks, "render:env:PORT", "Render declares PORT")


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-smoke", action="store_true", help="Start Streamlit and check health.")
    parser.add_argument("--smoke-timeout-seconds", type=int, default=80)
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    checks: list[dict[str, str]] = []
    _required_file_checks(checks)
    _dockerignore_checks(checks)
    _dockerfile_checks(checks)
    _compose_checks(checks)
    _render_checks(checks)
    if args.run_smoke:
        _run_smoke(args.smoke_timeout_seconds, checks)

    failed = [check for check in checks if check["status"] != "pass"]
    payload = {"status": "pass" if not failed else "fail", "failed_count": len(failed), "checks": checks}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for check in checks:
            print(f"[{check['status']}] {check['name']} - {check['message']}")
        print(f"preflight-{payload['status']} failed_count={payload['failed_count']}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
