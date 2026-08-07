#!/usr/bin/env python3
"""
Compila AnalizadorCBFI.exe con PyInstaller.

Alternativa multiplataforma a build.bat. Invoca PyInstaller como
`python -m PyInstaller` para no depender de que pyinstaller.exe
este en el PATH (problema comun en Windows).

Uso:
    python build_exe.py
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

APP_NAME = "AnalizadorCBFI"
ENTRY_POINT = "analizar_cbfi.py"


def step(number, text):
    print(f"[{number}/4] {text}...")


def ok(text):
    print(f"  OK - {text}\n")


def die(text):
    print(f"\n  ERROR: {text}\n")
    sys.exit(1)


def check_python():
    step(1, "Verificando Python")
    if sys.version_info < (3, 7):
        die(f"Python {sys.version.split()[0]} es muy viejo. Necesitas 3.7+")
    ok(f"Python {sys.version.split()[0]}")


def check_yfinance():
    """yfinance se necesita en tiempo de build para que PyInstaller lo empaque."""
    try:
        import yfinance, pypdf  # noqa: F401
        return
    except ImportError:
        pass

    print("  yfinance no disponible. Instalando...")
    if subprocess.run([sys.executable, "-m", "pip", "install", "yfinance", "pypdf"]).returncode != 0:
        die("No se pudo instalar yfinance")
    try:
        import yfinance  # noqa: F401
    except ImportError:
        die("yfinance se instalo pero no se puede importar")


def check_pyinstaller():
    step(2, "Verificando PyInstaller")

    def version():
        result = subprocess.run(
            [sys.executable, "-m", "PyInstaller", "--version"],
            capture_output=True,
            text=True,
        )
        return result.stdout.strip() if result.returncode == 0 else None

    installed = version()
    if installed is None:
        print("  PyInstaller no disponible. Instalando...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "pyinstaller"]
        )
        if result.returncode != 0:
            die("No se pudo instalar PyInstaller")
        installed = version()
        if installed is None:
            die("PyInstaller se instalo pero no se puede invocar")

    ok(f"PyInstaller {installed}")
    print("  Verificando yfinance (descarga de precios)...")
    check_yfinance()
    ok("yfinance disponible")


def clean():
    step(3, "Limpiando builds anteriores")
    for directory in ("build", "dist"):
        if os.path.isdir(directory):
            shutil.rmtree(directory)
            print(f"  - eliminado {directory}/")
    ok("Directorio limpio")


def build():
    step(4, f"Compilando {APP_NAME}")
    print("  (30-60 segundos, paciencia)\n")

    args = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name", APP_NAME,
        "--onefile",
        "--console",
        # yfinance carga modulos en runtime que el analisis estatico no ve, y
        # curl_cffi trae binarios nativos. Sin esto el .exe compila pero
        # truena al intentar descargar precios.
        "--collect-all", "yfinance",
        "--collect-all", "curl_cffi",
        "--hidden-import", "pypdf",
        "--hidden-import", "extraer_reportes",
        "--distpath", "dist",
        # --workpath, NO --buildpath: esa opcion no existe en PyInstaller.
        "--workpath", "build",
        "--specpath", "build",
        "--noconfirm",
        ENTRY_POINT,
    ]

    # Sin capture_output: el log de PyInstaller se ve en vivo, que es
    # justo lo que hace falta cuando algo falla.
    result = subprocess.run(args)
    if result.returncode != 0:
        die("La compilacion fallo. Revisa el log de arriba.")

    exe = Path("dist") / (APP_NAME + (".exe" if os.name == "nt" else ""))
    if not exe.exists():
        die("PyInstaller termino sin error pero no genero el ejecutable")

    ok(f"{exe.name} generado ({exe.stat().st_size / (1024 * 1024):.1f} MB)")
    return exe


def main():
    print(f"\n{'=' * 68}\n   COMPILADOR DE {APP_NAME}\n{'=' * 68}\n")

    if not os.path.exists(ENTRY_POINT):
        die(
            f"No se encontro {ENTRY_POINT}.\n"
            f"  Ejecuta este script desde la carpeta del proyecto."
        )

    try:
        check_python()
        check_pyinstaller()
        clean()
        exe = build()
    except KeyboardInterrupt:
        print("\n\nCompilacion cancelada.")
        sys.exit(1)

    print(f"{'=' * 68}\n   COMPILACION EXITOSA\n{'=' * 68}\n")
    print(f"  Archivo: {exe.resolve()}\n")
    print("  Para ejecutarlo:")
    print(f"     .{os.sep}{exe}\n")
    print("  Es portable: no necesita Python instalado.\n")


if __name__ == "__main__":
    main()
