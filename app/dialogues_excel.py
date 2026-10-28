"""Tableaux du PDF vers Excel : PhilPDF montre ce qu'il a repere (cadres sur la page, contenu cellule par cellule)
avant d'ecrire le .xlsx. On coche les tableaux voulus, on peut en tracer un a la main."""
import os

import pymupdf as fitz
from PySide6.QtCore import Qt, QRectF, Signal, QPointF
from PySide6.QtGui import QImage, QPixmap, QPainter, QPen, QColor, QFont
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QCheckBox, QPushButton,
                               QListWidget, QListWidgetItem, QTableWidget, QTableWidgetItem, QSplitter, QWidget,
                               QFileDialog, QMessageBox, QSpinBox, QFormLayout, QApplication)

from moteur import tableaux as TB
from .langue import _

COULEURS = ["#1462c2", "#2a7a3b", "#b0186b", "#a35c00", "#6d3fc6", "#0b7a80"]


class VuePage(QLabel):
    """La page, avec les tableaux reperes encadres et numerotes ; glisser pour tracer un tableau a la main."""
    zone = Signal(object)              # fitz.Rect trace
    choisi = Signal(int)               # indice du tableau clique

    def __init__(self):
        super().__init__()
        self.setMinimumSize(420, 520)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("background:#e6e6e6")
        self.setMouseTracking(True)
        self.doc, self.num, self.cadres, self.actif = None, 0, [], None
        self.k, self.dx, self.dy, self.img = 1, 0, 0, None
        self.debut, self.fin = None, None

    def montrer(self, doc, num, cadres, actif):
        self.doc, self.num, self.cadres, self.actif = doc, num, cadres, actif
        page = doc[num]
        k = min((self.width() - 16) / page.rect.width, (self.height() - 16) / page.rect.height)
        self.k = max(0.2, k)
        pm = page.get_pixmap(matrix=fitz.Matrix(self.k, self.k), alpha=False)
        self.img = QImage(pm.samples, pm.width, pm.height, pm.stride, QImage.Format_RGB888).copy()
        self.update()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.doc is not None:
            self.montrer(self.doc, self.num, self.cadres, self.actif)

    def _vers_pdf(self, p):
        return fitz.Point((p.x() - self.dx) / self.k, (p.y() - self.dy) / self.k)

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#e6e6e6"))
        if self.img is None:
            return
        self.dx, self.dy = (self.width() - self.img.width()) // 2, (self.height() - self.img.height()) // 2
        p.drawImage(self.dx, self.dy, self.img)
        fo = QFont()
        fo.setBold(True)
        p.setFont(fo)
        for i, r, coche in self.cadres:
            c = QColor(COULEURS[i % len(COULEURS)])
            rr = QRectF(self.dx + r.x0 * self.k, self.dy + r.y0 * self.k, r.width * self.k, r.height * self.k)
            p.setPen(QPen(c, 3 if i == self.actif else 1.6, Qt.SolidLine if coche else Qt.DashLine))
            c2 = QColor(c)
            c2.setAlpha(40 if coche else 12)
            p.setBrush(c2)
            p.drawRect(rr)
            etiq = QRectF(rr.x(), rr.y() - 18, 26, 18)
            p.setPen(Qt.NoPen)
            p.setBrush(c)
            p.drawRoundedRect(etiq, 3, 3)
            p.setPen(QColor("#ffffff"))
            p.drawText(etiq, Qt.AlignCenter, str(i + 1))
        if self.debut and self.fin:
            p.setPen(QPen(QColor("#d81b60"), 1.5, Qt.DashLine))
            p.setBrush(QColor(216, 27, 96, 25))
            p.drawRect(QRectF(self.debut, self.fin).normalized())
        p.end()

    def mousePressEvent(self, e):
        pt = self._vers_pdf(e.position())
        for i, r, _c in reversed(self.cadres):
            if r.contains(pt):
                self.choisi.emit(i)
                return
        self.debut, self.fin = e.position(), e.position()

    def mouseMoveEvent(self, e):
        if self.debut is not None:
            self.fin = e.position()
            self.update()
        else:
            pt = self._vers_pdf(e.position())
            dedans = any(r.contains(pt) for _i, r, _c in self.cadres)
            self.setCursor(Qt.PointingHandCursor if dedans else Qt.CrossCursor)

    def mouseReleaseEvent(self, e):
        if self.debut is None:
            return
        r = fitz.Rect(self._vers_pdf(self.debut), self._vers_pdf(e.position()))
        r.normalize()
        self.debut = self.fin = None
        self.update()
        if r.width > 20 and r.height > 10:
            self.zone.emit(r)


