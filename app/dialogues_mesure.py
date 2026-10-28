"""Fenetres de l'outil Mesure : reglage de l'echelle d'une page, liste des mesures (copie, export Excel)."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QComboBox, QDoubleSpinBox,
                               QRadioButton, QButtonGroup, QCheckBox, QDialogButtonBox, QTableWidget,
                               QTableWidgetItem, QPushButton, QHeaderView, QApplication, QFileDialog, QMessageBox,
                               QInputDialog, QWidget)

from moteur import mesure as M
from .langue import _
from .dialogues import boutons_fr

RAPPORTS = [20, 50, 100, 200, 250, 500, 1000, 1250, 2000, 2500, 5000, 10000, 25000]
UNITES = [("m", _("mètres (m)")), ("cm", _("centimètres (cm)")), ("mm", _("millimètres (mm)")),
          ("km", _("kilomètres (km)")), ("ft", _("pieds (ft)")), ("in", _("pouces (in)"))]


def libelle_echelle(e):
    if not e:
        return _("aucune")
    if e.get("genre") == "papier":
        return _("aucune (mesures du papier, en cm)")
    t = e.get("texte") or ""
    if e["u"] in M.UNITES and e.get("genre") != "rapport":
        t = f"1:{M._n(M.rapport(e))}" + (f"  ({t})" if t and not t.startswith("1:") else "")
    return t + "  ·  " + _("en {u}", u=e["u"])


class DialogueEchelle(QDialog):
    """Echelle de la page, choisie au moment de mesurer. resultat = echelle, ou {"etalonner": unite} pour cliquer
    ensuite les deux bouts d'une longueur connue."""

    def __init__(self, parent, num_page, lue_pdf=None, lue_texte=None, actuelle=None):
        super().__init__(parent)
        self.setWindowTitle(_("Echelle de la page {n}", n=num_page + 1))
        self.setMinimumWidth(560)
        v = QVBoxLayout(self)
        intro = QLabel(_("A quelle échelle est ce plan ? Elle sert à convertir ce que vous mesurez à l'écran en "
                         "longueurs et surfaces réelles. Chaque page peut avoir la sienne."))
        intro.setWordWrap(True)
        v.addWidget(intro)
        self.groupe = QButtonGroup(self)
        self.lue = lue_pdf
        self.r_pdf = None
        if lue_pdf:
            self.r_pdf = QRadioButton(_("Celle enregistrée dans le PDF : {e}", e=libelle_echelle(lue_pdf)))
            v.addWidget(self.r_pdf)
            self.groupe.addButton(self.r_pdf)
        # rapport
        self.r_rapport = QRadioButton(_("Rapport du plan"))
        self.groupe.addButton(self.r_rapport)
        h = QHBoxLayout()
        h.addWidget(self.r_rapport)
        h.addWidget(QLabel("1 :"))
        self.rapport = QComboBox()
        self.rapport.setEditable(True)
        self.rapport.setObjectName("ech_rapport")
        for r in RAPPORTS:
            self.rapport.addItem(str(r))
        self.rapport.setCurrentText("100")
        h.addWidget(self.rapport)
        h.addStretch(1)
        v.addLayout(h)
        if lue_texte:
            n, lib = lue_texte
            self.rapport.setCurrentText(str(n))
            l = QLabel(_("Lu sur le plan : « {t} ». Juste seulement si le PDF est à la taille de l'impression "
                         "d'origine : vérifiez sur une cote connue.", t=lib))
            l.setWordWrap(True)
            l.setStyleSheet("color:#8a5a00;margin-left:24px")
            v.addWidget(l)
        # equivalence
        self.r_equiv = QRadioButton(_("Equivalence"))
        self.groupe.addButton(self.r_equiv)
        h = QHBoxLayout()
        h.addWidget(self.r_equiv)
        self.papier = QDoubleSpinBox()
        self.papier.setDecimals(2)
        self.papier.setRange(0.01, 1000)
        self.papier.setValue(1)
        h.addWidget(self.papier)
        h.addWidget(QLabel(_("cm sur le papier =")))
        self.reel = QDoubleSpinBox()
        self.reel.setDecimals(3)
        self.reel.setRange(0.001, 1000000)
        self.reel.setValue(1)
        h.addWidget(self.reel)
        self.u_equiv = QComboBox()
        for u, _l in UNITES:
            self.u_equiv.addItem(u, u)
        h.addWidget(self.u_equiv)
        h.addStretch(1)
        v.addLayout(h)
        # etalonnage
        self.r_etalon = QRadioButton(_("Etalonner sur une longueur connue (une cote, l'échelle graphique, un mur...)"))
        self.r_etalon.setObjectName("ech_etalon")
        self.groupe.addButton(self.r_etalon)
        v.addWidget(self.r_etalon)
        l = QLabel(_("Après OK : cliquez les deux bouts de cette longueur sur le plan, puis tapez sa vraie longueur. "
                     "C'est le plus sûr, surtout pour un plan scanné ou réduit."))
        l.setWordWrap(True)
        l.setStyleSheet("color:#555;margin-left:24px")
        v.addWidget(l)
        self.r_papier = QRadioButton(_("Sans échelle : mesurer le papier (en cm)"))
        self.groupe.addButton(self.r_papier)
        v.addWidget(self.r_papier)
        f = QFormLayout()
        self.unite = QComboBox()
        self.unite.setObjectName("ech_unite")
        for u, l_ in UNITES:
            self.unite.addItem(l_, u)
        f.addRow(_("Résultats en"), self.unite)
        v.addLayout(f)
        self.toutes = QCheckBox(_("Même échelle pour toutes les pages de ce document"))
        self.toutes.setObjectName("ech_toutes")
        v.addWidget(self.toutes)
        self.garder = QCheckBox(_("Garder l'échelle dans le PDF (Acrobat la reprend dans son outil Mesure)"))
        self.garder.setChecked(True)
        v.addWidget(self.garder)
        bb = boutons_fr(QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel))
        bb.accepted.connect(self.valider)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        # choix de depart : l'echelle actuelle, sinon celle du PDF, sinon ce qui est lu, sinon etalonner
        e = actuelle or lue_pdf
        if e and e.get("genre") == "pdf" and self.r_pdf:
            self.r_pdf.setChecked(True)
        elif e and e.get("genre") == "rapport":
            self.r_rapport.setChecked(True)
            self.rapport.setCurrentText(M._n(M.rapport(e)))
        elif e and e.get("genre") == "papier":
            self.r_papier.setChecked(True)
        elif lue_texte:
            self.r_rapport.setChecked(True)
        else:
            self.r_etalon.setChecked(True)
        if e and e.get("u") in M.UNITES and e.get("genre") != "papier":
            self.unite.setCurrentIndex(self.unite.findData(e["u"]))
        self.u_equiv.currentIndexChanged.connect(lambda _i: self.unite.setCurrentIndex(
            self.unite.findData(self.u_equiv.currentData())))
        for w in (self.rapport, self.papier, self.reel, self.u_equiv):
            (w.currentTextChanged if isinstance(w, QComboBox) else w.valueChanged).connect(self._coche_selon(w))

    def _coche_selon(self, w):
        def f(*_a):
            (self.r_rapport if w is self.rapport else self.r_equiv).setChecked(True)
        return f

    def valider(self):
        u = self.unite.currentData()
        try:
            if self.r_pdf is not None and self.r_pdf.isChecked():
                e = dict(self.lue)
                if e["u"] in M.UNITES and u != e["u"]:
                    e = M.dans_unite(e, u)
            elif self.r_rapport.isChecked():
                n = float(self.rapport.currentText().replace(",", ".").replace(" ", ""))
                if n <= 0:
                    raise ValueError
                e = M.depuis_rapport(n, u)
            elif self.r_equiv.isChecked():
                e = M.depuis_equivalence(self.papier.value(), self.reel.value(), self.u_equiv.currentData())
                if u != e["u"]:
                    e = dict(M.dans_unite(e, u), texte=e["texte"])
            elif self.r_etalon.isChecked():
                e = {"etalonner": u}
            else:
                e = M.sans_echelle()
        except ValueError:
            QMessageBox.warning(self, _("Echelle"), _("Rapport incorrect : tapez par exemple 100 pour 1:100."))
            return
        self.resultat = e
        self.accept()


