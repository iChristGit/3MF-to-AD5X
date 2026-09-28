@echo off
cd /d "%~dp0"
where pyw >nul 2>nul && (start "" pyw bambu2ad5x_gui.py & exit /b)
start "" pythonw bambu2ad5x_gui.py
