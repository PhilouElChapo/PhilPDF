"""Boite aux lettres de PhilPDF sur un emplacement de synchronisation : Drive « en direct » (sans l'application de
bureau), NAS (Synology, WebDAV), FTP ou dossier reseau. Le dossier PhilPDF est cree dans le dossier du compte.

Le dossier PhilPDF du Drive (session, correspondances, preferences, sauvegarde des tampons et signatures)
est recopie dans un dossier miroir local ; le reste de PhilPDF lit et ecrit ce miroir comme un dossier
synchronise ordinaire. synchroniser() rapproche les deux, dans les deux sens :
  - fichier modifie d'un seul cote : il est recopie de l'autre ;
  - fichier modifie des deux cotes : les fichiers JSON sont fusionnes (chaque poste garde sa partie),
    les autres prennent la version la plus recente ;
  - fichier supprime d'un cote depuis la derniere synchro : supprime de l'autre.
"""
import json, os, posixpath, threading, time
from . import distant

_VERROU = threading.RLock()          # jamais deux synchros en meme temps (demarrage, minute, envoi immediat...)
RECEPTIONS = ("recevoir", "fusionner", "supprimer_ici")
# envois de routine (chaque minute, a la fermeture) : ce poste envoie ses changements ; la session et les reglages
# modifies des deux cotes sont fusionnes (chaque poste garde sa partie), sinon ils resteraient bloques
ENVOIS = {"envoyer", "fusionner:session.json", "fusionner:preferences.json"}

RACINE_DISTANTE = "/PhilPDF"


TEMPORAIRES = (".distant", ".tmp", ".part")


def journal(texte):
    try:
        from .journal import ecrire
        ecrire("synchro", texte)
    except Exception:
        pass


def racine_distante(compte):
    return posixpath.join(compte.get("dossier") or "/", "PhilPDF")


def libelle_compte(c):
    return distant.libelle(c)


def compte_drive(params):
    """Compte choisi comme emplacement de synchronisation (Drive en direct, NAS, FTP...), ou None."""
    cid = params.get("drive_compte")
    return next((c for c in params.get("comptes", []) if c["id"] == cid and c["type"] in distant.TYPES), None)


def dossier_miroir(compte):
    from .config import dossier_donnees
    d = os.path.join(dossier_donnees(), "miroir", compte["id"])
    os.makedirs(os.path.join(d, "PhilPDF"), exist_ok=True)
    return d


def _date(v):
    return (v.get("maj") or v.get("date") or "") if isinstance(v, dict) else ""


