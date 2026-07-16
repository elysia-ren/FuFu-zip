@echo off
cd /d "%~dp0"
title FuFu-zip Installer Build
echo ============================================
echo   FuFu-zip Installer Build
echo ============================================
echo.

echo [1/3] Installing dependencies...
pip install pyzipper pycryptodomex cython setuptools pyinstaller windnd >nul 2>&1
echo Done.
echo.

echo [2/3] Compiling Cython core...
python build_core.py build_ext --inplace
if %errorlevel% neq 0 (
    echo WARNING: Cython compile failed, using pure Python fallback.
)
echo.

echo [3/3] Building with PyInstaller (onedir)...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

set "CMD=pyinstaller --onedir --windowed --name FuFu-zip --clean --noconfirm"
set "CMD=%CMD% --collect-all Cryptodome"
set "CMD=%CMD% --collect-all pyzipper"
set "CMD=%CMD% --collect-all windnd"
if defined CORE_PYD set "CMD=%CMD% --add-binary "%CORE_PYD%;.""
set "CMD=%CMD% --hidden-import tkinter"
set "CMD=%CMD% --hidden-import tkinter.ttk"
set "CMD=%CMD% --hidden-import tkinter.filedialog"
set "CMD=%CMD% --hidden-import tkinter.messagebox"
set "CMD=%CMD% --hidden-import tkinter.scrolledtext"
set "CMD=%CMD% --exclude-module unittest"
set "CMD=%CMD% --exclude-module test"
set "CMD=%CMD% --exclude-module xml"
set "CMD=%CMD% --exclude-module pydoc"
set "CMD=%CMD% --exclude-module doctest"
set "CMD=%CMD% --exclude-module pdb"
set "CMD=%CMD% --exclude-module lib2to3"
set "CMD=%CMD% --exclude-module ensurepip"
if exist fufu.ico (
    set "CMD=%CMD% --icon fufu.ico"
    set "CMD=%CMD% --add-data fufu.ico;."
)
set "CORE_PYD="
for %%f in (core*.pyd) do set "CORE_PYD=%%f"
if defined CORE_PYD set "CMD=%CMD% --add-binary %CORE_PYD%;."
set "CMD=%CMD% zip_tool_modern_v1_0_0.py"

%CMD%

if %errorlevel% neq 0 (
    echo ERROR: PyInstaller build failed.
    pause
    exit /b 1
)

echo.
echo PyInstaller build done.
echo.

REM Copy icon to dist directory for Inno Setup
if exist fufu.ico copy fufu.ico dist\FuFu-zip\fufu.ico >nul

REM Check if Inno Setup is installed
set "ISCC="
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"

if not defined ISCC (
    echo ============================================
    echo   Inno Setup not found!
    echo   Please install Inno Setup 6 from:
    echo   https://jrsoftware.org/isinfo.php
    echo   Then run this script again.
    echo ============================================
    echo   Or manually: open installer.iss in Inno Setup
    echo ============================================
    pause
    exit /b 1
)

echo Building installer with Inno Setup...
"%ISCC%" installer.iss

if %errorlevel% neq 0 (
    echo ERROR: Inno Setup build failed.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   DONE!
echo   Installer: installer_output\FuFu-zip-v1.1.0-Setup.exe
echo ============================================
pause
start "" explorer /select,"installer_output\FuFu-zip-v1.1.0-Setup.exe"
