# ── Cadux Pairing — Hermes Skill Installer (Windows PowerShell) ─────
# Installs paird daemon + Hermes skill into the current user's
# Hermes installation.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File install.ps1
#
# Run this from the paird/ directory.

$SkillName = "cadux-pairing"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$SkillSrc = Join-Path $ScriptRoot "skills" $SkillName
$PairdSrc = Join-Path $ScriptRoot "server.py"

# Detect Hermes home
if (-not $env:HERMES_HOME) {
    $HermesHome = Join-Path $env:LOCALAPPDATA "hermes"
    if (-not (Test-Path $HermesHome)) {
        $HermesHome = Join-Path $env:USERPROFILE ".hermes"
    }
    if (-not (Test-Path $HermesHome)) {
        Write-Error "Could not find Hermes installation. Set HERMES_HOME and re-run."
        exit 1
    }
} else {
    $HermesHome = $env:HERMES_HOME
}

$SkillDir = Join-Path $HermesHome "skills" $SkillName
$ScriptsDir = Join-Path $SkillDir "scripts"

Write-Host "Installing Cadux Pairing skill..."
Write-Host "  Hermes home:  $HermesHome"
Write-Host "  Skill dir:    $SkillDir"

# Create directories
New-Item -ItemType Directory -Path $ScriptsDir -Force | Out-Null

# Copy skill files
Copy-Item (Join-Path $SkillSrc "SKILL.md") $SkillDir -Force
Copy-Item (Join-Path $SkillSrc "scripts" "paird_manager.py") $ScriptsDir -Force

# Copy paird daemon
Copy-Item $PairdSrc $SkillDir -Force

# Install aiohttp if needed
try {
    python -c "import aiohttp" 2>$null
} catch {
    Write-Host "Installing aiohttp dependency..."
    python -m pip install aiohttp 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Could not install aiohttp. Run: pip install aiohttp"
    }
}

Write-Host "`n✓ Cadux Pairing skill installed!"
Write-Host "`nTo verify:"
Write-Host "  python $ScriptsDir\paird_manager.py status"
Write-Host "`nTo start the pairing daemon:"
Write-Host "  python $ScriptsDir\paird_manager.py start"
Write-Host "`nThe manager auto-detects Hermes config from your environment or .env file."
Write-Host "Refresh Hermes skills (restart Hermes) to activate."
