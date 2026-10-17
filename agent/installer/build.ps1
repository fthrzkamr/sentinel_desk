<#
  Stages the already-built agent + watchdog into installer/payload/, then
  compiles the MSI. Run this from the `installer/` folder (or anywhere -
  paths below are relative to this script's own location).

  Prerequisites (one-time):
    dotnet tool install --global wix

  Usage:
    .\build.ps1
        Plain build - matches every install today (localhost default,
        blank enrollment token, msiexec command-line overrides still work).

    .\build.ps1 -ServerUrl "http://your-server:8000" -EnrollmentToken "<reusable token>"
        Bakes both values into the compiled .msi itself so a plain
        double-click install with zero parameters just works - for mass
        deployment, use a *reusable* token created via the dashboard's
        "Reusable (deployment key)" checkbox (Agent Management page).
        Devices installed this way land in Pending Approval until an
        admin approves them - see README.md. The token is never written
        to Product.wxs, only into this one compiled .msi output file.
  Output:
    .\SentinelDeskAgent.msi
#>

param(
    [string]$ServerUrl = "",
    [string]$EnrollmentToken = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$agentDist = Join-Path $root "..\dist"
$payload = Join-Path $root "payload"

if (-not (Test-Path (Join-Path $agentDist "SentinelDeskAgent.exe"))) {
    throw "agent\dist\SentinelDeskAgent.exe not found - build the agent first (pyinstaller --clean --noconfirm ..\SentinelDeskAgent.spec)."
}
if (-not (Test-Path (Join-Path $agentDist "SentinelDeskWatchdog\SentinelDeskWatchdog.exe"))) {
    throw "agent\dist\SentinelDeskWatchdog\SentinelDeskWatchdog.exe not found - build the watchdog first (pyinstaller --clean --noconfirm ..\SentinelDeskWatchdog.spec)."
}

Write-Host "Staging payload..."
Remove-Item -Recurse -Force $payload -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $payload | Out-Null

Copy-Item (Join-Path $agentDist "SentinelDeskAgent.exe") $payload
Copy-Item (Join-Path $agentDist "SentinelDeskWatchdog") (Join-Path $payload "SentinelDeskWatchdog") -Recurse

# MSI-installed devices default to every monitor ON (unlike the plain
# opt-in-false .env.example template manually-configured devices use) -
# an explicit policy choice, not a code-level default, so devices set up
# by hand keep their existing opt-in behavior unchanged.
#
# INSTALLED_VIA_MSI=true is a marker the agent's config loader checks (see
# ../src/config/settings.py) to auto-add any *future* monitor flag that
# doesn't exist yet in an already-installed device's .env - so a new
# feature added after this device was installed still defaults to "on"
# here without needing a reinstall or manual edit. Real SERVER_URL/
# ENROLLMENT_TOKEN values aren't known until install time, so
# Product.wxs's SetServerUrl/SetEnrollmentToken custom actions append the
# real values as later lines in this same file after it's copied into
# place (python-dotenv resolves a repeated key to its last occurrence).
$envContent = @"
SERVER_URL=http://localhost:8000
ENROLLMENT_TOKEN=
MONITOR_INTERVAL=15
INSTALLED_VIA_MSI=true
SCREEN_MONITOR_ENABLED=true
USB_MONITOR_ENABLED=true
APP_USAGE_MONITOR_ENABLED=true
BROWSER_HISTORY_MONITOR_ENABLED=true
FILE_ACTIVITY_MONITOR_ENABLED=true
IDLE_ACTIVITY_MONITOR_ENABLED=true
SYSTEM_ERROR_MONITOR_ENABLED=true
"@
Set-Content -Path (Join-Path $payload ".env") -Value $envContent -Encoding Ascii

Write-Host "Building MSI..."
Push-Location $root
try {
    $wixArgs = @("build", "Product.wxs", "-ext", "WixToolset.UI.wixext", "-ext", "WixToolset.Util.wixext", "-out", "SentinelDeskAgent.msi")
    if ($ServerUrl) { $wixArgs += @("-d", "ServerUrl=$ServerUrl") }
    if ($EnrollmentToken) { $wixArgs += @("-d", "EnrollmentToken=$EnrollmentToken") }
    wix @wixArgs
    if ($LASTEXITCODE -ne 0) {
        throw "wix build failed with exit code $LASTEXITCODE (see errors above)."
    }
} finally {
    Pop-Location
}

Write-Host "Done: $(Join-Path $root 'SentinelDeskAgent.msi')"
