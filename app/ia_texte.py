"""Outils IA sur le texte : corriger / reformuler un paragraphe, remettre en page un scan (nouveau PDF propre),
extraire les donnees d'un document (tableau modifiable, copie ou Excel). Rien ne part sans un clic, et les
donnees sensibles sont signalees avant l'envoi."""
import datetime
import os
import re

import pymupdf as fitz
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox, QPlainTextEdit,
                               QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox, QApplication,
                               QDialogButtonBox, QSpinBox, QLineEdit, QFormLayout, QCheckBox)

from .langue import _
from . import ia

ACTIONS = [("corriger", _("Corriger les fautes (sans changer le style)")),
           ("clarifier", _("Reformuler plus clairement")),
           ("formel", _("Rendre plus formel")),
           ("simple", _("Rendre plus simple, plus direct")),
           ("court", _("Raccourcir")),
           ("libre", _("Consigne libre..."))]

CONSIGNES = {
    "corriger": "Corrige l'orthographe, la grammaire, les accords et la ponctuation du texte. Ne change ni le style, "
                "ni le vocabulaire, ni l'ordre des phrases.",
    "clarifier": "Reformule le texte pour qu'il soit plus clair et plus fluide, en gardant exactement le même sens, "
                 "les mêmes informations et à peu près la même longueur.",
    "formel": "Reformule le texte dans un registre plus formel et professionnel (vouvoiement), même sens, mêmes "
              "informations.",
    "simple": "Reformule le texte avec des phrases plus courtes et des mots plus simples, même sens, mêmes "
              "informations.",
    "court": "Raccourcis le texte d'environ un tiers en gardant toutes les informations importantes.",
}
REGLES = ("Réponds uniquement par le texte final, sans guillemets, sans commentaire ni explication. Garde les "
          "retours à la ligne, les noms propres, les nombres, les dates et les montants tels quels. Écris en "
          "français sauf si le texte est dans une autre langue : garde alors sa langue.")


def _executer(parent, texte, f):
    from .dialogues_ia import executer
    return executer(parent, texte, f)


def transformer(parent, params, texte, action):
    """Texte corrige / reformule par l'IA, ou None (annule, erreur affichee)."""
    from .dialogues_ia import preparer_envoi, montrer_erreur
    if not texte.strip():
        return None
    consigne = CONSIGNES.get(action)
    if action == "libre":
        from PySide6.QtWidgets import QInputDialog
        hist = list(params.get("ia_consignes_texte") or [])
        c, ok = QInputDialog.getItem(parent, _("Consigne libre"), _("Que faut-il faire de ce texte ?"),
                                     hist or [""], 0, True)
        if not ok or not c.strip():
            return None
        consigne = c.strip()
        params["ia_consignes_texte"] = [consigne] + [h for h in hist if h != consigne][:9]
        params.enregistrer()
    if not preparer_envoi(parent, params, texte):
        return None
    try:
        r = _executer(parent, _("L'IA travaille sur le texte..."),
                      lambda: ia.demander(params, consigne + "\n\n" + REGLES, texte, max_jetons=4000))
    except Exception as e:                           # noqa: BLE001
        montrer_erreur(parent, e)
        return None
    r = (r or "").strip()
    if len(r) > 1 and r[0] in "«\"“" and r[-1] in "»\"”" and not (texte.strip()[:1] in "«\"“"):
        r = r[1:-1].strip()
    return r or None


# ================================================================ remettre en page un scan
CONSIGNE_MISE_EN_PAGE = """Tu reçois l'image d'une page scannée (parfois de travers, tachée ou mal cadrée).
Recopie TOUT son contenu, sans rien résumer, reformuler ni inventer, sous forme de HTML simple pour la recréer
proprement : <h1>, <h2>, <h3> pour les titres, <p> pour les paragraphes (un paragraphe = un <p>, pas un <p> par
ligne du scan), <ul>/<ol>/<li> pour les listes, <table> avec <tr>/<th>/<td> pour les tableaux, <b> et <i> pour le
gras et l'italique, style="text-align:center" ou "text-align:right" quand c'est le cas sur la page.
Un en-tête d'adresse ou une signature : garde les retours à la ligne avec <br>. Un logo, une image ou une
signature manuscrite : écris [image] ou [signature] à sa place. Un mot illisible : [illisible].
Réponds uniquement par le HTML du contenu (sans <html>, <head> ni <body>), sans balises de code."""

