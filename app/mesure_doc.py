"""Outil Mesure dans un document (mixin de OngletDocument) : bandeau, trace a la souris, echelle par page."""
import math

import pymupdf as fitz
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor, QPen, QPolygonF, QFont
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton, QCheckBox, QButtonGroup, QDialog, QMenu,
                               QInputDialog)

from moteur import mesure as M
from .langue import _

GENRES = [("distance", _("Distance")), ("perimetre", _("Périmètre")), ("surface", _("Surface"))]
AIDES = {"distance": _("Cliquez le point de départ puis le point d'arrivée."),
         "perimetre": _("Cliquez chaque point ; double-clic, Entrée ou clic droit pour finir."),
         "surface": _("Cliquez chaque coin de la surface ; double-clic, Entrée ou clic droit pour la fermer.")}


class MixinMesure:
    def _construire_bandeau_mesure(self, v):
        b = self.bandeau_mesure = QFrame()
        b.setObjectName("bandeaumesure")
        b.setStyleSheet("QFrame#bandeaumesure{background:#e8f1fb;border-bottom:1px solid #c5d9f1}"
                        "QLabel{color:#123a66} QPushButton{padding:4px 12px}"
                        "QPushButton:checked{background:#1462c2;color:#fff;border-color:#1462c2}")
        h = QHBoxLayout(b)
        h.setContentsMargins(16, 6, 16, 6)
        t = QLabel("<b>" + _("Mesure") + "</b>")
        h.addWidget(t)
        self.groupe_mesure = QButtonGroup(b)
        self.boutons_mesure = {}
        for k, lib in GENRES:
            bt = QPushButton(lib)
            bt.setCheckable(True)
            bt.setObjectName("mesure_" + k)
            bt.setToolTip(AIDES[k])
            bt.clicked.connect(lambda _c=False, k=k: self.choisir_genre_mesure(k))
            self.groupe_mesure.addButton(bt)
            self.boutons_mesure[k] = bt
            h.addWidget(bt)
        self.boutons_mesure["distance"].setChecked(True)
        h.addSpacing(10)
        self.lbl_echelle = QLabel()
        self.lbl_echelle.setObjectName("lbl_echelle")
        h.addWidget(self.lbl_echelle)
        bt = QPushButton(_("Echelle..."))
        bt.setToolTip(_("Régler l'échelle de cette page (rapport, équivalence ou longueur connue)"))
        bt.clicked.connect(lambda: self.regler_echelle(self.page_courante()))
        h.addWidget(bt)
        self.cb_aimant = QCheckBox(_("Aimanter"))
        self.cb_aimant.setChecked(self.params.get("mesure_aimant", True))
        self.cb_aimant.setToolTip(_("S'accrocher aux extrémités et coins des traits du plan (Maj : horizontal, "
                                    "vertical ou 45°)"))
        self.cb_aimant.toggled.connect(lambda x: (self.params.__setitem__("mesure_aimant", x), self.params.enregistrer()))
        h.addWidget(self.cb_aimant)
        self.cb_nommer = QCheckBox(_("Nommer"))
        self.cb_nommer.setChecked(self.params.get("mesure_nommer", False))
        self.cb_nommer.setToolTip(_("Demander un nom à chaque mesure (Salon, Parcelle 12...)"))
        self.cb_nommer.toggled.connect(lambda x: (self.params.__setitem__("mesure_nommer", x), self.params.enregistrer()))
        h.addWidget(self.cb_nommer)
        self.lbl_mesure = QLabel()
        self.lbl_mesure.setObjectName("lbl_mesure")
        self.lbl_mesure.setWordWrap(True)
        h.addWidget(self.lbl_mesure, 1)
        bt = QPushButton(_("Liste des mesures..."))
        bt.clicked.connect(self.liste_mesures)
        h.addWidget(bt)
        bt = QPushButton(_("Terminer"))
        bt.setProperty("primaire", True)
        bt.clicked.connect(lambda: self.changer_mode(None))
        h.addWidget(bt)
        b.hide()
        v.addWidget(b)
        self.mesure = {"genre": "distance", "page": None, "points": [], "survol": None, "accroche": False,
                       "etalon": None}
        self.echelles = {}                 # page (ou "*") -> echelle choisie pendant cette session
        self._aimants = {}

    # ------------------------------------------------------------ etat
    def entrer_mesure(self):
        self.bandeau_mesure.show()
        self.mesure.update(page=None, points=[], survol=None, etalon=None)
        self._maj_bandeau_mesure()
        n = self.page_courante()
        if self.echelle_page(n) is None:
            self.regler_echelle(n)

    def sortir_mesure(self):
        self.bandeau_mesure.hide()
        self.mesure.update(page=None, points=[], survol=None, etalon=None)

    def choisir_genre_mesure(self, k):
        self.mesure.update(genre=k, page=None, points=[], etalon=None)
        self.boutons_mesure[k].setChecked(True)
        self._maj_bandeau_mesure()
        self.rafraichir_pages()

    def echelle_page(self, n):
        """Echelle de la page : celle choisie ici, sinon celle gardee par PhilPDF dans le PDF. None : a demander."""
        if n in self.echelles:
            return self.echelles[n]
        if "*" in self.echelles:
            return self.echelles["*"]
        e = M.lire_vp(self.doc, n)
        if e and e.get("philpdf") and e["u"] in M.UNITES:
            self.echelles[n] = e
            return e
        return None

    def _maj_bandeau_mesure(self):
        from .dialogues_mesure import libelle_echelle
        n = self.mesure.get("page")
        n = self.mesure.get("page_vue", self.page_courante()) if n is None else n
        e = self.echelle_page(n)
        self.lbl_echelle.setText(_("Echelle p. {n} : {e}", n=n + 1, e=libelle_echelle(e) if e else _("à régler")))
        if self.mesure.get("etalon") is not None:
            txt = _("Etalonnage : cliquez les deux bouts de la longueur connue.")
        elif self.mesure["points"]:
            txt = self._texte_en_cours() or AIDES[self.mesure["genre"]]
        else:
            txt = getattr(self, "_derniere_mesure", "") or AIDES[self.mesure["genre"]]
        self.lbl_mesure.setText(txt)

    def regler_echelle(self, n, apres=None):
        from .dialogues_mesure import DialogueEchelle
        d = DialogueEchelle(self, n, lue_pdf=M.lire_vp(self.doc, n), lue_texte=M.lire_texte(self.doc, n),
                            actuelle=self.echelles.get(n) or self.echelles.get("*"))
        if d.exec() != QDialog.Accepted:
            return False
        e = d.resultat
        cible = "*" if d.toutes.isChecked() else n
        if "etalonner" in e:
            self.mesure.update(etalon={"unite": e["etalonner"], "cible": cible, "garder": d.garder.isChecked()},
                               page=None, points=[])
            self._maj_bandeau_mesure()
            self.rafraichir_pages()
            return True
        self._poser_echelle(cible, e, d.garder.isChecked())
        return True

    def _poser_echelle(self, cible, e, garder):
        if cible == "*":
            self.echelles.clear()
        self.echelles[cible] = e
        journal = [_("Echelle : {e}", e=e.get("texte") or "")]
        if garder:
            self.memoriser(_("Echelle du plan"))
            pages = range(len(self.doc)) if cible == "*" else [cible]
            refus = [p + 1 for p in pages if not M.ecrire_vp(self.doc, p, e)]
            if refus:
                journal.append(_("Pages {p} : leur échelle d'origine (logiciel de plan) est gardée dans le PDF ; "
                                 "PhilPDF utilise la vôtre pour mesurer.", p=", ".join(map(str, refus))))
            self.apres_modif(journal)
        self._maj_bandeau_mesure()

    # ------------------------------------------------------------ souris
    def _point_mesure(self, pw, pt, mods):
        """Point corrige : Maj = angle droit/45°, sinon aimant sur les traits du plan."""
        m = self.mesure
        p = (pt.x, pt.y)
        m["accroche"] = False
        if mods & Qt.ShiftModifier and m["points"] and m["page"] == pw.num:
            return M.contraindre(m["points"][-1], p)
        if self.cb_aimant.isChecked():
            a = self._aimants.get(pw.num)
            if a is None:
                a = self._aimants[pw.num] = M.Aimant(self.doc[pw.num])
            q = a.proche(p[0], p[1], 7 / pw.echelle())
            if q is not None:
                m["accroche"] = True
                return q
        return p

    def clic_mesure(self, pw, pt, mods):
        m = self.mesure
        if m["points"] and m["page"] != pw.num:
            m["points"] = []
        if m["etalon"] is None and self.echelle_page(pw.num) is None:
            if not self.regler_echelle(pw.num):
                return
            if m["etalon"] is None and self.echelle_page(pw.num) is None:
                return
        m["page"] = pw.num
        p = self._point_mesure(pw, pt, mods)
        if m["points"] and math.dist(p, m["points"][-1]) < 0.5:
            return
        m["points"].append(p)
        deux = m["etalon"] is not None or m["genre"] == "distance"
        if deux and len(m["points"]) == 2:
            self.finir_mesure()
            return
        self._maj_bandeau_mesure()
        pw.update()

    def survol_mesure(self, pw, pt, mods):
        m = self.mesure
        m["survol"] = (pw.num, self._point_mesure(pw, pt, mods))
        if not m["points"] and getattr(self, "_page_lbl_mesure", None) != pw.num:
            self._page_lbl_mesure = pw.num
            m["page_vue"] = pw.num
            self._maj_bandeau_mesure()
        if m["points"]:
            self.lbl_mesure.setText(self._texte_en_cours())
        pw.update()

    def _points_avec_survol(self):
        m = self.mesure
        pts = list(m["points"])
        s = m.get("survol")
        if s and s[0] == m["page"] and pts:
            pts.append(s[1])
        return pts

    def _texte_en_cours(self):
        m = self.mesure
        if m["page"] is None:
            return ""
        pts = self._points_avec_survol()
        if m["etalon"] is not None:
            return _("Etalonnage : {d:.1f} pt dans le PDF", d=M.longueur(pts))
        e = self.echelle_page(m["page"])
        if not e or len(pts) < 2:
            return AIDES[m["genre"]]
        g = m["genre"]
        v = M.valeurs(g, pts, e)
        if g == "surface":
            if len(pts) < 3:
                return _("Longueur : {v}", v=M.texte_valeur("distance", v, e["u"]))
            return _("Surface : {s}  ·  périmètre {p}", s=M.texte_valeur(g, v, e["u"]),
                     p=M.texte_valeur("distance", v, e["u"]))
        seg = M.longueur(pts[-2:]) * e["c"]
        if g == "perimetre" and len(pts) > 2:
            return _("Total : {t}  ·  dernier côté {s}", t=M.texte_valeur(g, v, e["u"]),
                     s=f"{M.nombre(seg)} {e['u']}")
        return _("Distance : {t}", t=M.texte_valeur(g, v, e["u"]))

    def finir_mesure(self):
        m = self.mesure
        pts, n, g = list(m["points"]), m["page"], m["genre"]
        if n is None:
            return
        if m["etalon"] is not None:
            et = m["etalon"]
            m.update(points=[], page=None, etalon=None)
            if len(pts) == 2 and M.longueur(pts) > 1:
                from .dialogues_mesure import demander_longueur
                reel = demander_longueur(self, et["unite"])
                if reel:
                    self._poser_echelle(et["cible"] if et["cible"] == "*" else n,
                                        M.depuis_etalon(M.longueur(pts), reel, et["unite"]), et["garder"])
                    self._derniere_mesure = _("Echelle étalonnée : {e}", e=self.echelle_page(n)["texte"])
            self._maj_bandeau_mesure()
            self.rafraichir_pages()
            return
        mini = 3 if g == "surface" else 2
        if len(pts) < mini:
            return
        e = self.echelle_page(n)
        nom = ""
        if self.cb_nommer.isChecked():
            nom, ok = QInputDialog.getText(self, _("Mesure"), _("Nom de cette mesure (laisser vide : aucun) :"))
            if not ok:
                m.update(points=[], page=None)
                self.rafraichir_pages()
                return
            nom = nom.strip()
        self.memoriser(_("Mesure"))
        texte, _i = M.ecrire(self.doc, n, g, pts, e, nom)
        m.update(points=[], page=None)
        self._derniere_mesure = _("Dernière mesure : {t}", t=texte)
        self.apres_modif([_("Mesure ajoutée (page {n}) : {t}", n=n + 1, t=texte)])
        self._maj_bandeau_mesure()

    def annuler_point_mesure(self):
        m = self.mesure
        if m["points"]:
            m["points"].pop()
            if not m["points"]:
                m["page"] = None
            self._maj_bandeau_mesure()
            self.rafraichir_pages()
            return True
        return False

    def abandonner_mesure(self):
        """Echap : abandonne le trace en cours ; s'il n'y en a pas, False (on sort de l'outil)."""
        m = self.mesure
        if m["points"] or m["etalon"] is not None:
            m.update(points=[], page=None, etalon=None)
            self._maj_bandeau_mesure()
            self.rafraichir_pages()
            return True
        return False

    def menu_mesure(self, pw, pt, pos_globale):
        """Clic droit : finit le trace en cours ; sur une mesure posee : renommer, supprimer."""
        m = self.mesure
        if m["points"]:
            if m["genre"] in ("perimetre", "surface"):
                self.finir_mesure()
            return
        ident = None
        for a in self.doc[pw.num].annots():
            if fitz.Rect(a.rect).contains(pt):
                ident = M.identifiant(self.doc, a) or ident
        menu = QMenu(self)
        if ident:
            menu.addAction(_("Renommer la mesure..."), lambda: self._renommer_mesure(pw.num, ident))
            menu.addAction(_("Supprimer la mesure"), lambda: self._supprimer_mesure(pw.num, ident))
            menu.addSeparator()
        menu.addAction(_("Echelle de cette page..."), lambda: self.regler_echelle(pw.num))
        menu.addAction(_("Liste des mesures..."), self.liste_mesures)
        menu.exec(pos_globale)

    def _renommer_mesure(self, n, ident):
        info = next((x for x in M.lister(self.doc) if x["ident"] == ident and x["philpdf"]), None)
        nom, ok = QInputDialog.getText(self, _("Renommer"), _("Nom de la mesure (ex. Salon, Parcelle 12) :"),
                                       text=info["nom"] if info else "")
        if ok:
            self.memoriser(_("Mesure renommée"))
            M.renommer(self.doc, n, ident, nom.strip())
            self.apres_modif([_("Mesure renommée : {n}", n=nom.strip() or "-")])

    def _supprimer_mesure(self, n, ident):
        self.memoriser(_("Mesure supprimée"))
        M.supprimer(self.doc, n, ident)
        self.apres_modif([_("Mesure supprimée.")])

    def liste_mesures(self):
        from .dialogues_mesure import DialogueMesures
        DialogueMesures(self).exec()

    # ------------------------------------------------------------ dessin du trace en cours
    def dessiner_mesure(self, p, pw):
        m = self.mesure
        s = m.get("survol")
        if s and s[0] == pw.num and m.get("accroche"):
            c = pw.vers_ecran(fitz.Rect(s[1], s[1])).center()
            p.setPen(QPen(QColor("#d81b60"), 1.5))
            p.setBrush(Qt.NoBrush)
            p.drawRect(QRectF(c.x() - 5, c.y() - 5, 10, 10))
        if m["page"] != pw.num or not m["points"]:
            return
        pts = self._points_avec_survol()
        ecran = [pw.vers_ecran(fitz.Rect(q, q)).center() for q in pts]
        coul = QColor("#d81b60") if m["etalon"] is not None else QColor(*[int(c * 255) for c in M.COULEURS[m["genre"]]])
        p.setPen(QPen(coul, 1.8, Qt.DashLine))
        if m["genre"] == "surface" and m["etalon"] is None and len(ecran) >= 3:
            f = QColor(coul)
            f.setAlpha(40)
            p.setBrush(f)
            p.drawPolygon(QPolygonF(ecran))
        else:
            p.setBrush(Qt.NoBrush)
            for a, b in zip(ecran, ecran[1:]):
                p.drawLine(a, b)
        p.setPen(QPen(coul, 1))
        p.setBrush(QColor("#ffffff"))
        for c in ecran[:len(m["points"])]:
            p.drawEllipse(c, 3.5, 3.5)
        t = self._texte_en_cours()
        if t and len(pts) >= 2:
            fo = QFont()
            fo.setBold(True)
            p.setFont(fo)
            fin = ecran[-1]
            lt = p.fontMetrics().horizontalAdvance(t) + 12
            r = QRectF(fin.x() + 12, fin.y() + 10, lt, p.fontMetrics().height() + 6)
            if r.right() > pw.width():
                r.moveRight(fin.x() - 12)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(20, 20, 20, 200))
            p.drawRoundedRect(r, 4, 4)
            p.setPen(QColor("#ffffff"))
            p.drawText(r, Qt.AlignCenter, t)
