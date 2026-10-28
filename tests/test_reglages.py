"""Preferences : export chiffre, import selectif (communs / poste / secrets), copie automatique sur le Drive."""
import json, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import annotations  # noqa: F401  (erreurs lisibles sur GitHub)
os.environ["PHILPDF_LANGUE"] = "fr"
base = tempfile.mkdtemp()
os.environ["HOME"] = os.environ["APPDATA"] = base
from app import reglages, coffre

ok = 0
def verifie(cond, msg):
    global ok
    assert cond, msg
    ok += 1
    print("OK ", msg)

class P(dict):
    def enregistrer(self): pass

drive = os.path.join(base, "Drive"); os.makedirs(drive)
a = P(machine="Pharmacie", auteur="Phil", langue="fr", outils_epingles=["modifier", "imprimer"], volet="icones",
      comptes=[{"id": "c1", "type": "webdav", "adresse": "https://nas:5006"}], nas="Z:\\", racines=["D:\\Docs"],
      drive=drive, clef_claude="sk-test")
coffre.enregistrer("c1", "motdepasse")
f = os.path.join(base, "p.philpdf")
reglages.exporter(f, reglages.instantane(a, avec_secrets=True), "phrase secrète")
verifie(b"motdepasse" not in open(f, "rb").read() and b"sk-test" not in open(f, "rb").read(), "export chiffré : rien de lisible")
try:
    reglages.importer(f, "mauvaise"); verifie(False, "phrase vérifiée")
except reglages.PhraseRequise:
    verifie(True, "mauvaise phrase refusée")
d = reglages.importer(f, "phrase secrète")
coffre.supprimer("c1")
b = P(machine="Maison", nas="")
reglages.appliquer(b, d, communs=True, poste=False, secrets=True)
verifie(b["machine"] == "Maison" and b["nas"] == "" and b["volet"] == "icones" and b["outils_epingles"] == ["modifier", "imprimer"],
        "nouveau poste : réglages communs repris, chemins du poste gardés")
verifie(coffre.lire("c1") == "motdepasse" and b["clef_claude"] == "sk-test", "mots de passe et clefs restaurés")
c = P(machine="?")
reglages.appliquer(c, d, communs=True, poste=True, secrets=False)
verifie(c["machine"] == "Pharmacie" and c["racines"] == ["D:\\Docs"], "réinstallation du même poste : ses chemins reviennent")
a["communs_maj"] = "2026-10-24T10:00:00"           # reglages vraiment changes sur ce poste
verifie(reglages.ecrire_drive(a), "copie automatique sur le Drive")
dd = reglages.lire_drive(os.path.join(drive, "PhilPDF", "preferences.json"))
verifie("Pharmacie" in dd["postes"] and dd["communs"]["auteur"] == "Phil" and "secrets" not in json.dumps(dd)
        and "motdepasse" not in json.dumps(dd), "Drive : communs + poste, jamais de mot de passe")

# --- un poste neuf (reglages par defaut, jamais changes) n'ecrase pas les reglages communs du Drive
neuf = P(machine="Portable", drive=drive, outils_epingles=["imprimer"], auteur="", comptes=[])
reglages.ecrire_drive(neuf)
dd = reglages.lire_drive(os.path.join(drive, "PhilPDF", "preferences.json"))
verifie(dd["communs"]["outils_epingles"] == ["modifier", "imprimer"] and "Portable" in dd["postes"],
        "poste neuf : ses réglages par défaut n'écrasent pas ceux du Drive")
r = reglages.reprendre_communs_drive(neuf)
verifie(r and r[0] == "Pharmacie" and neuf["outils_epingles"] == ["modifier", "imprimer"] and neuf["volet"] == "icones"
        and [c["id"] for c in r[1]] == ["c1"], "au démarrage : favoris, volets et comptes repris du poste le plus récent")
verifie(reglages.reprendre_communs_drive(neuf) is None, "rien à reprendre ensuite")
neuf["outils_epingles"] = ["alleger"]; neuf["communs_maj"] = "2026-10-24T12:00:00"
reglages.ecrire_drive(neuf)
r = reglages.reprendre_communs_drive(a)
verifie(r and a["outils_epingles"] == ["alleger"], "changement fait ailleurs plus récemment : repris ici")

