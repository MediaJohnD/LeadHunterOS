param(
  [string]$TaskName = "LeadHunterOS-Daily-Hot-Leads",
  [string]$RepoPath = "D:\Codex\LeadHunterOS-audit\v2",
  [string]$PythonExe = "python",
  [int]$Hour = 6,
  [int]$Minute = 30
)

$runCmd = "cd `"$RepoPath`"; $PythonExe scripts\run_daily_hot_batch.py --gating ops\hot_warm_gating.yaml --target-hot 10 --target-warm 100; if (`$LASTEXITCODE -eq 0) { $PythonExe scripts\generate_morning_digest.py --hot-limit 10 --warm-limit 100 }"

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -WindowStyle Hidden -Command $runCmd"
$trigger = New-ScheduledTaskTrigger -Daily -At ([datetime]::Today.AddHours($Hour).AddMinutes($Minute))
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Force | Out-Null
Write-Host "Scheduled task '$TaskName' created/updated for $Hour`:$Minute daily."

