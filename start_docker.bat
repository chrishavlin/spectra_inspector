@echo off
setlocal

:: 1. Check if Docker is already running
docker info >nul 2>&1
if %errorlevel% equ 0 (
    echo Docker is already running.
    goto RUN_SCRIPT
)

echo Docker is not running. Resolving Docker Desktop path...

:: 2. Derive Docker Desktop.exe path relative to docker.exe CLI
for /f "delims=" %%I in ('powershell -NoProfile -Command ^
    "$cli = (Get-Command docker -ErrorAction SilentlyContinue).Source; if ($cli) { Join-Path (Split-Path (Split-Path $cli -Parent) -Parent) 'Docker Desktop.exe' }"'
) do set "DOCKER_PATH=%%I"

if not defined DOCKER_PATH (
    echo ERROR: Could not resolve Docker Desktop executable!
    exit /b 1
)

echo Starting Docker Desktop from: "%DOCKER_PATH%"
start "" "%DOCKER_PATH%"

:: 3. Wait until the daemon is fully initialized
echo Waiting for Docker engine to start...
:WAIT_DOCKER
timeout /t 3 /nobreak >nul
docker info >nul 2>&1
if %errorlevel% neq 0 (
    goto WAIT_DOCKER
)

echo Docker is up and running!

:RUN_SCRIPT
echo Running start_docker.ps1...
powershell -ExecutionPolicy Bypass -File "%~dp0start_docker.ps1"

endlocal
