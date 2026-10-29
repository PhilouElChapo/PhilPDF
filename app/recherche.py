"""Rechercher dans tous mes PDF : une question en francais, PhilPDF retrouve les documents.

Index sur ce poste (texte integral, date, expediteur), mis a jour en arriere-plan a chaque ouverture de la
fenetre. Avec une clef d'IA, la question est d'abord traduite en mots-clefs, expediteur et periode (seule la
question est envoyee a l'IA, jamais vos documents).
"""
import datetime, os, re

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QListWidget,
                               QListWidgetItem, QCheckBox, QFileDialog, QMenu, QTreeWidget, QTreeWidgetItem,
                               QComboBox, QWidget, QHeaderView, QDialogButtonBox)

from .langue import _
from .icones import icone
from . import ia

MOTS_VIDES = set("""le la les un une des du de d l au aux et ou a à en dans sur pour par avec sans mon ma mes ton ta tes
son sa ses notre nos votre vos leur leurs ce cet cette ces qui que quoi dont où ne pas plus est sont été retrouve
retrouver trouve trouver cherche chercher montre montrer donne donner document documents fichier fichiers pdf courrier
courriers lettre the of""".split())
CONSIGNES = """Tu transformes une demande de recherche de documents PDF en critères. Réponds en JSON :
{"mots": ["<mots-clefs et synonymes utiles à chercher dans le texte, 1 à 8>"], "expediteur": "<organisme ou
personne qui a envoyé le document, ou chaîne vide>", "date_debut": "AAAA-MM-JJ ou vide", "date_fin": "AAAA-MM-JJ ou vide"}.
Calcule les périodes relatives (« le dernier trimestre », « l'an dernier », « en mars ») à partir de la date du jour.
N'invente pas de critère absent de la demande. Si l'expéditeur est le seul critère, 'mots' peut être vide."""


def chemin_index():
    from .config import dossier_donnees
    return os.path.join(dossier_donnees(), "index_recherche.sqlite")


def racines_par_defaut(params):
    from .session import dossiers_connus
    out = [{"genre": "local", "chemin": c} for k, c in dossiers_connus(params).items() if k != "maison"]
    return out


def libelle_racine(r, params):
    if r["genre"] == "local":
        return r["chemin"]
    from . import distant
    c = next((x for x in params.get("comptes", []) if x["id"] == r["id"]), None)
    return f"{distant.libelle(c) if c else '?'} : {r.get('dossier') or '/'}"


def racines(params):
    r = params.get("recherche_racines")
    return r if r else racines_par_defaut(params)


