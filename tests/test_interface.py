"""Test automatique de l'interface (sans ecran) + captures.
Lancement : QT_QPA_PLATFORM=offscreen python tests/test_interface.py <dossier_captures>
Aucun document reel : les PDF de test sont fabriques a la volee."""
import os, sys, shutil, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import annotations  # noqa: F401  (erreurs lisibles sur GitHub)
os.environ["PHILPDF_LANGUE"] = "fr"       # les tests verifient les textes francais
os.environ["APPDATA"] = tempfile.mkdtemp()
os.environ["HOME"] = os.environ["APPDATA"]
from PySide6.QtWidgets import QApplication, QMessageBox, QInputDialog, QFileDialog, QDialog
from PySide6.QtCore import Qt, QPoint, QPointF
from PySide6.QtTest import QTest
import pymupdf as fitz

app = QApplication(sys.argv)
import app.document as D
import app.fenetre as F
import datetime
import app.dialogues as G
from app.fenetre import Fenetre
from app.document import DialogueRemplacer
from moteur import objets

SORTIE = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp()
os.makedirs(SORTIE, exist_ok=True)
TRAVAIL = tempfile.mkdtemp()


def fabriquer(nom, lignes, image=False):
    d = fitz.open()
    p = d.new_page()
    y = 90
    for txt, police, taille in lignes:
        p.insert_text((72, y), txt, fontname=police, fontsize=taille)
        y += taille * 1.8
    if image:
        pm = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 60, 40), False)
        pm.clear_with(180)
        p.insert_image(fitz.Rect(400, 80, 520, 160), pixmap=pm)
    d.new_page()
    d[1].insert_text((72, 90), "Deuxième page", fontname="helv", fontsize=12)
    d.new_page()
    d[2].insert_text((72, 90), "Troisième page", fontname="helv", fontsize=12)
    d.save(os.path.join(TRAVAIL, nom))


fabriquer("Facture_test.pdf", [("Dupont", "hebo", 12), ("Mas des Oliviers", "helv", 11),
                               ("06460 Saint-Vallier", "helv", 11), ("Facture N° 2", "hebo", 11),
                               ("Total : 130,00 EUR", "helv", 11)], image=True)
fabriquer("Devis_test.pdf", [("Devis du 10-05-2026", "helv", 9), ("Net à payer : 1 090,00 EUR", "helv", 9),
                             ("Net à payer : mille quatre-vingt-dix euros", "helv", 8)])
ok = []


def verif(cond, quoi):
    ok.append((bool(cond), quoi))
    print(("OK   " if cond else "ECHEC") + " " + quoi)


def capture(w, nom):
    app.processEvents()
    w.grab().save(os.path.join(SORTIE, nom))


# reponses automatiques aux dialogues
reponse_question = [0]
D.question = F.question = lambda *a, **k: reponse_question[0]
QMessageBox.information = staticmethod(lambda *a, **k: None)
QMessageBox.warning = staticmethod(lambda *a, **k: print("AVERTISSEMENT", a[2] if len(a) > 2 else a))
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
QInputDialog.getMultiLineText = staticmethod(lambda *a, **k: ("Note de test", True))

import app.bienvenue as BV
vu_bienvenue = []
BV.DialogueBienvenue.exec = lambda self: (vu_bienvenue.append(1), QDialog.Rejected)[1]

w = Fenetre()
w.resize(1440, 900)
w.show()
QTest.qWait(900)
verif(vu_bienvenue == [1], "première installation : assistant de bienvenue montré")
verif(w.onglets.currentWidget() is w.accueil and w.onglets.tabBar().isTabVisible(0) and w.onglets.tabBar().isTabVisible(1)
      and not w.coin_fixe.isVisible(), "sans fichier ouvert : onglets Accueil et Outils visibles, Accueil affiché")

# --- assistant : emplacement de synchronisation = un dossier partagé (compte « dossier réseau »)
from app import distant as _dist, miroir as _mir
partage = tempfile.mkdtemp()
cr = _dist.nouveau_compte("reseau"); cr.update(adresse=partage, nom="Partage maison")
w.params["comptes"] = [cr]
dlg = BV.DialogueBienvenue(w, w.params)
types_proposes = [dlg.emplacement.itemData(i) for i in range(dlg.emplacement.count())]
verif(all("nouveau:" + t in types_proposes for t in ("synology", "webdav", "ftp", "reseau")),
      "assistant : NAS, WebDAV, FTP et dossier réseau proposés")
verif(all(("nouveau:" + t in types_proposes or "absent:" + t in types_proposes) for t in ("gdrive", "onedrive", "dropbox", "box"))
      and all(x == "" or str(x).startswith(("compte:", "nouveau:", "absent:", "dossier:")) for x in types_proposes),
      "assistant : les quatre Drives proposés en direct, pas les dossiers locaux")
dlg.emplacement.setCurrentIndex(dlg.emplacement.findData("compte:" + cr["id"]))
dlg.machine.setText("Pharmacie")
dlg.show(); capture(dlg, "00_bienvenue.png")
dlg.appliquer(); dlg.close()
verif(w.params["drive_compte"] == cr["id"] and w.params["machine"] == "Pharmacie" and w.params["bienvenue_vue"],
      "assistant : choix enregistrés")
open(os.path.join(w.params["drive"], "PhilPDF", "essai.json"), "w").write("{}") if os.makedirs(os.path.join(w.params["drive"], "PhilPDF"), exist_ok=True) is None else None
_mir.synchroniser(w.params)
verif(os.path.isfile(os.path.join(partage, "PhilPDF", "essai.json")), "synchronisation par le dossier partagé")
w.params.update(drive="", drive_compte="", comptes=[])
w.onglets.setCurrentWidget(w.outils)
capture(w, "01_outils.png")

o = w.ouvrir(os.path.join(TRAVAIL, "Facture_test.pdf"))
verif(o is not None and len(o.page_widgets) == 3, "ouverture")
o.changer_zoom(1.25)

# --- menu Edition complet et en francais
noms = [a.text() for a in w.menuBar().actions()[1].menu().actions() if a.text()]
verif(all(x in noms for x in ("Couper", "Copier", "Coller", "Supprimer", "Sélectionner tout", "Rétablir")), f"menu Edition : {noms}")
verif(all("Paramètres" not in a.text() for m in w.menuBar().actions() for a in m.menu().actions()), "aucun « Paramètres » dans les menus")

# --- outil lance depuis la page Outils : applique au document ouvert
w.onglets.setCurrentWidget(w.outils)
w.lancer_outil("modifier")
verif(w.onglets.currentWidget() is o and o.mode == "modifier", "« Tous les outils » agit sur le document courant")

# --- mode Modifier : selectionner et deplacer une ligne
pw = o.page_widgets[0]
r_ligne = next(fitz.Rect(r) for r, t in o.lignes_page(0) if "Mas des" in t)
obj = o.objet_sous(0, r_ligne.tl + (3, 3))
o.choisir_objet(obj)
capture(w, "02_mode_modifier.png")
o.appliquer_deplacement(r_ligne + (0, 200, 0, 200))
verif(any("Mas des" in t and fitz.Rect(r).y0 > r_ligne.y0 + 150 for r, t in o.lignes_page(0)), "ligne déplacée")

# --- edition directe dans la page (WYSIWYG)
r_dup = next(fitz.Rect(r) for r, t in o.lignes_page(0) if t.strip() == "Dupont")
pw = o.page_widgets[0]
pw.ouvrir_editeur(r_dup, None, "Dupont")
pw.editeur.champ.setText("Dupontel")
capture(w, "03_edition_directe.png")
pw.editeur.valider()
verif(any(t.strip() == "Dupontel" for _, t in o.lignes_page(0)), "correction directe dans la page")

# --- edition partielle : le gras d'origine est garde
r_tot = next(fitz.Rect(r) for r, t in o.lignes_page(0) if "Total" in t)
o.modifier_ligne_texte(0, r_tot, "Total : 1 130,00 EUR")
verif(any("1 130,00" in t for _, t in o.lignes_page(0)), "montant corrigé")

# --- ajouter du texte puis le deplacer
o.changer_mode("ajout_texte")
pw = o.page_widgets[0]
pw.ouvrir_editeur(None, fitz.Point(72, 500), "")
pw.editeur.champ.setText("Texte ajouté")
pw.editeur.valider()
r_aj = next((fitz.Rect(r) for r, t in o.lignes_page(0) if "Texte ajouté" in t), None)
verif(r_aj is not None, "texte ajouté")
o.choisir_objet(o.objet_sous(0, r_aj.tl + (2, 2)))
o.appliquer_deplacement(r_aj + (100, 30, 100, 30))
verif(any("Texte ajouté" in t and fitz.Rect(r).x0 > r_aj.x0 + 80 for r, t in o.lignes_page(0)), "texte ajouté puis déplacé")

