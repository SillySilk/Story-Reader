@echo off
cd /d "%~dp0"

echo ============================================================
echo  Story Reader Pro
echo ============================================================

:: Check Python is available
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python not found. Please install Python 3.10+ and add it to PATH.
    pause
    exit /b 1
)

:: Install / verify dependencies on first run or if requirements changed
echo Checking dependencies...
python -m pip install -r requirements.txt --quiet
if %errorlevel% neq 0 (
    echo.
    echo ERROR: Failed to install dependencies.
    echo Try running: python -m pip install -r requirements.txt
    pause
    exit /b 1
)

echo Starting Story Reader Pro...
echo.
python main.py

if %errorlevel% neq 0 (
    echo.
    echo ============================================================
    echo  CRITICAL ERROR: The application crashed.
    echo  Please review the error message above.
    echo ============================================================
    pause
)
