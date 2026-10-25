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
        b3.clicked.connect(self.cacher_synchro)
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
        self.bandeau.linkActivated.connect(lambda _l: self.changer_synchro.emit())
        hl.addWidget(self.bandeau, 1)
        bs = QPushButton()
        bs.setIcon(icone("synchro", "#2b6cb0"))
        bs.setToolTip(_('Synchroniser les fichiers ouverts avec vos autres postes'))
        bs.setFlat(True)
        bs.clicked.connect(self.synchroniser)
        hl.addWidget(bs)
        v.addLayout(hl)
        r = QLabel(_('Récents'))
        r.setStyleSheet("font-size:18px;font-weight:600")
        v.addWidget(r)
        self.liste = QListWidget()
        self.liste.setStyleSheet("QListWidget{background:#fff;border:1px solid #e2e2e2;border-radius:10px;font-size:14px}"
                                 "QListWidget::item{padding:10px;border-bottom:1px solid #f0f0f0}"
                                 "QListWidget::item:hover{background:#f4f7fb}")
        self.liste.itemActivated.connect(lambda it: self.ouvrir.emit(it.data(Qt.UserRole)))
        self.liste.setContextMenuPolicy(Qt.CustomContextMenu)
        self.liste.customContextMenuRequested.connect(self._menu_fichier)
        self.liste.itemClicked.connect(lambda it: self.ouvrir.emit(it.data(Qt.UserRole)))
        v.addWidget(self.liste, 1)
        self.rafraichir()

    def rafraichir(self):
        self.liste.clear()
        for p in self.params["recents"]:
            existe = os.path.exists(p)
            it = QListWidgetItem(icone("creer", "#c9252d" if existe else "#bbbbbb"),
                                 f"{os.path.basename(p)}\n{os.path.dirname(p)}" + ("" if existe else _('   (introuvable sur ce PC)')))
            it.setData(Qt.UserRole, p)
            if not existe:
                it.setForeground(Qt.gray)
            self.liste.addItem(it)
        self.bandeau.setText(_('Poste : <b>{machine}</b>. ', machine=self.params['machine']) + (
                _('Synchronisation : ') + self._lieu_synchro() + " &nbsp;<a href='changer_synchro'>" + _("changer") + "</a>"
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

    def _echeance_lien(self, lien):
        from urllib.parse import unquote
        from .apprentissage import marquer_echeance
        action, _s, cle = lien.partition(":")
        cle = unquote(cle)
        if cle == "*" and QMessageBox.question(self, "PhilPDF", _("Retirer toutes les échéances proposées par l'IA ?")) != QMessageBox.Yes:
            return
        marquer_echeance(self.params, cle, retirer=(action == "retirer"))
        self.rafraichir()

    def _lieu_synchro(self):
        cid = self.params.get("drive_compte")
        c = next((x for x in self.params.get("comptes", []) if x["id"] == cid), None) if cid else None
        if c:
            from .synchro_choix import libelle_compte
            return libelle_compte(c)
        return self.params.get("drive", "")

    def _menu_fichier(self, pos):
        it = self.liste.itemAt(pos)
        if not it:
            return
        chemin = it.data(Qt.UserRole)
        existe = os.path.exists(chemin)
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

    def montrer_synchro(self, machine, date, fichiers, resultats):
        from .session import date_fr, nb_fichiers
        n = sum(1 for c, _x in resultats if c)
        self.carte_titre.setText(_('<b>Session plus récente sur {machine}</b> (le {date}) : {nb}, {n} retrouvé{x} sur ce poste.', machine=machine, date=date_fr(date), nb=nb_fichiers(len(fichiers)), n=n, x='s' if n > 1 else ''))
        self.carte_liste.clear()
        for e, (c, cm) in zip(fichiers, resultats):
            it = QListWidgetItem(f"{e['nom']}  —  {c}" if c else
                                 _('{nom}  —  introuvable sur {machine} (ouvert sur {machine2} le {date})', nom=e['nom'], machine=self.params['machine'], machine2=machine, date=date_fr(date)))
            it.setToolTip(cm)
            if not c:
                it.setForeground(Qt.gray)
            self.carte_liste.addItem(it)
        self.carte_liste.setFixedHeight(min(150, self.carte_liste.sizeHintForRow(0) * len(fichiers) + 6))
        self.b_reprendre.setEnabled(n > 0)
        self.carte.show()

    def cacher_synchro(self):
        self.carte.hide()
