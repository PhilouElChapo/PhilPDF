@echo off
REM Lance PhilPDF depuis les sources (sans construire l'exe).
cd /d "%~dp0"
if not exist .venv (
    python -m venv .venv
    call .venv\Scripts\activate.bat
    pip install -r requirements.txt
) else (
    call .venv\Scripts\activate.bat
)
start "" .venv\Scripts\pythonw.exe philpdf.py %*
