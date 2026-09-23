#!/usr/bin/env bash
# Wraps dist/Se7e.app (built by `pyinstaller packaging/se7e.spec`) into a
# real macOS .pkg installer with a postinstall script that wires Claude
# Code hooks automatically — the closest equivalent to installer.iss's
# [Run] step on Windows. Needs nothing beyond stock macOS tools.
#
# Unsigned by default (fine for personal use or a locally-built app —
# Gatekeeper only really objects to something downloaded from the
# internet). Once you have an Apple Developer ID ($99/yr,
# developer.apple.com/programs) and a "Developer ID Installer: ..."
# certificate installed (check with `security find-identity -v`), sign it
# with no other changes:
#   SE7E_PKG_SIGN_IDENTITY="Developer ID Installer: Your Name (TEAMID)" \
#     packaging/build_pkg.sh
# Signing here doesn't notarize it — for smooth installs on OTHER
# people's Macs, also notarize the signed .pkg afterwards with
# `xcrun notarytool submit --wait` and `xcrun stapler staple`.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_NAME="Se7e"
APP_PATH="$ROOT/dist/$APP_NAME.app"
PKG_PATH="$ROOT/dist/$APP_NAME.pkg"
IDENTIFIER="com.se7e.app"
VERSION="1.3.4"

if [[ ! -d "$APP_PATH" ]]; then
    echo "error: $APP_PATH not found — run 'pyinstaller packaging/se7e.spec' first" >&2
    exit 1
fi

SIGN_ARGS=()
if [[ -n "${SE7E_PKG_SIGN_IDENTITY:-}" ]]; then
    SIGN_ARGS=(--sign "$SE7E_PKG_SIGN_IDENTITY")
fi

rm -f "$PKG_PATH"
pkgbuild \
    --component "$APP_PATH" \
    --install-location /Applications \
    --scripts "$ROOT/packaging/scripts" \
    --identifier "$IDENTIFIER" \
    --version "$VERSION" \
    "${SIGN_ARGS[@]+"${SIGN_ARGS[@]}"}" \
    "$PKG_PATH"

echo "wrote $PKG_PATH"
if [[ -z "${SE7E_PKG_SIGN_IDENTITY:-}" ]]; then
    echo "note: unsigned — Gatekeeper will warn on any Mac other than the one that built it."
fi
