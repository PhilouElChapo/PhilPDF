"""Scan deja en noir et blanc TRAME (pilote de scanner, papier securise d'ordonnance) : le fond pointille doit
partir au blanc et le texte rester. Image fabriquee : aucun document reel."""
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from moteur import nettoyage as N  # noqa: E402
from moteur import scan  # noqa: E402

ok = True


def verifier(cond, msg):
    global ok
    print(("OK   " if cond else "ECHEC ") + msg)
    ok = ok and cond


# page A4 a 300 dpi : fond gris clair (motif du papier) en diagonales, texte noir
h, w = 3508, 2480
gris = np.full((h, w), 255, np.uint8)
for k in range(-h, w, 60):
    cv2.line(gris, (k, 0), (k + h, h), 175, 18)
for i, ligne in enumerate(["Jean Martin", "3 rue des Lilas", "06000 Nice", "Ordonnance du 12/03/2026"]):
    cv2.putText(gris, ligne, (250, 900 + i * 160), cv2.FONT_HERSHEY_SIMPLEX, 3, 0, 7)
# tramage par diffusion d'erreur, comme un pilote de scanner en « noir et blanc »
from PIL import Image  # noqa: E402
trame = np.array(Image.fromarray(gris).convert("1", dither=Image.Dither.FLOYDSTEINBERG).convert("L"))

verifier(N.tramee(trame), "image tramee reconnue")
verifier(not N.tramee(gris), "image en niveaux de gris : pas tramee")
nette = np.where(gris < 128, 0, 255).astype(np.uint8)
verifier(not N.tramee(nette), "texte noir et blanc net : pas tramee")

res = scan.nettoyer(trame, 300)
fond = res[1500:3300, 200:2300]                 # sous le texte : motif seul
verifier(float((fond == 0).mean()) < 0.01, f"fond pointille retire ({(fond == 0).mean():.3%} de noir restant)")
texte = (gris[700:1500] < 128)
garde = float((res[700:1500][texte] == 0).mean())
verifier(garde > 0.85, f"texte garde ({garde:.0%} des traits)")
avant = float((trame[1500:3300, 200:2300] == 0).mean())
print(f"     noir dans le fond : {avant:.1%} avant, {(fond == 0).mean():.2%} apres")
sys.exit(0 if ok else 1)
