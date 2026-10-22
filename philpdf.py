"""PhilPDF - Editeur PDF. Lancement : python philpdf.py [fichier.pdf ...]"""
import os, sys

sys.path.insert(0, getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))))

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
    lignes.append("RESULTAT: " + ("OK" if ok else "ECHEC"))
    with open(sortie, "w", encoding="utf-8") as f:
        f.write("\n".join(lignes))
    return 0 if ok else 1


def main():
    if "--verifier" in sys.argv:
        sys.exit(verifier(sys.argv[sys.argv.index("--verifier") + 1]))
    app = QApplication(sys.argv)
    app.setApplicationName("PhilPDF")
    app.setOrganizationName("PhilPDF")
    app.setStyle("Fusion")
    pal = app.palette()
    pal.setColor(QPalette.Window, QColor("#f3f3f3"))
    pal.setColor(QPalette.Base, QColor("#ffffff"))
    pal.setColor(QPalette.Highlight, QColor("#1462c2"))
    pal.setColor(QPalette.ToolTipBase, QColor("#1f1f1f"))
    pal.setColor(QPalette.ToolTipText, QColor("#ffffff"))
    app.setPalette(pal)
    app.setFont(QFont("Segoe UI" if sys.platform == "win32" else "Inter", 10))
    app.setStyleSheet("QToolTip{background:#1f1f1f;color:#fff;border:none;padding:8px;border-radius:6px}"
                      "QMenuBar{background:#fff;border-bottom:1px solid #e2e2e2}QMenuBar::item{padding:6px 10px}"
                      "QMenu{background:#fff;border:1px solid #d0d0d0}QMenu::item{padding:6px 28px 6px 28px}"
                      "QMenu::item:selected{background:#e6f0fc;color:#1f1f1f}")
    fichiers = [a for a in sys.argv[1:] if a.lower().endswith(".pdf") and os.path.exists(a)]
    w = Fenetre(fichiers)
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
