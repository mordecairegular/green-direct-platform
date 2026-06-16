"""Start the Streamlit app briefly and verify its health endpoint.

This is a pre-deployment smoke check for the internal pilot path. It starts the
app with pilot auth enabled, runtime snapshots disabled, and an isolated temp
pilot store, then polls Streamlit's health endpoint and shuts the process down.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "src" / "green_direct" / "ui" / "app.py"
SRC_PATH = ROOT / "src"


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


def _tail(path: Path, max_lines: int = 80) -> str:
    if not path.exists():
        return ""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-max_lines:])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=_positive_int, default=8517, help="Local port for the smoke app.")
    parser.add_argument(
        "--timeout-seconds",
        type=_positive_int,
        default=60,
        help="Maximum seconds to wait for Streamlit health.",
    )
    parser.add_argument(
        "--store-dir",
        type=Path,
        help="Pilot store directory. Defaults to a temporary directory that is deleted after the check.",
    )
    parser.add_argument("--keep-store", action="store_true", help="Keep the temporary pilot store after the check.")
    parser.add_argument(
        "--check-import-only",
        action="store_true",
        help="Only import the app module and exit; useful for fast CI checks.",
    )
    return parser


def _smoke_env(store_dir: Path, port: int) -> dict[str, str]:
    env = os.environ.copy()
    pythonpath = str(SRC_PATH)
    if env.get("PYTHONPATH"):
        pythonpath = pythonpath + os.pathsep + str(env["PYTHONPATH"])
    env.update(
        {
            "PYTHONPATH": pythonpath,
            "GREEN_DIRECT_ENABLE_PILOT_AUTH": "1",
            "GREEN_DIRECT_ENABLE_RUNTIME_SNAPSHOT": "0",
            "GREEN_DIRECT_PILOT_STORE_DIR": str(store_dir),
            "GREEN_DIRECT_MAX_UPLOAD_MB": env.get("GREEN_DIRECT_MAX_UPLOAD_MB", "20"),
            "GREEN_DIRECT_MAX_SCENARIOS_PER_RUN": env.get("GREEN_DIRECT_MAX_SCENARIOS_PER_RUN", "20000"),
            "PORT": str(port),
            "STREAMLIT_SERVER_ADDRESS": "127.0.0.1",
            "STREAMLIT_SERVER_PORT": str(port),
            "STREAMLIT_SERVER_HEADLESS": "true",
            "STREAMLIT_BROWSER_GATHER_USAGE_STATS": "false",
        }
    )
    return env


def _check_import(env: dict[str, str]) -> None:
    completed = subprocess.run(
        [sys.executable, "-c", "import green_direct.ui.app; print('import-ok')"],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    if "import-ok" not in completed.stdout:
        raise RuntimeError("Streamlit app import check did not print import-ok.")


def _health_ok(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return 200 <= int(response.status) < 300
    except (OSError, urllib.error.URLError):
        return False


def _stop_process(process: subprocess.Popen[object]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=8)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not APP_PATH.exists():
        raise SystemExit(f"Streamlit app not found: {APP_PATH}")

    temp_root = Path(tempfile.mkdtemp(prefix="green-direct-smoke-"))
    store_dir = args.store_dir or (temp_root / "pilot_store")
    log_dir = temp_root / "logs"
    store_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = log_dir / "streamlit.out.log"
    stderr_path = log_dir / "streamlit.err.log"
    env = _smoke_env(store_dir=store_dir, port=args.port)

    try:
        _check_import(env)
        if args.check_import_only:
            print("import-ok")
            return 0

        command = [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(APP_PATH),
            "--server.address=127.0.0.1",
            f"--server.port={args.port}",
            "--server.headless=true",
            "--browser.gatherUsageStats=false",
            f"--server.maxUploadSize={env['GREEN_DIRECT_MAX_UPLOAD_MB']}",
        ]
        with stdout_path.open("w", encoding="utf-8") as stdout_file, stderr_path.open(
            "w", encoding="utf-8"
        ) as stderr_file:
            process = subprocess.Popen(
                command,
                cwd=ROOT,
                env=env,
                stdout=stdout_file,
                stderr=stderr_file,
                text=True,
            )
            try:
                health_url = f"http://127.0.0.1:{args.port}/_stcore/health"
                deadline = time.monotonic() + args.timeout_seconds
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        break
                    if _health_ok(health_url):
                        print(f"streamlit-smoke-ok url=http://127.0.0.1:{args.port}")
                        return 0
                    time.sleep(0.75)

                print("streamlit-smoke-failed", file=sys.stderr)
                print(f"stdout log: {stdout_path}", file=sys.stderr)
                print(_tail(stdout_path), file=sys.stderr)
                print(f"stderr log: {stderr_path}", file=sys.stderr)
                print(_tail(stderr_path), file=sys.stderr)
                return 1
            finally:
                _stop_process(process)
    finally:
        if args.store_dir is None and not args.keep_store:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
