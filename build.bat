@echo off
chcp 65001 >nul 2>&1
REM ============================================================================
REM Compila AnalizadorCBFI.exe en Windows
REM ============================================================================

echo.
echo ====================================================================
echo    COMPILADOR DE ANALIZADOR CBFI
echo    Genera dist\AnalizadorCBFI.exe
echo ====================================================================
echo.

REM ---------------------------------------------------------------------------
REM [1/4] Python
REM ---------------------------------------------------------------------------
echo [1/4] Verificando Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo   ERROR: Python no esta instalado o no esta en PATH
    echo   Descarga desde: https://www.python.org/downloads/
    echo   IMPORTANTE: marca "Add Python to PATH" al instalar
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo   OK - %%v

REM ---------------------------------------------------------------------------
REM [2/4] PyInstaller
REM Se invoca SIEMPRE como "python -m PyInstaller".
REM El ejecutable pyinstaller.exe suele quedar fuera del PATH en Windows.
REM ---------------------------------------------------------------------------
echo.
echo [2/4] Verificando PyInstaller...
python -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo   PyInstaller no disponible. Instalando...
    python -m pip install --upgrade pip
    python -m pip install pyinstaller
    python -m PyInstaller --version >nul 2>&1
    if errorlevel 1 (
        echo   ERROR: No se pudo instalar PyInstaller
        pause
        exit /b 1
    )
)
for /f "tokens=*" %%v in ('python -m PyInstaller --version 2^>^&1') do echo   OK - PyInstaller %%v

echo.
echo       Verificando yfinance (descarga de precios)...
python -c "import yfinance, pypdf" >nul 2>&1
if errorlevel 1 (
    echo       yfinance no disponible. Instalando...
    python -m pip install yfinance pypdf
    python -c "import yfinance" >nul 2>&1
    if errorlevel 1 (
        echo   ERROR: No se pudo instalar yfinance
        pause
        exit /b 1
    )
)
echo   OK - yfinance disponible

REM ---------------------------------------------------------------------------
REM [3/4] Limpiar
REM ---------------------------------------------------------------------------
echo.
echo [3/4] Limpiando builds anteriores...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
echo   OK - Directorio limpio

REM ---------------------------------------------------------------------------
REM [4/4] Compilar
REM --workpath (NO --buildpath, esa opcion no existe)
REM --console y --windowed son mutuamente excluyentes: solo se pasa --console
REM ---------------------------------------------------------------------------
echo.
echo [4/4] Compilando AnalizadorCBFI.exe...
echo   (2-5 minutos: yfinance arrastra pandas y numpy)
echo.

REM --collect-all: yfinance carga modulos en runtime que el analisis estatico
REM de PyInstaller no detecta, y curl_cffi trae binarios nativos. Sin esto el
REM .exe compila pero truena al descargar.
python -m PyInstaller ^
    --name AnalizadorCBFI ^
    --onefile ^
    --console ^
    --collect-all yfinance ^
    --collect-all curl_cffi ^
    --hidden-import pypdf ^
    --hidden-import extraer_reportes ^
    --distpath dist ^
    --workpath build ^
    --specpath build ^
    --noconfirm ^
    analizar_cbfi.py

if errorlevel 1 (
    echo.
    echo   ERROR: La compilacion fallo. Revisa el log de arriba.
    pause
    exit /b 1
)

if not exist "dist\AnalizadorCBFI.exe" (
    echo.
    echo   ERROR: PyInstaller termino sin error pero no genero el .exe
    pause
    exit /b 1
)

REM ---------------------------------------------------------------------------
REM Resultado
REM ---------------------------------------------------------------------------
echo.
echo ====================================================================
echo    COMPILACION EXITOSA
echo ====================================================================
echo.
echo   Archivo: dist\AnalizadorCBFI.exe
echo.
echo   Para ejecutarlo:
echo      .\dist\AnalizadorCBFI.exe
echo.
echo   Es portable: funciona en cualquier Windows 64-bit
echo   sin necesidad de tener Python instalado.
echo.
pause
