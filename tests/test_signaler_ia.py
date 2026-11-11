"""Signaler un resultat de l'IA : ce qui part (champs du formulaire Google), rien sans motif, outil present.
Le reseau est simule : aucun vrai signalement n'est envoye."""
import os, sys, urllib.parse
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])
from app import signaler_ia, ia
from app.outils import outil

ok = True


def verifier(cond, texte):
    global ok
    print(("OK    " if cond else "ECHEC ") + texte)
    ok &= bool(cond)


envoyes = []


class _Rep:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def faux_urlopen(req, timeout=0):
    envoyes.append((req.full_url, urllib.parse.parse_qs(req.data.decode("utf-8"))))
    return _Rep()


signaler_ia.urllib.request.urlopen = faux_urlopen
ia.dernier.update(moteur="gemini", modele="gemini-2.5-flash")
signaler_ia.envoyer("Résumer", "Faux", "date inventée", "Réponse pour Jean Martin " + "x" * 20000)
url, champs = envoyes[-1]
verifier(url.endswith("/formResponse") and "1FAIpQLSf" in url, "envoi au formulaire Google (formResponse)")
verifier(set(champs) == set(signaler_ia.CHAMPS.values()), "les 6 champs du formulaire sont remplis")
c = {k: champs[v][0] for k, v in signaler_ia.CHAMPS.items()}
verifier(c["fonction"] == "Résumer" and c["motif"] == "Faux" and c["commentaire"] == "date inventée", "fonction, motif, commentaire")
verifier(c["service"] == "Gemini gemini-2.5-flash", f"service et modele ({c['service']})")
verifier(len(c["texte"]) == signaler_ia.MAX_TEXTE, "texte limite a 8000 caracteres")
verifier(c["version"].split()[0] in ("Windows", "Linux") and c["version"].split()[1][0].isdigit(), f"version ({c['version']})")

d = signaler_ia.DialogueSignaler(None, "Expliquer simplement", "Texte de l'IA")
verifier(not d.b_envoyer.isEnabled(), "Envoyer grise tant qu'aucun motif n'est choisi")
d.groupe.button(0).click()
verifier(d.b_envoyer.isEnabled(), "motif choisi : Envoyer actif")
verifier(d.texte.toPlainText() == "Texte de l'IA", "le texte envoye est montre (modifiable)")
verifier(outil("ia_signaler") is not None, "outil « Signaler un resultat de l'IA » dans l'Assistant IA")
print("RESULTAT :", "OK" if ok else "ECHEC")
sys.exit(0 if ok else 1)
