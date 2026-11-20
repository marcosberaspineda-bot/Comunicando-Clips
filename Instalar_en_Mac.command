#!/bin/zsh
# Compatibilidad con el paquete anterior: crea la aplicación y el .dmg.
set -e
cd "${0:A:h}"
exec ./Crear_DMG_en_Mac.command
