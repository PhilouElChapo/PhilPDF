"""Signature numerique : identites, signer comme Acrobat, champs pour d'autres signataires, verrouillage, ajout
incremental (une modification ne casse jamais une signature), synchronisation chiffree des identites.
Lancement : QT_QPA_PLATFORM=offscreen python tests/test_signature.py"""
import os, sys, tempfile, base64
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import annotations  # noqa: F401
os.environ["PHILPDF_LANGUE"] = "fr"
os.environ["APPDATA"] = tempfile.mkdtemp()
os.environ["HOME"] = os.environ["APPDATA"]
os.environ["PHILPDF_SANS_FIL"] = "1"
from PySide6.QtWidgets import QApplication, QMessageBox, QFileDialog, QDialog
import pymupdf as fitz
app = QApplication.instance() or QApplication([])

from moteur import signature_num as S
from app.config import Parametres
from app.bibliotheque import Bibliotheque
from app import identites as ID, reglages
import app.dialogues_signature as DS
from app.document import OngletDocument

ok = []


def verif(cond, quoi):
    ok.append((bool(cond), quoi))
    print(("OK   " if cond else "ECHEC") + " " + quoi)


QMessageBox.information = staticmethod(lambda *a, **k: None)
QMessageBox.warning = staticmethod(lambda *a, **k: print("AVERTISSEMENT", a[2] if len(a) > 2 else a))
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
T = tempfile.mkdtemp()

# ---------------------------------------------------------------- moteur
pfx = S.creer_identite("Jeanne Exemple", "secret1", organisation="Essai", email="jeanne@exemple.fr")
i = S.infos_pfx(pfx, "secret1")
verif(i["nom"] == "Jeanne Exemple" and i["autosigne"] and not i["expire"], "identité créée : autosignée, valable")
try:
    S.infos_pfx(pfx, "faux")
    verif(False, "mauvais mot de passe refusé")
except S.ErreurSignature as e:
    verif(str(e) == "mot_de_passe", "mauvais mot de passe refusé")
cer = S.exporter_cer(pfx, "secret1")
verif(S.lire_cer(cer).subject == S.ouvrir_pfx(pfx, "secret1")[1].subject, "certificat exporté (.cer) sans la clef")
p2 = S.changer_mot_de_passe(pfx, "secret1", "autre2")
verif(S.infos_pfx(p2, "autre2")["empreinte"] == i["empreinte"], "mot de passe de l'identité changé")
l = S.lignes_apparence("Jeanne Exemple", motif="J'approuve")
verif(l[0] == "Signature numérique de" and l[1] == "Jeanne Exemple" and l[2].startswith("Date : ") and "Motif" in l[-1],
      "apparence : mêmes lignes qu'Acrobat")


def formulaire(chemin):
    d = fitz.open()
    p = d.new_page()
    p.insert_text((72, 80), "Contrat de test", fontsize=14)
    for nom, y in (("Nom", 120), ("Ville", 150)):
        w = fitz.Widget()
        w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
        w.field_name = nom
        w.rect = fitz.Rect(150, y, 350, y + 20)
        p.add_widget(w)
    d.save(chemin)


# ---------------------------------------------------------------- identites (synchronisees, chiffrees)
params = Parametres()
params["auteur"] = "Jeanne Exemple"
e = ID.ajouter_pfx(params, pfx, "secret1", origine="acrobat")
verif(e["ici"] and e["defaut"] and ID.par_defaut(params)["id"] == e["id"], "identité importée (.pfx d'Acrobat), par défaut")
verif(ID.ajouter_pfx(params, pfx, "secret1")["id"] == e["id"] and len(ID.liste(params)) == 1, "même identité importée deux fois : une seule")
verif(any(c["empreinte"] == i["empreinte"] and c["soi"] for c in ID.approuves(params)), "vos propres signatures sont approuvées")
inst = reglages.instantane(params, avec_secrets=True)
verif(("identite:" + e["id"]) in inst["secrets"] and "identites" in inst["communs"], "identité dans les secrets synchronisés (chiffrés)")
f_ = os.path.join(T, "prefs.philpdf")
reglages.exporter(f_, inst, "phrase principale")
verif(base64.b64encode(pfx)[:40] not in open(f_, "rb").read(), "identité jamais en clair dans le fichier synchronisé")
os.remove(ID._fichier(e["id"]))
verif(not ID.liste(params)[0]["ici"], "autre poste : identité connue mais absente")
ID.reprendre_secret(params, "identite:" + e["id"], inst["secrets"]["identite:" + e["id"]])
verif(ID.liste(params)[0]["ici"] and ID.lire(e) == pfx, "identité reprise depuis le Drive")
verif(not ID.reprendre_secret(params, "identite:../x", "AAAA"), "nom d'identité suspect refusé")

