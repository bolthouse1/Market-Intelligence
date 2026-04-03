@echo off
cd /d C:\Market_Intelligence
call .venv\Scripts\activate
python -m src.cli scan