CSS = """
* { font-family: sans-serif; }
body { font-size: 10.5pt; line-height: 1.35; color: #111; }
h1 { font-size: 17pt; margin: 0 0 8pt 0; } h2 { font-size: 13.5pt; margin: 10pt 0 5pt 0; }
h3 { font-size: 11.5pt; margin: 8pt 0 4pt 0; }
p { margin: 0 0 6pt 0; text-align: justify; }
table { border-collapse: collapse; width: 100%; margin: 4pt 0 8pt 0; }
td, th { border: 0.6pt solid #888; padding: 2pt 4pt; font-size: 9.5pt; vertical-align: top; }
th { background-color: #eee; }
li { margin-bottom: 2pt; }
"""


def _html_propre(h):
    h = re.sub(r"^```(?:html)?\s*|\s*```$", "", (h or "").strip())
    h = re.sub(r"(?is)<(script|style|head)\b.*?</\1>", "", h)
    h = re.sub(r"(?is)</?(html|body)[^>]*>", "", h)
    return h


def html_vers_pdf(pages_html, largeur=595, hauteur=842, marge=56):
    """PDF A4 : chaque page du scan devient une ou plusieurs pages propres (polices integrees)."""
    import io
    buf = io.BytesIO()
    ecrivain = fitz.DocumentWriter(buf)
    boite = fitz.Rect(0, 0, largeur, hauteur)
    cadre = fitz.Rect(marge, marge, largeur - marge, hauteur - marge)
    for h in pages_html:
        story = fitz.Story(html=_html_propre(h) or "<p></p>", user_css=CSS)
        while True:
            dev = ecrivain.begin_page(boite)
            plus, _f = story.place(cadre)
            story.draw(dev)
            ecrivain.end_page()
            if not plus:
                break
    ecrivain.close()
    return fitz.open("pdf", buf.getvalue())


def _image_page(page, dpi=170):
    pm = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
    if pm.width > 2000:
        pm = page.get_pixmap(matrix=fitz.Matrix(2000 / page.rect.width, 2000 / page.rect.width), colorspace=fitz.csGRAY)
    return pm.tobytes("png")


def remettre_en_page(fenetre, onglet):
    """Chaque page (scannee) relue par l'IA puis recomposee proprement : nouveau document, l'original intact."""
    from .dialogues_ia import verifier_cle, montrer_erreur, executer_suivi
    params = fenetre.params
    if not verifier_cle(fenetre, params):
        return
    n = len(onglet.doc)
    d = QDialog(fenetre)
    d.setWindowTitle(_("Remettre en page un scan"))
    v = QVBoxLayout(d)
    l = QLabel(_("L'IA relit chaque page (image envoyée à {ia}) et la recompose proprement : texte net, titres, "
                 "paragraphes, listes et tableaux, au format A4. Le résultat s'ouvre dans un nouvel onglet ; le "
                 "scan d'origine n'est pas modifié. Relisez le résultat : l'IA peut se tromper sur un mot.",
                 ia=ia.nom_moteur(params)))
    l.setWordWrap(True)
    v.addWidget(l)
    f = QFormLayout()
    de, a = QSpinBox(), QSpinBox()
    for s in (de, a):
        s.setRange(1, n)
    de.setValue(1)
    a.setValue(min(n, 20))
    h = QHBoxLayout()
    h.addWidget(de)
    h.addWidget(QLabel(_("à")))
    h.addWidget(a)
    h.addStretch(1)
    f.addRow(_("Pages"), h)
    v.addLayout(f)
    bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    bb.button(QDialogButtonBox.Ok).setText(_("Envoyer à l'IA"))
    bb.button(QDialogButtonBox.Cancel).setText(_("Annuler"))
    bb.accepted.connect(d.accept)
    bb.rejected.connect(d.reject)
    v.addWidget(bb)
    if d.exec() != QDialog.Accepted:
        return
    pages = list(range(de.value() - 1, max(de.value(), a.value())))
    images = [_image_page(onglet.doc[p]) for p in pages]

    def travail(t):
        out = []
        for k, (p, img) in enumerate(zip(pages, images)):
            t.avancer(_("Page {p} ({k} sur {n})...", p=p + 1, k=k + 1, n=len(pages)), k, len(pages))
            out.append(ia.demander(params, CONSIGNE_MISE_EN_PAGE, _("Page {p} du document.", p=p + 1),
                                   images=[img], max_jetons=8000))
            t.noter(_("Page {p} relue.", p=p + 1))
        return out
    try:
        html = executer_suivi(fenetre, _("Remettre en page un scan"), travail)
    except InterruptedError:
        return
    except Exception as e:                           # noqa: BLE001
        montrer_erreur(fenetre, e)
        return
    doc = html_vers_pdf(html)
    from .document import OngletDocument
    base = os.path.splitext(onglet.nom)[0]
    o = fenetre.ajouter_onglet(OngletDocument(fenetre.params, biblio=fenetre.biblio,
                                              doc=fitz.open("pdf", doc.tobytes(garbage=3, deflate=True)),
                                              nom=_("{nom} (remis en page).pdf", nom=base)))
    if onglet.chemin and not getattr(onglet, "distant", None):
        o.dossier_propose = os.path.dirname(onglet.chemin)
    o.modifie = True
    fenetre._maj_titre(o)
    fenetre.statusBar().showMessage(_("Document remis en page : relisez-le puis enregistrez-le (Ctrl+S)."), 10000)


