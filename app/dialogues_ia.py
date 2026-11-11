"""Fenetres de l'assistant IA : resume, renommer et classer (et la tache d'attente commune)."""
import datetime, os, re, shutil

from PySide6.QtCore import Qt, QThread, Signal, QEventLoop
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit, QComboBox,
                               QPushButton, QDialogButtonBox, QTextBrowser, QCheckBox, QProgressDialog, QFileDialog,
                               QMessageBox, QApplication, QListWidget, QListWidgetItem, QPlainTextEdit)

import pymupdf as fitz

from .langue import _
from . import ia, apprentissage


def boutons_fr(bb):
    from .dialogues import boutons_fr as b
    return b(bb)


# ------------------------------------------------------------------ tache d'attente
class _Tache(QThread):
    fini = Signal(object, object)
    info = Signal(str)

    def __init__(self, fonction):
        super().__init__()
        self.fonction = fonction

    def run(self):
        ia.suivre(self.info.emit)
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
    import time
    debut = time.monotonic()
    t.info.connect(lambda m: pd.setLabelText(f"{texte}\n\n[{int(time.monotonic() - debut)} s] {m}"))

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


class _TacheSuivie(QThread):
    etape = Signal(str, int, int)          # texte, valeur, total
    detail = Signal(str)
    fini = Signal(object, object)

    def __init__(self, fonction):
        super().__init__()
        self.fonction, self.stop = fonction, False

    def run(self):
        ia.suivre(self.detail.emit)
        try:
            self.fini.emit(self.fonction(self), None)
        except Exception as e:
            self.fini.emit(None, e)

    def avancer(self, texte, valeur=0, total=0):
        if self.stop:
            raise InterruptedError(_("Arrêté à votre demande."))
        self.etape.emit(texte, valeur, total)

    def noter(self, texte):
        self.detail.emit(texte)


class Avancement(QDialog):
    """Fenetre d'avancement : etape en cours, barre (page x / y), detail des operations, bouton Arreter.

    bloquante=False (telechargement, conversion, lecture : rien ne change dans le document ouvert) : la fenetre ne
    bloque pas PhilPDF, et « Reduire » la range dans la barre d'etat (barre + « Afficher ») ; on continue de
    travailler. bloquante=True seulement quand la tache modifie le document ouvert (sinon on le changerait deux fois)."""

    def __init__(self, parent, titre, bloquante=True):
        from PySide6.QtWidgets import QProgressBar, QPlainTextEdit
        super().__init__(parent)
        self.setWindowTitle(titre)
        self.setMinimumWidth(560)
        self.bloquante = bloquante
        self.en_cours = True
        self.setWindowModality(Qt.WindowModal if bloquante else Qt.NonModal)
        self._reduite = None
        v = QVBoxLayout(self)
        self.etat = QLabel(_("Préparation..."))
        self.etat.setWordWrap(True)
        v.addWidget(self.etat)
        self.barre = QProgressBar()
        self.barre.setRange(0, 0)
        v.addWidget(self.barre)
        self.journal = QPlainTextEdit()
        self.journal.setReadOnly(True)
        self.journal.setMaximumHeight(150)
        self.journal.setStyleSheet("font-size:12px;color:#444")
        v.addWidget(self.journal)
        h = QHBoxLayout()
        if not bloquante:
            note = QLabel(_("Vous pouvez continuer à travailler pendant ce temps."))
            note.setStyleSheet("color:#666")
            h.addWidget(note)
        h.addStretch(1)
        if not bloquante:
            self.b_reduire = QPushButton(_("Réduire"))
            self.b_reduire.setToolTip(_("Ranger cette fenêtre dans la barre d'état, en bas ; « Afficher » la rouvre."))
            self.b_reduire.clicked.connect(self.reduire)
            h.addWidget(self.b_reduire)
        self.b_stop = QPushButton(_("Arrêter"))
        h.addWidget(self.b_stop)
        v.addLayout(h)

    def _barre_etat(self):
        w = self.parent()
        while w is not None and not hasattr(w, "statusBar"):
            w = w.parent()
        return w.statusBar() if w is not None else None

    def reduire(self):
        """Fenetre rangee dans la barre d'etat de la fenetre principale : titre, barre, « Afficher »."""
        from PySide6.QtWidgets import QProgressBar, QWidget
        be = self._barre_etat()
        if be is None:
            self.showMinimized()
            return
        if self._reduite is None:
            z = QWidget()
            hz = QHBoxLayout(z)
            hz.setContentsMargins(0, 0, 0, 0)
            z.texte = QLabel()
            z.texte.setMaximumWidth(360)
            z.barre = QProgressBar()
            z.barre.setMaximumWidth(160)
            z.barre.setMaximumHeight(16)
            b = QPushButton(_("Afficher"))
            b.setFlat(True)
            b.setStyleSheet("color:#0b62c4;text-decoration:underline")
            b.clicked.connect(self.afficher)
            for x in (z.texte, z.barre, b):
                hz.addWidget(x)
            be.addPermanentWidget(z)
            self._reduite = z
        self._copier_vers_reduite()
        self._reduite.show()
        self.hide()

    def afficher(self):
        if self._reduite is not None:
            self._reduite.hide()
        self.show()
        self.raise_()
        self.activateWindow()

    def _copier_vers_reduite(self):
        z = self._reduite
        if z is None:
            return
        z.texte.setText(self.windowTitle() + " — " + self.etat.text())
        z.barre.setRange(self.barre.minimum(), self.barre.maximum())
        z.barre.setValue(self.barre.value())
        z.barre.setFormat(self.barre.format())

    def done(self, r):
        self._retirer_reduite()
        super().done(r)

    def closeEvent(self, e):
        if getattr(self, "en_cours", False) and not self.bloquante:   # la croix range la fenetre, rien ne s'arrete en cachette
            e.ignore()
            self.reduire()
            return
        self._retirer_reduite()
        super().closeEvent(e)

    def reject(self):                                    # Echap : pareil que la croix
        if getattr(self, "en_cours", False) and not self.bloquante:
            self.reduire()
            return
        super().reject()

    def _retirer_reduite(self):
        z, self._reduite = self._reduite, None
        if z is not None:
            try:
                be = self._barre_etat()
                if be is not None:
                    be.removeWidget(z)
                z.deleteLater()
            except RuntimeError:                         # fenetre principale deja fermee
                pass

    def terminer(self):
        """Fin de la tache : fenetre et barre d'etat rangees."""
        self.en_cours = False
        self._retirer_reduite()
        self.close()

    def etape(self, texte, valeur, total):
        self.etat.setText(texte)
        if total:
            self.barre.setRange(0, total)
            self.barre.setValue(valeur)
            self.barre.setFormat(f"{valeur} / {total}")
        else:
            self.barre.setRange(0, 0)
        self._copier_vers_reduite()

    def noter(self, texte):
        import time
        self.journal.appendPlainText(time.strftime("%H:%M:%S  ") + texte)


