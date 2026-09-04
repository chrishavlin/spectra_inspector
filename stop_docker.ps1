# Stop and remove the containers started by start_docker.ps1.
#
#   ./stop_docker.ps1             stop a development stack
#   ./stop_docker.ps1 prod        stop a deployment stack
param(
    [ValidateSet("dev", "prod")]
    [string]$Mode = "dev"
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$compose = @(
    "compose",
    "--env-file", "packages/spectra_inspector/.env",
    "--env-file", "packages/spectra_inspector_server/.env"
)
if ($Mode -eq "prod") {
    $compose += @("-f", "compose.yaml", "-f", "compose.prod.yaml")
}
docker @compose down
