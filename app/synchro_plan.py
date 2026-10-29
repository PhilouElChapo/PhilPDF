"""Fenetre « Synchronisation » : ce qui va etre recu de vos autres postes et envoye depuis celui-ci, a cocher.

Rien n'est recu sans votre accord. Ce qui reste decoche n'est pas perdu : c'est propose a nouveau la fois suivante.
Les envois de ce poste sont coches d'avance (rien n'ecrase l'autre poste : les listes sont fusionnees).
"""
import datetime, json, os, posixpath, tempfile

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QHeaderView, QLabel, QPushButton, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout)

from .langue import _
from .icones import icone
from . import miroir, distant

# fichiers dont l'envoi seul ne merite pas d'ouvrir la fenetre (ils changent a chaque utilisation)
ROUTINE = ("session.json", "preferences.json")


def date_locale(texte):
    """Date du Drive (ISO, souvent UTC) -> '27/10 à 12h00' en heure locale ; '' si illisible."""
    if not texte:
        return ""
    t = str(texte).split("|")[0].strip()
    try:
        d = datetime.datetime.fromisoformat(t.replace("Z", "+00:00"))
    except ValueError:
        return ""
    if d.tzinfo:
        d = d.astimezone().replace(tzinfo=None)
    from .session import date_fr
    return date_fr(d.isoformat(timespec="minutes"))


def merite_fenetre(lignes):
    """Faut-il ouvrir la fenetre ? Seulement s'il y a un vrai changement pour vous : tampons, signatures, reglages
    modifies sur un autre poste, mots de passe... Pas pour la routine (etat des autres postes, fichiers ouverts
    ailleurs — montres sur l'Accueil —, etat de ce poste envoye) : elle se fait sans rien demander."""
    return any(not l.get("routine") for l in lignes)


