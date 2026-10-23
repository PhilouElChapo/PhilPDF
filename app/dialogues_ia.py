"""Fenetres de l'assistant IA : resume, renommer et classer (et la tache d'attente commune)."""
import datetime, os, re, shutil

from PySide6.QtCore import Qt, QThread, Signal, QEventLoop
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit, QComboBox,
                               QPushButton, QDialogButtonBox, QTextBrowser, QCheckBox, QProgressDialog, QFileDialog,
                               QMessageBox, QApplication, QListWidget, QListWidgetItem)

from .langue import _
from . import ia, apprentissage


# ------------------------------------------------------------------ tache d'attente
class _Tache(QThread):
    fini = Signal(object, object)

    def __init__(self, fonction):
        super().__init__()
        self.fonction = fonction

    def run(self):
        try:
            self.fini.emit(self.fonction(), None)
        except Exception as e:                          # remonte a l'interface
            self.fini.emit(None, e)


def executer(parent, texte, fonction):
    """Lance fonction() hors de l'interface avec une fenetre d'attente ; renvoie son resultat ou leve son erreur."""
    pd = QProgressDialog(texte, None, 0, 0, parent)
    pd.setWindowTitle("PhilPDF")
    pd.setWindowModality(Qt.WindowModal)
    pd.setMinimumDuration(300)
    t = _Tache(fonction)
    res = {}
    boucle = QEventLoop()

    def fin(r, e):
        res["r"], res["e"] = r, e
        boucle.quit()
    t.fini.connect(fin)
    t.start()
    boucle.exec()
    t.wait()
    pd.close()
    if res.get("e"):
        raise res["e"]
    return res.get("r")


def verifier_cle(parent, params):
    if ia.disponible(params):
        return True
    QMessageBox.information(parent, _("Assistant IA"), _(
        "Pour utiliser l'assistant IA, renseignez votre clef Claude ou Gemini dans Edition › Préférences › IA.\n\n"
        "Rien n'est envoyé sans votre clic, et PhilPDF vous prévient si le document contient des données sensibles."))
    return False


def preparer_envoi(parent, params, texte):
    """Clef presente + rappel des donnees sensibles. True = on peut envoyer."""
    return verifier_cle(parent, params) and ia.confirmer_envoi(parent, texte, ia.nom_moteur(params))


def montrer_erreur(parent, e):
    QMessageBox.warning(parent, _("Assistant IA"), _("L'IA n'a pas pu répondre :\n{e}", e=e))


def _date_valide(d):
    try:
        datetime.date.fromisoformat(str(d)[:10])
        return str(d)[:10]
    except ValueError:
        return ""


# ------------------------------------------------------------------ resume
CONSIGNES_RESUME = """Tu es l'assistant d'un éditeur PDF. Résume le document en français, de façon claire et utile pour
quelqu'un de pressé. Réponds en JSON : {"resume": "<texte en Markdown : un paragraphe de résumé, puis une section
'Points clefs' en liste à puces, puis 'Action attendue' si le document demande quelque chose>",
"echeances": [{"date": "AAAA-MM-JJ", "libelle": "<ce qui est dû à cette date>"}]}.
'echeances' ne contient que les dates limites réelles (délai de recours, date de paiement, rendez-vous...),
calculées si le document donne un délai à partir d'une date. Liste vide s'il n'y en a pas."""


