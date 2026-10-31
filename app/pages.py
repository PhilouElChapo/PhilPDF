"""Onglets Accueil et Outils."""
import os
from PySide6.QtCore import Qt, Signal, QRect, QSize, QPoint
from PySide6.QtWidgets import (QMessageBox, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QScrollArea, QFrame, QLayout, QSizePolicy, QListWidget, QListWidgetItem,
                               QToolButton)
from .icones import icone, logo
from .outils import FAMILLES, OUTILS, famille
from .langue import _


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
        _x, _x, coul, fond = famille(fam)
        self.oid, self.titre, self.texte = oid, titre, (titre + " " + sous + " " + aide).lower()
        self.setObjectName("tuile")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(236, 160)
        self.setToolTip(_('<b>{titre}</b><br>{aide}', titre=titre, aide=aide) + ("" if dispo else _('<br><i>Prévu dans une prochaine version.</i>')))
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
            b = QLabel(_('Bientôt'))
            b.setStyleSheet("color:#666;background:#f1f1f1;border-radius:8px;padding:2px 8px;font-size:11px")
            h.addWidget(b, 0, Qt.AlignTop)
        self.etoile = QToolButton()
        self.etoile.setAutoRaise(True)
        self.etoile.setCheckable(True)
        self.etoile.setChecked(epinglee)
        self.etoile.setToolTip(_('Epingler dans le volet de droite des fichiers ouverts'))
        self.etoile.setAccessibleName(_("Epingler {outil}", outil=titre))
        self._maj_etoile()
        self.etoile.toggled.connect(lambda c: (self._maj_etoile(), self.epingle.emit(self.oid, c)))
        h.addWidget(self.etoile, 0, Qt.AlignTop)
        v.addLayout(h)
        t = QLabel(titre)
        t.setWordWrap(True)                          # titre long : sur deux lignes plutot que coupe
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

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._depart = e.position().toPoint()
            self._glisse = False

    def mouseMoveEvent(self, e):
        """Glisser une tuile la deplace parmi celles de sa famille (ordre garde et synchronise)."""
        d = getattr(self, "_depart", None)
        if d is None or not (e.buttons() & Qt.LeftButton):
            return
        if (e.position().toPoint() - d).manhattanLength() < 12:
            return
        from PySide6.QtGui import QDrag
        from PySide6.QtCore import QMimeData
        self._glisse = True
        self._depart = None
        m = QMimeData()
        m.setData("application/x-philpdf-tuile", self.oid.encode())
        dr = QDrag(self)
        dr.setMimeData(m)
        pm = self.grab()
        dr.setPixmap(pm.scaledToWidth(180, Qt.SmoothTransformation))
        dr.setHotSpot(d * 180 / max(1, pm.width()))
        dr.exec(Qt.MoveAction)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and not getattr(self, "_glisse", False):
            self.clique.emit(self.oid)
        self._glisse = False


class GrilleTuiles(QWidget):
    """Grille d'une famille : on y depose une tuile glissee pour changer l'ordre."""
    deplace = Signal(str, int)

    def __init__(self, fid):
        super().__init__()
        self.fid = fid
        self.setAcceptDrops(True)

    def _ok(self, e):
        return e.mimeData().hasFormat("application/x-philpdf-tuile")

    def dragEnterEvent(self, e):
        if self._ok(e):
            e.acceptProposedAction()

    def dragMoveEvent(self, e):
        if self._ok(e):
            e.acceptProposedAction()

    def dropEvent(self, e):
        if not self._ok(e):
            return
        oid = bytes(e.mimeData().data("application/x-philpdf-tuile")).decode()
        pos = e.position().toPoint()
        fl = self.layout()
        rang = fl.count()
        for i in range(fl.count()):
            w = fl.itemAt(i).widget()
            g = w.geometry()
            if pos.y() < g.top() or (pos.y() <= g.bottom() and pos.x() < g.center().x()):
                rang = i
                break
        e.acceptProposedAction()
        self.deplace.emit(oid, rang)


def ordre_outils(params, outils):
    """Les outils dans l'ordre choisi a la souris (les nouveaux a leur place d'origine, a la fin de leur famille)."""
    ordre = list(params.get("ordre_outils") or [])
    rang = {o: i for i, o in enumerate(ordre)}
    return sorted(outils, key=lambda o: (rang.get(o[0], 10000 + outils.index(o))))


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
        q = QLabel(_('Que voulez-vous faire ?'))
        q.setStyleSheet("font-size:26px;font-weight:600")
        v.addWidget(q)
        self.recherche = QLineEdit()
        self.recherche.setPlaceholderText(_('Rechercher un outil : signer, alléger, OCR...'))
        self.recherche.setClearButtonEnabled(True)
        self.recherche.setMaximumWidth(620)
        self.recherche.setStyleSheet("QLineEdit{background:#fff;border:1px solid #cfcfcf;border-radius:10px;padding:10px 12px;font-size:15px}")
        self.recherche.textChanged.connect(self._filtrer)
        v.addWidget(self.recherche)
        zone_filtres = QWidget()
        filtres = FlowLayout(zone_filtres, espace=8)     # passe a la ligne si la fenetre est etroite (langues longues)
        self.boutons_fam = {}
        tout = QPushButton(_('Tous'))
        tout.setCheckable(True)
        tout.setChecked(True)
        tout.clicked.connect(lambda: self._choisir_famille(None))
        self.bouton_tous = tout
        filtres.addWidget(tout)
        for fid, nom, coul, fond in FAMILLES:
            b = QPushButton("● " + nom)
            b.setCheckable(True)
            b.setProperty("coul", coul)
            b.clicked.connect(lambda _x=False, f=fid: self._choisir_famille(f))
            self.boutons_fam[fid] = b
            filtres.addWidget(b)
        v.addWidget(zone_filtres)
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
            grille = GrilleTuiles(fid)
            grille.deplace.connect(self._deplacer)
            fl = FlowLayout(grille)
            for o in ordre_outils(params, OUTILS):
                if o[1] == fid:
                    t = Tuile(o, o[0] in params["outils_epingles"])
                    t.clique.connect(self.outil_choisi)
                    t.epingle.connect(self._epingler)
                    fl.addWidget(t)
                    self.tuiles.append((t, fid))
            sv.addWidget(grille)
            self.sections[fid] = sec
            v.addWidget(sec)
        aide = QLabel(_("L'étoile épingle un outil dans le volet de droite des fichiers ouverts. Glissez une tuile pour "
                        "changer l'ordre (gardé sur vos autres postes). Survolez un outil pour sa bulle d'aide."))
        aide.setWordWrap(True)
        aide.setStyleSheet("color:#555;font-size:13px")
        v.addWidget(aide)
        v.addStretch()
        self.famille_active = None

    def _deplacer(self, oid, rang):
        grille = self.sender()
        fl = grille.layout()
        items = [fl.itemAt(i).widget() for i in range(fl.count())]
        t = next((w for w in items if w.oid == oid), None)
        if t is None:                                # tuile d'une autre famille : elle reste dans la sienne
            return
        avant = items.index(t)
        items.remove(t)
        items.insert(rang - (1 if rang > avant else 0), t)
        while fl.count():
            fl.takeAt(0)
        for w in items:
            fl.addWidget(w)
        fl.invalidate()
        grille.updateGeometry()
        ordre = [o[0] for o in ordre_outils(self.params, OUTILS)]
        fam = [w.oid for w in items]
        pos = sorted(ordre.index(x) for x in fam)        # memes places, nouvel ordre dans la famille
        for p_, x in zip(pos, fam):
            ordre[p_] = x
        self.params["ordre_outils"] = ordre
        self.params.enregistrer()

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

    def maj_etoiles(self):
        for t, _x in self.tuiles:
            t.etoile.blockSignals(True)
            t.etoile.setChecked(t.oid in self.params["outils_epingles"])
            t._maj_etoile()
            t.etoile.blockSignals(False)

    def _epingler(self, oid, on):
        e = [x for x in self.params["outils_epingles"] if x != oid]
        if on:
            e.append(oid)
        self.params["outils_epingles"] = e
        self.params.enregistrer()
        self.epingles_changes.emit(e)


