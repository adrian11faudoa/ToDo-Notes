# -*- mode: python ; coding: utf-8 -*-
# NoteFlow PyInstaller spec file
# Build: pyinstaller noteflow.spec

import sys
from pathlib import Path

ROOT = Path('.').resolve()
APP_DIR = ROOT / 'app'

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        # Include the SQL schema
        (str(APP_DIR / 'database' / 'schema.sql'), 'app/database'),
        # Include any assets
        (str(APP_DIR / 'assets'), 'app/assets'),
    ],
    hiddenimports=[
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'PySide6.QtNetwork',
        'markdown2',
        'reportlab',
        'reportlab.platypus',
        'reportlab.lib.styles',
        'reportlab.lib.pagesizes',
        'reportlab.lib.units',
        'PIL',
        'PIL.Image',
        'plyer',
        'plyer.platforms.win.notification',
        'schedule',
        'watchdog',
        'watchdog.observers',
        'watchdog.events',
        'sqlite3',
        'json',
        'threading',
        'pathlib',
        'datetime',
        'logging',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'unittest',
        'email',
        'html',
        'http',
        'urllib',
        'xml',
        'xmlrpc',
        'pydoc',
        'doctest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher,
)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='NoteFlow',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,           # No console window on Windows
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # Windows-specific:
    icon=None,               # Set to 'app/assets/icon.ico' if you have one
    version=None,            # Set to a version info file for Windows metadata
    uac_admin=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='NoteFlow',
)
