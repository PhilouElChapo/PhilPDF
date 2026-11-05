"""Lecture fluide (comme le « Mode liquide » d'Acrobat, et PhilPDF Android) : le texte de chaque page remis en
colonne, avec ses titres, paragraphes recousus, gras, italique et images ; numeros de page et titres courants laisses.
Le PDF n'est pas modifie. Resultat : du HTML simple pour un afficheur de texte."""
import base64
import html
import re
from collections import Counter

import pymupdf as fitz

PUCES = set("•▪◦·‣–—-*■□➢►✓")
NUMERO = re.compile(r"^(\d{1,3}|[a-zA-Z]|[ivxIVX]{1,4})[.)]\s")


def _gras(span):
    return bool(span["flags"] & 16) or bool(re.search(r"(?i)bold|black|heavy|semibold|demi", span.get("font", "")))


def _italique(span):
    return bool(span["flags"] & 2) or bool(re.search(r"(?i)italic|oblique", span.get("font", "")))


def page(p, avec_images=True):
    """Blocs de la page : [("titre", niveau, texte) | ("para", puce, [(texte, gras, italique)]) | ("image", png)].
    Liste vide et scannee=True si la page n'a pas de texte."""
    d = p.get_text("dict", flags=fitz.TEXT_PRESERVE_IMAGES)
    tailles = Counter()
    for b in d["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                n = len(s["text"].strip())
                if n:
                    tailles[round(s["size"] * 2) / 2] += n
    if not tailles:
        return [], True
    corps = tailles.most_common(1)[0][0]
    haut = p.rect.height
    out = []
    for b in d["blocks"]:
        r = fitz.Rect(b["bbox"])
        if b["type"] == 1:
            if not avec_images or r.width < 40 or r.height < 30 or (r.width > 0.9 * p.rect.width and r.height > 0.9 * haut):
                continue
            try:
                pm = p.get_pixmap(clip=r, dpi=min(200, max(72, int(900 / max(r.width, 1) * 72))))
                out.append(("image", pm.tobytes("png")))
            except Exception:                       # noqa: BLE001
                pass
            continue
        lignes = []
        for l in b.get("lines", []):
            spans = [s for s in l["spans"] if s["text"]]
            if spans and "".join(s["text"] for s in spans).strip():
                lignes.append((fitz.Rect(l["bbox"]), spans))
        if not lignes:
            continue
        texte = " ".join("".join(s["text"] for s in sp) for _r, sp in lignes).strip()
        marge = 0.06 * haut
        if (r.y1 < marge or r.y0 > haut - marge) and len(texte) <= 80:
            continue                                # en-tete ou pied de page court
        out += _paragraphes(lignes, r, corps)
    return out, False


def _moyenne(spans):
    t = [(s["size"], len(s["text"].strip())) for s in spans if s["text"].strip()]
    n = sum(k for _s, k in t)
    return sum(s * k for s, k in t) / n if n else 0


def _paragraphes(lignes, r, corps):
    out, courant, avant = [], [], None
    largeur = max(r.width, 1)
    for lr, sp in lignes:
        t = "".join(s["text"] for s in sp).strip()
        if avant is not None:
            pr, psp = avant
            tp = "".join(s["text"] for s in psp).strip()
            ecart = lr.y0 - pr.y1
            courte = pr.width < 0.7 * largeur and tp[-1:] in ".:!?;"
            puce = t[:1] in PUCES or NUMERO.match(t)
            autre = abs(_moyenne(sp) - _moyenne(psp)) > 0.2 * corps
            if ecart > 0.8 * max(pr.height, 1) or courte or puce or autre:
                out.append(_para(courant, corps))
                courant = []
        courant.append(sp)
        avant = (lr, sp)
    if courant:
        out.append(_para(courant, corps))
    return out


def _para(lignes, corps):
    morceaux = []                                   # (texte, gras, italique)
    for k, sp in enumerate(lignes):
        if k and morceaux:
            t0, g0, i0 = morceaux[-1]
            suivant = next((s["text"].lstrip() for s in sp if s["text"].strip()), "")
            if t0.endswith("-") and len(t0) > 1 and t0[-2].isalpha() and suivant[:1].islower():
                morceaux[-1] = (t0[:-1], g0, i0)    # mot coupe en fin de ligne : recolle
            elif not t0.endswith(" "):
                morceaux.append((" ", g0, i0))
        for s in sp:
            t = s["text"]
            if k == 0 and not morceaux:
                t = t.lstrip()
            g, i = _gras(s), _italique(s)
            if morceaux and morceaux[-1][1:] == (g, i):
                morceaux[-1] = (morceaux[-1][0] + t, g, i)
            else:
                morceaux.append((t, g, i))
    texte = re.sub(r" {2,}", " ", "".join(m[0] for m in morceaux)).strip()
    taille = _moyenne([s for sp in lignes for s in sp])
    lettres = [(s, len(s["text"].strip())) for sp in lignes for s in sp if s["text"].strip()]
    n = sum(k for _s, k in lettres)
    gras = n and sum(k for s, k in lettres if _gras(s)) > 0.8 * n
    if taille >= 1.7 * corps and len(texte) <= 160:
        return ("titre", 1, texte)
    if taille >= 1.25 * corps and len(texte) <= 200:
        return ("titre", 2, texte)
    if gras and len(lignes) == 1 and len(texte) <= 90 and taille >= 0.95 * corps and texte[-1:] not in ".,;":
        return ("titre", 3, texte)
    return ("para", texte[:1] in PUCES or bool(NUMERO.match(texte)), morceaux)


def html_page(blocs, scannee, image_page=None, texte_scannee="Page scannée : son texte n'est pas encore reconnu."):
    """HTML d'une page (pour QTextBrowser)."""
    if scannee:
        h = "<p style='color:#888'>" + html.escape(texte_scannee) + "</p>"
        if image_page:
            h += f"<p><img src='data:image/png;base64,{base64.b64encode(image_page).decode()}' width='100%'></p>"
        return h
    out = []
    for b in blocs:
        if b[0] == "titre":
            out.append(f"<h{b[1]}>{html.escape(b[2])}</h{b[1]}>")
        elif b[0] == "image":
            out.append(f"<p align='center'><img src='data:image/png;base64,{base64.b64encode(b[1]).decode()}'></p>")
        else:
            corps = ""
            for t, g, i in b[2]:
                t = html.escape(t)
                if g:
                    t = f"<b>{t}</b>"
                if i:
                    t = f"<i>{t}</i>"
                corps += t
            out.append(f"<p class='{'puce' if b[1] else 'para'}'>{corps.strip()}</p>")
    return "\n".join(out)

