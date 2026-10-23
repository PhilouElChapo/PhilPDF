"""Rechercher dans tous mes PDF : une question en francais, PhilPDF retrouve les documents.

Index sur ce poste (texte integral, date, expediteur), mis a jour en arriere-plan a chaque ouverture de la
fenetre. Avec une clef d'IA, la question est d'abord traduite en mots-clefs, expediteur et periode (seule la
question est envoyee a l'IA, jamais vos documents).
"""
import datetime, os, re

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QListWidget,
                               QListWidgetItem, QCheckBox, QFileDialog, QMenu)

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
        self.b_lieux = QPushButton(_("Où chercher..."))
        self.b_lieux.clicked.connect(self.menu_lieux)
        h.addWidget(self.b_lieux)
        b = QPushButton(icone("synchro", "#0f6cbd"), _(" Mettre à jour l'index"))
        b.clicked.connect(self.mettre_a_jour)
        h.addWidget(b)
        v.addLayout(h)
        self.criteres = QLabel()
        self.criteres.setStyleSheet("color:#555")
        self.criteres.setWordWrap(True)
        v.addWidget(self.criteres)
        self.liste = QListWidget()
        self.liste.setWordWrap(True)
        self.liste.itemDoubleClicked.connect(self.ouvrir)
        self.liste.setStyleSheet("QListWidget::item{padding:6px;border-bottom:1px solid #eee}")
        v.addWidget(self.liste, 1)
        self.etat = QLabel()
        self.etat.setStyleSheet("color:#777;font-size:12px")
        v.addWidget(self.etat)
        self.mettre_a_jour()

    # ---------------------------------------------------------------- lieux
    def racines(self):
        r = self.params.get("recherche_racines")
        return r if r else racines_par_defaut(self.params)

    def _enregistrer_racines(self, r):
        self.params["recherche_racines"] = r
        self.params.enregistrer()

    def menu_lieux(self):
        m = QMenu(self)
        actuelles = self.racines()
        for r in actuelles:
            a = m.addAction(icone("supprimer", "#a33"), _("Retirer : {lieu}", lieu=libelle_racine(r, self.params)))
            a.triggered.connect(lambda _c=False, r=r: self._enregistrer_racines([x for x in self.racines() if x != r]))
        m.addSeparator()
        a = m.addAction(icone("ouvrir", "#c8a000"), _("Ajouter un dossier de ce PC..."))
        a.triggered.connect(self._ajouter_dossier)
        for c in self.params.get("comptes", []):
            if not any(r.get("id") == c["id"] for r in actuelles):
                from . import distant
                a = m.addAction(icone("archiver", "#0f6cbd"), _("Ajouter : {lieu}", lieu=distant.libelle(c)))
                a.triggered.connect(lambda _c=False, c=c: self._enregistrer_racines(
                    self.racines() + [{"genre": "compte", "id": c["id"], "dossier": c.get("dossier") or "/"}]))
        m.exec(self.b_lieux.mapToGlobal(self.b_lieux.rect().bottomLeft()))

    def _ajouter_dossier(self):
        p = QFileDialog.getExistingDirectory(self, _("Où chercher"), self.fenetre.dossier_depart())
        if p:
            self._enregistrer_racines(self.racines() + [{"genre": "local", "chemin": p}])

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
        self.liste.clear()
        for r in res:
            lieu = r["chemin"]
            if lieu.startswith("distant:"):
                from . import distant
                _p, cid, ch = lieu.split(":", 2)
                cpt = next((x for x in self.params.get("comptes", []) if x["id"] == cid), None)
                lieu = f"{distant.libelle(cpt) if cpt else '?'} : {ch}"
            tete = r["nom"] + (f"   ·   {_jour(r['date'])}" if r["date"] else "")
            it = QListWidgetItem(icone("creer", "#c9252d"), f"{tete}\n{lieu}\n{r['extrait'][:220]}")
            it.setData(Qt.UserRole, r["chemin"])
            self.liste.addItem(it)
        self.resultats = res
        return res

    def ouvrir(self, it):
        c = it.data(Qt.UserRole)
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
