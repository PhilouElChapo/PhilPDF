"""Paragraphe d'une ligne modifie avec un texte plus long : la ligne s'allonge (centree dans son bandeau si elle
l'etait) au lieu de passer a la ligne hors du bandeau ; au-dela de la place, la 2e ligne est signalee."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")
import pymupdf as fitz
from moteur.modifier import Editeur

ok = 0


def verif(c, m):
    global ok
    assert c, m
    ok += 1
    print("✓", m)


def page_bandeau():
    d = fitz.open()
    p = d.new_page(width=595, height=842)
    bandeau = fitz.Rect(60, 100, 535, 118)
    p.draw_rect(bandeau, color=(0.78, 0.25, 0.25), fill=(0.78, 0.25, 0.25))
    t = "Pharmacien du 01/01/1997"
    w = fitz.get_text_length(t, "hebo", 10)
    p.insert_text(((60 + 535) / 2 - w / 2, 113), t, fontname="hebo", fontsize=10, color=(1, 1, 1))
    p.insert_text((70, 150), "Vous exercez la profession de pharmacien depuis le 01/01/1997.", fontname="helv", fontsize=10)
    return d, bandeau


d, bandeau = page_bandeau()
ed = Editeur(d)
para = ed.paragraphe_a(0, fitz.Point(297, 110))
verif(para and len(para["lignes"]) == 1, "titre du bandeau trouvé (une ligne)")
lo, hi, centre, cadre = ed.limites_ligne(0, para)
verif(cadre is not None and centre, "bandeau reconnu, ligne centrée dedans")
nouveau = "Salarié non titulaire de l'Etat du 01/12/1994 au 30/03/1995"
res = ed.modifier_paragraphe(0, para, nouveau)
verif(res["lignes"] == 1 and res["en_plus"] == 0, "texte plus long : toujours une seule ligne")
verif(not res["deborde_cadre"], "rien ne sort du bandeau")
mots = [w for w in d[0].get_text("words") if bandeau.contains(fitz.Rect(w[:4]))]
txt = " ".join(w[4] for w in mots)
verif(txt == nouveau, "tout le texte est dans le bandeau : " + txt)
x0 = min(w[0] for w in mots); x1 = max(w[2] for w in mots)
verif(abs((x0 + x1) / 2 - bandeau.x0 - bandeau.width / 2) < 4, f"texte centré dans le bandeau ({x0:.0f}–{x1:.0f})")

# trop long pour le bandeau : passe sur deux lignes, et c'est signale
d, bandeau = page_bandeau()
ed = Editeur(d)
para = ed.paragraphe_a(0, fitz.Point(297, 110))
long_ = "Salarié non titulaire de l'Etat du 01/12/1994 au 30/03/1995, puis contractuel jusqu'au 31/12/1996, puis pharmacien adjoint à Cannes"
res = ed.modifier_paragraphe(0, para, long_)
verif(not res["deborde_cadre"] and (res["dans_cadre"] or res["reduit"]), "trop long pour une ligne : tout tient DANS le bandeau")
mots = [w for w in d[0].get_text("words") if fitz.Rect(bandeau).include_rect(fitz.Rect(0, 0, 0, 0)) or True]
dedans = " ".join(w[4] for w in d[0].get_text("words") if fitz.Rect(w[:4]).intersects(bandeau))
verif(dedans.split() == long_.split(), "tout le texte est dans le bandeau (police réduite si besoin)")
verif(all(bandeau.y0 - 1 <= w[1] and w[3] <= bandeau.y1 + 1 for w in d[0].get_text("words") if fitz.Rect(w[:4]).intersects(bandeau)),
      "aucune ligne ne dépasse en haut ou en bas")
# Entree tapee par l'utilisateur : deux lignes voulues, dans le bandeau aussi
d, bandeau = page_bandeau()
ed = Editeur(d)
para = ed.paragraphe_a(0, fitz.Point(297, 110))
res = ed.modifier_paragraphe(0, para, "Pharmacien\ndu 01/01/1997")
verif(res["lignes"] == 2 and res["dans_cadre"], "retour à la ligne voulu : deux lignes dans le bandeau")
# vraiment trop long (meme a 55 %) : signale
d, bandeau = page_bandeau()
ed = Editeur(d)
para = ed.paragraphe_a(0, fitz.Point(297, 110))
res = ed.modifier_paragraphe(0, para, "Très long titre " * 30)
verif(res["deborde_cadre"], "beaucoup trop long : débordement signalé")

# largeur choisie a la poignee : respectee (pas d'allongement)
d, bandeau = page_bandeau()
ed = Editeur(d)
para = ed.paragraphe_a(0, fitz.Point(297, 110))
para["largeur_choisie"] = True
res = ed.modifier_paragraphe(0, para, nouveau)
verif(res["lignes"] > 1, "largeur tirée à la poignée : coupure à cette largeur")

# ligne ordinaire a gauche : s'allonge jusqu'a la marge
d, _b = page_bandeau()
ed = Editeur(d)
para = ed.paragraphe_a(0, fitz.Point(100, 147))
res = ed.modifier_paragraphe(0, para, "Vous exercez la profession de pharmacien depuis le 01/01/1997, à Cannes, en officine.")
verif(res["lignes"] == 1 and res["x1"] <= 595 - 18 + 0.5, "ligne à gauche : allongée jusqu'à la marge, une ligne")
print("RESULTAT : OK" if ok == 13 else "RESULTAT : ECHEC")
