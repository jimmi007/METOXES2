param(
    [string]$ProjectRoot = "C:\Users\anagn\PycharmProjects\ΜΕΤΟΧΕΣ2"
)

$ErrorActionPreference = "Stop"
$PatchRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupRoot = Join-Path $ProjectRoot ("_backup_v12_" + $Stamp)

$Files = @(
    "metoxes\routers\stock.py",
    "metoxes\services\sold_history_service.py",
    "metoxes\services\broker_history_debug_service.py",
    "metoxes\services\excel_service.py",
    "metoxes\services\candidate_research_service.py",
    "metoxes\services\dashboard_service.py",
    "metoxes\services\market_context_service.py",
    "metoxes\services\secondary_fundamentals_service.py",
    "metoxes\services\financial_sector_scoring_service.py",
    "metoxes\services\anomaly_detection_service.py",
    "metoxes\services\ai_commentary_service.py",
    "metoxes\services\scoring_services.py",
    "metoxes\services\absolute_quality_service.py",
    "metoxes\services\portfolio_metadata_service.py",
    "metoxes\services\forward_growth_service.py"
)

if (-not (Test-Path $ProjectRoot)) {
    throw "Project root not found: $ProjectRoot"
}

New-Item -ItemType Directory -Force -Path $BackupRoot | Out-Null

foreach ($Relative in $Files) {
    $Source = Join-Path $PatchRoot $Relative
    $Target = Join-Path $ProjectRoot $Relative

    if (-not (Test-Path $Source)) {
        throw "Patch file missing: $Source"
    }

    $TargetDir = Split-Path -Parent $Target
    New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null

    if (Test-Path $Target) {
        $Backup = Join-Path $BackupRoot $Relative
        $BackupDir = Split-Path -Parent $Backup
        New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
        Copy-Item $Target $Backup -Force
    }

    Copy-Item $Source $Target -Force
}

$InstalledStock = Join-Path $ProjectRoot "metoxes\routers\stock.py"
$StockText = Get-Content $InstalledStock -Raw

$Checks = @(
    "/stocks/enrichment-status",
    "/stocks/capital/realized",
    "safe_collect_capital_realized_history",
    "merge_realized_history_results",
    "V12-capital-sold-enrichment"
)

foreach ($Check in $Checks) {
    if ($StockText -notmatch [regex]::Escape($Check)) {
        throw "VERIFY FAILED: '$Check' was not found in installed stock.py"
    }
}

$UpdateCount = ([regex]::Matches($StockText, '@router\.post\("/stocks/update-excel"\)')).Count
if ($UpdateCount -ne 1) {
    throw "VERIFY FAILED: expected exactly 1 /stocks/update-excel route, found $UpdateCount"
}

Write-Host ""
Write-Host "METOXES2 V12 installed successfully." -ForegroundColor Green
Write-Host "Backup: $BackupRoot"
Write-Host "Verified routes:"
Write-Host "  GET  /stocks/enrichment-status"
Write-Host "  GET  /stocks/capital/realized"
Write-Host "  POST /stocks/update-excel"
Write-Host ""
Write-Host "Now fully restart FastAPI/Uvicorn and open /docs." -ForegroundColor Yellow