# --- mots de passe synchronises, chiffres par la phrase
a["synchro_secrets"] = True
coffre.enregistrer("c1", "motdepasse")
verifie(reglages.ecrire_secrets_drive(a, "ma phrase secrète"), "mots de passe envoyés sur le Drive")
brut = open(os.path.join(drive, "PhilPDF", "secrets.philpdf"), "rb").read()
verifie(b"motdepasse" not in brut and b"sk-test" not in brut, "fichier des mots de passe illisible sans la phrase")
coffre.supprimer("c1")
autre = P(machine="Maison", drive=drive, comptes=[{"id": "c1", "type": "webdav"}], clef_claude="")
try:
    reglages.reprendre_secrets_drive(autre, "faux"); verifie(False, "phrase")
except reglages.PhraseRequise:
    verifie(True, "mauvaise phrase : rien n'est repris")
n = reglages.reprendre_secrets_drive(autre, "ma phrase secrète")
verifie(n >= 2 and coffre.lire("c1") == "motdepasse" and autre["clef_claude"] == "sk-test", "autre poste : mots de passe et clef IA repris")

# --- mise a jour choisie : rien en silence, chaque reglage decrit et a cocher
a["outils_epingles"] = ["alleger", "ocr"]; a["auteur"] = "Philippe"; a["communs_maj"] = "2026-10-25T09:00:00"
a["comptes"] = [{"id": "c1", "type": "webdav", "nom": "NAS maison"}, {"id": "c2", "type": "ftp", "nom": "FTP bureau"}]
reglages.ecrire_drive(a)
av_auteur = neuf["auteur"]
ch = reglages.changements_communs(neuf)
items = {it["cle"]: it for it in ch["items"]}
verifie(ch["par"] == "Pharmacie" and "auteur" in items and "outils_epingles" in items and neuf["auteur"] == av_auteur,
        "changements listés sans rien appliquer")
verifie("ajoute : ocr" in items["outils_epingles"]["detail"] and "FTP bureau" in items["comptes"]["detail"]
        and "Philippe" in items["auteur"]["detail"], f"chaque changement décrit ({items['comptes']['detail']})")
reglages.appliquer_communs(neuf, ch, ["outils_epingles"])
verifie(neuf["outils_epingles"] == ["alleger", "ocr"] and neuf["auteur"] == av_auteur and len(neuf["comptes"]) != 2,
        "seuls les réglages cochés sont repris")
verifie(reglages.changements_communs(neuf) is None, "refusés : la question ne revient pas")
# --- un poste aux reglages plus recents n'ecrase pas en silence ceux d'un autre poste qu'il n'a jamais vus
x = P(machine="Cannes", drive=drive, outils_epingles=["x"], auteur="Autre", communs_maj="2030-01-01T00:00:00")
reglages.ecrire_drive(x)
dd = reglages.lire_drive(os.path.join(drive, "PhilPDF", "preferences.json"))
verifie(dd["communs"]["par"] != "Cannes", "réglages d'un autre poste jamais vus : pas écrasés, même par un poste plus récent")
ch = reglages.changements_communs(x)
verifie(ch and ch["items"] and not ch["plus_recent_ailleurs"] and not any(it["coche"] for it in ch["items"]),
        "proposés quand même, décochés d'avance car ce poste est le plus récent")
reglages.appliquer_communs(x, ch, [])
reglages.ecrire_drive(x)
dd = reglages.lire_drive(os.path.join(drive, "PhilPDF", "preferences.json"))
verifie(dd["communs"]["par"] == "Cannes" and dd["communs"]["outils_epingles"] == ["x"] and reglages.changements_communs(x) is None,
        "vus et gardés : ce poste devient la référence, plus de question")
# --- un reglage jamais touche ici (vide) vaut sa valeur par defaut : « (vide) -> google » n'est pas propose
y = P(machine="Neuf2", drive=drive)
dd = reglages.lire_drive(os.path.join(drive, "PhilPDF", "preferences.json"))
dd["communs"].update(agenda="google", messagerie="gmail", maj="2027-01-01T00:00:00", par="Pharmacie")
json.dump(dd, open(os.path.join(drive, "PhilPDF", "preferences.json"), "w", encoding="utf-8"))
ch = reglages.changements_communs(y)
verifie(ch is not None and not any(it["cle"] in ("agenda", "messagerie") for it in ch["items"]),
        "réglage jamais touché = valeur par défaut : pas de faux changement")
