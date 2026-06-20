"""PyInstaller launcher for the Streamlit application."""

from __future__ import annotations

import os
from pathlib import Path
import socket
import sys
import threading
import time
import webbrowser


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def _port_is_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
        return True


def _select_port(start: int = 8503, end: int = 8515) -> int:
    for port in range(start, end + 1):
        if _port_is_available(port):
            return port
    raise RuntimeError(f"No available localhost port found in {start}-{end}.")


def _open_browser_later(url: str) -> None:
    time.sleep(5)
    webbrowser.open(url)


def _configure_browser_path() -> None:
    if os.environ.get("BROWSER_PATH"):
        return
    candidates = [
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            os.environ["BROWSER_PATH"] = str(candidate)
            return


def main() -> None:
    base = _base_dir()
    src = base / "src"
    runtime_temp = base / ".runtime" / "tmp"
    runtime_temp.mkdir(parents=True, exist_ok=True)
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    os.environ.setdefault("PYTHONPATH", str(src))
    os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
    os.environ.setdefault("STREAMLIT_GLOBAL_DEVELOPMENT_MODE", "false")
    os.environ.setdefault("GREEN_DIRECT_ENABLE_RUNTIME_SNAPSHOT", "1")
    os.environ["TEMP"] = str(runtime_temp)
    os.environ["TMP"] = str(runtime_temp)
    os.environ["TMPDIR"] = str(runtime_temp)
    _configure_browser_path()

    app_path = src / "green_direct" / "ui" / "app.py"
    preferred_port = int(os.environ.get("GREEN_DIRECT_PORT", "8503"))
    port = _select_port(preferred_port, max(preferred_port, 8515))
    url = f"http://localhost:{port}"
    threading.Thread(target=_open_browser_later, args=(url,), daemon=True).start()

    from streamlit.web import bootstrap

    sys.argv = [
        "streamlit",
        "run",
        str(app_path),
        "--server.port",
        str(port),
        "--server.address",
        "localhost",
        "--server.headless",
        "true",
        "--browser.gatherUsageStats",
        "false",
        "--global.developmentMode",
        "false",
    ]
    bootstrap.run(str(app_path), False, [], {})


if __name__ == "__main__":
    main()