# ---------------------------------------------------------------- document : champ pour un autre, signer, verrou
src = os.path.join(T, "Contrat.pdf")
formulaire(src)
biblio = Bibliotheque(params)
o = OngletDocument(params, src, biblio=biblio)
verif(not o.est_signe(), "document sans signature : enregistrement normal")
# champ de signature pour le client, verrouillant « Nom »
DS.DialogueChampSignature.exec = lambda self: (self.signataire.setText("le client"), self.ordre.setValue(2),
                                               self.findChild(type(self.modes.button(0)), "cs_verrou_ceux").setChecked(True),
                                               [self.champs.item(k).setCheckState(DS.Qt.Checked) for k in range(self.champs.count())
                                                if self.champs.item(k).text() == "Nom"], QDialog.Accepted)[-1]
o.changer_mode("champ_signature")
o.ajouter_champ_signature(0, fitz.Rect(320, 600, 500, 650))
ws = o.widgets_signature()
verif(len(ws) == 1 and ws[0][1].field_name == "Signature1", "champ de signature posé")
inf = o.infos_champ_sig(ws[0][1])
verif(inf["signataire"] == "le client" and inf["ordre"] == 2 and inf["verrou"] == ("ceux", ["Nom"]),
      f"champ : signataire, ordre, verrou gardés ({inf})")
verif(o.bandeau_sig.isVisibleTo(o) and "1 champ(s) à signer" in o.lbl_sig.text(), "bandeau : champ à signer")
o.changer_mode(None)
o.enregistrer(src)
verif(S.champs_signature(src) == [("Signature1", False)], "Acrobat verra un champ de signature vide")
# remplir puis signer ce champ (comme le client dans Acrobat)
o.valeur_champ(0, next(w.xref for w in o.doc[0].widgets() if w.field_name == "Nom"), "Dupont")
signe = os.path.join(T, "Contrat signé.pdf")


def signer_auto(self):
    self.mdp.setText("secret1")
    self.motif.setCurrentText("J'approuve ce document")
    self.lieu.setText("Cannes")
    self.horodatage.setChecked(False)
    self.valider()
    return QDialog.Accepted if self.resultat else QDialog.Rejected


DS.DialogueSigner.exec = signer_auto
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (signe, ""))
o.clic_champ_signature(0, o.widgets_signature()[0][1])
verif(os.path.exists(signe) and o.chemin == signe and o.est_signe() and not o.modifie, "signé dans le champ, document rechargé")
verif(len(o.signatures) == 1 and o.signatures[0]["intacte"] and o.signatures[0]["approuve"]
      and o.signatures[0]["nom"] == "Jeanne Exemple" and o.signatures[0]["raison"] == "J'approuve ce document",
      f"vérification : signature valide et approuvée ({o.signatures[0].get('erreur')})")
verif("toutes les signatures sont valides" in o.lbl_sig.text(), "bandeau : signé, tout est valide")
verif(o.champ_verrouille(next(w for w in o.doc[0].widgets() if w.field_name == "Nom")), "champ « Nom » verrouillé par la signature")
avant = next(w for w in o.doc[0].widgets() if w.field_name == "Nom").field_value
pw_ = type("PW", (), {"num": 0, "ouvrir_saisie_champ": lambda self, w: None})()
o.remplir_champ(pw_, next(w for w in o.doc[0].widgets() if w.field_name == "Nom"))
verif(avant == "Dupont", "champ verrouillé : modification refusée")
# champ non verrouille : rempli puis enregistre (ajout), la signature reste valide
o.valeur_champ(0, next(w.xref for w in o.doc[0].widgets() if w.field_name == "Ville"), "Cannes")
o.annuler()
o.retablir()
o.enregistrer(signe)
v = S.verifier(signe, ID.approuves_der(params))
if os.environ.get("DIAG"):
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.pdf_utils.generic import Reference
    r_ = PdfFileReader(open(signe, "rb"))
    for rv_ in range(1, r_.xrefs.total_revisions):
        print(rv_, sorted(x.idnum for x in r_.xrefs.explicit_refs_in_revision(rv_)))
        for i_ in (8, 18, 26, 27):
            try:
                print("  ", i_, r_.get_historical_resolver(rv_)(Reference(i_, 0)))
            except Exception as e_:
                print("  ", i_, e_)
verif(v[0]["intacte"] and v[0]["modifs"] == "formulaires", f"rempli après signature + annuler/rétablir : signature intacte ({v[0]['modifs']} {v[0].get('detail_modifs', '')})")
verif(fitz.open(signe)[0].widgets().__next__() is not None and
      [w.field_value for w in fitz.open(signe)[0].widgets() if w.field_name == "Ville"] == ["Cannes"], "valeur gardée")
