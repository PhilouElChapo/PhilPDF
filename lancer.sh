#!/bin/sh
# Lance PhilPDF sous Linux (Zorin OS) depuis les sources.
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
else
  . .venv/bin/activate
fi
exec python philpdf.py "$@"