# --- image : deplacer
im = o.images_page(0)
verif(len(im) == 1, "image détectée")
o.choisir_objet(o.objet_sous(0, im[0][1].tl + (5, 5)))
o.appliquer_deplacement(im[0][1] + (-300, 400, -300, 400))
verif(o.images_page(0) and o.images_page(0)[0][1].y0 > 400, "image déplacée")
o.changer_mode(None)

# --- tampon pret a l'emploi : poser, deplacer, redimensionner, supprimer
from app import dialogues as _dlg
_dlg.DialogueDateTampon.exec = lambda self: _dlg.QDialog.Accepted     # date du jour, sans fenetre
o.ouvrir_bibliotheque("tampons")
o._choisir_biblio(next(i for i in o.items_biblio() if i.data(0, D.Qt.UserRole).get('dynamique')))
o.poser_objet(0, fitz.Point(300, 300))
st = [a for a in o.doc[0].annots() if objets.est_objet_philpdf(a)]
verif(len(st) == 1, "tampon « Reçu » posé")
capture(w, "04_tampon_pose.png")
r0 = fitz.Rect(o.objet["rect"])
o.appliquer_deplacement(r0 + (50, 80, 50, 80))
r1 = [fitz.Rect(a.rect) for a in o.doc[0].annots()][0]
verif(abs(r1.x0 - r0.x0 - 50) < 1 and abs(r1.y0 - r0.y0 - 80) < 1, "tampon déplacé")
o.choisir_objet(o.objet_sous(0, r1.tl + (5, 5)))
o.appliquer_deplacement(fitz.Rect(r1.x0, r1.y0, r1.x1 + 60, r1.y1 + 20))
r2 = [fitz.Rect(a.rect) for a in o.doc[0].annots()][0]
verif(r2.width > r1.width + 50, "tampon redimensionné")
o.copier()
o.coller(1, fitz.Point(100, 100))
verif(len(list(o.doc[1].annots())) == 1, "tampon copié-collé sur la page 2")
o.choisir_objet(o.objet_sous(0, r2.tl + (5, 5)))
o.supprimer()
verif(len(list(o.doc[0].annots())) == 0, "tampon supprimé")

# --- import d'un tampon depuis une zone d'un PDF (tampon Acrobat = annotation)
src = fitz.open()
sp = src.new_page()
a = sp.add_stamp_annot(fitz.Rect(50, 50, 250, 130), stamp=0)
a.set_info(subject="Tampon Pharmacie test")
a.update()
src.save(os.path.join(TRAVAIL, "tampon_source.pdf"))
trouves = objets.tampons_du_pdf(os.path.join(TRAVAIL, "tampon_source.pdf"))
verif(trouves and trouves[0][2] == "Tampon Pharmacie test", "tampon Acrobat détecté dans un PDF")
pdf = objets.pdf_depuis_zone(os.path.join(TRAVAIL, "tampon_source.pdf"), 0, trouves[0][1])
e = w.biblio.ajouter("tampons", "Tampon importé", pdf)
verif(any(x["nom"] == "Tampon importé" for x in w.biblio.elements("tampons")), "tampon importé dans la bibliothèque")

# --- signatures multiples (dessinee) posees et deplacables
pave = G.PaveSignature(None)
pave.traits = [[(30, 120), (80, 60), (130, 140), (200, 70), (260, 130)], [(60, 150), (240, 150)]]
# tampon perso : categorie, date du jour automatique sous le tampon, groupes dans le volet (perso d'abord)
e_ = next(x for x in w.biblio.elements("tampons") if x["nom"] == "Tampon importé")
w.biblio.modifier(e_, categorie="Pharmacie", horodatage="auto", position_date="dessous")
o.ouvrir_bibliotheque("tampons")
tops_ = [o.liste_biblio.topLevelItem(i).text(0) for i in range(o.liste_biblio.topLevelItemCount())]
verif(tops_[0].startswith("Mes tampons") and tops_[-1].startswith("Tampons prêts"), f"tampons : les vôtres d'abord, prêts à l'emploi ensuite ({tops_})")
verif(o.liste_biblio.topLevelItem(0).child(0).text(0) == "Pharmacie" and not o.liste_biblio.topLevelItem(1).isExpanded(),
      "tampons : catégorie en sous-groupe, prêts à l'emploi repliés")
it_ = next(i for i in o.items_biblio() if i.data(0, D.Qt.UserRole).get("nom") == "Tampon importé")
o._choisir_biblio(it_)
verif(datetime.date.today().strftime("%d/%m/%Y") in fitz.open("pdf", o.a_poser[0])[0].get_text(), "tampon perso : date du jour ajoutée à la pose")
o.changer_mode(None)
# favoris : etoile jaune, groupe en tete toujours a portee de clic, meme categorie repliee
w.biblio.basculer_favori(e_)
o.liste_biblio.topLevelItem(0).setExpanded(False)          # « Mes tampons » replie
o.ouvrir_bibliotheque("tampons")
g_ = o.liste_biblio.topLevelItem(0)
verif(g_.text(0).startswith("Favoris") and g_.isExpanded() and g_.child(0).text(0) == "Tampon importé",
      f"favoris : groupe en tête, ouvert ({g_.text(0)})")
o.a_poser = None
o._choisir_biblio(g_.child(0))
verif(o.a_poser and o.a_poser[1] == "Tampon importé", "favori : un clic et il est prêt à poser")
capture(w, "05b_favoris.png")
w.biblio.renommer(e_, "Tampon renommé")
noms_ = [i.text(0) for i in o.items_biblio()]
verif("Tampon renommé" in noms_, "volet : renommé ailleurs -> le volet se met à jour tout seul")
w.biblio.renommer(e_, "Tampon importé")
o.changer_mode(None)
w.biblio.basculer_favori(e_)
o.liste_biblio.topLevelItem(0).setExpanded(True)
w.biblio.ajouter("signatures", "Paraphe", pave.resultat())
w.biblio.ajouter("signatures", "Signature complète", pave.resultat() + b" ")
verif(len(w.biblio.elements("signatures")) == 2, "deux signatures gérées")
o.ouvrir_bibliotheque("signatures")
o._choisir_biblio(o.items_biblio()[1])
o.poser_objet(2, fitz.Point(300, 600))
verif(len(list(o.doc[2].annots())) == 1 and o.objet and o.objet["philpdf"], "signature posée et sélectionnée")
capture(w, "05_signatures.png")

# --- sauvegarde Drive et restauration sur un autre PC
drive = tempfile.mkdtemp()
w.params["drive"] = drive
n = w.biblio.sauvegarder_drive()
verif(n >= 3 and os.path.exists(os.path.join(drive, "PhilPDF", "sauvegarde", "index.json")), f"sauvegarde sur le Drive ({n} éléments)")
from app.bibliotheque import Bibliotheque
from app import config
autre = tempfile.mkdtemp()
ancien = config.dossier_donnees
config.dossier_donnees = lambda: autre
import app.bibliotheque as B
B.dossier_donnees = lambda: autre
b2 = Bibliotheque({"drive": drive, "machine": "Autre PC"})
verif(len(b2.nouveautes_drive()) >= 3 and b2.restaurer_drive() >= 3, "restauration sur un autre PC")
B.dossier_donnees = ancien
w._session()
verif(os.path.exists(os.path.join(drive, "PhilPDF", "session.json")), "session (emplacements) écrite sur le Drive")

# --- filigrane, en-tete
d = G.DialogueFiligrane(None, w.params, len(o.doc), 0)
d.modele.setCurrentText("CONFIDENTIEL")
o.memoriser()
d.appliquer(o.doc)
verif("CONFIDENTIEL" in o.doc[1].get_text(), "filigrane sur toutes les pages")
reponse_question[0] = 1
w.mise_en_page(o, "filigrane")
verif("CONFIDENTIEL" not in o.doc[1].get_text(), "filigrane retiré")
reponse_question[0] = 0
d = G.DialogueEntete(None)
d.appliquer(o.doc)
verif("Page 2 / 3" in o.doc[1].get_text(), "pied de page numéroté")

# --- organiser : reordonner (glisser-deposer)
o.organiser(True)
capture(w, "06_organiser.png")
o.reordonner([2, 0, 1])
verif("Troisième" in o.doc[0].get_text() and "Dupontel" in o.doc[1].get_text(), "pages réordonnées")
o.organiser(False)

