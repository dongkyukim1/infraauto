# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['infra_auto_gui.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('pricing.db', '.'),
        ('resources/models', 'models'),
        ('resources/icon_auto.ico', 'resources'),
        ('resources/icon_auto.png', 'resources'),
        ('config.py', '.'),
    ],
    hiddenimports=[
        'config',
        'core', 'core.app_path', 'core.database',
        'analysis', 'analysis.engine', 'analysis.building_engine',
        'analysis.llm_engine', 'analysis.llm_analyzer',
        'analysis.ml_predictor', 'analysis.ocr_engine',
        'export', 'export.excel_exporter', 'export.process_mapper',
        'gui', 'gui.styles', 'gui.dialogs', 'gui.workers', 'gui.canvas',
        'statistics',
    ],
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
    icon='resources/icon_auto.ico',
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
