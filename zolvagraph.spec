# -*- mode: python ; coding: utf-8 -*-
# Zolvagraph – Windows app (PyInstaller)
# Build:  build.bat   or   pyinstaller --noconfirm zolvagraph.spec

import sys
from pathlib import Path

block_cipher = None
root = Path(SPECPATH)

native_binaries = []
for name in ("zolvagraph_scan.dll", "libzolvagraph_scan.so", "libzolvagraph_scan.dylib"):
    for folder in (root / "native", root):
        cand = folder / name
        if cand.is_file():
            native_binaries.append((str(cand), "native"))
            break

a = Analysis(
    ["src/main.py"],
    pathex=[str(root / "src")],
    binaries=native_binaries,
    datas=[
        (str(root / "native" / "README.md"), "native"),
    ] if (root / "native" / "README.md").is_file() else [],
    hiddenimports=[
        "customtkinter",
        "PIL",
        "PIL.Image",
        "PIL.ImageTk",
        "PIL.ImageOps",
        "core",
        "core.carver",
        "core.disk_access",
        "core.recover",
        "core.scanner",
        "core.signatures",
        "core.ntfs",
        "core.image_formats",
        "core.media_recovery",
        "core.memory_capture",
        "core.native_scan",
        "core.forensics",
        "ui",
        "ui.main_window",
        "ui.results_view",
        "ui.widgets",
        "ui.dialogs",
        "utils",
        "utils.helpers",
        "psutil",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter.test",
        "unittest",
        "test",
        "pytest",
        "numpy",
        "scipy",
        "pandas",
        "matplotlib",
        "IPython",
        "notebook",
        "django",
        "flask",
        "tornado",
        "sqlalchemy",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

try:
    import customtkinter
    ctk_path = Path(customtkinter.__file__).parent
    a.datas += Tree(str(ctk_path), prefix="customtkinter")
except Exception:
    pass

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Zolvagraph",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=True,
    icon=str(root / "assets" / "icon.ico") if (root / "assets" / "icon.ico").is_file() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=["zolvagraph_scan.dll", "libzolvagraph_scan.so"],
    name="Zolvagraph",
)
