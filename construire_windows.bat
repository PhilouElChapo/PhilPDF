@echo off
REM ============================================================
REM  PhilPDF - construction de l'executable Windows
REM  Prerequis : Python 3.11 ou plus recent (python.org), coche "Add to PATH"
REM  Resultat :
REM    dist\PhilPDF\PhilPDF.exe          (version a installer ou a copier)
REM    dist\PhilPDF_portable.zip         (version portable, rien dans le registre)
REM ============================================================
cd /d "%~dp0"

if not exist .venv (
    echo Creation de l'environnement Python...
    python -m venv .venv || goto erreur
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul
pip install -r requirements.txt pyinstaller || goto erreur

echo Test rapide du moteur...
python tests\test_moteur.py || goto erreur

echo Construction de PhilPDF.exe...
pyinstaller --noconfirm --clean --windowed --name PhilPDF --icon philpdf.ico ^
  --add-data "fonts;fonts" --add-data "tessdata;tessdata" ^
  --hidden-import moteur.modifier --hidden-import moteur.scan ^
  --exclude-module scipy --exclude-module onnxruntime --exclude-module pymupdf.layout --exclude-module pymupdf_layout --exclude-module pymupdf4llm --exclude-module matplotlib --exclude-module pandas --exclude-module tkinter ^
  philpdf.py || goto erreur

echo Version portable...
copy /y LISEZMOI.txt dist\PhilPDF\ >nul
echo PhilPDF portable : parametres et session ranges dans le dossier "donnees" > dist\PhilPDF\portable.txt
powershell -NoProfile -Command "Compress-Archive -Force -Path 'dist\PhilPDF\*' -DestinationPath 'dist\PhilPDF_portable.zip'"
del dist\PhilPDF\portable.txt

echo.
echo Termine :
echo   dist\PhilPDF\PhilPDF.exe
echo   dist\PhilPDF_portable.zip
pause
exit /b 0

:erreur
echo.
echo *** La construction a echoue : copiez le message ci-dessus et envoyez-le a Claude. ***
pause
exit /b 1
