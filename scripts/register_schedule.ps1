# Registers a weekly Windows Task Scheduler job that runs the RAAM strategy and,
# optionally, syncs an Alpaca paper-trading account to the new target portfolio.
#
# Usage (run from an elevated or normal PowerShell prompt):
#   .\scripts\register_schedule.ps1 -TickersPath "Tickers_file.csv" -PythonExe "C:\path\to\python.exe"
#   .\scripts\register_schedule.ps1 -SyncPaperAccount:$false   # raam only, no trading
#
# Re-running this script updates the existing task instead of duplicating it.

param(
    [string]$TaskName = "RAAM_Weekly_Run",
    [string]$ProjectDir = (Resolve-Path "$PSScriptRoot\..").Path,
    [string]$TickersPath = "Tickers_file.csv",
    [string]$PythonExe = (Get-Command python).Source,
    [string]$DayOfWeek = "Monday",
    [string]$Time = "07:00",
    [bool]$SyncPaperAccount = $true
)

$logDir = Join-Path $ProjectDir "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logPath = Join-Path $logDir "raam_run.log"

$runCommand = "`"$PythonExe`" -m raam.cli --tickers `"$TickersPath`" --out `"results`""
$commandList = @($runCommand)

if ($SyncPaperAccount) {
    $hasApiKey = [Environment]::GetEnvironmentVariable("ALPACA_API_KEY", "User")
    $hasSecretKey = [Environment]::GetEnvironmentVariable("ALPACA_SECRET_KEY", "User")
    if (-not $hasApiKey -or -not $hasSecretKey) {
        Write-Warning (
            "ALPACA_API_KEY / ALPACA_SECRET_KEY are not set as persistent User environment " +
            "variables. A Scheduled Task runs in its own session and won't see keys set only " +
            "with `$env:VAR = '...'` in your current terminal -- it needs them saved permanently, e.g.:`n" +
            "  [Environment]::SetEnvironmentVariable('ALPACA_API_KEY', '<key>', 'User')`n" +
            "  [Environment]::SetEnvironmentVariable('ALPACA_SECRET_KEY', '<secret>', 'User')`n" +
            "Without that, the weekly trade-sync step will fail every run (check $logPath)."
        )
    }
    $tradeCommand = "`"$PythonExe`" -m raam.trade_cli --execute"
    $commandList += $tradeCommand
}

# Wrap in cmd so stdout/stderr land in a log file we can check after unattended runs.
# Steps are chained with && so the trade sync only runs if `raam` succeeded.
$fullCommand = ($commandList -join " && ")
$action = New-ScheduledTaskAction -Execute "cmd.exe" `
    -Argument "/c $fullCommand >> `"$logPath`" 2>&1" `
    -WorkingDirectory $ProjectDir

$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $DayOfWeek -At $Time

$description = if ($SyncPaperAccount) {
    "Runs the RAAM portfolio strategy weekly, records the result to raam_history.db, " +
    "and syncs the Alpaca paper-trading account to the new target portfolio."
} else {
    "Runs the RAAM portfolio strategy weekly and records the result to raam_history.db."
}

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Set-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger | Out-Null
    Write-Host "Updated existing scheduled task '$TaskName'."
} else {
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Description $description | Out-Null
    Write-Host "Registered scheduled task '$TaskName' to run every $DayOfWeek at $Time."
}

if ($SyncPaperAccount) {
    Write-Host "Each run will: (1) recompute the portfolio, (2) place Alpaca paper orders to match it."
} else {
    Write-Host "Each run will only recompute and record the portfolio -- no trades will be placed."
}
Write-Host "Logs will be written to $logPath"
Write-Host "To inspect or remove the task: Get-ScheduledTask -TaskName $TaskName | Unregister-ScheduledTask"
