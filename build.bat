@echo off
REM ============================================================================
REM Script para compilar AnalizadorCBFI.exe en Windows
REM Autor: Claude
REM ============================================================================

echo.
echo ╔════════════════════════════════════════════════════════════════════╗
echo ║         COMPILADOR DE ANALIZADOR CBFI v1.0                        ║
echo ║            Genera AnalizadorCBFI.exe para Windows                  ║
echo ╚════════════════════════════════════════════════════════════════════╝
echo.

REM ============================================================================
REM PASO 1: Verificar instalaciones
REM ============================================================================

echo [1/4] Verificando Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python no está instalado o no está en PATH
    echo Descarga desde: https://www.python.org/downloads/
    pause
    exit /b 1
)
echo ✓ Python encontrado

echo.
echo [2/4] Verificando PyInstaller...
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo ⚠ PyInstaller no está instalado. Instalando...
    pip install pyinstaller
    if errorlevel 1 (
        echo ERROR: No se pudo instalar PyInstaller
        pause
        exit /b 1
    )
)
echo ✓ PyInstaller encontrado

REM ============================================================================
REM PASO 2: Limpiar builds anteriores
REM ============================================================================

echo.
echo [3/4] Limpiando builds anteriores...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist AnalizadorCBFI.spec del AnalizadorCBFI.spec
echo ✓ Directorio limpio

REM ============================================================================
REM PASO 3: Compilar con PyInstaller
REM ============================================================================

echo.
echo [4/4] Compilando AnalizadorCBFI.exe...
echo (Esto puede tardar 30-60 segundos...)
echo.

pyinstaller --name=AnalizadorCBFI ^
            --onefile ^
            --console ^
            --windowed=False ^
            --distpath=.\dist ^
            --buildpath=.\build ^
            --specpath=. ^
            analizar_cbfi.py

if errorlevel 1 (
    echo.
    echo ERROR: La compilación falló
    pause
    exit /b 1
)

REM ============================================================================
REM PASO 4: Confirmación y instrucciones
REM ============================================================================

echo.
echo ╔════════════════════════════════════════════════════════════════════╗
echo ║              ✓ COMPILACIÓN EXITOSA                                ║
echo ╚════════════════════════════════════════════════════════════════════╝
echo.
echo 📦 Archivo generado: dist\AnalizadorCBFI.exe
echo.
echo 📋 Lo que puedes hacer ahora:
echo.
echo   1. OPCIÓN A: Ejecutar desde PowerShell
echo      .\dist\AnalizadorCBFI.exe
echo.
echo   2. OPCIÓN B: Hacer clic en el archivo
echo      Abre: dist\AnalizadorCBFI.exe
echo.
echo   3. OPCIÓN C: Compartir el exe
echo      El archivo en dist\ es portable y no necesita Python
echo.
echo 📂 Carpetas generadas:
echo      dist\        → Tu ejecutable (.exe)
echo      build\       → Archivos temporales de compilación
echo      *.spec       → Configuración de PyInstaller
echo.
echo 🎯 Tips:
echo    • Copia dist\AnalizadorCBFI.exe a cualquier lugar
echo    • Funciona sin necesidad de Python instalado
echo    • Tamaño típico: 40-60 MB
echo    • Algunos antivirus pueden alertar (es normal en .exe generados)
echo.
pause
