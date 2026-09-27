# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build of WorkshopArt.exe (single file, no console).

    pip install -r requirements.txt pyinstaller playwright browser_cookie3
    pyinstaller WorkshopArt.spec

Every module under src/ is found by following the imports of main.py. The
optional packages (Playwright for the Upload Tool, browser_cookie3,
realesrgan-ncnn-py) are bundled only when installed in the build environment.
"""
from PyInstaller.utils.hooks import collect_data_files

datas = collect_data_files("customtkinter")
binaries = []
hiddenimports = ["upload_tool", "steam_uploader"]

# Playwright: its Node driver must travel with the exe for the Upload Tool.
try:
    from playwright._impl._driver import compute_driver_executable
    node_exe, _cli = compute_driver_executable()
    binaries.append((str(node_exe), "playwright/driver"))
    datas += [(src, dst) for src, dst in collect_data_files("playwright")
              if "node.exe" not in src.lower()]
    hiddenimports.append("playwright.sync_api")
except Exception as error:  # optional
    print(f"Playwright no incluido: {error}")

for optional in ("browser_cookie3", "realesrgan_ncnn_py"):
    try:
        __import__(optional)
        hiddenimports.append(optional)
        datas += collect_data_files(optional, include_py_files=False)
    except ImportError:
        print(f"{optional} no incluido (opcional)")

a = Analysis(
    ["main.py"],
    pathex=["src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["torch", "tensorflow", "sklearn", "scipy", "pandas", "IPython",
              "notebook", "pytest", "moviepy"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="WorkshopArt",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=None,
)
