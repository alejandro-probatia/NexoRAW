#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON="${PYTHON:-python3}"
APP_VERSION="${PROBRAW_APP_VERSION:-$("$PYTHON" - "$ROOT" <<'PY'
import sys
from pathlib import Path

root = Path(sys.argv[1])
namespace = {}
exec((root / "src" / "probraw" / "version.py").read_text(encoding="utf-8"), namespace)
print(namespace["__version__"])
PY
)}"
DEB_VERSION="${PROBRAW_DEB_VERSION:-$(printf '%s' "$APP_VERSION" | sed -E 's/([0-9.]+)b([0-9]+)/\1~beta\2/')}"
ARCH="${PROBRAW_DEB_ARCH:-$(dpkg --print-architecture)}"
BUILD_AMAZE="${PROBRAW_BUILD_AMAZE:-1}"
REQUIRE_AMAZE="${PROBRAW_REQUIRE_AMAZE:-$BUILD_AMAZE}"
RAWPY_DEMOSAIC_WHEEL="${PROBRAW_RAWPY_DEMOSAIC_WHEEL:-}"
RAWPY_DEMOSAIC_REPO="${PROBRAW_RAWPY_DEMOSAIC_REPO:-https://github.com/exfab/rawpy-demosaic.git}"
RAWPY_DEMOSAIC_REF="${PROBRAW_RAWPY_DEMOSAIC_REF:-8b17075}"
RAWPY_DEMOSAIC_SOURCE="${PROBRAW_RAWPY_DEMOSAIC_SOURCE:-git+https://github.com/exfab/rawpy-demosaic.git@8b17075}"
RAWPY_DEMOSAIC_PACKAGE="${PROBRAW_RAWPY_DEMOSAIC_PACKAGE:-rawpy-demosaic}"
PKG_NAME="probraw"
BUILD_ROOT="$ROOT/build/deb/${PKG_NAME}_${DEB_VERSION}_${ARCH}"
DIST_DIR="$ROOT/dist"
DEB_PATH="$DIST_DIR/${PKG_NAME}_${DEB_VERSION}_${ARCH}.deb"
VENV_DIR="$BUILD_ROOT/opt/probraw/venv"
VENV_INSTALL_DIR="/opt/probraw/venv"

is_true() {
  case "${1,,}" in
    1|true|yes|on) return 0 ;;
    *) return 1 ;;
  esac
}

install_amaze_backend() {
  local wheel="$RAWPY_DEMOSAIC_WHEEL"
  if [[ -z "$wheel" && "$RAWPY_DEMOSAIC_SOURCE" == "git+https://github.com/exfab/rawpy-demosaic.git@8b17075" ]]; then
    "$PYTHON" "$ROOT/scripts/build_rawpy_demosaic_wheel.py" \
      --python "$VENV_DIR/bin/python" \
      --repo "$RAWPY_DEMOSAIC_REPO" \
      --ref "$RAWPY_DEMOSAIC_REF" \
      --work-dir "$BUILD_ROOT/rawpy-demosaic-build" \
      --output-dir "$BUILD_ROOT/rawpy-demosaic-wheel" \
      --force
    wheel="$(find "$BUILD_ROOT/rawpy-demosaic-wheel" -maxdepth 1 -type f -name 'rawpy_demosaic-*.whl' | sort | tail -n 1)"
  fi
  local args=("$ROOT/scripts/install_amaze_backend.py")
  if [[ -n "$wheel" ]]; then
    RAWPY_DEMOSAIC_WHEEL="$wheel"
    args+=("--wheel" "$wheel")
  elif [[ -n "$RAWPY_DEMOSAIC_SOURCE" ]]; then
    args+=("--source" "$RAWPY_DEMOSAIC_SOURCE")
  else
    args+=("--pypi" "--package" "$RAWPY_DEMOSAIC_PACKAGE")
  fi
  "$VENV_DIR/bin/python" -m pip install --upgrade "setuptools<70" wheel "Cython<3"
  "$VENV_DIR/bin/python" "${args[@]}"
}