# --- disposition (largeur des volets) changee sur un autre poste : proposee une fois, reprise ou non
pp = os.path.join(drive, "PhilPDF", "preferences.json")
dd = reglages.lire_drive(pp)
dd.setdefault("postes", {})["Cannes"] = {"machine": "Cannes", "maj": "2027-02-01T10:00", "volet_largeur": 410}
json.dump(dd, open(pp, "w", encoding="utf-8"))
z = P(machine="Pharma2", drive=drive, volet_largeur=300)
dp = reglages.disposition_autre(z)
verifie(dp and dp["poste"] == "Cannes" and dp["items"][0]["valeur"] == 410, "disposition d'un autre poste proposée")
reglages.appliquer_disposition(z, dp, [])
verifie(z["volet_largeur"] == 300 and reglages.disposition_autre(z) is None, "ignorée : plus de question")
dd["postes"]["Cannes"]["volet_largeur"] = 380
json.dump(dd, open(pp, "w", encoding="utf-8"))
verifie(reglages.disposition_autre(z) is not None, "changée à nouveau sur l'autre poste : la question revient")
coffre.supprimer("c1")
autre2 = P(machine="Labo", drive=drive, comptes=[{"id": "c1", "type": "webdav", "nom": "NAS maison"}], clef_claude="")
nv = reglages.secrets_nouveaux(autre2, "ma phrase secrète")
verifie(any("NAS maison" in x["libelle"] for x in nv) and "motdepasse" not in json.dumps(nv), "mots de passe nouveaux listés, sans leur valeur")
reglages.reprendre_secrets_choisis(autre2, "ma phrase secrète", [x["cle"] for x in nv if "NAS" in x["libelle"]])
verifie(coffre.lire("c1") == "motdepasse" and not autre2["clef_claude"], "seuls les mots de passe cochés sont repris")
reglages.ecrire_indice(a, "la phrase du carnet bleu")
verifie(reglages.lire_indice(autre2) == "la phrase du carnet bleu", "indice de la phrase secrète visible sur les autres postes")
# identites : un poste dont la liste est vide ne la vide plus chez les autres ; elle repart et revient
import tempfile as _tf
_dr = _tf.mkdtemp()
os.makedirs(os.path.join(_dr, "PhilPDF"))
class _P(dict):
    def enregistrer(self):
        pass
_ph = _P(machine="Pharma", drive=_dr, identites=[{"id": "a1", "nom": "Philippe"}], communs_maj="2026-10-28T20:00:00")
_ca = _P(machine="Cannes", drive=_dr, identites=[], communs_maj="2026-10-28T23:11:00", communs_drive_vu="")
reglages.ecrire_drive(_ca)
_ch = reglages.changements_communs(_ph)
reglages.appliquer_communs(_ph, _ch, [i["cle"] for i in _ch["items"] if not i.get("cache")])
reglages.ecrire_drive(_ph)
verifie(_ph["identites"] and reglages.lire_drive(reglages.chemin_drive(_ph))["communs"]["identites"],
        "identités : le poste qui les a les garde et les renvoie au Drive")
_ch2 = reglages.changements_communs(_ca)
reglages.appliquer_communs(_ca, _ch2, [i["cle"] for i in _ch2["items"]])
verifie(_ca["identites"] == [{"id": "a1", "nom": "Philippe"}], "identités retrouvées sur l'autre poste")
# meme ID d'Acrobat importe sur les deux postes : une seule ligne apres la fusion, un seul « par defaut »
from app.miroir import unir as _unir
_u = _unir("identites", [{"id": "c9", "nom": "Philippe", "empreinte": "E1", "defaut": True}],
           [{"id": "a1", "nom": "Philippe", "empreinte": "E1", "defaut": True}, {"id": "b2", "nom": "Autre", "empreinte": "E2"}])
verifie(len(_u) == 2 and _u[0]["alias"] == ["c9"] and sum(1 for x in _u if x.get("defaut")) == 1,
        "même ID importé sur deux postes : une seule identité (l'autre numéro gardé en alias)")
print(f"\n{ok} vérifications de préférences réussies")
