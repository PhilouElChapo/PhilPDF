#!/bin/sh
# Lanceur de PhilPDF dans le Flatpak
for d in /app/lib/python3*/site-packages; do export PYTHONPATH="$d${PYTHONPATH:+:$PYTHONPATH}"; done
export TESSDATA_PREFIX="/app/philpdf/tessdata"
exec python3 /app/philpdf/philpdf.py "$@"
