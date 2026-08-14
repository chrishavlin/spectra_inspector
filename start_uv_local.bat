@echo off
rem Start the backend (FastAPI) and the frontend (Dash) with uv as detached
rem background processes, each writing its output to its own log file under
rem logs\ in the repository root.
rem
rem   start_uv_local.bat        starts the backend with 4 uvicorn workers
rem   start_uv_local.bat 8      starts the backend with 8 uvicorn workers
rem
rem Both processes keep running after this window is closed and survive a
rem remote desktop disconnect (but not a log off). Use stop_uv_local.bat to stop
rem them.

setlocal

rem %~dp0 is this script's directory, with a trailing backslash.
set "REPO_ROOT=%~dp0"
set "SERVER_DIR=%REPO_ROOT%packages\spectra_inspector_server"
set "FRONTEND_DIR=%REPO_ROOT%packages\spectra_inspector"
set "LOG_DIR=%REPO_ROOT%logs"

set "WORKERS=%~1"
if "%WORKERS%"=="" set "WORKERS=4"

set "SERVER_TITLE=spectra-inspector-server"
set "FRONTEND_TITLE=spectra-inspector-frontend"

rem When its output is redirected to a file, python encodes it with the legacy
rem Windows code page (cp1252) rather than utf-8, and the emoji in the fastapi
rem CLI banner raise UnicodeEncodeError. Both services inherit this.
set "PYTHONIOENCODING=utf-8"

where uv >nul 2>&1
if errorlevel 1 (
    echo uv was not found on PATH. See https://docs.astral.sh/uv/ to install it.
    exit /b 1
)

if not exist "%SERVER_DIR%\pyproject.toml" (
    echo Could not find %SERVER_DIR%. Run this script from the repository root.
    exit /b 1
)

if not exist "%SERVER_DIR%\.env" echo Warning: no .env in %SERVER_DIR%, the backend will use the packaged defaults.
if not exist "%FRONTEND_DIR%\.env" echo Warning: no .env in %FRONTEND_DIR%, the frontend will use the packaged defaults.

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

rem Each service is launched in its own minimized console window so that it is
rem detached from this one. The carets escape the redirection so that it is
rem performed by the new console rather than by this script.
echo Starting the backend with %WORKERS% workers, logging to %LOG_DIR%\server.log
start "%SERVER_TITLE%" /min /d "%SERVER_DIR%" cmd /c uv run fastapi run --workers %WORKERS% src\spectra_inspector_server\main.py ^> "%LOG_DIR%\server.log" 2^>^&1

rem Give the backend a head start so the first frontend page load finds it.
timeout /t 5 /nobreak >nul 2>nul

echo Starting the frontend, logging to %LOG_DIR%\frontend.log
start "%FRONTEND_TITLE%" /min /d "%FRONTEND_DIR%" cmd /c uv run python serve.py ^> "%LOG_DIR%\frontend.log" 2^>^&1

echo.
echo Frontend: http://127.0.0.1:8050
echo API docs: http://127.0.0.1:8000/docs
echo.
echo Logs:     %LOG_DIR%\server.log
echo           %LOG_DIR%\frontend.log
echo Stop with stop_uv_local.bat
