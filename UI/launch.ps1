<#
.SYNOPSIS
    Starts Stock Transfer Manager after checking everything it needs, fixing what it can.

.DESCRIPTION
    1. Python environment: creates UI\venv if missing, repairs it if packages are missing or broken.
    2. MySQL: finds the Windows service, starts it if stopped (asks Windows for permission once),
       waits while it is starting, and waits until it accepts connections (slow after a reboot).
    3. Database: if the mysql client and a saved login path are available, checks that
       stock_transfer_db exists and offers to load stock_transfer_db.sql if it does not.
    4. Detects a copy of the app that is already running.
    5. Starts the app without a console window; if it exits immediately, shows the error.
    Every run is logged to %LOCALAPPDATA%\StockTransferManager\launcher.log.

.PARAMETER CheckOnly
    Run all checks and repairs, but do not start the app.
.PARAMETER NoPause
    Never wait for a key press (for automated runs).
.PARAMETER ServiceName
    MySQL Windows service to use. Default: detected (normally MySQL80).
.PARAMETER WaitSeconds
    How long to wait for MySQL to accept connections. Default: 90.
.PARAMETER LoginPath
    mysql client login path used for the database check. Default: local.
.PARAMETER HostName
    MySQL host to wait for. Default: the host saved by the app's login dialog, else localhost.
.PARAMETER Port
    MySQL port to wait for. Default: the port saved by the app's login dialog, else 3306.
#>
param(
    [switch]$CheckOnly,
    [switch]$NoPause,
    [string]$ServiceName = "",
    [int]$WaitSeconds = 90,
    [string]$LoginPath = "local",
    [string]$HostName = "",
    [int]$Port = 0
)

$ErrorActionPreference = "Stop"
$UiDir = $PSScriptRoot
$ProjectDir = Split-Path $UiDir -Parent
$VenvDir = Join-Path $UiDir "venv"
$Python = Join-Path $VenvDir "Scripts\python.exe"
$PythonW = Join-Path $VenvDir "Scripts\pythonw.exe"
$MainScript = Join-Path $UiDir "main.py"
$Requirements = Join-Path $UiDir "requirements.txt"
$SchemaScript = Join-Path $ProjectDir "stock_transfer_db.sql"
$DatabaseName = "stock_transfer_db"
$SettingsKey = "HKCU:\Software\StockTransfer\Stock Transfer Manager"
$LogDir = Join-Path $env:LOCALAPPDATA "StockTransferManager"
$LogFile = Join-Path $LogDir "launcher.log"
$MinPython = [Version]"3.12"

# ---- output and logging ------------------------------------------------------

function Write-Log([string]$Text) {
    try {
        if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }
        Add-Content -Path $LogFile -Value ("{0:yyyy-MM-dd HH:mm:ss}  {1}" -f (Get-Date), $Text) -Encoding UTF8
    } catch { }
}

function Write-Step([string]$Text) { Write-Host "  ..  $Text"; Write-Log "STEP $Text" }
function Write-Ok([string]$Text) { Write-Host "  OK  $Text" -ForegroundColor Green; Write-Log "OK   $Text" }
function Write-Note([string]$Text) { Write-Host "  !!  $Text" -ForegroundColor Yellow; Write-Log "NOTE $Text" }

function Stop-WithError([string]$Text) {
    Write-Host ""
    Write-Host "  XX  $Text" -ForegroundColor Red
    Write-Log "FAIL $Text"
    Write-Host ""
    Write-Host "  Log: $LogFile"
    if (-not $NoPause) { Read-Host "  Press Enter to close" | Out-Null }
    exit 1
}

function Confirm-Choice([string]$Question, [bool]$Default) {
    if ($NoPause) { return $Default }
    $hint = if ($Default) { "[Y/n]" } else { "[y/N]" }
    $answer = Read-Host "  ??  $Question $hint"
    if ([string]::IsNullOrWhiteSpace($answer)) { return $Default }
    return $answer.Trim().ToLower().StartsWith("y")
}

# ---- 1. Python environment ---------------------------------------------------

function Find-BasePython {
    # Returns the command line (exe + args) of a Python >= 3.12, or $null.
    $candidates = @()
    if (Get-Command py -ErrorAction SilentlyContinue) { $candidates += , @("py", "-3") }
    if (Get-Command python -ErrorAction SilentlyContinue) { $candidates += , @("python") }
    foreach ($candidate in $candidates) {
        $exe = $candidate[0]
        $prefix = @($candidate | Select-Object -Skip 1)
        try {
            $version = & $exe @prefix -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
            if ($LASTEXITCODE -eq 0 -and $version -and ([Version]$version.Trim()) -ge $MinPython) {
                return , $candidate
            }
        } catch { }
    }
    return $null
}

