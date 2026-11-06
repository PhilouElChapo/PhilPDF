"""Traitement par lot : une ou plusieurs actions sur tout un dossier (OCR, allegement, filigrane, numerotation Bates,
PDF/A, renommage selon un modele ou propose par l'IA, tri en sous-dossiers par expediteur, type ou annee). Avant de
lancer, PhilPDF montre la liste des fichiers et les noms de sortie (ceux de l'IA se corrigent) ; les originaux ne
sont jamais ecrases sans copie, les fichiers signes ou proteges sont signales et laisses de cote."""
import datetime
import os
import re
import shutil
import tempfile

import pymupdf as fitz
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit, QComboBox,
                               QCheckBox, QPushButton, QListWidget, QListWidgetItem, QFileDialog, QGroupBox,
                               QSpinBox, QProgressBar, QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView,
                               QSplitter, QWidget, QPlainTextEdit)

from .langue import _

ACTIONS = ("ocr", "alleger", "filigrane", "bates", "pdfa", "renommer", "courriel")


def fichiers_du_dossier(dossier, sous_dossiers=False):
    out = []
    if sous_dossiers:
        for r, ds, fs in os.walk(dossier):
            ds[:] = [d for d in ds if d not in ("Traités", "Traites")]
            out += [os.path.join(r, f) for f in fs if f.lower().endswith(".pdf")]
    else:
        out = [os.path.join(dossier, f) for f in os.listdir(dossier) if f.lower().endswith(".pdf")]
    return sorted(out, key=lambda f: f.lower())


def _propre(t):
    return re.sub(r"\s+", " ", re.sub(r'[<>:"/\\|?*]', "-", t or "")).strip(" .")


def nom_sortie(chemin, regl, n):
    """Nom du fichier produit (sans le dossier). n : rang du fichier dans le lot (1 pour le premier)."""
    base = os.path.splitext(os.path.basename(chemin))[0]
    ia_nom = (regl.get("noms_ia") or {}).get(chemin) if regl.get("mode_nom") == "ia" else None
    if "renommer" in regl["actions"] and ia_nom:
        base = os.path.splitext(_propre(ia_nom.get("nom", "")))[0] or base
    elif "renommer" in regl["actions"]:
        try:
            st = os.stat(chemin)
            date_f = datetime.date.fromtimestamp(st.st_mtime)
        except OSError:
            date_f = datetime.date.today()
        titre = ""
        try:
            with fitz.open(chemin) as d:
                titre = (d.metadata or {}).get("title") or ""
        except Exception:
            pass
        modele = regl.get("modele") or "{nom}"
        try:
            base = modele.format(nom=base, n=f"{regl.get('n_debut', 1) + n - 1:0{regl.get('n_chiffres', 3)}d}",
                                 date=date_f.strftime("%Y-%m-%d"), aujourdhui=datetime.date.today().strftime("%Y-%m-%d"),
                                 titre=titre or base)
        except (KeyError, IndexError, ValueError):
            pass
        if regl.get("chercher"):
            base = base.replace(regl["chercher"], regl.get("remplacer", ""))
        base = re.sub(r'[<>:"/\\|?*]', "-", base).strip() or "document"
    if regl.get("suffixe") and regl["sortie"] == "cote":
        base += regl["suffixe"]
    return base + ".pdf"


def sous_dossier_tri(chemin, regl):
    """Tri par l'IA : sous-dossier selon l'expediteur, le type ou l'annee lus par l'IA ("" sans tri ou sans reponse)."""
    tri = regl.get("tri") or ""
    r = (regl.get("noms_ia") or {}).get(chemin)
    if "renommer" not in regl["actions"] or not tri or not r:
        return ""
    infos = r.get("infos") or {}
    if tri == "annee":
        v = (infos.get("date") or "")[:4]
        return v if re.fullmatch(r"(19|20)\d\d", v) else _("Sans date")
    v = _propre(infos.get("expediteur" if tri == "expediteur" else "type") or "")
    return (v[:1].upper() + v[1:])[:60] if v else _("Non classés")


def dossier_sortie(chemin, regl):
    if regl["sortie"] == "sous_dossier":
        d = os.path.join(os.path.dirname(chemin), _("Traités"))
    elif regl["sortie"] == "dossier" and regl.get("dossier"):
        d = regl["dossier"]
    else:
        d = os.path.dirname(chemin)
    t = sous_dossier_tri(chemin, regl)
    return os.path.join(d, t) if t else d


