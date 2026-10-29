"""Envoi par e-mail : volet, versions du fichier joint, envoi direct et brouillon (serveurs simules)."""
import sys, os, tempfile
racine = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, racine)
os.environ["PHILPDF_LANGUE"] = "fr"
import pymupdf as fitz
os.environ["APPDATA"]=tempfile.mkdtemp(); os.environ["HOME"]=os.environ["APPDATA"]
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox; app=QApplication([])
SP=tempfile.mkdtemp()
d0=fitz.open(); d0.new_page().insert_text((72,72),"Bonjour"); d0.save(SP+"/img.pdf")
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
import app.bienvenue as BV
BV.DialogueBienvenue.exec = lambda self: QDialog.Rejected
from app import courriel as C, coffre
envoyes=[]
class FauxSMTP:
    def __init__(s,*a,**k): pass
    def login(s,u,p): envoyes.append(("login",u,p))
    def send_message(s,m): envoyes.append(("send",m["To"],m["Subject"],[p.get_filename() for p in m.iter_attachments()])); envoyes.append(("bcc", m["Bcc"]))
    def quit(s): pass
import smtplib, imaplib
smtplib.SMTP_SSL=FauxSMTP
class FauxIMAP:
    def __init__(s,*a,**k): pass
    def login(s,u,p): pass
    def list(s): return "OK",[b'(\\HasNoChildren) "/" "INBOX"', b'(\\HasNoChildren \\Drafts) "/" "Brouillons"']
    def append(s,dos,fl,d,m): envoyes.append(("append",dos,fl,len(m))); return "OK",[b""]
    def logout(s): pass
imaplib.IMAP4_SSL=FauxIMAP
import app.agenda as AG; AG.ouvrir=lambda c: envoyes.append(("ouvrir",c[:40]))
from app.fenetre import Fenetre
f=Fenetre(); f.resize(1500,950); f.show(); app.processEvents()
f.ouvrir(SP+"/img.pdf"); app.processEvents(); o=f.doc_courant()
R=[]
def verif(c,t):
    R.append(bool(c)); print("OK   " if c else "ECHEC", t)
verif("courriel" in o.barre_par_defaut(), "bouton Envoyer dans la barre")
f.lancer_outil("courriel"); app.processEvents()
p=o.panneau_envoi; verif(o.pile_volet.currentWidget() is p and p.l_tailles["tel_quel"].text().endswith("Ko"), "volet de droite avec le poids du fichier")
p.radios["allege"].setChecked(True); app.processEvents(); verif(p.l_tailles["allege"].text(), "poids de la version allegee")
f.params["comptes_mail"]=[dict(C.nouveau_compte(), id="x1", adresse="test@orange.fr", serveur="smtp.orange.fr", fournisseur="orange")]
coffre.enregistrer("mail_x1","secret")
p._remplir_comptes("x1"); p.r_compte.setChecked(True); app.processEvents()
p.a.setText("dest@exemple.fr"); p.cci.setText("Cache <cache@exemple.fr>"); p.r_direct.setChecked(True); p.valider()
while p._t.isRunning(): app.processEvents()
app.processEvents(); verif("envoyé" in p.etat.text() and ("send","dest@exemple.fr","img",["img.pdf"]) in envoyes, "envoi direct, PDF joint")
p.r_brouillon.setChecked(True); p.valider()
while p._t.isRunning(): app.processEvents()
app.processEvents(); verif(any(e[0]=="append" and e[1]=='"Brouillons"' for e in envoyes) and ("ouvrir","https://messagerie.orange.fr") in envoyes, "brouillon depose puis messagerie web ouverte")
from app import reglages
verif(("bcc", "cache@exemple.fr") in envoyes, "copie cachée (Cci) envoyée sans apparaître dans À")
verif(any(c["email"] == "cache@exemple.fr" and c["nom"] == "Cache" for c in f.params.get("carnet", [])),
      "nouvelles adresses ajoutées au carnet (avec le nom)")
from app import dialogues_courriel as DC
import time as _tm
lent = DC.lancer(lambda: _tm.sleep(1.5), lambda r: None)
dlg = DC.DialogueCompteMail(None); dlg.mdp.setText("x"); dlg.adresse.setText("a@orange.fr"); dlg.tester(); dlg.deleteLater(); del dlg
for _i in range(40):
    app.processEvents(); _tm.sleep(0.05)
verif(True, "fenêtre du compte fermée pendant le test de connexion : pas de plantage")
pass
import tempfile as _tf
vcf = os.path.join(_tf.mkdtemp(), "c.vcf"); open(vcf, "w").write("BEGIN:VCARD\nFN:Paul Durand\nEMAIL:paul@ex.fr\nEND:VCARD\n")
verif(C.ajouter_contacts(f.params, C.lire_contacts(vcf)) == 1, "import vCard dans le carnet")
verif("coffre:mail_x1" in reglages.instantane(f.params, True)["secrets"], "mot de passe suit les postes (chiffre)")
p.r_logiciel.setChecked(True); app.processEvents()
o.sp.setSizes([140, 900, 300]); app.processEvents()
tronques = [w.text() for w in p.findChildren(__import__("PySide6.QtWidgets", fromlist=["QAbstractButton"]).QAbstractButton)
            if w.isVisible() and w.text() and w.width() < w.sizeHint().width() - 2]
verif(not tronques, f"volet E-mail à 300 px : aucun bouton tronqué {tronques}")
if len(sys.argv) > 1: f.grab().save(sys.argv[1] + "/mail.png")
print(); print(f"{sum(R)}/{len(R)} vérifications d'envoi par e-mail réussies"); sys.exit(0 if all(R) else 1)
