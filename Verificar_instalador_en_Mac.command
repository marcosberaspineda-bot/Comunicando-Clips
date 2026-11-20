#!/bin/zsh
set -euo pipefail
cd "${0:A:h}"
DMG="$PWD/entrega/Comunicando_Clips_Mac_M2.dmg"
[[ -f "$DMG" ]] || { print -u2 "No existe $DMG"; exit 1; }
hdiutil verify "$DMG"
MNT="$(mktemp -d)"
cleanup() { hdiutil detach "$MNT" -quiet >/dev/null 2>&1 || true; rmdir "$MNT" >/dev/null 2>&1 || true; }
trap cleanup EXIT
hdiutil attach "$DMG" -mountpoint "$MNT" -nobrowse -readonly -quiet
APP="$MNT/Comunicando Clips.app"
[[ -d "$APP" ]] || { print -u2 'La imagen no incluye la aplicación'; exit 1; }
[[ -x "$APP/Contents/MacOS/Comunicando Clips" ]] || { print -u2 'Falta el ejecutable'; exit 1; }
file "$APP/Contents/MacOS/Comunicando Clips"
codesign --verify --deep "$APP"
print 'DMG válido: incluye aplicación firmada ad hoc y ejecutable de macOS.'
