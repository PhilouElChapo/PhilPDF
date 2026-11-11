"""Conversion en PDF sans Office ni LibreOffice (moteur/office_interne.py) et fenetre d'avancement non bloquante
(Reduire -> barre d'etat). Exemples fictifs (Jean Martin)."""
import os, sys, tempfile
sys.stdout.reconfigure(encoding="utf-8")
racine = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, racine)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pymupdf as fitz
import docx
from docx.enum.section import WD_ORIENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor
from moteur import office_interne

ok = True


def verifier(cond, texte):
    global ok
    print(("OK    " if cond else "ECHEC ") + texte)
    ok &= bool(cond)


d = tempfile.mkdtemp()
# -- Word : titre, liste, tableau long avec ligne d'en-tete, cellules colorees, paysage
w = docx.Document()
s = w.sections[0]
s.orientation = WD_ORIENT.LANDSCAPE
s.page_width, s.page_height = s.page_height, s.page_width
w.add_heading("Dossier de Jean Martin", 1)
p = w.add_paragraph()
r = p.add_run("Texte en gras rouge")
r.bold = True
r.font.color.rgb = RGBColor(0xC0, 0, 0)
r.font.size = Pt(14)
w.add_paragraph("Premier point", style="List Bullet")
w.add_paragraph("Second point", style="List Bullet")
t = w.add_table(rows=1, cols=3)
t.style = "Table Grid"
for i, x in enumerate(("Colonne A", "Colonne B", "Colonne C")):
    t.rows[0].cells[i].text = x
trp = t.rows[0]._tr.get_or_add_trPr()
trp.append(OxmlElement("w:tblHeader"))
for n in range(60):
    c = t.add_row().cells
    c[0].text = f"Ligne {n + 1}"
    c[1].text = "Jean Martin " * (3 + n % 5)
    c[2].text = "fin"
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), "FBEAEA")
    shd.set(qn("w:val"), "clear")
    c[0]._tc.get_or_add_tcPr().append(shd)
w.add_paragraph("Conclusion de Jean Martin")
src = os.path.join(d, "essai.docx")
w.save(src)
pdf = os.path.join(d, "essai.pdf")
manques = office_interne.convertir(src, pdf, os.path.join(d, "img"))
doc = fitz.open(pdf)
texte = "".join(pg.get_text() for pg in doc)
verifier(len(doc) >= 2, f"Word : plusieurs pages ({len(doc)})")
verifier(doc[0].rect.width > doc[0].rect.height, "Word : orientation paysage gardee")
verifier(all(f"Ligne {n} " in texte.replace("\n", " ") + " " for n in (1, 30, 60)), "Word : toutes les lignes du tableau")
verifier("Conclusion de Jean Martin" in texte and "Premier point" in texte, "Word : texte apres le tableau, liste")
verifier(all("Colonne A" in pg.get_text() for pg in doc if "Ligne" in pg.get_text()),
         "Word : ligne d'en-tete repetee sur chaque page du tableau")
dans = all(fitz.Rect(b[:4]) in pg.rect + (-1, -1, 1, 1) for pg in doc for b in pg.get_text("words"))
verifier(dans, "Word : aucun mot hors de la page")
coupees = [n for n in range(1, 61) if texte.count(f"Ligne {n}\n") > 1]
verifier(not coupees, "Word : aucune ligne de tableau coupee ni en double")
rouge = any(abs(sp["size"] - 14) < 0.5 and sp["color"] == 0xC00000 and "bold" in sp["font"].lower() or sp["flags"] & 16
            for b in doc[0].get_text("dict")["blocks"] for l in b.get("lines", []) for sp in l["spans"]
            if "gras rouge" in sp["text"])
verifier(rouge, "Word : gras, couleur et taille gardes")
verifier(manques == [], f"Word : rien de non repris ({manques})")

# -- tableur CSV et texte
csvf = os.path.join(d, "t.csv")
open(csvf, "w", encoding="utf-8").write("Nom;Ville\n" + "".join(f"Jean Martin {i};Lyon\n" for i in range(120)))
office_interne.convertir(csvf, os.path.join(d, "t.pdf"), os.path.join(d, "img2"))
dc = fitz.open(os.path.join(d, "t.pdf"))
tc = "".join(pg.get_text() for pg in dc)
verifier("Jean Martin 119" in tc and len(dc) >= 2 and all("Nom" in pg.get_text() for pg in dc), "CSV : tout, en-tete sur chaque page")
txt = os.path.join(d, "t.txt")
open(txt, "w", encoding="utf-8").write("Bonjour Jean Martin\n" * 200)
office_interne.convertir(txt, os.path.join(d, "x.pdf"), os.path.join(d, "img3"))
verifier("Bonjour Jean Martin" in fitz.open(os.path.join(d, "x.pdf"))[0].get_text(), "Texte : converti")
try:
    office_interne.convertir(os.path.join(d, "a.pptx"), os.path.join(d, "a.pdf"), d)
    verifier(False, "PowerPoint : refuse sans Office")