_TACHES_ACCUEIL = set()


class PageAccueil(QWidget):
    SYNCHRONE = False
    ouvrir = Signal(str)
    ouvrir_dialogue = Signal()
    ouvrir_distant = Signal()
    action_fichier = Signal(str, str)     # chemin, action (menu clic droit des fichiers recents)
    reprendre = Signal()          # reprendre la session proposee (remplace les fichiers ouverts)
    synchroniser = Signal()       # fenetre de synchronisation manuelle
    synchro_drive = Signal()
    chercher_recent = Signal(str, object)   # poste, fichier de ce poste introuvable ici      # synchroniser maintenant (fenetre a cocher)
    session_vue = Signal()        # Reprendre ou Ignorer : on ne remontre le bandeau qu'apres un changement sur l'autre poste
    doublon_choisi = Signal(str, object, str)   # machine, fichier de l'autre poste, chemin choisi ici
    rechercher = Signal()         # rechercher dans tous mes PDF
    changer_synchro = Signal()    # changer l'emplacement de synchronisation

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
        self._marque = t
        h.addWidget(t)
        h.addStretch()
        b = QPushButton(_('  Ouvrir un fichier...'))
        b.setIcon(icone("ouvrir", "#ffffff"))
        b.setStyleSheet("QPushButton{background:#c9252d;color:#fff;border:none;border-radius:8px;padding:10px 18px;font-weight:600}"
                        "QPushButton:hover{background:#a81e25}")
        b.clicked.connect(self.ouvrir_dialogue)
        bd = QPushButton(_("  NAS, FTP, Drive..."))
        bd.setIcon(icone("archiver", "#0f6cbd"))
        bd.setToolTip(_("Ouvrir depuis un emplacement (NAS, FTP, Drive)..."))
        bd.setStyleSheet("QPushButton{padding:10px 16px;border-radius:8px;font-weight:600}")
        bd.clicked.connect(self.ouvrir_distant)
        br = QPushButton(_("  Rechercher dans mes PDF"))
        br.setIcon(icone("rechercher", "#0b5e63"))
        br.setStyleSheet("QPushButton{padding:10px 16px;border-radius:8px;font-weight:600}")
        br.clicked.connect(lambda: self.rechercher.emit())
        bw = QWidget()
        hb_ = QHBoxLayout(bw)
        hb_.setContentsMargins(0, 0, 0, 0)
        hb_.addStretch()
        hb_.addWidget(br)
        hb_.addWidget(bd)
        hb_.addWidget(b)
        from PySide6.QtWidgets import QSizePolicy as _SP
        bw.setSizePolicy(_SP.Ignored, _SP.Preferred)   # la fenetre peut retrecir : les boutons s'adaptent
        bw.setMinimumWidth(200)
        self._marque.setSizePolicy(_SP.Preferred, _SP.Preferred)
        self._marque.setMinimumWidth(110)
        h.addWidget(bw, 1)
        # fenetre etroite : d'abord sans le sous-titre, puis boutons en icones seules (nom en bulle) : rien de tronque
        self._boutons_tete = [(x, x.text()) for x in (br, bd, b)]
        for x, txt in self._boutons_tete:
            x.setToolTip(x.toolTip() or txt.strip())
        self._tete_mode = None
        v.addLayout(h)
        # --- carte "session plus recente sur un autre poste" (reste la tant qu'elle n'est pas traitee)
        self.carte = QFrame()
        self.carte.setObjectName("carte")
        self.carte.setStyleSheet("#carte{background:#fff;border:1px solid #e2e2e2;border-left:4px solid #2b6cb0;border-radius:10px}")
        vc = QVBoxLayout(self.carte)
        vc.setContentsMargins(14, 10, 14, 10)
        self.carte_titre = QLabel()
        self.carte_titre.setWordWrap(True)
        vc.addWidget(self.carte_titre)
        self.carte_liste = QListWidget()
        self.carte_liste.setStyleSheet("QListWidget{border:none;font-size:13px}")
        self.carte_liste.setMaximumHeight(130)
        vc.addWidget(self.carte_liste)
        hb = QHBoxLayout()
        self.b_reprendre = QPushButton(_('Reprendre ces fichiers'))
        self.b_reprendre.setToolTip(_("Ferme les fichiers ouverts ici et ouvre ceux de l'autre poste, à la même page"))
        self.b_reprendre.setStyleSheet("QPushButton{background:#2b6cb0;color:#fff;border:none;border-radius:6px;padding:7px 14px;font-weight:600}")
        self.b_reprendre.clicked.connect(self.reprendre)
        hb.addWidget(self.b_reprendre)
        b2 = QPushButton(_(' Synchroniser...'))
        b2.setIcon(icone("synchro", "#2b6cb0"))
        b2.clicked.connect(self.synchroniser)
        hb.addWidget(b2)
        hb.addStretch()
        b3 = QPushButton(_('Ignorer'))
        b3.setFlat(True)
        b3.clicked.connect(lambda: (self.session_vue.emit(), self.cacher_synchro()))
        self.carte_liste.itemDoubleClicked.connect(lambda it: self.choisir_doublon(it.data(Qt.UserRole)))
        hb.addWidget(b3)
        vc.addLayout(hb)
        self.carte.hide()
        v.addWidget(self.carte)
        self.echeances = QLabel()
        self.echeances.setWordWrap(True)
        self.echeances.setTextFormat(Qt.RichText)
        self.echeances.setStyleSheet("QLabel{background:#fff8e6;border:1px solid #f0d58c;border-left:4px solid #d69e00;"
                                     "border-radius:10px;padding:8px 12px}")
        self.echeances.hide()
        self.echeances.linkActivated.connect(self._echeance_lien)
        v.addWidget(self.echeances)
        hl = QHBoxLayout()
        self.bandeau = QLabel()
        self.bandeau.setWordWrap(True)
        self.bandeau.setStyleSheet("color:#555")
        self.bandeau.setTextFormat(Qt.RichText)
        self.bandeau.linkActivated.connect(lambda l: self.revoir_autre() if l == "autre" else self.changer_synchro.emit())
        hl.addWidget(self.bandeau, 1)
        bs = QPushButton()
        bs.setIcon(icone("synchro", "#2b6cb0"))
        bs.setToolTip(_('Synchroniser maintenant avec vos autres postes (réglages, tampons, fichiers ouverts) : '
                        'vous voyez d\'abord ce qui va être fait'))
        bs.setFlat(True)
        bs.clicked.connect(lambda: self.synchro_drive.emit() if self.params.get("drive_compte") else self.synchroniser.emit())
        hl.addWidget(bs)
        v.addLayout(hl)
        r = QLabel(_('Récents'))
        r.setStyleSheet("font-size:18px;font-weight:600")
        v.addWidget(r)
        self.liste = QListWidget()
        self.liste.setIconSize(QSize(40, 52))
        self.liste.setStyleSheet("QListWidget{background:#fff;border:1px solid #e2e2e2;border-radius:10px;font-size:14px}"
                                 "QListWidget::item{padding:10px;border-bottom:1px solid #f0f0f0}"
                                 "QListWidget::item:hover{background:#f4f7fb}")
        self.liste.setItemDelegate(DelegueRecent(self.liste))
        self.liste.setResizeMode(QListWidget.Adjust)        # largeur changee : hauteur des lignes recalculee
        self.liste.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.liste.setWordWrap(True)
        self.liste.setContextMenuPolicy(Qt.CustomContextMenu)
        self.liste.customContextMenuRequested.connect(self._menu_fichier)
        self.liste.itemClicked.connect(self._clic_recent)
        self.liste.setMouseTracking(True)
        self.liste.viewport().setMouseTracking(True)
        self.liste.viewport().installEventFilter(self)
        self.liste.currentItemChanged.connect(lambda it, _p: self._survol(it))
        corps = QHBoxLayout()
        corps.setSpacing(16)
        corps.addWidget(self.liste, 1)
        self.fiche = FicheFichier()
        corps.addWidget(self.fiche)
        v.addLayout(corps, 1)
        from PySide6.QtCore import QTimer
        self._t_fiche = QTimer(self)
        self._t_fiche.setSingleShot(True)
        self._t_fiche.timeout.connect(lambda: self.fiche.montrer(getattr(self, "_l_fiche", None)))
        QTimer.singleShot(50, self.rafraichir)       # apres l'affichage : un NAS lent ne retarde plus l'ouverture

    def eventFilter(self, obj, ev):
        """Apercu seulement quand la souris est sur l'icone, le nom ou le chemin : pas dans le blanc de la ligne."""
        from PySide6.QtCore import QEvent
        try:
            vp = self.liste.viewport()
        except RuntimeError:                       # liste deja detruite (fermeture)
            return False
        if obj is vp:
            if ev.type() == QEvent.MouseMove:
                pos = ev.position().toPoint()
                it = self.liste.itemAt(pos)
                if it is None or not it.data(Qt.UserRole + 1):
                    self._survol(None)
                else:
                    r = self.liste.visualItemRect(it)
                    fm = self.liste.fontMetrics()
                    largeur = max((fm.horizontalAdvance(l) for l in it.text().split("\n")), default=0)
                    fin = r.left() + self.liste.iconSize().width() + 24 + largeur + 16
                    self._survol(it if pos.x() <= fin else None)
            elif ev.type() == QEvent.Leave:
                self._survol(None)
        return super().eventFilter(obj, ev)

    def _survol(self, it):
        """Le fichier survole (ou choisi au clavier) s'affiche dans la fiche de droite, apres un court instant."""
        l = it.data(Qt.UserRole + 1) if it is not None else None
        if l is getattr(self, "_l_fiche", None):
            return
        self._l_fiche = l
        self._t_fiche.start(140)

    def lignes_recents(self):
        """Recents de ce poste et des autres (session partagee), 30 jours, 30 fichiers, une seule liste."""
        try:
            from .session import session_de
            return session_de(self.params).recents_communs()
        except Exception:
            return [{"chemin": p if os.path.exists(p) else None, "chemin_origine": p, "nom": os.path.basename(p),
                     "dossier": os.path.dirname(p), "date": "", "poste": self.params.get("machine", ""), "ouvert_sur": [],
                     "machine": self.params.get("machine", ""), "e": None, "introuvable_ici": not os.path.exists(p)}
                    for p in self.params["recents"][:30]]

    def rafraichir(self, lignes=None):
        """Affichage en deux temps, pour que l'Accueil soit immediat :
        1. tout de suite : les recents de CE poste (rien n'est lu sur le reseau) et ce qu'on savait des autres
           postes au lancement precedent ; miniatures deja faites seulement ;
        2. en arriere-plan : les autres postes revus (« aussi sur Pharma »), puis les miniatures qui manquent,
           une par une, en commencant par le haut de la liste. La liste n'est redessinee que si elle a change."""
        if lignes is None and self.SYNCHRONE:          # tests : tout de suite
            lignes = self.lignes_recents()
        if lignes is None:
            import time
            t0 = time.monotonic()
            self._gen_recents = gen = getattr(self, "_gen_recents", 0) + 1
            lignes = self._recents_immediats()
            self._t_local = time.monotonic() - t0
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, lambda: self._lancer_complet(gen, t0))
        self._afficher_recents(lignes)

    # ---- recents : affichage immediat, puis complet en arriere-plan
    def _cache_accueil(self):
        from .config import dossier_donnees
        return os.path.join(dossier_donnees(), "accueil_recents.json")

    def _recents_immediats(self):
        """Recents de ce poste (instantane) completes par la derniere liste complete connue."""
        try:
            from .session import session_de, _norm
            ici = session_de(self.params).recents_communs(rapide=True)
        except Exception:                            # noqa: BLE001
            return self.lignes_recents()
        if not hasattr(self, "_derniere_complete"):
            try:
                import json
                with open(self._cache_accueil(), encoding="utf-8") as f:
                    self._derniere_complete = json.load(f)
            except (OSError, ValueError):
                self._derniere_complete = []
        avant = {_norm(l.get("chemin_origine") or l.get("chemin") or ""): l
                 for l in self._derniere_complete if not l.get("autre_poste")}
        for l in ici:                                # « aussi sur Pharma » deja connu : affiche tout de suite
            x = avant.get(_norm(l["chemin_origine"]))
            if x:
                l["aussi_sur"] = list(x.get("aussi_sur") or [])
                l["chemins_autres"] = dict(x.get("chemins_autres") or {})
        autres = []
        for x in self._derniere_complete:
            if x.get("autre_poste"):
                x = dict(x)
                c = x.get("chemin")
                if c and not c.replace("/", "\\").startswith("\\\\") and not os.path.exists(c):
                    x["chemin"], x["section"], x["introuvable_ici"] = None, "introuvable", True
                autres.append(x)
        rang = {"ici": 0, "autres": 1, "introuvable": 2}
        return sorted(ici + autres, key=lambda l: rang.get(l.get("section") or "ici", 0))

    @staticmethod
    def _signature(lignes):
        return [(l.get("chemin"), l.get("chemin_origine"), l.get("section"), tuple(l.get("aussi_sur") or ()),
                 tuple(l.get("ouvert_sur") or ()), l.get("poste"), l.get("date")) for l in lignes]

    def _lancer_complet(self, gen, t0):
        if self._gen_recents != gen:
            return
        from PySide6.QtCore import QThread, Signal as _S

        class _T(QThread):
            pret = _S(object)

            def __init__(s_, f):
                super().__init__()
                s_.f = f

            def run(s_):
                try:
                    s_.pret.emit(s_.f())
                except Exception:                    # noqa: BLE001
                    s_.pret.emit(None)
        t = _T(self.lignes_recents)
        _TACHES_ACCUEIL.add(t)
        t.pret.connect(lambda l, g=gen, t0=t0: self._recents_complets(l, g, t0))
        t.finished.connect(lambda t=t: _TACHES_ACCUEIL.discard(t))
        t.start()

    def _recents_complets(self, lignes, gen, t0):
        import time, json
        if lignes is None or self._gen_recents != gen:
            return
        self._t_complet = time.monotonic() - t0
        propres = [{k: v for k, v in l.items() if k != "e" or isinstance(v, (dict, type(None)))} for l in lignes]
        self._derniere_complete = propres
        try:
            with open(self._cache_accueil(), "w", encoding="utf-8") as f:
                json.dump(propres, f, ensure_ascii=False, default=str)
        except OSError:
            pass
        change = self._signature(lignes) != getattr(self, "_sig_affichee", None)
        if change:
            self._afficher_recents(lignes)
        if not getattr(self, "_mesure_faite", False):     # une ligne dans le journal, au premier affichage
            self._mesure_faite = True
            _ecrire_journal(f"accueil : {sum(1 for l in lignes if not l.get('autre_poste'))} récents de ce poste affichés en "
                            f"{_duree(self._t_local)}, autres postes revus en {_duree(self._t_complet)}"
                            + (" (liste mise à jour)" if change else " (rien n'avait changé)"))

    def _afficher_recents(self, lignes):
        self._sig_affichee = self._signature(lignes)
        from .session import date_fr
        self.liste.clear()
        moi = self.params.get("machine", "")
        section = "ici"
        titres = {"autres": _("Sur vos autres postes"), "introuvable": _("Introuvables sur ce poste")}
        self._a_vignetter = []
        for l in lignes:
            ici = l["chemin"]
            sec = l.get("section") or ("introuvable" if not ici else "autres" if l.get("autre_poste") else "ici")
            if sec != section and sec in titres:          # separation : ce poste, les autres postes, les introuvables
                section = sec
                t = QListWidgetItem(titres[sec])
                t.setFlags(Qt.NoItemFlags)
                f = t.font()
                f.setBold(True)
                t.setFont(f)
                t.setForeground(__import__("PySide6.QtGui", fromlist=["QColor"]).QColor("#555555"))
                t.setData(Qt.UserRole, "")
                self.liste.addItem(t)
            infos = []
            if l.get("autre_poste"):
                infos.append(l["poste"] + (", " + date_fr(l["date"]) if l["date"] else ""))
            if l.get("aussi_sur"):
                infos.append(_("aussi sur {poste}", poste=", ".join(l["aussi_sur"])))
            aussi = infos[-1] if l.get("aussi_sur") else None
            if l["ouvert_sur"]:
                infos.append("● " + _("ouvert sur {poste}", poste=", ".join(l["ouvert_sur"])))
            if l.get("autre_poste") and ici:
                infos.append(_("retrouvé sur ce poste"))
            if not ici:
                infos.append(_("introuvable sur ce poste"))
            it = QListWidgetItem(icone("creer", "#c9252d" if ici else "#bbbbbb"),
                                 f"{l['nom']}\n{l['dossier']}" + ("   ·   " + "   ·   ".join(infos) if infos else ""))
            import html as _h                         # meme texte, « aussi sur ... » seul en gras
            it.setData(Qt.UserRole + 2, _h.escape(l["nom"]) + "<br>" + _h.escape(l["dossier"]) + "".join(
                "&nbsp;&nbsp;&nbsp;·&nbsp;&nbsp;&nbsp;" + (f"<b>{_h.escape(x)}</b>" if x == aussi else _h.escape(x))
                for x in infos))
            it.setData(Qt.UserRole, ici or "")
            it.setData(Qt.UserRole + 1, l)
            # plus de bulle : la fiche de droite montre l'apercu, le detail et le debut du texte
            if not ici:
                it.setForeground(Qt.gray)
            else:
                self._a_vignetter.append(it)
            self.liste.addItem(it)
        self._vignetter()
        self.bandeau.setText(_('Poste : <b>{machine}</b>. ', machine=self.params['machine']) + (
                _('Synchronisation : ') + self._lieu_synchro() + self._etat_synchro() + " &nbsp;<a href='changer_synchro'>" + _("changer") + "</a>"
                + self._rappel_autre()
                if (self.params.get("drive") or self.params.get("drive_compte")) else
            _('Choisissez un emplacement de synchronisation (bouton à droite) pour retrouver vos fichiers ouverts, préférences et tampons sur vos autres PC.')))
        try:
            from .apprentissage import echeances_a_venir
            import datetime
            ech = echeances_a_venir(self.params, 45)
        except Exception:
            ech = []
        if ech:
            import html
            from urllib.parse import quote
            lignes = [f"<b>{datetime.date.fromisoformat(e['date']).strftime('%d/%m/%Y')}</b> — {html.escape(e.get('libelle', ''))}"
                      f" <span style='color:#777'>({html.escape(os.path.basename(e.get('fichier', '')))})</span>"
                      f" &nbsp;<a href='fait:{quote(e['cle'])}'>{_('✓ fait')}</a>"
                      f" &nbsp;<a href='retirer:{quote(e['cle'])}' style='color:#a33'>{_('✕ retirer')}</a>" for e in ech[:6]]
            self.echeances.setText(_("<b>Echéances à venir</b>") + f" &nbsp; <a href='retirer:*' style='color:#a33'>{_('tout retirer')}</a>"
                                   + "<br>" + "<br>".join(lignes))
            self.echeances.show()
        else:
            self.echeances.hide()

    def _vignetter(self):
        """Miniature de la premiere page a la place de l'icone (comme Acrobat). Celles deja faites tout de suite ;
        les autres sont fabriquees en arriere-plan, une par une, du haut de la liste vers le bas. Les fichiers
        OneDrive « en ligne uniquement » gardent d'abord leur icone : ils passent en dernier (Windows les telecharge)."""
        import time
        from .session import en_nuage
        a_faire, nuages = [], []
        for it in getattr(self, "_a_vignetter", []):
            c = it.data(Qt.UserRole)
            if not c or str(c).startswith("distant:"):
                continue
            if c.replace("/", "\\").startswith("\\\\"):    # NAS : jamais regarde depuis l'interface
                if c not in a_faire:
                    a_faire.append(c)
                continue
            pm = miniature_cachee(c)
            if pm is not None:
                it.setIcon(pm)
            elif pm is None and c not in _SANS_MINIATURE:
                if en_nuage(c):
                    if c not in nuages:
                        nuages.append(c)
                elif c not in a_faire:
                    a_faire.append(c)
        self._a_vignetter = []
        self._gen_vign = gen = getattr(self, "_gen_vign", 0) + 1
        nuage = len(nuages)
        a_faire += nuages
        if not a_faire:
            return
        from PySide6.QtCore import QThread, Signal as _S

        class _V(QThread):
            faite = _S(str)
            fin = _S(int, int, float)

            def run(s_):
                t0, ok, ko = time.monotonic(), 0, 0
                for c in a_faire:
                    if self._gen_vign != gen:
                        return
                    try:
                        from .session import joignable
                        r = preparer_miniature(c) if joignable(c) else None
                    except Exception:                # noqa: BLE001
                        r = None
                    if r:
                        ok += 1
                        s_.faite.emit(c)
                    else:
                        ko += 1
                        _SANS_MINIATURE.add(c)
                s_.fin.emit(ok, ko, time.monotonic() - t0)
        v = _V()
        _TACHES_ACCUEIL.add(v)
        v.faite.connect(lambda c, g=gen: self._gen_vign == g and self._poser_miniature(c))
        v.fin.connect(lambda ok, ko, d, n=nuage: self._noter_miniatures(ok, ko, n, d))
        v.finished.connect(lambda v=v: _TACHES_ACCUEIL.discard(v))
        v.start()

    def _poser_miniature(self, chemin):
        pm = miniature_cachee(chemin)
        if pm is None:
            return
        try:
            for i in range(self.liste.count()):
                it = self.liste.item(i)
                if it.data(Qt.UserRole) == chemin:
                    it.setIcon(pm)
        except RuntimeError:
            pass

    def _noter_miniatures(self, ok, ko, nuage, duree):
        if getattr(self, "_journal_ecrit", False) or not (ok or ko or nuage):
            return
        self._journal_ecrit = True
        _ecrire_journal(f"accueil : miniatures {ok} faites en {_duree(duree)}"
                        + (f", {ko} impossibles (protégés ou abîmés)" if ko else "")
                        + (f", dont {nuage} OneDrive en ligne uniquement (téléchargés en dernier)" if nuage else ""))

    def _echeance_lien(self, lien):
        from urllib.parse import unquote
        from .apprentissage import marquer_echeance
        action, _s, cle = lien.partition(":")
        cle = unquote(cle)
        if cle == "*" and QMessageBox.question(self, "PhilPDF", _("Retirer toutes les échéances proposées par l'IA ?")) != QMessageBox.Yes:
            return
        marquer_echeance(self.params, cle, retirer=(action == "retirer"))
        self.rafraichir()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._adapter_tete()
        # fenetre etroite (petit ecran) : la fiche de droite laisse toute la largeur a la liste des recents
        if hasattr(self, "fiche"):
            large = self.width() >= 900
            if getattr(self.fiche, "autorisee", True) != large:
                self.fiche.autorisee = large
                sp = self.fiche.sizePolicy()
                sp.setRetainSizeWhenHidden(large)
                self.fiche.setSizePolicy(sp)
                if not large:
                    self.fiche.hide()

    def _adapter_tete(self):
        if not hasattr(self, "_boutons_tete"):
            return
        if not hasattr(self, "_larg_tete"):          # largeurs reelles (police grasse du style comprise), une fois
            self._larg_tete = (sum(x.sizeHint().width() + 8 for x, _t in self._boutons_tete),
                               self._marque.sizeHint().width())
        dispo = self.width() - 64 - 56 - 40
        plein, marque = self._larg_tete
        mode = "complet" if dispo >= plein + marque else "court" if dispo >= plein + 150 else "icones"
        if mode == self._tete_mode:
            return
        self._tete_mode = mode
        self._marque.setText('<span style="font-size:26px;font-weight:700">Phil<span style="color:#c9252d">PDF</span></span>'
                             + ('<br><span style="color:#555">Editeur PDF · éditez, signez, allégez en toute liberté</span>'
                                if mode == "complet" else ""))
        for x, t in self._boutons_tete:
            x.setText(t if mode != "icones" else "")
            x.setIconSize(QSize(20, 20) if mode == "icones" else QSize(16, 16))

    def _etat_synchro(self):
        """Derniere synchronisation de ce poste : reussie (heure) ou echec (raison), visible sur l'Accueil."""
        e = self.params.get("synchro_etat") or {}
        if not e.get("quand"):
            return ""
        import html
        j, _t, h = e["quand"].partition("T")
        quand = h[:5] if j == __import__("datetime").date.today().isoformat() else f"{j[8:10]}/{j[5:7]} {h[:5]}"
        if e.get("ok"):
            autres = []
            try:                                     # memes sources que « Mes postes » : reglages ET session
                from .session import session_de
                from . import reglages as _rg
                moi = self.params.get("machine", "")
                autres = [m for m, v in session_de(self.params).lire().items() if m != moi and isinstance(v, dict)]
                if not autres:
                    pd = _rg.chemin_drive(self.params)
                    autres = [m for m in ((_rg.lire_drive(pd).get("postes") if pd else None) or {}) if m != moi]
            except Exception:                        # noqa: BLE001
                autres = None
            seul = "" if autres or autres is None else (
                " · <span style='color:#a35c00'>" + _("aucun autre poste trouvé à cet emplacement : vos autres postes "
                                                      "utilisent peut-être un autre compte") + "</span>")
            return " · <span style='color:#1d7a35'>" + _("✓ synchronisé à {h}", h=quand) + "</span>" + seul
        return " · <span style='color:#c9252d'>" + _("✕ échec à {h} : {raison}", h=quand, raison=html.escape(e.get("erreur", "")[:90])) + "</span>"

    def _rappel_autre(self):
        """Fichiers ouverts sur l'autre poste deja vus (bandeau ferme) : une simple mention, cliquable."""
        a = getattr(self, "_autre", None)
        if not a or self.carte.isVisible():
            return ""
        m, _d, fichiers = a[0], a[1], a[2]
        return " &nbsp;·&nbsp; " + _("Sur {m} : {n} fichier(s) ouvert(s)", m=m, n=len(fichiers)) + \
            " <a href='autre'>" + _("voir") + "</a>"

    def revoir_autre(self):
        a = getattr(self, "_autre", None)
        if a:
            self.montrer_synchro(*a, forcer=True)

    def _lieu_synchro(self):
        cid = self.params.get("drive_compte")
        c = next((x for x in self.params.get("comptes", []) if x["id"] == cid), None) if cid else None
        if c:
            from .synchro_choix import libelle_compte
            return libelle_compte(c)
        return self.params.get("drive", "")

    def _clic_recent(self, it):
        chemin = it.data(Qt.UserRole)
        if chemin:
            self.ouvrir.emit(chemin)
            return
        l = it.data(Qt.UserRole + 1) or {}
        if l.get("e") is not None:                    # fichier d'un autre poste introuvable ici : le chercher
            self.chercher_recent.emit(l["machine"], l["e"])

    def _menu_fichier(self, pos):
        it = self.liste.itemAt(pos)
        if not it:
            return
        chemin = it.data(Qt.UserRole)
        existe = bool(chemin) and os.path.exists(chemin)
        if not chemin:
            l = it.data(Qt.UserRole + 1) or {}
            from PySide6.QtWidgets import QMenu
            m = QMenu(self)
            if l.get("e") is not None:
                m.addAction(icone("rechercher", "#444444"), _("Chercher sur ce poste..."),
                            lambda: self.chercher_recent.emit(l["machine"], l["e"]))
            if l.get("chemin_origine") and l.get("machine") == self.params.get("machine"):
                m.addAction(icone("fermer", "#444444"), _("Retirer de la liste"),
                            lambda: self.action_fichier.emit(l["chemin_origine"], "retirer"))
            m.exec(self.liste.viewport().mapToGlobal(pos))
            return
        from PySide6.QtWidgets import QMenu
        m = QMenu(self)

        def act(ic, texte, action, actif=True):
            a = m.addAction(icone(ic, "#444444"), texte)
            a.setEnabled(actif)
            a.triggered.connect(lambda: self.action_fichier.emit(chemin, action))
        act("ouvrir", _("Ouvrir"), "ouvrir", existe)
        act("archiver", _("Ouvrir l'emplacement du fichier"), "emplacement", existe)
        m.addSeparator()
        act("ocr", _("Reconnaître le texte (OCR)..."), "ocr", existe)
        act("ia", _("Résumer avec l'IA..."), "resume", existe)
        act("archiver", _("Renommer et classer avec l'IA..."), "classer", existe)
        act("filigrane", _("Ajouter un filigrane..."), "filigrane", existe)
        act("entete", _("En-tête et pied de page..."), "entete", existe)
        act("alleger", _("Alléger le fichier..."), "alleger", existe)
        act("imprimer", _("Imprimer..."), "imprimer", existe)
        m.addSeparator()
        act("copier", _("Copier le chemin"), "copier_chemin")
        act("fermer", _("Retirer de la liste"), "retirer")
        m.exec(self.liste.viewport().mapToGlobal(pos))

    def montrer_synchro(self, machine, date, fichiers, resultats, plus_recente=True, doublons=None, deja_vu=False, forcer=False):
        from .session import date_fr, nb_fichiers
        self._autre = (machine, date, fichiers, resultats, plus_recente, doublons)
        self.doublons = doublons or {}
        if deja_vu and not forcer:                 # deja traite (Reprendre ou Ignorer) : simple mention sur la ligne d'etat
            self.carte.hide()
            self.rafraichir()
            return
        n = sum(1 for c, _x in resultats if c)
        if plus_recente:
            self.carte_titre.setText(_('<b>Session plus récente sur {machine}</b> (le {date}) : {nb}, {n} retrouvé{x} sur ce poste.', machine=machine, date=date_fr(date), nb=nb_fichiers(len(fichiers)), n=n, x='s' if n > 1 else ''))
        else:
            self.carte_titre.setText(_("<b>Ouverts sur {machine}</b> (le {date}) : {nb}, {n} retrouvé(s) sur ce poste (les autres sont grisés).",
                                       machine=machine, date=date_fr(date), nb=nb_fichiers(len(fichiers)), n=n))
        self.carte_liste.clear()
        for i, (e, (c, cm)) in enumerate(zip(fichiers, resultats)):
            if i in self.doublons:
                it = QListWidgetItem(_("{nom}  —  trouvé à {n} endroits sur ce poste : double-cliquez pour choisir lequel",
                                       nom=e['nom'], n=len(self.doublons[i])))
                it.setForeground(Qt.darkYellow)
            else:
                it = QListWidgetItem(f"{e['nom']}  —  {c}" if c else
                                     _('{nom}  —  introuvable sur {machine} (ouvert sur {machine2} le {date})', nom=e['nom'], machine=self.params['machine'], machine2=machine, date=date_fr(date)))
            it.setToolTip(cm)
            it.setData(Qt.UserRole, i)
            if not c:
                it.setForeground(Qt.gray)
            self.carte_liste.addItem(it)
        self.carte_liste.setFixedHeight(min(150, self.carte_liste.sizeHintForRow(0) * len(fichiers) + 6))
        self.b_reprendre.setEnabled(n > 0)
        self.carte.show()
        self.rafraichir()

    def cacher_synchro(self):
        self.carte.hide()
        self.rafraichir()

    def choisir_doublon(self, i):
        """Le meme fichier est a plusieurs endroits ici : on choisit une fois, PhilPDF retient le dossier."""
        chemins = (self.doublons or {}).get(i)
        if not chemins:
            return None
        import datetime
        from PySide6.QtWidgets import QInputDialog
        lignes = []
        for p in chemins:
            try:
                q = datetime.datetime.fromtimestamp(os.path.getmtime(p)).strftime("%d/%m/%Y %H:%M")
            except OSError:
                q = "?"
            lignes.append(_("{chemin}   (modifié le {date})", chemin=p, date=q))
        a = self._autre
        nom = a[2][i]["nom"]
        choix, ok = QInputDialog.getItem(self, _("Fichier à plusieurs endroits"),
                                         _("« {nom} » est à {n} endroits sur ce poste. Lequel correspond à celui de {m} ?\n"
                                           "PhilPDF retiendra ce dossier et ne posera plus la question.", nom=nom, n=len(chemins), m=a[0]),
                                         lignes, 0, False)
        if not ok:
            return None
        p = chemins[lignes.index(choix)]
        res = list(a[3])
        res[i] = (p, _("choisi par vous"))
        self.doublon_choisi.emit(a[0], a[2][i], p)
        self.doublons = {k: v for k, v in self.doublons.items() if k != i}
        return p