class DialogueResume(QDialog):
    def __init__(self, parent, params, onglet, resultat):
        super().__init__(parent)
        self.params, self.onglet = params, onglet
        self.setWindowTitle(_("Résumé — {nom}", nom=onglet.nom))
        self.resize(720, 620)
        v = QVBoxLayout(self)
        self.texte = QTextBrowser()
        self.texte.setMarkdown(resultat.get("resume", ""))
        v.addWidget(self.texte, 1)
        self.echeances = [e for e in resultat.get("echeances") or [] if _date_valide(e.get("date"))]
        self.case = None
        if self.echeances:
            lst = QListWidget()
            for e in self.echeances:
                lst.addItem(QListWidgetItem(f"{_date_fr(e['date'])} — {e.get('libelle', '')}"))
            lst.setMaximumHeight(min(120, 24 * len(self.echeances) + 8))
            v.addWidget(QLabel(_("<b>Echéances repérées</b>")))
            v.addWidget(lst)
            self.case = QCheckBox(_("Me les rappeler (Accueil, sur tous mes postes)"))
            self.case.setChecked(True)
            v.addWidget(self.case)
        h = QHBoxLayout()
        b = QPushButton(_("Copier"))
        b.clicked.connect(lambda: QApplication.clipboard().setText(self.texte.toPlainText()))
        h.addWidget(b)
        b = QPushButton(_("Ajouter en note sur la page 1"))
        b.clicked.connect(self._note)
        h.addWidget(b)
        h.addStretch(1)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        bb.accepted.connect(self.accept)
        h.addWidget(bb)
        v.addLayout(h)
        self.finished.connect(self._retenir)

    def _note(self):
        p = self.onglet.doc[0]
        self.onglet.memoriser(_("Note de résumé"))
        a = p.add_text_annot((20, 20), self.texte.toPlainText(), icon="Note")
        a.set_info(title=self.params.get("auteur") or "PhilPDF", subject=_("Résumé IA"))
        a.update()
        self.onglet.modifie = True
        self.onglet.rafraichir_pages()
        self.onglet.titre_change.emit()

    def _retenir(self, *_a):
        if self.case and self.case.isChecked():
            for e in self.echeances:
                apprentissage.ajouter_echeance(self.params, _date_valide(e["date"]), e.get("libelle", ""), self.onglet.chemin or self.onglet.nom)


def libelle_dossier(d, params):
    """Texte lisible d'un dossier de classement (local, ou distant:<compte>:<chemin>)."""
    if d.startswith("distant:"):
        from . import distant as D
        _p, cle, chemin = d.split(":", 2)
        c = next((x for x in params.get("comptes", []) if D.cle_compte(x) == cle), None)
        return f"{D.libelle(c) if c else cle.split('|')[1]} : {chemin}"
    return d


