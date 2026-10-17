# -*- mode: python ; coding: utf-8 -*-
#
# Build with (from this `agent/` directory, venv activated):
#   pyinstaller --clean --noconfirm SentinelDeskWatchdog.spec
#
# Output: dist/SentinelDeskWatchdog/SentinelDeskWatchdog.exe — a separate,
# tiny Windows Service (see services/hardening.py for why this is a separate
# binary rather than a mode of the main agent exe).
#
# Built as onedir (a folder), not onefile: onefile extracts pywin32's
# compiled extensions (pywintypes/pythoncom) into a fresh per-run temp
# folder every launch, and that extraction — reliable for an interactive
# admin session — silently failed when Windows' Service Control Manager
# started this as a real SYSTEM-context service (SCM just reported "did not
# respond in a timely fashion", nothing more specific). onedir keeps every
# DLL sitting right next to the exe permanently, so there's nothing to
# extract and nothing that can fail that way. win32timezone is an explicit
# hidden import because pywin32's service framework imports it lazily in a
# way PyInstaller's static analysis doesn't always catch on its own.
a = Analysis(
    ['src/services/watchdog_service.py'],
    pathex=['src'],
    binaries=[],
    datas=[],
    hiddenimports=['win32timezone'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SentinelDeskWatchdog',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SentinelDeskWatchdog',
)