_MINIATURES = {}


def _cle_miniature(chemin, hauteur):
    import hashlib
    st = os.stat(chemin)
    return hashlib.sha1(f"{os.path.normcase(chemin)}|{st.st_mtime_ns}|{st.st_size}|{hauteur}".encode()).hexdigest()


def preparer_miniature(chemin, hauteur=52):
    """Fabrique la miniature dans le cache disque (utilisable hors de l'interface : QImage seulement).
    Renvoie le chemin du PNG, ou None si le fichier ne s'ouvre pas."""
    from PySide6.QtGui import QImage, QPainter, QColor
    from .config import dossier_donnees
    try:
        cle = _cle_miniature(chemin, hauteur)
    except OSError:
        return None
    d = os.path.join(dossier_donnees(), "miniatures")
    f = os.path.join(d, cle + ".png")
    if os.path.exists(f):
        return f
    import pymupdf as fitz
    try:
        with fitz.open(chemin) as doc:
            if doc.needs_pass or not len(doc):
                return None
            p = doc[0]
            z = hauteur * 2 / max(1, p.rect.height)
            png = p.get_pixmap(matrix=fitz.Matrix(z, z), alpha=False, annots=True).tobytes("png")
    except Exception:                                # noqa: BLE001
        return None
    img = QImage()
    img.loadFromData(png, "PNG")
    img = img.scaledToHeight(hauteur * 2, Qt.SmoothTransformation)
    cadre = QImage(img.width() + 2, img.height() + 2, QImage.Format_RGB32)
    cadre.fill(QColor("#cfcfcf"))
    pt = QPainter(cadre)
    pt.drawImage(1, 1, img)
    pt.end()
    try:
        os.makedirs(d, exist_ok=True)
        cadre.save(f, "PNG")
    except OSError:
        return None
    return f


