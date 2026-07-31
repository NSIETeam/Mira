#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

APP_NAME="Mira"
ARTIFACT_LIMIT_MB="${MIRA_RELEASE_ARTIFACT_LIMIT_MB:-180}"
BUNDLE_LIMIT_MB="${MIRA_RELEASE_BUNDLE_LIMIT_MB:-119}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

log() {
  printf '\n==> %s\n' "$*"
}

native_bin() {
  local crate="$1"
  local name="$2"
  local path="native/${crate}/target/release/${name}"
  if [[ "$(uname -s)" =~ MINGW|MSYS|CYGWIN ]]; then
    path="${path}.exe"
  fi
  printf '%s' "$path"
}

log "Build native helpers"
cargo build --release --manifest-path native/mira-launcher/Cargo.toml
cargo build --release --manifest-path native/mira-sandbox/Cargo.toml
cargo build --release --manifest-path native/mira-pack/Cargo.toml

log "Stage native helpers"
rm -rf dist/native
mkdir -p dist/native
cp "$(native_bin mira-launcher mira-launcher)" dist/native/
cp "$(native_bin mira-sandbox mira-sandbox)" dist/native/
cp "$(native_bin mira-pack mira-pack)" dist/native/

log "Build WebUI"
if command -v bun >/dev/null 2>&1; then
  (cd webui && bun install --frozen-lockfile && bun run build)
else
  (cd webui && npm install && npm run build)
fi

log "Install local packaging dependencies"
"$PYTHON_BIN" -m pip install --upgrade pip
"$PYTHON_BIN" -m pip install '.[desktop,dev]'

log "Build PyInstaller app"
data_sep=":"
if [[ "$(uname -s)" =~ MINGW|MSYS|CYGWIN ]]; then
  data_sep=";"
fi
"$PYTHON_BIN" -m PyInstaller \
  --noconfirm \
  --clean \
  --name "$APP_NAME" \
  --windowed \
  --collect-all webview \
  --add-data "mira/web/dist${data_sep}mira/web/dist" \
  --add-data "dist/native${data_sep}native" \
  scripts/mira_desktop.py

log "Audit app bundle"
pack_tool="$(native_bin mira-pack mira-pack)"
if [[ -d "dist/${APP_NAME}.app" ]]; then
  "$pack_tool" "dist/${APP_NAME}.app" --json --limit-mb "$BUNDLE_LIMIT_MB" > "dist/${APP_NAME}-bundle-pack-local.json"
  "$PYTHON_BIN" scripts/package_size_report.py "dist/${APP_NAME}.app" --budget-mb "$BUNDLE_LIMIT_MB"
elif [[ -d "dist/${APP_NAME}" ]]; then
  "$pack_tool" "dist/${APP_NAME}" --json --limit-mb "$BUNDLE_LIMIT_MB" > "dist/${APP_NAME}-bundle-pack-local.json"
  "$PYTHON_BIN" scripts/package_size_report.py "dist/${APP_NAME}" --budget-mb "$BUNDLE_LIMIT_MB"
fi
cat "dist/${APP_NAME}-bundle-pack-local.json"

if [[ "$(uname -s)" == "Darwin" ]]; then
  log "Build macOS DMG"
  rm -rf dist/dmg-root "dist/${APP_NAME}.dmg"
  mkdir -p dist/dmg-root
  cp -R "dist/${APP_NAME}.app" "dist/dmg-root/${APP_NAME}.app"
  ln -s /Applications dist/dmg-root/Applications
  if command -v create-dmg >/dev/null 2>&1; then
    create-dmg \
      --volname "${APP_NAME} Installer" \
      --window-pos 200 120 \
      --window-size 840 520 \
      --icon-size 120 \
      --icon "${APP_NAME}.app" 220 250 \
      --icon "Applications" 620 250 \
      --hide-extension "${APP_NAME}.app" \
      --app-drop-link 620 250 \
      "dist/${APP_NAME}.dmg" \
      "dist/dmg-root"
  else
    hdiutil create \
      -volname "${APP_NAME} Installer" \
      -srcfolder dist/dmg-root \
      -ov \
      -format UDZO \
      "dist/${APP_NAME}.dmg"
  fi
  "$pack_tool" "dist/${APP_NAME}.dmg" --json --limit-mb "$ARTIFACT_LIMIT_MB" > "dist/${APP_NAME}-pack-local.json"
  cat "dist/${APP_NAME}-pack-local.json"
fi

log "Dependency self-containment checks"
test -d "mira/web/dist"
if [[ -d "dist/${APP_NAME}.app" ]]; then
  test -x "dist/${APP_NAME}.app/Contents/MacOS/${APP_NAME}"
  native_root="dist/${APP_NAME}.app/Contents/Resources/native"
  if [[ ! -d "$native_root" ]]; then
    native_root="dist/${APP_NAME}.app/Contents/Frameworks/native"
  fi
  test -x "${native_root}/mira-launcher"
  test -x "${native_root}/mira-sandbox"
  test -x "${native_root}/mira-pack"
  test -f "dist/${APP_NAME}.app/Contents/Resources/mira/web/dist/index.html"
  find "$native_root" -maxdepth 1 -type f -print
  otool -L "dist/${APP_NAME}.app/Contents/MacOS/${APP_NAME}" || true
else
  test -x "dist/${APP_NAME}/${APP_NAME}" || test -x "dist/${APP_NAME}/${APP_NAME}.exe"
  test -d "dist/${APP_NAME}/native"
  test -x "dist/${APP_NAME}/native/mira-launcher" || test -x "dist/${APP_NAME}/native/mira-launcher.exe"
  test -x "dist/${APP_NAME}/native/mira-sandbox" || test -x "dist/${APP_NAME}/native/mira-sandbox.exe"
  test -x "dist/${APP_NAME}/native/mira-pack" || test -x "dist/${APP_NAME}/native/mira-pack.exe"
  test -f "dist/${APP_NAME}/mira/web/dist/index.html"
  find "dist/${APP_NAME}/native" -maxdepth 1 -type f -print
fi

log "Smoke packaged executable"
if [[ -d "dist/${APP_NAME}.app" ]]; then
  MIRA_DESKTOP_SMOKE=1 "dist/${APP_NAME}.app/Contents/MacOS/${APP_NAME}"
else
  MIRA_DESKTOP_SMOKE=1 "dist/${APP_NAME}/${APP_NAME}"
fi

log "Artifacts"
find dist -maxdepth 2 \( -name "${APP_NAME}.app" -o -name "${APP_NAME}.dmg" -o -name "${APP_NAME}-pack-local.json" -o -name "${APP_NAME}-bundle-pack-local.json" \) -print
