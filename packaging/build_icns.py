"""Generate se7e_icon_v2.icns from the app's own procedural icon badge
(se7e.tray_ui_qt.make_icon_image) instead of upscaling the low-res .ico —
a crisp 512px source downscales sharp at every iconset size, upscaling a
256px one (the .ico's largest embedded frame) would look pixelated.

macOS only (needs iconutil). Run manually when the badge design changes:
    python packaging/build_icns.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from se7e.tray_ui_qt import make_icon_image  # noqa: E402
from se7e.ui_colors import STATUS_COLORS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "se7e" / "assets"
ICON_COLOR = STATUS_COLORS["parado"]  # neutral idle gray — the app's resting badge

# Apple's iconset naming convention: each base size plus its @2x (Retina) variant.
ICONSET_BASE_SIZES = (16, 32, 128, 256, 512)


def main() -> None:
    if sys.platform != "darwin":
        raise SystemExit("build_icns.py needs macOS's iconutil")

    iconset_dir = ASSETS / "se7e_icon_v2.iconset"
    if iconset_dir.exists():
        shutil.rmtree(iconset_dir)
    iconset_dir.mkdir()

    for size in ICONSET_BASE_SIZES:
        make_icon_image(ICON_COLOR, size).save(iconset_dir / f"icon_{size}x{size}.png")
        make_icon_image(ICON_COLOR, size * 2).save(iconset_dir / f"icon_{size}x{size}@2x.png")

    icns_path = ASSETS / "se7e_icon_v2.icns"
    subprocess.run(
        ["iconutil", "-c", "icns", str(iconset_dir), "-o", str(icns_path)],
        check=True,
    )
    shutil.rmtree(iconset_dir)
    print(f"wrote {icns_path}")


if __name__ == "__main__":
    main()