def _filigrane(doc, texte, opacite=0.18):
    for page in doc:
        r = page.rect
        taille = min(r.width, r.height) / max(4, len(texte)) * 1.5
        taille = max(24, min(120, taille))
        larg = fitz.get_text_length(texte, fontname="hebo", fontsize=taille)
        centre = fitz.Point(r.width / 2, r.height / 2)
        import math
        a = math.radians(45)
        debut = centre - fitz.Point(larg / 2 * math.cos(a), -larg / 2 * math.sin(a))
        page.insert_text(debut, texte, fontname="hebo", fontsize=taille, color=(0.6, 0.6, 0.6),
                         morph=(debut, fitz.Matrix(45)), fill_opacity=opacite, stroke_opacity=opacite, overlay=True)


def _bates(doc, regl, numero):
    """Numero Bates en bas a droite de chaque page ; renvoie le numero suivant (continu d'un fichier a l'autre)."""
    t = regl.get("bates_taille", 9)
    for page in doc:
        txt = f"{regl.get('bates_prefixe', '')}{numero:0{regl.get('bates_chiffres', 6)}d}{regl.get('bates_suffixe', '')}"
        L = fitz.get_text_length(txt, fontname="helv", fontsize=t)
        R = page.rect
        page.insert_text((R.width - 36 - L, R.height - 20), txt, fontname="helv", fontsize=t, color=(0.15, 0.15, 0.15))
        numero += 1
    return numero


def traiter_fichier(chemin, regl, rang, numero_bates, journal):
    """Un fichier du lot. Renvoie (chemin produit ou None, numero Bates suivant, octets avant, octets apres)."""
    avant = os.path.getsize(chemin)
    doc = fitz.open(chemin)
    if doc.needs_pass:
        journal.append(_("protégé par mot de passe : laissé tel quel"))
        return None, numero_bates, avant, avant
    try:
        signe = any(w.field_type == fitz.PDF_WIDGET_TYPE_SIGNATURE and w.is_signed for p in doc for w in p.widgets())
    except Exception:
        signe = False
    modifie = any(a in regl["actions"] for a in ("ocr", "alleger", "filigrane", "bates", "pdfa"))
    if "renommer" in regl["actions"] and regl.get("mode_nom") == "ia" and chemin not in (regl.get("noms_ia") or {}):
        journal.append(_("pas de nom proposé par l'IA : nom selon le modèle"))
    if signe and modifie and not regl.get("signes"):
        journal.append(_("signé : laissé tel quel (le modifier rendrait la signature invalide)"))
        return None, numero_bates, avant, avant
    doc.close()
    tmp = tempfile.mkdtemp(prefix="philpdf-lot-")
    courant = chemin
    if "ocr" in regl["actions"]:
        from moteur.scan import a_du_texte, traiter
        with fitz.open(courant) as d:
            a_scanner = sum(1 for p in d if not a_du_texte(p))
        if a_scanner:
            sortie = os.path.join(tmp, "ocr.pdf")
            traiter(courant, sortie)
            courant = sortie
            journal.append(_("texte reconnu ({n} page(s))", n=a_scanner))
        else:
            journal.append(_("OCR inutile : le texte est déjà là"))
    doc = fitz.open(courant)
    if "filigrane" in regl["actions"] and regl.get("filigrane"):
        _filigrane(doc, regl["filigrane"])
        journal.append(_("filigrane « {t} »", t=regl["filigrane"]))
    if "bates" in regl["actions"]:
        debut = numero_bates
        numero_bates = _bates(doc, regl, numero_bates)
        journal.append(_("Bates {a} à {b}", a=debut, b=numero_bates - 1))
    octets = None
    if "alleger" in regl["actions"]:
        from .alleger import alleger, PREREGLAGES
        _nom, dpi, q, seuil = PREREGLAGES[regl.get("prereglage", 0)]
        r = {"images": True, "dpi": dpi, "qualite": q, "seuil": seuil, "gris": False, "polices": True,
             "nettoyer": True, "infos": False, "jbig2": True, "noir_blanc": regl.get("noir_blanc", False),
             "polices_formulaire": True}
        octets = alleger(doc.tobytes(garbage=1), r)
        journal.append(_("allégé"))
        doc = fitz.open("pdf", octets)
    if "pdfa" in regl["actions"]:
        from moteur import pdfa
        pdfa.convertir(doc)
        octets = pdfa.octets(doc)
        ok = pdfa.conforme(fitz.open("pdf", octets))
        journal.append(_("PDF/A-2b") + ("" if ok else " " + _("(points à revoir)")))
    elif octets is None:
        octets = doc.tobytes(garbage=3, deflate=True) if modifie else open(chemin, "rb").read()
    dossier = dossier_sortie(chemin, regl)
    os.makedirs(dossier, exist_ok=True)
    cible = os.path.join(dossier, nom_sortie(chemin, regl, rang))
    if regl["sortie"] == "remplacer":
        cible = os.path.join(dossier, nom_sortie(chemin, regl, rang))
        sauvegarde = os.path.join(os.path.dirname(chemin), _("Originaux"))
        os.makedirs(sauvegarde, exist_ok=True)
        shutil.copy2(chemin, os.path.join(sauvegarde, os.path.basename(chemin)))
    # jamais d'ecrasement d'un autre fichier : « (2) », « (3) »...
    if os.path.exists(cible) and os.path.normcase(os.path.abspath(cible)) != os.path.normcase(os.path.abspath(chemin)):
        b, ext = os.path.splitext(cible)
        k = 2
        while os.path.exists(f"{b} ({k}){ext}"):
            k += 1
        cible = f"{b} ({k}){ext}"
    with open(cible + ".tmp", "wb") as f:
        f.write(octets)
    os.replace(cible + ".tmp", cible)
    if regl["sortie"] == "remplacer" and os.path.normcase(cible) != os.path.normcase(chemin) and os.path.exists(chemin):
        os.remove(chemin)                                   # renomme : l'ancien nom part (copie dans « Originaux »)
    shutil.rmtree(tmp, ignore_errors=True)
    return cible, numero_bates, avant, len(octets)


