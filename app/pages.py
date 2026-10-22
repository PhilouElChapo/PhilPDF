"""Onglets Accueil et Outils."""
import os
from PySide6.QtCore import Qt, Signal, QRect, QSize, QPoint
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QScrollArea, QFrame, QLayout, QSizePolicy, QListWidget, QListWidgetItem,
                               QToolButton)
from .icones import icone, logo
from .outils import FAMILLES, OUTILS, famille


class FlowLayout(QLayout):
    """Tuiles qui passent a la ligne selon la largeur."""

    def __init__(self, parent=None, espace=14):
        super().__init__(parent)
        self._items, self._esp = [], espace

    def addItem(self, it):
        self._items.append(it)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientations(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        return self._placer(QRect(0, 0, w, 0), True)

    def setGeometry(self, r):
        super().setGeometry(r)
        self._placer(r, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        s = QSize()
        for it in self._items:
            s = s.expandedTo(it.minimumSize())
        return s

    def _placer(self, r, test):
        x, y, h = r.x(), r.y(), 0
        for it in self._items:
            if it.widget().isHidden():
                continue
            sh = it.sizeHint()
            if x + sh.width() > r.right() and h > 0:
                x, y, h = r.x(), y + h + self._esp, 0
            if not test:
                it.setGeometry(QRect(QPoint(x, y), sh))
            x += sh.width() + self._esp
            h = max(h, sh.height())
        return y + h - r.y()


class Tuile(QFrame):
    clique = Signal(str)
    epingle = Signal(str, bool)

    def __init__(self, o, epinglee):
        super().__init__()
        oid, fam, ic, titre, sous, aide, dispo = o
        _, _, coul, fond = famille(fam)
        self.oid, self.titre, self.texte = oid, titre, (titre + " " + sous + " " + aide).lower()
        self.setObjectName("tuile")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(236, 148)
        self.setToolTip(f"<b>{titre}</b><br>{aide}" + ("" if dispo else "<br><i>Prévu dans une prochaine version.</i>"))
        self.setStyleSheet(f"#tuile{{background:#fff;border:1px solid #e2e2e2;border-radius:12px}}"
                           f"#tuile:hover{{border:2px solid {coul}}}"
                           "QLabel{background:transparent} QToolButton{background:transparent;border:none}")
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 14, 12, 12)
        v.setSpacing(8)
        h = QHBoxLayout()
        ico = QLabel()
        ico.setFixedSize(44, 44)
        ico.setAlignment(Qt.AlignCenter)
        ico.setStyleSheet(f"background:{fond};border-radius:10px")
        ico.setPixmap(icone(ic, coul, 48).pixmap(26, 26))
        h.addWidget(ico)
        h.addStretch()
        if not dispo:
            b = QLabel("Bientôt")
            b.setStyleSheet("color:#666;background:#f1f1f1;border-radius:8px;padding:2px 8px;font-size:11px")
            h.addWidget(b, 0, Qt.AlignTop)
        self.etoile = QToolButton()
        self.etoile.setAutoRaise(True)
        self.etoile.setCheckable(True)
        self.etoile.setChecked(epinglee)
        self.etoile.setToolTip("Epingler dans le volet de droite des fichiers ouverts")
        self.etoile.setAccessibleName("Epingler " + titre)
        self._maj_etoile()
        self.etoile.toggled.connect(lambda c: (self._maj_etoile(), self.epingle.emit(self.oid, c)))
        h.addWidget(self.etoile, 0, Qt.AlignTop)
        v.addLayout(h)
        t = QLabel(titre)
        t.setStyleSheet("font-size:15px;font-weight:600;color:#1f1f1f")
        v.addWidget(t)
        s = QLabel(sous)
        s.setWordWrap(True)
        s.setStyleSheet("font-size:13px;color:#555")
        v.addWidget(s)
        v.addStretch()

    def _maj_etoile(self):
        c = self.etoile.isChecked()
        self.etoile.setIcon(icone("etoile", "#e8a317" if c else "#b5b5b5", 36, rempli=c))

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clique.emit(self.oid)


class PageOutils(QScrollArea):
    outil_choisi = Signal(str)
    epingles_changes = Signal(list)

    def __init__(self, params):
        super().__init__()
        self.params = params
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        w = QWidget()
        w.setObjectName("fond_outils")
        w.setStyleSheet("#fond_outils{background:#f3f3f3} QLabel{background:transparent}")
        self.setWidget(w)
        v = QVBoxLayout(w)
        v.setContentsMargins(32, 24, 32, 40)
        v.setSpacing(26)
        q = QLabel("Que voulez-vous faire ?")
        q.setStyleSheet("font-size:26px;font-weight:600")
        v.addWidget(q)
        self.recherche = QLineEdit()
        self.recherche.setPlaceholderText("Rechercher un outil : signer, alléger, OCR...")
        self.recherche.setClearButtonEnabled(True)
        self.recherche.setMaximumWidth(620)
        self.recherche.setStyleSheet("QLineEdit{background:#fff;border:1px solid #cfcfcf;border-radius:10px;padding:10px 12px;font-size:15px}")
        self.recherche.textChanged.connect(self._filtrer)
        v.addWidget(self.recherche)
        filtres = QHBoxLayout()
        filtres.setSpacing(8)
        self.boutons_fam = {}
        tout = QPushButton("Tous")
        tout.setCheckable(True)
        tout.setChecked(True)
        tout.clicked.connect(lambda: self._choisir_famille(None))
        self.bouton_tous = tout
        filtres.addWidget(tout)
        for fid, nom, coul, fond in FAMILLES:
            b = QPushButton("● " + nom)
            b.setCheckable(True)
            b.setProperty("coul", coul)
            b.clicked.connect(lambda _=False, f=fid: self._choisir_famille(f))
            self.boutons_fam[fid] = b
            filtres.addWidget(b)
        filtres.addStretch()
        v.addLayout(filtres)
        self._style_filtres(None)
        self.sections, self.tuiles = {}, []
        for fid, nom, coul, fond in FAMILLES:
            sec = QWidget()
            sv = QVBoxLayout(sec)
            sv.setContentsMargins(0, 0, 0, 0)
            sv.setSpacing(12)
            titre = QLabel(f'<span style="color:{coul}">●</span>&nbsp; {nom}'
                           + (' <span style="font-size:13px;font-weight:400;color:#555">· optionnel, à la demande, avec votre clef API</span>' if fid == "ia" else ""))
            titre.setStyleSheet("font-size:18px;font-weight:600")
            sv.addWidget(titre)
            grille = QWidget()
            fl = FlowLayout(grille)
            for o in OUTILS:
                if o[1] == fid:
                    t = Tuile(o, o[0] in params["outils_epingles"])
                    t.clique.connect(self.outil_choisi)
                    t.epingle.connect(self._epingler)
                    fl.addWidget(t)
                    self.tuiles.append((t, fid))
            sv.addWidget(grille)
            self.sections[fid] = sec
            v.addWidget(sec)
        aide = QLabel("L'étoile épingle un outil dans le volet de droite des fichiers ouverts. Survolez un outil pour sa bulle d'aide.")
        aide.setStyleSheet("color:#555;font-size:13px")
        v.addWidget(aide)
        v.addStretch()
        self.famille_active = None

    def _style_filtres(self, actif):
        self.bouton_tous.setStyleSheet(
            "QPushButton{border-radius:14px;padding:6px 12px;" +
            ("background:#1f1f1f;color:#fff;border:none}" if actif is None else "background:#fff;border:1px solid #d6d6d6}"))
        for fid, b in self.boutons_fam.items():
            c = b.property("coul")
            on = fid == actif
            b.setChecked(on)
            b.setStyleSheet(f"QPushButton{{border-radius:14px;padding:6px 12px;color:{'#fff' if on else c};"
                            f"background:{c if on else '#fff'};border:1px solid {c if on else '#d6d6d6'}}}")
        self.bouton_tous.setChecked(actif is None)

    def _choisir_famille(self, fid):
        self.famille_active = fid
        self._style_filtres(fid)
        self._filtrer()

    def _filtrer(self):
        t = self.recherche.text().strip().lower()
        visibles = set()
        for tu, fid in self.tuiles:
            ok = (self.famille_active in (None, fid)) and (not t or all(m in tu.texte for m in t.split()))
            tu.setVisible(ok)
            if ok:
                visibles.add(fid)
        for fid, sec in self.sections.items():
            sec.setVisible(fid in visibles)
            sec.updateGeometry()

    def _epingler(self, oid, on):
        e = [x for x in self.params["outils_epingles"] if x != oid]
        if on:
            e.append(oid)
        self.params["outils_epingles"] = e
        self.params.enregistrer()
        self.epingles_changes.emit(e)


class PageAccueil(QWidget):
    ouvrir = Signal(str)
    ouvrir_dialogue = Signal()
    reprendre = Signal(str)

    def __init__(self, params):
        super().__init__()
        self.params = params
        self.setObjectName("accueil")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("#accueil{background:#f3f3f3} QLabel{background:transparent}")
        v = QVBoxLayout(self)
        v.setContentsMargins(32, 24, 32, 24)
        v.setSpacing(16)
        h = QHBoxLayout()
        lg = QLabel()
        lg.setPixmap(logo(96).pixmap(56, 56))
        h.addWidget(lg)
        t = QLabel('<span style="font-size:26px;font-weight:700">Phil<span style="color:#c9252d">PDF</span></span>'
                   '<br><span style="color:#555">Editeur PDF · éditez, signez, allégez en toute liberté</span>')
        h.addWidget(t)
        h.addStretch()
        b = QPushButton("  Ouvrir un fichier...")
        b.setIcon(icone("ouvrir", "#ffffff"))
        b.setStyleSheet("QPushButton{background:#c9252d;color:#fff;border:none;border-radius:8px;padding:10px 18px;font-weight:600}"
                        "QPushButton:hover{background:#a81e25}")
        b.clicked.connect(self.ouvrir_dialogue)
        h.addWidget(b)
        v.addLayout(h)
        self.bandeau = QLabel()
        self.bandeau.setStyleSheet("background:#fff;border:1px solid #e2e2e2;border-radius:10px;padding:12px 14px")
        self.bandeau.setTextInteractionFlags(Qt.LinksAccessibleByMouse)
        self.bandeau.linkActivated.connect(self.reprendre)
        v.addWidget(self.bandeau)
        r = QLabel("Récents")
        r.setStyleSheet("font-size:18px;font-weight:600")
        v.addWidget(r)
        self.liste = QListWidget()
        self.liste.setStyleSheet("QListWidget{background:#fff;border:1px solid #e2e2e2;border-radius:10px;font-size:14px}"
                                 "QListWidget::item{padding:10px;border-bottom:1px solid #f0f0f0}"
                                 "QListWidget::item:hover{background:#f4f7fb}")
        self.liste.itemActivated.connect(lambda it: self.ouvrir.emit(it.data(Qt.UserRole)))
        self.liste.itemClicked.connect(lambda it: self.ouvrir.emit(it.data(Qt.UserRole)))
        v.addWidget(self.liste, 1)
        self.rafraichir()

    def rafraichir(self):
        self.liste.clear()
        for p in self.params["recents"]:
            existe = os.path.exists(p)
            it = QListWidgetItem(icone("creer", "#c9252d" if existe else "#bbbbbb"),
                                 f"{os.path.basename(p)}\n{os.path.dirname(p)}" + ("" if existe else "   (introuvable sur ce PC)"))
            it.setData(Qt.UserRole, p)
            if not existe:
                it.setForeground(Qt.gray)
            self.liste.addItem(it)
        sess = self.params.lire_session()
        autres = {m: f for m, f in sess.items() if m != self.params["machine"] and f}
        if autres:
            liens = " · ".join(f'<a href="{m}">Reprendre la session de {m} ({len(f)} fichiers)</a>' for m, f in autres.items())
            self.bandeau.setText(liens)
            self.bandeau.show()
        else:
            self.bandeau.setText(f"Machine : <b>{self.params['machine']}</b>. Indiquez un dossier synchronisé dans "
                                 "Paramètres pour retrouver vos fichiers ouverts sur vos autres PC.")
