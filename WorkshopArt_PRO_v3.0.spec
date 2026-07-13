# -*- mode: python ; coding: utf-8 -*-

import os
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

ctk_datas = collect_data_files('customtkinter')

# Playwright driver
try:
    from playwright._impl._driver import compute_driver_executable
    _pw_node, _pw_cli = compute_driver_executable()
    import pathlib as _pl
    _pw_driver_dir = _pl.Path(_pw_node).parent
    pw_binaries = [
        (str(_pw_node), 'playwright/driver'),
    ]
    pw_datas = collect_data_files('playwright')
    pw_datas = [(s, d) for s, d in pw_datas if 'node.exe' not in s.lower()]
except Exception as _e:
    print(f"Warning: no se pudo recopilar playwright: {_e}")
    pw_binaries = []
    pw_datas = []

# realesrgan-ncnn-py data files (optional PRO bindings)
try:
    realesr_datas = collect_data_files('realesrgan_ncnn_py')
except Exception:
    realesr_datas = []

# rife-ncnn-py data files (optional PRO bindings)
try:
    rife_datas = collect_data_files('rife_ncnn_py')
except Exception:
    rife_datas = []

a = Analysis(
    ['main.py'],
    pathex=['src'],
    binaries=[] + pw_binaries,
    datas=[
        ('src/*.py', 'src'),
    ] + ctk_datas + pw_datas + realesr_datas + rife_datas,
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
        '_pro_features',
        'customtkinter',
        'upload_tool', 'steam_uploader',
        'browser_cookie3',
        'GPUtil', 'gputil',
        'pygifsicle',
        'realesrgan_ncnn_py',
        # 'rife_ncnn_py',  # no en PyPI, se usa subprocess
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    exclude_binaries=False,
    name='WorkshopArt',
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
    onefile=True,
)