_ABANDONNEES = []          # taches arretees qui finissent en arriere-plan (leur resultat est ignore)


def executer_suivi(parent, titre, fonction, abandonner=False, bloquante=True):
    """Comme executer(), avec une fenetre d'avancement : fonction(tache) appelle tache.avancer(texte, n, total)
    et tache.noter(detail). Leve l'erreur de fonction, ou InterruptedError si l'utilisateur arrete.
    abandonner : « Arreter » rend la main tout de suite (reseau qui ne repond pas...) ; la tache finit seule, ignoree.
    bloquante=False : on continue de travailler pendant la tache (voir Avancement)."""
    dlg = Avancement(parent, titre, bloquante)
    t = _TacheSuivie(fonction)
    res = {}
    boucle = QEventLoop()
    t.etape.connect(dlg.etape)
    t.detail.connect(dlg.noter)
    t.fini.connect(lambda r, e: (res.setdefault("r", r), res.setdefault("e", e), boucle.quit()))

    def arreter():
        t.stop = True
        dlg.etat.setText(_("Arrêt en cours..."))
        if abandonner:
            res.update(r=None, e=InterruptedError(_("Arrêté à votre demande.")))
            boucle.quit()
    dlg.b_stop.clicked.connect(arreter)
    t.start()
    # la fenetre ne s'ouvre que si la tache dure : pas de clignotement pour une tache de quelques millisecondes
    from PySide6.QtCore import QTimer
    QTimer.singleShot(400, lambda: (not res) and dlg.show())
    boucle.exec()
    if t.isRunning():
        if abandonner:
            _ABANDONNEES.append(t)
            t.finished.connect(lambda t=t: t in _ABANDONNEES and _ABANDONNEES.remove(t))
        else:
            t.wait()
    dlg.terminer()
    if res.get("e"):
        raise res["e"]
    return res.get("r")


