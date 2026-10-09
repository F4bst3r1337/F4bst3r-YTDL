@echo off
chcp 65001 >nul
cd /d "%~dp0"
title F4bst3r-YTDL

rem ---- 1. Python suchen, sonst per winget installieren
set "PY=python"
%PY% --version >nul 2>nul && goto havepy
set "PY=%LocalAppData%\Programs\Python\Python312\python.exe"
if exist "%PY%" goto havepy

echo Python wurde nicht gefunden und wird jetzt installiert ...
where winget >nul 2>nul || goto nowinget
winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
if exist "%PY%" goto havepy
echo.
echo Python wurde installiert. Bitte schliesse dieses Fenster und starte start.bat noch einmal.
pause
exit /b 0

:nowinget
echo.
echo Python fehlt und konnte nicht automatisch installiert werden.
echo Installiere es von https://www.python.org/downloads/ (Haken bei "Add python.exe to PATH")
echo und starte danach start.bat noch einmal.
pause
exit /b 1

:havepy
rem ---- 2. Eigene Python-Umgebung mit yt-dlp
if exist ".venv\Scripts\python.exe" goto havevenv
echo Erste Einrichtung, das dauert eine Minute ...
"%PY%" -m venv .venv
if errorlevel 1 goto fail
:havevenv
".venv\Scripts\python.exe" -c "import yt_dlp" >nul 2>nul && goto haveytdlp
echo yt-dlp wird installiert ...
".venv\Scripts\python.exe" -m pip install -U pip >nul 2>nul
".venv\Scripts\python.exe" -m pip install -U "yt-dlp[default]"
if errorlevel 1 goto fail
:haveytdlp

if /i "%~1"=="update" goto update

rem ---- 3. ffmpeg und Deno bei Bedarf in den Ordner bin laden
".venv\Scripts\python.exe" setup_tools.py

rem ---- 4. F4bst3r-YTDL starten
".venv\Scripts\python.exe" server.py --open %*
pause
exit /b 0

:update
echo Aktualisiere yt-dlp ...
".venv\Scripts\python.exe" -m pip install -U "yt-dlp[default]"
pause
exit /b 0

:fail
echo.
echo Die Einrichtung ist fehlgeschlagen. Pruefe die Internetverbindung und versuche es erneut.
pause
exit /b 1
