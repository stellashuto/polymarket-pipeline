# publish.ps1 - End-to-end publisher
#
#   1. Generate articles (Flow A + Flow B + C + D)
#   2. Sync to polymarket-site/content/articles/
#   3. git commit and push -> Vercel auto-deploys
#
# Examples:
#   .\publish.ps1                                  # default: 1 each = 4 articles
#   .\publish.ps1 -NewsLimit 2 -CryptoLimit 0      # custom counts
#   .\publish.ps1 -DryRun                          # preview only
#   .\publish.ps1 -SkipPush                        # local only, no git push
#
# Defaults reduced 2026-05-30 for AdSense quality (was 3/1/2/2 = 8/run).

[CmdletBinding()]
param(
  [int]$NewsLimit = 1,
  [int]$MarketLimit = 1,
  [int]$AirdropLimit = 1,
  [int]$CryptoLimit = 1,
  [switch]$DryRun,
  [switch]$SkipPush
)

$ErrorActionPreference = "Stop"
$PipelineDir = $PSScriptRoot
$SiteDir     = Join-Path (Split-Path $PipelineDir -Parent) "polymarket-site"
$LogDir      = Join-Path $PipelineDir "logs"
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$LogFile = Join-Path $LogDir ("publish_{0}.log" -f (Get-Date -Format "yyyyMMdd"))

function Log {
  param([string]$Msg, [string]$Level = "INFO")
  $line = "{0} [{1}] {2}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Level, $Msg
  Write-Host $line
  Add-Content -Path $LogFile -Value $line -Encoding utf8
}

Log "=== publish.ps1 START (news=$NewsLimit, market=$MarketLimit, dryRun=$DryRun, skipPush=$SkipPush) ==="

# Load secrets from .env if not already set
$envFile = Join-Path $PipelineDir ".env"
if (Test-Path $envFile) {
  Get-Content $envFile | ForEach-Object {
    if ($_ -match '^\s*([A-Z_]+)\s*=\s*(.+)\s*$') {
      $name  = $matches[1]
      $value = $matches[2].Trim().Trim('"').Trim("'")
      if (-not (Get-Item -Path "Env:$name" -ErrorAction SilentlyContinue)) {
        Set-Item -Path "Env:$name" -Value $value
      }
    }
  }
}

if (-not $env:ANTHROPIC_API_KEY) {
  Log "ANTHROPIC_API_KEY is not set. Aborting." "ERROR"
  exit 1
}
if (-not $env:REPLICATE_API_TOKEN) {
  Log "REPLICATE_API_TOKEN is not set. Thumbnails will be skipped." "WARN"
}

# --- Step 1: Generate articles ---
Log "Step 1: generating articles..."
Push-Location $PipelineDir
try {
  $pyArgs = @("main.py", "all", "--news-limit", $NewsLimit, "--market-limit", $MarketLimit, "--airdrop-limit", $AirdropLimit, "--crypto-limit", $CryptoLimit)
  if ($DryRun) { $pyArgs += "--dry-run" }
  & python @pyArgs *>&1 | Tee-Object -FilePath $LogFile -Append
  if ($LASTEXITCODE -ne 0) {
    Log "Pipeline returned non-zero exit code: $LASTEXITCODE" "ERROR"
    exit $LASTEXITCODE
  }
} finally {
  Pop-Location
}

if ($DryRun) {
  Log "Dry run complete."
  exit 0
}

# --- Step 2: Detect changes in site content ---
Log "Step 2: checking site for changes..."
Push-Location $SiteDir
try {
  $status = git status --porcelain content/articles/ public/thumbnails/
  if (-not $status) {
    Log "No changes in content/articles or public/thumbnails. Nothing to publish."
    exit 0
  }
  Log "Detected changes:"
  $status | ForEach-Object { Log "  $_" }

  if ($SkipPush) {
    Log "SkipPush flag set - leaving local changes uncommitted."
    exit 0
  }

  # --- Step 3: commit and push ---
  Log "Step 3: committing and pushing..."
  git add content/articles/ public/thumbnails/
  $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm"
  $count = ($status | Measure-Object).Count
  git commit -m "Auto-publish: $count article change(s) at $timestamp"
  if ($LASTEXITCODE -ne 0) {
    Log "git commit failed." "ERROR"
    exit 1
  }
  git push origin main
  if ($LASTEXITCODE -ne 0) {
    Log "git push failed." "ERROR"
    exit 1
  }
  Log "Pushed successfully. Vercel will deploy automatically."
} finally {
  Pop-Location
}

Log "=== publish.ps1 DONE ==="
