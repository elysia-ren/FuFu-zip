@echo off
cd /d "%~dp0"
title FuFu-zip Build
echo ============================================
echo   FuFu-zip Build Tool
echo ============================================
echo.

REM [1/3] Install dependencies
echo [1/3] Installing dependencies...
pip install pyzipper pycryptodomex pyinstaller windnd >nul 2>&1
echo Done.
echo.

REM [2/3] Compile Cython core (show output)
echo [2/3] Compiling Cython core...
python build_core.py build_ext --inplace
if %errorlevel% neq 0 (
    echo WARNING: Cython compile failed, using pure Python fallback.
) else (
    echo Cython core compiled successfully.
)
echo.

REM [3/3] Build exe
echo [3/3] Building with PyInstaller...
if exist build rmdir /s /q build
if exist dist  rmdir /s /q dist

REM Find compiled Cython pyd
set CORE_PYD=
for %%f in (core*.pyd) do set "CORE_PYD=%%f"

REM Build the command dynamically
set "CMD=pyinstaller --onefile --windowed --name FuFu-zip --clean --noconfirm"
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
set "CMD=%CMD% --icon fufu.ico"
set "CMD=%CMD% --add-data fufu.ico;."
set "CMD=%CMD% zip_tool_modern_v1_0_0.py"

echo Executing: %CMD%
%CMD%

if %errorlevel% neq 0 (
    echo ERROR: Build failed.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   DONE! Output: dist\FuFu-zip.exe
echo ============================================
pause
start "" explorer /select,"dist\FuFu-zip.exe"