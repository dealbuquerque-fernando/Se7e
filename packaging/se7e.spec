# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path

root = Path(SPECPATH).parent
is_macos = sys.platform == "darwin"
icon_path = (
    root / "se7e" / "assets" / ("se7e_icon_v2.icns" if is_macos else "se7e_icon_v2.ico")
)

a = Analysis(
    [str(root / "packaging" / "entry.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[(str(root / "se7e" / "assets"), "se7e/assets")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Se7e",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(icon_path),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Se7e",
)

# BUNDLE only does anything on macOS (PyInstaller no-ops it elsewhere) — it's
# what turns the loose COLLECT output into a real double-clickable Se7e.app
# with an Info.plist, instead of just a folder with a Unix executable in it.
if is_macos:
    app = BUNDLE(
        coll,
        name="Se7e.app",
        icon=str(icon_path),
        bundle_identifier="com.se7e.app",
        info_plist={
            "CFBundleShortVersionString": "1.3.2",
            # A tray-only app: no Dock icon, no menu bar, matching the
            # Windows build's own no-taskbar-window presence.
            "LSUIElement": True,
            "NSHighResolutionCapable": True,
        },
    )
