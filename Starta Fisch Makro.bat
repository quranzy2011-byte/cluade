@echo off
setlocal
title Fisch Makro
rem Fisch Makro - dubbelklicka for att starta. Forsta gangen installeras
rem Python och makrot automatiskt (tar nagra minuter), sedan startar det direkt.

set "MAPP=%USERPROFILE%\FischMakro"
if not exist "%MAPP%" mkdir "%MAPP%"

set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if exist "%PY%" goto harpython
for /f "delims=" %%i in ('py -3 -c "import sys;print(sys.executable)" 2^>nul') do set "PY=%%i"
if exist "%PY%" goto harpython

echo Installerar Python, en gang. Det tar nagra minuter...
powershell -NoProfile -Command "Invoke-WebRequest -UseBasicParsing 'https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe' -OutFile '%TEMP%\python-installer.exe'"
"%TEMP%\python-installer.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0
set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not exist "%PY%" (
  echo Kunde inte installera Python. Kolla internet och forsok igen.
  pause
  exit /b
)

:harpython
if not exist "%MAPP%\fisch_app.py" (
  echo Hamtar makrot...
  powershell -NoProfile -Command "Invoke-WebRequest -UseBasicParsing 'https://raw.githubusercontent.com/quranzy2011-byte/cluade/main/fisch_app.py' -OutFile '%MAPP%\fisch_app.py'"
)
if not exist "%MAPP%\fisch_app.py" (
  echo Kunde inte hamta makrot. Kolla internet och forsok igen.
  pause
  exit /b
)
"%PY%" -c "import numpy, mss" 2>nul
if errorlevel 1 (
  echo Installerar det sista...
  "%PY%" -m pip install --user --upgrade numpy mss
)
set "PYW=%PY:python.exe=pythonw.exe%"
cd /d "%MAPP%"
start "" "%PYW%" fisch_app.py --bara-fiske
