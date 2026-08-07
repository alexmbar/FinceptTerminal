# -*- mode: python ; coding: utf-8 -*-
#
# Spec de PyInstaller para AnalizadorCBFI (modo onefile).
# Probado contra PyInstaller 6.x, que es lo que instala `pip install pyinstaller` hoy.
#
# Uso:
#     python -m PyInstaller analizar_cbfi.spec
#
# Normalmente NO hace falta usar este archivo: build.bat y build_exe.py
# generan su propio spec. Esto es para cuando quieras personalizar el build
# (icono, datos embebidos, hiddenimports).

a = Analysis(
    ['analizar_cbfi.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

# onefile: todo va dentro del EXE, por eso no hay COLLECT.
# (Un COLLECT aqui produciria ademas una carpeta suelta que contradice el onefile.)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='AnalizadorCBFI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # p.ej. 'fincept_icon.ico'
)