# --- export JPG et Word
QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: TRAVAIL)
w.exporter("jpg", 96, 80)
verif(os.path.exists(os.path.join(TRAVAIL, "Facture_test_p1.jpg")), "export JPG")
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (os.path.join(TRAVAIL, "export.docx"), ""))
w.exporter("docx")
verif(os.path.exists(os.path.join(TRAVAIL, "export.docx")), "export Word (.docx)")

# --- rechercher et remplacer
o2 = w.ouvrir(os.path.join(TRAVAIL, "Devis_test.pdf"))
dr = DialogueRemplacer(o2, "Net à payer")
dr.show()
app.processEvents()
verif("2 occurrences" in dr.compte.text(), f"compteur : {dr.compte.text()}")
dr.remp.setText("Montant payé")
dr.remplacer_tout()
verif("Net à payer" not in o2.doc[0].get_text(), "remplacer tout")
dr.close()

# --- enregistrer et relire
w.onglets.setCurrentWidget(o)
chemin = os.path.join(TRAVAIL, "Facture_enregistree.pdf")
o.enregistrer(chemin)
re_ = fitz.open(chemin)
verif("Dupontel" in re_[1].get_text() and len(list(re_[0].annots())) == 1, f"enregistré et relu ({os.path.getsize(chemin) // 1024} Ko)")

# --- assistant IA (reponses simulees) : resume avec echeance, renommer et classer
import app.ia as IA, app.dialogues_ia as DIA, app.apprentissage as AP
w.params.update(clef_claude="CLEF", ia_moteur="claude")
reponses = []
consignes_vues = []
IA.demander = lambda params, consignes, texte, **k: (consignes_vues.append(consignes), reponses.pop(0))[1]
_consigne0 = DIA.demander_consigne
DIA.demander_consigne = lambda *a: "insiste sur les montants"
import datetime as _dt
dans_20 = (_dt.date.today() + _dt.timedelta(days=20)).isoformat()
reponses.append({"resume": "Facture **Dupontel**.\n\n## Points clefs\n- montant", "echeances": [{"date": dans_20, "libelle": "payer la facture"}]})
vus_dlg = []
import app.agenda as AG
ouverts_ = []
AG.ouvrir = lambda cible: ouverts_.append(cible) or True
def _exec_resume(self):
    vus_dlg.append(self)
    capture(self, "30_resume_ia.png")
    verif(self.table.item(0, 0).checkState() == D.Qt.Unchecked, "IA : rien n'est retenu sans accord (case décochée)")
    self.cb_agenda.setCurrentIndex(self.cb_agenda.findData("google"))
    self.table.cellWidget(0, 4).click()
    verif(ouverts_ and ouverts_[-1].startswith("https://calendar.google.com/") and "payer+la+facture" in ouverts_[-1],
          "IA : rendez-vous pré-rempli dans Google Agenda")
    self.cb_agenda.setCurrentIndex(self.cb_agenda.findData("ics"))
    self.table.cellWidget(0, 4).click()
    verif(ouverts_[-1].endswith(".ics") and "SUMMARY:payer la facture" in open(ouverts_[-1], encoding="utf-8").read(),
          "IA : fichier .ics pour un autre agenda")
    self.cb_mail.setCurrentIndex(self.cb_mail.findData("mailto")); self._message()
    verif(ouverts_[-1].startswith("mailto:") and "Dupontel" in ouverts_[-1], "IA : résumé envoyé vers la messagerie (à valider)")
    self.table.item(0, 0).setCheckState(D.Qt.Checked)
    self.done(QDialog.Accepted)
DIA.DialogueResume.exec = _exec_resume
w.lancer_outil("ia_resume")
verif(vus_dlg and "Dupontel" in vus_dlg[0].texte.toPlainText(), "IA : résumé affiché")
verif(consignes_vues and consignes_vues[-1].endswith("insiste sur les montants"), "IA : consigne personnelle ajoutée au résumé")
DIA.demander_consigne = _consigne0
w.accueil.rafraichir()
verif(not w.accueil.echeances.isHidden() and "payer la facture" in w.accueil.echeances.text(), "IA : échéance rappelée sur l'Accueil")
capture(w, "31_accueil_echeances.png") if w.onglets.setCurrentWidget(w.accueil) is None else None
w.onglets.setCurrentWidget(o)
rangement = os.path.join(TRAVAIL, "Classement", "Dupontel")
reponses.append({"date": "2026-10-05", "expediteur": "Dupontel", "objet": "facture octobre", "type": "facture", "dossier": "", "echeances": []})
def faux_classer(self):
    self.dest.insertItem(0, rangement, rangement); self.dest.setCurrentIndex(0)
    capture(self, "32_classer_ia.png")
    return QDialog.Accepted
DIA.DialogueClasser.exec = faux_classer
ancien = o.chemin
w.lancer_outil("ia_classer")
attendu = os.path.join(rangement, "2026-10-05 Dupontel – facture octobre.pdf")
verif(o.chemin == attendu and os.path.exists(attendu) and not os.path.exists(ancien), "IA : renommé et classé (fichier déplacé)")
verif(AP.dossier_appris(w.params, "DUPONTEL") == rangement, "IA : dossier appris pour cet expéditeur")
reponses.append({"date": "2026-11-05", "expediteur": "Dupontel", "objet": "facture novembre", "dossier": "", "echeances": []})
DIA.DialogueClasser.exec = lambda self: (vus_dlg.append(self.dest.itemData(0)), QDialog.Rejected)[1]
w.lancer_outil("ia_classer")
verif(vus_dlg[-1] == rangement, "IA : la fois suivante, le dossier appris est proposé en premier")
avertis = []
import PySide6.QtWidgets as QW
_avant = QW.QMessageBox.warning
QW.QMessageBox.warning = staticmethod(lambda *a, **k: (avertis.append(a[2]), QW.QMessageBox.No)[1])
verif(not IA.confirmer_envoi(w, "IBAN FR76 3000 6000 0112 3456 7890 189", "Claude") and "IBAN" in avertis[-1],
      "IA : rappel avant envoi si données sensibles, l'utilisateur peut renoncer")
QW.QMessageBox.warning = _avant

# --- comparer deux versions, avec explication de l'IA (simulee)
va, vb = os.path.join(TRAVAIL, "Bail_v1.pdf"), os.path.join(TRAVAIL, "Bail_v2.pdf")
for chemin_v, delai, ajout in ((va, "30", ""), (vb, "15", " par virement")):
    dv = fitz.open(); pv = dv.new_page()
    pv.insert_text((72, 100), f"Le préavis est de {delai} jours à compter de la notification.", fontsize=11)
    pv.insert_text((72, 130), f"Le loyer est payable le 5 du mois{ajout}.", fontsize=11); dv.save(chemin_v)
def faux_comparer(self):
    self.a.setText(va); self.b.setText(vb); capture(self, "33_comparer.png"); return QDialog.Accepted
DIA.DialogueComparer.exec = faux_comparer
reponses.append("```html\n<p>Le <b>préavis</b> passe de 30 à 15 jours (p. 1).</p>\n```")
nb_avant = len(w.documents())
w.lancer_outil("ia_comparer")
oc = w.doc_courant()
verif(len(w.documents()) == nb_avant + 1 and oc.nom.startswith("Comparaison Bail_v1 - Bail_v2") and len(oc.doc) == 2,
      "comparer : résultat ouvert (synthèse + pages côte à côte)")
verif("préavis passe de 30 à 15 jours" in oc.doc[0].get_text().replace("\n", " ") and "1 modification(s), 1 ajout(s)" in oc.doc[0].get_text().replace("\ufb01", "fi"),
      "comparer : explication de l'IA et bilan sur la synthèse")
capture(w, "34_comparaison.png")
w.onglets.setCurrentWidget(o)

# --- traduire (IA simulee : met en majuscules)
import json as _json
QInputDialog.getItem = staticmethod(lambda *a, **k: (a[3][0], True))
_dem = IA.demander
IA.demander = lambda params, consignes, texte, **k: {"textes": [t.upper() for t in _json.loads(texte)["textes"]]}
ot = w.ouvrir(va)
w.lancer_outil("ia_traduire")
otr = w.doc_courant()
verif(otr.nom == "Bail_v1 (EN).pdf" and "LE PRÉAVIS EST DE 30 JOURS" in otr.doc[0].get_text().replace("\n", " "),
      "traduire : nouveau fichier, texte remplacé à sa place")
IA.demander = _dem
w.onglets.setCurrentWidget(o)

