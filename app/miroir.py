"""Boite aux lettres de PhilPDF sur un Drive « en direct » (sans l'application de bureau du Drive).

Le dossier PhilPDF du Drive (session, correspondances, preferences, sauvegarde des tampons et signatures)
est recopie dans un dossier miroir local ; le reste de PhilPDF lit et ecrit ce miroir comme un dossier
synchronise ordinaire. synchroniser() rapproche les deux, dans les deux sens :
  - fichier modifie d'un seul cote : il est recopie de l'autre ;
  - fichier modifie des deux cotes : les fichiers JSON sont fusionnes (chaque poste garde sa partie),
    les autres prennent la version la plus recente ;
  - fichier supprime d'un cote depuis la derniere synchro : supprime de l'autre.
"""
import json, os, posixpath, time
from . import distant

RACINE_DISTANTE = "/PhilPDF"


def compte_drive(params):
    cid = params.get("drive_compte")
    return next((c for c in params.get("comptes", []) if c["id"] == cid and c["type"] in distant.NUAGES), None)


def dossier_miroir(compte):
    from .config import dossier_donnees
    d = os.path.join(dossier_donnees(), "miroir", compte["id"])
    os.makedirs(os.path.join(d, "PhilPDF"), exist_ok=True)
    return d


def _date(v):
    return (v.get("maj") or v.get("date") or "") if isinstance(v, dict) else ""


def _fusion(local, dist):
    """Fusion de deux JSON : union des clefs ; conflit -> la valeur la plus recente (champ maj/date),
    dictionnaires sans date fusionnes recursivement, listes « supprimes » et « elements » reunies."""
    if not isinstance(local, dict) or not isinstance(dist, dict):
        return local
    out = dict(dist)
    for k, v in local.items():
        w = dist.get(k)
        if w is None:
            out[k] = v
        elif k == "supprimes" and isinstance(v, list) and isinstance(w, list):
            out[k] = sorted(set(v) | set(w))
        elif k == "elements" and isinstance(v, list) and isinstance(w, list):
            vus = {}
            for x in w + v:
                vus[x.get("hash") or x.get("id")] = x
            out[k] = list(vus.values())
        elif isinstance(v, dict) and isinstance(w, dict):
            if _date(v) or _date(w):
                out[k] = v if _date(v) >= _date(w) else w
            else:
                out[k] = _fusion(v, w)
        else:
            out[k] = v
    return out


def synchroniser(params, compte=None, emplacement=None):
    """Renvoie (recus, envoyes). Leve distant.ErreurDistant si le Drive est injoignable."""
    compte = compte or compte_drive(params)
    if not compte:
        return 0, 0
    e = emplacement or distant.emplacement(compte)
    base = dossier_miroir(compte)
    local_racine = os.path.join(base, "PhilPDF")
    chemin_etat = os.path.join(base, "etat.json")
    try:
        with open(chemin_etat, encoding="utf-8") as f:
            etat = json.load(f)
    except (OSError, ValueError):
        etat = {}
    nouvel_etat, recus, envoyes = {}, 0, 0

    def local_de(rel):
        return os.path.join(local_racine, *rel.split("/"))

    def parcourir(rel_dossier):
        nonlocal recus, envoyes
        distants = e.modifies(posixpath.join(RACINE_DISTANTE, rel_dossier) if rel_dossier else RACINE_DISTANTE)
        ld = local_de(rel_dossier) if rel_dossier else local_racine
        os.makedirs(ld, exist_ok=True)
        locaux = {n for n in os.listdir(ld)}
        for nom in sorted(set(distants) | locaux):
            rel = f"{rel_dossier}/{nom}" if rel_dossier else nom
            lp = local_de(rel)
            dp = posixpath.join(RACINE_DISTANTE, rel)
            d = distants.get(nom)
            if (d and d[2]) or (not d and os.path.isdir(lp)):
                parcourir(rel)               # les dossiers manquants sur le Drive sont crees au premier envoi
                continue
            avant = etat.get(rel, {})
            l_mtime = os.path.getmtime(lp) if os.path.exists(lp) else None
            local_modifie = l_mtime is not None and l_mtime != avant.get("local")
            distant_modifie = d is not None and d[1] != avant.get("distant")
            if d is None and l_mtime is None:
                continue
            envoye = False
            if d is None:                                   # absent du Drive
                if avant.get("distant") and not local_modifie:
                    os.remove(lp)                           # supprime ailleurs
                    continue
                e.envoyer(lp, dp)
                envoyes += 1
                envoye = True
            elif l_mtime is None:                           # absent ici
                if avant.get("local") and not distant_modifie:
                    continue                                # supprime ici : on laisse (pas de suppression distante)
                e.telecharger(dp, lp)
                recus += 1
            elif local_modifie and distant_modifie:         # conflit
                tmp = lp + ".distant"
                e.telecharger(dp, tmp)
                if nom.endswith(".json"):
                    try:
                        with open(lp, encoding="utf-8") as f:
                            a = json.load(f)
                        with open(tmp, encoding="utf-8") as f:
                            b = json.load(f)
                        with open(lp, "w", encoding="utf-8") as f:
                            json.dump(_fusion(a, b), f, ensure_ascii=False, indent=1)
                    except (OSError, ValueError):
                        pass
                    os.remove(tmp)
                    e.envoyer(lp, dp)
                    envoyes += 1
                    envoye = True
                    recus += 1
                else:
                    os.replace(tmp, lp)
                    recus += 1
            elif distant_modifie:
                e.telecharger(dp, lp)
                recus += 1
            elif local_modifie:
                e.envoyer(lp, dp)
                envoyes += 1
                envoye = True
            # etat apres synchro
            if envoye:
                d = e.modifies(posixpath.dirname(dp)).get(nom) or d
            if os.path.exists(lp):
                nouvel_etat[rel] = {"local": os.path.getmtime(lp), "distant": (d or (0, None))[1]}

    parcourir("")
    with open(chemin_etat, "w", encoding="utf-8") as f:
        json.dump(nouvel_etat, f, indent=1)
    return recus, envoyes
