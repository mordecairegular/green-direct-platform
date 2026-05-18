"""PyInstaller launcher for the Streamlit application."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import webbrowser


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def main() -> None:
    base = _base_dir()
    src = base / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    os.environ.setdefault("PYTHONPATH", str(src))
    os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
    os.environ.setdefault("STREAMLIT_GLOBAL_DEVELOPMENT_MODE", "false")

    app_path = src / "green_direct" / "ui" / "app.py"
    port = int(os.environ.get("GREEN_DIRECT_PORT", "8501"))
    webbrowser.open(f"http://localhost:{port}")

    from streamlit.web import bootstrap

    sys.argv = [
        "streamlit",
        "run",
        str(app_path),
        "--server.port",
        str(port),
        "--global.developmentMode",
        "false",
    ]
    bootstrap.run(str(app_path), False, [], {})


if __name__ == "__main__":
    main()