def _date_fr(iso):
    try:
        return datetime.date.fromisoformat(iso[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return iso


def resumer(fenetre, onglet):
    params = fenetre.params
    texte = ia.texte_document(onglet.doc)
    if not texte.strip():
        QMessageBox.information(fenetre, _("Résumer avec l'IA"), _(
            "Ce document ne contient pas de texte (scan ?) : lancez d'abord « Reconnaître le texte »."))
        return
    if not preparer_envoi(fenetre, params, texte):
        return
    consignes = CONSIGNES_RESUME + f"\nDate du jour : {datetime.date.today().isoformat()}."
    try:
        r = executer(fenetre, _("L'IA lit le document..."),
                     lambda: ia.demander(params, consignes, texte, json_attendu=True))
    except Exception as e:
        montrer_erreur(fenetre, e)
        return
    if isinstance(r, dict):
        DialogueResume(fenetre, params, onglet, r).exec()


# ------------------------------------------------------------------ renommer et classer
CONSIGNES_CLASSER = """Tu aides à ranger des courriers et documents PDF. Lis le document et réponds en JSON :
{"date": "AAAA-MM-JJ (date du document)", "expediteur": "<organisme ou personne qui l'envoie, nom court usuel,
ex. CPAM, URSSAF, DGFiP, EDF, Maître Dupont>", "objet": "<objet en 2 à 6 mots>",
"type": "<facture, courrier, contrat, relevé, avis, attestation...>",
"dossier": "<un des dossiers proposés qui convient le mieux, recopié exactement, ou chaîne vide>",
"echeances": [{"date": "AAAA-MM-JJ", "libelle": "<ce qui est dû>"}]}"""


def nom_propose(r):
    d = _date_valide(r.get("date")) or datetime.date.today().isoformat()
    exp = (r.get("expediteur") or "").strip()
    obj = (r.get("objet") or "").strip()
    nom = " ".join(x for x in (d, exp) if x) + (f" – {obj}" if obj else "")
    nom = re.sub(r'[\\/:*?"<>|]+', " ", nom)
    return re.sub(r"\s+", " ", nom).strip()[:150] + ".pdf"


class DialogueClasser(QDialog):
    def __init__(self, fenetre, onglet, r, dossiers, appris):
        super().__init__(fenetre)
        self.fenetre, self.params, self.onglet, self.r = fenetre, fenetre.params, onglet, r
        self.distant_choisi = None
        self.setWindowTitle(_("Renommer et classer"))
        self.setMinimumWidth(640)
        v = QVBoxLayout(self)
        info = QLabel(_("<b>{exp}</b> — {type} du {date}<br>{objet}", exp=r.get("expediteur") or "?",
                        type=r.get("type") or _("document"), date=_date_fr(r.get("date") or ""), objet=r.get("objet") or ""))
        info.setWordWrap(True)
        v.addWidget(info)
        f = QFormLayout()
        self.nom = QLineEdit(nom_propose(r))
        f.addRow(_("Nouveau nom"), self.nom)
        self.dest = QComboBox()
        actuel = os.path.dirname(onglet.chemin) if onglet.chemin and not getattr(onglet, "distant", None) else ""
        vus = []
        if appris:
            self.dest.addItem(_("{d}   (appris pour cet expéditeur)", d=libelle_dossier(appris, self.params)), appris)
            vus.append(appris)
        choix_ia = r.get("dossier") or ""
        for d in ([choix_ia] if choix_ia in dossiers else []) + dossiers + ([actuel] if actuel else []):
            if d and d not in vus:
                self.dest.addItem(libelle_dossier(d, self.params) + (_("   (proposé par l'IA)") if d == choix_ia else
                                       _("   (dossier actuel)") if d == actuel else ""), d)
                vus.append(d)
        self.dest.addItem(_("Choisir un dossier sur ce PC..."), "__choisir__")
        if self.params.get("comptes"):
            self.dest.addItem(_("Sur un NAS, un FTP ou un Drive..."), "__distant__")
        self.dest.activated.connect(self._dest_choisie)
        f.addRow(_("Ranger dans"), self.dest)
        v.addLayout(f)
        self.echeances = [e for e in r.get("echeances") or [] if _date_valide(e.get("date"))]
        self.case = None
        if self.echeances:
            self.case = QCheckBox(_("Me rappeler : {liste}", liste="; ".join(
                f"{_date_fr(e['date'])} {e.get('libelle', '')}" for e in self.echeances)))
            self.case.setChecked(True)
            v.addWidget(self.case)
        self.supprimer = QCheckBox(_("Retirer le fichier de son dossier d'origine (sinon : copie)"))
        self.supprimer.setChecked(True)
        self.supprimer.setVisible(bool(actuel))
        v.addWidget(self.supprimer)
        bb = QDialogButtonBox()
        bb.addButton(_("Renommer et classer"), QDialogButtonBox.AcceptRole)
        bb.addButton(_("Annuler"), QDialogButtonBox.RejectRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def _dest_choisie(self, i):
        d = self.dest.itemData(i)
        if d == "__choisir__":
            p = QFileDialog.getExistingDirectory(self, _("Ranger dans"), self.fenetre.dossier_depart())
            if p:
                self.dest.insertItem(0, p, p)
            self.dest.setCurrentIndex(0)
        elif d == "__distant__":
            from .dialogues_distant import DialogueParcourir
            dp = DialogueParcourir(self, self.params, "enregistrer", nom=self.nom.text())
            if dp.exec() == QDialog.Accepted and dp.choisi:
                c = dp.compte()
                self.distant_choisi = (c, dp.choisi)
                self.nom.setText(os.path.basename(dp.choisi))
                lib = f"{c.get('nom')} : {os.path.dirname(dp.choisi) or '/'}"
                self.dest.insertItem(0, lib, "__pris__")
            self.dest.setCurrentIndex(0)

    def destination(self):
        """("local", dossier) ou ("distant", compte, chemin complet)."""
        d = self.dest.currentData()
        if d == "__pris__" and self.distant_choisi:
            c, chemin = self.distant_choisi
            return ("distant", c, os.path.dirname(chemin).rstrip("/") + "/" + self.nom.text().strip())
        if isinstance(d, str) and d.startswith("distant:"):
            _p, cle, chemin = d.split(":", 2)
            from . import distant as D
            c = next((x for x in self.params.get("comptes", []) if D.cle_compte(x) == cle), None)
            if c:
                return ("distant", c, chemin.rstrip("/") + "/" + self.nom.text().strip())
            return ("local", "")
        return ("local", d if d and not d.startswith("__") else "")


def classer(fenetre, onglet):
    params = fenetre.params
    texte = ia.texte_document(onglet.doc, max_car=40000)
    if not texte.strip():
        QMessageBox.information(fenetre, _("Renommer et classer"), _(
            "Ce document ne contient pas de texte (scan ?) : lancez d'abord « Reconnaître le texte »."))
        return
    if not preparer_envoi(fenetre, params, texte):
        return
    dossiers = apprentissage.dossiers_connus_classement(params)
    consignes = CONSIGNES_CLASSER + f"\nDate du jour : {datetime.date.today().isoformat()}.\nDossiers proposés :\n" + \
        ("\n".join(dossiers[:60]) if dossiers else "(aucun pour l'instant)")
    try:
        r = executer(fenetre, _("L'IA lit le document..."), lambda: ia.demander(params, consignes, texte, json_attendu=True))
    except Exception as e:
        montrer_erreur(fenetre, e)
        return
    if not isinstance(r, dict):
        return
    appris = apprentissage.dossier_appris(params, r.get("expediteur", ""))
    d = DialogueClasser(fenetre, onglet, r, dossiers, appris)
    if d.exec() != QDialog.Accepted:
        return
    nom = d.nom.text().strip()
    if not nom.lower().endswith(".pdf"):
        nom += ".pdf"
    dest = d.destination()
    try:
        if dest[0] == "distant":
            _g, c, chemin = dest
            nouveau = classer_distant(fenetre, onglet, c, chemin)
            from . import distant as D
            forme = f"distant:{D.cle_compte(c)}:{os.path.dirname(chemin) or '/'}"
        else:
            dossier = dest[1]
            if not dossier:
                return
            nouveau = classer_local(fenetre, onglet, dossier, nom, d.supprimer.isChecked())
            forme = dossier
    except Exception as e:
        QMessageBox.warning(fenetre, _("Renommer et classer"), _("Classement impossible :\n{e}", e=e))
        return
    if not nouveau:
        return
    apprentissage.retenir_classement(params, r.get("expediteur", ""), forme)
    if d.case and d.case.isChecked():
        for e in d.echeances:
            apprentissage.ajouter_echeance(params, _date_valide(e["date"]), e.get("libelle", ""), nouveau)
    fenetre.statusBar().showMessage(_("Classé : {chemin}", chemin=nouveau), 10000)
    if hasattr(fenetre, "accueil"):
        fenetre.accueil.rafraichir()


def _sans_doublon(chemin):
    if not os.path.exists(chemin):
        return chemin
    base, ext = os.path.splitext(chemin)
    i = 2
    while os.path.exists(f"{base} ({i}){ext}"):
        i += 1
    return f"{base} ({i}){ext}"


def classer_local(fenetre, onglet, dossier, nom, retirer=True):
    os.makedirs(dossier, exist_ok=True)
    cible = os.path.join(dossier, nom)
    ancien = onglet.chemin if onglet.chemin and os.path.exists(onglet.chemin) and not getattr(onglet, "distant", None) else None
    if ancien and os.path.normcase(os.path.abspath(ancien)) == os.path.normcase(os.path.abspath(cible)):
        return cible
    cible = _sans_doublon(cible)
    onglet.enregistrer(cible)                          # garde aussi les modifications en cours
    if ancien and retirer:
        try:
            os.remove(ancien)
        except OSError:
            pass
        fenetre.params["recents"] = [p for p in fenetre.params.get("recents", []) if p != ancien]
    fenetre.params.ajouter_recent(cible)
    fenetre.params.enregistrer()
    fenetre._maj_titre(onglet)
    return cible


def classer_distant(fenetre, onglet, compte, chemin):
    from . import distant as D
    from .config import dossier_donnees
    local = D.cache(dossier_donnees(), compte, chemin)
    onglet.enregistrer(local)
    onglet.chemin, onglet.nom = local, os.path.basename(local)
    onglet.distant = {"compte": compte["id"], "cle": D.cle_compte(compte), "chemin": chemin, "lieu": D.libelle(compte)}
    fenetre._maj_titre(onglet)
    if not fenetre._renvoyer(onglet):
        return None
    return f"{D.libelle(compte)} : {chemin}"


# ------------------------------------------------------------------ comparer deux versions
CONSIGNES_COMPARER = """Tu compares deux versions d'un document (contrat, acte, courrier, devis...). On te donne la liste
numérotée des différences de texte trouvées automatiquement, avec leur contexte. Explique en français ce qui change
concrètement pour le lecteur, en commençant par les changements importants (montants, dates, délais, obligations,
parties, conditions), puis les changements mineurs regroupés en une phrase (orthographe, mise en forme...).
Réponds en HTML simple (<p>, <ul>, <li>, <b>), sans titre général. Cite le numéro de page entre parenthèses."""


class DialogueComparer(QDialog):
    def __init__(self, fenetre, chemin_a="", avec_ia=False):
        super().__init__(fenetre)
        self.fenetre = fenetre
        self.setWindowTitle(_("Comparer deux versions"))
        self.setMinimumWidth(640)
        v = QVBoxLayout(self)
        f = QFormLayout()
        self.a = QLineEdit(chemin_a)
        self.b = QLineEdit()
        for champ, titre in ((self.a, _("Ancienne version")), (self.b, _("Nouvelle version"))):
            h = QHBoxLayout()
            h.addWidget(champ, 1)
            bt = QPushButton(_("Choisir..."))
            bt.clicked.connect(lambda _c=False, champ=champ, titre=titre: self._choisir(champ, titre))
            h.addWidget(bt)
            f.addRow(titre, h)
        v.addLayout(f)
        self.ia = QCheckBox(_("Expliquer les différences avec l'IA (envoie seulement les passages qui changent)"))
        self.ia.setChecked(avec_ia)
        v.addWidget(self.ia)
        n = QLabel(_("Le résultat s'ouvre dans un nouvel onglet : ancienne version à gauche, nouvelle à droite ; "
                     "retraits en rouge, ajouts en vert, modifications en orange."))
        n.setWordWrap(True)
        n.setStyleSheet("color:#555")
        v.addWidget(n)
        bb = QDialogButtonBox()
        bb.addButton(_("Comparer"), QDialogButtonBox.AcceptRole)
        bb.addButton(_("Annuler"), QDialogButtonBox.RejectRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def _choisir(self, champ, titre):
        p, _f = QFileDialog.getOpenFileName(self, titre, self.fenetre.dossier_depart(), "PDF (*.pdf)")
        if p:
            champ.setText(p)


def comparer(fenetre, onglet=None, avec_ia=False):
    import pymupdf as fitz
    from moteur import comparer as C
    from .config import dossier_donnees
    params = fenetre.params
    d = DialogueComparer(fenetre, onglet.chemin if onglet and onglet.chemin else "", avec_ia)
    while True:
        if d.exec() != QDialog.Accepted:
            return
        a, b = d.a.text().strip(), d.b.text().strip()
        if os.path.isfile(a) and os.path.isfile(b):
            break
        QMessageBox.information(fenetre, _("Comparer"), _("Choisissez les deux fichiers PDF à comparer."))
    try:
        doc_a, doc_b = fitz.open(a), fitz.open(b)
        changements = executer(fenetre, _("Comparaison en cours..."), lambda: C.comparer(doc_a, doc_b))
    except Exception as e:
        QMessageBox.warning(fenetre, _("Comparer"), _("Comparaison impossible :\n{e}", e=e))
        return
    explication = None
    if d.ia.isChecked() and changements:
        texte = C.texte_pour_ia(changements)
        if preparer_envoi(fenetre, params, texte):
            try:
                explication = executer(fenetre, _("L'IA analyse les différences..."), lambda: ia.demander(
                    params, CONSIGNES_COMPARER, f"Ancienne version : {os.path.basename(a)}\nNouvelle version : "
                    f"{os.path.basename(b)}\n\nDifférences :\n{texte}", max_jetons=3000))
                explication = re.sub(r"^```(?:html)?\s*|\s*```$", "", explication.strip())
            except Exception as e:
                montrer_erreur(fenetre, e)
    dossier = os.path.join(dossier_donnees(), "comparaisons")
    os.makedirs(dossier, exist_ok=True)
    nom = re.sub(r'[\\/:*?"<>|]+', " ", f"Comparaison {os.path.splitext(os.path.basename(a))[0]} - "
                                           f"{os.path.splitext(os.path.basename(b))[0]}.pdf")
    sortie = _sans_doublon(os.path.join(dossier, nom))
    titres = {"titre": _("Comparaison"), "ancienne": _("Ancienne version"), "nouvelle": _("Nouvelle version"),
              "bilan": _("{m} modification(s), {a} ajout(s), {r} retrait(s)"),
              "identiques": _("Le texte des deux versions est identique."), "explication": _("Ce qui change"),
              "legende": _("Rouge : retiré. Vert : ajouté. Orange : modifié. Comparaison du texte (les images et la mise "
                           "en forme ne sont pas comparées).")}
    try:
        C.rapport(doc_a, doc_b, changements, sortie, os.path.basename(a), os.path.basename(b), explication, titres)
    except Exception as e:
        QMessageBox.warning(fenetre, _("Comparer"), _("Comparaison impossible :\n{e}", e=e))
        return
    fenetre.ouvrir(sortie)
    return sortie


# ------------------------------------------------------------------ traduire
LANGUES_CIBLES = [("anglais", "English", "EN"), ("espagnol", "español", "ES"), ("italien", "italiano", "IT"),
                  ("allemand", "Deutsch", "DE"), ("portugais", "português", "PT"), ("néerlandais", "Nederlands", "NL"),
                  ("français", "français", "FR"), ("arabe", "العربية", "AR"), ("russe", "русский", "RU"),
                  ("chinois", "中文", "ZH"), ("japonais", "日本語", "JA")]
CONSIGNES_TRADUIRE = """Tu traduis les textes d'un document PDF en {langue}. On te donne un objet JSON {{"textes": [...]}} ;
réponds par {{"textes": [...]}} avec exactement le même nombre d'éléments, dans le même ordre, chacun traduit.
Garde les nombres, montants, dates, références, noms propres et adresses tels quels (adapte seulement le format
si c'est l'usage dans la langue cible). Traduction fidèle et naturelle, registre du document, sans commentaire."""


def traduire(fenetre, onglet):
    from PySide6.QtWidgets import QInputDialog
    import json as _json
    import pymupdf as fitz
    from moteur import traduire as T
    params = fenetre.params
    noms = [_(n) + f" ({natif})" if _(n) != natif else natif for n, natif, _c in LANGUES_CIBLES]
    choix, ok = QInputDialog.getItem(fenetre, _("Traduire le document"), _("Traduire en :"), noms, 0, True)
    if not ok or not choix.strip():
        return
    if choix in noms:
        langue, _natif, code = LANGUES_CIBLES[noms.index(choix)]
    else:
        langue, code = choix.strip(), re.sub(r"\W", "", choix.strip())[:2].upper() or "TR"
    doc = fitz.open(stream=onglet.doc.tobytes(), filetype="pdf")
    bs = T.blocs(doc)
    if not bs:
        QMessageBox.information(fenetre, _("Traduire le document"), _(
            "Ce document ne contient pas de texte (scan ?) : lancez d'abord « Reconnaître le texte »."))
        return
    textes = [b["texte"] for b in bs]
    if not preparer_envoi(fenetre, params, "\n".join(textes)):
        return
    consignes = CONSIGNES_TRADUIRE.format(langue=langue)
    traductions = list(textes)

    def travail():
        for lot in T.lots(textes):
            r = ia.demander(params, consignes, _json.dumps({"textes": [textes[i] for i in lot]}, ensure_ascii=False),
                            json_attendu=True, max_jetons=8000)
            res = r.get("textes") if isinstance(r, dict) else r
            if not isinstance(res, list) or len(res) != len(lot):
                raise ia.ErreurIA(_("Réponse de l'IA incomplète (lot de {n} textes).", n=len(lot)))
            for i, t in zip(lot, res):
                traductions[i] = str(t)
        return T.appliquer(doc, bs, traductions)
    try:
        n = executer(fenetre, _("Traduction en {langue} ({n} paragraphes)...", langue=langue, n=len(bs)), travail)
    except Exception as e:
        montrer_erreur(fenetre, e)
        return
    base = onglet.chemin if onglet.chemin and not getattr(onglet, "distant", None) else \
        os.path.join(fenetre.dossier_depart(), onglet.nom)
    sortie = _sans_doublon(f"{os.path.splitext(base)[0]} ({code}).pdf")
    try:
        doc.save(sortie, garbage=3, deflate=True)
    except OSError:
        from .config import dossier_donnees
        sortie = _sans_doublon(os.path.join(dossier_donnees(), os.path.basename(sortie)))
        doc.save(sortie, garbage=3, deflate=True)
    fenetre.ouvrir(sortie)
    fenetre.statusBar().showMessage(_("{n} paragraphe(s) traduit(s) : {chemin}", n=n, chemin=sortie), 10000)
    return sortie


# ------------------------------------------------------------------ OCR IA compare a l'OCR classique
CONSIGNES_OCR = """Tu lis une page scannée. Transcris EXACTEMENT tout le texte visible, dans l'ordre de lecture, ligne
par ligne, avec la ponctuation, les chiffres et les accents tels qu'ils sont imprimés. Ne corrige rien, ne résume
rien, n'ajoute aucun commentaire ni mise en forme. Si un mot est illisible, écris-le au mieux."""


def _png_reduit(nb, largeur_max=2000):
    import cv2
    h, w = nb.shape[:2]
    if w > largeur_max:
        nb = cv2.resize(nb, (largeur_max, int(h * largeur_max / w)), interpolation=cv2.INTER_AREA)
    return cv2.imencode(".png", nb)[1].tobytes()


def _vignette(nb, zone, hauteur=46):
    from PySide6.QtGui import QImage, QPixmap
    import numpy as np
    x0, y0, x1, y1 = [int(v) for v in zone]
    h, w = nb.shape[:2]
    morceau = np.ascontiguousarray(nb[max(0, y0):min(h, y1), max(0, x0):min(w, x1)])
    if morceau.size == 0:
        return QPixmap()
    img = QImage(morceau.data, morceau.shape[1], morceau.shape[0], morceau.strides[0], QImage.Format_Grayscale8).copy()
    return QPixmap.fromImage(img).scaledToHeight(hauteur, Qt.SmoothTransformation)


class DialogueOCRIA(QDialog):
    """Une ligne par difference : l'image du passage, la lecture de Tesseract, celle de l'IA ; vous choisissez."""

    def __init__(self, parent, lignes):
        from PySide6.QtWidgets import QScrollArea, QWidget, QGridLayout, QFrame
        super().__init__(parent)
        self.setWindowTitle(_("OCR IA comparé — {n} différence(s)", n=len(lignes)))
        self.resize(900, 640)
        v = QVBoxLayout(self)
        t = QLabel(_("Pour chaque passage, choisissez la bonne lecture (ou corrigez-la). Vos choix sont retenus : les mots "
                     "rejoignent votre liste personnelle et les corrections confirmées deux fois s'appliqueront seules, "
                     "sur tous vos postes."))
        t.setWordWrap(True)
        v.addWidget(t)
        zone = QScrollArea()
        zone.setWidgetResizable(True)
        w = QWidget()
        g = QGridLayout(w)
        g.setColumnStretch(1, 2)
        g.setColumnStretch(2, 1)
        g.setColumnStretch(3, 1)
        for c, titre in enumerate((_("Image"), _("Lecture retenue"), _("Tesseract"), _("IA"))):
            l = QLabel(f"<b>{titre}</b>")
            g.addWidget(l, 0, c)
        self.choix = []
        for i, ln in enumerate(lignes, 1):
            im = QLabel()
            im.setPixmap(ln["vignette"])
            im.setFrameShape(QFrame.StyledPanel)
            g.addWidget(im, i, 0)
            cb = QComboBox()
            cb.setEditable(True)
            for x in dict.fromkeys([ln["ia"], ln["tesseract"]]):
                cb.addItem(x if x else _("(rien)"), x)
            cb.setCurrentIndex(0)
            g.addWidget(cb, i, 1)
            lt = QLabel(ln["tesseract"] + (_("  (règle apprise)") if ln.get("auto") else ""))
            lt.setStyleSheet("color:#8a1c1c")
            g.addWidget(lt, i, 2)
            la = QLabel(ln["ia"])
            la.setStyleSheet("color:#1d6b2f")
            g.addWidget(la, i, 3)
            self.choix.append(cb)
        g.setRowStretch(len(lignes) + 1, 1)
        zone.setWidget(w)
        v.addWidget(zone, 1)
        h = QHBoxLayout()
        b = QPushButton(_("Tout selon l'IA"))
        b.clicked.connect(lambda: [cb.setCurrentIndex(0) for cb in self.choix])
        h.addWidget(b)
        b = QPushButton(_("Tout selon Tesseract"))
        b.clicked.connect(lambda: [cb.setCurrentIndex(cb.count() - 1) for cb in self.choix])
        h.addWidget(b)
        h.addStretch(1)
        bb = QDialogButtonBox()
        bb.addButton(_("Valider et apprendre"), QDialogButtonBox.AcceptRole)
        bb.addButton(_("Annuler"), QDialogButtonBox.RejectRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        h.addWidget(bb)
        v.addLayout(h)

    def valeurs(self):
        out = []
        for cb in self.choix:
            i = cb.findText(cb.currentText())
            out.append(cb.itemData(i) if i >= 0 and cb.itemData(i) is not None else cb.currentText().strip())
        return out


def ocr_ia(fenetre, onglet):
    from moteur import scan
    from .config import dossier_donnees
    params = fenetre.params
    if not scan.tesseract_exe():
        QMessageBox.information(fenetre, _("OCR IA comparé"), _(
            "Le module de reconnaissance de texte est absent de ce paquet PhilPDF.\nTéléchargez la version complète (elle l'embarque)."))
        return
    if not onglet.chemin or onglet.modifie:
        QMessageBox.information(fenetre, _("OCR IA comparé"), _("Enregistrez d'abord le document."))
        return
    if not verifier_cle(fenetre, params):
        return
    try:
        an = executer(fenetre, _("Lecture par Tesseract (redressement, nettoyage)..."),
                      lambda: scan.analyser(onglet.chemin, apprentissage=apprentissage.ocr_appris(params)))
    except Exception as e:
        QMessageBox.warning(fenetre, _("OCR IA comparé"), _("La reconnaissance a échoué :\n{e}", e=e))
        return
    a_lire = [pg for pg in an["pages"] if not pg["garder"]]
    if not a_lire:
        QMessageBox.information(fenetre, _("OCR IA comparé"), _(
            "Ce document contient déjà du texte sur toutes ses pages : il n'y a rien à reconnaître. "
            "(La reconnaissance sert aux scans et aux photos de documents.)"))
        return
    texte_classique = "\n".join(" ".join(m["texte"] for m in pg["mots"]) for pg in a_lire)
    if not ia.confirmer_envoi(fenetre, texte_classique, ia.nom_moteur(params)):
        return

    def lire_ia():
        for pg in a_lire:
            pg["texte_ia"] = ia.demander(params, CONSIGNES_OCR, _("Page {n}", n=pg["num"] + 1),
                                         images=[_png_reduit(pg["image"])], max_jetons=8000)
    try:
        executer(fenetre, _("Lecture par l'IA ({n} page(s))...", n=len(a_lire)), lire_ia)
    except Exception as e:
        montrer_erreur(fenetre, e)
        return
    lignes = []
    for pg in a_lire:
        auto = {i: (avant, apres) for i, avant, apres in pg["auto"]}
        vus = set()
        for d in scan.differences(pg["mots"], pg["texte_ia"]):
            lignes.append(dict(d, page=pg, vignette=_vignette(pg["image"], scan.zone_mots(pg["mots"], d["i1"], d["i2"]))))
            vus.update(range(d["i1"], d["i2"]))
        for i, (avant, apres) in auto.items():        # corrections appliquees seules : montrees pour controle
            if i not in vus:
                lignes.append({"i1": i, "i2": i + 1, "tesseract": avant, "ia": apres, "auto": True, "page": pg,
                               "vignette": _vignette(pg["image"], scan.zone_mots(pg["mots"], i, i + 1))})
    if lignes:
        d = DialogueOCRIA(fenetre, lignes)
        if d.exec() != QDialog.Accepted:
            return
        corrections = []
        echantillons = os.path.join(dossier_donnees(), "apprentissage_ocr")
        os.makedirs(echantillons, exist_ok=True)
        for ln, val in zip(lignes, d.valeurs()):
            pg = ln["page"]
            actuel = " ".join(m["texte"] for m in pg["mots"][ln["i1"]:ln["i2"]] if m["texte"])
            if val != actuel:
                scan.remplacer_mots(pg["mots"], ln["i1"], ln["i2"], val)
                pg["modifie"] = True
            corrections.append((ln["tesseract"], val))
            if val and val != ln["tesseract"]:            # echantillon image + verite, pour un futur entrainement
                try:
                    import cv2, hashlib
                    x0, y0, x1, y1 = [int(v) for v in scan.zone_mots(pg["mots"], ln["i1"], ln["i2"], 2)]
                    morceau = pg["image"][max(0, y0):y1, max(0, x0):x1]
                    cle = hashlib.sha1(morceau.tobytes()).hexdigest()[:12]
                    cv2.imwrite(os.path.join(echantillons, cle + ".png"), morceau)
                    with open(os.path.join(echantillons, cle + ".gt.txt"), "w", encoding="utf-8") as f:
                        f.write(val)
                except Exception:
                    pass
        apprentissage.retenir_ocr(params, corrections)
    else:
        QMessageBox.information(fenetre, _("OCR IA comparé"), _("Tesseract et l'IA ont lu exactement la même chose."))
    sortie = _sans_doublon(os.path.splitext(onglet.chemin)[0] + "_OCR.pdf")
    try:
        scan.assembler(an, sortie)
    except Exception as e:
        QMessageBox.warning(fenetre, _("OCR IA comparé"), _("Enregistrement impossible :\n{e}", e=e))
        return
    fenetre.ouvrir(sortie)
    fenetre.statusBar().showMessage(_("Texte reconnu et vérifié : {nom}", nom=os.path.basename(sortie)), 10000)
    return sortie