class _Tache(QThread):
    etape = Signal(int, str, str, int, int)          # rang, fichier produit, journal, avant, apres
    fini = Signal()

    def __init__(self, fichiers, regl):
        super().__init__()
        self.fichiers, self.regl, self.stop = fichiers, regl, False

    def run(self):
        numero = self.regl.get("bates_debut", 1)
        for i, f in enumerate(self.fichiers):
            if self.stop:
                break
            j = []
            try:
                cible, numero, av, ap = traiter_fichier(f, self.regl, i + 1, numero, j)
            except Exception as e:
                cible, av, ap = None, 0, 0
                j.append(_("erreur : {e}", e=e))
            self.etape.emit(i, cible or "", " · ".join(j), av, ap)
        self.fini.emit()


class DialogueLot(QDialog):
    def __init__(self, parent, params, dossier=""):
        super().__init__(parent)
        self.params = params
        self.setWindowTitle(_("Traitement par lot"))
        self.resize(1100, 720)
        v = QVBoxLayout(self)
        h = QHBoxLayout()
        self.dossier = QLineEdit(dossier)
        self.dossier.setObjectName("lot_dossier")
        self.dossier.setPlaceholderText(_("dossier des PDF à traiter"))
        self.dossier.editingFinished.connect(self.lister)
        h.addWidget(QLabel(_("Dossier :")))
        h.addWidget(self.dossier, 1)
        b = QPushButton(_("Choisir..."))
        b.clicked.connect(self.choisir_dossier)
        h.addWidget(b)
        b = QPushButton(_("Ajouter des fichiers..."))
        b.clicked.connect(self.ajouter_fichiers)
        h.addWidget(b)
        self.sous = QCheckBox(_("avec les sous-dossiers"))
        self.sous.toggled.connect(self.lister)
        h.addWidget(self.sous)
        v.addLayout(h)
        sp = QSplitter()
        v.addWidget(sp, 1)
        gauche = QWidget()
        g = QVBoxLayout(gauche)
        g.setContentsMargins(0, 0, 0, 0)
        ga = QGroupBox(_("Actions (dans cet ordre)"))
        fa = QFormLayout(ga)
        self.cases = {}
        libelles = {"ocr": _("Reconnaître le texte (OCR) des pages scannées"),
                    "alleger": _("Alléger"), "filigrane": _("Filigrane"), "bates": _("Numérotation Bates"),
                    "pdfa": _("Archiver en PDF/A"), "renommer": _("Renommer"),
                    "courriel": _("Envoyer par e-mail à la fin (les fichiers produits, joints au même message)")}
        for a in ACTIONS:
            c = QCheckBox(libelles[a])
            c.setObjectName("lot_" + a)
            c.toggled.connect(self.maj_apercu)
            self.cases[a] = c
        fa.addRow(self.cases["ocr"])
        fa.addRow(self.cases["alleger"])
        self.prereglage = QComboBox()
        from .alleger import PREREGLAGES
        for nom, *_r in PREREGLAGES:
            self.prereglage.addItem(nom)
        fa.addRow("      " + _("Réglage"), self.prereglage)
        self.noir_blanc = QCheckBox(_("scans de texte en noir et blanc (JBIG2)"))
        fa.addRow("      ", self.noir_blanc)
        fa.addRow(self.cases["filigrane"])
        self.t_filigrane = QLineEdit(_("COPIE"))
        self.t_filigrane.setObjectName("lot_texte_filigrane")
        fa.addRow("      " + _("Texte"), self.t_filigrane)
        fa.addRow(self.cases["bates"])
        hb = QHBoxLayout()
        self.b_prefixe = QLineEdit()
        self.b_prefixe.setPlaceholderText(_("préfixe"))
        self.b_debut = QSpinBox()
        self.b_debut.setRange(0, 99999999)
        self.b_debut.setValue(1)
        self.b_chiffres = QSpinBox()
        self.b_chiffres.setRange(1, 12)
        self.b_chiffres.setValue(6)
        for w in (self.b_prefixe, self.b_debut, self.b_chiffres):
            hb.addWidget(w)
        fa.addRow("      " + _("Préfixe, début, chiffres"), hb)
        fa.addRow(self.cases["pdfa"])
        fa.addRow(self.cases["renommer"])
        # nom : selon un modele, ou propose par l'IA (date, expediteur, objet) ; tri en sous-dossiers
        self.mode_nom = QComboBox()
        self.mode_nom.setObjectName("lot_mode_nom")
        self.mode_nom.addItem(_("Selon le modèle ci-dessous"), "modele")
        self.mode_nom.addItem(_("Proposé par l'IA : date, expéditeur, objet"), "ia")
        self.mode_nom.currentIndexChanged.connect(self._mode_nom_change)
        fa.addRow("      " + _("Nom"), self.mode_nom)
        self.tri = QComboBox()
        self.tri.setObjectName("lot_tri")
        self.tri.addItem(_("Pas de tri"), "")
        self.tri.addItem(_("Un sous-dossier par expéditeur (CPAM, EDF...)"), "expediteur")
        self.tri.addItem(_("Un sous-dossier par type (facture, courrier...)"), "type")
        self.tri.addItem(_("Un sous-dossier par année"), "annee")
        self.tri.setToolTip(_("Lu par l'IA dans chaque document, avec le nom proposé"))
        self.tri.currentIndexChanged.connect(self.maj_apercu)
        fa.addRow("      " + _("Trier"), self.tri)
        self.b_ia = QPushButton(_("Proposer les noms avec l'IA..."))
        self.b_ia.setObjectName("lot_ia")
        self.b_ia.setToolTip(_("L'IA lit chaque document et propose son nom (et son sous-dossier) ; vous les "
                               "voyez et les corrigez à droite avant « Lancer ». Rien n'est envoyé sans votre accord."))
        self.b_ia.clicked.connect(self.proposer_noms)
        hia = QHBoxLayout()                         # bouton seul : garde sa taille, aligne a gauche
        hia.addWidget(self.b_ia)
        hia.addStretch(1)
        fa.addRow("      ", hia)
        self.modele = QLineEdit("{date} {nom}")
        self.modele.setObjectName("lot_modele")
        self.modele.setToolTip(_("{nom} nom actuel, {n} numéro (001, 002...), {date} date du fichier, "
                                 "{aujourdhui} date du jour, {titre} titre du PDF"))
        self.modele.textChanged.connect(self.maj_apercu)
        fa.addRow("      " + _("Nouveau nom"), self.modele)
        aide = QLabel(_("{nom} nom actuel · {n} numéro · {date} date du fichier · {aujourdhui} · {titre}"))
        aide.setStyleSheet("color:#666;font-size:11px")
        fa.addRow("", aide)
        hr = QHBoxLayout()
        self.chercher = QLineEdit()
        self.chercher.setPlaceholderText(_("remplacer..."))
        self.remplacer = QLineEdit()
        self.remplacer.setPlaceholderText(_("...par"))
        for w in (self.chercher, self.remplacer):
            w.textChanged.connect(self.maj_apercu)
            hr.addWidget(w)
        fa.addRow("", hr)
        fa.addRow(self.cases["courriel"])
        g.addWidget(ga)
        gs = QGroupBox(_("Où mettre les fichiers produits"))
        fs = QVBoxLayout(gs)
        self.sortie = QComboBox()
        self.sortie.setObjectName("lot_sortie")
        self.sortie.addItem(_("Dans un sous-dossier « Traités » (conseillé)"), "sous_dossier")
        self.sortie.addItem(_("A côté des originaux, avec un suffixe"), "cote")
        self.sortie.addItem(_("Dans un autre dossier..."), "dossier")
        self.sortie.addItem(_("Remplacer les originaux (copie gardée dans « Originaux »)"), "remplacer")
        self.sortie.currentIndexChanged.connect(self._sortie_change)
        fs.addWidget(self.sortie)
        self.suffixe = QLineEdit(_(" (traité)"))
        fs.addWidget(self.suffixe)
        self.suffixe.textChanged.connect(self.maj_apercu)
        self.signes = QCheckBox(_("Traiter aussi les fichiers signés (leurs signatures ne seront plus valides)"))
        fs.addWidget(self.signes)
        g.addWidget(gs)
        g.addStretch(1)
        sp.addWidget(gauche)
        droite = QWidget()
        dv = QVBoxLayout(droite)
        dv.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, 3)
        self.table.setObjectName("lot_table")
        self.table.setHorizontalHeaderLabels([_("Fichier"), _("Sera enregistré sous"), _("Résultat")])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.EditKeyPressed)
        self.table.itemChanged.connect(self._nom_corrige)
        dv.addWidget(self.table, 1)
        self.barre = QProgressBar()
        self.barre.hide()
        dv.addWidget(self.barre)
        self.bilan = QLabel()
        self.bilan.setWordWrap(True)
        dv.addWidget(self.bilan)
        sp.addWidget(droite)
        sp.setSizes([430, 670])
        hb = QHBoxLayout()
        hb.addStretch(1)
        self.b_lancer = QPushButton(_("Lancer"))
        self.b_lancer.setProperty("primaire", True)
        self.b_lancer.clicked.connect(self.lancer)
        hb.addWidget(self.b_lancer)
        self.b_arreter = QPushButton(_("Arrêter"))
        self.b_arreter.clicked.connect(self.arreter)
        self.b_arreter.setEnabled(False)
        hb.addWidget(self.b_arreter)
        self.b_mail = QPushButton(_("Envoyer par e-mail..."))
        self.b_mail.setToolTip(_("Les fichiers produits, joints au même message (avant de lancer : les fichiers de la liste, tels quels)"))
        self.b_mail.clicked.connect(self.envoyer_mail)
        hb.addWidget(self.b_mail)
        self.b_ouvrir = QPushButton(_("Ouvrir le dossier"))
        self.b_ouvrir.clicked.connect(self.ouvrir_dossier)
        self.b_ouvrir.setEnabled(False)
        hb.addWidget(self.b_ouvrir)
        b = QPushButton(_("Fermer"))
        b.clicked.connect(self.close)
        hb.addWidget(b)
        v.addLayout(hb)
        for w in (self.prereglage, self.noir_blanc, self.t_filigrane, self.b_prefixe, self.b_debut, self.b_chiffres):
            (w.textChanged if isinstance(w, QLineEdit) else w.currentIndexChanged if isinstance(w, QComboBox)
             else w.toggled if isinstance(w, QCheckBox) else w.valueChanged).connect(self._coche_action(w))
        self.fichiers, self.tache, self.produits = [], None, []
        self.noms_ia = {}                         # chemin -> {"nom": ..., "infos": reponse de l'IA}
        self._mode_nom_change()
        self._sortie_change()
        if dossier:
            self.lister()

    def _mode_nom_change(self, *_a):
        ia_choisie = self.mode_nom.currentData() == "ia"
        if ia_choisie:
            self.cases["renommer"].setChecked(True)
        for w in (self.tri, self.b_ia):
            w.setEnabled(ia_choisie)
        for w in (self.modele, self.chercher, self.remplacer):
            w.setEnabled(not ia_choisie)
        self.maj_apercu()

    def _nom_corrige(self, it):
        """Double-clic sur « Sera enregistre sous » (noms de l'IA) : le nom corrige est garde."""
        if getattr(self, "_remplissage", False) or it.column() != 1 or self.mode_nom.currentData() != "ia":
            return
        f = it.data(Qt.UserRole)
        if f in self.noms_ia:
            n = os.path.basename(it.text().strip())
            if n:
                self.noms_ia[f]["nom"] = n if n.lower().endswith(".pdf") else n + ".pdf"
            self.maj_apercu()

    def proposer_noms(self):
        """L'IA lit chaque fichier (son texte, sinon l'image de sa premiere page) et propose nom et sous-dossier.
        Un seul accord pour tout le lot ; les fichiers aux donnees sensibles sont signales et peuvent etre exclus."""
        from . import ia
        from .dialogues_ia import verifier_cle, executer_suivi, CONSIGNES_NOMMER, nom_propose
        if not self.fichiers or not verifier_cle(self, self.params):
            return
        a_faire = [f for f in self.fichiers if f not in self.noms_ia] or list(self.fichiers)
        textes, sans_texte, sensibles = {}, [], {}
        for f in a_faire:
            try:
                with fitz.open(f) as d:
                    if d.needs_pass:
                        continue
                    t = ia.texte_document(d, max_car=8000)
            except Exception:                            # noqa: BLE001
                continue
            textes[f] = t
            if not t.strip():
                sans_texte.append(f)
            else:
                trouves = ia.donnees_sensibles(t)
                if trouves:
                    sensibles[f] = sorted({g for g, _x in trouves})
        if not textes:
            return
        moteur = ia.nom_moteur(self.params)
        detail = _("{n} document(s) vont être envoyés à l'IA ({ia}) pour proposer leur nom.", n=len(textes), ia=moteur)
        if sans_texte:
            detail += "\n\n" + _("{n} n'ont pas de texte reconnu : l'image de leur première page sera envoyée.", n=len(sans_texte))
        if sensibles:
            detail += "\n\n" + _("Données sensibles repérées dans {n} fichier(s) :", n=len(sensibles)) + "\n" + "\n".join(
                f"  • {os.path.basename(f)} : {', '.join(g)}" for f, g in list(sensibles.items())[:12])
            if len(sensibles) > 12:
                detail += "\n  • ..."
        q = QMessageBox(QMessageBox.Question, _("Proposer les noms avec l'IA"), detail, parent=self)
        b_tous = q.addButton(_("Envoyer"), QMessageBox.AcceptRole)
        b_sans = q.addButton(_("Envoyer, sans les fichiers sensibles"), QMessageBox.AcceptRole) if sensibles else None
        q.addButton(_("Annuler"), QMessageBox.RejectRole)
        q.exec()
        if q.clickedButton() not in (b_tous, b_sans):
            return
        envoi = [f for f in textes if not (q.clickedButton() is b_sans and f in sensibles)]
        consignes = CONSIGNES_NOMMER + f"\nDate du jour : {datetime.date.today().isoformat()}."
        rates = []

        def travail(t):
            for k, f in enumerate(envoi):
                t.avancer(_("Lecture de « {f} » par l'IA...", f=os.path.basename(f)), k, len(envoi))
                images = None
                texte = textes[f]
                if f in sans_texte:
                    with fitz.open(f) as d:
                        images = [d[0].get_pixmap(dpi=110, colorspace=fitz.csGRAY).tobytes("png")]
                    texte = _("Document numérisé : la première page est en image.")
                try:
                    r = ia.demander(self.params, consignes, texte, images=images, json_attendu=True, max_jetons=400)
                except InterruptedError:
                    raise
                except Exception as e:                   # noqa: BLE001
                    rates.append(os.path.basename(f))
                    t.noter(f"✕ {os.path.basename(f)} : {e}")
                    continue
                if isinstance(r, dict):
                    self.noms_ia[f] = {"nom": nom_propose(r), "infos": r}   # garde au fur et a mesure (Arreter)
                    t.noter(f"✓ {os.path.basename(f)} → {self.noms_ia[f]['nom']}")
            t.avancer(_("Terminé."), len(envoi), len(envoi))
        try:
            executer_suivi(self, _("Proposer les noms avec l'IA"), travail)
        except InterruptedError:
            pass
        except Exception as e:                           # noqa: BLE001
            QMessageBox.warning(self, _("Proposer les noms avec l'IA"), str(e))
        from .journal import ecrire
        ecrire("IA", f"traitement par lot : {len([f for f in envoi if f in self.noms_ia])} nom(s) proposé(s) sur {len(envoi)}")
        self.maj_apercu()
        if rates:
            QMessageBox.information(self, _("Proposer les noms avec l'IA"), _(
                "Pas de nom proposé pour {n} fichier(s) (ils gardent le nom selon le modèle) :\n{l}",
                n=len(rates), l="\n".join(rates[:15])))

    def _coche_action(self, w):
        cible = {self.prereglage: "alleger", self.noir_blanc: "alleger", self.t_filigrane: "filigrane",
                 self.b_prefixe: "bates", self.b_debut: "bates", self.b_chiffres: "bates"}[w]
        return lambda *_a: self.cases[cible].setChecked(True)

    def _sortie_change(self, *_a):
        s = self.sortie.currentData()
        self.suffixe.setVisible(s == "cote")
        if s == "dossier" and not getattr(self, "autre_dossier", ""):
            d = __import__('app.choix_dossier', fromlist=['x']).choisir_dossier(self, _("Dossier des fichiers produits"), self.dossier.text())
            if d:
                self.autre_dossier = d
            else:
                self.sortie.setCurrentIndex(0)
        self.maj_apercu()

    def choisir_dossier(self):
        d = __import__('app.choix_dossier', fromlist=['x']).choisir_dossier(self, _("Dossier des PDF"), self.dossier.text())
        if d:
            self.dossier.setText(d)
            self.lister()

    def ajouter_fichiers(self):
        fs, _x = QFileDialog.getOpenFileNames(self, _("PDF à traiter"), self.dossier.text(), "PDF (*.pdf)")
        for f in fs:
            if f not in self.fichiers:
                self.fichiers.append(f)
        self.maj_apercu()

    def lister(self, *_a):
        d = self.dossier.text().strip()
        if d and os.path.isdir(d):
            self.fichiers = fichiers_du_dossier(d, self.sous.isChecked())
        self.noms_ia = {f: v for f, v in self.noms_ia.items() if f in self.fichiers}
        self.maj_apercu()

    def reglages(self):
        return {"actions": [a for a in ACTIONS if self.cases[a].isChecked()],
                "prereglage": self.prereglage.currentIndex(), "noir_blanc": self.noir_blanc.isChecked(),
                "filigrane": self.t_filigrane.text().strip(), "bates_prefixe": self.b_prefixe.text(),
                "bates_debut": self.b_debut.value(), "bates_chiffres": self.b_chiffres.value(),
                "modele": self.modele.text().strip() or "{nom}", "chercher": self.chercher.text(),
                "remplacer": self.remplacer.text(), "sortie": self.sortie.currentData(),
                "dossier": getattr(self, "autre_dossier", ""), "suffixe": self.suffixe.text(),
                "signes": self.signes.isChecked(), "mode_nom": self.mode_nom.currentData(),
                "tri": self.tri.currentData() if self.mode_nom.currentData() == "ia" else "", "noms_ia": dict(self.noms_ia)}

    def maj_apercu(self, *_a):
        if self.tache and self.tache.isRunning():
            return
        r = self.reglages()
        self._remplissage = True
        self.table.setRowCount(len(self.fichiers))
        base = self.dossier.text().strip()
        par_ia = "renommer" in r["actions"] and r["mode_nom"] == "ia"
        for i, f in enumerate(self.fichiers):
            rel = os.path.relpath(f, base) if base and f.startswith(base) else f
            it0 = QTableWidgetItem(rel)
            it0.setFlags(it0.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(i, 0, it0)
            sortie = os.path.join(dossier_sortie(f, r), nom_sortie(f, r, i + 1))
            rel2 = os.path.relpath(sortie, base) if base and sortie.startswith(base) else sortie
            it1 = QTableWidgetItem(rel2)
            it1.setData(Qt.UserRole, f)
            if par_ia and f in self.noms_ia:
                it1.setToolTip(_("Proposé par l'IA : double-clic pour corriger"))
            else:
                it1.setFlags(it1.flags() & ~Qt.ItemIsEditable)
                if par_ia:
                    it1.setForeground(Qt.gray)
                    it1.setToolTip(_("Pas encore de nom proposé par l'IA : « Proposer les noms avec l'IA... »"))
            self.table.setItem(i, 1, it1)
            it2 = QTableWidgetItem("")
            it2.setFlags(it2.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(i, 2, it2)
        self._remplissage = False
        n = len(self.fichiers)
        acts = r["actions"]
        self.b_lancer.setEnabled(bool(n and acts))
        if hasattr(self, "b_mail"):
            self.b_mail.setEnabled(bool(n or self.produits))
        self.bilan.setText(_("{n} fichier(s) PDF.", n=n) + " " +
                           (_("Cochez au moins une action.") if not acts else
                            _("Vérifiez les noms à droite, puis « Lancer ». Les originaux restent intacts.")
                            if r["sortie"] != "remplacer" else
                            _("Les originaux seront remplacés ; une copie est gardée dans le dossier « Originaux ».")))

    def lancer(self):
        r = self.reglages()
        if not self.fichiers or not r["actions"]:
            return
        if r["actions"] == ["courriel"]:                    # rien a transformer : les fichiers partent tels quels
            self.envoyer_mail()
            return
        if "renommer" in r["actions"] and r["mode_nom"] == "ia":
            manquent = [f for f in self.fichiers if f not in self.noms_ia]
            if manquent:
                q = QMessageBox.question(self, self.windowTitle(), _(
                    "{n} fichier(s) n'ont pas encore de nom proposé par l'IA. Les proposer maintenant ?\n\n"
                    "Non : ils sont renommés selon le modèle.", n=len(manquent)),
                    QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
                if q == QMessageBox.Cancel:
                    return
                if q == QMessageBox.Yes:
                    self.proposer_noms()
                    return                                   # on revoit les noms avant de lancer
        if r["sortie"] == "remplacer" and QMessageBox.question(
                self, self.windowTitle(), _("Remplacer {n} fichier(s) ? Une copie de chacun est gardée dans le "
                                            "dossier « Originaux ».", n=len(self.fichiers))) != QMessageBox.Yes:
            return
        self.produits = []
        self.gain = 0
        self.barre.setRange(0, len(self.fichiers))
        self.barre.setValue(0)
        self.barre.show()
        self.b_lancer.setEnabled(False)
        self.b_arreter.setEnabled(True)
        self.tache = _Tache(list(self.fichiers), r)
        self.tache.etape.connect(self._etape)
        self.tache.fini.connect(self._fini)
        self.tache.start()

    def _etape(self, i, cible, journal, av, ap):
        it = QTableWidgetItem(("✓ " if cible else "– ") + journal +
                              (f"  ({av // 1024} → {ap // 1024} Ko)" if cible and av != ap else ""))
        it.setForeground(Qt.darkGreen if cible else Qt.darkYellow)
        if "erreur" in journal:
            it.setForeground(Qt.red)
        it.setToolTip(journal)
        self.table.setItem(i, 2, it)
        if cible:
            self.produits.append(cible)
            self.table.setItem(i, 1, QTableWidgetItem(cible))
            self.gain += av - ap
        self.barre.setValue(i + 1)

    def _fini(self):
        self.b_arreter.setEnabled(False)
        self.b_lancer.setEnabled(True)
        self.b_ouvrir.setEnabled(bool(self.produits))
        self.bilan.setText(_("Terminé : {n} fichier(s) produit(s) sur {t}.", n=len(self.produits), t=len(self.fichiers))
                           + (" " + _("{k} Ko gagnés.", k=self.gain // 1024) if self.gain > 0 else ""))
        if self.produits and self.cases["courriel"].isChecked() and not (self.tache and self.tache.stop):
            self.envoyer_mail()                            # « Envoyer par e-mail a la fin » : le message s'ouvre

    def envoyer_mail(self):
        from .dialogues_courriel import envoyer_fichiers
        fen = self.parent() if self.parent() is not None and hasattr(self.parent(), "statusBar") else self.window()
        self._mail = envoyer_fichiers(fen, self.produits or self.fichiers)

    def arreter(self):
        if self.tache:
            self.tache.stop = True
            self.bilan.setText(_("Arrêt après le fichier en cours..."))

    def ouvrir_dossier(self):
        if self.produits:
            from PySide6.QtGui import QDesktopServices
            from PySide6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(self.produits[0])))

    def closeEvent(self, e):
        if self.tache and self.tache.isRunning():
            self.tache.stop = True
            self.tache.wait(60000)
        super().closeEvent(e)
