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
        aide = QLabel(_("L'étoile épingle un outil dans le volet de droite des fichiers ouverts. Survolez un outil pour sa bulle d'aide."))
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


class PageAccueil(QWidget):
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
        from .document import defilable
        h.addWidget(defilable(bw), 1)
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
        self.liste.setContextMenuPolicy(Qt.CustomContextMenu)
        self.liste.customContextMenuRequested.connect(self._menu_fichier)
        self.liste.itemClicked.connect(self._clic_recent)
        v.addWidget(self.liste, 1)
        self.rafraichir()

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

    def rafraichir(self):
        from .session import date_fr
        self.liste.clear()
        moi = self.params.get("machine", "")
        section = "ici"
        titres = {"autres": _("Sur vos autres postes"), "introuvable": _("Introuvables sur ce poste")}
        self._a_vignetter = []
        for l in self.lignes_recents():
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
            if l["ouvert_sur"]:
                infos.append("● " + _("ouvert sur {poste}", poste=", ".join(l["ouvert_sur"])))
            if l.get("autre_poste") and ici:
                infos.append(_("retrouvé sur ce poste"))
            if not ici:
                infos.append(_("introuvable sur ce poste"))
            it = QListWidgetItem(icone("creer", "#c9252d" if ici else "#bbbbbb"),
                                 f"{l['nom']}\n{l['dossier']}" + ("   ·   " + "   ·   ".join(infos) if infos else ""))
            it.setData(Qt.UserRole, ici or "")
            it.setData(Qt.UserRole + 1, l)
            it.setToolTip(ici or (_("Sur {poste} : {chemin}", poste=l["poste"], chemin=l["chemin_origine"] or "?") + "\n"
                                  + _("Cliquez pour le chercher sur ce poste ou l'indiquer vous-même.")))
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
        """Miniature de la premiere page a la place de l'icone (comme Acrobat), une par une pour ne pas bloquer."""
        from PySide6.QtCore import QTimer
        if not getattr(self, "_a_vignetter", None):
            return
        it = self._a_vignetter.pop(0)
        try:
            pm = miniature(it.data(Qt.UserRole))
            if pm is not None:
                it.setIcon(pm)
        except RuntimeError:                              # liste reconstruite entre-temps
            return
        QTimer.singleShot(0, self._vignetter)

    def _echeance_lien(self, lien):
        from urllib.parse import unquote
        from .apprentissage import marquer_echeance
        action, _s, cle = lien.partition(":")
        cle = unquote(cle)
        if cle == "*" and QMessageBox.question(self, "PhilPDF", _("Retirer toutes les échéances proposées par l'IA ?")) != QMessageBox.Yes:
            return
        marquer_echeance(self.params, cle, retirer=(action == "retirer"))
        self.rafraichir()

    def _etat_synchro(self):
        """Derniere synchronisation de ce poste : reussie (heure) ou echec (raison), visible sur l'Accueil."""
        e = self.params.get("synchro_etat") or {}
        if not e.get("quand"):
            return ""
        import html
        j, _t, h = e["quand"].partition("T")
        quand = h[:5] if j == __import__("datetime").date.today().isoformat() else f"{j[8:10]}/{j[5:7]} {h[:5]}"
        if e.get("ok"):
            return " · <span style='color:#1d7a35'>" + _("✓ synchronisé à {h}", h=quand) + "</span>"
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


def miniature(chemin, hauteur=52):
    """Icone : premiere page du PDF en petit, avec un fin cadre ; gardee en cache disque (chemin + date + taille).
    None si le fichier ne s'ouvre pas (protege, abime)."""
    import hashlib
    from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QPen
    from .config import dossier_donnees
    try:
        st = os.stat(chemin)
    except OSError:
        return None
    cle = hashlib.sha1(f"{os.path.normcase(chemin)}|{st.st_mtime_ns}|{st.st_size}|{hauteur}".encode()).hexdigest()
    if cle in _MINIATURES:
        return _MINIATURES[cle]
    d = os.path.join(dossier_donnees(), "miniatures")
    f = os.path.join(d, cle + ".png")
    pm = QPixmap()
    if not (os.path.exists(f) and pm.load(f)):
        import pymupdf as fitz
        try:
            with fitz.open(chemin) as doc:
                if doc.needs_pass or not len(doc):
                    _MINIATURES[cle] = None
                    return None
                p = doc[0]
                z = hauteur * 2 / max(1, p.rect.height)
                img = p.get_pixmap(matrix=fitz.Matrix(z, z), alpha=False, annots=True)
        except Exception:
            _MINIATURES[cle] = None
            return None
        pm.loadFromData(img.tobytes("png"), "PNG")
        pm = pm.scaledToHeight(hauteur * 2, Qt.SmoothTransformation)
        cadre = QPixmap(pm.width() + 2, pm.height() + 2)
        cadre.fill(QColor("#cfcfcf"))
        pt = QPainter(cadre)
        pt.drawPixmap(1, 1, pm)
        pt.end()
        pm = cadre
        try:
            os.makedirs(d, exist_ok=True)
            pm.save(f, "PNG")
        except OSError:
            pass
    _MINIATURES[cle] = QIcon(pm)
    return _MINIATURES[cle]
