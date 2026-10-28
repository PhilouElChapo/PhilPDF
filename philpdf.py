"""PhilPDF - Editeur PDF. Lancement : python philpdf.py [fichier.pdf ...]"""
import os, sys

sys.path.insert(0, getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))))
if sys.stdout is None:          # programme sans console (Windows) : certaines bibliotheques ecrivent quand meme
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont, QPalette, QColor
from PySide6.QtCore import Qt
from app.fenetre import Fenetre


def verifier(sortie):
    """Auto-controle sans fenetre (utilise par la fabrication automatique) :
    moteur Modifier + reconnaissance de texte embarquee."""
    import tempfile, pymupdf as fitz
    from moteur.modifier import Editeur
    from moteur.scan import tesseract_exe, traiter
    lignes, ok = [], True
    from moteur.scan import versions_moteurs
    for k, x in versions_moteurs().items():
        lignes.append(f"moteur {k}: {x}")
    try:
        from app.orthographe import fautes, suggestions
        bon = [m for _a, _b, m in fautes("Le documment est signé.", {"langue": "fr"})] == ["documment"] and \
            "document" in suggestions("documment", {"langue": "fr"})
    except Exception as ex:
        bon = False
        lignes.append(f"orthographe: {ex}")
    ok &= bon
    lignes.append(f"orthographe: {'OK' if bon else 'ECHEC'}")
    try:                                         # icones des comptes (module charge a la demande : present dans l'exe ?)
        from app import avatars
        from PySide6.QtWidgets import QApplication
        _qa = QApplication.instance() or QApplication([])
        bon = not avatars.icone_compte({"id": "verif", "type": "gdrive"}, {"comptes_icone": "pastille"}).isNull()
    except Exception as ex:
        bon = False
        lignes.append(f"icones des comptes: {ex}")
    ok &= bon
    lignes.append(f"icones des comptes: {'OK' if bon else 'ECHEC'}")
    try:                                         # signature numerique (pyHanko et ses modules, presents dans l'exe ?)
        import tempfile
        from moteur import signature_num as SN
        t = tempfile.mkdtemp()
        d0 = fitz.open(); d0.new_page(); d0.save(os.path.join(t, "a.pdf"))
        pfx = SN.creer_identite("Verification", "verif-123")
        SN.signer(os.path.join(t, "a.pdf"), os.path.join(t, "b.pdf"), pfx, "verif-123", page=0,
                  rect=(72, 72, 252, 117), horodatage=False)
        v = SN.verifier(os.path.join(t, "b.pdf"), [SN.exporter_cer(pfx, "verif-123")])
        bon = len(v) == 1 and v[0]["intacte"] and v[0]["approuve"]
    except Exception as ex:
        bon = False
        lignes.append(f"signature numerique: {ex}")
    ok &= bon
    lignes.append(f"signature numerique: {'OK' if bon else 'ECHEC'}")
    try:                                         # JBIG2 (bibliotheque C embarquee) et Excel
        from moteur import jbig2, tableaux
        flux = jbig2.encoder(bytes([0x0F, 0xF0] * 64), 16, 64)
        bon = jbig2.rapide() and flux[:4] == b"\0\0\0\0"
        tableaux.ecrire_xlsx(os.path.join(tempfile.mkdtemp(), "v.xlsx"), [("A", [["a", "1,5"]])])
    except Exception as ex:
        bon = False
        lignes.append(f"jbig2 / excel: {ex}")
    ok &= bon
    lignes.append(f"moteur jbig2 et excel: {'OK' if bon else 'ECHEC'}")
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
    try:
        from app import oauth
        for t, n in (("gdrive", "google drive"), ("onedrive", "onedrive"), ("dropbox", "dropbox"), ("box", "box")):
            lignes.append(f"{n}: {'identifiant present' if oauth.disponible(t) else 'identifiant absent'}")
    except Exception as ex:
        lignes.append(f"google drive: {ex}")
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
    fichiers = [os.path.abspath(a) for a in sys.argv[1:] if a.lower().endswith(".pdf") and os.path.exists(a)]
    if "--nouvelle-instance" not in sys.argv and confier_a_instance_ouverte(fichiers):
        sys.exit(0)                                   # PhilPDF tourne deja : il ouvre les fichiers lui-meme
    preparer(app)
    w = Fenetre(fichiers)
    ecouter_autres_lancements(w)
    w.show()
    sys.exit(app.exec())


def _nom_instance():
    """Un PhilPDF par utilisateur et par dossier de donnees (la version portable reste independante)."""
    import hashlib
    from app.config import dossier_donnees
    return "PhilPDF-" + hashlib.sha1(dossier_donnees().encode("utf-8")).hexdigest()[:12]


def confier_a_instance_ouverte(fichiers):
    """Si PhilPDF est deja ouvert, lui passe les fichiers (ou lui demande de se montrer) et renvoie True."""
    import json
    from PySide6.QtNetwork import QLocalSocket
    s = QLocalSocket()
    s.connectToServer(_nom_instance())
    if not s.waitForConnected(400):
        return False
    s.write((json.dumps({"ouvrir": fichiers}) + "\n").encode("utf-8"))
    s.flush()
    s.waitForBytesWritten(1000)
    ok = s.waitForReadyRead(2000) and s.readAll().data().startswith(b"ok")
    s.disconnectFromServer()
    return ok


def ecouter_autres_lancements(fenetre):
    import json
    from PySide6.QtNetwork import QLocalServer
    QLocalServer.removeServer(_nom_instance())        # reste d'un PhilPDF arrete brutalement
    serveur = QLocalServer(fenetre)
    if not serveur.listen(_nom_instance()):
        return

    def connexion():
        c = serveur.nextPendingConnection()

        def lire():
            if not c.canReadLine():
                return
            try:
                d = json.loads(bytes(c.readLine()).decode("utf-8"))
            except ValueError:
                d = {}
            c.write(b"ok\n")
            c.flush()
            for f in d.get("ouvrir") or []:
                fenetre.ouvrir(f)
            fenetre.setWindowState((fenetre.windowState() & ~Qt.WindowMinimized) | Qt.WindowActive)
            fenetre.show()
            fenetre.raise_()
            fenetre.activateWindow()
        c.readyRead.connect(lire)
        if c.bytesAvailable():
            lire()
    serveur.newConnection.connect(connexion)
    fenetre.serveur_instance = serveur


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
    from app.theme import feuille, proteger_bulles
    proteger_bulles()
    from app.config import dossier_donnees
    app.setStyleSheet(feuille(dossier_donnees()))


if __name__ == "__main__":
    main()
