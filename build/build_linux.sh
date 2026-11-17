#!/usr/bin/env bash
# Build a portable Linux folder and tarball for AutoClicker.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VERSION="$(python -c "from novaclick import __version__; print(__version__)")"
DIST="$ROOT/build/dist-linux"
WORK="$ROOT/build/work-linux"

python -m PyInstaller \
  --noconfirm --clean --windowed \
  --name AutoClicker \
  --distpath "$DIST" \
  --workpath "$WORK" \
  --specpath "$ROOT/build" \
  "$ROOT/main.py"

APPDIR="$DIST/AutoClicker"
install -m 0644 "$ROOT/build/autoclicker.desktop" "$APPDIR/AutoClicker.desktop"
install -m 0644 "$ROOT/build/autoclicker.png" "$APPDIR/autoclicker.png"
mkdir -p "$APPDIR/data"

ARCHIVE="$ROOT/build/AutoClicker-${VERSION}-linux-x86_64.tar.gz"
tar -C "$DIST" -czf "$ARCHIVE" AutoClicker

echo "Built $APPDIR"
echo "Archive: $ARCHIVE"
echo "Run $APPDIR/AutoClicker, or copy AutoClicker.desktop to ~/.local/share/applications."
