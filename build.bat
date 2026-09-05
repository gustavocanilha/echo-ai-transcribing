@echo off
REM Gera echo.exe (arquivo unico, sem console extra escondido)
cd /d "%~dp0"
pip install pyinstaller
python -m PyInstaller --onefile --name echo app.py
echo.
echo Pronto: dist\echo.exe
echo Copie dist\echo.exe para onde quiser e rode digitando echo.exe
pause
