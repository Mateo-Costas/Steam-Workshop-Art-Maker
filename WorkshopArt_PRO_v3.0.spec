# -*- mode: python ; coding: utf-8 -*-

import os
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

ctk_datas = collect_data_files('customtkinter')

a = Analysis(
    ['main.py'],
    pathex=['src'],
    binaries=[],
    datas=[
        ('src/*.py', 'src'),
    ] + ctk_datas,
    hiddenimports=[
        'PIL.Image', 'PIL.ImageTk', 'PIL.ImageSequence', 'PIL.ImageEnhance',
        'PIL.ImageDraw', 'PIL.ImageFont',
        'moviepy.editor',
        'numpy',
        'cv2',
        'matplotlib', 'matplotlib.pyplot', 'matplotlib.backends.backend_agg',
        'requests',
        'tqdm',
        'windnd',
        'gui', 'gui_methods', 'processor', 'models', 'analyzers',
        'config', 'theme_PRO', 'quality_report', 'fragment_preview', 'i18n',
        'customtkinter',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'torch', 'tensorflow', 'sklearn', 'scipy', 'pandas',
        'IPython', 'notebook', 'pytest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='WorkshopArtPRO',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='WorkshopArtPRO',
)
