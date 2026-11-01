#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
command -v python3 >/dev/null || { echo "Python 3.11 ou mais recente não encontrado."; exit 1; }
if [ ! -d .venv ]; then
  echo "Criando ambiente virtual..."
  python3 -m venv .venv
fi
source .venv/bin/activate
if [ ! -f .venv/.instalado ]; then
  echo "Instalando dependências do Python..."
  python -m pip install --upgrade pip
  pip install -r requirements.txt
  touch .venv/.instalado
fi
[ -f .env ] || cp .env.example .env
VERSAO=$(tr -d '[:space:]' < VERSION)
if [ ! -f frontend/out/index.html ] || [ "$(tr -d '[:space:]' < frontend/out/.versao 2>/dev/null)" != "$VERSAO" ]; then
  if command -v npm >/dev/null; then
    echo "Compilando a interface $VERSAO..."
    (cd frontend && npm install && npm run build) && echo "$VERSAO" > frontend/out/.versao
  else
    echo "Node.js não encontrado. A API sobe, mas a interface precisa do build em frontend/out."
  fi
fi
exec python -m apogeu