def demander_longueur(parent, unite):
    """Vraie longueur du segment d'etalonnage ; None si annule."""
    v, ok = QInputDialog.getDouble(parent, _("Etalonner"), _("Vraie longueur de ce que vous venez de mesurer ({u}) :",
                                                             u=unite), 1.0, 0.001, 10000000, 3)
    return v if ok and v > 0 else None


class DialogueMesures(QDialog):
    """Toutes les mesures du document, avec les totaux ; copier, exporter vers Excel, renommer, supprimer."""

    def __init__(self, onglet):
        super().__init__(onglet)
        self.o = onglet
        self.setWindowTitle(_("Mesures du document"))
        self.resize(760, 460)
        v = QVBoxLayout(self)
        self.table = QTableWidget(0, 5)
        self.table.setObjectName("table_mesures")
        self.table.setHorizontalHeaderLabels([_("Page"), _("Nom"), _("Type"), _("Valeur"), _("Echelle")])
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.cellDoubleClicked.connect(lambda r, _c: self.o.aller_a(self.mesures[r]["page"]))
        v.addWidget(self.table, 1)
        self.totaux = QLabel()
        self.totaux.setWordWrap(True)
        self.totaux.setStyleSheet("color:#333;padding:4px")
        v.addWidget(self.totaux)
        h = QHBoxLayout()
        for txt, f in ((_("Renommer..."), self.renommer), (_("Supprimer"), self.supprimer), (None, None),
                       (_("Copier le tableau"), self.copier), (_("Exporter vers Excel..."), self.exporter)):
            if txt is None:
                h.addStretch(1)
                continue
            b = QPushButton(txt)
            b.clicked.connect(f)
            h.addWidget(b)
        b = QPushButton(_("Fermer"))
        b.clicked.connect(self.accept)
        h.addWidget(b)
        v.addLayout(h)
        self.remplir()

    def remplir(self):
        self.mesures = M.lister(self.o.doc)
        noms = {"distance": _("Distance"), "perimetre": _("Périmètre"), "surface": _("Surface")}
        self.table.setRowCount(len(self.mesures))
        tot = {}
        for i, m in enumerate(self.mesures):
            val = m["texte"].split(" : ", 1)[-1] if m["nom"] else m["texte"]
            for j, t in enumerate((str(m["page"] + 1), m["nom"], noms.get(m["genre"], m["genre"]), val,
                                   m["echelle"] if m["philpdf"] else _("(Acrobat)"))):
                it = QTableWidgetItem(t)
                if j == 0:
                    it.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(i, j, it)
            if m["valeur"]:
                k = (m["genre"], m["unite"])
                tot[k] = tot.get(k, 0) + (m["valeur"]["aire"] if m["genre"] == "surface" else m["valeur"]["longueur"])
        lignes = []
        for (g, u), x in sorted(tot.items()):
            lignes.append(_("Total {type} : {v}", type=noms[g].lower(),
                            v=M.texte_valeur(g, {"aire": x, "longueur": x}, u)))
        self.totaux.setText("   ·   ".join(lignes) if lignes else _("Aucune mesure dans ce document."))

    def _choisie(self):
        r = self.table.currentRow()
        return self.mesures[r] if 0 <= r < len(self.mesures) else None

    def renommer(self):
        m = self._choisie()
        if not m or not m["philpdf"]:
            return
        nom, ok = QInputDialog.getText(self, _("Renommer"), _("Nom de la mesure (ex. Salon, Parcelle 12) :"), text=m["nom"])
        if ok:
            self.o.memoriser(_("Mesure renommée"))
            M.renommer(self.o.doc, m["page"], m["ident"], nom.strip())
            self.o.apres_modif([_("Mesure renommée : {n}", n=nom.strip() or "-")])
            self.remplir()

    def supprimer(self):
        m = self._choisie()
        if not m:
            return
        self.o.memoriser(_("Mesure supprimée"))
        if m["ident"]:
            M.supprimer(self.o.doc, m["page"], m["ident"])
        else:
            page = self.o.doc[m["page"]]
            a = next((a for a in page.annots() if a.xref == m["xref"]), None)
            if a:
                page.delete_annot(a)
        self.o.apres_modif([_("Mesure supprimée.")])
        self.remplir()

    def lignes(self):
        out = [[_("Page"), _("Nom"), _("Type"), _("Valeur"), _("Unité"), _("Echelle"), _("Texte")]]
        noms = {"distance": _("Distance"), "perimetre": _("Périmètre"), "surface": _("Surface")}
        for m in self.mesures:
            v = m["valeur"]
            x = None if not v else round(v["aire"] if m["genre"] == "surface" else v["longueur"], 4)
            u = (m["unite"] + "²" if m["genre"] == "surface" else m["unite"]) if v else ""
            out.append([m["page"] + 1, m["nom"], noms.get(m["genre"], m["genre"]), x, u, m["echelle"], m["texte"]])
        return out

    def copier(self):
        txt = "\n".join("\t".join("" if c is None else str(c).replace(".", ",") if isinstance(c, float) else str(c)
                                  for c in l) for l in self.lignes())
        QApplication.clipboard().setText(txt)
        self.totaux.setText(self.totaux.text() + "   ·   " + _("Copié : collez dans Excel ou un courrier."))

    def exporter(self):
        import os
        base = os.path.splitext(self.o.nom)[0] + " - mesures.xlsx"
        dossier = os.path.dirname(self.o.chemin) if getattr(self.o, "chemin", None) else ""
        f, _x = QFileDialog.getSaveFileName(self, _("Exporter vers Excel"), os.path.join(dossier, base), "Excel (*.xlsx)")
        if not f:
            return
        from moteur import tableaux
        tableaux.ecrire_xlsx(f, [(_("Mesures"), self.lignes())])
        QMessageBox.information(self, _("Exporter vers Excel"), _("Mesures enregistrées :\n{f}", f=f))
