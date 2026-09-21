#!/usr/bin/env bash
# Wraps dist/Se7e.app (built by `pyinstaller packaging/se7e.spec`) into a
# drag-to-Applications .dmg — the closest macOS equivalent to installer.iss's
# job on Windows. Needs nothing beyond stock macOS tools (hdiutil).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_NAME="Se7e"
APP_PATH="$ROOT/dist/$APP_NAME.app"
DMG_PATH="$ROOT/dist/$APP_NAME.dmg"

if [[ ! -d "$APP_PATH" ]]; then
    echo "error: $APP_PATH not found — run 'pyinstaller packaging/se7e.spec' first" >&2
    exit 1
fi

STAGING_DIR="$(mktemp -d)"
trap 'rm -rf "$STAGING_DIR"' EXIT

cp -R "$APP_PATH" "$STAGING_DIR/"
ln -s /Applications "$STAGING_DIR/Applications"

rm -f "$DMG_PATH"
hdiutil create -volname "$APP_NAME" -srcfolder "$STAGING_DIR" -ov -format UDZO "$DMG_PATH"

echo "wrote $DMG_PATH"