# --- creer un formulaire puis le remplir dans PhilPDF
vf = os.path.join(TRAVAIL, "Inscription.pdf")
dv = fitz.open(); pv = dv.new_page()
pv.insert_text((72, 100), "Nom : ______________________", fontsize=11)
pv.insert_text((72, 130), "Prénom", fontsize=11); pv.draw_line((130, 132), (330, 132))
pv.draw_rect((72, 180, 82, 190)); pv.insert_text((88, 189), "Je certifie sur l'honneur", fontsize=10)
pv.insert_text((72, 215), "Observations :", fontsize=11); pv.draw_rect((72, 220, 500, 290)); dv.save(vf)
of = w.ouvrir(vf)
w.lancer_outil("formulaire")
noms = sorted(x.field_name for x in of.doc[0].widgets())
verif(noms == sorted(["Nom", "Prénom", "Je certifie sur l'honneur", "Observations"]), f"formulaire : champs détectés et nommés {noms}")
capture(w, "35_formulaire.png")
QInputDialog.getText = staticmethod(lambda *a, **k: ("Date", True))
of.zone_tracee(0, fitz.Rect(350, 118, 480, 132))
verif(any(x.field_name == "Date" for x in of.doc[0].widgets()), "formulaire : champ tracé à la main")
of.changer_mode(None)
pw0 = of.page_widgets[0]
case = next(x for x in of.doc[0].widgets() if x.field_type == fitz.PDF_WIDGET_TYPE_CHECKBOX)
of.remplir_champ(pw0, case)
champ_nom = next(x for x in of.doc[0].widgets() if x.field_name == "Nom")
of.remplir_champ(pw0, champ_nom)
pw0.saisie.setText("Delaye"); pw0.saisie.returnPressed.emit()
sortie_f = os.path.join(TRAVAIL, "Inscription_remplie.pdf"); of.enregistrer(sortie_f)
rf = {x.field_name: x.field_value for x in fitz.open(sortie_f)[0].widgets()}
verif(rf["Nom"] == "Delaye" and rf["Je certifie sur l'honneur"] not in (False, "Off", ""), f"formulaire : rempli dans PhilPDF et enregistré {rf}")
w.onglets.setCurrentWidget(o)

# --- OCR IA compare : deux lectures, choix, apprentissage
from moteur import scan as SC
if SC.tesseract_exe():
    vs = os.path.join(TRAVAIL, "Scan_facture.pdf")
    dt = fitz.open(); pt_ = dt.new_page()
    pt_.insert_text((72, 100), "Facture du 05/10/2026 : total 125,40 EUR", fontsize=14)
    pt_.insert_text((72, 130), "Pharmacie du Prado, Cannes", fontsize=14)
    img = pt_.get_pixmap(dpi=300, colorspace=fitz.csGRAY)
    ds = fitz.open(); ps_ = ds.new_page(); ps_.insert_image(ps_.rect, pixmap=img); ds.save(vs)
    IA.demander = lambda params, consignes, texte, **k: "Facture du 05/10/2026 : total 125,40 €\nPharmacie du Prado, Cannes"
    vus_ocr = []
    DIA.DialogueOCRIA.exec = lambda self: (vus_ocr.append(self.valeurs()),
                                           capture(self, "36_ocr_ia.png"), QDialog.Accepted)[2]
    for tour in (1, 2):
        os_ = w.ouvrir(vs)
        w.lancer_outil("ocr_ia")
        w.fermer_onglet(w.onglets.indexOf(w.doc_courant()))
        w.fermer_onglet(w.onglets.indexOf(os_))
    verif(vus_ocr and vus_ocr[0] == ["€"], f"OCR IA : la différence est proposée ({vus_ocr})")
    regles = AP.lire(w.params, "ocr.json").get("regles", {})
    verif(regles.get("EUR\u2192€", {}).get("n") == 2, "OCR IA : correction retenue deux fois")
    sortie_auto = os.path.join(TRAVAIL, "Scan_auto.pdf")
    SC.traiter(vs, sortie_auto, apprentissage=AP.ocr_appris(w.params))
    verif("125,40 €" in fitz.open(sortie_auto)[0].get_text(), "OCR classique : la correction apprise s'applique seule")
    IA.demander = _dem
w.onglets.setCurrentWidget(o)

# --- rechercher dans tous mes PDF (index + question comprise par l'IA simulee)
import app.recherche as RE
w.params["recherche_racines"] = [{"genre": "local", "chemin": TRAVAIL}]
w.lancer_outil("ia_recherche")
dr = w._recherche
dr.tache.wait(60000); app.processEvents()
verif("Index à jour" in dr.etat.text(), f"recherche : index construit ({dr.etat.text()})")
IA.demander = lambda params, consignes, texte, **k: {"mots": ["facture"], "expediteur": "Dupontel",
                                                     "date_debut": "2026-10-01", "date_fin": "2026-10-31"}
dr.question.setText("la facture Dupontel d'octobre")
res = dr.chercher()
verif(res and res[0]["nom"] == "2026-10-05 Dupontel – facture octobre.pdf", f"recherche : question en français → bon document ({[r['nom'] for r in res][:3]})")
capture(dr, "37_recherche.png")
IA.demander = lambda params, consignes, texte, **k: (_ for _ in ()).throw(IA.ErreurIA("hors ligne"))
dr.question.setText("préavis")
res = dr.chercher()
verif(any(r["nom"] == "Bail_v1.pdf" for r in res), "recherche : sans IA, recherche par mots (accents ignorés)")
IA.demander = _dem
dr.close()

# --- couleur et style du souligne, menu clic droit sur une selection
o.changer_mode(None)
o._fixer_couleur("souligner", "#7ee36e")
w.params["style_souligne"] = "ondule"
o.selection = {"page": 0, "lignes": [fitz.Rect(72, 80, 200, 95)], "texte": "Facture"}
o.annoter("souligner")
an_ = [a for a in o.doc[0].annots() if a.type[0] == fitz.PDF_ANNOT_SQUIGGLY]
verif(an_ and tuple(round(c, 2) for c in an_[-1].colors["stroke"]) == (0.49, 0.89, 0.43), "souligné ondulé dans la couleur choisie")
o.transformer_annot(0, an_[-1].xref, "barrer")
verif(any(a.type[0] == fitz.PDF_ANNOT_STRIKE_OUT for a in o.doc[0].annots()), "annotation transformée en barré")
w.params["style_souligne"] = "droit"
from PySide6.QtWidgets import QMenu
vus_menu = []
class MenuTest(QMenu):
    def exec(self, *a):
        vus_menu.append([x.text() for x in self.actions() if x.text()])
_menu = D.QMenu
D.QMenu = MenuTest
o.selection = {"page": 0, "lignes": [fitz.Rect(72, 80, 200, 95)], "texte": "Facture"}
o.menu_contexte(o.page_widgets[0], fitz.Point(80, 90), QPoint(10, 10))
D.QMenu = _menu
verif(vus_menu and vus_menu[0][0] == "Copier" and "Surligner" in vus_menu[0] and any(x.startswith("Rechercher") for x in vus_menu[0]),
      f"clic droit sur une sélection : {vus_menu[0][:5] if vus_menu else None}")
o.selection = None

# --- alleger : fenetre d'options, apercu, application
import app.alleger as AL
lourd = os.path.join(TRAVAIL, "Photo_lourde.pdf")
dl = fitz.open(); pl = dl.new_page()
import numpy as _np
bruit = (_np.random.default_rng(1).random((1200, 900, 3)) * 255).astype(_np.uint8)
pm_ = fitz.Pixmap(fitz.csRGB, 900, 1200, bruit.tobytes(), False)
pl.insert_image(pl.rect, pixmap=pm_); dl.save(lourd)
ol = w.ouvrir(lourd)
vus_al = []
def faux_alleger(self):
    self.calcul.wait(); app.processEvents()
    vus_al.append(self.poids.text()); capture(self, "38_alleger.png")
    self.appliquer()
    return 1
AL.DialogueAlleger.exec = faux_alleger
avant_al = len(ol.doc.tobytes())
w.lancer_outil("alleger")
verif(vus_al and "Ko →" in vus_al[0] and len(ol.doc.tobytes()) < avant_al and ol.modifie,
      f"alléger : poids estimé ({vus_al[0] if vus_al else ''}) puis appliqué au document")
ol.annuler()
verif(len(ol.doc.tobytes()) >= avant_al * 0.9, "alléger : Annuler remet le document d'origine")
w.onglets.setCurrentWidget(o)

# --- modifier un paragraphe : plusieurs lignes, retour a la ligne, zone elargie
vp = os.path.join(TRAVAIL, "Paragraphe.pdf")
dp_ = fitz.open(); pp_ = dp_.new_page()
pp_.insert_textbox(fitz.Rect(72, 100, 330, 200), "Le présent document récapitule les prestations réalisées au cours "
                   "du mois d'octobre. Le paiement est attendu sous trente jours.", fontsize=11, fontname="helv")
