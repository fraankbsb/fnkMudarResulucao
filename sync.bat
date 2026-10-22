@echo off
setlocal
cd /d "%~dp0"
python sync.py %*
set "taskExit=%ERRORLEVEL%"
if not "%taskExit%"=="0" echo A sincronizacao falhou. Nenhuma alteracao foi descartada.
pause
exit /b %taskExit%
