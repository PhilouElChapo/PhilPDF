"""Formulaires : types de champs, proprietes simples (format, date automatique, calcul, plage, listes dependantes,
afficher / masquer), remplissage dans PhilPDF comme dans Acrobat, JavaScript standard pour Acrobat, ordre de tabulation.
Lancement : QT_QPA_PLATFORM=offscreen python tests/test_formulaire.py"""
import os, sys, tempfile, datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import annotations  # noqa: F401
os.environ["PHILPDF_LANGUE"] = "fr"
os.environ["APPDATA"] = tempfile.mkdtemp()
os.environ["HOME"] = os.environ["APPDATA"]
from PySide6.QtWidgets import QApplication, QMessageBox, QInputDialog, QDialog
from PySide6.QtCore import Qt
import pymupdf as fitz
app = QApplication.instance() or QApplication([])

from moteur import champs as C
from app.config import Parametres
from app.document import OngletDocument
import app.dialogues_champ as DC

ok = []


def verif(cond, quoi):
    ok.append((bool(cond), quoi))
    print(("OK   " if cond else "ECHEC") + " " + quoi)


avert = []
QMessageBox.information = staticmethod(lambda *a, **k: None)
QMessageBox.warning = staticmethod(lambda *a, **k: avert.append(a[2] if len(a) > 2 else a))
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
reponses = []
QInputDialog.getText = staticmethod(lambda *a, **k: (reponses.pop(0), True))
QInputDialog.getItem = staticmethod(lambda *a, **k: (reponses.pop(0), True))
QInputDialog.getMultiLineText = staticmethod(lambda *a, **k: (reponses.pop(0), True))

T = tempfile.mkdtemp()
src = os.path.join(T, "Bon de commande.pdf")
d = fitz.open()
d.new_page().insert_text((72, 60), "Bon de commande", fontsize=16)
d.save(src)
o = OngletDocument(Parametres(), src)
o.changer_mode("formulaire")


def tracer(genre, rect, *rep):
    reponses[:] = list(rep)
    o.type_trace.setCurrentIndex(o.type_trace.findData(genre))
    o.zone_tracee(0, fitz.Rect(rect))


tracer("texte", (100, 100, 200, 120), "Quantité")
tracer("montant", (100, 130, 200, 150), "Prix")
tracer("texte", (100, 160, 200, 180), "Total")
tracer("date", (100, 190, 200, 210), "Date")
tracer("liste", (100, 220, 200, 240), "Pays", "France\nItalie")
tracer("liste", (100, 250, 200, 270), "Ville", "")
tracer("case", (100, 280, 112, 292), "Livraison")
tracer("texte", (100, 300, 300, 320), "Adresse")
tracer("radio", (100, 330, 112, 342), "Avis", "Favorable")
tracer("radio", (150, 330, 162, 342), "Avis", "Défavorable")
noms = sorted({w.field_name for p in o.doc for w in p.widgets()})
verif(noms == sorted(["Quantité", "Prix", "Total", "Date", "Pays", "Ville", "Livraison", "Adresse", "Avis"]),
      f"champs tracés selon le type choisi ({noms})")
types = {w.field_name: w.field_type for w in o.doc[0].widgets()}
verif(types["Pays"] == fitz.PDF_WIDGET_TYPE_COMBOBOX and types["Livraison"] == fitz.PDF_WIDGET_TYPE_CHECKBOX
      and types["Avis"] == fitz.PDF_WIDGET_TYPE_RADIOBUTTON, "liste déroulante, case, boutons radio")
verif(len([w for w in o.doc[0].widgets() if w.field_name == "Avis"]) == 2, "deux boutons dans le même groupe radio")
verif(C.lire(o.doc, o._widget_nom("Prix"))["format"]["genre"] == "nombre", "montant : format nombre en euros")


def proprietes(nom, regler):
    w = o._widget_nom(nom)
    DC.DialogueChamp.exec = lambda self: (regler(self), self.valider(), QDialog.Accepted if hasattr(self, "resultat") else QDialog.Rejected)[-1]
    o.proprietes_champ(0, w)


