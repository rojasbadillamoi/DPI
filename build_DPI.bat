@echo off
:: =============================================================================
:: build_DPI.bat — Script de construcción para Dendro Pixel Interface (DPI)
:: Suite MoiCedrus — Moisés E. Rojas Badilla
::
:: USO:
::   1. Abre una terminal (cmd o PowerShell) en la carpeta del proyecto.
::   2. Ejecuta:  build_DPI.bat
::   3. Al terminar encontrarás el ejecutable en:  dist\DPI\DPI.exe
::
:: REQUISITOS PREVIOS:
::   - Python 3.10+ instalado y en el PATH
::   - Dependencias instaladas:
::       pip install pyinstaller PyQt6 pyqtgraph opencv-python numpy pandas
::                   Pillow scipy openpyxl matplotlib
:: =============================================================================

setlocal EnableDelayedExpansion

:: --- Colores de consola (solo informativo) ---
set "INFO=[INFO]"
set "OK=[OK]"
set "ERR=[ERROR]"

echo.
echo  ============================================================
echo   DPI Build Script — Suite MoiCedrus
echo   Moisés E. Rojas Badilla
echo  ============================================================
echo.

:: --- 1. Verificar Python ---
echo %INFO% Verificando Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo %ERR% Python no encontrado. Instala Python 3.10+ y agrégalo al PATH.
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo %OK% %%v encontrado.

:: --- 2. Verificar PyInstaller ---
echo %INFO% Verificando PyInstaller...
python -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo %INFO% PyInstaller no encontrado. Instalando...
    pip install pyinstaller
    if errorlevel 1 (
        echo %ERR% No se pudo instalar PyInstaller.
        pause
        exit /b 1
    )
)
echo %OK% PyInstaller listo.

:: --- 3. Limpiar compilaciones anteriores ---
echo %INFO% Limpiando compilaciones anteriores...
if exist "build" (
    rmdir /s /q "build"
    echo %OK% Carpeta build eliminada.
)
if exist "dist\DPI" (
    rmdir /s /q "dist\DPI"
    echo %OK% Carpeta dist\DPI eliminada.
)
if exist "DPI.spec" (
    del /q "DPI.spec"
    echo %OK% Archivo DPI.spec eliminado.
)

:: --- 4. Construir con PyInstaller ---
echo.
echo %INFO% Construyendo DPI con PyInstaller...
echo       (Este proceso puede tardar 2-5 minutos)
echo.

:: Opciones de PyInstaller:
::   --name DPI              : nombre del ejecutable y carpeta de salida
::   --onedir                : carpeta con todos los archivos (más rápido que --onefile)
::   --windowed              : no muestra ventana de consola al ejecutar
::   --noconfirm             : sobreescribe sin preguntar
::   --add-data              : incluye archivos de datos adicionales
::   --hidden-import         : módulos que PyInstaller no detecta automáticamente
::   --collect-all pyqtgraph : incluye todos los recursos de pyqtgraph

python -m PyInstaller ^
    --name "DPI" ^
    --onedir ^
    --windowed ^
    --noconfirm ^
    --icon "iconos\dpi.ico" ^
    --add-data "species_profiles.json;." ^
    --add-data "iconos\dpi.ico;iconos" ^
    --hidden-import "PyQt6.QtPrintSupport" ^
    --hidden-import "pyqtgraph.graphicsItems.ViewBox.axisCtrlTemplate_pyqt6" ^
    --hidden-import "pyqtgraph.graphicsItems.PlotItem.plotConfigTemplate_pyqt6" ^
    --hidden-import "pyqtgraph.imageview.ImageViewTemplate_pyqt6" ^
    --hidden-import "pandas._libs.tslibs.np_datetime" ^
    --hidden-import "pandas._libs.tslibs.nattype" ^
    --hidden-import "pandas._libs.tslibs.timedeltas" ^
    --hidden-import "scipy.special._cython_special" ^
    --collect-all "pyqtgraph" ^
    --collect-all "cv2" ^
    main_anillos.py

if errorlevel 1 (
    echo.
    echo %ERR% La construcción falló. Revisa los mensajes anteriores.
    pause
    exit /b 1
)

:: --- 5. Verificar resultado ---
if not exist "dist\DPI\DPI.exe" (
    echo %ERR% No se encontró DPI.exe en dist\DPI. Algo salió mal.
    pause
    exit /b 1
)

:: --- 6. Copiar archivos de datos adicionales ---
echo %INFO% Copiando archivos de datos...

:: species_profiles.json (por si PyInstaller no lo copió correctamente)
if exist "species_profiles.json" (
    copy /y "species_profiles.json" "dist\DPI\species_profiles.json" >nul
    echo %OK% species_profiles.json copiado.
)

:: iconos (si existen en la carpeta iconos/)
if exist "iconos" (
    xcopy /s /q /y "iconos" "dist\DPI\iconos\" >nul
    echo %OK% Carpeta iconos copiada.
)

:: --- 7. Crear lanzador auxiliar (opcional: para debug desde consola) ---
echo %INFO% Creando lanzador de depuración...
(
    echo @echo off
    echo cd /d "%%~dp0"
    echo DPI.exe
    echo if errorlevel 1 pause
) > "dist\DPI\Iniciar_DPI.bat"
echo %OK% Iniciar_DPI.bat creado en dist\DPI\.

:: --- 8. Resumen final ---
echo.
echo  ============================================================
echo   BUILD COMPLETADO
echo  ============================================================
echo.
echo   Ejecutable:  dist\DPI\DPI.exe
echo   Tamaño carpeta:
for /f "tokens=3" %%s in ('dir "dist\DPI" /s /-c ^| findstr "archivos"') do (
    set SIZE=%%s
)
echo     !SIZE! bytes aprox.
echo.
echo   Próximo paso:
echo     - Para distribuir como carpeta portable: comprime dist\DPI en un .zip
echo     - Para crear instalador .exe: abre DPI_setup.iss con Inno Setup
echo.

pause
endlocal
