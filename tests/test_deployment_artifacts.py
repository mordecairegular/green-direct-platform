from pathlib import Path
import subprocess
import sys

import yaml


ROOT = Path(__file__).resolve().parents[1]


def _load_preflight_module():
    import importlib.util

    path = ROOT / "scripts" / "preflight_internal_pilot_deploy.py"
    spec = importlib.util.spec_from_file_location("preflight_internal_pilot_deploy", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_preflight_parses_github_remote_slug():
    preflight = _load_preflight_module()

    assert preflight._github_repo_slug_from_remote("https://github.com/acme/green-direct.git") == "acme/green-direct"
    assert preflight._github_repo_slug_from_remote("git@github.com:acme/green-direct.git") == "acme/green-direct"
    assert preflight._github_repo_slug_from_remote("https://gitlab.com/acme/green-direct.git") is None


def test_docker_compose_defaults_to_internal_pilot_safety():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    service = compose["services"]["green-direct"]
    environment = service["environment"]

    assert environment["GREEN_DIRECT_ENABLE_PILOT_AUTH"] == "1"
    assert environment["GREEN_DIRECT_ENABLE_RUNTIME_SNAPSHOT"] == "0"
    assert environment["GREEN_DIRECT_PILOT_STORE_DIR"] == "/data/pilot_store"
    assert environment["GREEN_DIRECT_MAX_UPLOAD_MB"] == "${GREEN_DIRECT_MAX_UPLOAD_MB:-20}"
    assert environment["GREEN_DIRECT_MAX_SCENARIOS_PER_RUN"] == "${GREEN_DIRECT_MAX_SCENARIOS_PER_RUN:-20000}"
    assert environment["GREEN_DIRECT_DEFAULT_PARALLEL_WORKERS"] == "${GREEN_DIRECT_DEFAULT_PARALLEL_WORKERS:-1}"
    assert environment["GREEN_DIRECT_ECONOMY_CASHFLOW_RETENTION_THRESHOLD"] == (
        "${GREEN_DIRECT_ECONOMY_CASHFLOW_RETENTION_THRESHOLD:-1000}"
    )
    assert environment["GREEN_DIRECT_ECONOMY_RETAINED_CASHFLOW_LIMIT"] == (
        "${GREEN_DIRECT_ECONOMY_RETAINED_CASHFLOW_LIMIT:-20}"
    )
    assert environment["BROWSER_PATH"] == "/usr/bin/chromium"
    assert environment["STREAMLIT_SERVER_ADDRESS"] == "0.0.0.0"
    assert environment["STREAMLIT_SERVER_PORT"] == "8503"
    assert environment["STREAMLIT_SERVER_HEADLESS"] == "true"
    assert environment["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] == "false"
    assert environment["PYTHONPATH"] == "/app/src"
    assert "green_direct_pilot_store:/data/pilot_store" in service["volumes"]
    assert compose["volumes"]["green_direct_pilot_store"]["name"] == "green_direct_pilot_store"
    assert service["ports"] == ["8503:8503"]
    worker_environment = compose["services"]["green-direct-worker"]["environment"]
    assert worker_environment["GREEN_DIRECT_ENABLE_PILOT_AUTH"] == "1"
    assert worker_environment["GREEN_DIRECT_ENABLE_RUNTIME_SNAPSHOT"] == "0"
    assert worker_environment["GREEN_DIRECT_PILOT_STORE_DIR"] == "/data/pilot_store"
    assert worker_environment["BROWSER_PATH"] == "/usr/bin/chromium"
    assert worker_environment["PYTHONPATH"] == "/app/src"
    worker_command = compose["services"]["green-direct-worker"]["command"]
    assert "technical_study" in worker_command
    assert "economic_study" in worker_command


def test_dockerfile_defaults_to_safe_server_mode():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "GREEN_DIRECT_ENABLE_PILOT_AUTH=1" in dockerfile
    assert "GREEN_DIRECT_ENABLE_RUNTIME_SNAPSHOT=0" in dockerfile
    assert "GREEN_DIRECT_PILOT_STORE_DIR=/data/pilot_store" in dockerfile
    assert "GREEN_DIRECT_MAX_SCENARIOS_PER_RUN=20000" in dockerfile
    assert "GREEN_DIRECT_DEFAULT_PARALLEL_WORKERS=1" in dockerfile
    assert "GREEN_DIRECT_ECONOMY_CASHFLOW_RETENTION_THRESHOLD=1000" in dockerfile
    assert "GREEN_DIRECT_ECONOMY_RETAINED_CASHFLOW_LIMIT=20" in dockerfile
    assert "BROWSER_PATH=/usr/bin/chromium" in dockerfile
    assert "streamlit" in dockerfile
    assert "_stcore/health" in dockerfile
    assert "USER appuser" in dockerfile
    assert "COPY requirements-runtime.txt ./" in dockerfile
    assert "pip install --no-cache-dir -r requirements-runtime.txt" in dockerfile
    assert "--server.maxUploadSize=${STREAMLIT_SERVER_MAX_UPLOAD_SIZE:-${GREEN_DIRECT_MAX_UPLOAD_MB:-20}}" in dockerfile


def test_dockerignore_excludes_local_state_and_secrets():
    ignored = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()

    for pattern in [".env", ".env.*", ".github/", ".runtime/", ".venv/", "outputs/", "*.log"]:
        assert pattern in ignored
    assert "!.env.example" in ignored


def test_render_blueprint_targets_pilot_branch_after_checks_pass():
    render = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))
    service = render["services"][0]

    assert service["runtime"] == "docker"
    assert service["branch"] == "codex/UI"
    assert service["numInstances"] == 1
    assert service["autoDeployTrigger"] == "checksPass"
    assert service["healthCheckPath"] == "/_stcore/health"
    assert service["disk"]["name"] == "green-direct-pilot-store"
    assert service["disk"]["mountPath"] == "/data"
    assert service["disk"]["sizeGB"] >= 10
    env = {item["key"]: str(item["value"]) for item in service["envVars"]}
    assert env["GREEN_DIRECT_MAX_UPLOAD_MB"] == "20"
    assert env["GREEN_DIRECT_DEFAULT_PARALLEL_WORKERS"] == "1"
    assert env["STREAMLIT_SERVER_ADDRESS"] == "0.0.0.0"
    assert env["STREAMLIT_SERVER_PORT"] == "8503"
    assert env["STREAMLIT_SERVER_HEADLESS"] == "true"
    assert env["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] == "false"
    assert env["PORT"] == "8503"
    assert env["BROWSER_PATH"] == "/usr/bin/chromium"


def test_github_actions_quality_gate_exists():
    workflow = (ROOT / ".github" / "workflows" / "internal-pilot-quality.yml").read_text(encoding="utf-8")

    assert "Internal Pilot Quality Gate" in workflow
    assert "python -m compileall -q src scripts tests" in workflow
    assert "python scripts/preflight_internal_pilot_deploy.py --json" in workflow
    assert 'python scripts/preflight_internal_pilot_deploy.py --pilot-store-dir "$RUNNER_TEMP/green-direct-pilot-store" --json' in workflow
    assert "python -m pytest -q" in workflow
    assert "python scripts/smoke_streamlit_app.py --timeout-seconds 80" in workflow


def test_streamlit_smoke_script_import_check_runs():
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "smoke_streamlit_app.py"),
            "--check-import-only",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "import-ok" in completed.stdout