write_amaze_build_metadata() {
  local dest="$BUILD_ROOT/usr/share/doc/probraw/third_party/rawpy-demosaic"
  mkdir -p "$dest"
  local check_json="$dest/check-amaze.json"
  "$VENV_DIR/bin/python" "$ROOT/scripts/check_amaze_support.py" > "$check_json"
  local wheel_name=""
  local wheel_sha256=""
  if [[ -n "$RAWPY_DEMOSAIC_WHEEL" ]]; then
    wheel_name="$(basename "$RAWPY_DEMOSAIC_WHEEL")"
    wheel_sha256="$(sha256sum "$RAWPY_DEMOSAIC_WHEEL" | awk '{print $1}')"
  fi
  "$VENV_DIR/bin/python" - "$dest/build-metadata.json" "$RAWPY_DEMOSAIC_PACKAGE" "$RAWPY_DEMOSAIC_SOURCE" "$wheel_name" "$wheel_sha256" <<'PY'
import json
import sys
from pathlib import Path

metadata_path = Path(sys.argv[1])
payload = {
    "backend": "rawpy-demosaic",
    "package": sys.argv[2],
    "source": sys.argv[3] or None,
    "wheel": sys.argv[4] or None,
    "wheel_sha256": sys.argv[5] or None,
    "source_url": "https://github.com/exfab/rawpy-demosaic",
    "runtime_check": json.loads((metadata_path.parent / "check-amaze.json").read_text(encoding="utf-8")),
}
metadata_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
PY
}

rm -rf "$BUILD_ROOT"
mkdir -p \
  "$BUILD_ROOT/DEBIAN" \
  "$BUILD_ROOT/opt/probraw" \
  "$BUILD_ROOT/usr/bin" \
  "$BUILD_ROOT/usr/share/applications" \
  "$BUILD_ROOT/usr/share/icons/hicolor/scalable/apps" \
  "$BUILD_ROOT/usr/share/pixmaps" \
  "$BUILD_ROOT/usr/share/doc/probraw" \
  "$DIST_DIR"

"$PYTHON" -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --upgrade pip setuptools wheel
"$VENV_DIR/bin/python" -m pip install "$ROOT[gui,c2pa]"
if is_true "$BUILD_AMAZE" || is_true "$REQUIRE_AMAZE" || [[ -n "$RAWPY_DEMOSAIC_WHEEL" ]]; then
  install_amaze_backend
  write_amaze_build_metadata
fi
if is_true "$REQUIRE_AMAZE"; then
  "$VENV_DIR/bin/python" "$ROOT/scripts/check_amaze_support.py"
fi
SITE_PACKAGES="$("$VENV_DIR/bin/python" - <<'PY'
import site
print(site.getsitepackages()[0])
PY
)"
"$VENV_DIR/bin/python" -m compileall -q "$SITE_PACKAGES/probraw"
rm -f "$VENV_DIR/bin/nexoraw" "$VENV_DIR/bin/nexoraw-ui" "$VENV_DIR/bin/iccraw" "$VENV_DIR/bin/iccraw-ui"

for entry in "$VENV_DIR/bin/"*; do
  [ -f "$entry" ] || continue
  grep -Iq . "$entry" || continue
  first_line="$(head -n 1 "$entry" || true)"
  case "$first_line" in
    "#!$VENV_DIR/bin/python"*)
      sed -i "1s|^#!.*|#!$VENV_INSTALL_DIR/bin/python|" "$entry"
      ;;
  esac
done
sed -i "s|$VENV_DIR|$VENV_INSTALL_DIR|g" "$VENV_DIR/pyvenv.cfg"

cat > "$BUILD_ROOT/usr/bin/probraw" <<'SH'
#!/usr/bin/env sh
exec /opt/probraw/venv/bin/probraw "$@"
SH

cat > "$BUILD_ROOT/usr/bin/probraw-ui" <<'SH'
#!/usr/bin/env sh
exec /opt/probraw/venv/bin/probraw-ui "$@"
SH

chmod 0755 \
  "$BUILD_ROOT/usr/bin/probraw" \
  "$BUILD_ROOT/usr/bin/probraw-ui"

cat > "$BUILD_ROOT/usr/share/applications/probraw.desktop" <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=ProbRAW
GenericName=RAW color profiling
Comment=Pipeline reproducible RAW -> carta -> perfil ICC de sesion
Exec=probraw-ui
Icon=/usr/share/pixmaps/probraw.png
Terminal=false
Categories=Graphics;Photography;
Keywords=RAW;ICC;color;photography;forensics;
StartupWMClass=probraw
DESKTOP

install -m 0644 "$ROOT/src/probraw/resources/icons/probraw-icon.svg" "$BUILD_ROOT/usr/share/icons/hicolor/scalable/apps/probraw.svg"
"$VENV_DIR/bin/python" - "$ROOT/src/probraw/resources/icons/probraw-icon.png" "$BUILD_ROOT" <<'PY'
from pathlib import Path
import sys

from PIL import Image

src = Path(sys.argv[1])
build_root = Path(sys.argv[2])
with Image.open(src) as image:
    image = image.convert("RGBA")
    for size in (16, 32, 48, 64, 128, 256, 512):
        dest = build_root / "usr" / "share" / "icons" / "hicolor" / f"{size}x{size}" / "apps" / "probraw.png"
        dest.parent.mkdir(parents=True, exist_ok=True)
        resized = image if image.size == (size, size) else image.resize((size, size), Image.Resampling.LANCZOS)
        resized.save(dest)
    pixmap = build_root / "usr" / "share" / "pixmaps" / "probraw.png"
    pixmap.parent.mkdir(parents=True, exist_ok=True)
    image.save(pixmap)