class EditeurLieux(QWidget):
    """Liste des emplacements ou chercher (ce PC, NAS, Drives), a ajouter ou retirer : dans la fenetre de
    recherche et dans les Preferences."""

    def __init__(self, params, parent=None, depart=None):
        super().__init__(parent)
        self.params, self.depart = params, depart
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        self.liste = QListWidget()
        self.liste.setObjectName("lieux_recherche")
        self.liste.setMinimumHeight(110)
        v.addWidget(self.liste, 1)
        h = QHBoxLayout()
        b = QPushButton(icone("ouvrir", "#c8a000"), _(" Ajouter un dossier de ce PC..."))
        b.clicked.connect(self._ajouter_dossier)
        h.addWidget(b)
        self.b_compte = QPushButton(icone("archiver", "#0f6cbd"), _(" Ajouter un NAS ou un Drive"))
        self.b_compte.clicked.connect(self._menu_comptes)
        h.addWidget(self.b_compte)
        b = QPushButton(icone("supprimer", "#a33"), _(" Retirer"))
        b.clicked.connect(self._retirer)
        h.addWidget(b)
        h.addStretch(1)
        b = QPushButton(_("Dossiers habituels"))
        b.setToolTip(_("Revenir aux dossiers habituels de ce PC (Documents, Bureau, Téléchargements...)"))
        b.clicked.connect(lambda: self._ecrire([]))
        h.addWidget(b)
        v.addLayout(h)
        self._remplir()

    def _remplir(self):
        self.liste.clear()
        for r in racines(self.params):
            it = QListWidgetItem(icone("ouvrir" if r["genre"] == "local" else "archiver",
                                       "#c8a000" if r["genre"] == "local" else "#0f6cbd"), libelle_racine(r, self.params))
            it.setData(Qt.UserRole, r)
            self.liste.addItem(it)
        if not self.liste.count():
            it = QListWidgetItem(_("Aucun emplacement : ajoutez un dossier, un NAS ou un Drive."))
            it.setFlags(Qt.NoItemFlags)
            self.liste.addItem(it)

    def _ecrire(self, r):
        self.params["recherche_racines"] = r
        self.params.enregistrer()
        self._remplir()

    def _ajouter_dossier(self):
        p = QFileDialog.getExistingDirectory(self, _("Où chercher"), self.depart or os.path.expanduser("~"))
        if p:
            self._ecrire(racines(self.params) + [{"genre": "local", "chemin": p}])

    def _menu_comptes(self):
        m = QMenu(self)
        from . import distant
        actuelles = racines(self.params)
        for c in self.params.get("comptes", []):
            if not any(x.get("id") == c["id"] for x in actuelles):
                a = m.addAction(icone("archiver", "#0f6cbd"), distant.libelle(c))
                a.triggered.connect(lambda _c=False, c=c: self._ecrire(
                    racines(self.params) + [{"genre": "compte", "id": c["id"], "dossier": c.get("dossier") or "/"}]))
        if m.isEmpty():
            a = m.addAction(_("Aucun autre compte (Préférences › Comptes pour en ajouter)"))
            a.setEnabled(False)
        m.exec(self.b_compte.mapToGlobal(self.b_compte.rect().bottomLeft()))

    def _retirer(self):
        it = self.liste.currentItem()
        if it and it.data(Qt.UserRole):
            r = it.data(Qt.UserRole)
            self._ecrire([x for x in racines(self.params) if x != r])


class TacheIndex(QThread):
    etat = Signal(str)
    fini = Signal(int)

    def __init__(self, params, racines):
        super().__init__()
        self.params, self.racines, self.stop = params, racines, False

    def run(self):
        from moteur.index import Index
        ix = Index(chemin_index())
        total_lus = 0
        try:
            for r in self.racines:
                if self.stop:
                    break
                lib = libelle_racine(r, self.params)

                def prog(vus, lus, chemin, lib=lib):
                    self.etat.emit(_("Mise à jour de l'index : {lieu} — {n} PDF lus", lieu=lib, n=total_lus + lus))
                if r["genre"] == "local":
                    if os.path.isdir(r["chemin"]):
                        total_lus += ix.indexer_dossier(r["chemin"], prog, lambda: self.stop)[1]
                else:
                    from . import distant
                    c = next((x for x in self.params.get("comptes", []) if x["id"] == r["id"]), None)
                    if c:
                        try:
                            e = distant.emplacement(c)
                            total_lus += ix.indexer_distant(c, e, r.get("dossier") or e.racine(), prog, lambda: self.stop)[1]
                        except Exception as ex:
                            self.etat.emit(_("{lieu} injoignable : {raison}", lieu=lib, raison=str(ex)[:80]))
            n = ix.nombre()
        finally:
            ix.fermer()
        self.fini.emit(n)


def criteres(params, question, avec_ia):
    """{"mots", "expediteur", "date_debut", "date_fin"} a partir de la question."""
    if avec_ia and ia.disponible(params):
        r = ia.demander(params, CONSIGNES + f"\nDate du jour : {datetime.date.today().isoformat()}.", question,
                        json_attendu=True, max_jetons=600)
        if isinstance(r, dict):
            return {"mots": [str(m) for m in r.get("mots") or [] if str(m).strip()][:10],
                    "expediteur": str(r.get("expediteur") or "").strip(),
                    "date_debut": str(r.get("date_debut") or "")[:10], "date_fin": str(r.get("date_fin") or "")[:10]}
    mots = [m for m in re.findall(r"[\w'-]+", question.lower()) if m not in MOTS_VIDES and len(m) > 1]
    return {"mots": mots, "expediteur": "", "date_debut": "", "date_fin": ""}


