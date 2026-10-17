$ErrorActionPreference = 'Stop'
$taskPidFile = Join-Path $PSScriptRoot '.runtime\server-process.json'
if (-not (Test-Path -LiteralPath $taskPidFile)) { Write-Output 'Nie znaleziono procesu uruchomionego przez skrypt.'; exit }
$taskSaved = Get-Content -LiteralPath $taskPidFile -Raw | ConvertFrom-Json
$taskProcess = Get-Process -Id $taskSaved.id -ErrorAction SilentlyContinue
if ($taskProcess) {
    if ($taskProcess.StartTime.ToUniversalTime().Ticks -ne ([datetime]$taskSaved.started).ToUniversalTime().Ticks -or $taskProcess.ProcessName -notlike 'python*') { throw 'Identyfikator nalezy juz do innego procesu. Nie zatrzymano go.' }
    Stop-Process -Id $taskProcess.Id
}
Remove-Item -LiteralPath $taskPidFile
Write-Output 'Zatrzymano proces aplikacji. Dane pozostaja w bazie.'
