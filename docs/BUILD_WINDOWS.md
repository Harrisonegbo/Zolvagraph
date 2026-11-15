# Build Zolvagraph on Windows

Step-by-step instructions to produce a portable **Windows 10/11** app (`Zolvagraph.exe`).

---

## Requirements

| Item | Notes |
|------|--------|
| **OS** | Windows 10 or Windows 11 (64-bit recommended) |
| **Python** | [Python 3.10+](https://www.python.org/downloads/) — during setup, check **“Add python.exe to PATH”** |
| **Disk space** | ~1 GB free (venv + PyInstaller build) |
| **Optional: GCC** | [MinGW-w64](https://www.mingw-w64.org/) or MSYS2 — builds the native C scan engine for faster carving |

Administrator rights are **not** required to *build*. They are required when *running* the app against live disks.

---

## Method A — One-click build (recommended)

1. Clone or download the source:
   ```bat
   git clone https://github.com/Harrisonegbo/Zolvagraph.git
   cd Zolvagraph
   ```
2. Double-click **`build.bat`**  
   (or from Command Prompt / PowerShell: `build.bat`)
3. Wait until you see **BUILD COMPLETE**.
4. Open the output folder:
   ```
   dist\Zolvagraph\
   ```
5. Run **`Zolvagraph.exe`** (right-click → **Run as administrator** for full disk access).

### What `build.bat` does

1. Creates a local `venv\` if missing  
2. Installs dependencies from `requirements.txt` + PyInstaller  
3. Optionally compiles `native\zolvagraph_scan.dll` if `gcc` is on PATH  
4. Runs PyInstaller with `zolvagraph.spec`  
5. Copies native libs and tools into `dist\Zolvagraph\`

---

## Method B — Manual build

```bat
cd Zolvagraph

python -m venv venv
venv\Scripts\activate.bat

python -m pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller

REM Optional native scanner (faster signature carving)
gcc -O3 -shared -o native\zolvagraph_scan.dll native\scan_engine.c

pyinstaller --noconfirm --clean zolvagraph.spec

REM Copy native DLL next to the app if built
if exist native\zolvagraph_scan.dll (
  mkdir dist\Zolvagraph\native 2>nul
  copy /Y native\zolvagraph_scan.dll dist\Zolvagraph\native\
)
```

Output:

```
dist\Zolvagraph\Zolvagraph.exe
dist\Zolvagraph\Launch Zolvagraph.bat
dist\Zolvagraph\...          (dependencies)
```

---

## Method C — Run from source (no .exe)

Useful for development:

```bat
cd Zolvagraph
python -m venv venv
venv\Scripts\activate.bat
pip install -r requirements.txt
python src\main.py
```

Or:

```bat
run.bat
```

---

## Native C scan engine (optional but recommended)

Without the DLL, Zolvagraph still works using pure Python (`bytes.find`).  
With **`zolvagraph_scan.dll`**, multi-signature carving uses the optimized C engine (SSE2 / BMH).

### Install GCC on Windows

**Option 1 — MSYS2**

1. Install from https://www.msys2.org/  
2. In MSYS2 UCRT64 terminal:
   ```bash
   pacman -S mingw-w64-ucrt-x86_64-gcc
   ```
3. Add to PATH, e.g.:
   ```
   C:\msys64\ucrt64\bin
   ```
4. Verify:
   ```bat
   gcc --version
   ```

**Option 2 — winlibs / MinGW-w64 zip**  
Download a prebuilt MinGW-w64 toolchain, extract, add its `bin` folder to PATH.

Then re-run `build.bat` or the `gcc` command in Method B.

---

## Distribute the app

1. Zip the **entire** folder:
   ```
   dist\Zolvagraph\
   ```
2. Name it e.g. `Zolvagraph-Windows-x64.zip`
3. Users unzip anywhere and run `Zolvagraph.exe`  
   **No Python install required** on their machine.

Do **not** distribute only the single `.exe` without the accompanying files in that folder (onedir layout).

### Optional: GitHub Release

```bat
git tag v1.0.0
git push origin v1.0.0
```

Attach the zip to the release notes on GitHub.

---

## Run-time notes

| Topic | Guidance |
|--------|-----------|
| **Admin** | Required for `\\.\C:`, physical drives, and some memory tools |
| **Windows Defender** | First launch of a new unsigned build may be scanned or blocked; allow if you trust the build |
| **Destination** | Always recover to a **different** drive than the one you scan |
| **Console** | The packaged app is windowed (`console=False`); no black console window |

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `python` not found | Reinstall Python and enable **Add to PATH**, or use the full path to `python.exe` |
| PyInstaller fails on customtkinter | Ensure `pip install customtkinter` succeeded inside the venv |
| App starts but native engine not used | Confirm `dist\Zolvagraph\native\zolvagraph_scan.dll` exists; rebuild with GCC |
| Access denied on disk | Run as Administrator; close apps locking the volume |
| Build is very slow | Normal for first PyInstaller run; later builds are faster |

---

## Project files involved

| File | Role |
|------|------|
| `build.bat` | Automated Windows build |
| `zolvagraph.spec` | PyInstaller recipe (GUI, UAC admin, native bundle) |
| `requirements.txt` | Python dependencies |
| `native/scan_engine.c` | C scan engine source |
| `src/main.py` | App entry point |