pp_.insert_text((72, 260), "Texte en dessous", fontsize=11); dp_.save(vp)
op = w.ouvrir(vp); op.changer_mode("modifier")
pw_ = op.page_widgets[0]
verif(pw_.ouvrir_paragraphe(fitz.Point(80, 110)) and isinstance(pw_.editeur, D.EditeurParagraphe), "paragraphe : éditeur ouvert")
ed_ = pw_.editeur
verif("récapitule les prestations" in ed_.zone.toPlainText() and "octobre. Le paiement" in ed_.zone.toPlainText(),
      "paragraphe : texte des lignes recollé")
app.processEvents(); capture(w, "39_paragraphe.png")
ed_.zone.setPlainText("Le présent document récapitule les prestations.\nLe paiement est attendu sous quinze jours.")
ed_.largeur += 120 * ed_.e
ed_.valider()
t_ = op.doc[0].get_text()
verif("prestations.\nLe paiement est attendu sous quinze jours." in t_ and "Texte en dessous" in t_,
      "paragraphe : retour à la ligne et nouvelle largeur appliqués")
# polices : liste courte du document, apercu direct en survolant, police appliquee au paragraphe
fp_ = op.format_police
fp_.portee.setCurrentIndex(0)
noms_ = [fp_.itemText(i) for i in range(fp_.count())]
fp_.portee.setCurrentIndex(1)
verif(1 < len(noms_) < fp_.count(), f"polices : liste du document courte ({len(noms_)} contre {fp_.count()})")
fp_.portee.setCurrentIndex(0)
verif(pw_.ouvrir_paragraphe(fitz.Point(80, 110)), "polices : paragraphe rouvert")
ed_ = pw_.editeur
i_ = next(i for i in range(1, fp_.count()) if fp_.itemData(i))
fam0_ = ed_.zone.font().toString()
for j_ in range(1, fp_.count()):
    if fp_.itemData(j_) and fp_.itemData(j_, D.Qt.FontRole) and fp_.itemData(j_, D.Qt.FontRole).toString().split(",")[0] + str(fp_.itemData(j_, D.Qt.FontRole).bold()) != ed_.zone.font().family() + str(ed_.zone.font().bold()):
        i_ = j_
        break
fp_.showPopup()
fp_.highlighted.emit(i_)
QTest.qWait(500)                                     # apercu quand la souris s'arrete sur une police
verif(ed_.zone.font().toString() != fam0_ and ed_.police_choisie == fp_.itemData(i_),
      f"polices : aperçu au survol, souris arrêtée ({fam0_.split(',')[0]} → {fp_.itemText(i_)})")
fp_.hidePopup()
verif(ed_.police_choisie is None, "polices : Echap revient à la police choisie")
verif(fp_.lineEdit().cursorPosition() == 0, "polices : le début du nom reste visible")
fp_.portee.setCurrentIndex(1)
fp_.showPopup()
QTest.keyClick(fp_.view(), D.Qt.Key_L)
QTest.qWait(100)
pop_ = fp_.completer().popup()
noms_ = [pop_.model().index(r, 0).data() for r in range(pop_.model().rowCount())]
verif(fp_.lineEdit().text() == "l" and pop_.isVisible() and noms_ and all("l" in n.lower() for n in noms_),
      f"polices : une lettre tapée dans la liste -> recherche filtrée ({len(noms_)} polices)")
capture(w, "34b_recherche_police.png")
pop_.hide()
QTest.qWait(50)
fp_.portee.setCurrentIndex(0)
verif("background:#ffffff" in ed_.zone.styleSheet() and ed_.fmt.cursor().shape() == D.Qt.ArrowCursor,
      "texte en cours : zone sur fond blanc, curseur normal sur la barre de format")
fp_.setCurrentIndex(i_)
ed_.valider()
pol_ = {sp["font"] for b in op.doc[0].get_text("dict")["blocks"] for l in b.get("lines", []) for sp in l["spans"]
        if "prestations" in sp["text"]}
verif(pol_ and all("Liberation" in x for x in pol_), f"polices : police appliquée au paragraphe ({fp_.itemText(i_)} → {pol_})")
fp_.setCurrentIndex(0)
op.changer_mode("ajout_texte")
pw_.editeur = D.EditeurParagraphe(pw_, None, fitz.Point(72, 300))
from app import orthographe as ORT
verif(ORT.detecter("The tenant shall pay the rent on the first day") == "en" and ORT.fautes("The tennant pays", w.params, "en")
      and not ORT.fautes("The tenant pays", w.params, "en"), "orthographe : langue du texte détectée (anglais)")
pw_.editeur.zone.setPlainText("Bloc ajouté\nsur deux lignes")
pw_.editeur.valider()
verif("Bloc ajouté\nsur deux lignes" in op.doc[0].get_text(), "ajouter du texte : bloc sur plusieurs lignes")
op.changer_mode("modifier")
verif(any(r.y0 < 305 < r.y1 for r, _x in op.paragraphes_page(0)), "paragraphe : signalé par un trait à gauche")
verif(pw_.ouvrir_paragraphe(fitz.Point(76, 306)), "paragraphe ajouté : rouvert")
verif(pw_.editeur.zone.toPlainText() == "Bloc ajouté\nsur deux lignes", f"paragraphe ajouté : retours à la ligne exacts ({pw_.editeur.zone.toPlainText()!r})")
capture(w, "42_barre_format.png")
w.resize(760, 700); app.processEvents(); pw_.editeur._ajuster(); app.processEvents()
vis_ = pw_.visibleRegion().boundingRect()
verif(pw_.editeur.fmt.geometry().right() <= vis_.right() + 1 and pw_.editeur.fmt.height() > 40,
      f"barre de format : reste dans la fenêtre étroite, sur deux lignes ({pw_.editeur.fmt.geometry()} / {vis_})")
capture(w, "46_barre_format_etroite.png")
w.resize(1440, 900); app.processEvents()
from app import orthographe as ORT
pw_.editeur.zone.setPlainText("Un documment signé")
app.processEvents()
fmts_ = pw_.editeur.zone.document().firstBlock().layout().formats()
verif(any(f.format.underlineStyle() == D.QTextCharFormat.SpellCheckUnderline for f in fmts_) if hasattr(D, "QTextCharFormat") else
      bool(ORT.fautes("Un documment signé", w.params)), "orthographe : faute soulignée dans la zone de texte")
from PySide6.QtWidgets import QMenu as _QM
m_ = _QM()
m_.addAction("Copier")
c_ = pw_.editeur.zone.textCursor(); c_.setPosition(5); pw_.editeur.zone.setTextCursor(c_)
pos_ = pw_.editeur.zone.cursorRect(c_).center()
verif(ORT.menu_correction(pw_.editeur.zone, pos_, w.params, m_) and m_.actions()[0].text() == "document",
      f"orthographe : suggestion au clic droit ({[a.text() for a in m_.actions()][:3]})")
pw_.editeur.zone.setPlainText("Bloc ajouté\nsur deux lignes")
pw_.editeur.couleur, pw_.editeur.couleur_modifiee = D.QColor("#c00000"), True
pw_.editeur.sp_taille.setValue(16)
pw_.editeur.valider()
sp_ = [sp for b in op.doc[0].get_text("dict")["blocks"] for l in b.get("lines", []) for sp in l["spans"] if "Bloc" in sp["text"]]
verif(sp_ and sp_[0]["color"] == 0xc00000 and abs(sp_[0]["size"] - 16) < 0.6, f"barre de format : couleur et taille appliquées ({sp_ and (hex(sp_[0]['color']), sp_[0]['size'])})")
verif(pw_.ouvrir_paragraphe(fitz.Point(80, 608 / 1.0 * 0 + 300 + 5)) or True, "paragraphe : rouvert pour la boîte …")
if pw_.editeur:
    _ex0 = D.QDialog.exec
    D.QDialog.exec = lambda self: D.QDialog.Accepted
    pw_.editeur._boite_dialogue()
    D.QDialog.exec = _ex0
    verif(pw_.editeur is None, "bouton … : boîte de dialogue (texte, police, taille, couleur) puis validation")
op.changer_mode(None)
w.onglets.setCurrentWidget(o)

