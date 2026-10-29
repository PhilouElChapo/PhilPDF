"""Fractionner un PDF en plusieurs fichiers, et parapher toutes les pages en un clic."""
import os

import pymupdf as fitz
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPixmap, QImage, QFont, QFontDatabase
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton, QComboBox,
                               QLineEdit, QSpinBox, QDoubleSpinBox, QRadioButton, QButtonGroup, QListWidget,
                               QFileDialog, QMessageBox, QCheckBox, QColorDialog, QDialogButtonBox, QApplication,
                               QGroupBox)

from .langue import _
from moteur import fractionner as F, paraphe as P


def _octets_lisibles(n):
    return f"{n / 1048576:.1f} Mo".replace(".", ",") if n >= 1048576 else f"{max(1, n // 1024)} Ko"


# ================================================================ fractionner
class DialogueFractionner(QDialog):
    """Choix du decoupage, liste des fichiers qui seront crees (nom, pages), puis ecriture."""

    def __init__(self, onglet):
        super().__init__(onglet)
        self.o, self.doc = onglet, onglet.doc
        self.setWindowTitle(_("Fractionner le document"))
        self.setMinimumSize(640, 560)
        r = onglet.params.get("fractionner") or {}
        self.morceaux = []
        self._minuterie = QTimer(self)
        self._minuterie.setSingleShot(True)
        self._minuterie.setInterval(350)
        self._minuterie.timeout.connect(self._calculer)
        v = QVBoxLayout(self)
        v.addWidget(QLabel(_("« {nom} » : {n} pages. Le document ouvert n'est pas modifié : les parties sont de "
                             "nouveaux fichiers.", nom=onglet.nom, n=len(self.doc))))
        g = QGroupBox(_("Découper"))
        f = QFormLayout(g)
        self.grp = QButtonGroup(self)
        toc = self.doc.get_toc()
        self.modes = {}

        def ligne(cle, texte, champ):
            rb = QRadioButton(texte)
            self.grp.addButton(rb)
            self.modes[cle] = rb
            rb.toggled.connect(self._maj)
            f.addRow(rb, champ)
        self.n_pages = QSpinBox()
        self.n_pages.setRange(1, max(1, len(self.doc)))
        self.n_pages.setValue(min(int(r.get("nombre", 1)), max(1, len(self.doc))))
        self.n_pages.setSuffix(_(" page(s) par fichier"))
        ligne("nombre", _("Toutes les"), self.n_pages)
        self.niveau = QComboBox()
        for i in range(1, 4):
            self.niveau.addItem(_("signets de niveau {n}", n=i) if i > 1 else _("signets principaux"), i)
        ligne("signets", _("À chaque signet"), self.niveau)
        self.taille = QDoubleSpinBox()
        self.taille.setRange(0.1, 500)
        self.taille.setDecimals(1)
        from PySide6.QtCore import QLocale
        self.taille.setLocale(QLocale(QLocale.French, QLocale.France))
        self.taille.setValue(float(r.get("taille", 10)))
        self.taille.setSuffix(_(" Mo maximum par fichier"))
        ligne("taille", _("Par taille"), self.taille)
        self.plages = QLineEdit(r.get("plages", ""))
        self.plages.setPlaceholderText(_("ex. 1-3, 4-10, 11-"))
        ligne("plages", _("Selon des plages"), self.plages)
        v.addWidget(g)
        if not toc:
            self.modes["signets"].setEnabled(False)
            self.modes["signets"].setToolTip(_("Ce document n'a pas de signets."))
            self.niveau.setEnabled(False)
        (self.modes.get(r.get("mode")) if (self.modes.get(r.get("mode")) and self.modes[r.get("mode")].isEnabled())
         else self.modes["signets" if toc else "nombre"]).setChecked(True)
        for w in (self.n_pages, self.taille):
            w.valueChanged.connect(self._plus_tard)
        self.niveau.currentIndexChanged.connect(self._plus_tard)
        self.plages.textChanged.connect(self._plus_tard)
        hd = QHBoxLayout()
        hd.addWidget(QLabel(_("Dossier")))
        base = os.path.dirname(onglet.chemin) if onglet.chemin and not getattr(onglet, "distant", None) else \
            os.path.join(os.path.expanduser("~"), "Documents")
        self.dossier = QLineEdit(base)
        hd.addWidget(self.dossier, 1)
        b = QPushButton(_("Parcourir..."))
        b.clicked.connect(self._parcourir)
        hd.addWidget(b)
        v.addLayout(hd)
        self.sous = QCheckBox(_("Dans un sous-dossier « {nom} »", nom=self._base()))
        self.sous.setChecked(r.get("sous_dossier", True))
        v.addWidget(self.sous)
        self.l_plan = QLabel()
        self.l_plan.setStyleSheet("font-weight:600;margin-top:6px")
        v.addWidget(self.l_plan)
        self.liste = QListWidget()
        self.liste.setObjectName("plan_fractionner")
        v.addWidget(self.liste, 1)
        self.ouvrir = QCheckBox(_("Ouvrir le dossier à la fin"))
        self.ouvrir.setChecked(r.get("ouvrir", True))
        v.addWidget(self.ouvrir)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.b_ok = bb.button(QDialogButtonBox.Ok)
        self.b_ok.setText(_("Créer les fichiers"))
        bb.button(QDialogButtonBox.Cancel).setText(_("Annuler"))
        bb.accepted.connect(self.valider)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self._maj()

    def _base(self):
        return os.path.splitext(self.o.nom)[0]

    def _parcourir(self):
        d = QFileDialog.getExistingDirectory(self, _("Dossier des fichiers fractionnés"), self.dossier.text())
        if d:
            self.dossier.setText(d)

    def mode(self):
        return next(k for k, rb in self.modes.items() if rb.isChecked())

    def _maj(self, *_a):
        m = self.mode() if any(rb.isChecked() for rb in self.modes.values()) else None
        self.n_pages.setEnabled(m == "nombre")
        self.niveau.setEnabled(m == "signets")
        self.taille.setEnabled(m == "taille")
        self.plages.setEnabled(m == "plages")
        self._plus_tard()

    def _plus_tard(self, *_a):
        self._minuterie.start()

    def _valeur(self, m):
        return {"nombre": self.n_pages.value(), "signets": self.niveau.currentData(), "taille": self.taille.value(),
                "plages": self.plages.text()}[m]

    def _calculer(self):
        m = self.mode()
        self.liste.clear()
        try:
            if m == "taille":
                QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                self.morceaux = F.plan(self.doc, self._base(), m, self._valeur(m))
            finally:
                if m == "taille":
                    QApplication.restoreOverrideCursor()
        except ValueError as e:
            self.morceaux = []
            self.l_plan.setText(_("Plage incorrecte : « {p} » (pages 1 à {n})", p=str(e), n=len(self.doc)))
            self.b_ok.setEnabled(False)
            return
        for nom, pages in self.morceaux:
            p = _("page {a}", a=pages[0] + 1) if len(pages) == 1 else _("pages {a} à {b}", a=pages[0] + 1, b=pages[-1] + 1)
            self.liste.addItem(f"{nom}    ({p})")
        n = len(self.morceaux)
        self.l_plan.setText(_("{n} fichier(s) seront créés :", n=n) if n > 1 else
                            _("Un seul fichier : rien à fractionner avec ce choix."))
        self.b_ok.setEnabled(n > 1)

    def valider(self):
        if self._minuterie.isActive():
            self._minuterie.stop()
            self._calculer()
        if len(self.morceaux) < 2:
            return
        dossier = self.dossier.text().strip()
        if self.sous.isChecked():
            dossier = os.path.join(dossier, F.nom_propre(self._base()))
        existants = [n for n, _p in self.morceaux if os.path.exists(os.path.join(dossier, n))]
        if existants and QMessageBox.question(
                self, self.windowTitle(),
                _("{n} fichier(s) de ce nom existent déjà dans ce dossier. Ils sont gardés : les nouveaux seront "
                  "nommés « (2) », « (3) »... Continuer ?", n=len(existants))) != QMessageBox.Yes:
            return
        m = self.mode()
        self.o.params["fractionner"] = {"mode": m, "nombre": self.n_pages.value(), "taille": self.taille.value(),
                                        "plages": self.plages.text(), "sous_dossier": self.sous.isChecked(),
                                        "ouvrir": self.ouvrir.isChecked()}
        self.o.params.enregistrer()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.faits = F.ecrire(self.doc, dossier, self.morceaux)
        except OSError as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, self.windowTitle(), _("Écriture impossible : {e}", e=e))
            return
        QApplication.restoreOverrideCursor()
        self.dossier_fait = dossier
        if self.ouvrir.isChecked():
            from PySide6.QtGui import QDesktopServices
            from PySide6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl.fromLocalFile(dossier))
        self.accept()


