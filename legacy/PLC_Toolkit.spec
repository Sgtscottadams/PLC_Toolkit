# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['plc_toolkit_consolidated.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['pycomm3', 'pycomm3.cip', 'pycomm3.cip.data_types', 'pycomm3.packets', 'pycomm3.utils', 'openpyxl', 'openpyxl.styles', 'openpyxl.worksheet', 'openpyxl.chart', 'xml.etree.ElementTree', 'xml.dom.minidom', 'sqlite3'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'numpy', 'pandas', 'scipy', 'tkinter'],
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
    name='PLC_Toolkit',
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
)
