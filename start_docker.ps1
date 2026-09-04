# Build and start the app with docker compose. See start_docker.sh for what the
# two modes do.
#
#   ./start_docker.ps1            development (default)
#   ./start_docker.ps1 prod       deployment
param(
    [ValidateSet("dev", "prod")]
    [string]$Mode = "dev"
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$envFiles = @("packages/spectra_inspector/.env", "packages/spectra_inspector_server/.env")
foreach ($envFile in $envFiles) {
    if (-not (Test-Path $envFile)) {
        Write-Error "missing $envFile: copy the defaults.env next to it and edit"
    }
}
$compose = @("compose", "--env-file", $envFiles[0], "--env-file", $envFiles[1])

if ($Mode -eq "prod") {
    $compose += @("-f", "compose.yaml", "-f", "compose.prod.yaml")
    docker @compose up --build --detach
    docker @compose ps
    Write-Host "frontend listening on 127.0.0.1:8050 (loopback only). stop: ./stop_docker.ps1 prod"
} else {
    docker @compose up --build
}
