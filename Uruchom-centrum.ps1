param([switch]$BezPrzegladarki)
$ErrorActionPreference = 'Stop'
$taskRoot = $PSScriptRoot
$taskUrl = 'http://127.0.0.1:8766'
$taskRuntime = Join-Path $taskRoot '.runtime'
New-Item -ItemType Directory -Path $taskRuntime -Force | Out-Null
$taskReady = $false
try {
    $taskHealth = Invoke-RestMethod -Uri "$taskUrl/health" -TimeoutSec 2
    $taskReady = $taskHealth.app -eq 'centrum-kariery'
    if (-not $taskReady) { throw 'Port 8766 jest zajety przez inny program.' }
} catch {
    if ($_.Exception.Message -like '*inny program*') { throw }
}
if (-not $taskReady) {
    $taskPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $taskPython)) {
        $taskPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
        if (-not (Test-Path -LiteralPath $taskPython)) { throw 'Nie znaleziono Pythona. Szczegoly instalacji: app/README.md.' }
    }
    Push-Location -LiteralPath $taskRoot
    try {
        $taskStarted = & $taskPython -m app.launcher
        if ($LASTEXITCODE -ne 0) { throw 'Nie udalo sie uruchomic serwera niezaleznie od skryptu.' }
        $taskProcess = Get-Process -Id ([int]$taskStarted) -ErrorAction Stop
    } finally { Pop-Location }
    $taskProcessInfo = @{ id = $taskProcess.Id; started = $taskProcess.StartTime.ToUniversalTime().ToString('O') }
    $taskProcessInfo | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskRuntime 'server-process.json') -Encoding utf8
    for ($taskAttempt = 0; $taskAttempt -lt 100; $taskAttempt++) {
        Start-Sleep -Milliseconds 200
        $taskProcess.Refresh()
        if ($taskProcess.HasExited) { throw 'Serwer zakonczyl prace. Sprawdz .runtime/start.stderr.log.' }
        try {
            $taskHealth = Invoke-RestMethod -Uri "$taskUrl/health" -TimeoutSec 1
            if ($taskHealth.app -eq 'centrum-kariery') { $taskReady = $true; break }
        } catch { }
    }
    if (-not $taskReady) { throw 'Serwer nie odpowiedzial. Sprawdz .runtime/start.stderr.log.' }
}
if (-not $BezPrzegladarki) { Start-Process "$taskUrl/" }
Write-Output "Centrum Kariery dziala: $taskUrl/"