function Test-VenvPackages {
    if (-not (Test-Path $Python)) { return $false }
    try {
        & $Python -c "import PySide6.QtWidgets, mysql.connector, keyring" 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch { return $false }
}

function Install-Requirements {
    Write-Step "Installing the pinned packages from requirements.txt (needs internet, about a minute)"
    # pip writes progress to stderr; keep going on stderr output and judge by the exit code.
    $ErrorActionPreference = "Continue"
    $output = @(& $Python -m pip install --disable-pip-version-check --quiet -r $Requirements 2>&1 | ForEach-Object { "$_" })
    $exitCode = $LASTEXITCODE
    $ErrorActionPreference = "Stop"
    $output | ForEach-Object { Write-Log "PIP  $_" }
    if ($exitCode -eq 0) { return }
    $text = $output -join "`n"
    if ($text -match "WinError 206|filename or extension is too long") {
        Stop-WithError "The project folder path is too long for Windows ($UiDir). Move the project to a shorter folder, for example C:\Projects\DBMS-Project, then run this again."
    }
    if ($text -match "getaddrinfo failed|Failed to establish a new connection|NewConnectionError|ProxyError|timed out") {
        Stop-WithError "Could not download the packages: no internet connection. Connect to the internet and run this again."
    }
    $last = ($output | Where-Object { $_.Trim() } | Select-Object -Last 1)
    Stop-WithError "Package installation failed: $last"
}

function Initialize-Python {
    Write-Step "Checking the Python environment"
    if (Test-VenvPackages) { Write-Ok "Python environment ready"; return }

    $pythonRuns = $false
    if (Test-Path $Python) {
        try { & $Python -c "pass" 2>$null; $pythonRuns = ($LASTEXITCODE -eq 0) } catch { }
    }
    if (-not $pythonRuns) {
        $base = Find-BasePython
        if ($null -eq $base) {
            Stop-WithError "Python $MinPython or newer was not found. Install it from https://www.python.org/downloads/ (tick 'Add python.exe to PATH'), then run this again."
        }
        $exe = $base[0]
        $prefix = @($base | Select-Object -Skip 1)
        Write-Step "Creating the Python environment in UI\venv"
        & $exe @prefix -m venv --clear $VenvDir
        if ($LASTEXITCODE -ne 0) { Stop-WithError "Could not create the Python environment in $VenvDir." }
    } else {
        Write-Note "Some packages are missing or broken; repairing"
    }
    Install-Requirements
    if (-not (Test-VenvPackages)) { Stop-WithError "The packages are still not importable after installation." }
    Write-Ok "Python environment ready"
}

# ---- 2. Connection target ----------------------------------------------------

function Get-ConnectionTarget {
    $target = [ordered]@{ Host = "localhost"; Port = 3306 }
    if (Test-Path $SettingsKey) {
        $saved = Get-ItemProperty -Path $SettingsKey -ErrorAction SilentlyContinue
        if ($saved.host) { $target.Host = [string]$saved.host }
        if ($saved.port) { $target.Port = [int]$saved.port }
    }
    if ($HostName) { $target.Host = $HostName }
    if ($Port -gt 0) { $target.Port = $Port }
    return $target
}

function Test-LocalHost([string]$HostName) {
    return @("localhost", "127.0.0.1", "::1", ".", $env:COMPUTERNAME) -contains $HostName.ToLower() -or
        $HostName -eq $env:COMPUTERNAME
}

# ---- 3. MySQL service ---------------------------------------------------------

function Find-MySqlService {
    if ($ServiceName) { return Get-Service -Name $ServiceName -ErrorAction SilentlyContinue }
    $services = @(Get-Service -ErrorAction SilentlyContinue | Where-Object { $_.Name -like "MySQL*" })
    $preferred = $services | Where-Object { $_.Name -eq "MySQL80" } | Select-Object -First 1
    if ($preferred) { return $preferred }
    return $services | Select-Object -First 1
}

function Start-MySqlService($Service) {
    Write-Step "Starting the MySQL service '$($Service.Name)'"
    try {
        Start-Service -Name $Service.Name -ErrorAction Stop
        return
    } catch {
        Write-Note "Starting a service needs administrator rights; Windows will ask for permission"
    }
    try {
        $command = "Start-Service -Name '$($Service.Name)'"
        Start-Process -FilePath "powershell.exe" -Verb RunAs -Wait -WindowStyle Hidden `
            -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $command
    } catch {
        Stop-WithError "MySQL was not started (permission was declined). Start it yourself: Start menu > Services > $($Service.Name) > Start, then run this again."
    }
}

function Initialize-MySqlService([string]$HostName) {
    if (-not (Test-LocalHost $HostName)) {
        Write-Note "The saved server is '$HostName', not this computer; skipping the local service check"
        return
    }
    Write-Step "Checking the MySQL service"
    $service = Find-MySqlService
    if ($null -eq $service) {
        if ($ServiceName) { Stop-WithError "No Windows service named '$ServiceName' exists." }
        Write-Note "No MySQL Windows service was found. If MySQL is started another way, start it now."
        return
    }
    $startType = (Get-CimInstance Win32_Service -Filter "Name='$($service.Name)'").StartMode
    if ($startType -eq "Disabled") {
        Stop-WithError "The MySQL service '$($service.Name)' is disabled. Open Services, set its Startup type to Automatic, then run this again."
    }
    $service.Refresh()
    if ($service.Status -eq "Running") { Write-Ok "MySQL service '$($service.Name)' is running"; return }
    if ($service.Status -in @("Stopped", "Paused")) { Start-MySqlService $service }
    Write-Step "Waiting for the service to finish starting"
    try {
        $service.Refresh()
        $service.WaitForStatus("Running", [TimeSpan]::FromSeconds($WaitSeconds))
    } catch {
        Stop-WithError "The MySQL service '$($service.Name)' did not reach 'Running' within $WaitSeconds seconds (status: $($service.Status)). See the MySQL error log in C:\ProgramData\MySQL\MySQL Server 8.0\Data."
    }
    Write-Ok "MySQL service '$($service.Name)' is running"
}

function Wait-ForPort([string]$HostName, [int]$Port) {
    Write-Step "Waiting for MySQL to accept connections on ${HostName}:$Port"
    $deadline = (Get-Date).AddSeconds($WaitSeconds)
    while ((Get-Date) -lt $deadline) {
        $client = New-Object System.Net.Sockets.TcpClient
        try {
            $attempt = $client.BeginConnect($HostName, $Port, $null, $null)
            if ($attempt.AsyncWaitHandle.WaitOne(2000) -and $client.Connected) {
                Write-Ok "MySQL is accepting connections"
                return
            }
        } catch { } finally { $client.Close() }
        Start-Sleep -Seconds 2
    }
    Stop-WithError "MySQL did not accept connections on ${HostName}:$Port within $WaitSeconds seconds. If it is still starting after a reboot, wait a minute and run this again."
}

# ---- 4. Database ---------------------------------------------------------------

function Find-MySqlClient {
    $command = Get-Command mysql -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    $default = "C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe"
    if (Test-Path $default) { return $default }
    return $null
}

function Test-Database {
    $client = Find-MySqlClient
    if (-not $client) { Write-Note "mysql client not found; the app will report database problems at login"; return }
    Write-Step "Checking that the database '$DatabaseName' exists"
    $query = "SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name = '$DatabaseName'"
    $result = & $client "--login-path=$LoginPath" "--connect-timeout=5" -N -B -e $query 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Note "No saved mysql login path '$LoginPath'; skipping the database check (the app checks at login)"
        return
    }
    if ("$result".Trim() -eq "1") { Write-Ok "Database '$DatabaseName' found"; return }
    Write-Note "Database '$DatabaseName' does not exist on this server"
    if (-not (Test-Path $SchemaScript)) { Stop-WithError "stock_transfer_db.sql was not found in $ProjectDir." }
    if (-not (Confirm-Choice "Create it now from stock_transfer_db.sql (tables, triggers, view, sample data)?" $false)) {
        Stop-WithError "The database is missing. Load stock_transfer_db.sql, then run this again."
    }
    Write-Step "Loading stock_transfer_db.sql"
    & $client "--login-path=$LoginPath" -e ("source " + ($SchemaScript -replace "\\", "/"))
    if ($LASTEXITCODE -ne 0) { Stop-WithError "Loading stock_transfer_db.sql failed; see the messages above." }
    Write-Ok "Database '$DatabaseName' created"
}

# ---- 5. App ----------------------------------------------------------------------

function Get-RunningApp {
    $pattern = "*" + $MainScript + "*"
    return @(Get-CimInstance Win32_Process -Filter "Name LIKE 'python%'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like $pattern })
}

function Start-App {
    $running = Get-RunningApp
    if ($running.Count -gt 0) {
        Write-Note "Stock Transfer Manager is already running (look for it on the taskbar)"
        if (-not (Confirm-Choice "Start another copy?" $false)) { Write-Log "Kept the running copy"; return }
    }
    Write-Step "Starting Stock Transfer Manager"
    $process = Start-Process -FilePath $PythonW -ArgumentList "`"$MainScript`"" -WorkingDirectory $UiDir -PassThru
    Start-Sleep -Seconds 3
    if ($process.HasExited -and $process.ExitCode -ne 0) {
        Write-Note "The app closed straight away; collecting the error"
        $output = & $Python $MainScript 2>&1 | Select-Object -Last 15
        $output | ForEach-Object { Write-Host "      $_"; Write-Log "APP  $_" }
        Stop-WithError "The app could not start. The last lines of its output are shown above."
    }
    Write-Ok "Stock Transfer Manager is open. Sign in with the MySQL password if it is not filled in."
}

# ---- main --------------------------------------------------------------------------

Write-Host ""
Write-Host "  Stock Transfer Manager - start-up checks" -ForegroundColor Cyan
Write-Host ""
Write-Log "---- launcher started (CheckOnly=$CheckOnly) from $UiDir"

Initialize-Python
$target = Get-ConnectionTarget
Initialize-MySqlService $target.Host
Wait-ForPort $target.Host $target.Port
if (Test-LocalHost $target.Host) { Test-Database }

if ($CheckOnly) {
    Write-Ok "All checks passed (CheckOnly: the app was not started)"
    exit 0
}
Start-App
if (-not $NoPause) { Start-Sleep -Seconds 4 }
exit 0
