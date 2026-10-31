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
# app.fenetre (et tout PhilPDF) est charge apres l'affichage de l'ecran de demarrage : voir main()


class EcranDemarrage:
    """Fenetre de lancement affichee tout de suite (logo, version, etape en cours, barre qui avance), le temps
    de charger les moteurs PDF et d'ouvrir la fenetre : on voit que PhilPDF demarre."""

    def __init__(self, app):
        from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QProgressBar
        from app.config import VERSION
        from app.icones import logo
        self.app = app
        w = self.w = QWidget(None, Qt.SplashScreen | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        w.setObjectName("demarrage")
        w.setStyleSheet("#demarrage{background:#ffffff;border:1px solid #d9d9d9;border-radius:14px}"
                        "QLabel{background:transparent}")
        w.setAttribute(Qt.WA_TranslucentBackground, False)
        w.setFixedSize(420, 230)
        v = QVBoxLayout(w)
        v.setContentsMargins(28, 24, 28, 22)
        h = __import__("PySide6.QtWidgets", fromlist=["QHBoxLayout"]).QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(logo(64).pixmap(64, 64))
        h.addWidget(ic)
        t = QLabel("<span style='font-size:28px;font-weight:700;color:#1f1f1f'>Phil</span>"
                   "<span style='font-size:28px;font-weight:700;color:#c9252d'>PDF</span>"
                   f"<br><span style='color:#666;font-size:12px'>Version {VERSION}</span>")
        h.addWidget(t, 1)
        v.addLayout(h)
        v.addStretch(1)
        self.etat = QLabel("Démarrage...")
        self.etat.setStyleSheet("color:#444;font-size:13px")
        v.addWidget(self.etat)
        self.barre = QProgressBar()
        self.barre.setRange(0, 100)
        self.barre.setTextVisible(False)
        self.barre.setFixedHeight(6)
        self.barre.setStyleSheet("QProgressBar{background:#eee;border:none;border-radius:3px}"
                                 "QProgressBar::chunk{background:#c9252d;border-radius:3px}")
        v.addWidget(self.barre)
        ecr = app.primaryScreen().availableGeometry()
        w.move(ecr.center() - w.rect().center())
        w.show()
        try:                                         # image de lancement de l'exe (avant Python) : remplacee
            import pyi_splash
            pyi_splash.close()
        except Exception:
            pass
        self.etape("Démarrage...", 5)

    def etape(self, texte, pourcent):
        self.etat.setText(texte)
        self.barre.setValue(pourcent)
        for _i in range(3):
            self.app.processEvents()

    def fermer(self, fenetre=None):
        self.etape("Prêt.", 100)
        self.w.close()


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
    try:
        from app.reseau import activer
        mode = activer()
    except Exception as ex:
        mode = f"erreur {ex}"
    lignes.append(f"moteur https: certificats verifies par {mode}")
    if sys.platform == "win32" and mode != "windows":
        ok = False
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
    try:                                          # certificats HTTPS verifies par Windows (comme le navigateur)
        from app.reseau import activer
        activer()
    except Exception:
        pass
    if "--verifier" in sys.argv:
        sys.exit(verifier(sys.argv[sys.argv.index("--verifier") + 1]))
    app = QApplication(sys.argv)
    try:
        from app.mise_a_jour import debloquer
        debloquer()
    except Exception:
        pass
    impressions = [os.path.abspath(sys.argv[i + 1]) for i, a in enumerate(sys.argv[:-1]) if a == "--impression"]
    fichiers = [os.path.abspath(a) for a in sys.argv[1:] if a.lower().endswith(".pdf") and os.path.exists(a)
                and os.path.abspath(a) not in impressions]
    import app.config as _cfg                         # lance seulement pour une impression (PhilPDF etait ferme)
    _cfg.LANCE_PAR_IMPRIMANTE = bool(impressions) and not fichiers
    # un seul PhilPDF a la fois : verrou du systeme (meme si deux lancements arrivent ensemble), puis les fichiers
    # sont confies a celui qui est deja ouvert ; apres une mise a jour, le nouveau attend que l'ancien soit ferme
    global _VERROU
    _VERROU = verrou_instance()
    if not _VERROU.tryLock(20000 if "--nouvelle-instance" in sys.argv else 0):
        import time
        libre = False
        for _i in range(25):                          # l'autre est peut-etre occupe (synchronisation) : on insiste
            if _VERROU.tryLock(0):                    # ...ou il vient de se fermer (redemarrage) : on prend sa place
                libre = True
                break
            if confier_a_instance_ouverte(fichiers, impressions):
                sys.exit(0)
            app.processEvents()
            time.sleep(0.4)
        if libre:
            pass
        else:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(None, "PhilPDF", "PhilPDF est déjà ouvert sur ce PC (il est peut-être occupé). "
                                                     "Utilisez sa fenêtre, ou fermez-le avant de le relancer.")
            sys.exit(0)
    import time as _tm
    _t0 = _tm.monotonic()
    demarrage = EcranDemarrage(app)
    demarrage.etape("Chargement du moteur PDF...", 20)
    _t1 = _tm.monotonic()
    import pymupdf                                # noqa: F401  (le plus long a charger)
    demarrage.etape("Chargement de l'interface...", 45)
    _t2 = _tm.monotonic()
    from app.fenetre import Fenetre
    _t3 = _tm.monotonic()
    demarrage.etape("Préparation...", 70)
    preparer(app)
    try:                                          # aucune fenetre plus grande que l'ecran (ex. 1024 x 768)
        from app import ecran
        ecran.installer(app)
    except Exception:
        pass
    surveiller_plantages()
    nettoyer_temporaires()
    demarrage.etape("Ouverture de la fenêtre...", 85)
    _t4 = _tm.monotonic()
    w = Fenetre(fichiers)
    _t5 = _tm.monotonic()
    QTimer_ = __import__("PySide6.QtCore", fromlist=["QTimer"]).QTimer
    QTimer_.singleShot(3000, lambda: signaler_plantage(w))
    ecouter_autres_lancements(w)
    w.show()
    demarrage.fermer(w)
    try:                                          # duree du lancement, dans le journal (pour l'ameliorer)
        from app.journal import ecrire, noter_version
        noter_version(_cfg.VERSION)
        ecrire("démarrage", f"fenêtre prête en {_tm.monotonic() - _t0:.1f} s (Qt {_t1 - _t0:.1f} s, moteur PDF "
                            f"{_t2 - _t1:.1f} s, interface {_t3 - _t2:.1f} s, fenêtre {_t5 - _t4:.1f} s)")
        if impressions:
            ecrire("démarrage", "ouvert par l'imprimante PhilPDF : " + ", ".join(os.path.basename(x) for x in impressions))
        elif fichiers:
            ecrire("démarrage", "ouvert avec : " + ", ".join(os.path.basename(x) for x in fichiers))
    except Exception:
        pass
    from PySide6.QtCore import QTimer
    QTimer.singleShot(800, lambda: w.impressions_en_attente(impressions))
    sys.exit(app.exec())


_VERROU = None
_FICHIER_PLANTAGE = None


def _chemin_plantage():
    from app.config import dossier_donnees
    return os.path.join(dossier_donnees(), "plantage.txt")


def surveiller_plantages():
    """Si PhilPDF se ferme brutalement, la cause est notee dans plantage.txt (signalee au lancement suivant) ;
    une erreur ordinaire est notee dans le journal et affichee, sans fermer PhilPDF."""
    global _FICHIER_PLANTAGE
    import faulthandler, traceback
    try:
        _FICHIER_PLANTAGE = open(_chemin_plantage(), "a", encoding="utf-8")
        faulthandler.enable(_FICHIER_PLANTAGE, all_threads=True)
    except Exception:
        pass

    def crochet(typ, val, tb):
        texte = "".join(traceback.format_exception(typ, val, tb))
        try:
            from app.journal import ecrire
            ecrire("erreur", texte)
        except Exception:
            pass
        try:
            from PySide6.QtWidgets import QMessageBox, QApplication
            if QApplication.instance():
                QMessageBox.warning(None, "PhilPDF", "Une erreur est survenue (PhilPDF reste ouvert) :\n\n"
                                    + str(val)[:400] + "\n\nLe détail est dans Aide › Journal des échanges.")
        except Exception:
            pass
    sys.excepthook = crochet
    # Windows : faulthandler note aussi des alertes internes sans gravite (ex. 0x80040155 dans la fenetre de choix
    # de dossier) alors que PhilPDF continue. Fermeture normale = pas de plantage : le fichier est vide a la sortie.
    import atexit

    def sortie_normale():
        try:
            faulthandler.disable()
            if _FICHIER_PLANTAGE:
                _FICHIER_PLANTAGE.seek(0)
                _FICHIER_PLANTAGE.truncate()
                _FICHIER_PLANTAGE.close()
        except Exception:
            pass
    atexit.register(sortie_normale)
    import threading
    threading.excepthook = lambda a: crochet(a.exc_type, a.exc_value, a.exc_traceback)


def signaler_plantage(fenetre):
    """Au lancement : si la derniere session s'est fermee brutalement, on le dit et on montre la cause."""
    try:
        p = _chemin_plantage()
        with open(p, encoding="utf-8", errors="replace") as f:
            texte = f.read()
    except OSError:
        return
    if "Fatal Python error" not in texte and "Windows fatal exception" not in texte:
        return
    try:
        from app.journal import ecrire
        ecrire("plantage", texte[-6000:])
        with open(p + ".precedent", "w", encoding="utf-8") as f:
            f.write(texte)
        if _FICHIER_PLANTAGE:
            _FICHIER_PLANTAGE.seek(0)
            _FICHIER_PLANTAGE.truncate()
    except Exception:
        pass
    from PySide6.QtWidgets import QMessageBox
    QMessageBox.information(fenetre, "PhilPDF", "PhilPDF s'est fermé brutalement la dernière fois. La cause a été "
                            "notée dans le journal (Aide › Journal des échanges) : envoyez-la si vous voulez qu'elle soit corrigée.")


def nettoyer_temporaires(age_jours=1):
    """Copies temporaires (pieces jointes preparees pour un e-mail, apercus, conversions) de plus d'un jour :
    effacees. Celles d'aujourd'hui restent, le temps de les glisser dans un message."""
    import tempfile, time, shutil
    base = tempfile.gettempdir()
    try:
        for n in os.listdir(base):
            if n.startswith(("philpdf-envoi-", "philpdf-apercu-", "philpdf-office-")):
                p = os.path.join(base, n)
                if time.time() - os.path.getmtime(p) > age_jours * 86400:
                    shutil.rmtree(p, ignore_errors=True)
    except OSError:
        pass


def _nom_instance():
    """Un seul PhilPDF par utilisateur de ce PC (version installee et portable comprises : elles partagent la
    synchronisation, deux a la fois se marcheraient dessus)."""
    import getpass
    import hashlib
    try:
        u = getpass.getuser()
    except Exception:
        u = os.environ.get("USERNAME") or os.environ.get("USER") or "?"
    return "PhilPDF-" + hashlib.sha1(u.lower().encode("utf-8")).hexdigest()[:12]


def verrou_instance():
    """Verrou du systeme : libere tout seul si PhilPDF s'arrete, meme brutalement (processus disparu)."""
    from PySide6.QtCore import QLockFile, QDir
    v = QLockFile(os.path.join(QDir.tempPath(), _nom_instance() + ".lock"))
    v.setStaleLockTime(0)
    return v


def confier_a_instance_ouverte(fichiers, impressions=()):
    """Si PhilPDF est deja ouvert, lui passe les fichiers (ou lui demande de se montrer) et renvoie True."""
    import json
    from PySide6.QtNetwork import QLocalSocket
    s = QLocalSocket()
    s.connectToServer(_nom_instance())
    if not s.waitForConnected(400):
        return False
    s.write((json.dumps({"ouvrir": fichiers, "impression": list(impressions)}) + "\n").encode("utf-8"))
    s.flush()
    s.waitForBytesWritten(3000)
    s.waitForReadyRead(5000)                          # reponse attendue, mais il tourne de toute facon : on s'arrete
    s.disconnectFromServer()
    return True


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
            if d.get("impression"):
                fenetre.impressions_en_attente(d["impression"])
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
