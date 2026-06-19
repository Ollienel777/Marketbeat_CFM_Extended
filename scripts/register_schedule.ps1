# Registers a weekly Windows Task Scheduler job that runs the RAAM strategy and,
# optionally, syncs an IBKR paper-trading account to the new target portfolio.
#
# Usage (run from an elevated or normal PowerShell prompt):
#   .\scripts\register_schedule.ps1 -TickersPath "Tickers_file.csv" -PythonExe "C:\path\to\python.exe"
#   .\scripts\register_schedule.ps1 -SyncPaperAccount:$true   # also run raam-trade --execute each week
#
# Re-running this script updates the existing task instead of duplicating it.
#
# SyncPaperAccount defaults to $false: IBKR's API requires TWS or IB Gateway to be
# running and logged in (it's a local desktop app, not a pure cloud API like Alpaca's),
# and 2FA can block a fully unattended login. Until that's set up reliably on your
# machine (auto-restart + saved login in IB Gateway, or a tool like IBC), the safer
# default is to only recompute/record the portfolio automatically, and run
# `raam-trade --execute` by hand whenever IB Gateway happens to be open.

param(
    [string]$TaskName = "RAAM_Weekly_Run",
    [string]$ProjectDir = (Resolve-Path "$PSScriptRoot\..").Path,
    [string]$TickersPath = "Tickers_file.csv",
    [string]$PythonExe = (Get-Command python).Source,
    [string]$DayOfWeek = "Monday",
    [string]$Time = "07:00",
    [bool]$SyncPaperAccount = $false
)

$logDir = Join-Path $ProjectDir "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logPath = Join-Path $logDir "raam_run.log"

$runCommand = "`"$PythonExe`" -m raam.cli --tickers `"$TickersPath`" --out `"results`""
$commandList = @($runCommand)

if ($SyncPaperAccount) {
    Write-Warning (
        "SyncPaperAccount is enabled: this scheduled task will also run " +
        "'raam-trade --execute' automatically. That requires TWS or IB Gateway to " +
        "already be running and logged into your PAPER account at the scheduled time " +
        "-- it won't launch itself, and 2FA can block an unattended login even if it " +
        "is running. If the trade step fails, check $logPath."
    )
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
    "and syncs the IBKR paper-trading account to the new target portfolio."
} else {
    "Runs the RAAM portfolio strategy weekly and records the result to raam_history.db. " +
    "Does not place trades -- run `raam-trade --execute` manually while IB Gateway is open."
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
    Write-Host "Each run will: (1) recompute the portfolio, (2) place IBKR paper orders to match it (requires IB Gateway/TWS already running and logged in)."
} else {
    Write-Host "Each run will only recompute and record the portfolio -- no trades will be placed automatically."
    Write-Host "Run 'raam-trade --execute' yourself whenever IB Gateway is open and you want to sync the paper account."
}
Write-Host "Logs will be written to $logPath"
Write-Host "To inspect or remove the task: Get-ScheduledTask -TaskName $TaskName | Unregister-ScheduledTask"
