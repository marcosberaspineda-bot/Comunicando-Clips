#!/bin/zsh
# Ejecutar EN macOS Apple Silicon. Construye .app y .dmg localmente.
set -euo pipefail
cd "${0:A:h}"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
print '=============================================='
print ' COMUNICANDO CLIPS — CREAR APLICACIÓN Y DMG'
print '=============================================='
if [[ "$(uname -s)" != Darwin ]]; then
  print -u2 'ERROR: Este script debe ejecutarse en un Mac.'
  exit 1
fi
if [[ "$(uname -m)" != arm64 ]]; then
  print -u2 'ERROR: Para el instalador M2, ejecuta Terminal nativo ARM64 (sin Rosetta).'
  exit 1
fi
if ! command -v brew >/dev/null; then
  print -u2 'Falta Homebrew. Instálalo desde https://brew.sh y vuelve a abrir este archivo.'
  exit 1
fi
print '1/5 — Instalando las herramientas necesarias (primera instalación)…'
brew list --versions ffmpeg >/dev/null 2>&1 || brew install ffmpeg
brew list --versions python@3.12 >/dev/null 2>&1 || brew install python@3.12
PYTHON="$(brew --prefix python@3.12)/bin/python3.12"
print '2/5 — Preparando entorno aislado…'
"$PYTHON" -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -r requirements.txt
print '3/5 — Pruebas automáticas del motor…'
.venv/bin/python -m unittest discover -s tests -p test_engine.py -v
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests -p 'test_gui.py' -v
print '4/5 — Compilando Comunicando Clips.app (Apple Silicon)…'
.venv/bin/pyinstaller --noconfirm --clean --windowed --onedir \
  --target-arch arm64 --name 'Comunicando Clips' \
  --osx-bundle-identifier 'com.comunicandoparalagente.clips' \
  --collect-all faster_whisper --collect-all ctranslate2 \
  --collect-all tokenizers --collect-submodules yt_dlp \
  --hidden-import PySide6.QtMultimedia --hidden-import PySide6.QtMultimediaWidgets \
  app.py
APP="$PWD/dist/Comunicando Clips.app"
[[ -d "$APP" ]] || { print -u2 'No se generó la aplicación .app'; exit 1; }
# Identidad ad-hoc: no exige una cuenta de desarrollador Apple.
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP"
print '5/5 — Creando DMG instalable…'
STAGING="$(mktemp -d)"
trap 'rm -rf "$STAGING"' EXIT
ditto "$APP" "$STAGING/Comunicando Clips.app"
ln -s /Applications "$STAGING/Aplicaciones"
mkdir -p "$PWD/entrega"
DMG="$PWD/entrega/Comunicando_Clips_Mac_M2.dmg"
rm -f "$DMG"
hdiutil create -volname 'Comunicando Clips' -srcfolder "$STAGING" \
  -ov -format UDZO "$DMG"
hdiutil verify "$DMG"
print ''
print 'DMG CREADO Y VERIFICADO:'
print "$DMG"
print 'Abre el DMG y arrastra Comunicando Clips a Aplicaciones.'
print 'REQUISITO: FFmpeg de Homebrew debe continuar instalado en este Mac.'
print 'Sin firma Developer ID ni notarización, macOS podría exigir Abrir desde el menú contextual.'
read '?Presiona Enter para cerrar…'
