param([switch]$OpenBrowser)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$baseUrl = 'http://127.0.0.1:3001'

function Test-AppReady {
    try {
        $health = Invoke-RestMethod "$baseUrl/api/health" -TimeoutSec 2
        return ($health.ok -eq $true -and $health.service -eq 'connected')
    } catch { return $false }
}

if (-not (Test-AppReady)) {
    $listener = Get-NetTCPConnection -LocalPort 3001 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($listener) {
        $savedPidFile = Join-Path $projectRoot 'data/active/runtime/server.pid'
        $savedPid = if (Test-Path -LiteralPath $savedPidFile) { (Get-Content -LiteralPath $savedPidFile -Raw).Trim() } else { '' }
        $existing = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
        if ($savedPid -ne [string]$listener.OwningProcess -or $existing.CommandLine -notmatch 'server[/\\]main\.ts') {
            throw 'Port 3001 belongs to another application. Close that application before starting Finance.'
        }
        # Replace this project's unhealthy host and its own service only.
        Get-CimInstance Win32_Process -Filter "ParentProcessId=$($listener.OwningProcess)" |
            Where-Object { $_.CommandLine -match '-m service\.server' -and $_.ExecutablePath.StartsWith($projectRoot, [StringComparison]::OrdinalIgnoreCase) } |
            ForEach-Object {
                # A Windows venv launcher may own a second, real Python process.
                # Stop only its verified service worker before the launcher.
                Get-CimInstance Win32_Process -Filter "ParentProcessId=$($_.ProcessId)" |
                    Where-Object { $_.CommandLine -match '-m service\.server' } |
                    ForEach-Object { Stop-Process -Id $_.ProcessId -ErrorAction SilentlyContinue }
                Stop-Process -Id $_.ProcessId -ErrorAction SilentlyContinue
            }
        Stop-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue
    }
    $nodeExe = (Get-Command node.exe -ErrorAction Stop).Source
    foreach ($relative in @('node_modules/tsx/dist/loader.mjs', '.venv/Scripts/python.exe', 'web/dist/index.html')) {
        if (-not (Test-Path -LiteralPath (Join-Path $projectRoot $relative))) {
            throw "Missing $relative. Follow README.txt to install and build first."
        }
    }
    Push-Location $projectRoot
    try {
        & $nodeExe scripts/fix_dependency.mjs --check
        if ($LASTEXITCODE -ne 0) { throw 'Dependency integrity check failed.' }
        $logDir = Join-Path $projectRoot 'data/active/runtime'
        New-Item -ItemType Directory -Path $logDir -Force | Out-Null
        $env:FINANCE_HOST = '127.0.0.1'
        $env:FINANCE_PORT = '3001'
        $env:FINANCE_DATA_DIR = Join-Path $projectRoot 'data/active'
        $env:FINANCE_PYTHON = Join-Path $projectRoot '.venv/Scripts/python.exe'
        $serverProcess = Start-Process -FilePath $nodeExe -ArgumentList @('--import', 'tsx', 'server/main.ts') -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logDir 'server.stdout.log') -RedirectStandardError (Join-Path $logDir 'server.stderr.log') -PassThru
        $serverProcess.Id | Set-Content -LiteralPath (Join-Path $logDir 'server.pid') -Encoding ascii
        $ready = $false
        $deadline = (Get-Date).AddSeconds(45)
        while ((Get-Date) -lt $deadline) {
            if (Test-AppReady) { $ready = $true; break }
            $serverProcess.Refresh()
            if ($serverProcess.HasExited) { throw 'Application exited. See data/active/runtime/server.stderr.log.' }
            Start-Sleep -Milliseconds 400
        }
        if (-not $ready) { throw 'Startup timed out. See data/active/runtime/server.stderr.log.' }
    } finally { Pop-Location }
}
# Reuse only an already prepared project VM. Never download or install runtimes.
$vmRoot = Join-Path $projectRoot 'sandbox/runtime'
if ((Test-Path -LiteralPath (Join-Path $vmRoot 'remote.json')) -and
    (Test-Path -LiteralPath (Join-Path $vmRoot 'finance-vm.qcow2')) -and
    (Test-Path -LiteralPath (Join-Path $vmRoot 'qemu/qemu-system-x86_64.exe'))) {
    & (Join-Path $projectRoot '.venv/Scripts/python.exe') (Join-Path $projectRoot 'sandbox/portable_vm.py') start
    if ($LASTEXITCODE -ne 0) { Write-Warning 'The page is ready, but the analysis VM could not start.' }
}
Write-Host "Ready: $baseUrl"
if ($OpenBrowser) { Start-Process $baseUrl }