class DialogueExcel(QDialog):
    def __init__(self, onglet):
        super().__init__(onglet)
        self.o, self.doc = onglet, onglet.doc
        self.setWindowTitle(_("Tableaux vers Excel"))
        self.resize(1180, 760)
        v = QVBoxLayout(self)
        intro = QLabel(_("PhilPDF a repéré les tableaux encadrés en couleur. Cochez ceux à mettre dans Excel et "
                         "vérifiez leur contenu à droite : c'est exactement ce qui sera écrit. Si un tableau manque, "
                         "tracez-le sur la page à la souris."))
        intro.setWordWrap(True)
        v.addWidget(intro)
        h = QHBoxLayout()
        h.addWidget(QLabel(_("Repérage :")))
        self.strategie = QComboBox()
        self.strategie.setObjectName("xl_strategie")
        for k, t in (("auto", _("Automatique")), ("traits", _("Tableaux encadrés (traits)")),
                     ("texte", _("Colonnes alignées, sans traits (relevés)"))):
            self.strategie.addItem(t, k)
        self.strategie.currentIndexChanged.connect(self.reperer)
        h.addWidget(self.strategie)
        self.assembler = QCheckBox(_("Réunir un tableau qui continue sur la page suivante"))
        self.assembler.setChecked(True)
        self.assembler.toggled.connect(self.reperer)
        h.addWidget(self.assembler)
        h.addStretch(1)
        v.addLayout(h)
        sp = QSplitter()
        v.addWidget(sp, 1)
        gauche = QWidget()
        gv = QVBoxLayout(gauche)
        gv.setContentsMargins(0, 0, 0, 0)
        nav = QHBoxLayout()
        self.b_prec = QPushButton("‹")
        self.b_prec.clicked.connect(lambda: self.aller(self.num - 1))
        self.b_suiv = QPushButton("›")
        self.b_suiv.clicked.connect(lambda: self.aller(self.num + 1))
        self.lbl_page = QLabel()
        nav.addWidget(self.b_prec)
        nav.addWidget(self.lbl_page, 1, Qt.AlignCenter)
        nav.addWidget(self.b_suiv)
        gv.addLayout(nav)
        self.vue = VuePage()
        self.vue.zone.connect(self.tableau_trace)
        self.vue.choisi.connect(lambda i: self.liste.setCurrentRow(i))
        gv.addWidget(self.vue, 1)
        sp.addWidget(gauche)
        droite = QWidget()
        dv = QVBoxLayout(droite)
        dv.setContentsMargins(0, 0, 0, 0)
        self.liste = QListWidget()
        self.liste.setObjectName("xl_liste")
        self.liste.setMaximumHeight(170)
        self.liste.currentRowChanged.connect(self.montrer_tableau)
        self.liste.itemChanged.connect(lambda _it: self._maj_vue())
        dv.addWidget(self.liste)
        hh = QHBoxLayout()
        self.cb_entete = QCheckBox(_("Première ligne = titres des colonnes"))
        self.cb_entete.toggled.connect(self._entete_change)
        hh.addWidget(self.cb_entete)
        hh.addStretch(1)
        b = QPushButton(_("Retirer ce tableau"))
        b.clicked.connect(self.retirer)
        hh.addWidget(b)
        dv.addLayout(hh)
        self.grille = QTableWidget()
        self.grille.setObjectName("xl_grille")
        self.grille.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.EditKeyPressed)
        self.grille.itemChanged.connect(self._cellule_modifiee)
        dv.addWidget(self.grille, 1)
        l = QLabel(_("Double-clic sur une cellule pour corriger. Nombres et dates en bleu : Excel pourra les "
                     "additionner et les trier."))
        l.setWordWrap(True)
        l.setStyleSheet("color:#555")
        dv.addWidget(l)
        sp.addWidget(droite)
        sp.setSizes([480, 700])
        bas = QHBoxLayout()
        bas.addWidget(QLabel(_("Dans le fichier Excel :")))
        self.feuilles = QComboBox()
        self.feuilles.setObjectName("xl_feuilles")
        self.feuilles.addItem(_("Une feuille par tableau"), "separees")
        self.feuilles.addItem(_("Tous les tableaux sur une seule feuille"), "une")
        bas.addWidget(self.feuilles)
        self.convertir = QCheckBox(_("Nombres et dates reconnus"))
        self.convertir.setChecked(True)
        self.convertir.toggled.connect(lambda _x: self.montrer_tableau(self.liste.currentRow()))
        bas.addWidget(self.convertir)
        bas.addStretch(1)
        self.lbl_bilan = QLabel()
        bas.addWidget(self.lbl_bilan)
        b = QPushButton(_("Copier"))
        b.setToolTip(_("Copier le tableau affiché, à coller dans Excel"))
        b.clicked.connect(self.copier)
        bas.addWidget(b)
        self.b_exporter = QPushButton(_("Enregistrer en Excel..."))
        self.b_exporter.setProperty("primaire", True)
        self.b_exporter.clicked.connect(self.exporter)
        bas.addWidget(self.b_exporter)
        b = QPushButton(_("Fermer"))
        b.clicked.connect(self.reject)
        bas.addWidget(b)
        v.addLayout(bas)
        self.num = onglet.page_courante() if hasattr(onglet, "page_courante") else 0
        self.tableaux = []
        self.reperer()

    # ------------------------------------------------------------ reperage
    def reperer(self, *_x):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            t = TB.trouver(self.doc, strategie=self.strategie.currentData())
            if self.assembler.isChecked():
                t = TB.assembler(t)
        finally:
            QApplication.restoreOverrideCursor()
        manuels = [x for x in self.tableaux if x.get("manuel")]
        self.tableaux = [dict(x, coche=True, page_fin=x.get("page_fin", x["page"])) for x in t] + manuels
        self._remplir_liste()
        if self.tableaux:
            p = next((i for i, x in enumerate(self.tableaux) if x["page"] <= self.num <= x["page_fin"]), 0)
            self.liste.setCurrentRow(p)
        else:
            self.aller(self.num)

    def _remplir_liste(self):
        self.liste.blockSignals(True)
        self.liste.clear()
        for i, t in enumerate(self.tableaux):
            pages = (_("page {n}", n=t["page"] + 1) if t["page_fin"] == t["page"] else
                     _("pages {a} à {b}", a=t["page"] + 1, b=t["page_fin"] + 1))
            it = QListWidgetItem(_("Tableau {i} — {pages} — {l} lignes × {c} colonnes", i=i + 1, pages=pages,
                                   l=len(t["lignes"]), c=max(len(x) for x in t["lignes"]))
                                 + ("  " + _("(tracé)") if t.get("manuel") else ""))
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if t.get("coche", True) else Qt.Unchecked)
            it.setForeground(QColor(COULEURS[i % len(COULEURS)]))
            self.liste.addItem(it)
        self.liste.blockSignals(False)
        n = len(self.tableaux)
        self.lbl_bilan.setText(_("{n} tableau(x) repéré(s)", n=n) if n else _("Aucun tableau repéré : tracez-en un sur la page."))

    def tableau_trace(self, r):
        page = self.doc[self.num]
        lignes = None
        for s in ("lines", "text"):
            try:
                tf = page.find_tables(clip=r, strategy=s)
            except Exception:
                continue
            if tf.tables:
                t = max(tf.tables, key=lambda t: t.row_count * t.col_count)
                lignes = [l for l in TB.grille(page, t) if any(l)]
                if lignes and len(lignes[0]) >= 2:
                    break
        if not lignes:                                    # aucune colonne : une ligne par ligne de texte
            mots = page.get_text("words", clip=r)
            par_ligne = {}
            for m in mots:
                par_ligne.setdefault((m[5], m[6]), []).append(m[4])
            lignes = [[" ".join(v)] for v in par_ligne.values()]
        if not lignes:
            QMessageBox.information(self, self.windowTitle(), _("Pas de texte dans la zone tracée."))
            return
        self.tableaux.append({"page": self.num, "page_fin": self.num, "rect": r, "lignes": lignes,
                              "entete": TB._a_entete(lignes), "manuel": True, "coche": True})
        self._remplir_liste()
        self.liste.setCurrentRow(len(self.tableaux) - 1)

    def retirer(self):
        i = self.liste.currentRow()
        if 0 <= i < len(self.tableaux):
            del self.tableaux[i]
            self._remplir_liste()
            self.liste.setCurrentRow(min(i, len(self.tableaux) - 1))
            if not self.tableaux:
                self.grille.clear()
                self.grille.setRowCount(0)
                self._maj_vue()

    # ------------------------------------------------------------ affichage
    def aller(self, n):
        self.num = max(0, min(len(self.doc) - 1, n))
        self.lbl_page.setText(_("Page {n} / {t}", n=self.num + 1, t=len(self.doc)))
        self.b_prec.setEnabled(self.num > 0)
        self.b_suiv.setEnabled(self.num < len(self.doc) - 1)
        self._maj_vue()

    def _coches(self):
        return [self.liste.item(i).checkState() == Qt.Checked for i in range(self.liste.count())]

    def _maj_vue(self):
        coches = self._coches()
        for t, c in zip(self.tableaux, coches):
            t["coche"] = c
        cadres = [(i, t["rect"], t["coche"]) for i, t in enumerate(self.tableaux) if t["page"] == self.num]
        self.vue.montrer(self.doc, self.num, cadres, self.liste.currentRow())
        n = sum(coches)
        self.b_exporter.setEnabled(n > 0)

    def montrer_tableau(self, i):
        if not (0 <= i < len(self.tableaux)):
            return
        t = self.tableaux[i]
        if not (t["page"] <= self.num <= t["page_fin"]):
            self.num = t["page"]
        self.aller(self.num)
        self.cb_entete.blockSignals(True)
        self.cb_entete.setChecked(bool(t["entete"]))
        self.cb_entete.blockSignals(False)
        self._remplir_grille(t)

    def _remplir_grille(self, t):
        self.grille.blockSignals(True)
        self.grille.clear()
        lignes = t["lignes"]
        nc = max(len(l) for l in lignes)
        corps = lignes[1:] if t["entete"] else lignes
        self.grille.setColumnCount(nc)
        self.grille.setRowCount(len(corps))
        if t["entete"]:
            self.grille.setHorizontalHeaderLabels([lignes[0][j] if j < len(lignes[0]) else "" for j in range(nc)])
        else:
            self.grille.setHorizontalHeaderLabels([chr(65 + j) if j < 26 else str(j + 1) for j in range(nc)])
        for i, l in enumerate(corps):
            for j in range(nc):
                txt = l[j] if j < len(l) else ""
                it = QTableWidgetItem(txt)
                v = TB.valeur_cellule(txt) if self.convertir.isChecked() else txt
                if isinstance(v, (int, float)) or hasattr(v, "year"):
                    it.setForeground(QColor("#1462c2"))
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    it.setToolTip(_("Lu comme : {v}", v=v.strftime("%d/%m/%Y") if hasattr(v, "year") else
                                    f"{v:n}".replace(".", ",") if isinstance(v, float) else str(v)))
                self.grille.setItem(i, j, it)
        self.grille.resizeColumnsToContents()
        self.grille.blockSignals(False)

    def _entete_change(self, x):
        i = self.liste.currentRow()
        if 0 <= i < len(self.tableaux):
            self.tableaux[i]["entete"] = x
            self._remplir_grille(self.tableaux[i])

    def _cellule_modifiee(self, it):
        i = self.liste.currentRow()
        if not (0 <= i < len(self.tableaux)):
            return
        t = self.tableaux[i]
        r = it.row() + (1 if t["entete"] else 0)
        while len(t["lignes"][r]) <= it.column():
            t["lignes"][r].append("")
        t["lignes"][r][it.column()] = it.text()

    # ------------------------------------------------------------ sortie
    def lignes_tableau(self, t):
        nc = max(len(l) for l in t["lignes"])
        return [list(l) + [""] * (nc - len(l)) for l in t["lignes"]]

    def feuilles_excel(self):
        choisis = [t for t, c in zip(self.tableaux, self._coches()) if c]
        if self.feuilles.currentData() == "une":
            lignes = []
            for k, t in enumerate(choisis):
                if k:
                    lignes.append([])
                lignes.append([_("Tableau {i} (page {p})", i=k + 1, p=t["page"] + 1)])
                lignes += self.lignes_tableau(t)
            return [(_("Tableaux"), lignes)]
        return [(_("Tableau {i} p{p}", i=k + 1, p=t["page"] + 1), self.lignes_tableau(t)) for k, t in enumerate(choisis)]

    def copier(self):
        i = self.liste.currentRow()
        if 0 <= i < len(self.tableaux):
            QApplication.clipboard().setText("\n".join("\t".join(l) for l in self.lignes_tableau(self.tableaux[i])))
            self.lbl_bilan.setText(_("Tableau copié : collez-le dans Excel."))

    def exporter(self):
        base = os.path.splitext(self.o.nom)[0] + ".xlsx"
        dossier = os.path.dirname(self.o.chemin) if getattr(self.o, "chemin", None) else ""
        f, _x = QFileDialog.getSaveFileName(self, _("Enregistrer en Excel"), os.path.join(dossier, base), "Excel (*.xlsx)")
        if not f:
            return
        if not f.lower().endswith(".xlsx"):
            f += ".xlsx"
        try:
            TB.ecrire_xlsx(f, self.feuilles_excel(), convertir=self.convertir.isChecked())
        except PermissionError:
            QMessageBox.warning(self, self.windowTitle(), _("Impossible d'écrire le fichier : est-il ouvert dans Excel ?"))
            return
        self.fichier = f
        r = QMessageBox.question(self, self.windowTitle(), _("Fichier Excel enregistré :\n{f}\n\nL'ouvrir maintenant ?", f=f))
        if r == QMessageBox.Yes:
            from PySide6.QtGui import QDesktopServices
            from PySide6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl.fromLocalFile(f))
        self.accept()
