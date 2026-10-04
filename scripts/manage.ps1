param(
    [ValidateSet('install','start','stop','doctor')][string]$Action = 'start',
    [ValidateRange(1024,65535)][int]$Port = 3001,
    [string]$DataDirectory = '',
    [switch]$NoBrowser,
    [switch]$NoShortcut,
    [string]$ShortcutDirectory = ''
)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$dataRoot = if ($DataDirectory) { [IO.Path]::GetFullPath($DataDirectory) } else { Join-Path $projectRoot 'data' }
$logRoot = Join-Path $dataRoot 'runtime'
$recordPath = Join-Path $logRoot "launcher-$Port.json"
$entry = Join-Path $projectRoot 'server/dist/main.js'
$nodeExe = Join-Path $projectRoot 'runtime/node/node.exe'
if (-not (Test-Path -LiteralPath $nodeExe)) {
    $command = Get-Command node.exe -ErrorAction SilentlyContinue
    if ($command) { $nodeExe = $command.Source }
}
$pythonExe = Join-Path $projectRoot 'runtime/python/python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) { $pythonExe = Join-Path $projectRoot '.venv/Scripts/python.exe' }
$baseUrl = "http://127.0.0.1:$Port"

function Test-Ready {
    try { $health = Invoke-RestMethod "$baseUrl/api/health" -TimeoutSec 2; return ($health.ok -eq $true -and $health.service -eq 'connected' -and $health.version -eq '0.1.0') }
    catch { return $false }
}

function Test-Installation {
    if (-not [Environment]::Is64BitOperatingSystem) { throw 'Finance Agent 0.1 requires 64-bit Windows.' }
    foreach ($file in @($nodeExe,$pythonExe,$entry,(Join-Path $projectRoot 'web/dist/index.html'),(Join-Path $projectRoot 'node_modules/@modelcontextprotocol/sdk/package.json'))) {
        if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "Missing file: $file. Extract the complete Windows release ZIP, or follow the source-build section in README.md." }
    }
    $nodeVersion = ([string](& $nodeExe --version)).Trim()
    if ($LASTEXITCODE -ne 0 -or $nodeVersion -notmatch '^v(2[4-9]|[3-9][0-9])\.') { throw 'Node.js 24 or newer is required.' }
    & $pythonExe -B -c "import sys,sqlite3,fitz,pandas,openpyxl,rapidocr_onnxruntime,onnxruntime,mcp,langextract; assert sys.version_info[:2] == (3,12); print('Python 3.12 and document dependencies: OK')"
    if ($LASTEXITCODE -ne 0) { throw 'Python runtime check failed. See README.md for repair instructions.' }
    & $nodeExe (Join-Path $projectRoot 'scripts/fix_dependency.mjs') --check
    if ($LASTEXITCODE -ne 0) { throw 'Node dependency integrity check failed.' }
    Write-Host "Finance Agent 0.1 / $nodeVersion / Windows x64"
}

function Get-OwnedProcess {
    if (-not (Test-Path -LiteralPath $recordPath)) { return $null }
    $record = Get-Content -LiteralPath $recordPath -Raw | ConvertFrom-Json
    if ($record.root -ne $projectRoot -or $record.data -ne $dataRoot -or $record.port -ne $Port) { throw 'The launcher record belongs to a different installation or data folder.' }
    $candidate = Get-CimInstance Win32_Process -Filter "ProcessId=$([int]$record.processId)" -ErrorAction SilentlyContinue
    if (-not $candidate) { return $null }
    $created = ([datetime]$candidate.CreationDate).ToUniversalTime().Ticks.ToString()
    if ($created -ne $record.createdTicks -or $candidate.ExecutablePath -ne $record.node -or -not $candidate.CommandLine.Contains($entry)) { throw 'PID was reused or process ownership changed. No process was stopped.' }
    return $candidate
}

function Stop-OwnedProcess($owned) {
    if (-not $owned) { return }
    # Record only this launcher's descendants before terminating the parent.
    $descendants = @(); $parents = @([uint32]$owned.ProcessId)
    $all = @(Get-CimInstance Win32_Process)
    while ($parents.Count) {
        $next = @($all | Where-Object { $parents -contains $_.ParentProcessId })
        $descendants += $next
        $parents = @($next | ForEach-Object { [uint32]$_.ProcessId })
    }
    Stop-Process -Id $owned.ProcessId -ErrorAction SilentlyContinue
    foreach ($child in $descendants) {
        $current = Get-CimInstance Win32_Process -Filter "ProcessId=$($child.ProcessId)" -ErrorAction SilentlyContinue
        if ($current -and $current.CreationDate -eq $child.CreationDate -and $current.ExecutablePath -eq $pythonExe) {
            Stop-Process -Id $current.ProcessId -ErrorAction SilentlyContinue
        }
    }
    if (Test-Path -LiteralPath $recordPath) { Remove-Item -LiteralPath $recordPath }
}

