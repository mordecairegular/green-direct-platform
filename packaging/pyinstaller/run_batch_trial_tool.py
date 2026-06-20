"""PyInstaller launcher for the standalone batch trial GUI."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import traceback


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def main() -> None:
    base = _base_dir()
    os.chdir(base)
    src = base / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    os.environ.setdefault("PYTHONPATH", str(src))

    try:
        from green_direct.ui.batch_trial_gui import main as gui_main
        gui_main()
    except Exception:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "启动失败",
            f"程序启动时发生错误：\n\n{traceback.format_exc()}"
        )
        root.destroy()
        sys.exit(1)


if __name__ == "__main__":
    main()
