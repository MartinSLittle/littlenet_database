@echo off
setlocal

set BUILD_MODE=%~1
if "%BUILD_MODE%"=="" set BUILD_MODE=onedir

if /I not "%BUILD_MODE%"=="onedir" if /I not "%BUILD_MODE%"=="onefile" (
    echo Uso: build_windows.bat [onedir^|onefile]
    exit /b 1
)

set SCRIPT_DIR=%~dp0
pushd "%SCRIPT_DIR%"

echo.
echo ============================================
echo   Littlenet Database - Build GUI Windows
echo ============================================
echo.
echo Building Windows executable in %BUILD_MODE% mode...
echo.

py -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo Instalando dependencias de build...
    py -m pip install -r requirements-build-windows.txt
    if errorlevel 1 (
        echo.
        echo No se pudieron instalar las dependencias de build.
        popd
        exit /b 1
    )
)

set LITTLENET_BUILD_MODE=%BUILD_MODE%
py -m PyInstaller --noconfirm --clean pyinstaller\windows_gui.spec
if errorlevel 1 (
    echo.
    echo La build fallo.
    popd
    exit /b 1
)

echo.
if /I "%BUILD_MODE%"=="onedir" (
    echo Build completada.
    echo Ejecutable: dist\LittlenetDatabaseGUI\LittlenetDatabaseGUI.exe
) else (
    echo Build completada.
    echo Ejecutable: dist\LittlenetDatabaseGUI.exe
)

popd
exit /b 0