def _empreinte(chemin):
    import hashlib
    h = hashlib.sha1()
    with open(chemin, "rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


# listes fusionnees element par element (aucune ne remplace l'autre) : cle de l'element, liste des retraits voulus
UNIONS = {"identites": ("id", "identites_supprimees"), "certificats_approuves": ("empreinte", "certificats_retires")}


def unir(cle, local, autre, retires=()):
    """Union de deux listes d'elements (identites, certificats) : ceux des deux postes, sauf ceux retires
    expres ; pour un meme element, celui d'ici gagne, sauf s'il n'est qu'une identite a deverrouiller."""
    champ = UNIONS[cle][0]
    out, ordre = {}, []
    for x in list(autre or []) + list(local or []):
        if not isinstance(x, dict) or not x.get(champ):
            continue
        k = x[champ]
        if k not in out:
            ordre.append(k)
        if k in out and x.get("orpheline") and not out[k].get("orpheline"):
            continue
        out[k] = x
    retires = set(retires or ())
    return [out[k] for k in ordre if k not in retires]


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
        elif k in UNIONS and isinstance(v, list) and isinstance(w, list):
            out[k] = unir(k, v, w)
        elif k in ("identites_supprimees", "certificats_retires") and isinstance(v, list) and isinstance(w, list):
            out[k] = sorted(set(v) | set(w))
        elif isinstance(v, dict) and isinstance(w, dict):
            if _date(v) or _date(w):
                out[k] = v if _date(v) >= _date(w) else w
            else:
                out[k] = _fusion(v, w)
        else:
            out[k] = v
    for k, (_c, ret) in UNIONS.items():                 # retraits voulus : appliques apres la fusion
        if isinstance(out.get(k), list) and out.get(ret):
            out[k] = unir(k, out[k], [], out[ret])
    return out


def planifier(params, compte=None, emplacement=None):
    """Ce que ferait la synchronisation, sans rien changer : [{rel, action, taille, date}].
    action : « recevoir », « envoyer », « fusionner » (modifie des deux cotes) ou « supprimer_ici »."""
    plan = []
    synchroniser(params, compte, emplacement, plan=plan)
    return plan


def synchroniser(params, compte=None, emplacement=None, choix=None, sens=None, plan=None):
    """Renvoie (recus, envoyes). Leve distant.ErreurDistant si le Drive est injoignable.
    choix : ensemble des fichiers (rel) a traiter, None = tous ; sens : actions permises (ex. {"envoyer"}), None = toutes ;
    ce qui n'est pas traite reste en attente pour la fois suivante. plan : liste a remplir sans rien faire."""
    compte = compte or compte_drive(params)
    if not compte:
        return 0, 0
    with _VERROU:
        return _synchroniser(params, compte, emplacement, choix, sens, plan)


def _synchroniser(params, compte, emplacement, choix, sens, plan):
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
    RACINE_DISTANTE = racine_distante(compte)

    def local_de(rel):
        return os.path.join(local_racine, *rel.split("/"))

    def parcourir(rel_dossier):
        nonlocal recus, envoyes
        distants = e.modifies(posixpath.join(RACINE_DISTANTE, rel_dossier) if rel_dossier else RACINE_DISTANTE)
        ld = local_de(rel_dossier) if rel_dossier else local_racine
        os.makedirs(ld, exist_ok=True)
        locaux = {n for n in os.listdir(ld)}
        for nom in sorted(set(distants) | locaux):
            if nom.endswith(TEMPORAIRES):            # restes d'un transfert interrompu : jamais envoyes ni recus
                if nom in locaux and nom not in distants:
                    try:
                        os.remove(local_de(f"{rel_dossier}/{nom}" if rel_dossier else nom))
                    except OSError:
                        pass
                continue
            rel = f"{rel_dossier}/{nom}" if rel_dossier else nom
            lp = local_de(rel)
            dp = posixpath.join(RACINE_DISTANTE, rel)
            d = distants.get(nom)
            if (d and d[2]) or (not d and os.path.isdir(lp)):
                parcourir(rel)               # les dossiers manquants sur le Drive sont crees au premier envoi
                continue
            avant = etat.get(rel, {})
            l_mtime = os.path.getmtime(lp) if os.path.exists(lp) else None
            # l'heure seule ne suffit pas (horloge des fichiers grossiere sous Windows) : on compare aussi l'empreinte
            # l'empreinte decide : un fichier reecrit a l'identique (heure changee) n'est pas un changement
            local_modifie = l_mtime is not None and _empreinte(lp) != avant.get("empreinte")
            distant_modifie = d is not None and d[1] != avant.get("distant")
            if d is None and l_mtime is None:
                continue
            # decision
            if d is None:
                action = "supprimer_ici" if (avant.get("distant") and not local_modifie) else "envoyer"
            elif l_mtime is None:
                action = None if (avant.get("local") and not distant_modifie) else "recevoir"
            elif local_modifie and distant_modifie:
                action = "fusionner" if nom.endswith(".json") else "recevoir"
            elif distant_modifie:
                action = "recevoir"
            elif local_modifie:
                action = "envoyer"
            else:
                action = None
            if action and (plan is not None or (choix is not None and rel not in choix) or (sens is not None and action not in sens and f"{action}:{rel}" not in sens)):
                if plan is not None:
                    plan.append({"rel": rel, "action": action, "taille": (d[0] if d else (os.path.getsize(lp) if l_mtime else 0)),
                                 "date": d[1] if d else ""})
                if avant:
                    nouvel_etat[rel] = avant                # en attente : propose a nouveau la prochaine fois
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
            elif local_modifie and distant_modifie:         # conflit : les deux postes ont change ce fichier
                tmp = lp + ".distant"
                try:
                    e.telecharger(dp, tmp)
                except Exception:
                    if os.path.exists(tmp):
                        os.remove(tmp)                      # telechargement coupe : on ne touche a rien, on reessaiera
                    raise
                try:
                    attendu = int(d[0] or 0)
                except (TypeError, ValueError):
                    attendu = 0
                if attendu and os.path.getsize(tmp) == 0:      # copie du Drive recue vide : on ne decide rien
                    os.remove(tmp)
                    journal(f"conflit sur {rel} : copie du Drive reçue vide ({attendu} octets attendus), on réessaiera")
                    if avant:
                        nouvel_etat[rel] = avant
                    continue
                if nom.endswith(".json"):
                    try:
                        with open(lp, encoding="utf-8") as f:
                            a = json.load(f)
                        with open(tmp, encoding="utf-8") as f:
                            b = json.load(f)
                    except (OSError, ValueError):
                        # fusion impossible : on garde la version du Drive (celle de l'autre poste), jamais l'inverse
                        os.replace(tmp, lp)
                        journal(f"conflit sur {rel} : fusion impossible, version du Drive gardée")
                        recus += 1
                    else:
                        with open(lp, "w", encoding="utf-8") as f:
                            json.dump(_fusion(a, b), f, ensure_ascii=False, indent=1)
                        os.remove(tmp)
                        e.envoyer(lp, dp)
                        journal(f"conflit sur {rel} : les deux versions fusionnées")
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
                nouvel_etat[rel] = {"local": os.path.getmtime(lp), "empreinte": _empreinte(lp), "distant": (d or (0, None))[1]}

    parcourir("")
    if plan is not None:
        return 0, 0
    with open(chemin_etat, "w", encoding="utf-8") as f:
        json.dump(nouvel_etat, f, indent=1)
    journal(f"synchro {libelle_compte(compte)} : dossier local {local_racine} ↔ {RACINE_DISTANTE} ; "
            f"{recus} reçu(s), {envoyes} envoyé(s), {len(nouvel_etat)} fichier(s) suivis")
    try:                                               # photo du compte pour son icone (une fois)
        from . import avatars
        if avatars.photo_a_demander(compte):
            avatars.recuperer_photo(compte, e)
    except Exception:
        pass
    return recus, envoyes
