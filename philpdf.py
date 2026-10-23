"""PhilPDF - Editeur PDF. Lancement : python philpdf.py [fichier.pdf ...]"""
import os, sys

sys.path.insert(0, getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))))
if sys.stdout is None:          # programme sans console (Windows) : certaines bibliotheques ecrivent quand meme
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont, QPalette, QColor
from app.fenetre import Fenetre


def verifier(sortie):
    """Auto-controle sans fenetre (utilise par la fabrication automatique) :
    moteur Modifier + reconnaissance de texte embarquee."""
    import tempfile, pymupdf as fitz
    from moteur.modifier import Editeur
    from moteur.scan import tesseract_exe, traiter
    lignes, ok = [], True
    d = fitz.open(); p = d.new_page()
    p.insert_text((72, 100), "Net à payer : 130,00 EUR", fontname="hebo", fontsize=12)
    tmp = tempfile.mkdtemp(); src = os.path.join(tmp, "t.pdf"); d.save(src)
    e = Editeur(src); e.remplacer(0, "Net à payer", "Montant payé"); e.enregistrer(src + ".ok.pdf")
    t = fitz.open(src + ".ok.pdf")[0].get_text()
    ok &= "Montant payé" in t
    lignes.append(f"modifier: {'OK' if 'Montant payé' in t else 'ECHEC'}")
    from moteur import objets
    d2 = fitz.open(src + ".ok.pdf")
    objets.poser(d2, 0, fitz.Rect(300, 300, 450, 350), objets.tampon_predefini("REÇU", (0, 0, 1)), "Reçu")
    bon = len(list(d2[0].annots())) == 1
    ok &= bon
    lignes.append(f"tampon: {'OK' if bon else 'ECHEC'}")
    try:
        from pdf2docx import Converter
        c = Converter(src + ".ok.pdf"); c.convert(src + ".docx"); c.close()
        bon = os.path.getsize(src + ".docx") > 1000
    except Exception as ex:
        bon = False
        lignes.append(f"word: {ex}")
    ok &= bon
    lignes.append(f"word: {'OK' if bon else 'ECHEC'}")
    exe = tesseract_exe()
    lignes.append(f"tesseract: {exe}")
    if exe:
        scan = fitz.open(); pg = scan.new_page()
        pg.insert_text((72, 120), "Reconnaissance du texte en français", fontname="tiro", fontsize=20)
        pm = pg.get_pixmap(dpi=200, colorspace=fitz.csGRAY)
        img = fitz.open(); ip = img.new_page(width=pg.rect.width, height=pg.rect.height)
        ip.insert_image(ip.rect, pixmap=pm); s1 = os.path.join(tmp, "scan.pdf"); img.save(s1)
        traiter(s1, s1 + ".ocr.pdf")
        texte = fitz.open(s1 + ".ocr.pdf")[0].get_text()
        bon = "Reconnaissance" in texte and "français" in texte
        ok &= bon
        lignes.append(f"ocr: {'OK' if bon else 'ECHEC'} ({texte.strip()[:60]!r})")
    else:
        ok = False
    try:
        from app import coffre
        coffre.enregistrer("verification", "essai-123")
        bon = coffre.lire("verification") == "essai-123"
        coffre.supprimer("verification")
        lignes.append(f"coffre: {'OK' if bon else 'ECHEC'} ({'systeme' if coffre.systeme() else 'fichier chiffre'})")
        ok &= bon
    except Exception as ex:
        ok = False
        lignes.append(f"coffre: {ex}")
    from app.langue import disponibles
    langues = [c for c, _n in disponibles()]
    ok &= "en" in langues
    lignes.append(f"langues: {', '.join(langues)}")
    lignes.append("RESULTAT: " + ("OK" if ok else "ECHEC"))
    with open(sortie, "w", encoding="utf-8") as f:
        f.write("\n".join(lignes))
    return 0 if ok else 1


def main():
    if "--verifier" in sys.argv:
        sys.exit(verifier(sys.argv[sys.argv.index("--verifier") + 1]))
    app = QApplication(sys.argv)
    try:
        from app.mise_a_jour import debloquer
        debloquer()
    except Exception:
        pass
    preparer(app)
    fichiers = [a for a in sys.argv[1:] if a.lower().endswith(".pdf") and os.path.exists(a)]
    w = Fenetre(fichiers)
    w.show()
    sys.exit(app.exec())


def preparer(app):
    """Traduction, style plat, police : commun a l'appli et aux captures de test."""
    from PySide6.QtCore import QTranslator, QLibraryInfo, QLocale
    from app.langue import LANGUE
    QLocale.setDefault(QLocale(LANGUE))
    trad = QTranslator(app)
    for dossier in (QLibraryInfo.path(QLibraryInfo.TranslationsPath),
                    os.path.join(getattr(sys, "_MEIPASS", ""), "PySide6", "Qt", "translations")):
        if LANGUE != "en" and trad.load(f"qtbase_{LANGUE}", dossier):
            app.installTranslator(trad)
            break
    app.setApplicationName("PhilPDF")
    app.setOrganizationName("PhilPDF")
    app.setStyle("Fusion")
    pal = app.palette()
    pal.setColor(QPalette.Window, QColor("#f3f3f3"))
    pal.setColor(QPalette.Base, QColor("#ffffff"))
    pal.setColor(QPalette.Highlight, QColor("#0f6cbd"))
    pal.setColor(QPalette.ToolTipBase, QColor("#1f1f1f"))
    pal.setColor(QPalette.ToolTipText, QColor("#ffffff"))
    app.setPalette(pal)
    app.setFont(QFont("Segoe UI" if sys.platform == "win32" else "Inter", 10))
    from app.theme import feuille
    from app.config import dossier_donnees
    app.setStyleSheet(feuille(dossier_donnees()))


if __name__ == "__main__":
    main()
