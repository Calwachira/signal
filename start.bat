@echo off
cd /d "%~dp0"

if not exist .venv (
    echo Setting up for the first time, this takes a minute...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    pip install -r requirements.txt
) else (
    call .venv\Scripts\activate.bat
)

python run.py
pause