except office_interne.ErreurInterne:
    verifier(True, "PowerPoint : refuse sans Office (message clair)")


# -- Word par automatisation (simulee) : le modele Normal n'est jamais enregistre, l'Office de la personne reste tel quel
import types
from moteur import office


class _Doc:
    def ExportAsFixedFormat(self, sortie, *a, **k):
        open(sortie, "wb").write(b"%PDF-1.4")

    def Close(self, **k):
        journal.append(("close", k))


class _Word:
    def __init__(self, visible, docs):
        self.Visible, self.DisplayAlerts = visible, -1
        self.Documents = types.SimpleNamespace(Count=docs, Open=lambda *a, **k: _Doc())
        self.NormalTemplate = types.SimpleNamespace(Saved=False)

    def Quit(self, **k):
        journal.append(("quit", k, self.NormalTemplate.Saved))


def essai_word(dispatchex_ok, actif):
    global journal
    journal = []
    wc = types.SimpleNamespace()
    neuf = _Word(True, 0)

    def dex(nom):
        if not dispatchex_ok:
            raise OSError(-2146959355, "Echec de l'execution du serveur")
        return neuf
    wc.DispatchEx, wc.Dispatch = dex, lambda nom: neuf
    wc.GetActiveObject = lambda nom: actif if actif else (_ for _ in ()).throw(OSError("aucun"))
    sys.modules["pythoncom"] = types.SimpleNamespace(CoInitialize=lambda: None, CoUninitialize=lambda: None)
    sys.modules["win32com"] = types.SimpleNamespace(client=wc)
    sys.modules["win32com.client"] = wc
    office._par_office(src, os.path.join(d, "com.pdf"))
    return neuf


essai_word(True, None)
verifier(("quit", {"SaveChanges": 0}, True) in journal, "Word : ferme sans enregistrer, modele Normal marque non modifie")
verifier(any(j[0] == "close" and j[1] == {"SaveChanges": 0} for j in journal), "Word : document ferme sans enregistrer")
perso = _Word(True, 2)
essai_word(False, perso)
verifier(not any(j[0] == "quit" for j in journal) and perso.DisplayAlerts == -1,
         "Word deja ouvert par la personne : pas ferme, ses alertes remises")
orphelin = _Word(False, 0)
essai_word(False, orphelin)
verifier(("quit", {"SaveChanges": 0}, True) in journal, "Word cache reste d'un plantage : ferme proprement")
for m in ("pythoncom", "win32com", "win32com.client"):
    sys.modules.pop(m, None)

# -- fenetre d'avancement non bloquante
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMainWindow
app = QApplication.instance() or QApplication([])
from app.dialogues_ia import Avancement, en_tache
fen = QMainWindow()
fen.show()
a = Avancement(fen, "Essai", bloquante=False)
verifier(a.windowModality() == Qt.NonModal, "Avancement : non bloquante")
a.show()
a.etape("Telechargement", 40, 100)
a.reduire()
verifier(not a.isVisible() and a._reduite is not None and not a._reduite.isHidden() and a._reduite.parent() is not None, "Avancement : Reduire -> barre d'etat")
a.etape("Telechargement", 70, 100)
verifier(a._reduite.barre.value() == 70, "Avancement : la barre d'etat suit l'avancement")
a.afficher()
verifier(a.isVisible(), "Avancement : Afficher la rouvre")
a.close()
verifier(a.isVisible() is False and a._reduite is not None, "Avancement : la croix reduit (la tache continue, visible)")
a.terminer()
verifier(a._reduite is None, "Avancement : fin -> barre d'etat rangee")
b = Avancement(fen, "Essai", bloquante=True)
verifier(b.windowModality() == Qt.WindowModal and not hasattr(b, "b_reduire"), "Avancement : bloquante si elle modifie le document")
verifier(en_tache(fen, "Essai", "calcul", lambda x: x * 2, 21, lecture=True, bloquante=False) == 42, "en_tache non bloquante : resultat")
print("RESULTAT :", "OK" if ok else "ECHEC")
sys.exit(0 if ok else 1)
