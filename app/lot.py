"""Traitement par lot : une ou plusieurs actions sur tout un dossier (OCR, allegement, filigrane, numerotation Bates,
PDF/A, renommage). Avant de lancer, PhilPDF montre la liste des fichiers et les noms de sortie ; les originaux ne
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

ACTIONS = ("ocr", "alleger", "filigrane", "bates", "pdfa", "renommer")


def fichiers_du_dossier(dossier, sous_dossiers=False):
    out = []
    if sous_dossiers:
        for r, ds, fs in os.walk(dossier):
            ds[:] = [d for d in ds if d not in ("Traités", "Traites")]
            out += [os.path.join(r, f) for f in fs if f.lower().endswith(".pdf")]
    else:
        out = [os.path.join(dossier, f) for f in os.listdir(dossier) if f.lower().endswith(".pdf")]
    return sorted(out, key=lambda f: f.lower())


def nom_sortie(chemin, regl, n):
    """Nom du fichier produit (sans le dossier). n : rang du fichier dans le lot (1 pour le premier)."""
    base = os.path.splitext(os.path.basename(chemin))[0]
    if "renommer" in regl["actions"]:
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


def dossier_sortie(chemin, regl):
    if regl["sortie"] == "sous_dossier":
        return os.path.join(os.path.dirname(chemin), _("Traités"))
    if regl["sortie"] == "dossier" and regl.get("dossier"):
        return regl["dossier"]
    return os.path.dirname(chemin)


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
        cible = os.path.join(os.path.dirname(chemin), nom_sortie(chemin, regl, rang))
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
                    "pdfa": _("Archiver en PDF/A"), "renommer": _("Renommer")}
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
        g.addWidget(ga)
        gs = QGroupBox(_("Où mettre les fichiers produits"))
        fs = QVBoxLayout(gs)
        self.sortie = QComboBox()
        self.sortie.setObjectName("lot_sortie")
        self.sortie.addItem(_("Dans un sous-dossier « Traités » (conseillé)"), "sous_dossier")
        self.sortie.addItem(_("À côté des originaux, avec un suffixe"), "cote")
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
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
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
        self._sortie_change()
        if dossier:
            self.lister()

    def _coche_action(self, w):
        cible = {self.prereglage: "alleger", self.noir_blanc: "alleger", self.t_filigrane: "filigrane",
                 self.b_prefixe: "bates", self.b_debut: "bates", self.b_chiffres: "bates"}[w]
        return lambda *_a: self.cases[cible].setChecked(True)

    def _sortie_change(self, *_a):
        s = self.sortie.currentData()
        self.suffixe.setVisible(s == "cote")
        if s == "dossier" and not getattr(self, "autre_dossier", ""):
            d = QFileDialog.getExistingDirectory(self, _("Dossier des fichiers produits"), self.dossier.text())
            if d:
                self.autre_dossier = d
            else:
                self.sortie.setCurrentIndex(0)
        self.maj_apercu()

    def choisir_dossier(self):
        d = QFileDialog.getExistingDirectory(self, _("Dossier des PDF"), self.dossier.text())
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
        self.maj_apercu()

    def reglages(self):
        return {"actions": [a for a in ACTIONS if self.cases[a].isChecked()],
                "prereglage": self.prereglage.currentIndex(), "noir_blanc": self.noir_blanc.isChecked(),
                "filigrane": self.t_filigrane.text().strip(), "bates_prefixe": self.b_prefixe.text(),
                "bates_debut": self.b_debut.value(), "bates_chiffres": self.b_chiffres.value(),
                "modele": self.modele.text().strip() or "{nom}", "chercher": self.chercher.text(),
                "remplacer": self.remplacer.text(), "sortie": self.sortie.currentData(),
                "dossier": getattr(self, "autre_dossier", ""), "suffixe": self.suffixe.text(),
                "signes": self.signes.isChecked()}

    def maj_apercu(self, *_a):
        if self.tache and self.tache.isRunning():
            return
        r = self.reglages()
        self.table.setRowCount(len(self.fichiers))
        base = self.dossier.text().strip()
        for i, f in enumerate(self.fichiers):
            rel = os.path.relpath(f, base) if base and f.startswith(base) else f
            self.table.setItem(i, 0, QTableWidgetItem(rel))
            sortie = os.path.join(dossier_sortie(f, r), nom_sortie(f, r, i + 1))
            rel2 = os.path.relpath(sortie, base) if base and sortie.startswith(base) else sortie
            self.table.setItem(i, 1, QTableWidgetItem(rel2))
            self.table.setItem(i, 2, QTableWidgetItem(""))
        n = len(self.fichiers)
        acts = r["actions"]
        self.b_lancer.setEnabled(bool(n and acts))
        self.bilan.setText(_("{n} fichier(s) PDF.", n=n) + " " +
                           (_("Cochez au moins une action.") if not acts else
                            _("Vérifiez les noms à droite, puis « Lancer ». Les originaux restent intacts.")
                            if r["sortie"] != "remplacer" else
                            _("Les originaux seront remplacés ; une copie est gardée dans le dossier « Originaux ».")))

    def lancer(self):
        r = self.reglages()
        if not self.fichiers or not r["actions"]:
            return
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
