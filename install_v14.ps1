param(
    [string]$ProjectRoot = "C:\Users\anagn\PycharmProjects\ΜΕΤΟΧΕΣ2"
)

$ErrorActionPreference = "Stop"
$PatchRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupRoot = Join-Path $ProjectRoot ("_backup_v14_" + $Stamp)

# V14 adds score explanations + collapsible dashboard while preserving
# V13 broker-history fixes and V12 Capital/Freedom Sold integration.
$Files = @(
    "metoxes\routers\stock.py",
    "metoxes\services\dashboard_service.py",
    "metoxes\services\ai_commentary_service.py",
    "metoxes\services\score_explanation_service.py",
    "metoxes\services\candidate_research_service.py"
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

$StockText = Get-Content (Join-Path $ProjectRoot "metoxes\routers\stock.py") -Raw
$DashboardText = Get-Content (Join-Path $ProjectRoot "metoxes\services\dashboard_service.py") -Raw
$ScoreText = Get-Content (Join-Path $ProjectRoot "metoxes\services\score_explanation_service.py") -Raw

$Checks = @(
    @{Text=$StockText; Value='V14-score-accordion-fmp-explain'; File='stock.py'},
    @{Text=$StockText; Value='reconcile_financial_crosschecks'; File='stock.py'},
    @{Text=$StockText; Value='enrich_score_explanations'; File='stock.py'},
    @{Text=$DashboardText; Value='portfolioAccordion'; File='dashboard_service.py'},
    @{Text=$DashboardText; Value='Γιατί πήρε αυτό το Final Score'; File='dashboard_service.py'},
    @{Text=$ScoreText; Value='score_rationale_text'; File='score_explanation_service.py'},
    @{Text=$ScoreText; Value='ROE/P-B'; File='score_explanation_service.py'}
)
foreach ($Item in $Checks) {
    if ($Item.Text -notmatch [regex]::Escape($Item.Value)) {
        throw "VERIFY FAILED in $($Item.File): '$($Item.Value)' not found"
    }
}

$UpdateCount = ([regex]::Matches($StockText, '@router\.post\("/stocks/update-excel"\)')).Count
if ($UpdateCount -ne 1) {
    throw "VERIFY FAILED: expected exactly 1 /stocks/update-excel route, found $UpdateCount"
}

Write-Host ""
Write-Host "METOXES2 V14 installed successfully." -ForegroundColor Green
Write-Host "Backup: $BackupRoot"
Write-Host "Collapsible Final Score analysis + FMP/SEC explanation verified."
Write-Host ""
Write-Host "Now fully restart FastAPI/Uvicorn and run:" -ForegroundColor Yellow
Write-Host "  GET  /stocks/enrichment-status"
Write-Host "  POST /stocks/update-excel"
Write-Host "Then open portfolio_dashboard.html"
