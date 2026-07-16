# -*- coding: utf-8 -*-
# PyInstaller spec для fast_clear (генерируется/обновляется build_exe.bat)
# Можно собирать и напрямую: build_exe.bat

block_cipher = None

a = Analysis(
    ['fast_clear/__entry__.py'],
    pathex=[],
    binaries=[],
    datas=[('VERSION', '.')],
    hiddenimports=[
        'fast_clear',
        'fast_clear.gui',
        'fast_clear.cleanup',
        'fast_clear.admin',
        'fast_clear.registry_clean',
        'fast_clear.eventlog_clean',
        'fast_clear.file_clean',
        'fast_clear.self_clean',
        'fast_clear.reg_acl',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='fast_clear',
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
    uac_admin=True,
    uac_uiaccess=False,
)
