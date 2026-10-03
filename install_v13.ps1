param(
    [string]$ProjectRoot = "C:\Users\anagn\PycharmProjects\ΜΕΤΟΧΕΣ2"
)

$ErrorActionPreference = "Stop"
$PatchRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupRoot = Join-Path $ProjectRoot ("_backup_v13_" + $Stamp)

# V13 intentionally touches only the router build marker/status and the
# Trading212 history-debug parser. All V12 Capital/Sold/AI code stays intact.
$Files = @(
    "metoxes\routers\stock.py",
    "metoxes\services\broker_history_debug_service.py"
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
$InstalledDebug = Join-Path $ProjectRoot "metoxes\services\broker_history_debug_service.py"
$StockText = Get-Content $InstalledStock -Raw
$DebugText = Get-Content $InstalledDebug -Raw

$StockChecks = @(
    "/stocks/enrichment-status",
    "/stocks/capital/realized",
    "/stocks/trading212/history-debug",
    "V13-trading212-nested-history-debug"
)
foreach ($Check in $StockChecks) {
    if ($StockText -notmatch [regex]::Escape($Check)) {
        throw "VERIFY FAILED in stock.py: '$Check' not found"
    }
}

$DebugChecks = @(
    'item.get("order")',
    'item.get("fill")',
    '"order_keys"',
    '"fill_keys"',
    '"side_counts"'
)
foreach ($Check in $DebugChecks) {
    if ($DebugText -notmatch [regex]::Escape($Check)) {
        throw "VERIFY FAILED in broker_history_debug_service.py: '$Check' not found"
    }
}

$UpdateCount = ([regex]::Matches($StockText, '@router\.post\("/stocks/update-excel"\)')).Count
if ($UpdateCount -ne 1) {
    throw "VERIFY FAILED: expected exactly 1 /stocks/update-excel route, found $UpdateCount"
}

Write-Host ""
Write-Host "METOXES2 V13 installed successfully." -ForegroundColor Green
Write-Host "Backup: $BackupRoot"
Write-Host "Trading212 nested order/fill parser verified."
Write-Host ""
Write-Host "Now fully restart FastAPI/Uvicorn and run:" -ForegroundColor Yellow
Write-Host "  GET /stocks/enrichment-status"
Write-Host "  GET /stocks/trading212/history-debug?limit=50"
