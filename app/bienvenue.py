"""Assistant de premiere installation : les reglages indispensables, une seule fois.

Langue, votre nom (tampons, commentaires), le nom de ce poste et l'emplacement de synchronisation entre vos
postes (Drive, NAS, FTP, dossier partage). Les postes deja installes sans emplacement le voient aussi une fois.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QLabel, QLineEdit, QComboBox, QDialogButtonBox

from .langue import _, disponibles
from .synchro_choix import combo_emplacements, valeurs


class DialogueBienvenue(QDialog):
    def __init__(self, parent, params, seulement_synchro=False):
        super().__init__(parent)
        self.params = params
        self.setWindowTitle(_("Bienvenue dans PhilPDF") if not seulement_synchro else _("Synchronisation entre vos postes"))
        self.setMinimumWidth(620)
        v = QVBoxLayout(self)
        t = QLabel(_("<h3>Bienvenue dans PhilPDF</h3>Quelques réglages, une seule fois. Tout reste modifiable ensuite "
                     "dans Edition › Préférences.") if not seulement_synchro else
                   _("<h3>Synchronisation entre vos postes</h3>"))
        t.setWordWrap(True)
        v.addWidget(t)
        f = QFormLayout()
        self.langue = QComboBox()
        self.langue.addItem(_("Automatique (langue du système)"), "auto")
        for code, nom in disponibles():
            self.langue.addItem(nom, code)
        self.langue.setCurrentIndex(max(0, self.langue.findData(params.get("langue", "auto"))))
        self.auteur = QLineEdit(params.get("auteur", ""))
        self.auteur.setPlaceholderText(_("Nom inscrit sur les tampons et commentaires"))
        self.machine = QLineEdit(params.get("machine", ""))
        self.machine.setPlaceholderText(_("ex. Pharmacie, Maison, Portable Linux"))
        if not seulement_synchro:
            f.addRow(_("Langue"), self.langue)
            f.addRow(_("Votre nom"), self.auteur)
            f.addRow(_("Nom de ce poste"), self.machine)
        self.emplacement = combo_emplacements(self, params)
        f.addRow(_("Synchronisation"), self.emplacement)
        v.addLayout(f)
        n = QLabel(_("Pour retrouver sur chaque poste vos préférences, tampons, signatures, apprentissages et les fichiers "
                     "ouverts ailleurs, choisissez un emplacement commun : un Drive (Google Drive, OneDrive, Dropbox, Box), "
                     "votre NAS, un serveur FTP ou un dossier partagé. Choisissez le même sur tous vos postes. "
                     "PhilPDF n'y met que son dossier « PhilPDF », jamais vos PDF."))
        n.setWordWrap(True)
        n.setStyleSheet("color:#555")
        v.addWidget(n)
        bb = QDialogButtonBox()
        self.b_ok = bb.addButton(_("Commencer") if not seulement_synchro else _("Valider"), QDialogButtonBox.AcceptRole)
        bb.addButton(_("Plus tard"), QDialogButtonBox.RejectRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def appliquer(self):
        """Enregistre les choix ; renvoie True si la langue a change (redemarrage necessaire)."""
        p = self.params
        ancienne = p.get("langue", "auto")
        drive, compte = valeurs(self.emplacement, p)
        p.update(langue=self.langue.currentData(), auteur=self.auteur.text().strip() or p.get("auteur", ""),
                 machine=self.machine.text().strip() or p.get("machine", ""), drive=drive, drive_compte=compte,
                 bienvenue_vue=True)
        p.enregistrer()
        return self.langue.currentData() != ancienne