# ================================================================ extraire les donnees
MODELES = [
    ("facture", _("Facture, ticket, devis"),
     "fournisseur, numéro de facture, date, date d'échéance, client, montant HT, TVA (taux et montant), montant TTC, "
     "moyen de paiement, IBAN du fournisseur ; et les lignes (désignation, quantité, prix unitaire, total)"),
    ("releve", _("Relevé bancaire"),
     "banque, titulaire, numéro de compte (4 derniers chiffres seulement), période, solde initial, solde final ; et "
     "les opérations (date, libellé, débit, crédit)"),
    ("courrier", _("Courrier, avis, attestation"),
     "expéditeur, destinataire, date, référence ou numéro de dossier, objet, montants mentionnés, échéances et ce "
     "qu'il faut faire"),
    ("perso", _("Champs de mon choix..."), ""),
]

CONSIGNE_DONNEES = """Tu extrais les données d'un document. Champs voulus : {champs}.
Réponds en JSON : {{"champs": [{{"nom": "<nom du champ>", "valeur": "<valeur telle qu'écrite>"}}],
"tableau": {{"colonnes": ["..."], "lignes": [["...", "..."]]}}}}.
Mets "tableau" à null s'il n'y a pas de lignes répétées (articles, opérations...). Recopie les valeurs exactement
(nombres avec la virgule décimale, dates en JJ/MM/AAAA). Un champ absent du document : valeur vide, ne devine pas."""


class DialogueDonnees(QDialog):
    def __init__(self, parent, onglet, r):
        super().__init__(parent)
        self.o = onglet
        self.setWindowTitle(_("Données extraites"))
        self.resize(820, 620)
        v = QVBoxLayout(self)
        v.addWidget(QLabel(_("Vérifiez et corrigez si besoin (double-clic sur une case), puis copiez ou enregistrez.")))
        self.t_champs = QTableWidget(0, 2)
        self.t_champs.setObjectName("donnees_champs")
        self.t_champs.setHorizontalHeaderLabels([_("Champ"), _("Valeur")])
        self.t_champs.verticalHeader().hide()
        self.t_champs.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.t_champs.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        for c in r.get("champs") or []:
            i = self.t_champs.rowCount()
            self.t_champs.insertRow(i)
            self.t_champs.setItem(i, 0, QTableWidgetItem(str(c.get("nom", ""))))
            self.t_champs.setItem(i, 1, QTableWidgetItem(str(c.get("valeur", "") or "")))
        v.addWidget(self.t_champs, 1)
        tab = r.get("tableau") or {}
        cols, lignes = tab.get("colonnes") or [], tab.get("lignes") or []
        self.t_lignes = QTableWidget(len(lignes), len(cols))
        self.t_lignes.setObjectName("donnees_lignes")
        self.t_lignes.setHorizontalHeaderLabels([str(c) for c in cols])
        for i, l in enumerate(lignes):
            for j, x in enumerate(l[:len(cols)]):
                self.t_lignes.setItem(i, j, QTableWidgetItem("" if x is None else str(x)))
        self.t_lignes.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        if cols:
            v.addWidget(QLabel(_("<b>Lignes</b> ({n})", n=len(lignes))))
            v.addWidget(self.t_lignes, 2)
        else:
            self.t_lignes.hide()
        h = QHBoxLayout()
        b = QPushButton(_("Copier (pour Excel ou un e-mail)"))
        b.clicked.connect(self.copier)
        h.addWidget(b)
        b = QPushButton(_("Enregistrer en Excel..."))
        b.clicked.connect(self.excel)
        h.addWidget(b)
        h.addStretch(1)
        b = QPushButton(_("Fermer"))
        b.clicked.connect(self.accept)
        h.addWidget(b)
        v.addLayout(h)

    def _lignes_champs(self):
        return [[self.t_champs.item(i, j).text() if self.t_champs.item(i, j) else "" for j in range(2)]
                for i in range(self.t_champs.rowCount())]

    def _tableau(self):
        t = self.t_lignes
        cols = [t.horizontalHeaderItem(j).text() for j in range(t.columnCount())]
        return cols, [[t.item(i, j).text() if t.item(i, j) else "" for j in range(t.columnCount())]
                      for i in range(t.rowCount())]

    def copier(self):
        txt = "\n".join("\t".join(l) for l in self._lignes_champs())
        cols, lignes = self._tableau()
        if cols:
            txt += "\n\n" + "\n".join("\t".join(l) for l in [cols] + lignes)
        QApplication.clipboard().setText(txt)
        self.setWindowTitle(_("Données extraites — copiées"))

    def excel(self):
        base = os.path.splitext(self.o.nom)[0] + _(" (données).xlsx")
        dossier = os.path.dirname(self.o.chemin) if self.o.chemin and not getattr(self.o, "distant", None) else ""
        f, _x = QFileDialog.getSaveFileName(self, _("Enregistrer en Excel"), os.path.join(dossier, base),
                                           _("Classeur Excel (*.xlsx)"))
        if not f:
            return
        from openpyxl import Workbook
        from openpyxl.styles import Font
        from moteur.tableaux import valeur_cellule
        wb = Workbook()
        ws = wb.active
        ws.title = _("Données")
        for l in self._lignes_champs():
            ws.append([l[0], valeur_cellule(l[1])])
            ws.cell(ws.max_row, 1).font = Font(bold=True)
        cols, lignes = self._tableau()
        if cols:
            ws2 = wb.create_sheet(_("Lignes"))
            ws2.append(cols)
            for c in ws2[1]:
                c.font = Font(bold=True)
            for l in lignes:
                ws2.append([valeur_cellule(x) for x in l])
        for w in wb.worksheets:
            for col in w.columns:
                w.column_dimensions[col[0].column_letter].width = min(60, max(10, max(len(str(c.value or ""))
                                                                                     for c in col) + 2))
        try:
            wb.save(f)
        except OSError as e:
            QMessageBox.warning(self, self.windowTitle(), _("Enregistrement impossible : {e}", e=e))
            return
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl.fromLocalFile(f))


