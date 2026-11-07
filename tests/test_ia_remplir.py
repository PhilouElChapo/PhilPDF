"""Remplir un formulaire avec l'IA (Windows) : champs lus (nom, libelle, type, choix), valeurs ecrites (texte, case,
liste) ; champs en lecture seule et de signature ignores. L'IA elle-meme n'est pas appelee."""
import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")
import pymupdf as fitz
from app.dialogues_ia import _champs_formulaire, remplir_valeurs, CONSIGNES_EXPLIQUER, CONSIGNES_REMPLIR

ok = 0


def verif(c, m):
    global ok
    assert c, m
    ok += 1
    print("✓", m)


d = fitz.open()
p = d.new_page()
for nom, genre, r, extra in [("nom", fitz.PDF_WIDGET_TYPE_TEXT, (100, 100, 300, 120), {}),
                             ("majeur", fitz.PDF_WIDGET_TYPE_CHECKBOX, (100, 140, 115, 155), {}),
                             ("pays", fitz.PDF_WIDGET_TYPE_COMBOBOX, (100, 170, 300, 190), {"choice_values": ["France", "Italie"]}),
                             ("ref", fitz.PDF_WIDGET_TYPE_TEXT, (100, 200, 300, 220), {"field_flags": 1}),
                             ("sig", fitz.PDF_WIDGET_TYPE_SIGNATURE, (100, 240, 300, 280), {})]:
    w = fitz.Widget()
    w.field_name, w.field_type, w.rect = nom, genre, fitz.Rect(r)
    w.field_label = {"nom": "Nom et prénom"}.get(nom, "")
    for k, v in extra.items():
        setattr(w, k, v)
    p.add_widget(w)
champs = _champs_formulaire(d)
noms = [c["nom"] for c in champs]
verif(noms == ["nom", "majeur", "pays"], f"champs à remplir trouvés, lecture seule et signature écartés ({noms})")
verif(champs[0]["libelle"] == "Nom et prénom", "libellé visible transmis à l'IA")
verif(champs[2]["choix"] == ["France", "Italie"], "choix de la liste transmis")
n = remplir_valeurs(d, [(champs[0], "Jean Martin"), (champs[1], "oui"), (champs[2], "Italie")])
verif(n == 3, "trois champs remplis")
vals = {w.field_name: w.field_value for w in d[0].widgets()}
verif(vals["nom"] == "Jean Martin" and vals["pays"] == "Italie", "texte et liste écrits")
verif(vals["majeur"] not in ("Off", False, None, ""), "case cochée")
verif("{langue}" in CONSIGNES_EXPLIQUER and "Avant quand" in CONSIGNES_EXPLIQUER, "consigne Expliquer prête")
verif("n'invente" in CONSIGNES_REMPLIR.replace("’", "'"), "consigne Remplir : rien d'inventé")
print("RESULTAT : OK" if ok == 8 else "RESULTAT : ECHEC")