def en_tache(parent, titre, texte, fonction, *args, lecture=False, bloquante=True):
    """Longue tache sans etapes : fenetre d'avancement (texte, barre animee, Arreter) si elle dure, erreur levee.
    lecture : la tache ne change rien (lire, lister, tester) ; « Arreter » rend alors la main tout de suite. Une tache
    qui ecrit va au bout de ce qu'elle a commence : rien ne continue en cachette."""
    def travail(t):
        t.avancer(texte)
        return fonction(*args)
    return executer_suivi(parent, titre, travail, abandonner=lecture, bloquante=bloquante)


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
"echeances": [{"date": "AAAA-MM-JJ", "heure": "HH:MM ou vide", "type": "rendez-vous ou échéance",
"libelle": "<ce qui est dû ou prévu à cette date, avec le lieu pour un rendez-vous>"}]}.
'echeances' ne contient que les dates réelles (rendez-vous, convocation, délai de recours, date de paiement...),
calculées si le document donne un délai à partir d'une date. 'heure' seulement si le document la donne.
Liste vide s'il n'y en a pas."""


def consignes_resume():
    """Consigne du resume dans la langue de l'interface (le resume est lu par l'utilisateur)."""
    from .langue import LANGUE, NOMS
    nom = {"fr": "français", "en": "anglais", "de": "allemand", "es": "espagnol", "it": "italien"}.get(LANGUE, NOMS.get(LANGUE, "français"))
    return CONSIGNES_RESUME.replace("Résume le document en français", f"Résume le document en {nom}")


class DialogueResume(QDialog):
    def __init__(self, parent, params, onglet, resultat):
        super().__init__(parent)
        self.params, self.onglet = params, onglet
        self.setWindowTitle(_("Résumé — {nom}", nom=onglet.nom))
        self.resize(720, 620)
        v = QVBoxLayout(self)
        d = ia.dernier
        if d.get("moteur"):
            noms = {"claude": "Claude", "gemini": "Gemini"}
            src = QLabel(_("Résumé fait par {ia} (modèle {modele})", ia=noms.get(d["moteur"], d["moteur"]), modele=d.get("modele", "?"))
                         + (_(" — {autre} était surchargé ou injoignable", autre=noms.get(d.get("premier"), "?")) if d.get("secours") else ""))
            src.setStyleSheet("color:#666;font-size:11px")
            v.addWidget(src)
        self.texte = QTextBrowser()
        self.texte.setMarkdown(resultat.get("resume", ""))
        v.addWidget(self.texte, 1)
        self.echeances = [e for e in resultat.get("echeances") or [] if _date_valide(e.get("date"))]
        self.case = None
        self.table = None
        from . import agenda
        if self.echeances:
            from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
            lb = QLabel(_("<b>Dates repérées</b> — rien n'est retenu sans votre accord : cochez ce qui doit apparaître "
                          "sur l'Accueil (sur tous vos postes), corrigez le texte si besoin, et « Agenda » ouvre votre agenda "
                          "avec le rendez-vous pré-rempli, à enregistrer vous-même."))
            lb.setWordWrap(True)
            v.addWidget(lb)
            t = self.table = QTableWidget(len(self.echeances), 5)
            t.setHorizontalHeaderLabels([_("Accueil"), _("Date"), _("Heure"), _("Ce qui est prévu"), _("Agenda")])
            t.verticalHeader().hide()
            for r, e in enumerate(self.echeances):
                c = QTableWidgetItem()
                c.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                c.setCheckState(Qt.Unchecked)
                t.setItem(r, 0, c)
                for col, val in ((1, _date_fr(e["date"])), (2, (e.get("heure") or "").strip())):
                    it = QTableWidgetItem(val)
                    it.setFlags(Qt.ItemIsEnabled)
                    t.setItem(r, col, it)
                t.setItem(r, 3, QTableWidgetItem(e.get("libelle", "")))
                b = QPushButton(_("Agenda..."))
                b.setToolTip(_("Ouvre votre agenda avec ce rendez-vous pré-rempli : vous vérifiez et enregistrez."))
                b.clicked.connect(lambda _c=False, r=r: self._agenda(r))
                t.setCellWidget(r, 4, b)
            hh = t.horizontalHeader()
            for col in (0, 1, 2, 4):
                hh.setSectionResizeMode(col, QHeaderView.ResizeToContents)
            hh.setSectionResizeMode(3, QHeaderView.Stretch)
            t.setMaximumHeight(min(200, 32 * len(self.echeances) + 34))
            v.addWidget(t)
        ha = QHBoxLayout()
        ha.addWidget(QLabel(_("Agenda :")))
        self.cb_agenda = QComboBox()
        for k, nom in agenda.AGENDAS:
            self.cb_agenda.addItem(_("Fichier .ics (autre agenda)") if k == "ics" else nom, k)
        self.cb_agenda.setCurrentIndex(max(0, self.cb_agenda.findData(params.get("agenda") or "google")))
        ha.addWidget(self.cb_agenda)
        ha.addSpacing(12)
        ha.addWidget(QLabel(_("Messagerie :")))
        self.cb_mail = QComboBox()
        for k, nom in agenda.MESSAGERIES:
            self.cb_mail.addItem(_("Messagerie par défaut") if k == "mailto" else nom, k)
        self.cb_mail.setCurrentIndex(max(0, self.cb_mail.findData(params.get("messagerie") or "gmail")))
        ha.addWidget(self.cb_mail)
        bm = QPushButton(_("M'envoyer ce résumé..."))
        bm.setToolTip(_("Ouvre un nouveau message pré-rempli (résumé et dates) : vous choisissez le destinataire et l'envoyez vous-même."))
        bm.clicked.connect(self._message)
        ha.addWidget(bm)
        ha.addStretch(1)
        v.addLayout(ha)
        h = QHBoxLayout()
        b = QPushButton(_("Copier"))
        b.clicked.connect(lambda: QApplication.clipboard().setText(self.texte.toPlainText()))
        h.addWidget(b)
        b = QPushButton(_("Ajouter en note sur la page 1"))
        b.clicked.connect(self._note)
        h.addWidget(b)
        from . import signaler_ia
        h.addWidget(signaler_ia.bouton(self, self.windowTitle().split(" — ")[0], self.texte.toPlainText))
        h.addStretch(1)
        bf = QPushButton(_("Fermer"))
        bf.clicked.connect(self.accept)
        h.addWidget(bf)
        v.addLayout(h)
        self.finished.connect(self._retenir)

    def _note(self):
        p = self.onglet.doc[0]
        self.onglet.memoriser(_("Note de résumé"))
        a = p.add_text_annot((20, 20), self.texte.toPlainText(), icon="Note")
        a.set_info(title=self.params.get("auteur") or "PhilPDF", subject=_("Résumé IA"))
        a.update()
        self.onglet.apres_modif([_("Note de résumé ajoutée en haut de la page 1.")])

    def _libelle(self, r):
        return self.table.item(r, 3).text().strip() if self.table else self.echeances[r].get("libelle", "")

    def _memoriser_choix(self):
        self.params.update(agenda=self.cb_agenda.currentData(), messagerie=self.cb_mail.currentData())
        self.params.enregistrer()

    def _agenda(self, r):
        from . import agenda
        e = self.echeances[r]
        self._memoriser_choix()
        details = _("D'après « {nom} » (résumé PhilPDF).", nom=self.onglet.nom)
        cible = agenda.lien_agenda(self.cb_agenda.currentData(), self._libelle(r), _date_valide(e["date"]),
                                   (e.get("heure") or "").strip() or None, details)
        agenda.ouvrir(cible)

    def _message(self):
        from . import agenda
        self._memoriser_choix()
        dates = "".join(f"\n- {_date_fr(e['date'])}{' ' + e['heure'] if e.get('heure') else ''} : {self._libelle(r)}"
                        for r, e in enumerate(self.echeances))
        corps = self.texte.toPlainText() + (("\n\n" + _("Dates :") + dates) if dates else "")
        agenda.ouvrir(agenda.lien_message(self.cb_mail.currentData(), _("Résumé — {nom}", nom=self.onglet.nom), corps[:1800]))

    def _retenir(self, *_a):
        if not self.table:
            return
        for r, e in enumerate(self.echeances):
            if self.table.item(r, 0).checkState() == Qt.Checked:
                libelle = self._libelle(r)
                if e.get("heure"):
                    libelle = f"{e['heure']} — {libelle}"
                apprentissage.ajouter_echeance(self.params, _date_valide(e["date"]), libelle, self.onglet.chemin or self.onglet.nom)


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


def demander_consigne(parent, params, titre, cle, consigne_philpdf):
    """Fenetre avant l'envoi : consigne personnelle ajoutee a celle de PhilPDF (None si annule).
    Les 10 dernieres consignes sont gardees (et synchronisees entre postes) pour les reprendre d'un clic."""
    d = QDialog(parent)
    d.setWindowTitle(titre)
    d.resize(640, 420)
    v = QVBoxLayout(d)
    lb = QLabel(_("Vous pouvez ajouter votre propre consigne à celle de PhilPDF (facultatif). "
                  "Ex. : « insiste sur les montants », « fais un résumé en 3 lignes », « dis-moi si je dois répondre »."))
    lb.setWordWrap(True)
    v.addWidget(lb)
    historique = list(params.get(cle) or [])
    cb = QComboBox()
    cb.addItem(_("— consignes déjà utilisées —"), "")
    for h in historique:
        cb.addItem(h if len(h) < 90 else h[:87] + "...", h)
    cb.setEnabled(bool(historique))
    hc = QHBoxLayout()
    hc.addWidget(cb, 1)
    b_sup = QPushButton(_("Supprimer"))
    b_sup.setToolTip(_("Retirer cette consigne de la liste des consignes déjà utilisées"))
    hc.addWidget(b_sup)
    v.addLayout(hc)

    def supprimer():
        x = cb.currentData()
        if not x:
            return
        params[cle] = [h for h in (params.get(cle) or []) if h != x]
        params.enregistrer()
        cb.removeItem(cb.currentIndex())
        cb.setCurrentIndex(0)
        zone.clear()
        b_sup.setEnabled(cb.count() > 1)
        cb.setEnabled(cb.count() > 1)
    b_sup.clicked.connect(supprimer)
    b_sup.setEnabled(bool(historique))
    zone = QPlainTextEdit()
    zone.setPlaceholderText(_("Votre consigne (laisser vide pour la consigne habituelle)"))
    v.addWidget(zone, 1)
    # une consigne tapee ne reste en memoire que si on le demande (sinon elle sert pour cette fois seulement)
    garder = QCheckBox(_("Garder cette consigne dans la liste, pour la reprendre plus tard"))
    garder.setChecked(False)
    v.addWidget(garder)
    cb.currentIndexChanged.connect(lambda i: cb.itemData(i) and zone.setPlainText(cb.itemData(i)))
    voir = QPushButton(_("Voir la consigne de PhilPDF"))
    voir.setCheckable(True)
    texte_ph = QTextBrowser()
    texte_ph.setPlainText(consigne_philpdf)
    texte_ph.hide()
    voir.toggled.connect(texte_ph.setVisible)
    v.addWidget(voir, 0, Qt.AlignLeft)
    v.addWidget(texte_ph, 1)
    hm = QHBoxLayout()
    hm.addWidget(QLabel(_("Envoyer à :")))
    cb_ia = QComboBox()
    for m, _clef in ia.moteurs(params):
        cb_ia.addItem({"claude": "Claude (Anthropic)", "gemini": "Gemini (Google)"}[m], m)
    cb_ia.setToolTip(_("L'IA choisie dans les Préférences est proposée ; vous pouvez en prendre une autre pour cette "
                       "demande seulement"))
    hm.addWidget(cb_ia)
    hm.addStretch(1)
    if cb_ia.count() > 1:
        v.addLayout(hm)
    bb = QDialogButtonBox()
    bb.addButton(_("Lancer l'analyse"), QDialogButtonBox.AcceptRole)
    bb.addButton(_("Annuler"), QDialogButtonBox.RejectRole)
    bb.accepted.connect(d.accept)
    bb.rejected.connect(d.reject)
    v.addWidget(bb)
    zone.setFocus()
    if d.exec() != QDialog.Accepted:
        return None
    ia.MOTEUR_FORCE = cb_ia.currentData() if cb_ia.count() > 1 else None   # pour cette demande
    perso = zone.toPlainText().strip()
    if perso and garder.isChecked():
        params[cle] = [perso] + [h for h in historique if h != perso][:9]
        params.enregistrer()
    return perso