def _duree(x):
    return f"{x * 1000:.0f} ms" if x < 1 else f"{x:.1f} s"


def _ecrire_journal(texte):
    try:
        from .journal import ecrire
        ecrire("démarrage", texte)
    except Exception:                                # noqa: BLE001
        pass


_SANS_MINIATURE = set()     # fichiers qui ne s'ouvrent pas : pas la peine de reessayer


def miniature_cachee(chemin, hauteur=52):
    """Miniature deja faite (memoire ou disque), sans jamais ouvrir le PDF : None sinon."""
    from PySide6.QtGui import QIcon, QPixmap
    from .config import dossier_donnees
    if not chemin or str(chemin).startswith("distant:"):
        return None
    try:
        cle = _cle_miniature(chemin, hauteur)
    except OSError:
        return None
    if _MINIATURES.get(cle) is not None:
        return _MINIATURES[cle]
    f = os.path.join(dossier_donnees(), "miniatures", cle + ".png")
    pm = QPixmap()
    if os.path.exists(f) and pm.load(f):
        _MINIATURES[cle] = QIcon(pm)
        return _MINIATURES[cle]
    return None


def miniature(chemin, hauteur=52):
    """Icone : premiere page du PDF en petit, avec un fin cadre ; gardee en cache disque (chemin + date + taille).
    None si le fichier ne s'ouvre pas (protege, abime)."""
    from PySide6.QtGui import QIcon, QPixmap
    try:
        cle = _cle_miniature(chemin, hauteur)
    except OSError:
        return None
    if cle in _MINIATURES:
        return _MINIATURES[cle]
    f = preparer_miniature(chemin, hauteur)
    pm = QPixmap()
    if not f or not pm.load(f):
        _MINIATURES[cle] = None
        return None
    _MINIATURES[cle] = QIcon(pm)
    return _MINIATURES[cle]


