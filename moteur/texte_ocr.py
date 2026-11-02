"""Modifier le texte d'un scan (texte reconnu par l'OCR).

Sur une page scannee, ce qu'on voit est l'image ; le texte reconnu est pose dessus, invisible. Modifier ce texte comme
un texte ordinaire ne change donc rien a l'ecran. Ici, comme Acrobat :
- les lettres de l'image sont effacees sous la ligne (remplies avec la couleur du fond du scan) ;
- le nouveau texte est ecrit, visible, a la meme place ;
- sa police est choisie en comparant l'image des lettres a chaque police (avec ou sans empattements, normale ou
  grasse), sa taille et sa couleur sont celles des lettres de l'image.
"""
import numpy as np
import pymupdf as fitz

ZOOM = 4
MARGE = 1.2


def est_ocr(lignes):
    """Vrai si toutes les lettres des lignes sont invisibles (texte reconnu pose sur une image)."""
    vis = [sp for l in lignes for c, sp in l["chars"] if c["c"].strip()]
    return bool(vis) and all(sp.get("alpha", 255) == 0 for sp in vis)


def _candidats():
    from .modifier import CANDIDATS
    voulus = ("Liberation Sans", "Liberation Sans Bold", "Liberation Serif", "Liberation Serif Bold",
              "Liberation Mono", "Liberation Mono Bold", "Arial", "Arial Bold", "Times New Roman")
    vus, out = set(), []
    for n, f in CANDIDATS:
        if n in voulus and n not in vus:
            vus.add(n)
            out.append((n, f))
    return out


def _encre(page, zone):
    """(masque de l'encre, couleur de l'encre, couleur du fond) de l'image dans la zone (texte invisible exclu)."""
    pm = page.get_pixmap(clip=zone, matrix=fitz.Matrix(ZOOM, ZOOM), colorspace=fitz.csRGB, alpha=False, annots=False)
    rgb = np.frombuffer(pm.samples, np.uint8).reshape(pm.h, pm.w, 3).astype(np.int16)
    gris = rgb.mean(axis=2)
    seuil = min(160, (gris.min() + np.median(gris)) / 2 + 10)
    masque = gris < seuil
    fond = np.median(rgb[~masque], axis=0) / 255 if (~masque).any() else np.array([1.0, 1.0, 1.0])
    encre = np.median(rgb[masque], axis=0) / 255 if masque.any() else np.array([0.0, 0.0, 0.0])
    if encre.max() < 0.3:                              # noir de scan (gris fonce) : noir franc
        encre = np.array([0.0, 0.0, 0.0])
    if fond.min() > 0.85:
        fond = np.array([1.0, 1.0, 1.0])
    return masque, tuple(float(x) for x in encre), tuple(float(x) for x in fond)


def _boite(m):
    ys, xs = np.nonzero(m)
    if not len(ys):
        return None
    return xs.min(), ys.min(), xs.max() + 1, ys.max() + 1


def _ligne_de_base(masque, zone):
    """Ligne de base des lettres de l'image : bas de la bande de rangees la plus chargee d'encre (les jambages des
    p, q, g et les soulignements, peu charges ou separes, n'y comptent pas)."""
    prof = masque.sum(axis=1)
    if not prof.any():
        return None
    fort = prof >= 0.25 * prof.max()
    bandes, debut = [], None
    for i, f in enumerate(list(fort) + [False]):
        if f and debut is None:
            debut = i
        elif not f and debut is not None:
            bandes.append((int(prof[debut:i].sum()), debut, i))
            debut = None
    _poids, _d, fin = max(bandes)
    return zone.y0 + fin / ZOOM


def _rendu(zone, texte, fichier, taille, origine):
    tmp = fitz.open()
    pg = tmp.new_page(width=zone.x1 + 50, height=zone.y1 + 50)
    pg.insert_font(fontname="cand", fontfile=fichier)
    pg.insert_text(origine, texte, fontname="cand", fontsize=taille)
    pm = pg.get_pixmap(clip=zone, matrix=fitz.Matrix(ZOOM, ZOOM), colorspace=fitz.csGRAY, alpha=False)
    return np.frombuffer(pm.samples, np.uint8).reshape(pm.h, pm.w) < 128


