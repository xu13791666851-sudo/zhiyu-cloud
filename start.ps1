param(
    [switch]$WithProxy,
    [switch]$NoBuild
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  ZhiYu - Docker Compose startup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path ".env")) {
    Write-Host ".env was not found. Copying .env.example to .env..." -ForegroundColor Yellow
    Copy-Item ".env.example" ".env"
    Write-Host "Please edit .env with your API keys, then run this script again." -ForegroundColor Yellow
    exit 1
}

$composeArgs = @("compose")
if ($WithProxy) {
    $composeArgs += @("--profile", "proxy")
}
$composeArgs += @("up", "-d")
if (-not $NoBuild) {
    $composeArgs += "--build"
}

Write-Host "Starting services with: docker $($composeArgs -join ' ')" -ForegroundColor Yellow
& docker @composeArgs

Write-Host ""
Write-Host "Service status:" -ForegroundColor Green
& docker compose ps

Write-Host ""
Write-Host "Frontend:       http://localhost:3001" -ForegroundColor White
Write-Host "Backend health: http://localhost:8000/health" -ForegroundColor White
if ($WithProxy) {
    Write-Host "Proxy entry:    http://localhost:8080" -ForegroundColor White
}
Write-Host ""
Write-Host "Useful commands:" -ForegroundColor Gray
Write-Host "  docker compose logs -f backend"
Write-Host "  docker compose logs -f frontend"
Write-Host "  docker compose down"
