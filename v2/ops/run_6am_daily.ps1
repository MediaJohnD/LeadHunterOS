$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Write-Host "[$timestamp] LeadHunterOS daily batch start"

python .\run_agent.py --daily
$rc = $LASTEXITCODE

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
if ($rc -ne 0) {
  Write-Host "[$timestamp] LeadHunterOS daily batch FAILED (exit=$rc)"
  exit $rc
}

Write-Host "[$timestamp] LeadHunterOS daily batch OK"
exit 0