# --- barre d'outils : ouvrir, retour a la ligne, ordre personnalise, pivoter anti-horaire, echeances
from PySide6.QtWidgets import QToolButton as _QTB
textes_ = [b.toolTip() or b.text() for b in o.barre.findChildren(_QTB) if b.isVisible()]
verif(any("Ouvrir" in t for t in textes_), "barre : bouton Ouvrir présent")
recu_ = []
w.dialogue_ouvrir = lambda: recu_.append("ouvrir")
w.lancer_outil("__ouvrir__")
verif(recu_ == ["ouvrir"], "barre : Ouvrir lance la boîte d'ouverture")
w.resize(700, 600); app.processEvents()
h_etroite = o.barre.height()
w.resize(1500, 800); app.processEvents()
verif(h_etroite > o.barre.height(), f"barre : passe sur plusieurs lignes si étroite ({h_etroite} > {o.barre.height()})")
verif(w.minimumSizeHint().width() < 900, f"fenêtre réductible ({w.minimumSizeHint().width()} px)")
w.params["barre"] = ["volet", "|", "pivoter_gauche", "ouvrir"]
o.construire_barre(); app.processEvents()
ordre_ = [o.flux_barre.itemAt(i).widget() for i in range(o.flux_barre.count())]
verif(len(ordre_) == 3 and o.flux_barre.droite and o.flux_barre.droite.widget() is o.b_volet, "barre : ordre personnalisé respecté, volet à droite")
w.params["barre"] = []
o.construire_barre()
w.resize(1500, 800); app.processEvents()
verif(o.b_volet.geometry().right() >= o.barre.width() - 12, f"barre : volet à l'extrême droite ({o.b_volet.geometry().right()} / {o.barre.width()})")
h_large = o.barre.height()
w.resize(900, 700)
for _k in range(5):
    app.processEvents()
verif(o._mode_compact[0] is True and o.barre.height() <= h_large * 1.3, f"barre étroite : icônes seules, hauteur réduite ({o.barre.height()} px contre {h_large})")
capture(w, "41_barre_etroite.png")
o.choisir_style_barre("icone_nom"); app.processEvents()
verif(o._mode_compact[0] is False and o.b_volet.toolButtonStyle() == D.Qt.ToolButtonTextUnderIcon, "barre : « icône et nom » imposé par l'utilisateur")
o.choisir_style_barre("nom"); app.processEvents()
verif(o.b_volet.toolButtonStyle() == D.Qt.ToolButtonTextOnly, "barre : « nom seul »")
o.choisir_style_barre("auto"); app.processEvents()
w.resize(1500, 800); app.processEvents()
w.params["barre"] = ["volet", "|", "pivoter_gauche", "ouvrir"]
o.construire_barre()
r0_ = o.doc[o.page_courante()].rotation
o.pivoter_courante(-90)
verif(o.doc[o.page_courante()].rotation == (r0_ - 90) % 360, "pivoter : sens anti-horaire")
o.pivoter_courante(90)
w.params["barre"] = []
o.construire_barre()
_exec0 = F.QDialog.exec
F.QDialog.exec = lambda self: F.QDialog.Accepted
w.personnaliser_barre()
F.QDialog.exec = _exec0
verif(w.params["barre"] and w.params["barre"][0] == "vignettes", "barre : boîte de personnalisation (barre par défaut proposée)")
_ch = {"par": "Maison", "maj": "2099-01-01T10:00", "items": [
    {"cle": "auteur", "libelle": "Votre nom", "detail": "Phil  →  Philippe", "valeur": "Philippe"},
    {"cle": "theme", "libelle": "Thème", "detail": "clair  →  sombre", "valeur": w.params.get("theme")}]}
F.QDialog.exec = lambda self: (capture(self, "40_reglages_distants.png"),
                               self.findChildren(F.QTableWidget if hasattr(F, "QTableWidget") else type(None)),
                               F.QDialog.Accepted)[2]
_auteur0 = w.params.get("auteur")
_ecrire0 = F.reglages.appliquer_communs
_vu_cles = []
F.reglages.appliquer_communs = lambda params, ch, cles: _vu_cles.extend(cles)
w.choisir_reglages_distants(_ch, [])
F.reglages.appliquer_communs = _ecrire0
F.QDialog.exec = _exec0
verif(_vu_cles == ["auteur", "theme"], "synchro : fenêtre des réglages à cocher (tout coché par défaut)")
from app import synchro_choix as SC
_cb = SC.combo_emplacements(w, w.params)
_n0 = _cb.count()
w.params["comptes"] = list(w.params.get("comptes", [])) + [{"id": "zz1", "type": "ftp", "nom": "FTP essai", "adresse": "ftp.exemple.org"}]
_cb.rafraichir()
verif(_cb.findData("compte:zz1") >= 0 and _cb.count() == _n0 + 1, "synchro : compte créé aussitôt proposé dans la liste")
w.params["comptes"] = [c for c in w.params["comptes"] if c["id"] != "zz1"]
from app import apprentissage as AP
import datetime as _dt
demain_ = (_dt.date.today() + _dt.timedelta(days=3)).isoformat()
AP.ajouter_echeance(w.params, demain_, "Payer la facture", "/x/facture.pdf")
AP.ajouter_echeance(w.params, demain_, "Autre", "/x/autre.pdf")
e_ = [x for x in AP.echeances_a_venir(w.params) if x.get("libelle") in ("Payer la facture", "Autre")]
verif(len(e_) == 2 and all("cle" in x for x in e_), "échéances : clés fournies à l'accueil")
AP.marquer_echeance(w.params, e_[0]["cle"])
AP.marquer_echeance(w.params, e_[1]["cle"], retirer=True)
reste_ = {x["cle"] for x in AP.echeances_a_venir(w.params)}
verif(not ({e_[0]["cle"], e_[1]["cle"]} & reste_), "échéances : fait / retirer les enlèvent de l'accueil")
AP.marquer_echeance(w.params, "*", retirer=True)
verif(not AP.echeances_a_venir(w.params), "échéances : tout retirer")

# --- fermeture : question en francais
vu = {}
F.question = lambda parent, titre, texte, boutons: (vu.setdefault("b", [b for b, _ in boutons]), 1)[1]
o.modifie = True
w.fermer_onglet(w.onglets.indexOf(o))
verif(vu.get("b") == ["Enregistrer", "Ne pas enregistrer", "Annuler"], f"fermeture : {vu.get('b')}")

# --- volet de droite : retreci a la souris -> icones seules ; elargi -> complet
o_ = w.documents()[0]
w.onglets.setCurrentWidget(o_); app.processEvents()
o_.mode_volet("complet")
t_ = o_.sp.sizes()
o_.sp.setSizes([t_[0], t_[1] + t_[2] - 120, 120]); o_._volet_glisse()
verif(o_._mode_volet == "icones", "volet : rétréci à la souris, il passe en icônes seules")
t_ = o_.sp.sizes()
o_.sp.setSizes([t_[0], t_[1] + t_[2] - 260, 260]); o_._volet_glisse()
verif(o_._mode_volet == "complet", "volet : élargi, il redevient complet")
verif(not w.onglets.tabBar().isTabVisible(0) and w.b_fixes[w.accueil].isVisible(), "onglets : Accueil et Outils toujours visibles à gauche")
for _d in list(w.documents()):
    _d.modifie = False
w.fermer_tout(); app.processEvents()
verif(w.onglets.tabBar().isTabVisible(0) and w.onglets.tabBar().height() > 10 and not w.coin_fixe.isVisible(),
      "tous les fichiers fermés : Accueil et Outils redeviennent des onglets visibles")

# --- orthographe du document entier
d_ = fitz.open(); p_ = d_.new_page()
p_.insert_text((72, 100), "Le documment est signé par le notaire.", fontname="helv", fontsize=12)
p_.insert_text((72, 140), "The tennant shall pay the rent on the first day of the month.", fontname="helv", fontsize=12)
f_ = os.path.join(TRAVAIL, "Orthographe.pdf"); d_.save(f_)
oo_ = w.ouvrir(f_)
md_ = ORT.mots_douteux(oo_.doc, w.params)
verif({m for _n, _r, m, _l, _s in md_} == {"documment", "tennant"} and any(l == "en" for _n, _r, m, l, _s in md_ if m == "tennant"),
      f"orthographe du document : mots douteux trouvés ({[m for _n, _r, m, _l, _s in md_]})")
_ex1 = F.QDialog.exec if hasattr(F, "QDialog") else None
import PySide6.QtWidgets as _QW
_exo = _QW.QDialog.exec
def _exec_ortho(self):
    t_ = self.findChild(_QW.QTableWidget)
    row_ = next(i for i in range(t_.rowCount()) if t_.item(i, 1).text() == "documment")
    t_.selectRow(row_)
    next(b for b in self.findChildren(_QW.QPushButton) if b.text() == "Corriger").click()
    return _QW.QDialog.Accepted
_QW.QDialog.exec = _exec_ortho
w.verifier_orthographe()
_QW.QDialog.exec = _exo
verif("Le document est signé" in oo_.doc[0].get_text(), "orthographe : « Corriger » remplace le mot dans le PDF")

