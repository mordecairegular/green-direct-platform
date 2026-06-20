# -*- mode: python ; coding: utf-8 -*-

datas = [('src', 'src'), ('config', 'config'), ('samples', 'samples'), ('docs', 'docs')]
binaries = []
hiddenimports = ['tkinter', 'yaml', 'openpyxl', 'xlsxwriter']


a = Analysis(
    ['packaging\\pyinstaller\\run_batch_trial_tool.py'],
    pathex=['src'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'streamlit',
        'plotly',
        'matplotlib',
        'pytest',
        'pyarrow',
        'pandas.tests',
        'numpy.tests',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='GreenDirectBatchTrial',
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
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='GreenDirectBatchTrial',
)
