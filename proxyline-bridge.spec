# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
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
    name='proxyline-bridge',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=True,
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
    name='proxyline-bridge',
)

app = BUNDLE(
    coll,
    name='ProxylineBridge.app',
    icon=None,
    bundle_identifier='com.proxyline.bridge',
    info_plist={
        'LSUIElement': '1', # App runs in background without a dock icon
        'CFBundleName': 'ProxylineBridge',
        'CFBundleDisplayName': 'Proxyline Bridge',
        'CFBundleGetInfoString': 'Proxyline Bridge local server',
        'CFBundleIdentifier': 'com.proxyline.bridge',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
    },
)