_FICHES = {}


def fiche_fichier(chemin):
    """Ce que la fiche de l'Accueil montre d'un PDF : pages, poids, dates, etats (signe, formulaire, protege,
    scan sans texte), debut du texte et apercu de la page 1. Garde en cache (chemin + date + taille)."""
    import datetime
    import pymupdf as fitz
    try:
        st = os.stat(chemin)
    except OSError:
        return None
    cle = (os.path.normcase(chemin), st.st_mtime_ns, st.st_size)
    if cle in _FICHES:
        return _FICHES[cle]
    f = {"taille": st.st_size, "modifie": datetime.datetime.fromtimestamp(st.st_mtime), "pages": 0, "etats": [],
         "texte": "", "image": None}
    try:
        with fitz.open(chemin) as d:
            if d.needs_pass:
                f["etats"].append(("cadenas", _("Protégé par mot de passe")))
            else:
                f["pages"] = len(d)
                p = d[0]
                z = 640 / max(1, p.rect.height)            # net sur les ecrans haute definition (zoom Windows 150-200 %)
                f["image"] = p.get_pixmap(matrix=fitz.Matrix(z, z), alpha=False).tobytes("png")
                txt = " ".join(p.get_text("text").split())
                f["texte"] = (txt[:260] + "…") if len(txt) > 260 else txt
                if not txt:
                    f["etats"].append(("scan", _("Scan sans texte (OCR possible)")))
                try:
                    signes = [w for pg in d for w in (pg.widgets() or []) if w.field_type == fitz.PDF_WIDGET_TYPE_SIGNATURE]
                    champs = [w for pg in d for w in (pg.widgets() or []) if w.field_type != fitz.PDF_WIDGET_TYPE_SIGNATURE]
                except Exception:
                    signes, champs = [], []
                if any(w.is_signed for w in signes):
                    f["etats"].append(("signe", _("Signé numériquement")))
                elif signes:
                    f["etats"].append(("signe", _("Champ de signature à remplir")))
                if champs:
                    f["etats"].append(("formulaire", _("Formulaire ({n} champs)", n=len(champs))))
                if d.is_encrypted or (d.permissions is not None and d.permissions != -1 and d.permissions < 0xFFFFF000):
                    pass
                try:
                    if "pdfaid:part" in (d.get_xml_metadata() or ""):
                        f["etats"].append(("archive", _("PDF/A (archivage)")))
                except Exception:
                    pass
    except Exception:
        f["etats"].append(("erreur", _("Fichier illisible ou abîmé")))
    _FICHES[cle] = f
    return f


