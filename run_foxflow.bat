@echo off
rem Start FoxFlow from this folder, preferring the project's virtual environment.
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m src.main
) else (
    python -m src.main
)