def analyser_ligne(page, ligne):
    """Police, taille, origine (x, ligne de base), couleur, fond et zone a effacer d'une ligne du scan."""
    import cv2
    texte = "".join(c["c"] for c, _sp in ligne["chars"]).strip()
    r = fitz.Rect(ligne["rect"])
    zone = r + (-MARGE, -MARGE * 2, MARGE, MARGE * 2)
    masque, encre, fond = _encre(page, zone)
    # encre de la ligne seulement : les rangees de la ligne lue (une ligne voisine deborde dans la zone)
    h0 = int(round((r.y0 - 0.5 - zone.y0) * ZOOM))
    h1 = int(round((r.y1 + 0.5 - zone.y0) * ZOOM))
    seule = np.zeros_like(masque)
    seule[max(0, h0):h1] = masque[max(0, h0):h1]
    bi = _boite(seule)
    base = ligne["base"]
    x0 = ligne["x0"]
    taille0 = ligne["taille"]
    meilleur = None
    for nom, fichier in _candidats():
        f = fitz.Font(fontfile=fichier)
        lt = f.text_length(texte, fontsize=1) or 1
        s = (r.width / lt) if r.width > 2 else taille0         # meme largeur que la ligne lue
        b = _rendu(zone, texte, fichier, s, (x0, base))
        bc = _boite(b)
        if bi is None or bc is None:
            score = 0.0
        else:
            a = masque[bi[1]:bi[3], bi[0]:bi[2]].astype(np.uint8)
            c = b[bc[1]:bc[3], bc[0]:bc[2]].astype(np.uint8)
            c = cv2.resize(c, (a.shape[1], a.shape[0]), interpolation=cv2.INTER_NEAREST)
            score = float((a & c).sum()) / max(1.0, float((a | c).sum()))
        if meilleur is None or score > meilleur[0]:
            meilleur = (score, nom, fichier, s, bc)
    score, nom, fichier, s, bc = meilleur
    ox, oy = x0, base
    if bc is not None:                                 # debut des lettres : celui des mots lus
        ox = x0 + (r.x0 - (zone.x0 + bc[0] / ZOOM))
    lb = _ligne_de_base(seule, zone)
    if lb is not None and abs(lb - base) < r.height * 0.6:
        oy = lb                                        # bas de la plupart des lettres de l'image
    # zone effacee : des accents aux jambages, sur la largeur des mots (pas la ligne voisine, ni un filet proche)
    haut, bas = oy - s * 0.92, oy + s * 0.24
    efface = fitz.Rect(r.x0, haut, r.x1, bas)
    if bi is not None:
        efface |= fitz.Rect(zone.x0 + bi[0] / ZOOM, max(haut, zone.y0 + bi[1] / ZOOM),
                            zone.x0 + bi[2] / ZOOM, min(bas, zone.y0 + bi[3] / ZOOM))
    return {"police": nom, "fichier": fichier, "taille": s, "origine": fitz.Point(ox, oy), "couleur": encre,
            "fond": fond, "efface": efface + (-0.8, -0.5, 0.8, 0.5), "ressemblance": score}


def reecrire(doc, num_page, lignes, nouveau, taille=None, couleur=None, police=None, interligne=None):
    """Remplace le texte de ces lignes du scan par `nouveau` (une ligne par retour a la ligne).
    Renvoie (nombre de lignes ecrites, ligne de base de la derniere, journal)."""
    page = doc[num_page]
    infos = [analyser_ligne(page, l) for l in lignes]
    for i in infos:
        page.add_redact_annot(i["efface"], fill=i["fond"])
    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS, graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                          text=fitz.PDF_REDACT_TEXT_REMOVE)
    pas = interligne or ((infos[1]["origine"].y - infos[0]["origine"].y) if len(infos) > 1 else infos[0]["taille"] * 1.25)
    alias = {}
    y = infos[0]["origine"].y
    # retour a la ligne a la largeur des lignes d'origine (le paragraphe d'un scan arrive en un seul morceau)
    largeur = max(fitz.Rect(l["rect"]).x1 for l in lignes) - min(fitz.Rect(l["rect"]).x0 for l in lignes) + 2
    textes = []
    for morceau in nouveau.split("\n"):
        i = infos[min(len(textes), len(infos) - 1)]
        f = fitz.Font(fontfile=police or i["fichier"])
        t_ = taille or i["taille"]
        ligne = ""
        for mot in morceau.split(" "):
            essai = (ligne + " " + mot) if ligne else mot
            if ligne and len(lignes) > 1 and f.text_length(essai, fontsize=t_) > largeur:
                textes.append(ligne)
                ligne = mot
            else:
                ligne = essai
        textes.append(ligne)
    for k, t in enumerate(textes):
        i = infos[min(k, len(infos) - 1)]
        org = i["origine"] if k < len(infos) else fitz.Point(infos[-1]["origine"].x, y)
        y = org.y
        fichier = police or i["fichier"]
        if fichier not in alias:
            import hashlib
            alias[fichier] = "PhilScan" + hashlib.md5(fichier.encode("utf-8")).hexdigest()[:6]
            page.insert_font(fontname=alias[fichier], fontfile=fichier)
        if t.strip():
            page.insert_text(org, t, fontname=alias[fichier], fontsize=taille or i["taille"],
                             color=couleur or i["couleur"])
        y += pas
    journal = [f"texte du scan remplacé : lettres de l'image effacées, police {infos[0]['police']} "
               f"({infos[0]['taille']:.1f} pt)"]
    return len(textes), y - pas, journal