PY
install -m 0644 "$ROOT/README.md" "$BUILD_ROOT/usr/share/doc/probraw/README.md"
install -m 0644 "$ROOT/CHANGELOG.md" "$BUILD_ROOT/usr/share/doc/probraw/CHANGELOG.md"
install -m 0644 "$ROOT/LICENSE" "$BUILD_ROOT/usr/share/doc/probraw/LICENSE"
install -m 0644 "$ROOT/docs/THIRD_PARTY_LICENSES.md" "$BUILD_ROOT/usr/share/doc/probraw/THIRD_PARTY_LICENSES.md"
install -m 0644 "$ROOT/docs/LEGAL_COMPLIANCE.md" "$BUILD_ROOT/usr/share/doc/probraw/LEGAL_COMPLIANCE.md"
install -m 0644 "$ROOT/docs/AMAZE_GPL3.md" "$BUILD_ROOT/usr/share/doc/probraw/AMAZE_GPL3.md"
install -m 0644 "$ROOT/docs/DEBIAN_PACKAGE.md" "$BUILD_ROOT/usr/share/doc/probraw/DEBIAN_PACKAGE.md"
install -m 0644 "$ROOT/docs/RELEASE_INSTALLERS.md" "$BUILD_ROOT/usr/share/doc/probraw/RELEASE_INSTALLERS.md"
install -m 0644 "$ROOT/docs/MANUAL_USUARIO.md" "$BUILD_ROOT/usr/share/doc/probraw/MANUAL_USUARIO.md"
install -m 0644 "$ROOT/docs/METODOLOGIA_COLOR_RAW.md" "$BUILD_ROOT/usr/share/doc/probraw/METODOLOGIA_COLOR_RAW.md"
install -m 0644 "$ROOT/docs/COLOR_PIPELINE.md" "$BUILD_ROOT/usr/share/doc/probraw/COLOR_PIPELINE.md"
install -m 0644 "$ROOT/docs/DECISIONS.md" "$BUILD_ROOT/usr/share/doc/probraw/DECISIONS.md"
install -m 0644 "$ROOT/docs/C2PA_CAI.md" "$BUILD_ROOT/usr/share/doc/probraw/C2PA_CAI.md"
install -m 0644 "$ROOT/docs/PROBRAW_PROOF.md" "$BUILD_ROOT/usr/share/doc/probraw/PROBRAW_PROOF.md"
install -m 0755 "$ROOT/scripts/check_amaze_support.py" "$BUILD_ROOT/usr/share/doc/probraw/check_amaze_support.py"

INSTALLED_SIZE="$(du -sk "$BUILD_ROOT" | awk '{print $1}')"
cat > "$BUILD_ROOT/DEBIAN/control" <<EOF
Package: $PKG_NAME
Version: $DEB_VERSION
Section: graphics
Priority: optional
Architecture: $ARCH
Maintainer: Comunidad AEICF <release@probraw.local>
Installed-Size: $INSTALLED_SIZE
Depends: python3 (>= 3.11), argyll, exiftool, colord, libgl1, libegl1, libxkbcommon0, libxcb-cursor0, libxcb-xinerama0, libgomp1, liblcms2-2, libjpeg-turbo8, libstdc++6, desktop-file-utils, hicolor-icon-theme
Replaces: nexoraw, iccraw
Conflicts: nexoraw, iccraw
Homepage: https://github.com/alejandro-probatia/ProbRAW
Description: ProbRAW $APP_VERSION reproducible RAW and ICC session profiling
 ProbRAW is a technical/scientific RAW workflow for controlled development,
 color chart sampling, session development profiles and ICC camera profiles.
 This package installs a bundled Python environment under /opt/probraw and
 command launchers under /usr/bin. AMaZE builds install rawpy-demosaic during
 package construction and record the runtime check in documentation.
EOF

cat > "$BUILD_ROOT/DEBIAN/postinst" <<'SH'
#!/usr/bin/env sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database -q /usr/share/applications || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
fi
exit 0
SH

chmod 0755 "$BUILD_ROOT/DEBIAN/postinst"
chmod 0755 "$BUILD_ROOT/DEBIAN"

dpkg-deb --build --root-owner-group "$BUILD_ROOT" "$DEB_PATH"
dpkg-deb --info "$DEB_PATH"

echo
echo "Paquete generado: $DEB_PATH"
