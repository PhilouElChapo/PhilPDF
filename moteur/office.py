"""Fichiers Office (Word, Excel, PowerPoint, LibreOffice, RTF, texte) convertis en PDF, polices integrees, pour les
ouvrir dans PhilPDF par glisser-deposer ou « Creer un PDF ».

Sous Windows, par Office lui-meme (le rendu exact du document, comme « Enregistrer en PDF » d'Office) ; sinon par
LibreOffice (soffice --headless) ; sinon, pour Word (.docx), Excel (.xlsx, .csv) et le texte, par PhilPDF lui-meme
(moteur/office_interne.py : rendu simplifie, dit a l'utilisateur). Les polices sont toujours integrees.
"""
import glob
import os
import shutil
import subprocess
import sys
import tempfile

WORD = (".doc", ".docx", ".docm", ".dot", ".dotx", ".rtf", ".odt", ".txt", ".wpd")
EXCEL = (".xls", ".xlsx", ".xlsm", ".xlsb", ".ods", ".csv")
POWERPOINT = (".ppt", ".pptx", ".pptm", ".pps", ".ppsx", ".odp")
EXTENSIONS = WORD + EXCEL + POWERPOINT


class ErreurOffice(Exception):
    pass


def libreoffice():
    """Chemin de soffice, ou None."""
    for nom in ("soffice", "libreoffice"):
        p = shutil.which(nom)
        if p:
            return p
    if sys.platform == "win32":
        for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                     os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")):
            for p in glob.glob(os.path.join(base, "LibreOffice*", "program", "soffice.exe")):
                return p
    return None


def _par_office(source, sortie):
    """Conversion par Word / Excel / PowerPoint (automatisation COM). Leve ErreurOffice si Office est absent."""
    try:
        import pythoncom
        import win32com.client as wc
    except ImportError as e:
        raise ErreurOffice("pywin32") from e
    ext = os.path.splitext(source)[1].lower()
    pythoncom.CoInitialize()
    app = None
    deja_ouvert = False

    def lancer(nom):
        """Instance a part (DispatchEx) ; si Windows refuse (« Echec de l'execution du serveur », Office en version
        Microsoft Store / Demarrer en un clic, ou Office deja ouvert avec d'autres droits), l'instance ouverte."""
        nonlocal deja_ouvert
        try:
            return wc.DispatchEx(nom)
        except Exception:                                # noqa: BLE001
            try:
                deja_ouvert = True
                return wc.GetActiveObject(nom)
            except Exception:                            # noqa: BLE001
                deja_ouvert = False
                return wc.Dispatch(nom)
    try:
        if ext in WORD:
            app = lancer("Word.Application")
            if not deja_ouvert:
                app.Visible = False
            app.DisplayAlerts = 0
            d = app.Documents.Open(source, ReadOnly=True, AddToRecentFiles=False, ConfirmConversions=False)
            # 17 = PDF ; polices integrees, texte des polices non integrables mis en image (comme Adobe)
            d.ExportAsFixedFormat(sortie, 17, OpenAfterExport=False, OptimizeFor=0, Item=0,
                                  IncludeDocProps=True, CreateBookmarks=1, DocStructureTags=True,
                                  BitmapMissingFonts=True, UseISO19005_1=False)
            d.Close(False)
        elif ext in EXCEL:
            app = lancer("Excel.Application")
            if not deja_ouvert:
                app.Visible = False
            app.DisplayAlerts = False
            c = app.Workbooks.Open(source, ReadOnly=True, AddToMru=False)
            c.ExportAsFixedFormat(0, sortie, Quality=0, IncludeDocProperties=True, IgnorePrintAreas=False,
                                  OpenAfterPublish=False)
            c.Close(False)
        else:
            app = lancer("PowerPoint.Application")
            p = app.Presentations.Open(source, ReadOnly=True, WithWindow=False)
            p.SaveAs(sortie, 32)                         # 32 = PDF
            p.Close()
    except Exception as e:                               # noqa: BLE001 (Office absent, fichier protege)
        raise ErreurOffice(str(e)) from e
    finally:
        try:
            if app is not None and not deja_ouvert:   # jamais fermer l'Office ouvert par la personne
                app.Quit()
        except Exception:
            pass
        pythoncom.CoUninitialize()
    if not os.path.exists(sortie):
        raise ErreurOffice("aucun PDF produit")


def _par_libreoffice(source, sortie):
    so = libreoffice()
    if not so:
        raise ErreurOffice("LibreOffice absent")
    dossier = tempfile.mkdtemp(prefix="philpdf-office-")
    profil = "file:///" + os.path.join(dossier, "profil").replace("\\", "/").lstrip("/")
    filtre = "pdf:writer_pdf_Export:{\"EmbedStandardFonts\":{\"type\":\"boolean\",\"value\":\"true\"}}"
    r = subprocess.run([so, f"-env:UserInstallation={profil}", "--headless", "--norestore", "--convert-to", filtre,
                        "--outdir", dossier, source], capture_output=True, text=True, timeout=180,
                       creationflags=0x08000000 if sys.platform == "win32" else 0)
    produit = os.path.join(dossier, os.path.splitext(os.path.basename(source))[0] + ".pdf")
    if not os.path.exists(produit):
        raise ErreurOffice((r.stderr or r.stdout or "conversion").strip()[:300])
    shutil.move(produit, sortie)
    shutil.rmtree(dossier, ignore_errors=True)


def convertir(source, sortie=None, details=None):
    """Convertit le fichier en PDF ; renvoie (chemin du PDF, moyen utilise : "office", "libreoffice" ou "philpdf").
    details (liste) recoit les essais qui ont echoue et, pour "philpdf", ce qui n'a pas pu etre repris."""
    source = os.path.abspath(source)
    sortie = sortie or os.path.join(tempfile.mkdtemp(prefix="philpdf-office-"),
                                    os.path.splitext(os.path.basename(source))[0] + ".pdf")
    erreurs = []
    if sys.platform == "win32":
        try:
            _par_office(source, sortie)
            return sortie, "office"
        except ErreurOffice as e:
            erreurs.append(f"Office : {e}")
    try:
        _par_libreoffice(source, sortie)
        return sortie, "libreoffice"
    except (ErreurOffice, OSError, subprocess.SubprocessError) as e:
        erreurs.append(f"LibreOffice : {e}")
    from . import office_interne
    if os.path.splitext(source)[1].lower() in office_interne.INTERNES:
        try:
            manques = office_interne.convertir(source, sortie, os.path.join(os.path.dirname(sortie), "images"))
            if details is not None:
                details.extend(erreurs)
                details.append(("manques", manques))
            return sortie, "philpdf"
        except Exception as e:                           # noqa: BLE001
            erreurs.append(f"PhilPDF : {e}")
    raise ErreurOffice(" ; ".join(erreurs))


def polices_non_integrees(chemin):
    """Polices non integrees du PDF produit (normalement aucune) : [nom]."""
    import pymupdf as fitz
    out = set()
    with fitz.open(chemin) as d:
        for n in range(len(d)):
            for f in d.get_page_fonts(n):
                if f[1] == "n/a" and f[2] != "Type3":
                    out.add(f[3])
    return sorted(out)