def ajouter_consigne(consignes, perso):
    if not perso:
        return consignes
    return consignes + ("\n\nConsigne supplémentaire de l'utilisateur (à suivre en priorité, en gardant le format de réponse "
                        "demandé) :\n" + perso)


def resumer(fenetre, onglet):
    params = fenetre.params
    texte = ia.texte_document(onglet.doc)
    if not texte.strip():
        QMessageBox.information(fenetre, _("Résumer avec l'IA"), _(
            "Ce document ne contient pas de texte (scan ?) : lancez d'abord « Reconnaître le texte »."))
        return
    perso = demander_consigne(fenetre, params, _("Résumer avec l'IA"), "ia_consignes_resume", consignes_resume())
    if perso is None:
        return
    try:
        if not preparer_envoi(fenetre, params, texte):
            return
        consignes = ajouter_consigne(consignes_resume() + f"\nDate du jour : {datetime.date.today().isoformat()}.", perso)
        try:
            r = executer(fenetre, _("L'IA lit le document..."),
                         lambda: ia.demander(params, consignes, texte, json_attendu=True))
        except Exception as e:
            montrer_erreur(fenetre, e)
            return
    finally:
        ia.MOTEUR_FORCE = None                   # la fois suivante : l'IA des Preferences
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
    """« Expediteur – objet – AAAA-MM-JJ.pdf » : la date a la fin, pour qu'un meme expediteur et un meme objet se
    rangent ensemble, dans l'ordre chronologique."""
    d = _date_valide(r.get("date")) or datetime.date.today().isoformat()
    exp = (r.get("expediteur") or "").strip()
    obj = (r.get("objet") or "").strip()
    nom = " – ".join(x for x in (exp, obj, d) if x)
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
        from . import signaler_ia
        import json as _json
        v.addWidget(signaler_ia.bouton(self, _("Renommer et classer"),
                                       lambda: _json.dumps(self.r, ensure_ascii=False, indent=1, default=str)))
        bb = QDialogButtonBox()
        bb.addButton(_("Renommer et classer"), QDialogButtonBox.AcceptRole)
        bb.addButton(_("Annuler"), QDialogButtonBox.RejectRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def _dest_choisie(self, i):
        d = self.dest.itemData(i)
        if d == "__choisir__":
            p = __import__('app.choix_dossier', fromlist=['x']).choisir_dossier(self, _("Ranger dans"), self.fenetre.dossier_depart())
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


def _vignette(nb, zone, hauteur=34, largeur_max=320):
    from PySide6.QtGui import QImage, QPixmap
    import numpy as np
    x0, y0, x1, y1 = [int(v) for v in zone]
    h, w = nb.shape[:2]
    morceau = np.ascontiguousarray(nb[max(0, y0):min(h, y1), max(0, x0):min(w, x1)])
    if morceau.size == 0:
        return QPixmap()
    img = QImage(morceau.data, morceau.shape[1], morceau.shape[0], morceau.strides[0], QImage.Format_Grayscale8).copy()
    pm = QPixmap.fromImage(img).scaledToHeight(hauteur, Qt.SmoothTransformation)
    return pm if pm.width() <= largeur_max else pm.scaledToWidth(largeur_max, Qt.SmoothTransformation)


def _essentiel(t):
    return re.sub(r"[\W_]+", "", t.lower())


def differences_utiles(mots, texte_ia):
    """Differences qui comptent : ni simple ponctuation, ni majuscules, ni espaces, ni bruit des deux cotes."""
    from moteur import scan
    out = []
    for d in scan.differences(mots, texte_ia):
        a, b = _essentiel(d["tesseract"]), _essentiel(d["ia"])
        if a == b or (not a and not b):
            continue
        out.append(d)
    return out


class DialogueOCRIA(QDialog):
    """Tableau : une ligne par difference. Colonne « A garder » deja remplie avec la lecture de l'IA ;
    on ne touche qu'aux lignes ou l'IA se trompe. Valider = texte du PDF corrige + apprentissage."""

    def __init__(self, parent, lignes, moteur):
        from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
        super().__init__(parent)
        self.lignes = lignes
        self.setWindowTitle(_("OCR IA comparé — {n} différence(s) à vérifier", n=len(lignes)))
        self.resize(1100, 700)
        v = QVBoxLayout(self)
        t = QLabel(_("<b>Comment faire :</b> chaque ligne est un passage que Tesseract et {ia} n'ont pas lu pareil. "
                     "La colonne <b>A garder</b> contient déjà la lecture de l'IA (souvent la meilleure) : regardez "
                     "l'image et ne corrigez que si elle se trompe (double-clic dans la case, ou clic sur la lecture de Tesseract). "
                     "Puis <b>Valider</b> : le texte du PDF est corrigé et PhilPDF retient vos corrections pour les "
                     "prochaines lectures, sur tous vos postes.", ia=moteur))
        t.setWordWrap(True)
        v.addWidget(t)
        self.table = QTableWidget(len(lignes), 5)
        self.table.setHorizontalHeaderLabels([_("Page"), _("Image du passage"), _("Tesseract"), _("IA ({nom})", nom=moteur),
                                              _("A garder")])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed |
                                   QAbstractItemView.AnyKeyPressed)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.Fixed)
        self.table.setColumnWidth(1, 330)
        for c in (2, 3, 4):
            hh.setSectionResizeMode(c, QHeaderView.Stretch)
        for i, ln in enumerate(lignes):
            it = QTableWidgetItem(str(ln["page"]["num"] + 1))
            it.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(i, 0, it)
            im = QLabel()
            im.setPixmap(ln["vignette"])
            im.setAlignment(Qt.AlignCenter)
            self.table.setCellWidget(i, 1, im)
            for c, txt, coul in ((2, ln["tesseract"] + (_("  (règle apprise)") if ln.get("auto") else ""), "#8a1c1c"),
                                 (3, ln["ia"], "#1d6b2f")):
                it = QTableWidgetItem(txt)
                it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                from PySide6.QtGui import QColor
                it.setForeground(QColor(coul))
                self.table.setItem(i, c, it)
            self.table.setItem(i, 4, QTableWidgetItem(ln["ia"]))
            self.table.setRowHeight(i, 40)
        self.table.cellClicked.connect(self._clic)
        v.addWidget(self.table, 1)
        n = QLabel(_("Astuce : cliquez sur la colonne Tesseract ou IA d'une ligne pour recopier cette lecture dans « A garder »."))
        n.setStyleSheet("color:#666;font-size:12px")
        v.addWidget(n)
        h = QHBoxLayout()
        b = QPushButton(_("Tout selon l'IA"))
        b.clicked.connect(lambda: self._tout(3))
        h.addWidget(b)
        b = QPushButton(_("Tout selon Tesseract"))
        b.clicked.connect(lambda: self._tout(2))
        h.addWidget(b)
        h.addStretch(1)
        bb = QDialogButtonBox()
        bb.addButton(_("Valider et apprendre"), QDialogButtonBox.AcceptRole)
        bb.addButton(_("Annuler"), QDialogButtonBox.RejectRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        h.addWidget(bb)
        v.addLayout(h)

    def _clic(self, r, c):
        if c == 2:
            self.table.item(r, 4).setText(self.lignes[r]["tesseract"])
        elif c == 3:
            self.table.item(r, 4).setText(self.lignes[r]["ia"])

    def _tout(self, c):
        for r, ln in enumerate(self.lignes):
            self.table.item(r, 4).setText(ln["tesseract"] if c == 2 else ln["ia"])

    def valeurs(self):
        return [self.table.item(r, 4).text().strip() for r in range(self.table.rowCount())]


def _nom_ia(params):
    m = ia.moteurs(params)
    if not m:
        return "?"
    nom = {"claude": "Claude", "gemini": "Gemini"}[m[0][0]]
    modele = params.get("ia_modele_" + m[0][0]) or ia._modeles_trouves.get(m[0][0]) or \
        (ia.MODELE_CLAUDE if m[0][0] == "claude" else ia.MODELE_GEMINI)
    return f"{nom} ({modele})"


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
    appris = apprentissage.ocr_appris(params)

    def lecture_tesseract(t):
        def prog(i, n):
            t.avancer(_("Tesseract lit la page {i} sur {n}...", i=min(i + 1, n), n=n), i, n)
        an = scan.analyser(onglet.chemin, prog, appris)
        for pg in an["pages"]:
            if not pg["garder"]:
                t.noter(_("Page {p} : Tesseract, {m} mots, confiance {q} %", p=pg["num"] + 1, m=len(pg["mots"]),
                          q=round(pg["qualite"])))
        return an
    try:
        an = executer_suivi(fenetre, _("OCR IA comparé"), lecture_tesseract)
    except InterruptedError:
        return
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
    nom = _nom_ia(params)

    def lecture_ia(t):
        import time
        for k, pg in enumerate(a_lire):
            t.avancer(_("{ia} lit la page {i} sur {n}...", ia=nom, i=k + 1, n=len(a_lire)), k, len(a_lire))
            debut = time.time()
            pg["texte_ia"] = ia.demander(params, CONSIGNES_OCR, _("Page {n}", n=pg["num"] + 1),
                                         images=[_png_reduit(scan.image_de_tiff(pg["tif"]))], max_jetons=8000)
            pg["diffs"] = differences_utiles(pg["mots"], pg["texte_ia"])
            t.noter(_("Page {p} : {ia}, {m} mots en {s} s ; {d} différence(s) avec Tesseract", p=pg["num"] + 1,
                      ia=nom, m=len(pg["texte_ia"].split()), s=round(time.time() - debut), d=len(pg["diffs"])))
        t.avancer(_("Lecture terminée."), len(a_lire), len(a_lire))
    try:
        executer_suivi(fenetre, _("OCR IA comparé"), lecture_ia)
    except InterruptedError:
        return
    except Exception as e:
        montrer_erreur(fenetre, e)
        return
    lignes = []
    for pg in a_lire:
        image = None
        vus = set()
        for d in pg["diffs"]:
            image = image if image is not None else scan.image_de_tiff(pg["tif"])
            lignes.append(dict(d, page=pg, vignette=_vignette(image, scan.zone_mots(pg["mots"], d["i1"], d["i2"]))))
            vus.update(range(d["i1"], d["i2"]))
        for i, avant, apres in pg["auto"]:            # corrections appliquees seules : montrees pour controle
            if i not in vus:
                image = image if image is not None else scan.image_de_tiff(pg["tif"])
                lignes.append({"i1": i, "i2": i + 1, "tesseract": avant, "ia": apres, "auto": True, "page": pg,
                               "vignette": _vignette(image, scan.zone_mots(pg["mots"], i, i + 1))})
    corrige, appris_mots, appris_regles = 0, 0, 0
    if lignes:
        d = DialogueOCRIA(fenetre, lignes, nom)
        if d.exec() != QDialog.Accepted:
            return
        corrections = []
        echantillons = os.path.join(dossier_donnees(), "apprentissage_ocr")
        os.makedirs(echantillons, exist_ok=True)
        import difflib
        for ln, val in zip(lignes, d.valeurs()):
            pg = ln["page"]
            actuel = " ".join(m["texte"] for m in pg["mots"][ln["i1"]:ln["i2"]] if m["texte"])
            if val != actuel:
                scan.remplacer_mots(pg["mots"], ln["i1"], ln["i2"], val)
                corrige += 1
            avant = ln["tesseract"]
            # on n'apprend que des confusions plausibles de lettres (pas des passages entiers mal decoupes)
            if val and val != avant and len(avant.split()) <= 2 and \
                    (len(avant) <= 4 or difflib.SequenceMatcher(None, avant, val).ratio() >= 0.5):
                corrections.append((avant, val))
                try:
                    import cv2, hashlib
                    image = scan.image_de_tiff(pg["tif"])
                    x0, y0, x1, y1 = [int(v) for v in scan.zone_mots(pg["mots"], ln["i1"], ln["i2"], 2)]
                    morceau = image[max(0, y0):y1, max(0, x0):x1]
                    cle = hashlib.sha1(morceau.tobytes()).hexdigest()[:12]
                    cv2.imwrite(os.path.join(echantillons, cle + ".png"), morceau)
                    with open(os.path.join(echantillons, cle + ".gt.txt"), "w", encoding="utf-8") as f:
                        f.write(val)
                except Exception:
                    pass
            elif val == avant and ln.get("auto"):
                corrections.append((avant, avant))     # regle refusee : elle s'affaiblit
        appris_mots, appris_regles = apprentissage.retenir_ocr(params, corrections)
    sortie = _sans_doublon(os.path.splitext(onglet.chemin)[0] + "_OCR_IA.pdf")
    try:
        scan.assembler(an, sortie)
    except Exception as e:
        QMessageBox.warning(fenetre, _("OCR IA comparé"), _("Enregistrement impossible :\n{e}", e=e))
        return
    fenetre.ouvrir(sortie)
    QMessageBox.information(fenetre, _("OCR IA comparé"), _(
        "Terminé : {c} passage(s) corrigé(s) dans le texte du PDF, sur {n} différence(s).\n\n"
        "Appris : {m} mot(s) ajouté(s) à votre liste personnelle, {r} correction(s) retenue(s) (une correction "
        "s'applique seule dès qu'elle a été confirmée deux fois).\n\nFichier : {f}",
        c=corrige, n=len(lignes), m=appris_mots, r=appris_regles, f=os.path.basename(sortie)) if lignes else
        _("Tesseract et l'IA ont lu la même chose. Fichier : {f}", f=os.path.basename(sortie)))
    return sortie


# ------------------------------------------------------------------ nom propose apres une numerisation
CONSIGNES_NOMMER = """Tu aides à nommer un document qui vient d'être numérisé. Lis-le et réponds en JSON :
{"date": "AAAA-MM-JJ (date du document)", "expediteur": "<organisme ou personne qui l'envoie, nom court usuel,
ex. CPAM, URSSAF, DGFiP, EDF, Maître Dupont>", "objet": "<objet en 2 à 6 mots>",
"type": "<facture, courrier, contrat, relevé, avis, attestation, ordonnance...>"}"""


def proposer_nom_scan(fenetre, onglet):
    """L'IA lit le document numerise (son texte reconnu, sinon l'image de sa premiere page) et propose
    « Expediteur – objet – date » ; l'utilisateur corrige, puis enregistre sous ce nom ou le garde pour l'onglet.
    Renvoie le nom choisi, ou None."""
    params = fenetre.params
    if not verifier_cle(fenetre, params):
        return None
    texte = ia.texte_document(onglet.doc, max_car=20000)
    images = None
    if texte.strip():
        if not ia.confirmer_envoi(fenetre, texte, ia.nom_moteur(params)):
            return None
    else:
        if QMessageBox.question(fenetre, _("Proposer un nom"), _(
                "Le texte du document n'est pas encore reconnu : l'image de la première page va être envoyée à "
                "l'IA ({ia}) pour proposer un nom.\n\nEnvoyer ?", ia=ia.nom_moteur(params))) != QMessageBox.Yes:
            return None
        import pymupdf as fitz
        pm = onglet.doc[0].get_pixmap(dpi=110, colorspace=fitz.csGRAY)
        images = [pm.tobytes("png")]
        texte = _("Document numérisé : la première page est en image.")
    consignes = CONSIGNES_NOMMER + f"\nDate du jour : {datetime.date.today().isoformat()}."
    try:
        r = executer(fenetre, _("L'IA lit le document..."),
                     lambda: ia.demander(params, consignes, texte, images=images, json_attendu=True))
    except Exception as e:                              # noqa: BLE001
        montrer_erreur(fenetre, e)
        return None
    if not isinstance(r, dict):
        return None
    d = QDialog(fenetre)
    d.setWindowTitle(_("Proposer un nom"))
    d.setMinimumWidth(560)
    v = QVBoxLayout(d)
    info = QLabel(_("<b>{exp}</b> — {type} du {date}<br>{objet}", exp=r.get("expediteur") or "?",
                    type=r.get("type") or _("document"), date=_date_fr(r.get("date") or ""), objet=r.get("objet") or ""))
    info.setWordWrap(True)
    v.addWidget(info)
    nom = QLineEdit(nom_propose(r))
    v.addWidget(QLabel(_("Nom proposé (modifiable) :")))
    v.addWidget(nom)
    note = QLabel(_("Proposé par l'IA : vérifiez l'expéditeur et la date avant d'enregistrer."))
    note.setWordWrap(True)
    note.setStyleSheet("color:#666")
    v.addWidget(note)
    bb = QDialogButtonBox()
    b_enr = bb.addButton(_("Enregistrer sous ce nom..."), QDialogButtonBox.AcceptRole)
    b_garder = bb.addButton(_("Garder ce nom pour l'onglet"), QDialogButtonBox.ActionRole)
    bb.addButton(_("Annuler"), QDialogButtonBox.RejectRole)
    choix = {}
    b_enr.clicked.connect(lambda: (choix.update(k="enr"), d.accept()))
    b_garder.clicked.connect(lambda: (choix.update(k="garder"), d.accept()))
    bb.rejected.connect(d.reject)
    v.addWidget(bb)
    if d.exec() != QDialog.Accepted:
        return None
    n = nom.text().strip() or nom_propose(r)
    if not n.lower().endswith(".pdf"):
        n += ".pdf"
    onglet.nom = n
    try:
        fenetre._maj_titre(onglet)
    except Exception:                                   # noqa: BLE001
        pass
    from .journal import ecrire
    ecrire("IA", f"nom proposé après numérisation : {n}")
    if choix.get("k") == "enr":
        fenetre.enregistrer(onglet, sous=True, nom_propose=n)
    return n


# ------------------------------------------------------------------ expliquer simplement
CONSIGNES_EXPLIQUER = """Explique simplement ce document en {langue} à quelqu'un qui n'est pas spécialiste (courrier
administratif, contrat, avis d'imposition, ordonnance, facture...). Réponds en JSON :
{{"resume": "<texte en Markdown>", "echeances": [{{"date": "AAAA-MM-JJ", "heure": "HH:MM ou vide", "libelle": "<ce qu'il faut faire>"}}]}}
Le Markdown suit exactement ce plan, avec ces titres (traduits dans la langue demandée) :
### De quoi s'agit-il
2 ou 3 phrases : qui écrit, à qui, pourquoi.
### Ce qu'on vous demande
Les actions concrètes, en liste (payer, répondre, signer, envoyer une pièce, prendre rendez-vous...), ou « Rien à faire ».
### Avant quand
Les dates limites, ou « Pas de date limite indiquée ».
### Ce qu'il faut savoir
Montants, ce qui se passe si rien n'est fait, droits et recours mentionnés.
### Mots compliqués
Au plus 5 mots ou sigles du document, chacun expliqué en une phrase (rubrique absente s'il n'y en a pas).
Phrases courtes, vouvoiement, pas de jargon. N'invente rien : si une information manque, dis-le. Pour une ordonnance,
reprends les médicaments, doses et durées tels qu'écrits, sans conseil médical en plus. « echeances » : seulement les
dates où l'on doit faire quelque chose."""


def expliquer(fenetre, onglet):
    """Expliquer simplement : que me demande-t-on, avant quand. Meme fenetre que le resume (agenda, message, note)."""
    from .langue import LANGUE, NOMS
    params = fenetre.params
    texte = ia.texte_document(onglet.doc)
    if not texte.strip():
        QMessageBox.information(fenetre, _("Expliquer simplement"), _(
            "Ce document ne contient pas de texte (scan ?) : lancez d'abord « Reconnaître le texte »."))
        return
    if not preparer_envoi(fenetre, params, texte):
        return
    nom = {"fr": "français", "en": "anglais", "de": "allemand", "es": "espagnol", "it": "italien"}.get(LANGUE, NOMS.get(LANGUE, "français"))
    consignes = CONSIGNES_EXPLIQUER.format(langue=nom) + f"\nDate du jour : {datetime.date.today().isoformat()}."
    try:
        r = executer(fenetre, _("L'IA lit le document pour vous l'expliquer..."),
                     lambda: ia.demander(params, consignes, texte, json_attendu=True))
    except Exception as e:
        montrer_erreur(fenetre, e)
        return
    if isinstance(r, dict):
        d = DialogueResume(fenetre, params, onglet, r)
        d.setWindowTitle(_("Expliqué simplement — {nom}", nom=onglet.nom))
        d.exec()


# ------------------------------------------------------------------ remplir un formulaire avec l'IA
CONSIGNES_REMPLIR = """Tu aides à remplir un formulaire PDF. On te donne le texte du document, la liste de ses champs
(nom technique, libellé visible, type, choix possibles, valeur actuelle) et ce que la personne t'indique sur elle ou sur
la démarche. Réponds en JSON : {"valeurs": {"<nom technique du champ>": "<valeur>"}, "manque": ["<information
qu'il faudrait pour remplir un champ resté vide>"]}.
Règles : ne remplis un champ que si l'information est donnée par la personne ou évidente d'après le document ; n'invente
rien (ni numéro, ni date, ni adresse). Case à cocher : "oui" ou "non". Liste ou bouton radio : une des valeurs
possibles, recopiée exactement. Dates au format du document (sinon JJ/MM/AAAA). Champ de signature : jamais."""


def _champs_formulaire(doc):
    out = []
    for n, p in enumerate(doc):
        for w in p.widgets() or []:
            if w.field_type == fitz.PDF_WIDGET_TYPE_SIGNATURE or w.field_type == fitz.PDF_WIDGET_TYPE_BUTTON:
                continue
            if w.field_flags & 1:                         # lecture seule
                continue
            out.append({"page": n, "nom": w.field_name, "libelle": (w.field_label or "").strip(),
                        "type": w.field_type_string, "choix": list(w.choice_values or []) if w.field_type in (
                            fitz.PDF_WIDGET_TYPE_COMBOBOX, fitz.PDF_WIDGET_TYPE_LISTBOX) else
                        ([w.on_state()] if w.field_type in (fitz.PDF_WIDGET_TYPE_RADIOBUTTON,) and w.on_state() else []),
                        "valeur": w.field_value if not isinstance(w.field_value, bool) else ("oui" if w.field_value else "non"),
                        "case": w.field_type == fitz.PDF_WIDGET_TYPE_CHECKBOX, "radio": w.field_type == fitz.PDF_WIDGET_TYPE_RADIOBUTTON})
    return out


class DialogueRemplirIA(QDialog):
    """Valeurs proposees par l'IA, champ par champ : on coche ce qu'on garde, on corrige, puis « Remplir »."""

    def __init__(self, parent, champs, valeurs, manque):
        from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
        super().__init__(parent)
        self.setWindowTitle(_("Remplir avec l'IA"))
        self.resize(820, 560)
        v = QVBoxLayout(self)
        lb = QLabel(_("Vérifiez chaque valeur proposée : rien n'est écrit dans le formulaire avant « Remplir ». Décochez ce "
                      "que vous ne voulez pas, corrigez dans la colonne « Valeur ». Ctrl+Z annule ensuite."))
        lb.setWordWrap(True)
        v.addWidget(lb)
        self.lignes = [(c, str(valeurs[c["nom"]])) for c in champs if c["nom"] in valeurs and str(valeurs[c["nom"]]).strip()]
        t = self.table = QTableWidget(len(self.lignes), 4)
        t.setHorizontalHeaderLabels([_("Remplir"), _("Champ"), _("Valeur actuelle"), _("Valeur")])
        t.verticalHeader().hide()
        for r, (c, val) in enumerate(self.lignes):
            k = QTableWidgetItem()
            k.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            k.setCheckState(Qt.Checked if not str(c["valeur"] or "").strip() or str(c["valeur"]) in ("non", "Off") else Qt.Unchecked)
            t.setItem(r, 0, k)
            for col, x in ((1, (c["libelle"] or c["nom"]) + _(" (page {n})", n=c["page"] + 1)), (2, str(c["valeur"] or ""))):
                it = QTableWidgetItem(x)
                it.setFlags(Qt.ItemIsEnabled)
                t.setItem(r, col, it)
            t.setItem(r, 3, QTableWidgetItem(val))
        hh = t.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        for col in (1, 2, 3):
            hh.setSectionResizeMode(col, QHeaderView.Stretch)
        v.addWidget(t, 1)
        if not self.lignes:
            v.addWidget(QLabel(_("L'IA n'a proposé aucune valeur.")))
        if manque:
            m = QLabel(_("Il manque, pour aller plus loin :") + "\n• " + "\n• ".join(str(x) for x in manque[:8]))
            m.setWordWrap(True)
            m.setStyleSheet("color:#8a5a00")
            v.addWidget(m)
        from . import signaler_ia
        v.addWidget(signaler_ia.bouton(self, _("Remplir avec l'IA"), lambda: "\n".join(
            f"{c['libelle'] or c['nom']} : {self.table.item(r, 3).text()}" for r, (c, _v) in enumerate(self.lignes))))
        bb = boutons_fr(QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel))
        bb.button(QDialogButtonBox.Ok).setText(_("Remplir"))
        bb.button(QDialogButtonBox.Ok).setEnabled(bool(self.lignes))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def choisis(self):
        return [(c, self.table.item(r, 3).text()) for r, (c, _v) in enumerate(self.lignes)
                if self.table.item(r, 0).checkState() == Qt.Checked]


