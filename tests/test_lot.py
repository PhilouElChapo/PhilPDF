"""Traitement par lot (filigrane, Bates continu, PDF/A, renommage, signes laisses de cote) et Archiver PDF/A.
Lancement : QT_QPA_PLATFORM=offscreen python tests/test_lot.py"""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["PHILPDF_LANGUE"] = "fr"
os.environ["APPDATA"] = tempfile.mkdtemp()
os.environ["HOME"] = os.environ["APPDATA"]
import annotations  # noqa: F401
import pymupdf as fitz
from PySide6.QtWidgets import QApplication, QMessageBox
app = QApplication.instance() or QApplication([])
from app.config import Parametres
from app import lot as L
from moteur import pdfa

ok = []


def verif(c, quoi):
    ok.append((bool(c), quoi))
    print(("OK    " if c else "ECHEC ") + quoi)


T = tempfile.mkdtemp()
for i, n in enumerate((2, 3, 1)):
    d = fitz.open()
    for k in range(n):
        d.new_page().insert_text((72, 72), f"Facture {i} page {k}", fontname="helv")
    d.set_metadata({"title": f"Facture {i}"})
    d.save(os.path.join(T, f"facture_{i}.pdf"))
fitz.open().save if False else None
# un fichier signe : laisse de cote
from moteur import signature_num as SN
pfx = SN.creer_identite("Test", "mdp-123")
d = fitz.open()
d.new_page()
d.save(os.path.join(T, "signe_src.pdf"))
SN.signer(os.path.join(T, "signe_src.pdf"), os.path.join(T, "z_signe.pdf"), pfx, "mdp-123", page=0,
          rect=(72, 72, 250, 120), horodatage=False)
os.remove(os.path.join(T, "signe_src.pdf"))
dl = L.DialogueLot(None, Parametres(), T)
verif(len(dl.fichiers) == 4, f"dossier listé ({len(dl.fichiers)} PDF)")
for a in ("filigrane", "bates", "pdfa", "renommer"):
    dl.cases[a].setChecked(True)
dl.b_prefixe.setText("DOS-")
dl.b_chiffres.setValue(4)
dl.modele.setText("{n} {titre}")
dl.maj_apercu()
verif(dl.table.item(0, 1).text().endswith("001 Facture 0.pdf"), f"aperçu des noms ({dl.table.item(0, 1).text()})")
dl.lancer()
dl.tache.wait(120000)
app.processEvents()
sortie = os.path.join(T, "Traités")
fs = sorted(os.listdir(sortie)) if os.path.isdir(sortie) else []
verif(fs == ["001 Facture 0.pdf", "002 Facture 1.pdf", "003 Facture 2.pdf"], f"fichiers produits ({fs})")
d1 = fitz.open(os.path.join(sortie, "002 Facture 1.pdf"))
textes = [p.get_text() for p in d1]
verif("DOS-0003" in textes[0] and "DOS-0005" in textes[2], "Bates continu d'un fichier à l'autre")
verif("COPIE" in textes[0], "filigrane posé")
verif(pdfa.conforme(d1), "PDF/A-2b conforme aux vérifications")
verif("signé" in dl.table.item(3, 2).text(), "fichier signé laissé tel quel")
verif(sorted(f for f in os.listdir(T) if f.endswith(".pdf"))[0] == "facture_0.pdf", "originaux intacts")
# archiver : dialogue
from app.document import OngletDocument
from app.archiver import DialogueArchiver
o = OngletDocument(Parametres(), os.path.join(T, "facture_0.pdf"))
da = DialogueArchiver(None, o)
verif(da.changes.count() >= 2 and da.resultat and "Prêt" in da.bilan.text(), "Archiver : changements listés, prêt")
n_ok = sum(1 for c, _q in ok if c)
print(f"\n{n_ok}/{len(ok)} vérifications du traitement par lot réussies")
sys.exit(0 if n_ok == len(ok) else 1)
