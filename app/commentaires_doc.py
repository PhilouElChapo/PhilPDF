"""Outils de commentaire (mixin de OngletDocument) : note, texte libre, rectangle, rectangle arrondi, ellipse, ligne,
fleche, dessin a main levee ; et le volet « Commentaires » (liste, recherche, aller a).

Ce sont de vraies annotations PDF, lisibles et modifiables dans Acrobat (le rectangle arrondi est un polygone)."""
import datetime
import math

import pymupdf as fitz
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor, QPen, QPainterPath, QPixmap, QPainter, QIcon
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QButtonGroup, QComboBox,
                               QCheckBox, QInputDialog, QColorDialog, QWidget, QLineEdit, QListWidget,
                               QListWidgetItem, QToolButton, QMenu)

from .langue import _

OUTILS = [("note", _("Note")), ("texte", _("Texte libre")), ("rect", _("Rectangle")),
          ("arrondi", _("Rectangle arrondi")), ("ellipse", _("Ellipse")), ("ligne", _("Ligne")),
          ("fleche", _("Flèche")), ("main", _("Main levée"))]
AIDES = {"note": _("Cliquez où mettre la note"), "texte": _("Tracez le cadre du texte"),
         "rect": _("Glissez pour tracer (Maj : carré)"), "arrondi": _("Glissez pour tracer (Maj : carré)"),
         "ellipse": _("Glissez pour tracer (Maj : cercle)"), "ligne": _("Glissez d'un bout à l'autre (Maj : 45°)"),
         "fleche": _("Glissez du départ vers la pointe (Maj : 45°)"), "main": _("Dessinez en gardant le bouton appuyé")}
TYPES = {fitz.PDF_ANNOT_TEXT: _("Note"), fitz.PDF_ANNOT_FREE_TEXT: _("Texte libre"),
         fitz.PDF_ANNOT_SQUARE: _("Rectangle"), fitz.PDF_ANNOT_CIRCLE: _("Ellipse"), fitz.PDF_ANNOT_LINE: _("Ligne"),
         fitz.PDF_ANNOT_POLYGON: _("Forme"), fitz.PDF_ANNOT_POLY_LINE: _("Ligne brisée"),
         fitz.PDF_ANNOT_INK: _("Dessin"), fitz.PDF_ANNOT_HIGHLIGHT: _("Surlignage"),
         fitz.PDF_ANNOT_UNDERLINE: _("Soulignement"), fitz.PDF_ANNOT_SQUIGGLY: _("Soulignement ondulé"),
         fitz.PDF_ANNOT_STRIKE_OUT: _("Texte barré"), fitz.PDF_ANNOT_STAMP: _("Tampon")}


def _icone_couleur(c):
    pm = QPixmap(16, 16)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(c))
    p.setPen(QPen(QColor("#666"), 1))
    p.drawRoundedRect(QRectF(1, 1, 14, 14), 3, 3)
    p.end()
    return QIcon(pm)


def points_arrondi(r, rayon=None, pas=6):
    """Contour d'un rectangle aux coins arrondis (polygone : lisible par tous les lecteurs PDF)."""
    rayon = rayon if rayon is not None else min(r.width, r.height) * 0.18
    rayon = max(0.0, min(rayon, r.width / 2, r.height / 2))
    pts = []
    coins = ((r.x1 - rayon, r.y0 + rayon, -90), (r.x1 - rayon, r.y1 - rayon, 0),
             (r.x0 + rayon, r.y1 - rayon, 90), (r.x0 + rayon, r.y0 + rayon, 180))
    for cx, cy, a0 in coins:
        for k in range(pas + 1):
            a = math.radians(a0 + 90 * k / pas)
            pts.append(fitz.Point(cx + rayon * math.cos(a), cy + rayon * math.sin(a)))
    return pts


