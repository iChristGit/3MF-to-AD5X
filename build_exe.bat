@echo off
setlocal
cd /d "%~dp0"
title Building Bambu2AD5X v1.0.0 exe

set PY=python
where py >nul 2>nul
if %errorlevel%==0 set PY=py

%PY% --version >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install it from https://www.python.org/downloads/
  echo and tick "Add python.exe to PATH" during setup, then run this again.
  pause
  exit /b 1
)

if not exist "ad5x_template.json" (
  echo ad5x_template.json is missing from this folder - cannot build.
  pause
  exit /b 1
)

echo Installing PyInstaller...
%PY% -m pip install --upgrade pyinstaller
if errorlevel 1 (
  echo pip failed - check your internet connection.
  pause
  exit /b 1
)

echo Installing optional extras (Pillow = smooth previews, tkinterdnd2 = drag and drop)...
%PY% -m pip install --upgrade pillow tkinterdnd2 >nul 2>nul

set EXTRA=
%PY% -c "import tkinterdnd2" >nul 2>nul && set EXTRA=--collect-all tkinterdnd2
%PY% -c "import PIL.ImageTk" >nul 2>nul && set EXTRA=%EXTRA% --hidden-import PIL.ImageTk
echo Extras for this build: %EXTRA%

echo Building exe (takes about a minute)...
%PY% -m PyInstaller --onefile --windowed --clean --name Bambu2AD5X --add-data "%~dp0ad5x_template.json;." --collect-data tkinter %EXTRA% bambu2ad5x_gui.py
if not exist "dist\Bambu2AD5X.exe" (
  echo Build failed - see messages above.
  pause
  exit /b 1
)

copy /y "dist\Bambu2AD5X.exe" "Bambu2AD5X.exe" >nul
rmdir /s /q build dist >nul 2>nul
del /q Bambu2AD5X.spec >nul 2>nul

echo.
echo Done!  Bambu2AD5X.exe is in this folder - double-click it.
echo You can copy just that one file anywhere; it has everything built in.
pause
