"""Signaler un resultat de l'IA (regle Google Play sur le contenu genere par l'IA, meme bouton que sur Android).

Le signalement part vers le developpeur, sans quitter PhilPDF, par un formulaire Google (memes champs que sur
Android). Part : la fonction, le service (Claude / Gemini et modele), le motif, le commentaire et le texte de la
reponse de l'IA (montre et modifiable avant l'envoi) ; jamais le document."""
import urllib.parse
import urllib.request

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QRadioButton,
                               QButtonGroup, QMessageBox)

from .langue import _

FORMULAIRE = ("https://docs.google.com/forms/d/e/1FAIpQLSfNWw9iPeSQqrQkJOjrQd6BacqPP63cTXqero6QcU7biwfVJA/"
              "formResponse")
CHAMPS = {"fonction": "entry.1590891463", "service": "entry.2084492064", "motif": "entry.1760884179",
          "commentaire": "entry.723269897", "texte": "entry.1436294086", "version": "entry.1122929308"}
MAX_TEXTE = 8000


def corps(fonction, service, motif, commentaire, texte, version):
    valeurs = {"fonction": fonction, "service": service, "motif": motif, "commentaire": commentaire,
               "texte": (texte or "")[:MAX_TEXTE], "version": version}
    return urllib.parse.urlencode({CHAMPS[k]: v for k, v in valeurs.items()}).encode("utf-8")


def envoyer(fonction, motif, commentaire, texte):
    """Envoie le signalement ; leve une exception si le formulaire ne repond pas."""
    from .config import VERSION
    from . import ia
    from .journal import ecrire
    import sys
    d = getattr(ia, "dernier", {}) or {}
    service = (f"{ {'claude': 'Claude', 'gemini': 'Gemini'}.get(d['moteur'], d['moteur'])} {d.get('modele', '')}".strip()
               if d.get("moteur") else "?")
    plateforme = "Windows" if sys.platform == "win32" else "Linux"
    req = urllib.request.Request(FORMULAIRE, data=corps(fonction, service, motif, commentaire, texte,
                                                       f"{plateforme} {VERSION}"),
                                 headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            code = r.status
    except Exception as e:
        ecrire("signalement IA", f"{fonction} / {motif} : échec {e}")
        raise
    ecrire("signalement IA", f"{fonction} / {motif} : réponse {code}")
    return code


class DialogueSignaler(QDialog):
    def __init__(self, parent, fonction, texte):
        super().__init__(parent)
        self.fonction = fonction
        self.setWindowTitle(_("Signaler un résultat de l'IA"))
        self.resize(560, 480)
        v = QVBoxLayout(self)
        aide = QLabel(_("Envoyé au développeur de PhilPDF, pour améliorer les fonctions d'IA : la fonction, le service, "
                        "le motif, votre commentaire et le texte ci-dessous (vous pouvez le raccourcir). Votre document "
                        "n'est pas envoyé."))
        aide.setWordWrap(True)
        aide.setStyleSheet("color:#555")
        v.addWidget(aide)
        v.addWidget(QLabel(_("Motif")))
        h = QHBoxLayout()
        self.groupe = QButtonGroup(self)
        self.motifs = [_("Choquant"), _("Dangereux"), _("Faux"), _("Autre")]
        for i, m in enumerate(self.motifs):
            b = QRadioButton(m)
            self.groupe.addButton(b, i)
            h.addWidget(b)
        h.addStretch(1)
        v.addLayout(h)
        v.addWidget(QLabel(_("Commentaire (facultatif)")))
        self.commentaire = QPlainTextEdit()
        self.commentaire.setMaximumHeight(80)
        v.addWidget(self.commentaire)
        v.addWidget(QLabel(_("Réponse de l'IA envoyée")))
        self.texte = QPlainTextEdit((texte or "")[:MAX_TEXTE])
        v.addWidget(self.texte, 1)
        hb = QHBoxLayout()
        hb.addStretch(1)
        ba = QPushButton(_("Annuler"))
        ba.clicked.connect(self.reject)
        hb.addWidget(ba)
        self.b_envoyer = QPushButton(_("Envoyer"))
        self.b_envoyer.setEnabled(False)
        self.b_envoyer.clicked.connect(self._envoyer)
        hb.addWidget(self.b_envoyer)
        v.addLayout(hb)
        self.groupe.idClicked.connect(lambda _i: self.b_envoyer.setEnabled(True))

    def _envoyer(self):
        from .dialogues_ia import en_tache
        motif = self.motifs[self.groupe.checkedId()]
        try:
            en_tache(self, _("Signaler un résultat de l'IA"), _("Envoi du signalement..."), envoyer, self.fonction, motif,
                     self.commentaire.toPlainText().strip(), self.texte.toPlainText()[:MAX_TEXTE], lecture=True,
                     bloquante=False)
        except InterruptedError:
            return
        except Exception:
            QMessageBox.warning(self, _("Signaler un résultat de l'IA"),
                                _("Le signalement n'a pas pu partir (pas de connexion ?). Réessayez plus tard."))
            return
        QMessageBox.information(self, _("Signaler un résultat de l'IA"), _("Merci, votre signalement est envoyé."))
        self.accept()


def signaler(parent, fonction, texte):
    DialogueSignaler(parent, fonction, texte).exec()


def bouton(parent, fonction, texte_fn):
    """Bouton discret « Signaler ce résultat » a mettre sous une reponse de l'IA."""
    b = QPushButton(_("Signaler ce résultat"))
    b.setFlat(True)
    b.setStyleSheet("color:#666")
    b.setToolTip(_("Signaler au développeur une réponse de l'IA choquante, dangereuse ou fausse."))
    b.clicked.connect(lambda: signaler(parent, fonction, texte_fn()))
    return b
