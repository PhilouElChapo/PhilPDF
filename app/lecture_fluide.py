"""Fenetre de lecture fluide (Affichage > Lecture fluide), comme sur PhilPDF Android : le texte du document remis en
colonne, taille du texte, fond clair / sepia / sombre, texte justifie ou non, police avec ou sans empattements.
Cliquer « Page n » ramene a cette page dans le document. Le PDF n'est pas modifie."""
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QComboBox, QCheckBox,
                               QTextBrowser, QApplication)

from .langue import _
from moteur import fluide

THEMES = [("clair", "#ffffff", "#222222"), ("sepia", "#f6eedc", "#433422"), ("sombre", "#1e1e1e", "#dddddd")]


class FenetreLectureFluide(QDialog):
    def __init__(self, onglet, params):
        super().__init__(onglet.window())
        self.o, self.params = onglet, params
        import os
        nom = os.path.basename(getattr(onglet, "chemin", "") or "") or getattr(onglet, "nom", "")
        self.setWindowTitle(_("Lecture fluide") + (" — " + nom if nom else ""))
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        ecran = self.screen().availableGeometry()
        self.resize(min(900, ecran.width() - 40), min(900, ecran.height() - 60))
        v = QVBoxLayout(self)
        h = QHBoxLayout()
        for texte, d in (("A−", -2), ("A+", 2)):
            b = QPushButton(texte)
            b.setToolTip(_("Taille du texte"))
            b.clicked.connect(lambda _c=False, d=d: self._taille(d))
            h.addWidget(b)
        self.theme = QComboBox()
        for cle, lib in (("clair", _("Clair")), ("sepia", _("Sépia")), ("sombre", _("Sombre"))):
            self.theme.addItem(lib, cle)
        self.theme.setCurrentIndex(max(0, self.theme.findData(params.get("fluide_theme", "clair"))))
        self.theme.currentIndexChanged.connect(lambda _i: self._style(True))
        h.addWidget(QLabel(_("Fond :")))
        h.addWidget(self.theme)
        self.justifier = QCheckBox(_("Justifier"))
        self.justifier.setChecked(params.get("fluide_justifier", True))
        self.justifier.toggled.connect(lambda _b: self._style(True))
        h.addWidget(self.justifier)
        self.serif = QCheckBox(_("Police avec empattements"))
        self.serif.setChecked(params.get("fluide_serif", False))
        self.serif.toggled.connect(lambda _b: self._style(True))
        h.addWidget(self.serif)
        h.addStretch()
        v.addLayout(h)
        self.etat = QLabel()
        self.etat.setStyleSheet("color:#666")
        v.addWidget(self.etat)
        self.vue = QTextBrowser()
        self.vue.setOpenLinks(False)
        self.vue.anchorClicked.connect(self._lien)
        v.addWidget(self.vue, 1)
        self.taille = params.get("fluide_taille", 15)
        self.morceaux = []
        self.n = 0
        self._style(False)
        self._t = QTimer(self, interval=0, timeout=self._suivante)
        self._t.start()

    def _taille(self, d):
        self.taille = min(34, max(10, self.taille + d))
        self._style(True)

    def _style(self, garder):
        cle = self.theme.currentData()
        fond, encre = next((f, e) for c, f, e in THEMES if c == cle)
        police = "Georgia, 'Times New Roman', serif" if self.serif.isChecked() else "'Segoe UI', Arial, sans-serif"
        align = "justify" if self.justifier.isChecked() else "left"
        t = self.taille
        self.vue.setStyleSheet(f"QTextBrowser{{background:{fond};color:{encre};padding:18px 28px}}")
        self.vue.document().setDefaultStyleSheet(
            f"body{{font-family:{police};font-size:{t}pt;color:{encre}}}"
            f"p.para{{text-align:{align};margin-bottom:{t * 0.6:.0f}pt;line-height:150%}}"
            f"p.puce{{margin-left:12pt;margin-bottom:{t * 0.4:.0f}pt}}"
            f"h1{{font-size:{t * 1.45:.0f}pt}} h2{{font-size:{t * 1.2:.0f}pt}} h3{{font-size:{t * 1.05:.0f}pt}}"
            f"a.page{{color:#888888;font-size:{max(8, t - 5)}pt;text-decoration:none}}")
        if garder:
            for c, v in (("fluide_theme", cle), ("fluide_justifier", self.justifier.isChecked()),
                         ("fluide_serif", self.serif.isChecked()), ("fluide_taille", self.taille)):
                self.params[c] = v
            barre = self.vue.verticalScrollBar().value()
            self.vue.setHtml("\n".join(self.morceaux))
            self.vue.verticalScrollBar().setValue(barre)

    def _suivante(self):
        """Une page a la fois, pour que la fenetre reste vivante sur un gros document."""
        doc = self.o.doc
        if self.n >= len(doc):
            self._t.stop()
            self.etat.setText(_("{n} page(s). Cliquez « Page n » pour revenir à cette page dans le document.", n=len(doc)))
            return
        p = doc[self.n]
        try:
            blocs, scannee = fluide.page(p)
            img = p.get_pixmap(dpi=90).tobytes("png") if scannee else None
            corps = fluide.html_page(blocs, scannee, img, _("Page scannée : son texte n'est pas encore reconnu (Outils > Reconnaître le texte)."))
        except Exception as e:                      # noqa: BLE001
            corps = "<p style='color:#c62828'>" + _("Page illisible : {e}", e=e) + "</p>"
        self.morceaux.append(f"<p align='center'><a class='page' href='page:{self.n}'>— {_('Page {n}', n=self.n + 1)} —</a></p>"
                             + corps)
        self.n += 1
        self.etat.setText(_("Lecture de la page {i} sur {n}...", i=self.n, n=len(doc)))
        barre = self.vue.verticalScrollBar().value()
        self.vue.setHtml("\n".join(self.morceaux))
        self.vue.verticalScrollBar().setValue(barre)

    def _lien(self, url: QUrl):
        s = url.toString()
        if s.startswith("page:"):
            try:
                self.o.aller_a(int(s[5:]))
                self.o.window().activateWindow()
            except Exception:                       # noqa: BLE001
                pass

    def closeEvent(self, e):
        self._t.stop()
        try:
            self.params.enregistrer()
        except Exception:                           # noqa: BLE001
            pass
        super().closeEvent(e)