class MixinCommentaires:
    def _construire_bandeau_comm(self, v):
        b = self.bandeau_comm = QFrame()
        b.setObjectName("bandeaucomm")
        b.setStyleSheet("QFrame#bandeaucomm{background:#f1ebfc;border-bottom:1px solid #ddd0f6}"
                        "QLabel{color:#3f2380} QPushButton{padding:4px 10px}"
                        "QPushButton:checked{background:#6d3fc6;color:#fff;border-color:#6d3fc6}")
        h = QHBoxLayout(b)
        h.setContentsMargins(16, 6, 16, 6)
        h.addWidget(QLabel("<b>" + _("Commenter") + "</b>"))
        self.groupe_comm = QButtonGroup(b)
        self.boutons_comm = {}
        for k, lib in OUTILS:
            bt = QPushButton(lib)
            bt.setCheckable(True)
            bt.setObjectName("comm_" + k)
            bt.setToolTip(AIDES[k])
            bt.clicked.connect(lambda _c=False, k=k: self.choisir_outil_comm(k))
            self.groupe_comm.addButton(bt)
            self.boutons_comm[k] = bt
            h.addWidget(bt)
        h.addSpacing(8)
        self.b_coul_comm = QToolButton()
        self.b_coul_comm.setToolTip(_("Couleur du trait"))
        self.b_coul_comm.clicked.connect(self._choisir_couleur_comm)
        h.addWidget(self.b_coul_comm)
        self.c_epaisseur = QComboBox()
        self.c_epaisseur.setToolTip(_("Epaisseur du trait"))
        for e in (1, 2, 3, 5, 8):
            self.c_epaisseur.addItem(f"{e} pt", e)
        self.c_epaisseur.setCurrentIndex(1)
        h.addWidget(self.c_epaisseur)
        self.c_style = QComboBox()
        self.c_style.setToolTip(_("Type de stylo"))
        for k, lib in (("plein", _("Trait continu")), ("tirets", _("Tirets")), ("points", _("Pointillés")),
                       ("feutre", _("Surligneur (large, transparent)"))):
            self.c_style.addItem(lib, k)
        h.addWidget(self.c_style)
        self.cb_remplir = QCheckBox(_("Remplir"))
        self.cb_remplir.setToolTip(_("Fond de la forme, de la même couleur en transparent"))
        h.addWidget(self.cb_remplir)
        self.lbl_comm = QLabel()
        h.addWidget(self.lbl_comm, 1)
        bt = QPushButton(_("Terminer"))
        bt.setProperty("primaire", True)
        bt.clicked.connect(lambda: self.changer_mode(None))
        h.addWidget(bt)
        b.hide()
        v.addWidget(b)
        self.comm = {"outil": "rect", "debut": None, "fin": None, "points": [], "page": None}
        self.couleur_comm = self.params.get("couleur_formes", "#d32f2f")
        self._maj_couleur_comm()
        self.boutons_comm["rect"].setChecked(True)

    def _maj_couleur_comm(self):
        self.b_coul_comm.setIcon(_icone_couleur(self.couleur_comm))

    def _choisir_couleur_comm(self):
        m = QMenu(self)
        for c, nom in (("#d32f2f", _("Rouge")), ("#0f6cbd", _("Bleu")), ("#2e7d32", _("Vert")), ("#f59e0b", _("Orange")),
                       ("#6d3fc6", _("Violet")), ("#000000", _("Noir")), ("#ffe600", _("Jaune"))):
            m.addAction(_icone_couleur(c), nom, lambda c=c: self._poser_couleur_comm(c))
        m.addSeparator()
        m.addAction(_("Autre couleur..."), lambda: self._poser_couleur_comm(
            QColorDialog.getColor(QColor(self.couleur_comm), self).name()))
        m.exec(self.b_coul_comm.mapToGlobal(self.b_coul_comm.rect().bottomLeft()))

    def _poser_couleur_comm(self, c):
        if c and QColor(c).isValid():
            self.couleur_comm = c
            self.params["couleur_formes"] = c
            self.params.enregistrer()
            self._maj_couleur_comm()

    def choisir_outil_comm(self, k):
        self.comm.update(outil=k, debut=None, fin=None, points=[], page=None)
        self.boutons_comm[k].setChecked(True)
        self.lbl_comm.setText(AIDES[k])

    def entrer_commentaires(self):
        self.bandeau_comm.show()
        self.choisir_outil_comm(self.comm["outil"])
        self.montrer_volet_commentaires()

    def sortir_commentaires(self):
        self.bandeau_comm.hide()
        self.comm.update(debut=None, fin=None, points=[], page=None)

    # ------------------------------------------------------------ souris
    def _contraindre(self, a, b, outil):
        if outil in ("rect", "arrondi", "ellipse"):
            c = max(abs(b.x - a.x), abs(b.y - a.y))
            return fitz.Point(a.x + math.copysign(c, b.x - a.x or 1), a.y + math.copysign(c, b.y - a.y or 1))
        d = math.dist(a, b)
        ang = round(math.atan2(b.y - a.y, b.x - a.x) / (math.pi / 4)) * (math.pi / 4)
        return fitz.Point(a.x + d * math.cos(ang), a.y + d * math.sin(ang))

    def comm_presse(self, pw, pt, mods):
        c = self.comm
        if c["outil"] == "note":
            self.poser_note(pw.num, pt)
            return
        c.update(page=pw.num, debut=fitz.Point(pt), fin=fitz.Point(pt), points=[fitz.Point(pt)])

    def comm_glisse(self, pw, pt, mods):
        c = self.comm
        if c["page"] != pw.num or c["debut"] is None:
            return
        p = fitz.Point(pt)
        if mods & Qt.ShiftModifier and c["outil"] not in ("main", "texte"):
            p = self._contraindre(c["debut"], p, c["outil"])
        c["fin"] = p
        if c["outil"] == "main" and math.dist(c["points"][-1], p) > 1.2:
            c["points"].append(p)
        pw.update()

    def comm_lache(self, pw, pt, mods):
        c = self.comm
        if c["page"] != pw.num or c["debut"] is None:
            return
        a, b, outil = c["debut"], c["fin"], c["outil"]
        pts = list(c["points"])
        c.update(debut=None, fin=None, points=[], page=None)
        if outil != "main" and math.dist(a, b) < 3:
            pw.update()
            return
        self.creer_commentaire(pw.num, outil, a, b, pts)

    # ------------------------------------------------------------ creation
    def _auteur(self):
        return self.params.get("auteur") or self.params.get("machine", "")

    def poser_note(self, n, pt):
        txt, ok = QInputDialog.getMultiLineText(self, _("Note"), _("Texte de la note :"))
        if not ok or not txt.strip():
            return
        self.memoriser(_("Note"))
        a = self.doc[n].add_text_annot(fitz.Point(pt), txt, icon="Comment")
        a.set_info(title=self._auteur())
        a.set_colors(stroke=QColor(self.couleur_comm if self.couleur_comm != "#000000" else "#ffe600").getRgbF()[:3])
        a.update()
        self.apres_modif([_("Note ajoutée.")])
        self.remplir_volet_commentaires()

    def creer_commentaire(self, n, outil, a, b, pts=()):
        page = self.doc[n]
        coul = QColor(self.couleur_comm).getRgbF()[:3]
        ep = self.c_epaisseur.currentData() or 2
        r = fitz.Rect(a, b)
        r.normalize()
        if outil == "texte":
            txt, ok = QInputDialog.getMultiLineText(self, _("Texte libre"), _("Texte :"))
            if not ok or not txt.strip():
                return
            if r.height < 18:
                r.y1 = r.y0 + 22
            if r.width < 60:
                r.x1 = r.x0 + 160
        self.memoriser(dict(OUTILS)[outil])
        if outil == "rect":
            an = page.add_rect_annot(r)
        elif outil == "ellipse":
            an = page.add_circle_annot(r)
        elif outil == "arrondi":
            an = page.add_polygon_annot(points_arrondi(r))
        elif outil in ("ligne", "fleche"):
            an = page.add_line_annot(a, b)
            if outil == "fleche":
                an.set_line_ends(fitz.PDF_ANNOT_LE_NONE, fitz.PDF_ANNOT_LE_CLOSED_ARROW)
        elif outil == "main":
            if len(pts) < 2:
                return
            an = page.add_ink_annot([[(p.x, p.y) for p in pts]])
        else:
            an = page.add_freetext_annot(r, txt, fontsize=12, fontname="helv", text_color=coul,
                                         fill_color=None, align=fitz.TEXT_ALIGN_LEFT)
        if outil != "texte":
            remplir = self.cb_remplir.isChecked() and outil in ("rect", "ellipse", "arrondi")
            an.set_colors(stroke=coul, fill=coul if remplir else None)
            if outil == "fleche":
                an.set_colors(stroke=coul, fill=coul)
            style = self.c_style.currentData()
            if style == "feutre":
                an.set_border(width=max(ep, 8))
                an.set_opacity(0.4)
            else:
                an.set_border(width=ep, dashes={"tirets": [ep * 3, ep * 2], "points": [ep, ep * 1.5]}.get(style))
                if remplir:
                    an.set_opacity(0.35)
        an.set_info(title=self._auteur(), subject=dict(OUTILS)[outil])
        an.update()
        self.apres_modif([_("{x} ajouté(e).", x=dict(OUTILS)[outil])])
        self.remplir_volet_commentaires()

    # ------------------------------------------------------------ apercu pendant le trace
    def dessiner_comm(self, p, pw):
        c = self.comm
        if c["page"] != pw.num or c["debut"] is None:
            return
        a = pw.vers_ecran(fitz.Rect(c["debut"], c["debut"])).center()
        b = pw.vers_ecran(fitz.Rect(c["fin"], c["fin"])).center()
        coul = QColor(self.couleur_comm)
        p.setRenderHint(QPainter.Antialiasing)
        style = self.c_style.currentData()
        ep = (self.c_epaisseur.currentData() or 2) * (4 if style == "feutre" else 1)
        if style == "feutre":
            coul.setAlpha(110)
        p.setPen(QPen(coul, max(1.0, ep * pw.echelle()),
                      {"tirets": Qt.DashLine, "points": Qt.DotLine}.get(style, Qt.SolidLine), Qt.RoundCap, Qt.RoundJoin))
        f = QColor(coul)
        f.setAlpha(90 if self.cb_remplir.isChecked() else 0)
        p.setBrush(f)
        r = QRectF(a, b).normalized()
        o = c["outil"]
        if o in ("rect", "texte"):
            p.drawRect(r)
        elif o == "arrondi":
            ray = min(r.width(), r.height()) * 0.18
            p.drawRoundedRect(r, ray, ray)
        elif o == "ellipse":
            p.drawEllipse(r)
        elif o in ("ligne", "fleche"):
            p.drawLine(a, b)
            if o == "fleche":
                ang = math.atan2(b.y() - a.y(), b.x() - a.x())
                t = 12
                p.setBrush(coul)
                from PySide6.QtGui import QPolygonF
                p.drawPolygon(QPolygonF([b, QPointF(b.x() - t * math.cos(ang - 0.4), b.y() - t * math.sin(ang - 0.4)),
                                         QPointF(b.x() - t * math.cos(ang + 0.4), b.y() - t * math.sin(ang + 0.4))]))
        elif o == "main" and len(c["points"]) > 1:
            chemin = QPainterPath()
            ecr = [pw.vers_ecran(fitz.Rect(q, q)).center() for q in c["points"]]
            chemin.moveTo(ecr[0])
            for q in ecr[1:]:
                chemin.lineTo(q)
            p.setBrush(Qt.NoBrush)
            p.drawPath(chemin)

    # ------------------------------------------------------------ volet « Commentaires »
    def _volet_commentaires(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(10, 10, 10, 10)
        t = QLabel("<b>" + _("Commentaires") + "</b>")
        v.addWidget(t)
        self.comm_recherche = QLineEdit()
        self.comm_recherche.setPlaceholderText(_("Rechercher dans les commentaires"))
        self.comm_recherche.setClearButtonEnabled(True)
        self.comm_recherche.textChanged.connect(lambda _t: self.remplir_volet_commentaires())
        v.addWidget(self.comm_recherche)
        self.liste_comm = QListWidget()
        self.liste_comm.setObjectName("liste_commentaires")
        self.liste_comm.setWordWrap(True)
        self.liste_comm.setStyleSheet("QListWidget{border:none;background:transparent}"
                                      "QListWidget::item{border-bottom:1px solid #e6e6e6;padding:6px 2px}")
        self.liste_comm.itemClicked.connect(self._aller_commentaire)
        self.liste_comm.itemDoubleClicked.connect(self._modifier_commentaire)
        v.addWidget(self.liste_comm, 1)
        self.lbl_nb_comm = QLabel()
        self.lbl_nb_comm.setStyleSheet("color:#666")
        v.addWidget(self.lbl_nb_comm)
        b = QPushButton(_("Fermer la liste"))
        b.clicked.connect(lambda: self.pile_volet.setCurrentIndex(0))
        v.addWidget(b)
        return w

    def montrer_volet_commentaires(self):
        self.pile_volet.setCurrentIndex(self._idx_volet_comm)
        self._montrer_volet()
        self.remplir_volet_commentaires()

    def remplir_volet_commentaires(self):
        if not hasattr(self, "liste_comm") or self.pile_volet.currentIndex() != self._idx_volet_comm:
            return
        self.liste_comm.clear()
        cherche = self.comm_recherche.text().strip().lower()
        n_total = 0
        for n, page in enumerate(self.doc):
            for a in page.annots() or []:
                if a.type[0] in (fitz.PDF_ANNOT_POPUP, fitz.PDF_ANNOT_LINK, fitz.PDF_ANNOT_WIDGET):
                    continue
                info = a.info or {}
                texte = (info.get("content") or "").strip()
                if not texte and a.type[0] in (fitz.PDF_ANNOT_HIGHLIGHT, fitz.PDF_ANNOT_UNDERLINE,
                                               fitz.PDF_ANNOT_STRIKE_OUT, fitz.PDF_ANNOT_SQUIGGLY):
                    try:
                        texte = page.get_textbox(a.rect).strip().replace("\n", " ")
                    except Exception:
                        texte = ""
                n_total += 1
                type_ = (info.get("subject") or "").strip() or TYPES.get(a.type[0], a.type[1])
                auteur = info.get("title") or ""
                quand = _date_annot(info.get("modDate") or info.get("creationDate") or "")
                if cherche and cherche not in (texte + " " + auteur + " " + type_).lower():
                    continue
                coul = a.colors.get("stroke") or a.colors.get("fill") or (0.4, 0.4, 0.4)
                it = QListWidgetItem(_icone_couleur(QColor.fromRgbF(*coul[:3]).name()),
                                     f"p. {n + 1} · {type_}" + (f" · {auteur}" if auteur else "") +
                                     (f" · {quand}" if quand else "") + (f"\n{texte[:200]}" if texte else ""))
                it.setData(Qt.UserRole, (n, a.xref))
                self.liste_comm.addItem(it)
        self.lbl_nb_comm.setText(_("{n} commentaire(s)", n=n_total) if n_total else
                                 _("Aucun commentaire dans ce document."))

    def _aller_commentaire(self, it):
        n, x = it.data(Qt.UserRole)
        page = self.doc[n]                    # garder la page vivante tant qu'on se sert de l'annotation
        a = next((a for a in page.annots() if a.xref == x), None)
        if a is None:
            return
        r = fitz.Rect(a.rect)
        self.aller_a(n, r)
        self.objet = {"type": "annot", "page": n, "xref": x, "rect": r, "philpdf": False,
                      "garder_proportions": a.type[0] == fitz.PDF_ANNOT_STAMP}
        self.rafraichir_pages()

    def _modifier_commentaire(self, it):
        n, x = it.data(Qt.UserRole)
        page = self.doc[n]                    # garder la page vivante tant qu'on se sert de l'annotation
        a = next((a for a in page.annots() if a.xref == x), None)
        if a is None:
            return
        t, ok = QInputDialog.getMultiLineText(self, _("Commentaire"), _("Texte :"), (a.info or {}).get("content", ""))
        if ok:
            self.memoriser(_("Commentaire modifié"))
            a.set_info(content=t)
            a.update()
            self.apres_modif()
            self.remplir_volet_commentaires()


def _date_annot(d):
    """« D:20261029013000+01'00' » -> « 29/10 01:30 »."""
    try:
        from moteur.metadonnees import lire_date
        x = lire_date(d)
        if not x:
            return ""
        maint = datetime.datetime.now(x.tzinfo) if x.tzinfo else datetime.datetime.now()
        return x.strftime("%d/%m %H:%M" if x.year == maint.year else "%d/%m/%Y")
    except Exception:
        return ""