from PySide6.QtWidgets import QStyledItemDelegate as _Delegue


class DelegueRecent(_Delegue):
    """Ligne des Recents dessinee en texte riche (« aussi sur Bureau » en gras), sinon comme d'habitude.
    Le texte passe a la ligne quand la fenetre est etroite (petit ecran) : rien n'est coupe, la ligne grandit."""

    @staticmethod
    def _doc(html, police, largeur):
        from PySide6.QtGui import QTextDocument, QTextOption
        doc = QTextDocument()
        doc.setDefaultFont(police)
        doc.setDocumentMargin(0)
        o = QTextOption()
        o.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)   # chemins longs sans espace compris
        doc.setDefaultTextOption(o)
        doc.setHtml(html)
        doc.setTextWidth(max(80, largeur))
        return doc

    def sizeHint(self, option, index):
        base = super().sizeHint(option, index)
        html = index.data(Qt.UserRole + 2)
        w = option.widget
        if not html or w is None:
            return base
        icone = (option.decorationSize.width() if option.decorationSize.isValid() else 40) + 28
        larg = w.viewport().width() - icone - 12
        h = self._doc(html, option.font, larg).size().height()
        from PySide6.QtCore import QSize
        return QSize(max(100, w.viewport().width() - 4), max(base.height(), int(h) + 14))

    def paint(self, painter, option, index):
        html = index.data(Qt.UserRole + 2)
        if not html:
            return super().paint(painter, option, index)
        from PySide6.QtWidgets import QStyleOptionViewItem, QStyle, QApplication as _A
        from PySide6.QtGui import QAbstractTextDocumentLayout, QPalette
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        w = opt.widget
        st = w.style() if w else _A.style()
        texte = opt.text
        opt.text = ""
        st.drawControl(QStyle.CE_ItemViewItem, opt, painter, w)
        opt.text = texte
        zone = st.subElementRect(QStyle.SE_ItemViewItemText, opt, w)
        doc = self._doc(html, opt.font, zone.width() - 8)
        painter.save()
        painter.translate(zone.left() + 4, zone.top() + max(0, (zone.height() - doc.size().height()) / 2))
        ctx = QAbstractTextDocumentLayout.PaintContext()
        coul = index.data(Qt.ForegroundRole)
        ctx.palette.setColor(QPalette.Text, coul.color() if hasattr(coul, "color") else
                             (coul if coul is not None else opt.palette.color(QPalette.Text)))
        doc.documentLayout().draw(painter, ctx)
        painter.restore()


