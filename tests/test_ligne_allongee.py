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
res = ed.modifier_paragraphe(0, para, "Très long titre " * 9)
verif(res["en_plus"] > 0 and res["deborde_cadre"], "trop long : 2e ligne hors du bandeau signalée")

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
print("RESULTAT : OK" if ok == 9 else "RESULTAT : ECHEC")
