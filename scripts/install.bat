@echo off
echo === 120VC Intel Scanner — Setup ===
cd /d %~dp0..

if not exist .venv (
    echo Creating virtual environment...
    python -m venv .venv
)

echo Activating venv...
call .venv\Scripts\activate

echo Installing dependencies...
pip install -r requirements.txt

if not exist .env (
    echo Creating .env from template...
    copy .env.example .env
    echo.
    echo !! IMPORTANT: Edit .env and add your API keys !!
    echo.
)

echo.
echo Setup complete. Run: python -m src.cli scan --dry-run