class DialogueRecherche(QDialog):
    def __init__(self, fenetre):
        super().__init__(fenetre)
        self.fenetre, self.params = fenetre, fenetre.params
        self.tache = None
        self.setWindowTitle(_("Rechercher dans tous mes PDF"))
        self.resize(860, 620)
        v = QVBoxLayout(self)
        h = QHBoxLayout()
        self.question = QLineEdit()
        self.question.setPlaceholderText(_("ex. le courrier de l'URSSAF du dernier trimestre, la facture EDF de mars..."))
        self.question.returnPressed.connect(self.chercher)
        h.addWidget(self.question, 1)
        b = QPushButton(icone("rechercher", "#0b5e63"), _(" Chercher"))
        b.setProperty("primaire", True)
        b.clicked.connect(self.chercher)
        h.addWidget(b)
        v.addLayout(h)
        h = QHBoxLayout()
        self.avec_ia = QCheckBox(_("Comprendre la question avec l'IA (seule la question est envoyée)"))
        self.avec_ia.setChecked(ia.disponible(self.params))
        self.avec_ia.setEnabled(ia.disponible(self.params))
        h.addWidget(self.avec_ia)
        h.addStretch(1)
        h.addWidget(QLabel(_("Classer :")))
        self.classement = QComboBox()
        self.classement.addItem(_("par dossier"), "dossier")
        self.classement.addItem(_("par pertinence"), "pertinence")
        self.classement.addItem(_("par date (récents d'abord)"), "date")
        self.classement.setCurrentIndex(max(0, self.classement.findData(self.params.get("recherche_classement", "dossier"))))
        self.classement.currentIndexChanged.connect(self._reclasser)
        h.addWidget(self.classement)
        self.b_lieux = QPushButton(_("Où chercher..."))
        self.b_lieux.setToolTip(_("Les dossiers de ce PC, NAS et Drives où PhilPDF cherche (aussi dans Préférences › Recherche)"))
        self.b_lieux.clicked.connect(self.menu_lieux)
        h.addWidget(self.b_lieux)
        b = QPushButton(icone("synchro", "#0f6cbd"), _(" Mettre à jour l'index"))
        b.clicked.connect(self.mettre_a_jour)
        h.addWidget(b)
        v.addLayout(h)
        self.l_lieux = QLabel()
        self.l_lieux.setWordWrap(True)
        self.l_lieux.setStyleSheet("color:#555;font-size:12px")
        self.l_lieux.setTextFormat(Qt.RichText)
        self.l_lieux.linkActivated.connect(lambda _l: self.menu_lieux())
        v.addWidget(self.l_lieux)
        self._maj_lieux()
        self.criteres = QLabel()
        self.criteres.setStyleSheet("color:#555")
        self.criteres.setWordWrap(True)
        v.addWidget(self.criteres)
        self.liste = QTreeWidget()
        self.liste.setObjectName("resultats_recherche")
        self.liste.setColumnCount(2)
        self.liste.setHeaderLabels([_("Dossier / fichier"), _("Date")])
        self.liste.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.liste.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.liste.header().setStretchLastSection(False)
        self.liste.setWordWrap(True)
        self.liste.setUniformRowHeights(False)
        self.liste.itemDoubleClicked.connect(lambda it, _c: self.ouvrir(it))
        self.liste.itemActivated.connect(lambda it, _c: self.ouvrir(it))
        v.addWidget(self.liste, 1)
        self.resultats = []
        self.etat = QLabel()
        self.etat.setStyleSheet("color:#777;font-size:12px")
        v.addWidget(self.etat)
        self.mettre_a_jour()

    # ---------------------------------------------------------------- lieux
    def racines(self):
        return racines(self.params)

    def _enregistrer_racines(self, r):
        self.params["recherche_racines"] = r
        self.params.enregistrer()
        self._maj_lieux()

    def _maj_lieux(self):
        noms = [libelle_racine(r, self.params) for r in self.racines()]
        self.l_lieux.setText(_("Recherche dans : {l}", l=", ".join(noms[:6]) + (" …" if len(noms) > 6 else ""))
                             + " &nbsp;<a href='lieux'>" + _("modifier") + "</a>")

    def menu_lieux(self):
        """Fenetre des emplacements (ajouter, retirer) ; l'index est remis a jour en sortant si ca a change."""
        avant = list(self.racines())
        d = QDialog(self)
        d.setWindowTitle(_("Où chercher"))
        d.resize(640, 360)
        v = QVBoxLayout(d)
        lb = QLabel(_("PhilPDF lit les PDF de ces emplacements (et de leurs sous-dossiers) pour les retrouver. "
                      "Les mêmes réglages sont dans Préférences › Recherche."))
        lb.setWordWrap(True)
        v.addWidget(lb)
        v.addWidget(EditeurLieux(self.params, d, self.fenetre.dossier_depart()), 1)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.button(QDialogButtonBox.Close).setText(_("Fermer"))
        bb.rejected.connect(d.accept)
        v.addWidget(bb)
        d.exec()
        self._maj_lieux()
        if self.racines() != avant:
            self.mettre_a_jour()

    # ---------------------------------------------------------------- index
    def mettre_a_jour(self):
        if self.tache and self.tache.isRunning():
            return
        self.tache = TacheIndex(self.params, self.racines())
        self.tache.etat.connect(self.etat.setText)
        self.tache.fini.connect(lambda n: self.etat.setText(_("Index à jour : {n} PDF.", n=n)))
        self.fenetre.taches.append(self.tache)
        self.etat.setText(_("Mise à jour de l'index..."))
        self.tache.start()

    def done(self, r):
        if self.tache and self.tache.isRunning():
            self.tache.stop = True
            self.tache.wait(5000)
        super().done(r)

    # ---------------------------------------------------------------- recherche
    def chercher(self):
        from moteur.index import Index
        q = self.question.text().strip()
        if not q:
            return
        try:
            from .dialogues_ia import executer
            c = executer(self, _("L'IA lit votre question..."), lambda: criteres(self.params, q, self.avec_ia.isChecked())) \
                if self.avec_ia.isChecked() else criteres(self.params, q, False)
        except Exception as e:
            self.etat.setText(_("IA indisponible ({e}) : recherche par mots.", e=str(e)[:80]))
            c = criteres(self.params, q, False)
        ix = Index(chemin_index())
        try:
            res = ix.chercher(c["mots"], c["expediteur"], c["date_debut"], c["date_fin"])
            if not res and (c["expediteur"] or c["date_debut"]):        # trop strict : on elargit
                res = ix.chercher(c["mots"] + ([c["expediteur"]] if c["expediteur"] else []))
        finally:
            ix.fermer()
        morceaux = []
        if c["mots"]:
            morceaux.append(_("mots : {m}", m=", ".join(c["mots"])))
        if c["expediteur"]:
            morceaux.append(_("expéditeur : {e}", e=c["expediteur"]))
        if c["date_debut"] or c["date_fin"]:
            morceaux.append(_("du {d} au {f}", d=_jour(c["date_debut"]) or "…", f=_jour(c["date_fin"]) or "…"))
        self.criteres.setText(_("Recherché — {c}. {n} résultat(s).", c=" ; ".join(morceaux) or q, n=len(res)))
        self.resultats = res
        self._reclasser()
        return res

    def _lieu(self, chemin):
        """(racine affichee, [sous-dossiers], nom) d'un resultat, par rapport aux emplacements de recherche."""
        if chemin.startswith("distant:"):
            from . import distant
            _p, cid, ch = chemin.split(":", 2)
            cpt = next((x for x in self.params.get("comptes", []) if x["id"] == cid), None)
            parts = [x for x in ch.replace("\\", "/").split("/") if x]
            return (distant.libelle(cpt) if cpt else "?"), parts[:-1], parts[-1] if parts else ch
        n = os.path.normpath(chemin)
        meilleur = None
        for r in self.racines():
            if r["genre"] == "local":
                base = os.path.normpath(r["chemin"])
                if n.lower().startswith(base.lower() + os.sep) and (not meilleur or len(base) > len(meilleur)):
                    meilleur = base
        if meilleur:
            rel = n[len(meilleur) + 1:].split(os.sep)
            return meilleur, rel[:-1], rel[-1]
        return os.path.dirname(n), [], os.path.basename(n)

    def _feuille(self, parent, r):
        it = QTreeWidgetItem(parent, [r["nom"] + ("\n" + r["extrait"][:200] if r.get("extrait") else ""),
                                      _jour(r["date"]) if r.get("date") else ""])
        it.setIcon(0, icone("creer", "#c9252d"))
        it.setToolTip(0, r["chemin"])
        it.setData(0, Qt.UserRole, r["chemin"])
        return it

    def _reclasser(self, *_a):
        """Par dossier : arbre emplacement > sous-dossiers > fichiers, par ordre alphabetique ; ou liste par
        pertinence ou par date."""
        mode = self.classement.currentData()
        if self.params.get("recherche_classement") != mode:
            self.params["recherche_classement"] = mode
            self.params.enregistrer()
        t = self.liste
        t.clear()
        res = list(getattr(self, "resultats", []) or [])
        if mode != "dossier":
            if mode == "date":
                res.sort(key=lambda r: r.get("date") or "", reverse=True)
            t.setRootIsDecorated(False)
            for r in res:
                it = self._feuille(t, r)
                racine, sous, _n = self._lieu(r["chemin"])
                it.setToolTip(0, os.path.join(racine, *sous))
            return
        t.setRootIsDecorated(True)
        arbre = {}
        for r in res:
            racine, sous, nom = self._lieu(r["chemin"])
            noeud = arbre.setdefault(racine, {"_f": [], "_d": {}})
            for s_ in sous:
                noeud = noeud["_d"].setdefault(s_, {"_f": [], "_d": {}})
            noeud["_f"].append(r)

        def compter(n):
            return len(n["_f"]) + sum(compter(x) for x in n["_d"].values())

        def poser(parent, n):
            for nom_d in sorted(n["_d"], key=str.lower):            # sous-dossiers d'abord, puis les fichiers
                sd = n["_d"][nom_d]
                it = QTreeWidgetItem(parent, [f"{nom_d}  ({compter(sd)})", ""])
                it.setIcon(0, icone("ouvrir", "#c8a000"))
                poser(it, sd)
            for r in sorted(n["_f"], key=lambda r: r["nom"].lower()):
                self._feuille(parent, r)
        for racine in sorted(arbre, key=str.lower):
            it = QTreeWidgetItem(t, [f"{racine}  ({compter(arbre[racine])})", ""])
            it.setIcon(0, icone("ouvrir", "#c8a000"))
            f = it.font(0)
            f.setBold(True)
            it.setFont(0, f)
            poser(it, arbre[racine])
        t.expandToDepth(0 if len(res) > 30 else 3)

    def ouvrir(self, it):
        c = it.data(0, Qt.UserRole)
        if not c:                                    # un dossier : on le deplie
            it.setExpanded(not it.isExpanded())
            return
        if c.startswith("distant:"):
            _p, cid, ch = c.split(":", 2)
            self.fenetre.ouvrir_distant(cid, ch)
        else:
            self.fenetre.ouvrir(c)


def _jour(iso):
    try:
        return datetime.date.fromisoformat(iso[:10]).strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return ""