def test_internal_pilot_preflight_runs_static_checks_json():
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "preflight_internal_pilot_deploy.py"),
            "--json",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = yaml.safe_load(completed.stdout)
    assert payload["status"] == "pass"
    assert payload["failed_count"] == 0
    check_names = {check["name"] for check in payload["checks"]}
    assert "file:.github/workflows/internal-pilot-quality.yml" in check_names
    assert "file:docs/INTERNAL_PILOT_DEPLOYMENT_RUNBOOK.md" in check_names
    assert "file:docs/PUBLIC_BETA_OWNER_GO_LIVE_STEPS.md" in check_names
    assert "file:docs/PUBLIC_BETA_FIRST_LAUNCH_PLAYBOOK.md" in check_names
    assert "file:scripts/backup_pilot_store.ps1" in check_names
    assert "file:scripts/restore_pilot_store.ps1" in check_names
    assert "dockerignore:.github/" in check_names
    assert "runtime-deps:pyproject-sync" in check_names
    assert "render:runtime" in check_names
    assert "render:branch" in check_names
    assert "render:auto-deploy" in check_names
    assert "render:instances" in check_names
    assert "render:disk-name" in check_names
    assert "render:disk-size" in check_names
    assert "compose:volume" in check_names
    assert "compose:env:GREEN_DIRECT_MAX_UPLOAD_MB" in check_names
    assert "compose:env:GREEN_DIRECT_DEFAULT_PARALLEL_WORKERS" in check_names
    assert "compose:env:STREAMLIT_SERVER_HEADLESS" in check_names
    assert "compose:env:BROWSER_PATH" in check_names
    assert "compose:worker-env:GREEN_DIRECT_PILOT_STORE_DIR" in check_names
    assert "compose:worker-env:BROWSER_PATH" in check_names
    assert "compose:worker-job-types" in check_names
    assert "dockerfile:PORT=8503" in check_names
    assert "dockerfile:GREEN_DIRECT_DEFAULT_PARALLEL_WORKERS=1" in check_names
    assert "dockerfile:--server.maxUploadSize=${STREAMLIT_SERVER_MAX_UPLOAD_SIZE:-${GREEN_DIRECT_MAX_UPLOAD_MB:-20}}" in check_names
    assert "render:env:STREAMLIT_SERVER_HEADLESS" in check_names
    assert "render:env:GREEN_DIRECT_DEFAULT_PARALLEL_WORKERS" in check_names
    assert "render:env:BROWSER_PATH" in check_names
    assert "git-tracked:env-files" in check_names
    assert "git-tracked:local-state" in check_names
    assert "git-tracked:secret-payloads" in check_names
    assert "git-tracked:size" in check_names


