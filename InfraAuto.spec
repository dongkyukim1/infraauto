# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['infra_auto_gui.py'],
    pathex=[],
    binaries=[],
    datas=[('pricing.db', '.'), ('models', 'models'), ('sample_historical_data.csv', '.')],
    hiddenimports=['app_path', 'building_engine', 'process_mapper', 'ml_predictor', 'database', 'engine'],
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
    name='InfraAuto',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['icon_auto.icns'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='InfraAuto',
)
app = BUNDLE(
    coll,
    name='InfraAuto.app',
    icon='icon_auto.icns',
    bundle_identifier=None,
)