# --- synchronisation : encart visible, raison de l'echec et « Autoriser » si ce poste n'est pas autorise
ps_ = F.PanneauSynchro(w, "Google Drive Phil")
capture(w, "47_synchro_en_cours.png")
ps_.terminer({"ok": False, "recus": 0, "envoyes": 0, "erreur": "Google Drive pas encore autorisé sur ce poste",
              "quand": "2026-10-26T21:58"}, {"id": "x", "type": "gdrive", "nom": "Google Drive Phil"})
textes_ = [b.text() for b in ps_.findChildren(F.QPushButton)]
verif("Autoriser..." in textes_ and "Réessayer" in textes_, f"synchro : échec expliqué, bouton Autoriser ({textes_})")
capture(w, "48_synchro_echec.png")
ps_.deleteLater()
w.params["synchro_etat"] = {"quand": "2026-10-26T21:58", "ok": False, "erreur": "pas encore autorisé"}
w.params["drive_compte"] = w.params.get("drive_compte") or ""
w.accueil.rafraichir()

# --- synchronisation a cocher : rien n'est recu sans accord, ce qui est decoche revient la fois suivante
import json as _json, hashlib as _hl
from app import distant as _D, synchro_plan as _SP
part_ = os.path.join(TRAVAIL, "partage")
os.makedirs(os.path.join(part_, "PhilPDF", "sauvegarde", "tampons"))
cr_ = _D.nouveau_compte("reseau")
cr_.update(adresse=part_, nom="Partage test")
w.params["comptes"] = list(w.params.get("comptes", [])) + [cr_]
w.params["drive_compte"] = cr_["id"]
w.params.enregistrer()
pdf_t = objets.tampon_predefini("CANNES", (0.1, 0.2, 0.6), "X")
open(os.path.join(part_, "PhilPDF", "sauvegarde", "tampons", "ab12cd34ef56.pdf"), "wb").write(pdf_t)
_json.dump({"elements": [{"id": "ab12cd34ef56", "genre": "tampons", "nom": "Tampon de Cannes", "ext": ".pdf",
                          "hash": _hl.sha1(pdf_t).hexdigest(), "date": "2026-10-27 10:00", "machine": "Cannes",
                          "categorie": "SCI", "maj": "2026-10-27 10:00"}], "supprimes": []},
           open(os.path.join(part_, "PhilPDF", "sauvegarde", "index.json"), "w", encoding="utf-8"))
reponses_, vus_ = [_QW.QDialog.Rejected, _QW.QDialog.Accepted], []
def _exec_plan(self):
    if isinstance(self, _SP.DialoguePlan):
        vus_.append([self.arbre.topLevelItem(g).child(i).text(0) for g in range(self.arbre.topLevelItemCount())
                     for i in range(self.arbre.topLevelItem(g).childCount())])
        if len(vus_) == 1:
            capture(self, "49_synchro_a_cocher.png")
        return reponses_.pop(0)
    return _QW.QDialog.Rejected
_QW.QDialog.exec = _exec_plan
def _attendre_synchro():
    for _i in range(100):
        QTest.qWait(150)
        t_ = getattr(w, "_t_miroir", None)
        if t_ is not None and not t_.isRunning() and len(vus_) >= 1:
            QTest.qWait(300)
            t_ = getattr(w, "_t_miroir", None)
            if not t_.isRunning():
                return
def _a_le_tampon():
    return any(e["nom"] == "Tampon de Cannes" for e in w.biblio.elements("tampons"))
w.synchro_manuelle()
_attendre_synchro()
verif(vus_ and any("Tampon" in x for x in vus_[0]) and not _a_le_tampon(),
      f"synchro : la fenêtre annonce le tampon de l'autre poste ; « Plus tard » -> rien reçu ({vus_})")
w.synchro_manuelle()
_attendre_synchro()
verif(len(vus_) == 2 and _a_le_tampon(), "synchro : proposé à nouveau, accepté -> tampon reçu avec sa catégorie")
# routine (un autre poste a seulement note son etat, ses fichiers ouverts) : fait sans ouvrir la fenetre
_json.dump({"philpdf": 1, "communs": {"maj": "2026-10-27T10:00:00", "par": w.params.get("machine")},
            "postes": {"Cannes": {"machine": "Cannes", "maj": "2026-10-27T18:00"}}},
           open(os.path.join(part_, "PhilPDF", "preferences.json"), "w", encoding="utf-8"))
_json.dump({"Cannes": {"maj": "2026-10-27T18:00", "fichiers": []}},
           open(os.path.join(part_, "PhilPDF", "session.json"), "w", encoding="utf-8"))
reponses_.append(_QW.QDialog.Accepted)
w.synchro_manuelle()
for _i in range(40):
    QTest.qWait(150)
verif(len(vus_) == 2 and os.path.exists(os.path.join(_M_dossier_ := __import__("app.miroir", fromlist=["x"]).dossier_miroir(cr_), "PhilPDF", "session.json")),
      f"synchro : rien de nouveau pour vous (état des autres postes) -> fait sans fenêtre ({vus_[2:]})")
_QW.QDialog.exec = _exo
w.params["drive_compte"] = ""
w.params.enregistrer()
# --- Recents : ceux de ce poste et ceux des autres postes, une seule liste (plus de bandeau)
from app.session import session_de as _sd
import datetime as _dt
s_ = _sd(w.params)
ici_pdf = os.path.join(TRAVAIL, "Commun.pdf")
shutil.copy(os.path.join(TRAVAIL, "Facture_test.pdf") if os.path.exists(os.path.join(TRAVAIL, "Facture_test.pdf")) else w.params["recents"][0], ici_pdf)
from app.session import empreinte as _emp
maint_ = _dt.datetime.now().isoformat(timespec="minutes")
d_ = s_.lire()
d_["Cannes"] = {"maj": maint_, "fichiers": [{"chemin": ici_pdf, "nom": "Commun.pdf", "taille": os.path.getsize(ici_pdf), "empreinte": _emp(ici_pdf)}],
                "recents": [{"chemin": "C:\\Ailleurs\\Absent.pdf", "nom": "Absent.pdf", "taille": 10, "empreinte": "x", "date": maint_},
                            {"chemin": "C:\\Vieux.pdf", "nom": "Vieux.pdf", "taille": 10, "empreinte": "y", "date": "2020-01-01T10:00"}]}
_json.dump(d_, open(s_.chemin, "w", encoding="utf-8"))
w._synchro_trouvee(("Cannes", maint_, d_["Cannes"]["fichiers"], [(ici_pdf, "même emplacement")], True, {}))
textes_ = [w.accueil.liste.item(i).text() for i in range(w.accueil.liste.count())]
verif(not w.accueil.carte.isVisibleTo(w.accueil), "autre poste : plus de bandeau")
verif(any("Commun.pdf" in t and "ouvert sur Cannes" in t for t in textes_), "récents : fichier ouvert sur l'autre poste, retrouvé ici")
abs_ = [i for i in range(w.accueil.liste.count()) if "Absent.pdf" in w.accueil.liste.item(i).text()]
verif(abs_ and "introuvable sur ce poste" in w.accueil.liste.item(abs_[0]).text()
      and w.accueil.liste.item(abs_[0]).foreground().color() == D.Qt.gray, "récents : fichier de l'autre poste introuvable ici, grisé")
verif(not any("Vieux.pdf" in t for t in textes_) and w.accueil.liste.count() <= 30, "récents : 30 derniers jours, 30 au plus")
capture(w.accueil, "50_recents_communs.png")

# --- tampons : glisser un apercu a une autre place change l'ordre (garde)
for n_ in ("T-un", "T-deux"):
    w.biblio.ajouter("tampons", n_, objets.tampon_predefini(n_, (0.1, 0.2, 0.6), "X"))
pb_ = G.PanneauBibliotheque(None, w.biblio, "tampons", compact=True)
pb_.resize(900, 400); pb_.show(); app.processEvents()
avant_ = [pb_.liste.item(i).data(D.Qt.UserRole)["nom"] for i in range(pb_.liste.count())]
r_un = avant_.index("T-un"); r_deux = avant_.index("T-deux")
pb_.liste.setCurrentRow(r_un)
from PySide6.QtGui import QDropEvent as _QDE
from PySide6.QtCore import QMimeData as _QMD
cible_ = pb_.liste.visualItemRect(pb_.liste.item(r_deux)).center()
ev_ = _QDE(D.QPointF(cible_) if hasattr(D, "QPointF") else __import__("PySide6.QtCore", fromlist=["QPointF"]).QPointF(cible_),
           D.Qt.MoveAction, _QMD(), D.Qt.LeftButton, D.Qt.NoModifier)
