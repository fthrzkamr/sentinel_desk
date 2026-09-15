# -*- mode: python ; coding: utf-8 -*-
#
# Build with (from this `agent/` directory, venv activated):
#   pyinstaller --clean --noconfirm SentinelDeskAgent.spec
#
# Output: dist/SentinelDeskAgent.exe (single file, no console window — logs
# go to logs/agent.log next to the exe, not stdout). collect_all() is needed
# for winsdk/aiortc/av/pylibsrtp because they ship native DLLs and/or
# WinRT/WinMD metadata that PyInstaller's default import analysis can't find
# on its own; leaving any of them out produces an exe that builds fine but
# fails at import time when that feature is actually used (WinRT location,
# WebRTC, screen capture).
from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = []
tmp_ret = collect_all('winsdk')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('aiortc')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('av')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('pylibsrtp')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['src/main.py'],
    pathex=['src'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
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
    a.binaries,
    a.datas,
    [],
    name='SentinelDeskAgent',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