class FicheFichier(QFrame):
    """Fiche du fichier survole, a droite de la liste : grand apercu, detail, etats, debut du texte."""

    def __init__(self):
        super().__init__()
        self.setObjectName("fiche")
        self.setFixedWidth(300)
        self.setStyleSheet("#fiche{background:#ffffff;border:1px solid #e2e2e2;border-radius:12px}"
                           "QLabel{background:transparent}")
        v = QVBoxLayout(self)
        v.setContentsMargins(18, 18, 18, 18)
        v.setSpacing(10)
        self.apercu = QLabel()
        self.apercu.setAlignment(Qt.AlignCenter)
        self.apercu.setMinimumHeight(240)
        self.apercu.setStyleSheet("background:#f3f4f6;border-radius:8px")
        v.addWidget(self.apercu)
        self.titre = QLabel()
        self.titre.setWordWrap(True)
        self.titre.setStyleSheet("font-size:15px;font-weight:600;color:#1f1f1f")
        v.addWidget(self.titre)
        self.detail = QLabel()
        self.detail.setWordWrap(True)
        self.detail.setTextFormat(Qt.RichText)
        self.detail.setStyleSheet("color:#555;font-size:12px")
        v.addWidget(self.detail)
        self.etats = QLabel()
        self.etats.setWordWrap(True)
        self.etats.setTextFormat(Qt.RichText)
        v.addWidget(self.etats)
        self.texte = QLabel()
        self.texte.setWordWrap(True)
        self.texte.setStyleSheet("color:#444;font-size:12px;font-style:italic;border-left:3px solid #e6e6e6;"
                                 "padding-left:8px")
        v.addWidget(self.texte)
        v.addStretch(1)
        sp = self.sizePolicy()                      # cachee, elle garde sa place : la liste ne bouge pas
        sp.setRetainSizeWhenHidden(True)
        self.setSizePolicy(sp)
        self.montrer(None)

    def montrer(self, l):
        from PySide6.QtGui import QPixmap
        import html
        if not l or not getattr(self, "autorisee", True):   # rien sous la souris, ou fenetre trop etroite
            self.hide()
            return
        self.show()
        self.apercu.setStyleSheet("background:#f3f4f6;border-radius:8px")
        self.titre.setText(l.get("nom", ""))
        chemin = l.get("chemin")
        f = fiche_fichier(chemin) if chemin else None
        lignes = []
        if f is None:
            self.apercu.setPixmap(QPixmap())
            self.apercu.setText(_("Introuvable sur ce poste"))
            lignes.append(_("Ouvert sur {poste}", poste=html.escape(l.get("poste", "?"))))
            if l.get("chemin_origine"):
                lignes.append(html.escape(l["chemin_origine"]))
            lignes.append(_("Cliquez pour le chercher ici ou l'indiquer vous-même."))
            self.detail.setText("<br>".join(lignes))
            self.etats.setText("")
            self.texte.hide()
            return
        if f["image"]:
            pm = QPixmap()
            pm.loadFromData(f["image"], "PNG")
            dpr = self.devicePixelRatioF() or 1.0
            pm = pm.scaled(int(264 * dpr), int(240 * dpr), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            pm.setDevicePixelRatio(dpr)
            self.apercu.setPixmap(pm)
        else:
            self.apercu.setPixmap(QPixmap())
            self.apercu.setText("")
        ko = f["taille"] / 1024
        poids = f"{ko / 1024:.1f} Mo".replace(".", ",") if ko >= 1024 else f"{ko:.0f} Ko"
        if f["pages"]:
            lignes.append(_("{n} page(s) · {p}", n=f["pages"], p=poids))
        else:
            lignes.append(poids)
        lignes.append(_("Modifié le {d}", d=f["modifie"].strftime("%d/%m/%Y à %H:%M")))
        if l.get("date"):
            from .session import date_fr
            lignes.append(_("Ouvert {d}", d=date_fr(l["date"])))
        if l.get("ouvert_sur"):
            lignes.append(_("Ouvert en ce moment sur {p}", p=", ".join(l["ouvert_sur"])))
        if l.get("autre_poste") and l.get("chemin_origine"):
            lignes.append(_("<b>Sur {poste}</b> : {c}", poste=html.escape(l.get("poste", "?")),
                            c=html.escape(l["chemin_origine"])))
        for poste in l.get("aussi_sur") or []:
            c = (l.get("chemins_autres") or {}).get(poste) or ""
            lignes.append(_("<b>Aussi sur {poste}</b> : {c}", poste=html.escape(poste), c=html.escape(c) or "?"))
        self.detail.setText("<br>".join(lignes))
        couleurs = {"signe": ("#e6f4ea", "#1e6b34"), "formulaire": ("#fdf1e2", "#8a4b00"),
                    "cadenas": ("#fdecea", "#9b1c1c"), "scan": ("#eef2f7", "#3d5168"),
                    "archive": ("#e6f0fc", "#1452a0"), "erreur": ("#fdecea", "#9b1c1c")}
        self.etats.setText(" ".join(
            f"<span style='background:{couleurs[k][0]};color:{couleurs[k][1]};border-radius:8px;padding:2px 8px;"
            f"font-size:11px'>&nbsp;{html.escape(t)}&nbsp;</span>" for k, t in f["etats"]))
        self.texte.setText(f["texte"])
        self.texte.setVisible(bool(f["texte"]))
