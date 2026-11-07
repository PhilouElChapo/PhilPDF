"""Traitement par lot (filigrane, Bates continu, PDF/A, renommage, signes laisses de cote) et Archiver PDF/A.
Lancement : QT_QPA_PLATFORM=offscreen python tests/test_lot.py"""
import os, sys, tempfile
import faulthandler
faulthandler.dump_traceback_later(int(os.environ.get("LOT_DUMP", "0")) or 10**6, exit=True)
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
from app.langue import _
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
# nom propose par l'IA et tri par expediteur (IA simulee) : donnees sensibles exclues sur demande, scan envoye en image
T2 = tempfile.mkdtemp()
for nom, texte in (("a_edf.pdf", "EDF - Facture d'électricité du 12/10/2026"), ("b_banque.pdf", "RIB : IBAN FR76 3000 6000 0112 3456 7890 189"),
                   ("c_scan.pdf", None)):
    d = fitz.open()
    p = d.new_page()
    if texte:
        p.insert_text((72, 100), texte, fontsize=12)
    else:                                                  # scan : une image, pas de texte
        pm = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 200, 100), False)
        pm.clear_with(200)
        p.insert_image(fitz.Rect(72, 72, 272, 172), pixmap=pm)
    d.save(os.path.join(T2, nom))
import app.dialogues_ia as DI
from app import ia as IA
appels = []


def faux_demander(params, consignes, texte, images=None, json_attendu=False, max_jetons=4000):
    appels.append((texte, bool(images)))
    if "EDF" in texte:
        return {"date": "2026-10-12", "expediteur": "EDF", "objet": "Facture électricité", "type": "facture"}
    return {"date": "2026-09-01", "expediteur": "CPAM", "objet": "Attestation de droits", "type": "attestation"}


IA.demander = faux_demander
DI.verifier_cle = lambda *a, **k: True
choisi = _("Envoyer, sans les fichiers sensibles")
QMessageBox.exec = lambda self, *a: None
QMessageBox.clickedButton = lambda self: next(b for b in self.buttons() if b.text() == choisi)
dl2 = L.DialogueLot(None, Parametres(), T2)
dl2.mode_nom.setCurrentIndex(1)
dl2.tri.setCurrentIndex(1)                                  # par expediteur
verif(dl2.cases["renommer"].isChecked() and not dl2.modele.isEnabled(), "nom par l'IA : Renommer coché, modèle grisé")
dl2.proposer_noms()
app.processEvents()
verif(len(appels) == 2 and not any("IBAN" in t for t, _i in appels), f"fichier sensible exclu de l'envoi ({len(appels)} envoi(s))")
verif(any(i for _t, i in appels), "scan sans texte : image de la première page envoyée")
noms = [dl2.table.item(i, 1).text() for i in range(3)]
verif(noms[0].replace("\\", "/") == "Traités/EDF/EDF – Facture électricité – 2026-10-12.pdf", f"nom et sous-dossier proposés ({noms[0]})")
dl2.table.item(2, 1).setText("CPAM – Attestation corrigée – 2026-09-01")
verif(dl2.noms_ia[dl2.fichiers[2]]["nom"] == "CPAM – Attestation corrigée – 2026-09-01.pdf", "nom corrigé à la main gardé")
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.No)   # l'exclu : nom selon le modele
dl2.lancer()
dl2.tache.wait(120000)
app.processEvents()
produits = sorted(os.path.relpath(os.path.join(r, f), os.path.join(T2, "Traités")).replace("\\", "/")
                  for r, _d, fs in os.walk(os.path.join(T2, "Traités")) for f in fs)
verif(produits == sorted([f"b_banque {L.datetime.date.today():%Y-%m-%d}.pdf", "CPAM/CPAM – Attestation corrigée – 2026-09-01.pdf",
                          "EDF/EDF – Facture électricité – 2026-10-12.pdf"]),
      f"fichiers rangés par expéditeur, l'exclu garde le modèle ({produits})")
# archiver : dialogue
from app.document import OngletDocument
from app.archiver import DialogueArchiver
o = OngletDocument(Parametres(), os.path.join(T, "facture_0.pdf"))
da = DialogueArchiver(None, o)
verif(da.changes.count() >= 2 and da.resultat and "Prêt" in da.bilan.text(), "Archiver : changements listés, prêt")
n_ok = sum(1 for c, _q in ok if c)
print(f"\n{n_ok}/{len(ok)} vérifications du traitement par lot réussies")
sys.exit(0 if n_ok == len(ok) else 1)
