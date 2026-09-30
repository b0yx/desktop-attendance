@echo off
REM ========================================================
REM  SmartHR Biometric Attendance System - Windows Packaging
REM  Produces a zero-console standalone executable (.exe)
REM ========================================================

echo ========================================================
echo  Building SmartHR Attendance Desktop Executable (.exe)
echo ========================================================

REM Step 1: Ensure Python is available
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not found in PATH. Please install Python 3.10+ and add it to PATH.
    pause
    exit /b 1
)

REM Step 2: Install dependencies
echo [1/3] Installing / Verifying requirements...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)

REM Step 3: Clean previous builds
echo [2/3] Cleaning previous build artifacts...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist SmartHR_Attendance.spec del /q SmartHR_Attendance.spec

REM Step 4: Run PyInstaller
echo [3/3] Compiling standalone Windows executable...
pyinstaller ^
    --noconsole ^
    --onefile ^
    --name="SmartHR_Attendance" ^
    --icon="assets/app_icon.ico" ^
    --add-data="assets;assets" ^
    --hidden-import="customtkinter" ^
    --hidden-import="PIL" ^
    --hidden-import="PIL._imagingtk" ^
    --hidden-import="PIL.ImageTk" ^
    --hidden-import="openpyxl" ^
    --hidden-import="pandas" ^
    --hidden-import="sqlite3" ^
    --collect-all="customtkinter" ^
    main.py

if %errorlevel% neq 0 (
    echo [ERROR] PyInstaller compilation failed!
    pause
    exit /b 1
)

echo.
echo ========================================================
echo  BUILD SUCCESSFUL!
echo  Executable location: dist\SmartHR_Attendance.exe
echo ========================================================
pause
