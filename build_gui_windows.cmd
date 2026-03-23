@echo off
setlocal

cd /d "%~dp0"

echo.
echo ============================================
echo   Littlenet Database - Build GUI Windows
echo ============================================
echo.

py -m pip install -r requirements-build-windows.txt
if errorlevel 1 (
    echo.
    echo No se pudieron instalar las dependencias de build.
    pause
    exit /b 1
)

call build_windows.bat onedir
if errorlevel 1 (
    echo.
    echo La generacion del ejecutable fallo.
    pause
    exit /b 1
)

echo.
echo El ejecutable fue generado en:
echo dist\LittlenetDatabaseGUI\LittlenetDatabaseGUI.exe
echo.
pause
exit /b 0