def _lire_json(chemin):
    try:
        with open(chemin, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _distant_json(e, compte, rel):
    """Petit JSON du Drive lu sans toucher au miroir (pour decrire ce qui va arriver)."""
    tmp = os.path.join(tempfile.mkdtemp(), "x.json")
    try:
        e.telecharger(posixpath.join(miroir.racine_distante(compte), rel), tmp)
        return _lire_json(tmp)
    except Exception:
        return None
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def _secrets_recus(params, e, compte):
    """Ce que le fichier chiffre du Drive apporte a ce poste ([] : rien), ou None si on ne peut pas le lire."""
    from . import coffre, reglages
    phrase = coffre.lire(reglages.PHRASE)
    if not phrase:
        return None
    tmp = os.path.join(tempfile.mkdtemp(), "s.philpdf")
    try:
        e.telecharger(posixpath.join(miroir.racine_distante(compte), "secrets.philpdf"), tmp)
        sec = reglages.importer(tmp, phrase).get("secrets", {})
        return [x["libelle"] for x in reglages.secrets_nouveaux(params, phrase, sec)]
    except Exception:
        return None
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def decrire(plan, params, compte=None, emplacement=None):
    """Plan brut -> lignes lisibles : [{rel, action, groupe, titre, detail, date, famille}]."""
    compte = compte or miroir.compte_drive(params)
    e = None
    local = os.path.join(miroir.dossier_miroir(compte), "PhilPDF") if compte else ""
    machine = params.get("machine", "")
    rels = {a["rel"]: a for a in plan}
    distants = {}

    def dist(rel):
        nonlocal e
        if rel not in distants:
            if e is None:
                e = emplacement or distant.emplacement(compte)
            distants[rel] = _distant_json(e, compte, rel)
        return distants[rel]

    # noms des tampons : index du Drive (pour ce qui arrive) et index local (pour ce qui part)
    idx_local = _lire_json(os.path.join(local, "sauvegarde", "index.json")) or {}
    noms = {x.get("id"): x for x in idx_local.get("elements", [])}
    if any(a["rel"].startswith("sauvegarde/") and a["action"] in miroir.RECEPTIONS for a in plan):
        idx_d = dist("sauvegarde/index.json") or {}
        for x in idx_d.get("elements", []):
            noms.setdefault(x.get("id"), x)
    else:
        idx_d = None
    out = []
    for a in plan:
        rel, act = a["rel"], a["action"]
        apercu = None
        recoit = act in miroir.RECEPTIONS
        # envois : seuls les nouveaux tampons, signatures et filigranes de ce poste meritent la fenetre ; le reste
        # (listes, reglages, apprentissage...) part sans rien demander, comme chaque minute
        routine = not recoit and not (rel.startswith("sauvegarde/") and rel != "sauvegarde/index.json")
        titre, detail, famille = rel, "", "autre"
        if rel == "preferences.json":
            famille = "reglages"
            titre = _("Réglages")
            if recoit:
                d = dist(rel) or {}
                c = d.get("communs") or {}
                par = c.get("par") or ""
                if par and par != machine:
                    detail = _("modifiés sur « {poste} » ({date}) ; vous choisirez ensuite réglage par réglage",
                               poste=par, date=date_locale(c.get("maj")) or "?")
                else:
                    detail = _("état de vos autres postes (rien ne change sur ce poste)")
                # toujours recu sans demander : rien n'est applique ici sans la fenetre « Réglages de vos autres
                # postes », ou chaque reglage se coche ou s'ignore (ignore = plus propose, sauf nouveau changement)
                routine = True
            else:
                detail = _("réglages et état de ce poste")
        elif rel == "session.json":
            famille = "session"
            titre = _("Fichiers ouverts")
            if recoit:
                d = dist(rel) or {}
                autres = [f"{m} : {len(v.get('fichiers', []))} ({date_locale(v.get('maj'))})"
                          for m, v in d.items() if m != machine and isinstance(v, dict)]
                detail = _("sur vos autres postes — {liste}", liste=", ".join(autres) or "—")
                routine = True                           # montres sur l'Accueil (bandeau une fois par changement)
            else:
                detail = _("fichiers ouverts sur ce poste (emplacements seulement)")
        elif rel == "secrets.philpdf":
            famille = "secrets"
            titre = _("Mots de passe et autorisations")
            detail = _("chiffrés par votre mot de passe principal")
            if recoit:
                nouveaux = _secrets_recus(params, e or emplacement or distant.emplacement(compte), compte)
                if nouveaux == []:
                    # rien de nouveau pour ce poste (l'autre poste a seulement reecrit les memes) : sans demander
                    detail = _("rien de nouveau pour ce poste")
                    routine = True
                elif nouveaux:
                    detail = _("nouveau pour ce poste : {x}", x=", ".join(nouveaux))
        elif rel == "indice_phrase.json":
            famille = "secrets"
            titre = _("Indice du mot de passe principal")
        elif rel == "sauvegarde/index.json":
            famille = "biblio"
            titre = _("Liste des tampons et signatures")
            if recoit and idx_d is not None:
                ici = {x.get("hash"): x for x in (idx_local.get("elements") or [])}
                la = {x.get("hash"): x for x in (idx_d.get("elements") or [])}
                nouveaux = [x["nom"] for h, x in la.items() if h not in ici]
                supp = [ici[h]["nom"] for h in (idx_d.get("supprimes") or []) if h in ici]
                modifs = [x["nom"] for h, x in la.items() if h in ici and (x.get("maj", "") > ici[h].get("maj", ""))]
                morceaux = []
                if nouveaux:
                    morceaux.append(_("nouveaux : {n}", n=", ".join(nouveaux)))
                if modifs:
                    morceaux.append(_("modifiés (nom, catégorie, date) : {n}", n=", ".join(modifs)))
                if supp:
                    morceaux.append(_("supprimés sur l'autre poste : {n}", n=", ".join(supp)))
                detail = " ; ".join(morceaux) or _("noms, catégories, tampon par défaut")
            else:
                detail = _("noms, catégories, tampon par défaut de ce poste")
        elif rel.startswith("sauvegarde/"):
            famille = "biblio"
            parts = rel.split("/")
            genre = parts[1] if len(parts) > 2 else ""
            ident = os.path.splitext(parts[-1])[0]
            x = noms.get(ident) or {}
            genres = {"tampons": _("Tampon"), "signatures": _("Signature"), "filigranes": _("Filigrane")}
            titre = _("{genre} « {nom} »", genre=genres.get(genre, genre), nom=x.get("nom") or ident)
            if x.get("categorie"):
                detail = _("catégorie {c}", c=x["categorie"])
            if rel.lower().endswith(".pdf"):
                try:
                    if recoit:
                        if e is None:
                            e = emplacement or distant.emplacement(compte)
                        tmp = os.path.join(tempfile.mkdtemp(prefix="philpdf-apercu-"), "a.pdf")
                        e.telecharger(posixpath.join(miroir.racine_distante(compte), rel), tmp)
                    else:
                        tmp = os.path.join(local, *rel.split("/"))
                    with open(tmp, "rb") as fh:
                        from moteur import objets
                        apercu = objets.apercu(fh.read(), 40)
                except Exception:                        # noqa: BLE001
                    apercu = None
        elif rel.startswith("apprentissage/"):
            famille = "apprentissage"
            titre = _("Apprentissage")
            detail = os.path.splitext(os.path.basename(rel))[0]
        if act == "fusionner":
            detail = (detail + " — " if detail else "") + _("modifié des deux côtés : les deux versions seront réunies")
        elif act == "supprimer_ici":
            detail = (detail + " — " if detail else "") + _("supprimé sur l'autre poste : sera retiré de la copie de ce poste")
        out.append({"rel": rel, "action": act, "groupe": "recevoir" if recoit else "envoyer", "titre": titre,
                    "detail": detail, "date": date_locale(a.get("date")) if recoit else "", "famille": famille,
                    "routine": routine, "apercu": apercu,
                    "reglages_ensuite": rel == "preferences.json" and recoit and "choisirez ensuite" in detail})
    return out


class DialoguePlan(QDialog):
    """Liste a cocher, en deux parties : recu de vos autres postes / envoye depuis ce poste."""

    def __init__(self, parent, lignes, lieu, icone_compte=None):
        self._routine = {l["rel"] for l in lignes if l.get("routine")}
        super().__init__(parent)
        self.setWindowTitle(_("Synchronisation avec {lieu}", lieu=lieu))
        self.resize(900, 560)
        v = QVBoxLayout(self)
        h = QHBoxLayout()
        if icone_compte is not None:
            ic = QLabel()
            ic.setPixmap(icone_compte.pixmap(36, 36))
            h.addWidget(ic, 0, Qt.AlignTop)
        ensuite = any(l.get("reglages_ensuite") for l in lignes)
        lb = QLabel(_("<b>Voici ce qui va être fait si vous cliquez « Synchroniser la sélection ».</b><br>"
                      "• <b>Recevoir</b> : ce qui est coché est copié sur ce poste (tampons, signatures, mots de passe...)."
                      "<br>• <b>Envoyer</b> : ce qui est coché part vers vos autres postes ; rien n'y est écrasé, les "
                      "listes sont réunies.<br>• Ce qui reste <b>décoché</b> n'est pas perdu : ce sera proposé à la "
                      "prochaine synchronisation. « Plus tard » : rien n'est fait maintenant.") +
                    ("<br><br>" + _("<b>Ensuite</b>, une deuxième fenêtre « Réglages de vos autres postes » vous "
                                    "montrera les réglages modifiés ailleurs, un par un, à reprendre ou non.")
                     if ensuite else ""))
        lb.setWordWrap(True)
        h.addWidget(lb, 1)
        v.addLayout(h)
        t = self.arbre = QTreeWidget()
        t.setColumnCount(2)
        t.setHeaderLabels([_("Elément"), _("Modifié le")])
        t.setRootIsDecorated(True)
        from PySide6.QtCore import QSize
        t.setIconSize(QSize(64, 40))
        t.setWordWrap(True)
        t.setUniformRowHeights(False)
        hh = t.header()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setStretchLastSection(False)
        familles = {"biblio": _("Tampons et signatures"), "apprentissage": _("Apprentissage (OCR, classement)")}
        for groupe, titre_g, ic in (("recevoir", _("Recevoir de vos autres postes"), "mise_a_jour"),
                                    ("envoyer", _("Envoyer depuis ce poste"), "exporter")):
            ls = [l for l in lignes if l["groupe"] == groupe and not l.get("routine")]
            if not ls:
                continue
            g = QTreeWidgetItem(t, [f"{titre_g} ({len(ls)})"])
            g.setIcon(0, icone(ic, "#2b6cb0"))
            g.setFlags(g.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsAutoTristate)
            f = g.font(0)
            f.setBold(True)
            g.setFont(0, f)
            sous = {}
            for l in ls:
                parent = g
                if l["famille"] in familles and sum(1 for x in ls if x["famille"] == l["famille"]) > 1:
                    if l["famille"] not in sous:
                        s = QTreeWidgetItem(g, [familles[l["famille"]]])
                        s.setFlags(s.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsAutoTristate)
                        sous[l["famille"]] = s
                    parent = sous[l["famille"]]
                import textwrap
                detail = "\n".join(textwrap.wrap(l["detail"], 95)) if l["detail"] else ""
                it = QTreeWidgetItem(parent, [l["titre"] + ("\n" + detail if detail else ""), l["date"]])
                it.setToolTip(0, l["detail"])
                if l.get("apercu"):
                    from PySide6.QtGui import QPixmap, QIcon
                    pm = QPixmap()
                    pm.loadFromData(l["apercu"])
                    it.setIcon(0, QIcon(pm))
                it.setForeground(1, Qt.darkGray)
                it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
                it.setCheckState(0, Qt.Checked)
                it.setData(0, Qt.UserRole, l["rel"])
            g.setExpanded(True)
            for s in sous.values():
                s.setExpanded(s.childCount() <= 8)
        v.addWidget(t, 1)
        hb = QHBoxLayout()
        for txt, etat in ((_("Tout cocher"), Qt.Checked), (_("Tout décocher"), Qt.Unchecked)):
            b = QPushButton(txt)
            b.clicked.connect(lambda _c=False, e=etat: [t.topLevelItem(i).setCheckState(0, e) for i in range(t.topLevelItemCount())])
            hb.addWidget(b)
        hb.addStretch(1)
        b_tard = QPushButton(_("Plus tard"))
        b_tard.setToolTip(_("Rien n'est fait maintenant ; ce sera proposé à la prochaine synchronisation."))
        b_ok = QPushButton(icone("synchro", "#ffffff"), _(" Synchroniser la sélection"))
        b_ok.setDefault(True)
        b_ok.setStyleSheet("QPushButton{background:#2b6cb0;color:#fff;border:none;border-radius:6px;padding:7px 14px;font-weight:600}")
        hb.addWidget(b_tard)
        hb.addWidget(b_ok)
        v.addLayout(hb)
        b_tard.clicked.connect(self.reject)
        b_ok.clicked.connect(self.accept)

    def choisis(self):
        out = set(self._routine)                          # la routine (non montree) se fait toujours

        def tour(it):
            for i in range(it.childCount()):
                c = it.child(i)
                r = c.data(0, Qt.UserRole)
                if r and c.checkState(0) == Qt.Checked:
                    out.add(r)
                tour(c)
        for i in range(self.arbre.topLevelItemCount()):
            tour(self.arbre.topLevelItem(i))
        return out