def test_internal_pilot_preflight_summary_reports_static_readiness():
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "preflight_internal_pilot_deploy.py"),
            "--summary",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "Deployment readiness: PASS" in completed.stdout
    assert "Static deployment checks passed." in completed.stdout
    assert "--require-git-sync --summary" in completed.stdout
    assert "PUBLIC_BETA_OWNER_GO_LIVE_STEPS.md" in completed.stdout
    assert "PUBLIC_BETA_FIRST_LAUNCH_PLAYBOOK.md" in completed.stdout


def test_internal_pilot_preflight_summary_explains_git_sync_failure():
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "preflight_internal_pilot_deploy.py"),
            "--require-git-sync",
            "--summary",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    assert "Deployment readiness: FAIL" in completed.stdout
    assert "git:sync" in completed.stdout
    assert "git push origin codex/UI" in completed.stdout


def test_internal_pilot_preflight_can_run_pilot_store_doctor(tmp_path):
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "preflight_internal_pilot_deploy.py"),
            "--pilot-store-dir",
            str(tmp_path),
            "--json",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = yaml.safe_load(completed.stdout)
    assert payload["status"] == "pass"
    check_names = {check["name"] for check in payload["checks"]}
    assert "pilot-store:doctor" in check_names
    assert "pilot-store:lock" in check_names
    assert "pilot-store:json_metadata" in check_names


def test_internal_pilot_preflight_fails_on_corrupt_pilot_store_metadata(tmp_path):
    bad_path = tmp_path / "auth" / "credentials" / "broken.json"
    bad_path.parent.mkdir(parents=True)
    bad_path.write_text("{not json", encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "preflight_internal_pilot_deploy.py"),
            "--pilot-store-dir",
            str(tmp_path),
            "--json",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    payload = yaml.safe_load(completed.stdout)
    assert completed.returncode == 1
    assert payload["status"] == "fail"
    assert any(
        check["name"] == "pilot-store:json_metadata" and check["status"] == "fail"
        for check in payload["checks"]
    )


def test_internal_pilot_preflight_exposes_git_sync_check():
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "preflight_internal_pilot_deploy.py"),
            "--help",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "--require-git-sync" in completed.stdout
    assert "--require-github-private" in completed.stdout
    assert "--summary" in completed.stdout
    assert "--pilot-store-dir" in completed.stdout
    script = (ROOT / "scripts" / "preflight_internal_pilot_deploy.py").read_text(encoding="utf-8")
    assert "git:branch" in script
    assert "git:render-branch" in script
    assert "git:upstream-branch" in script
    assert "github:origin" in script
    assert "github:visibility" in script
    assert "git-tracked:env-files" in script
    assert "git-tracked:local-state" in script
    assert "git-tracked:secret-payloads" in script
    assert "git-tracked:size" in script


def test_public_beta_first_launch_playbook_covers_handoff_steps():
    playbook = (ROOT / "docs" / "PUBLIC_BETA_FIRST_LAUNCH_PLAYBOOK.md").read_text(encoding="utf-8")

    for needle in [
        "git push origin codex/UI",
        "preflight_internal_pilot_deploy.py --require-git-sync",
        "preflight_internal_pilot_deploy.py --require-git-sync --summary",
        "preflight_internal_pilot_deploy.py --require-github-private --summary",
        "preflight_internal_pilot_deploy.py --require-github-private",
        "Internal Pilot Quality Gate",
        "GREEN_DIRECT_DEFAULT_PARALLEL_WORKERS=1",
        "Render Web Service Shell",
        "pilot-admin doctor",
        "pilot-admin bootstrap",
        "green-direct-pilot-store-first-launch.tgz",
        "pilot_store_restore_check",
        "backup_pilot_store.ps1",
        "restore_pilot_store.ps1",
        "Cloudflare Zero Trust Access",
        "手机 4G/5G",
        "GREEN_DIRECT_ENABLE_PILOT_AUTH=1",
        "GREEN_DIRECT_ENABLE_RUNTIME_SNAPSHOT=0",
    ]:
        assert needle in playbook


def test_public_beta_owner_go_live_steps_covers_short_path():
    steps = (ROOT / "docs" / "PUBLIC_BETA_OWNER_GO_LIVE_STEPS.md").read_text(encoding="utf-8")

    for needle in [
        "preflight_internal_pilot_deploy.py --summary",
        "preflight_internal_pilot_deploy.py --require-git-sync --summary",
        "git push origin codex/UI",
        "Internal Pilot Quality Gate",
        "Render Docker Web Service",
        "green-direct-pilot-store",
        "GREEN_DIRECT_ENABLE_PILOT_AUTH=1",
        "GREEN_DIRECT_ENABLE_RUNTIME_SNAPSHOT=0",
        "pilot-admin doctor",
        "pilot-admin bootstrap",
        "Cloudflare",
        "手机 4G/5G",
        "release/GreenDirectLocalTrial_20260617.zip",
    ]:
        assert needle in steps
