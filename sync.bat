@echo off
setlocal
echo ===================================================
echo   Sincronizando fnkMudarResolucao com GitHub...
echo ==================================================
git pull --rebase origin main
if %ERRORLEVEL% NEQ 0 (
    git pull origin main
)
echo.
echo ===================================================
echo   Enviando alteracoes locais para o GitHub...
echo ==================================================
git add .
git diff-index --quiet HEAD >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    git commit -m "sync: sincronizacao automatica"
    git push origin main
) else (
    echo Tudo sincronizado!
)
echo.
echo [CONCLUIDO] 100% Sincronizado!
timeout /t 3
