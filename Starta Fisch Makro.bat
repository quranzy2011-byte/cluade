@echo off
rem Fisch Makro - startare for Windows (utan AutoHotkey).
set MAPP=%USERPROFILE%\FischMakro
if not exist "%MAPP%" mkdir "%MAPP%"
where py >nul 2>nul
if errorlevel 1 (
  echo Installerar Python...
  winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
  echo Starta den har filen igen nar Python ar installerat.
  pause
  exit /b
)
if not exist "%MAPP%\fisch_app.py" (
  powershell -NoProfile -Command "Invoke-WebRequest -UseBasicParsing https://raw.githubusercontent.com/quranzy2011-byte/cluade/main/fisch_app.py -OutFile '%MAPP%\fisch_app.py'"
)
py -3 -c "import numpy, mss" 2>nul || py -3 -m pip install --user --upgrade numpy mss
cd /d "%MAPP%"
start "" pyw -3 fisch_app.py
