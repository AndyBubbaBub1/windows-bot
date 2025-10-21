# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for building the desktop console on Windows."""

import pathlib
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

project_root = pathlib.Path(__file__).resolve().parents[1]
config_root = project_root / "moex_bot"

datas = [(str(config_root / "config.yaml"), "config")]
config_dir = config_root / "config.d"
if config_dir.exists():
    for pattern in ("*.yml", "*.yaml"):
        for fragment in config_dir.glob(pattern):
            datas.append((str(fragment), "config.d"))

hiddenimports = collect_submodules("moex_bot")


a = Analysis(
    ['packaging/desktop_entry.py'],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
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
    [],
    exclude_binaries=True,
    name='moex-bot-desktop',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='moex-bot-desktop',
)
