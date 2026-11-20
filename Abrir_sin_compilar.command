#!/bin/zsh
cd "${0:A:h}"
if [[ ! -x .venv/bin/python ]]; then
  echo 'Ejecuta primero Instalar_en_Mac.command'
  read '?Enter para cerrar...'
  exit 1
fi
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
.venv/bin/python app.py