function Start-Instance {
    param([switch]$EnvironmentChecked)
    $owned = Get-OwnedProcess
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($listener) {
        if (-not $owned -or $listener.OwningProcess -notcontains $owned.ProcessId) { throw "Port $Port is used by another instance or program. Use start-finance.cmd -Port 3010, or stop its owner first. No existing service was changed." }
        if (Test-Ready) { Write-Host "Already running: $baseUrl"; return }
        throw "This instance is not ready. Check $logRoot, then run stop-finance.cmd before retrying."
    }
    if ($owned) { throw 'This instance is still starting or closing. Wait briefly before retrying.' }
    if (-not $EnvironmentChecked) { Test-Installation }
    $env:FINANCE_HOST = '127.0.0.1'
    $env:FINANCE_PORT = [string]$Port
    $env:FINANCE_DATA_DIR = $dataRoot
    $env:FINANCE_PYTHON = $pythonExe
    $env:PYTHONDONTWRITEBYTECODE = '1'
    $process = Start-Process -FilePath $nodeExe -ArgumentList @(('"' + $entry + '"')) -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logRoot "server-$Port.stdout.log") -RedirectStandardError (Join-Path $logRoot "server-$Port.stderr.log") -PassThru
    $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId=$($process.Id)"
    if (-not $processInfo) { throw "Service exited during startup. Check $logRoot." }
    $record = @{ processId=$process.Id; createdTicks=([datetime]$processInfo.CreationDate).ToUniversalTime().Ticks.ToString(); node=$nodeExe; root=$projectRoot; data=$dataRoot; port=$Port; version='0.1.0' }
    $record | ConvertTo-Json | Set-Content -LiteralPath $recordPath -Encoding UTF8
    Write-Host 'Starting the local service. First launch may take up to three minutes while Windows checks the bundled dependencies...'
    $ready = $false; $deadline = (Get-Date).AddSeconds(180)
    while ((Get-Date) -lt $deadline) {
        if (Test-Ready) { $ready = $true; break }
        $process.Refresh()
        if ($process.HasExited) { break }
        Start-Sleep -Milliseconds 300
    }
    if (-not $ready) { Stop-OwnedProcess (Get-OwnedProcess); throw "Service did not become ready. See $logRoot/server-$Port.stderr.log." }
    Write-Host "Ready: $baseUrl"
}

function Install-Shortcuts {
    if ($NoShortcut) { return }
    $desktop = if ($ShortcutDirectory) { [IO.Path]::GetFullPath($ShortcutDirectory) } else { [Environment]::GetFolderPath('Desktop') }
    New-Item -ItemType Directory -Path $desktop -Force | Out-Null
    $shell = New-Object -ComObject WScript.Shell
    foreach ($item in @(@('Finance Agent 0.1','start-finance.cmd'),@('Stop Finance Agent 0.1','stop-finance.cmd'))) {
        $link = Join-Path $desktop ($item[0]+'.lnk'); $target = Join-Path $projectRoot $item[1]
        $shortcut = $shell.CreateShortcut($link)
        if ((Test-Path -LiteralPath $link) -and $shortcut.TargetPath -ne $target) { throw "Shortcut already belongs to another installation: $link. Use -NoShortcut or choose another ShortcutDirectory." }
        $shortcut.TargetPath = $target
        $shortcut.WorkingDirectory = $projectRoot
        $shortcut.Arguments = '-Port ' + $Port + $(if($DataDirectory){' -DataDirectory "'+$dataRoot+'"'}else{''})
        $shortcut.Description = 'Finance Agent 0.1 - local financial research'
        $shortcut.Save()
    }
    Write-Host "Shortcuts created in $desktop"
}

try {
    New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
    $lock = [IO.File]::Open((Join-Path $logRoot 'launcher.lock'), [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    try {
        switch ($Action) {
            'doctor' { Test-Installation; Write-Host "Data: $dataRoot"; Write-Host "Service ready: $(Test-Ready)" }
            'stop' {
                $owned = Get-OwnedProcess
                if ($owned -and (Test-Ready)) {
                    foreach ($project in (Invoke-RestMethod "$baseUrl/api/projects").projects) {
                        $active = @((Invoke-RestMethod "$baseUrl/api/projects/$($project.id)/conversations").conversations | Where-Object activeRunId)
                        if ($active.Count) { throw 'A conversation is still running. Stop it in the app before stopping the service.' }
                    }
                    if ((Invoke-RestMethod "$baseUrl/api/approvals").requests.Count) { throw 'Resolve pending authorizations in the app before stopping the service.' }
                }
                Stop-OwnedProcess $owned
                Write-Host 'Finance Agent service stopped. Data was preserved.'
            }
            'install' { Test-Installation; Install-Shortcuts; Start-Instance -EnvironmentChecked; if (-not $NoBrowser) { Start-Process $baseUrl } }
            'start' { Start-Instance; if (-not $NoBrowser) { Start-Process $baseUrl } }
        }
    } finally { $lock.Dispose() }
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
