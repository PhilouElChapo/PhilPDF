"""Fractionner un PDF en plusieurs fichiers : toutes les N pages, a chaque signet, par taille maximale, ou selon
des plages ecrites a la main (« 1-3, 4-10, 11- »). On calcule d'abord le plan (quelles pages, quel nom), montre a
l'utilisateur, puis on ecrit les fichiers sans jamais en ecraser un existant sans le dire."""
import os
import re

import pymupdf as fitz

INTERDITS = r'<>:"/\|?*'


def nom_propre(t, defaut="Partie"):
    t = "".join("" if c == ":" else "-" if c in INTERDITS else c for c in (t or "")).strip(" .")
    t = re.sub(r"\s+", " ", t)
    return t[:90] or defaut


def par_nombre(nb_pages, n):
    """[[pages]] par paquets de n pages."""
    n = max(1, int(n))
    return [list(range(i, min(i + n, nb_pages))) for i in range(0, nb_pages, n)]


def par_plages(nb_pages, texte):
    """« 1-3, 4-10, 11- » -> [[0,1,2], [3..9], [10..fin]] ; leve ValueError si une plage est fausse."""
    parts = []
    for morceau in re.split(r"[;,]", texte or ""):
        m = morceau.strip()
        if not m:
            continue
        r = re.fullmatch(r"(\d*)\s*-\s*(\d*)|(\d+)", m)
        if not r:
            raise ValueError(m)
        if r.group(3):
            a = b = int(r.group(3))
        else:
            a = int(r.group(1) or 1)
            b = int(r.group(2) or nb_pages)
        if a < 1 or b > nb_pages or a > b:
            raise ValueError(m)
        parts.append(list(range(a - 1, b)))
    if not parts:
        raise ValueError(texte)
    return parts


def par_signets(doc, niveau=1):
    """[(titre, [pages])] : un fichier par signet du niveau choisi (les pages avant le premier signet vont avec lui)."""
    toc = [(lvl, t, p) for lvl, t, p, *_ in doc.get_toc(simple=False) if lvl <= niveau and p and p > 0]
    if not toc:
        return []
    debuts = []
    for _lvl, t, p in toc:
        if debuts and debuts[-1][1] == p - 1:
            continue                                  # deux signets sur la meme page : un seul fichier
        debuts.append((t, p - 1))
    out = []
    for i, (t, d) in enumerate(debuts):
        d0 = 0 if i == 0 else d
        f = debuts[i + 1][1] if i + 1 < len(debuts) else len(doc)
        if f > d0:
            out.append((t, list(range(d0, f))))
    return out


def _poids(doc, pages):
    d = fitz.open()
    d.insert_pdf(doc, from_page=pages[0], to_page=pages[-1])
    return len(d.tobytes(garbage=3, deflate=True))


def par_taille(doc, max_octets, suivi=None):
    """[[pages]] : chaque fichier sous max_octets (une page plus lourde a elle seule fait un fichier a part)."""
    # poids de chaque page seule (les ressources partagees sont comptees plusieurs fois : estimation prudente),
    # paquets faits sur cette estimation, puis chaque paquet est verifie et recoupe s'il depasse quand meme
    poids = []
    for n in range(len(doc)):
        if suivi:
            suivi(n, len(doc))
        poids.append(_poids(doc, [n]))
    parts, cour, tot = [], [], 0
    for n, w in enumerate(poids):
        if cour and tot + w > max_octets:
            parts.append(cour)
            cour, tot = [], 0
        cour.append(n)
        tot += w
    if cour:
        parts.append(cour)

    def verifier(p):
        if len(p) == 1 or _poids(doc, p) <= max_octets:
            return [p]
        m = len(p) // 2
        return verifier(p[:m]) + verifier(p[m:])
    parts = [q for p in parts for q in verifier(p)]
    fusion = [parts[0]] if parts else []                # l'estimation est prudente : on regroupe ce qui tient
    for p in parts[1:]:
        if _poids(doc, fusion[-1] + p) <= max_octets:
            fusion[-1] = fusion[-1] + p
        else:
            fusion.append(p)
    return fusion


def plan(doc, base, mode, valeur, suivi=None):
    """[(nom de fichier, [pages])]. base : nom du document sans .pdf."""
    nb = len(doc)
    if mode == "nombre":
        groupes = [(None, g) for g in par_nombre(nb, valeur)]
    elif mode == "plages":
        groupes = [(None, g) for g in par_plages(nb, valeur)]
    elif mode == "signets":
        groupes = par_signets(doc, int(valeur or 1))
    elif mode == "taille":
        groupes = [(None, g) for g in par_taille(doc, float(valeur) * 1048576, suivi)]
    else:
        raise ValueError(mode)
    out, vus = [], set()
    larg = len(str(len(groupes)))
    for i, (titre, pages) in enumerate(groupes, 1):
        if titre:
            nom = f"{i:0{larg}d} - {nom_propre(titre)}"
        else:
            nom = f"{base} - partie {i:0{larg}d}"
        while nom.lower() in vus:
            nom += "_"
        vus.add(nom.lower())
        out.append((nom + ".pdf", pages))
    return out


def libre(chemin):
    """chemin, ou « nom (2).pdf », « nom (3).pdf »... s'il existe deja."""
    if not os.path.exists(chemin):
        return chemin
    b, e = os.path.splitext(chemin)
    i = 2
    while os.path.exists(f"{b} ({i}){e}"):
        i += 1
    return f"{b} ({i}){e}"


def ecrire(doc, dossier, morceaux, remplacer=False):
    """Ecrit chaque morceau [(nom, pages)] ; renvoie les chemins ecrits. Les signets suivent dans chaque fichier."""
    os.makedirs(dossier, exist_ok=True)
    toc = doc.get_toc(simple=True)
    faits = []
    for nom, pages in morceaux:
        d = fitz.open()
        d.insert_pdf(doc, from_page=pages[0], to_page=pages[-1])
        sous = [[l, t, p - pages[0]] for l, t, p in toc if pages[0] < p <= pages[-1] + 1]
        if sous:
            m = min(l for l, *_ in sous)
            sous = [[l - m + 1, t, p] for l, t, p in sous]
            prec = 0
            ok = []
            for l, t, p in sous:                     # niveaux consecutifs, sinon PyMuPDF refuse
                l = min(l, prec + 1)
                ok.append([l, t, p])
                prec = l
            try:
                d.set_toc(ok)
            except Exception:                        # noqa: BLE001
                pass
        if doc.metadata:
            d.set_metadata({k: v for k, v in doc.metadata.items() if k in ("author", "subject", "keywords", "creator")})
        cible = os.path.join(dossier, nom)
        if not remplacer:
            cible = libre(cible)
        d.save(cible, garbage=3, deflate=True)
        faits.append(cible)
    return faits