# deuxieme signature dans un rectangle trace : la premiere reste valide
pfx2 = S.creer_identite("Paul Second", "secret2")
e2 = ID.ajouter_pfx(params, pfx2, "secret2")


def signer_auto2(self):
    self.identite.setCurrentIndex(self.identite.findData(next(x for x in ID.liste(params) if x["id"] == e2["id"])))
    self.mdp.setText("secret2")
    self.horodatage.setChecked(False)
    self.valider()
    return QDialog.Accepted if self.resultat else QDialog.Rejected


DS.DialogueSigner.exec = signer_auto2
o.changer_mode("signer_num")
o.zone_tracee(0, fitz.Rect(72, 700, 252, 745))
v = S.verifier(signe, ID.approuves_der(params))
verif(len(v) == 2 and all(x["intacte"] for x in v) and v[1]["nom"] == "Paul Second",
      "deuxième signature (rectangle tracé) : les deux sont valides")
verif(o.mode is None and len(o.signatures) == 2, "après la signature : retour au mode normal")
# certificat d'un correspondant non approuve, puis approuve
ID.retirer(params, S.infos_pfx(pfx2, "secret2")["empreinte"])
o.verifier_signatures()
verif(not o.signatures[1]["approuve"] and "non vérifiée" in o.lbl_sig.text(), "certificat non approuvé : signalé")
ID.approuver(params, o.signatures[1]["der"])
o.verifier_signatures()
verif(all(s["approuve"] for s in o.signatures), "certificat approuvé depuis la signature")
# fichier modifie en entier (pas en ajout) : signature non valide
d = fitz.open(signe)
d[0].insert_text((72, 300), "ajout frauduleux")
casse = os.path.join(T, "casse.pdf")
d.save(casse, garbage=3)
v = S.verifier(casse)
verif(v and not v[0]["intacte"], "document réécrit après signature : signature non valide")
o2 = OngletDocument(params, casse, biblio=biblio)
o2.verifier_signatures()
verif("n'est pas valide" in o2.lbl_sig.text(), "bandeau rouge : signature non valide")
# volet signatures
dv = DS.DialogueSignatures(o, o.signatures, o.champs_sig_vides)
verif(dv.arbre.topLevelItemCount() == 2, "volet Signatures : deux signatures listées")
dv.close()
# apercu de l'apparence
dsg = DS.DialogueSigner(o, None, fitz.Rect(0, 0, 180, 45), 0)
verif(dsg.apercu.pixmap() is not None and not dsg.apercu.pixmap().isNull(), "aperçu de l'apparence affiché")
dsg.close()
# dialogue des identites
di = DS.DialogueIdentites(None, params)
verif(di.liste.count() == 2 and di.certs.count() >= 2, "fenêtre des identités : identités et certificats")
di.close()

# reprendre l'ID d'Acrobat sans « Exporter » : le fichier d'ID est retrouve tout seul (Security\*.pfx)
from app import identites_systeme as IS
sec_ = os.path.join(os.environ["HOME"], ".adobe", "Acrobat", "DC", "Security")
os.makedirs(sec_, exist_ok=True)
pfx3 = S.creer_identite("Philippe Acrobat", "acro123")
open(os.path.join(sec_, "PhilippeAcrobat.pfx"), "wb").write(pfx3)
dsrc = DS.DialogueSourcesID(None)
verif(dsrc.liste.count() >= 1 and dsrc.liste.item(0).data(DS.Qt.UserRole)[0] == "fichier", "fichier d'ID d'Acrobat retrouvé tout seul")
import app.dialogues as _DG
_DG.demander_secret = lambda *a, **k: ("acro123", True)
e3 = DS.importer_pfx(None, params, dsrc.liste.item(0).data(DS.Qt.UserRole))
verif(e3 and e3["nom"] == "Philippe Acrobat", "ID d'Acrobat importé avec son mot de passe")
# magasin Windows : export simule
appels_ = []
IS._powershell = lambda script, timeout=40: (appels_.append(script), (0, "", ""))[1]
try:
    IS.windows_exporter("ABC123", "mdp'x")
    verif(False, "export Windows : erreur si rien n'est produit")
except IS.ErreurExport:
    verif("'mdp''x'" in appels_[-1] and "Cert:\\CurrentUser\\My\\ABC123" in appels_[-1], "export Windows : commande sûre (guillemets échappés)")
try:
    IS.windows_exporter("ABC; rm", "x")
    verif(False, "empreinte suspecte refusée")
except IS.ErreurExport:
    verif(True, "empreinte suspecte refusée")

n_ok = sum(1 for c, _q in ok if c)
print(f"\n{n_ok}/{len(ok)} vérifications de signature réussies")
sys.exit(0 if n_ok == len(ok) else 1)
