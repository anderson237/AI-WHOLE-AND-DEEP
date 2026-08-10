@echo off
REM ==========================================================
REM  HERMES BRAIN - demarrage du pont local
REM  Hermes (modele) --> bridge:5050 --> opencode:4096 --> cloud
REM ==========================================================
setlocal

set OPCODE_EXE=%APPDATA%\npm\node_modules\opencode-ai\bin\opencode.exe
set BRIDGE_PY=C:\Users\HP ELITEBOOK G3\hermes-brain\bridge.py
set HERMES_DESKTOP=%LOCALAPPDATA%\hermes\hermes-agent\apps\desktop\release\win-unpacked\Hermes.exe

echo [1/3] Verification de opencode serve (port 4096)...
netstat -ano | findstr ":4096" | findstr /i "LISTEN" >nul
if errorlevel 1 (
    echo      demarrage de opencode serve...
    start "" /b "%OPCODE_EXE%" serve --port 4096
    timeout /t 8 /nobreak >nul
) else (
    echo      deja actif.
)

echo [2/3] Verification du pont Hermes-Brain (port 5050)...
netstat -ano | findstr ":5050" | findstr /i "LISTEN" >nul
if errorlevel 1 (
    echo      demarrage du pont...
    start "" /b python "%BRIDGE_PY%"
    timeout /t 4 /nobreak >nul
) else (
    echo      deja actif.
)

echo [3/3] Verification de bout en bout...
powershell -NoProfile -Command ^
  "try { $a=Invoke-RestMethod http://127.0.0.1:4096/global/health -TimeoutSec 8; $b=Invoke-RestMethod http://127.0.0.1:5050/v1/models -TimeoutSec 8; Write-Host ('OK -> opencode: ' + $a.healthy + ' | brain model: ' + $b.data[0].id) } catch { Write-Host ('ERREUR: ' + $_.Exception.Message) }"

echo.
echo  Hermes Desktop (si non ouvert) : "%HERMES_DESKTOP%"
echo  Base URL Hermes                : http://127.0.0.1:5050/v1  (modele: deepseek-v4-flash-free)
endlocal