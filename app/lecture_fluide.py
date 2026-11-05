"""Fenetre de lecture fluide (Affichage > Lecture fluide), comme sur PhilPDF Android : le texte du document remis en
colonne, taille du texte, fond clair / sepia / sombre, texte justifie ou non, police avec ou sans empattements.
Cliquer « Page n » ramene a cette page dans le document. Le PDF n'est pas modifie."""
import time

from PySide6.QtCore import Qt, QTimer, QUrl, QThread, Signal
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QComboBox, QCheckBox,
                               QTextBrowser, QApplication)

from .langue import _
from moteur import fluide

class _Traduction(QThread):
    """Traduit les pages une a une (a mesure qu'elles sont lues), sans bloquer la fenetre."""
    page = Signal(int, object)                      # numero, liste de textes traduits ou erreur

    def __init__(self, fenetre, langue):
        super().__init__(fenetre)
        self.f, self.langue, self.stop = fenetre, langue, False

    def run(self):
        import json
        from . import ia
        from .dialogues_ia import CONSIGNES_TRADUIRE
        n = 0
        while not self.stop:
            if n >= len(self.f.donnees):
                if self.f.lu:
                    return
                time.sleep(0.2)
                continue
            d = self.f.donnees[n]
            tx = fluide.textes(d[0]) if d and not d[1] else []
            try:
                out = []
                for i in range(0, len(tx), 40):
                    lot = tx[i:i + 40]
                    r = ia.demander(self.f.params, CONSIGNES_TRADUIRE.format(langue=self.langue),
                                    json.dumps({"textes": lot}, ensure_ascii=False), json_attendu=True, max_jetons=8000)
                    res = r.get("textes") if isinstance(r, dict) else r
                    if not isinstance(res, list) or len(res) != len(lot):
                        raise ia.ErreurIA(_("Réponse de l'IA incomplète (lot de {n} textes).", n=len(lot)))
                    out += [str(x) for x in res]
                self.page.emit(n, out)
            except Exception as e:                  # noqa: BLE001
                self.page.emit(n, e)
            n += 1


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
        from .dialogues_ia import LANGUES_CIBLES
        self.langue = QComboBox()
        self.langue.addItem(_("Texte d'origine"), "")
        for n, natif, _c in LANGUES_CIBLES:
            self.langue.addItem(_(n) + (f" ({natif})" if _(n) != natif else ""), n)
        self.langue.setToolTip(_("Traduire avec l'IA (votre clef Claude ou Gemini), page par page : le PDF n'est pas modifié."))
        self.langue.activated.connect(self._traduire)
        h.addWidget(QLabel(_("Traduire :")))
        h.addWidget(self.langue)
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
        self.donnees = []                           # par page : (blocs, scannee, image) ou None (illisible)
        self.erreurs = {}
        self.trad, self.trad_err, self.tache = {}, {}, None
        self.morceaux = []
        self.lu = False
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
            self.lu = True
            self.etat.setText(_("{n} page(s). Cliquez « Page n » pour revenir à cette page dans le document.", n=len(doc)))
            return
        p = doc[self.n]
        try:
            blocs, scannee = fluide.page(p)
            img = p.get_pixmap(dpi=90).tobytes("png") if scannee else None
            self.donnees.append((blocs, scannee, img))
        except Exception as e:                      # noqa: BLE001
            self.donnees.append(None)
            self.erreurs[self.n] = str(e)
        self.morceaux.append(self._html(self.n))
        self.n += 1
        self.etat.setText(_("Lecture de la page {i} sur {n}...", i=self.n, n=len(doc)))
        self._afficher()

    def _html(self, n):
        d = self.donnees[n]
        if d is None:
            corps = "<p style='color:#c62828'>" + _("Page illisible : {e}", e=self.erreurs.get(n, "?")) + "</p>"
        else:
            blocs, scannee, img = d
            if self.tache is not None and not scannee:
                if n in self.trad:
                    blocs = fluide.remplacer(blocs, self.trad[n])
                elif n in self.trad_err:
                    blocs = [("para", False, [(_("Traduction impossible : {e}", e=self.trad_err[n]), True, False)])] + blocs
                elif fluide.textes(blocs):
                    blocs = [("para", False, [(_("Traduction en cours..."), False, True)])] + blocs
            corps = fluide.html_page(blocs, scannee, img, _("Page scannée : son texte n'est pas encore reconnu (Outils > Reconnaître le texte)."))
        return f"<p align='center'><a class='page' href='page:{n}'>— {_('Page {n}', n=n + 1)} —</a></p>" + corps

    def _afficher(self):
        barre = self.vue.verticalScrollBar().value()
        self.vue.setHtml("\n".join(self.morceaux))
        self.vue.verticalScrollBar().setValue(barre)

    def _traduire(self, _i=0):
        """Langue choisie : accord (clef, donnees sensibles) une fois pour le document, puis page par page."""
        from . import ia
        from .dialogues_ia import preparer_envoi
        if self.tache is not None:
            self.tache.stop = True
            self.tache.wait(200)
            self.tache = None
        self.trad, self.trad_err = {}, {}
        langue = self.langue.currentData()
        if langue and not preparer_envoi(self, self.params, ia.texte_document(self.o.doc)):
            self.langue.setCurrentIndex(0)
            langue = ""
        if langue:
            self.tache = _Traduction(self, langue)
            self.tache.page.connect(self._traduite)
            self.tache.start()
        self.morceaux = [self._html(n) for n in range(len(self.donnees))]
        self._afficher()

    def _traduite(self, n, r):
        if self.tache is None or self.sender() is not self.tache:
            return
        if isinstance(r, Exception):
            self.trad_err[n] = str(r)
        else:
            self.trad[n] = r
        if n < len(self.morceaux):
            self.morceaux[n] = self._html(n)
            self._afficher()

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
        if self.tache is not None:
            self.tache.stop = True
            self.tache.wait(3000)
        try:
            self.params.enregistrer()
        except Exception:                           # noqa: BLE001
            pass
        super().closeEvent(e)