# ================================================================ paraphe
def remplir_polices_initiales(combo, doc):
    """Polices ecrites dans leur propre police : standard PDF, celles du document, puis celles du PC (les
    polices manuscrites du PC d'abord, les plus utilisees pour un paraphe)."""
    from moteur import apparence as AP

    def titre(t):
        combo.addItem("— " + t + " —", None)
        it = combo.model().item(combo.count() - 1)
        it.setEnabled(False)
        fo = QFont()
        fo.setBold(True)
        fo.setPointSize(9)
        it.setFont(fo)

    def ajouter(lib, cle, fo):
        combo.addItem(lib, cle)
        fo.setPointSize(13)
        combo.setItemData(combo.count() - 1, fo, Qt.FontRole)
    titre(_("Polices standard du PDF"))
    for k, lib, fam, gras, ital in (("TiIt", "Times italique", "Times New Roman", False, True),
                                    ("Helv", "Helvetica", "Arial", False, False),
                                    ("HeBo", "Helvetica gras", "Arial", True, False),
                                    ("HeOb", "Helvetica italique", "Arial", False, True),
                                    ("TiRo", "Times", "Times New Roman", False, False),
                                    ("TiBo", "Times gras", "Times New Roman", True, False),
                                    ("Cour", "Courier", "Courier New", False, False)):
        fo = QFont(fam)
        fo.setBold(gras)
        fo.setItalic(ital)
        ajouter(lib, k, fo)
    pol = P.polices_pages(doc)
    if pol:
        titre(_("Polices du document"))
        for nom, xref in pol:
            fo = QFont()
            try:
                i = QFontDatabase.addApplicationFontFromData(doc.extract_font(xref)[3])
                fams = QFontDatabase.applicationFontFamilies(i) if i >= 0 else []
                if fams:
                    fo = QFont(fams[0])
            except Exception:                         # noqa: BLE001
                pass
            ajouter(nom, f"doc:{xref}", fo)
    sys_pol = AP.polices_systeme()
    if sys_pol:
        titre(_("Polices de ce PC (intégrées au PDF)"))
        familles = set(QFontDatabase.families())
        manuscrites = ("script", "hand", "ink free", "brush", "segoe print", "mistral", "kristen", "comic", "bradley",
                       "freestyle", "vladimir", "pacifico", "dancing", "caveat", "satisfy")
        tri = sorted(sys_pol, key=lambda x: (not any(m in x[0].lower() for m in manuscrites), x[0].lower()))
        for nom, chemin in tri:
            fam = next((f for f in (nom, nom.rsplit(" ", 1)[0], nom.split(" ")[0]) if f in familles), None)
            fo = QFont(fam) if fam else QFont()
            if fam and ("Bold" in nom or "Gras" in nom):
                fo.setBold(True)
            if fam and ("Italic" in nom or "Italique" in nom):
                fo.setItalic(True)
            ajouter(nom, "fichier:" + chemin, fo)