def remplir_formulaire(fenetre, onglet):
    """Remplir un formulaire avec l'IA : vous dites ce qu'il faut savoir, l'IA propose, vous verifiez, puis c'est ecrit."""
    import json as _json
    params = fenetre.params
    champs = _champs_formulaire(onglet.doc)
    if not champs:
        QMessageBox.information(fenetre, _("Remplir avec l'IA"), _(
            "Ce document n'a pas de champs à remplir. « Créer un formulaire » (Outils) peut d'abord les ajouter."))
        return
    d = QDialog(fenetre)
    d.setWindowTitle(_("Remplir avec l'IA"))
    d.resize(640, 420)
    v = QVBoxLayout(d)
    lb = QLabel(_("{n} champ(s) à remplir. Dites à l'IA ce qu'elle doit savoir (nom, adresse, dates, numéros, choix...) : "
                  "elle ne remplit que ce que vous lui donnez ou ce que le document dit clairement, et vous vérifiez "
                  "tout avant que ce soit écrit.", n=len(champs)))
    lb.setWordWrap(True)
    v.addWidget(lb)
    zone = QPlainTextEdit(params.get("ia_infos_formulaire", ""))
    zone.setPlaceholderText(_("Ex. : Jean Martin, né le 12/03/1970 à Lyon, 3 rue des Lilas 06000 Nice, "
                              "demande de renouvellement..."))
    v.addWidget(zone, 1)
    garder = QCheckBox(_("Garder ces informations sur ce poste pour la prochaine fois (jamais envoyées ailleurs qu'à l'IA)"))
    garder.setChecked(bool(params.get("ia_infos_formulaire")))
    v.addWidget(garder)
    bb = boutons_fr(QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel))
    bb.button(QDialogButtonBox.Ok).setText(_("Proposer les valeurs"))
    bb.accepted.connect(d.accept)
    bb.rejected.connect(d.reject)
    v.addWidget(bb)
    if not d.exec():
        return
    infos = zone.toPlainText().strip()
    params["ia_infos_formulaire"] = infos if garder.isChecked() else ""
    params.enregistrer()
    texte = ia.texte_document(onglet.doc, max_car=40000)
    description = [{k: c[k] for k in ("nom", "libelle", "type", "choix", "valeur")} for c in champs]
    envoi = (_json.dumps({"champs": description}, ensure_ascii=False) + "\n\nCe que la personne indique :\n" + (infos or "(rien)") +
             "\n\nTexte du document :\n" + texte)
    if not preparer_envoi(fenetre, params, infos + "\n" + texte):
        return
    try:
        r = executer(fenetre, _("L'IA lit le formulaire..."),
                     lambda: ia.demander(params, CONSIGNES_REMPLIR, envoi, json_attendu=True, max_jetons=6000))
    except Exception as e:
        montrer_erreur(fenetre, e)
        return
    valeurs = (r or {}).get("valeurs") if isinstance(r, dict) else None
    if not isinstance(valeurs, dict):
        montrer_erreur(fenetre, _("Réponse de l'IA illisible."))
        return
    dr = DialogueRemplirIA(fenetre, champs, valeurs, (r or {}).get("manque") or [])
    if not dr.exec():
        return
    choisis = dr.choisis()
    if not choisis:
        return
    onglet.memoriser(_("Remplir avec l'IA"))
    n = remplir_valeurs(onglet.doc, choisis)
    onglet.apres_modif([_("{n} champ(s) rempli(s) avec l'IA : relisez avant d'enregistrer.", n=n)])


def remplir_valeurs(doc, choisis):
    """Ecrit les valeurs [(champ, valeur)] dans les champs du document ; renvoie le nombre de champs remplis."""
    n = 0
    for c, val in choisis:
        for w in doc[c["page"]].widgets() or []:
            if w.field_name != c["nom"]:
                continue
            if c["case"]:
                w.field_value = w.on_state() if val.strip().lower() in ("oui", "yes", "true", "1", "x", "ja", "sí", "si", "sì") else "Off"
            elif c["radio"]:
                if val.strip() != str(w.on_state()):
                    continue
                w.field_value = w.on_state()
            else:
                w.field_value = val
            w.update()
            n += 1
            if not c["radio"]:
                break
    return n