def coche(lst, *noms_):
    for i in range(lst.count()):
        lst.item(i).setCheckState(Qt.Checked if lst.item(i).text() in noms_ else Qt.Unchecked)


proprietes("Quantité", lambda s: (s.f_genre.setCurrentIndex(s.f_genre.findData("nombre")), s.f_dec.setValue(0),
                                  s.p_min_on.setChecked(True), s.p_min.setValue(1), s.p_max_on.setChecked(True),
                                  s.p_max.setValue(100), s.obligatoire.setChecked(True)))
proprietes("Total", lambda s: (s.f_genre.setCurrentIndex(s.f_genre.findData("montant")),
                               s.c_genre.setCurrentIndex(s.c_genre.findData("formule")),
                               s.c_formule.setText("[Quantité] * [Prix]")))
proprietes("Date", lambda s: s.auto.setCurrentIndex(s.auto.findData("date_clic")))
proprietes("Ville", lambda s: (s.d_parent.setCurrentIndex(s.d_parent.findData("Pays")),
                               s.d_table.item(0, 1).setText("Paris; Lyon; Cannes"),
                               s.d_table.item(1, 1).setText("Rome; Milan")))
proprietes("Livraison", lambda s: (s.a_on.setChecked(True), coche(s.a_cibles, "Adresse")))
r = C.lire(o.doc, o._widget_nom("Total"))
verif(r["calcul"] == {"genre": "formule", "formule": "[Quantité] * [Prix]"} and r["format"]["symbole"] == "€",
      "propriétés gardées : calcul et format")
sc = C.scripts(o.doc, o._widget_nom("Total"))
verif("AFNumber_Format(2, 2, 0, 0, \" €\", false)" in sc.get("F", "") and "BVCALC" in sc.get("C", "")
      and 'getField("Quantité")' in sc.get("C", ""), "JavaScript standard d'Acrobat : format et calcul")
verif("AFRange_Validate(true, 1.0, true, 100.0)" in C.scripts(o.doc, o._widget_nom("Quantité")).get("V", ""),
      "JavaScript d'Acrobat : plage autorisée")
verif("setItems" in C.scripts(o.doc, o._widget_nom("Pays")).get("V", ""), "JavaScript d'Acrobat : liste dépendante sur Pays")
verif("util.printd" in C.scripts(o.doc, o._widget_nom("Date")).get("Fo", ""), "JavaScript d'Acrobat : date au clic")
verif("display.hidden" in C.scripts(o.doc, o._widget_nom("Livraison")).get("U", ""), "JavaScript d'Acrobat : afficher / masquer")
co = o.doc.xref_get_key(o.doc.pdf_catalog(), "AcroForm/CO")
verif(co[0] == "array" and str(C.xref_champ(o.doc, o._widget_nom("Total"))) in co[1], "ordre de calcul (CO) renseigné")
o.changer_mode(None)

# --- remplir dans PhilPDF comme dans Acrobat
verif("Quantité" in o.champs_obligatoires_vides(), "champ obligatoire vide repéré")
o.valeur_champ(0, o._widget_nom("Quantité").xref, "500")
verif(avert and "entre 1 et 100" in avert[-1] and (o._widget_nom("Quantité").field_value or "") == "", "plage : 500 refusé")
o.valeur_champ(0, o._widget_nom("Quantité").xref, "3")
o.valeur_champ(0, o._widget_nom("Prix").xref, "1 234,5")
verif(o._widget_nom("Prix").field_value == "1234.5", f"montant gardé comme Acrobat ({o._widget_nom('Prix').field_value})")
verif(o._widget_nom("Total").field_value == "3703.5", f"total calculé ({o._widget_nom('Total').field_value})")
txt = o.doc[0].get_text("text", clip=fitz.Rect(95, 155, 210, 185))
ap = o.doc.xref_stream(int(o.doc.xref_get_key(o._widget_nom("Total").xref, "AP/N")[1].split()[0])).decode("latin-1")
verif("3.703,50" in ap, "total affiché formaté (3.703,50 €)")
avert.clear()
o.valeur_champ(0, o._widget_nom("Prix").xref, "abc")
verif(avert and "n'est pas un nombre" in avert[-1], "montant : texte refusé")
pw = type("PW", (), {"num": 0, "ouvrir_saisie_champ": lambda self, w: None})()
o.remplir_champ(pw, o._widget_nom("Date"))
verif(o._widget_nom("Date").field_value == datetime.date.today().strftime("%d/%m/%Y"), "date du jour mise au clic")
o.valeur_champ(0, o._widget_nom("Date").xref, "5/1/27")
verif(o._widget_nom("Date").field_value == "05/01/2027", "date saisie remise au format (05/01/2027)")
o.valeur_champ(0, o._widget_nom("Pays").xref, "Italie")
verif([c if isinstance(c, str) else c[0] for c in o._widget_nom("Ville").choice_values] == ["Rome", "Milan"],
      "liste dépendante : Italie → Rome, Milan")
