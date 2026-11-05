"""Langues de PhilPDF Android : chaque langue (fr, de, es, it) a tous les textes de l'anglais (values), avec les memes
%1$s / %2$d (sinon l'application plante a l'affichage), et un XML valide."""
import os, re, sys
import xml.etree.ElementTree as E

R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "android", "app", "src", "main", "res")


def lire(dossier):
    root = E.parse(os.path.join(R, dossier, "strings.xml")).getroot()
    return {s.get("name"): (s.text or "") for s in root if s.tag == "string" and s.get("translatable") != "false"}


ph = lambda t: sorted(re.findall(r"%\d\$[sd]|%%", t))
base = lire("values")
erreurs = 0
for l in ("fr", "de", "es", "it"):
    t = lire("values-" + l)
    manque = sorted(set(base) - set(t))
    formats = [k for k in base if k in t and ph(base[k]) != ph(t[k])]
    apos = [k for k, v in t.items() if re.search(r"(?<!\\)'", v) and not (v.startswith('"') and v.endswith('"'))]
    for nom, liste in (("textes manquants", manque), ("formats differents", formats), ("apostrophes non protegees", apos)):
        if liste:
            erreurs += 1
            print(f"ECHEC  {l} : {nom} : {', '.join(liste[:15])}")
    print(f"OK     {l} : {len(t)} textes" if not (manque or formats or apos) else "")
sys.exit(1 if erreurs else 0)
