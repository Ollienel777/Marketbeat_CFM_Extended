# Registers a weekly Windows Task Scheduler job that runs the RAAM strategy.
#
# Usage (run from an elevated or normal PowerShell prompt):
#   .\scripts\register_schedule.ps1 -TickersPath "Tickers_file.csv" -PythonExe "C:\path\to\python.exe"
#
# Re-running this script updates the existing task instead of duplicating it.

param(
    [string]$TaskName = "RAAM_Weekly_Run",
    [string]$ProjectDir = (Resolve-Path "$PSScriptRoot\..").Path,
    [string]$TickersPath = "Tickers_file.csv",
    [string]$PythonExe = (Get-Command python).Source,
    [string]$DayOfWeek = "Monday",
    [string]$Time = "07:00"
)

$logDir = Join-Path $ProjectDir "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$argumentList = "-m raam.cli --tickers `"$TickersPath`" --out `"results`""
$logPath = Join-Path $logDir "raam_run.log"

# Wrap in cmd so stdout/stderr land in a log file we can check after unattended runs.
$action = New-ScheduledTaskAction -Execute "cmd.exe" `
    -Argument "/c `"$PythonExe`" $argumentList >> `"$logPath`" 2>&1" `
    -WorkingDirectory $ProjectDir

$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $DayOfWeek -At $Time

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Set-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger | Out-Null
    Write-Host "Updated existing scheduled task '$TaskName'."
} else {
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
        -Description "Runs the RAAM portfolio strategy weekly and records the result to raam_history.db." | Out-Null
    Write-Host "Registered scheduled task '$TaskName' to run every $DayOfWeek at $Time."
}

Write-Host "Logs will be written to $logPath"
Write-Host "To inspect or remove the task: Get-ScheduledTask -TaskName $TaskName | Unregister-ScheduledTask"