o.valeur_champ(0, o._widget_nom("Pays").xref, "France")
verif([c if isinstance(c, str) else c[0] for c in o._widget_nom("Ville").choice_values] == ["Paris", "Lyon", "Cannes"],
      "liste dépendante : France → Paris, Lyon, Cannes")
o.remplir_champ(pw, o._widget_nom("Livraison"))
verif(o._widget_nom("Adresse").field_display == 0, "case cochée : Adresse affichée")
o.remplir_champ(pw, o._widget_nom("Livraison"))
verif(o._widget_nom("Adresse").field_display == 1, "case décochée : Adresse masquée")
radios = [w for w in o.doc[0].widgets() if w.field_name == "Avis"]
o.remplir_champ(pw, radios[1])
etats = [o.doc.xref_get_key(w.xref, "AS")[1] for w in o.doc[0].widgets() if w.field_name == "Avis"]
verif(etats[0] == "/Off" and etats[1] != "/Off", f"radio : un seul choix coché ({etats})")
o.remplir_champ(pw, [w for w in o.doc[0].widgets() if w.field_name == "Avis"][0])
etats = [o.doc.xref_get_key(w.xref, "AS")[1] for w in o.doc[0].widgets() if w.field_name == "Avis"]
verif(etats[0] != "/Off" and etats[1] == "/Off", "radio : changer de choix décoche l'autre")
o.remplir_champ(pw, o._widget_nom("Total"))
verif(o._widget_nom("Total").field_value == "3703.5", "champ calculé : non modifiable à la main")

# --- ordre de tabulation
xr = [w.xref for w in o.doc[0].widgets()]
o.poser_ordre_tabulation(0, list(reversed(xr)))
verif([w.xref for w in o.doc[0].widgets()] == list(reversed(xr)), "ordre de tabulation changé")

# --- enregistrer, rouvrir ; formulaire fait par Acrobat (sans regles PhilPDF) relu depuis son JavaScript
o.enregistrer(src)
o2 = OngletDocument(Parametres(), src)
verif(o2._widget_nom("Total").field_value == "3703.5" and C.lire(o2.doc, o2._widget_nom("Total"))["calcul"],
      "rouvert : valeurs et règles gardées")
dd = fitz.open(src)
for p in dd:
    for w in p.widgets():
        dd.xref_set_key(C.xref_champ(dd, w), C.CLE, "null")
r = C.lire(dd, next(w for w in dd[0].widgets() if w.field_name == "Total"))
verif(not r.get("_philpdf") and r["calcul"]["genre"] == "formule" and r["calcul"]["formule"] == "[Quantité] * [Prix]"
      and r["format"]["genre"] == "nombre", f"formulaire d'Acrobat : règles relues depuis le JavaScript ({r['calcul']})")
r = C.lire(dd, next(w for w in dd[0].widgets() if w.field_name == "Quantité"))
verif(r["plage"] == {"min": 1.0, "max": 100.0}, "formulaire d'Acrobat : plage relue")
r = C.lire(dd, next(w for w in dd[0].widgets() if w.field_name == "Date"))
verif(r["auto"] == "date_clic" and r["format"]["genre"] == "date", "formulaire d'Acrobat : date au clic relue")

n_ok = sum(1 for c, _q in ok if c)
print(f"\n{n_ok}/{len(ok)} vérifications de formulaire réussies")
sys.exit(0 if n_ok == len(ok) else 1)