def extraire_donnees(fenetre, onglet):
    from .dialogues_ia import preparer_envoi, verifier_cle, montrer_erreur, executer
    params = fenetre.params
    if not verifier_cle(fenetre, params):
        return
    d = QDialog(fenetre)
    d.setWindowTitle(_("Extraire les données"))
    d.setMinimumWidth(520)
    v = QVBoxLayout(d)
    f = QFormLayout()
    cb = QComboBox()
    for k, lib, _c in MODELES:
        cb.addItem(lib, k)
    cb.setCurrentIndex(max(0, cb.findData(params.get("ia_donnees_modele", "facture"))))
    f.addRow(_("Type de document"), cb)
    champs = QLineEdit(params.get("ia_donnees_champs", ""))
    champs.setPlaceholderText(_("ex. nom du patient, date de naissance, médecin, date de l'ordonnance"))
    f.addRow(_("Champs voulus"), champs)
    v.addLayout(f)
    cb.currentIndexChanged.connect(lambda _i: champs.setEnabled(cb.currentData() == "perso"))
    champs.setEnabled(cb.currentData() == "perso")
    bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    bb.button(QDialogButtonBox.Ok).setText(_("Extraire"))
    bb.button(QDialogButtonBox.Cancel).setText(_("Annuler"))
    bb.accepted.connect(d.accept)
    bb.rejected.connect(d.reject)
    v.addWidget(bb)
    if d.exec() != QDialog.Accepted:
        return
    k = cb.currentData()
    liste = champs.text().strip() if k == "perso" else next(c for kk, _l, c in MODELES if kk == k)
    if not liste:
        return
    params["ia_donnees_modele"] = k
    if k == "perso":
        params["ia_donnees_champs"] = liste
    params.enregistrer()
    texte = ia.texte_document(onglet.doc, 60000)
    images = None
    if len(texte.strip()) < 40:                      # scan sans texte : on envoie les images des premieres pages
        images = [_image_page(onglet.doc[p]) for p in range(min(4, len(onglet.doc)))]
        texte = _("Document scanné : voir les images des pages.")
    elif not preparer_envoi(fenetre, params, texte):
        return
    consigne = CONSIGNE_DONNEES.format(champs=liste) + f"\nDate du jour : {datetime.date.today().isoformat()}."
    try:
        r = executer(fenetre, _("L'IA lit le document..."),
                     lambda: ia.demander(params, consigne, texte, images=images, json_attendu=True, max_jetons=6000))
    except Exception as e:                           # noqa: BLE001
        montrer_erreur(fenetre, e)
        return
    if isinstance(r, dict):
        DialogueDonnees(fenetre, onglet, r).exec()
