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
# win32timezone isn't found by PyInstaller's static import analysis (it's
# pulled in dynamically by pywin32's COM marshalling, not a plain top-level
# import anywhere in this codebase) but is needed at runtime the moment any
# COM call touches a date/time-bearing object - hardening.py's Task
# Scheduler COM API use (win32com.client.Dispatch("Schedule.Service")) reads
# back and re-registers a task definition whose Triggers carry date fields,
# so this needs to be listed explicitly or it fails only at that runtime
# call, not at build time.
hiddenimports = ['win32timezone']
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
    # Fixed, not None/random: every "Failed to load Python DLL" dialog
    # seen in real testing quoted a path under
    # C:\Users\<user>\AppData\Local\Temp\_MEIxxxxxx - the DEFAULT onefile
    # extraction location, which is NOT covered by the Windows Defender
    # exclusion hardening.py adds for C:\ProgramData\SentinelDesk (see
    # _add_defender_exclusion). Pointing extraction at a fixed path INSIDE
    # that already-excluded folder means Defender never gets a chance to
    # lock/scan the freshly-extracted python312.dll mid-launch. A fixed
    # path also means the bootloader reuses an already-extracted,
    # matching-hash copy on repeat launches instead of re-extracting every
    # single time (a real PyInstaller behavior, not a hack) - fewer
    # extractions is itself fewer chances for this to happen at all.
    runtime_tmpdir=r'C:\ProgramData\SentinelDesk\_runtime',
    console=False,
    # True, not False: main.py's own try/except around run() (see
    # __main__) already catches and quietly logs everything that matters,
    # so this is just a second layer of defense for the one case Python
    # code can't cover (a crash before __main__ even runs) - deployed to
    # employee laptops, this process must never show a crash dialog, full
    # stop, not even in that edge case.
    disable_windowed_traceback=True,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