POSITIONS = [("bas_droite", _("En bas à droite")), ("bas_centre", _("En bas au centre")),
             ("bas_gauche", _("En bas à gauche")), ("haut_droite", _("En haut à droite")),
             ("haut_gauche", _("En haut à gauche"))]
PAGES = [("toutes", _("Toutes les pages")), ("sauf_derniere", _("Toutes sauf la dernière (signée)")),
         ("sauf_premiere", _("Toutes sauf la première")), ("plage", _("Pages choisies"))]


def initiales_de(nom):
    """« Jean-Philippe Durand » -> « J.-P. D. »."""
    out = []
    for mot in (nom or "").split():
        parts = [p for p in mot.split("-") if p]
        if parts:
            out.append("-".join(p[0].upper() + "." for p in parts))
    return " ".join(out)


class DialogueParaphe(QDialog):
    """Paraphe en un clic : tampon « paraphe » de la bibliotheque, ou initiales dans une police ; apercu de la page."""

    def __init__(self, onglet):
        super().__init__(onglet)
        self.o, self.doc, self.params = onglet, onglet.doc, onglet.params
        self.setWindowTitle(_("Parapher toutes les pages"))
        self.setMinimumSize(860, 600)
        r = self.params.get("paraphe") or {}
        h = QHBoxLayout(self)
        g = QVBoxLayout()
        h.addLayout(g, 3)
        self.grp = QButtonGroup(self)
        self.r_tampon = QRadioButton(_("Mon tampon"))
        self.r_init = QRadioButton(_("Mes initiales, écrites dans une police"))
        self.grp.addButton(self.r_tampon)
        self.grp.addButton(self.r_init)
        g.addWidget(self.r_tampon)
        self.tampons = QComboBox()
        if onglet.biblio is None:
            from .bibliotheque import Bibliotheque
            onglet.biblio = Bibliotheque(self.params)
        self._tampons = list(onglet.biblio.elements("tampons"))
        for e in self._tampons:
            self.tampons.addItem(e["nom"], e["id"])
        i = next((k for k, e in enumerate(self._tampons) if e["id"] == r.get("tampon")), None)
        if i is None:
            i = next((k for k, e in enumerate(self._tampons) if "paraphe" in e["nom"].lower()), 0)
        self.tampons.setCurrentIndex(i)
        g.addWidget(self.tampons)
        g.addWidget(self.r_init)
        f = QFormLayout()
        self.texte = QLineEdit(r.get("texte") or initiales_de(self.params.get("auteur", "")))
        self.texte.setPlaceholderText(_("ex. J.-P. D."))
        f.addRow(_("Initiales"), self.texte)
        self.police = QComboBox()
        self.police.setMaxVisibleItems(18)
        remplir_polices_initiales(self.police, self.doc)
        k = self.police.findData(r.get("police", "TiIt"))
        self.police.setCurrentIndex(k if k >= 0 else 1)
        f.addRow(_("Police"), self.police)
        hc = QHBoxLayout()
        self.couleur = QColor(r.get("couleur", "#1a3390"))
        self.b_coul = QPushButton()
        self.b_coul.setFixedWidth(60)
        self.b_coul.clicked.connect(self._choisir_couleur)
        hc.addWidget(self.b_coul)
        self.souligne = QCheckBox(_("Souligné"))
        self.souligne.setChecked(r.get("souligne", False))
        hc.addWidget(self.souligne)
        hc.addStretch(1)
        f.addRow(_("Couleur"), hc)
        g.addLayout(f)
        self.b_garder = QPushButton(_("Garder comme tampon « paraphe »"))
        self.b_garder.setToolTip(_("Ajouté à Mes tampons (suit sur vos autres postes)"))
        self.b_garder.clicked.connect(self._garder)
        g.addWidget(self.b_garder)
        f2 = QFormLayout()
        self.position = QComboBox()
        for k_, lib in POSITIONS:
            self.position.addItem(lib, k_)
        self.position.setCurrentIndex(max(0, self.position.findData(r.get("position", "bas_droite"))))
        f2.addRow(_("Position"), self.position)
        self.hauteur = QSpinBox()
        self.hauteur.setRange(4, 60)
        self.hauteur.setSuffix(" mm")
        self.hauteur.setValue(int(r.get("hauteur_mm", 10)))
        f2.addRow(_("Hauteur"), self.hauteur)
        self.marge = QSpinBox()
        self.marge.setRange(0, 60)
        self.marge.setSuffix(" mm")
        self.marge.setValue(int(r.get("marge_mm", 8)))
        f2.addRow(_("Marge du bord"), self.marge)
        self.pages = QComboBox()
        for k_, lib in PAGES:
            self.pages.addItem(lib, k_)
        self.pages.setCurrentIndex(max(0, self.pages.findData(r.get("pages", "toutes"))))
        f2.addRow(_("Pages"), self.pages)
        self.plage = QLineEdit()
        self.plage.setPlaceholderText(_("ex. 1-5, 8"))
        f2.addRow("", self.plage)
        g.addLayout(f2)
        g.addStretch(1)
        self.l_nb = QLabel()
        g.addWidget(self.l_nb)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.b_ok = bb.button(QDialogButtonBox.Ok)
        self.b_ok.setText(_("Parapher"))
        bb.button(QDialogButtonBox.Cancel).setText(_("Annuler"))
        bb.accepted.connect(self.valider)
        bb.rejected.connect(self.reject)
        g.addWidget(bb)
        d = QVBoxLayout()
        d.addWidget(QLabel(_("<b>Aperçu</b> (première page paraphée)")))
        self.apercu = QLabel()
        self.apercu.setObjectName("apercu_paraphe")
        self.apercu.setAlignment(Qt.AlignCenter)
        self.apercu.setMinimumSize(340, 460)
        self.apercu.setStyleSheet("background:#e6e6e6")
        d.addWidget(self.apercu, 1)
        h.addLayout(d, 2)
        (self.r_tampon if (self._tampons and r.get("source", "tampon" if any(
            "paraphe" in e["nom"].lower() for e in self._tampons) else "initiales") == "tampon") else self.r_init).setChecked(True)
        self.r_tampon.setEnabled(bool(self._tampons))
        if not self._tampons:
            self.r_tampon.setText(_("Mon tampon (aucun dans Mes tampons pour l'instant)"))
            self.tampons.hide()
        for w in (self.r_tampon, self.r_init, self.souligne):
            w.toggled.connect(self._maj)
        for w in (self.tampons, self.police, self.position, self.pages):
            w.currentIndexChanged.connect(self._maj)
        for w in (self.hauteur, self.marge):
            w.valueChanged.connect(self._maj)
        self.texte.textChanged.connect(self._maj)
        self.plage.textChanged.connect(self._maj)
        self._maj()

    def showEvent(self, e):
        super().showEvent(e)
        QTimer.singleShot(0, self._maj)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if hasattr(self, "b_ok"):
            QTimer.singleShot(0, self._maj)

    def _choisir_couleur(self):
        c = QColorDialog.getColor(self.couleur, self, _("Couleur des initiales"))
        if c.isValid():
            self.couleur = c
            self._maj()

    def pdf(self):
        """Octets du paraphe choisi."""
        if self.r_tampon.isChecked() and self._tampons:
            return self.o.biblio.lire(self._tampons[self.tampons.currentIndex()])
        c = self.couleur
        return P.initiales_pdf(self.texte.text(), self.police.currentData() or "TiIt",
                               (c.redF(), c.greenF(), c.blueF()), self.souligne.isChecked(), self.doc)

    def liste_pages(self):
        return P.pages_choisies(len(self.doc), self.pages.currentData(), self.plage.text())

    def _maj(self, *_a):
        ini = self.r_init.isChecked()
        for w in (self.texte, self.police, self.b_coul, self.souligne, self.b_garder):
            w.setEnabled(ini)
        self.tampons.setEnabled(self.r_tampon.isChecked())
        self.b_coul.setStyleSheet(f"background:{self.couleur.name()};border:1px solid #888;border-radius:4px;min-height:22px")
        self.plage.setVisible(self.pages.currentData() == "plage")
        try:
            pages = self.liste_pages()
        except ValueError:
            self.l_nb.setText(_("Pages incorrectes (1 à {n}).", n=len(self.doc)))
            self.b_ok.setEnabled(False)
            return
        self.l_nb.setText(_("{n} page(s) seront paraphées.", n=len(pages)))
        self.b_ok.setEnabled(bool(pages) and (not ini or bool(self.texte.text().strip())))
        if not pages:
            return
        try:
            essai = fitz.open()
            essai.insert_pdf(self.doc, from_page=pages[0], to_page=pages[0], annots=True)
            mm = 72 / 25.4
            P.parapher(essai, self.pdf(), [0], self.position.currentData(), self.hauteur.value() * mm,
                       self.marge.value() * mm)
            dpr = self.devicePixelRatioF()
            r = essai[0].rect
            z = min((self.apercu.width() - 16) / r.width, (self.apercu.height() - 16) / r.height) * dpr
            pm = essai[0].get_pixmap(matrix=fitz.Matrix(z, z), annots=True)
            img = QImage(pm.samples, pm.width, pm.height, pm.stride, QImage.Format_RGB888).copy()
            pix = QPixmap.fromImage(img)
            pix.setDevicePixelRatio(dpr)
            self.apercu.setPixmap(pix)
        except Exception as e:                        # noqa: BLE001
            self.apercu.setText(str(e)[:200])

    def _garder(self):
        e = self.o.biblio.ajouter("tampons", "paraphe", self.pdf())
        self._tampons = list(self.o.biblio.elements("tampons"))
        self.tampons.blockSignals(True)
        self.tampons.clear()
        for x in self._tampons:
            self.tampons.addItem(x["nom"], x["id"])
        self.tampons.setCurrentIndex(max(0, self.tampons.findData(e["id"])))
        self.tampons.blockSignals(False)
        self.r_tampon.setEnabled(True)
        self.r_tampon.setText(_("Mon tampon"))
        self.tampons.show()
        self.r_tampon.setChecked(True)
        QMessageBox.information(self, self.windowTitle(), _("Gardé dans Mes tampons sous le nom « paraphe »."))

    def valider(self):
        try:
            pages = self.liste_pages()
        except ValueError:
            return
        tampon = self._tampons[self.tampons.currentIndex()]["id"] if self._tampons else None
        self.params["paraphe"] = {"source": "tampon" if self.r_tampon.isChecked() else "initiales",
                                  "tampon": tampon, "texte": self.texte.text(),
                                  "police": self.police.currentData(), "couleur": self.couleur.name(),
                                  "souligne": self.souligne.isChecked(), "position": self.position.currentData(),
                                  "hauteur_mm": self.hauteur.value(), "marge_mm": self.marge.value(),
                                  "pages": self.pages.currentData()}
        self.params.enregistrer()
        self.resultat = (self.pdf(), pages, self.position.currentData(), self.hauteur.value() * 72 / 25.4,
                         self.marge.value() * 72 / 25.4)
        self.accept()
