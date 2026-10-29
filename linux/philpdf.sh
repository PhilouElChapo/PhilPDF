#!/bin/sh
# Lanceur de PhilPDF dans le Flatpak
export PYTHONPATH="/app/lib/python3.12/site-packages${PYTHONPATH:+:$PYTHONPATH}"
export TESSDATA_PREFIX="/app/philpdf/tessdata"
exec python3 /app/philpdf/philpdf.py "$@"
