@echo off
REM Gera echo.exe (arquivo unico, sem console extra escondido)
pip install pyinstaller
pyinstaller --onefile --name echo app.py
echo.
echo Pronto: dist\echo.exe
echo Copie dist\echo.exe para onde quiser e rode digitando echo.exe
pause
