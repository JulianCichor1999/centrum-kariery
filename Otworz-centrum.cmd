@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File "%~dp0Uruchom-centrum.ps1"
if errorlevel 1 (
    echo.
    echo Nie udalo sie uruchomic Centrum Kariery. Zachowaj widoczny komunikat bledu.
    pause
    exit /b 1
)
endlocal
