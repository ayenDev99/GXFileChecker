@echo off

REM If folder exists, go there. Otherwise use script location.
if exist "C:\GXFileChecker" (
    cd /d "C:\GXFileChecker"
) else (
    cd /d "%~dp0"
)

echo Installing Streamlit...
python -m pip install --upgrade pip
python -m pip install streamlit

if %errorlevel% neq 0 (
    echo Installation failed.
    pause
    exit /b
)

echo Starting Streamlit app...
python -m streamlit run file_checker_app.py

pause