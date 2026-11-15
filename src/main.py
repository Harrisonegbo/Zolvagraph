#!/usr/bin/env python3
"""
Zolvagraph – Forensic File Recovery Tool
Windows desktop app entry point.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _prepare_paths() -> None:
    """Ensure imports work both from source and from a frozen .exe."""
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
        meipass = Path(getattr(sys, "_MEIPASS", base))
        os.chdir(base)
        for p in (base, base / "native", meipass, meipass / "native"):
            if p.is_dir():
                os.environ["PATH"] = str(p) + os.pathsep + os.environ.get("PATH", "")
    else:
        src = Path(__file__).resolve().parent
        if str(src) not in sys.path:
            sys.path.insert(0, str(src))


def main() -> None:
    _prepare_paths()

    try:
        import customtkinter as ctk
    except ImportError:
        print("Missing dependency: customtkinter")
        print("Install with:  pip install -r requirements.txt")
        sys.exit(1)

    try:
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")
    except Exception:
        pass

    from ui.main_window import MainWindow

    app = MainWindow()
    app.mainloop()


if __name__ == "__main__":
    main()
