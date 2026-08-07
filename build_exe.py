#!/usr/bin/env python3
"""
Build script para compilar AnalizadorCBFI.exe
Alternativa a build.bat si tienes problemas con el batch script
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path


def print_header(text):
    """Imprime un encabezado formateado"""
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70 + "\n")


def print_step(number, text):
    """Imprime un paso numerado"""
    print(f"[{number}/4] {text}...")


def print_success(text):
    """Imprime un mensaje de éxito"""
    print(f"  ✓ {text}\n")


def print_error(text, exit_code=1):
    """Imprime un error y sale"""
    print(f"\n  ✗ ERROR: {text}\n")
    sys.exit(exit_code)


def check_python():
    """Verifica que Python esté disponible"""
    print_step(1, "Verificando Python")

    if sys.version_info < (3, 7):
        print_error(f"Python {sys.version} es muy viejo. Necesitas Python 3.7+")

    print_success(f"Python {sys.version.split()[0]} encontrado")


def check_pyinstaller():
    """Verifica que PyInstaller esté instalado"""
    print_step(2, "Verificando PyInstaller")

    try:
        import PyInstaller
        print_success("PyInstaller encontrado")
    except ImportError:
        print("  ⚠ PyInstaller no está instalado. Instalando...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "pyinstaller"],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            print_error("No se pudo instalar PyInstaller")

        print_success("PyInstaller instalado")


def clean_build():
    """Limpia builds anteriores"""
    print_step(3, "Limpiando builds anteriores")

    dirs_to_remove = ['build', 'dist']
    files_to_remove = ['AnalizadorCBFI.spec']

    for dir_name in dirs_to_remove:
        if os.path.exists(dir_name):
            shutil.rmtree(dir_name)
            print(f"  • Eliminado: {dir_name}/")

    for file_name in files_to_remove:
        if os.path.exists(file_name):
            os.remove(file_name)
            print(f"  • Eliminado: {file_name}")

    print_success("Directorio limpio")


def build_exe():
    """Compila el ejecutable con PyInstaller"""
    print_step(4, "Compilando AnalizadorCBFI.exe")
    print("  (Esto puede tardar 30-60 segundos...)\n")

    # Parámetros de compilación
    args = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name=AnalizadorCBFI",
        "--onefile",
        "--console",
        "--distpath=dist",
        "--buildpath=build",
        "--specpath=.",
        "analizar_cbfi.py"
    ]

    # Ejecutar PyInstaller
    result = subprocess.run(args, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"  STDOUT:\n{result.stdout}")
        print(f"  STDERR:\n{result.stderr}")
        print_error("La compilación falló")

    # Verificar que el exe se generó
    exe_path = Path("dist") / "AnalizadorCBFI.exe"
    if not exe_path.exists():
        print_error("No se generó el archivo .exe")

    file_size_mb = exe_path.stat().st_size / (1024 * 1024)
    print_success(f"AnalizadorCBFI.exe generado ({file_size_mb:.1f} MB)")


def show_success_message():
    """Muestra mensaje de éxito final"""
    print_header("✓ COMPILACIÓN EXITOSA")

    exe_path = Path("dist") / "AnalizadorCBFI.exe"

    print("📦 Archivo generado:")
    print(f"   {exe_path.resolve()}\n")

    print("📋 Lo que puedes hacer ahora:\n")
    print("   1. EJECUTAR desde PowerShell:")
    print("      .\\dist\\AnalizadorCBFI.exe\n")
    print("   2. HACER CLIC DIRECTO:")
    print("      dist\\AnalizadorCBFI.exe\n")
    print("   3. CREAR ACCESO DIRECTO:")
    print("      Clic derecho → Enviar a → Escritorio\n")
    print("   4. COMPARTIR:")
    print("      El archivo es portable (no necesita Python)\n")

    print("📂 Carpetas generadas:")
    print("   dist/        → Tu ejecutable (.exe)")
    print("   build/       → Archivos temporales")
    print("   *.spec       → Configuración de PyInstaller\n")

    print("🎯 Tips:")
    print("   • Copia dist\\AnalizadorCBFI.exe a cualquier lugar")
    print("   • Funciona sin necesidad de Python instalado")
    print("   • Tamaño típico: 40-60 MB")
    print("   • Algunos antivirus pueden alertar (es normal)\n")


def main():
    """Función principal"""

    print("""
╔════════════════════════════════════════════════════════════════════╗
║         COMPILADOR DE ANALIZADOR CBFI v1.0                        ║
║            Genera AnalizadorCBFI.exe para Windows                  ║
╚════════════════════════════════════════════════════════════════════╝
    """)

    # Verificar que analizar_cbfi.py existe
    if not os.path.exists("analizar_cbfi.py"):
        print_error(
            "No se encontró analizar_cbfi.py\n"
            "Asegúrate de estar en la carpeta correcta"
        )

    try:
        # Ejecutar pasos
        check_python()
        check_pyinstaller()
        clean_build()
        build_exe()

        # Mostrar resultado
        show_success_message()

    except KeyboardInterrupt:
        print("\n\n❌ Compilación cancelada por el usuario")
        sys.exit(1)
    except Exception as e:
        print_error(f"Error inesperado: {e}")


if __name__ == "__main__":
    main()
