"""Traductions : chaque texte du code est dans langues/*.json, avec les memes {noms}."""
import json, os, re, sys
racine = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(racine, "outils_dev"))
import i18n
textes = i18n.textes_du_code()
ok = True
for f in sorted(os.listdir(os.path.join(racine, "langues"))):
    d = json.load(open(os.path.join(racine, "langues", f), encoding="utf-8"))
    manquants = [t for t in textes if not d.get(t)]
    faux = [k for k, v in d.items() if v and not k.startswith("_") and
            not set(re.findall(r"\{(\w+)", v)) <= set(re.findall(r"\{(\w+)", k))]
    print(f"{f} : {len(textes) - len(manquants)}/{len(textes)} traduits, {len(faux)} {{noms}} incorrects")
    for t in manquants[:10]:
        print("   manque :", t[:80])
    for t in faux[:10]:
        print("   {noms} :", t[:80])
    ok &= f != "en.json" or (not manquants and not faux)     # l'anglais doit etre complet
# en anglais, l'interface se construit
os.environ["PHILPDF_LANGUE"] = "en"
sys.path.insert(0, racine)
from app.langue import _, LANGUE
ok &= LANGUE == "en" and _("Enregistrer") == "Save" and _("Annuler|action") == "Undo" and _("Annuler") == "Cancel"
print("RESULTAT :", "OK" if ok else "ECHEC")
sys.exit(0 if ok else 1)