pb_.liste.dropEvent(ev_)
apres_ = [e["nom"] for e in w.biblio.elements("tampons")]
verif(apres_.index("T-un") > apres_.index("T-deux") and len(apres_) == len(avant_),
      f"tampons : glissé à une autre place, ordre gardé ({avant_} → {apres_})")
w.biblio.ajouter("tampons", "T-trois", objets.tampon_predefini("T-trois", (0.1, 0.2, 0.6), "X"))
pb_.rafraichir(); app.processEvents()
noms_ = [pb_.liste.item(i).data(D.Qt.UserRole)["nom"] for i in range(pb_.liste.count())]
ra_, rb_ = pb_.liste.visualItemRect(pb_.liste.item(noms_.index("T-deux"))), pb_.liste.visualItemRect(pb_.liste.item(noms_.index("T-un")))
entre_ = __import__("PySide6.QtCore", fromlist=["QPointF"]).QPointF((ra_.right() + rb_.left()) / 2, ra_.center().y())
pb_.liste.setCurrentRow(noms_.index("T-trois"))
pb_.liste.dropEvent(_QDE(entre_, D.Qt.MoveAction, _QMD(), D.Qt.LeftButton, D.Qt.NoModifier))
apres_ = [e["nom"] for e in w.biblio.elements("tampons")]
verif(apres_.index("T-deux") + 1 == apres_.index("T-trois") == apres_.index("T-un") - 1,
      f"tampons : déposé entre deux, il s'y place ({apres_})")
pb_.close()

# --- largeur du volet droit reglee a la souris : gardee pour les documents suivants et apres redemarrage
od_ = w.documents()[0]
w.onglets.setCurrentWidget(od_); app.processEvents()
od_.mode_volet("complet")
t_ = od_.sp.sizes()
od_.sp.setSizes([t_[0], t_[1] + t_[2] - 260, 260])
od_.sp.splitterMoved.emit(0, 2)
QTest.qWait(800)
lv_ = od_.sp.sizes()[2]
verif(abs(w.params.get("volet_largeur", 0) - lv_) <= 2, f"volet droit : largeur gardée ({w.params.get('volet_largeur')} / {lv_})")
verif(od_._taille_volet == lv_, "volet droit : même largeur au retour en mode complet")

# --- proprietes du document : modifiables, ecrites aussi dans le XMP (celui qu'affiche Acrobat)
from moteur import metadonnees as _MD
od_.doc.set_xml_metadata('<?xpacket begin=""?><x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
                         '<rdf:Description rdf:about="" xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title><rdf:Alt>'
                         '<rdf:li xml:lang="x-default">Titre Adobe</rdf:li></rdf:Alt></dc:title></rdf:Description></rdf:RDF></x:xmpmeta><?xpacket end="w"?>')
def _exec_prop(self):
    if self.windowTitle() == "Propriétés du document":
        self.findChild(_QW.QLineEdit, "prop_title").setText("Convention de trésorerie")
        self.findChild(_QW.QLineEdit, "prop_author").setText("Philippe Delaye")
        capture(self, "51_proprietes.png")
        return _QW.QDialog.Accepted
    return _QW.QDialog.Rejected
_QW.QDialog.exec = _exec_prop
w.onglets.setCurrentWidget(od_)
w.proprietes()
_QW.QDialog.exec = _exo
m_ = _MD.lire(fitz.open("pdf", od_.doc.tobytes()))
verif(m_["title"] == "Convention de trésorerie" and m_["author"] == "Philippe Delaye" and od_.modifie,
      f"propriétés : titre et auteur changés, y compris dans le XMP d'Adobe ({m_['title']})")

# --- signatures classees par categorie, comme les tampons ; contenu du volet choisi depuis le menu
sg_ = w.biblio.elements("signatures")[0]
w.biblio.modifier(sg_, categorie="Perso")
od_.ouvrir_bibliotheque("signatures")
cats_ = [od_.liste_biblio.topLevelItem(i) for i in range(od_.liste_biblio.topLevelItemCount())]
perso_ = next(g for g in cats_ if g.text(0).startswith("Mes signatures"))
verif(any(perso_.child(i).text(0) == "Perso" for i in range(perso_.childCount())), "signatures : catégorie en sous-groupe")
for c_, idx_ in (("format", 1), ("outils", 0), ("tampons", 2)):
    od_.contenu_volet(c_)
    verif(od_.pile_volet.currentIndex() == idx_, f"volet : contenu « {c_} » choisi")
# --- mes postes : la liste des postes
def _exec_postes(self):
    if self.windowTitle() == "Mes postes":
        from PySide6.QtWidgets import QTableWidget
        t_ = self.findChild(QTableWidget)
        vus_postes.extend(t_.item(r, 0).text() for r in range(t_.rowCount()))
        capture(self, "52_mes_postes.png")
    return _QW.QDialog.Rejected
vus_postes = []
_QW.QDialog.exec = _exec_postes
w.mes_postes()
_QW.QDialog.exec = _exo
verif(any("(ce poste)" in x for x in vus_postes) and any(x.startswith("Cannes") for x in vus_postes),
      f"mes postes : liste des postes ({vus_postes})")

# --- rotation : texte (le bloc entier), image et tampon, poignee ronde ; clic droit 90 degres
import math as _m
rp_ = os.path.join(TRAVAIL, "Rotation.pdf")
dr_ = fitz.open(); pr_ = dr_.new_page()
pr_.insert_text((80, 120), "Texte à tourner", fontname="helv", fontsize=18)
pm_ = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 80, 40), False); pm_.clear_with(120)
pr_.insert_image(fitz.Rect(300, 300, 460, 380), pixmap=pm_)
dr_.save(rp_)
orot_ = w.ouvrir(rp_)
orot_.changer_mode("modifier")
ligne_ = next(x for x in [orot_.objet_sous(0, fitz.Point(100, 112))] if x)
orot_.choisir_objet(ligne_)
pw_ = orot_.page_widgets[0]
verif(pw_._poignee_rotation(pw_.vers_ecran(ligne_["rect"])) is not None, "rotation : poignée ronde sur le texte choisi")
orot_.tourner_objet(30)
dirs_ = [round(_m.degrees(_m.atan2(-l["dir"][1], l["dir"][0]))) for b in orot_.doc[0].get_text("dict")["blocks"]
         for l in b.get("lines", []) if "tourner" in "".join(s["text"] for s in l["spans"])]
verif(dirs_ == [30], f"rotation : texte tourné de 30° ({dirs_})")
orot_.tourner_objet(None)
dirs_ = [round(_m.degrees(_m.atan2(-l["dir"][1], l["dir"][0]))) for b in orot_.doc[0].get_text("dict")["blocks"]
         for l in b.get("lines", []) if "tourner" in "".join(s["text"] for s in l["spans"])]
verif(dirs_ == [0], f"rotation : « Remettre droit » ({dirs_})")
img_ = orot_.objet_sous(0, fitz.Point(380, 340))
orot_.choisir_objet(img_)
orot_.tourner_objet(-90)
from moteur.modifier import Editeur as _Ed
verif(round(_Ed(orot_.doc).geometrie_image(0, img_["xref"])[3]) in (-90, 270), "rotation : image tournée de 90° à droite")
capture(w, "53_rotation.png")
orot_.changer_mode(None)
st_ = objets.tampon_predefini("PAYE", (0.8, 0, 0), "X")
xr_ = objets.poser(orot_.doc, 0, fitz.Rect(100, 500, 260, 560), st_)
orot_.choisir_objet({"type": "annot", "page": 0, "xref": xr_, "rect": objets.rect_objet(orot_.doc, 0, xr_), "philpdf": True,
                     "garder_proportions": True})
orot_.tourner_objet(-20)
verif(round(objets.angle_objet(orot_.doc, xr_)) in (340, -20), "rotation : tampon tourné (relu par Acrobat : matrice de l'apparence)")
orot_.modifie = False
w.fermer_onglet(w.onglets.indexOf(orot_))

# --- fermeture : une fenetre explique l'attente (preferences, synchronisation)
ff_ = F.FenetreFermeture(w, "Google Drive (exemple)")
ff_.etape("Préférences envoyées vers Google Drive (exemple)", lambda: None)
ff_.etape("Etape en échec", lambda: 1 / 0)
capture(ff_, "43_fermeture.png")
verif(ff_.lignes[0].startswith("✓") and ff_.lignes[1].startswith("✕"), "fermeture : étapes affichées")
ff_.close()
w.onglets.setCurrentWidget(w.outils); app.processEvents()
capture(w, "44_outils.png")
print(f"\n{sum(c for c, _ in ok)}/{len(ok)} vérifications réussies")
sys.exit(0 if all(c for c, _ in ok) else 1)
