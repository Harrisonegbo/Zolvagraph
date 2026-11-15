@echo off
REM ============================================================
REM  Zolvagraph – Build standalone Windows APP
REM  Requires: Windows 10/11, Python 3.10+
REM  Output:   dist\Zolvagraph\Zolvagraph.exe  (portable folder)
REM ============================================================
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo.
echo  ========================================
echo   Zolvagraph  Windows App Builder
echo  ========================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found on PATH. Install Python 3.10+ and retry.
    pause
    exit /b 1
)

if not exist "venv\" (
    echo [1/5] Creating virtual environment...
    python -m venv venv
) else (
    echo [1/5] Using existing venv...
)

call venv\Scripts\activate.bat

echo [2/5] Installing dependencies...
python -m pip install -q --upgrade pip
pip install -q -r requirements.txt
pip install -q pyinstaller

echo [3/5] Building native C scan engine (optional, for speed)...
if exist "native\scan_engine.c" (
    where gcc >nul 2>&1
    if not errorlevel 1 (
        gcc -O3 -shared -o native\zolvagraph_scan.dll native\scan_engine.c 2>nul
        if exist "native\zolvagraph_scan.dll" (
            echo       Native DLL built: native\zolvagraph_scan.dll
        ) else (
            echo       Native build skipped/failed – Python fallback will be used.
        )
    ) else (
        echo       GCC not found – skipping native engine (still works in pure Python).
    )
) else (
    echo       No native sources found.
)

echo [4/5] Running PyInstaller...
if exist "build" rmdir /s /q build 2>nul
pyinstaller --noconfirm --clean zolvagraph.spec
if errorlevel 1 (
    echo.
    echo BUILD FAILED
    pause
    exit /b 1
)

echo [5/5] Packaging portable app folder...
if not exist "dist\Zolvagraph\native" mkdir "dist\Zolvagraph\native"
if exist "native\zolvagraph_scan.dll" copy /Y "native\zolvagraph_scan.dll" "dist\Zolvagraph\native\" >nul
if exist "native\libzolvagraph_scan.so" copy /Y "native\libzolvagraph_scan.so" "dist\Zolvagraph\native\" >nul
if exist "tools" xcopy /E /I /Y "tools" "dist\Zolvagraph\tools\" >nul

(
echo @echo off
echo cd /d "%%~dp0"
echo start "" "Zolvagraph.exe"
) > "dist\Zolvagraph\Launch Zolvagraph.bat"

echo.
echo  ========================================
echo   BUILD COMPLETE
echo  ========================================
echo.
echo   App folder:  dist\Zolvagraph\
echo   Executable:  dist\Zolvagraph\Zolvagraph.exe
echo.
echo   Distribute the whole Zolvagraph folder (or zip it).
echo   Users: right-click Zolvagraph.exe -^> Run as administrator
echo.
pause
