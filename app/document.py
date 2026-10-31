"""Onglet d'un fichier ouvert : visionneuse, vignettes, selection, barre rapide,
mode Modifier facon Acrobat (deplacer, editer dans la page), objets deplacables
(tampons, signatures, annotations), organisation des pages."""
import os, sys
import pymupdf as fitz
from PySide6.QtCore import Qt, Signal, QObject, QRectF, QPointF, QTimer, QSize, QPoint, QRect
from PySide6.QtGui import QImage, QPainter, QColor, QPen, QPixmap, QGuiApplication, QFont, QIcon
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QFrame, QLayout, QLabel, QToolButton,
                               QListWidget, QListWidgetItem, QSplitter, QPushButton, QInputDialog, QMenu,
                               QMessageBox, QLineEdit, QDialog, QDialogButtonBox, QCheckBox, QFormLayout,
                               QAbstractItemView, QComboBox, QSpinBox, QStackedWidget, QColorDialog, QFileDialog,
                               QDoubleSpinBox, QApplication)
from .icones import icone
from .outils import outil, famille
from .dialogues import boutons_fr, DialogueBibliotheque
from moteur.modifier import Editeur, CANDIDATS
from moteur import objets
from .signature_doc import MixinSignature
from .commentaires_doc import MixinCommentaires
from .signets_doc import MixinSignets
from .mesure_doc import MixinMesure
from .formulaire_doc import MixinFormulaire, types_a_tracer
from .langue import _

ECRAN = 96 / 72                 # points PDF -> pixels a 100 %
POIGNEE = 8                      # taille des poignees (pixels)
DEPLACABLES = (fitz.PDF_ANNOT_STAMP, fitz.PDF_ANNOT_FREE_TEXT, fitz.PDF_ANNOT_TEXT, fitz.PDF_ANNOT_INK,
               fitz.PDF_ANNOT_SQUARE, fitz.PDF_ANNOT_CIRCLE, fitz.PDF_ANNOT_LINE)


def question(parent, titre, texte, boutons):
    """Boite de question en francais. boutons = [(libelle, role)] ; renvoie l'indice clique."""
    m = QMessageBox(parent)
    m.setWindowTitle(titre)
    m.setText(texte)
    bs = [m.addButton(lib, role) for lib, role in boutons]
    m.exec()
    return bs.index(m.clickedButton()) if m.clickedButton() in bs else len(bs) - 1


# ================================================================ page
class PageWidget(QWidget):
    def __init__(self, onglet, num):
        super().__init__()
        self.o, self.num = onglet, num
        self.image, self.image_zoom = None, None
        self.survol = None
        self.glisse = None
        self.editeur = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.ClickFocus)
        self.maj_taille()

    # ---- geometrie
    def rect_page(self):
        r = self.o.doc[self.num].rect
        rot = self.o.rotation_vue.get(self.num, 0)
        return (r.height, r.width) if rot in (90, 270) else (r.width, r.height)

    def echelle(self):
        return self.o.zoom * ECRAN

    def maj_taille(self):
        w, h = self.rect_page()
        e = self.echelle()
        self.setFixedSize(int(w * e), int(h * e))
        self.image = None

    def _mat_affichage(self):
        page = self.o.doc[self.num]
        m = fitz.Matrix(self.echelle(), self.echelle()).prerotate(self.o.rotation_vue.get(self.num, 0))
        r = page.rect * m
        return m * fitz.Matrix(1, 0, 0, 1, -r.x0, -r.y0)

    def _mat_texte(self):
        return self.o.doc[self.num].rotation_matrix * self._mat_affichage()

    def vers_pdf(self, pos):
        return fitz.Point(pos.x(), pos.y()) * ~self._mat_texte()

    def vers_ecran(self, rect):
        r = fitz.Rect(rect) * self._mat_texte()
        r.normalize()
        return QRectF(r.x0, r.y0, r.width, r.height)

    # ---- dessin
    def paintEvent(self, ev):
        p = QPainter(self)
        if self.image is None or self.image_zoom != self.o.zoom:
            dpr = self.devicePixelRatioF()
            pm = self.o.doc[self.num].get_pixmap(matrix=self._mat_affichage() * fitz.Matrix(dpr, dpr), alpha=False)
            img = QImage(pm.samples, pm.width, pm.height, pm.stride, QImage.Format_RGB888).copy()
            img.setDevicePixelRatio(dpr)
            self.image, self.image_zoom = img, self.o.zoom
        p.drawImage(0, 0, self.image)
        o = self.o
        ed = getattr(self, "editeur", None)
        if ed is not None and getattr(ed, "para", None):      # pendant la saisie, l'ancien paragraphe est masque
            p.fillRect(self.vers_ecran(fitz.Rect(ed.para["rect"]) + (-1, -1, 1, 1)), QColor(255, 255, 255))
        champs = list(o.doc[self.num].widgets()) if o.mode in (None, "formulaire", "signer_num", "champ_signature") else []
        for w in champs:
            if w.field_type == fitz.PDF_WIDGET_TYPE_SIGNATURE:
                if w.is_signed and o.mode != "formulaire":
                    continue                       # signature apposee : on la laisse telle qu'Acrobat la montre
                if o.mode != "formulaire":
                    r = self.vers_ecran(w.rect)
                    p.setPen(QPen(QColor("#1462c2"), 1.5, Qt.DashLine))
                    p.setBrush(QColor(20, 98, 194, 28))
                    p.drawRect(r)
                    p.setPen(QColor("#1462c2"))
                    f = p.font()
                    f.setPointSizeF(max(7.0, min(10.0, r.height() / 4)))
                    p.setFont(f)
                    sign = o.infos_champ_sig(w)["signataire"]
                    p.drawText(r, Qt.AlignCenter | Qt.TextWordWrap,
                               _("Signer ici") + (f"\n{sign}" if sign else ""))
                    continue
            elif o.mode in ("signer_num", "champ_signature"):
                continue
            if w.field_display == 1 and o.mode is None:
                continue                           # champ masque (par une regle « afficher si... »)
            if w.field_type == fitz.PDF_WIDGET_TYPE_BUTTON and o.mode is None:
                continue                           # un bouton se montre tel qu'il est dessine
            choisi = o.mode == "formulaire" and o.champ_choisi == (self.num, w.xref)
            if (o.mode is None and w.field_flags & fitz.PDF_FIELD_IS_REQUIRED
                    and (w.field_value or "") in ("", "Off")):
                p.setPen(QPen(QColor("#d32f2f"), 1.5))
                p.setBrush(QColor(255, 120, 120, 40))
                p.drawRect(self.vers_ecran(w.rect))
                continue
            p.setPen(QPen(QColor("#a35c00" if o.mode == "formulaire" else "#8fb4e3"), 2 if choisi else 1))
            p.setBrush(QColor(255, 196, 120, 90) if choisi else QColor(200, 220, 255, 70))
            p.drawRect(self.vers_ecran(w.rect))
            if o.mode == "formulaire":
                f = p.font()
                f.setPointSize(8)
                p.setFont(f)
                r = self.vers_ecran(w.rect)
                nom_ = w.field_name or ""
                lt = p.fontMetrics().horizontalAdvance(nom_) + 8
                ht = p.fontMetrics().height() + 2
                chip = QRectF(r.x(), r.y() - ht - 1, lt, ht)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor("#a35c00") if choisi else QColor(163, 92, 0, 200))
                p.drawRoundedRect(chip, 3, 3)
                p.setPen(QColor("#ffffff"))
                p.drawText(chip, Qt.AlignCenter, nom_)
                if choisi:                         # poignee pour agrandir
                    p.setPen(QPen(QColor("#ffffff"), 1))
                    p.setBrush(QColor("#a35c00"))
                    p.drawRect(QRectF(r.right() - 5, r.bottom() - 5, 10, 10))
        sel = o.selection
        if sel and sel["page"] == self.num:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(20, 98, 194, 70))
            for r in sel["lignes"]:
                p.drawRect(self.vers_ecran(r))
        for (pg, r) in o.resultats:
            if pg == self.num:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(255, 210, 0, 110) if (pg, r) != o.resultat_courant else QColor(255, 140, 0, 150))
                p.drawRect(self.vers_ecran(r))
        if o.mode == "modifier":
            for r, _retenu in o.paragraphes_page(self.num):   # un trait continu a gauche : ces lignes forment un paragraphe
                re_ = self.vers_ecran(fitz.Rect(r))
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(20, 98, 194, 170))
                p.drawRoundedRect(QRectF(re_.x() - 7, re_.y(), 3.5, re_.height()), 1.5, 1.5)
            for r, _t in o.lignes_page(self.num):
                actif = self.survol is not None and fitz.Rect(r).contains(self.survol)
                p.setPen(QPen(QColor("#1462c2"), 2 if actif else 1, Qt.SolidLine if actif else Qt.DotLine))
                p.setBrush(QColor(20, 98, 194, 25) if actif else Qt.NoBrush)
                p.drawRect(self.vers_ecran(fitz.Rect(r) + (-1.5, -1, 1.5, 1)))
            for xref, r in o.images_page(self.num):
                p.setPen(QPen(QColor("#a35c00"), 1, Qt.DotLine))
                p.setBrush(Qt.NoBrush)
                p.drawRect(self.vers_ecran(r))
        rt = getattr(o, "retouche", None)
        if rt and rt["page"] == self.num and rt.get("apercu") is not None:       # retouche en direct sur l'image
            c, w_, h_, ang = rt["geo"]
            ce = self.vers_ecran(fitz.Rect(c, c))
            k = self.echelle()
            p.save()
            p.translate(ce.center())
            p.rotate(-ang)
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            p.fillRect(QRectF(-w_ * k / 2, -h_ * k / 2, w_ * k, h_ * k), QColor("#ffffff"))
            p.drawImage(QRectF(-w_ * k / 2, -h_ * k / 2, w_ * k, h_ * k), rt["apercu"])
            p.restore()
        obj = o.objet
        if obj and obj["page"] == self.num and not self.editeur:
            r = self.vers_ecran(obj["rect"])
            p.setPen(QPen(QColor("#1462c2"), 1.5))
            p.setBrush(Qt.NoBrush)
            p.drawRect(r)
            p.setBrush(QColor("#ffffff"))
            for c in self._poignees(r):
                p.drawRect(c)
            pr = self._poignee_rotation(r)
            if pr is not None:                       # poignee ronde de rotation, comme dans Word
                p.setPen(QPen(QColor("#1462c2"), 1.2))
                p.drawLine(QPointF(r.center().x(), r.top()), pr.center())
                p.setBrush(QColor("#ffffff"))
                p.drawEllipse(pr)
                p.setPen(QPen(QColor("#1462c2"), 1.4))
                p.drawArc(pr.adjusted(3, 3, -3, -3), 30 * 16, 270 * 16)
        for (pg, r) in o.marques_biffage:
            if pg == self.num:
                p.setPen(QPen(QColor("#c9252d"), 2))
                p.setBrush(QColor(0, 0, 0, 110))
                p.drawRect(self.vers_ecran(r))
        g = self.glisse
        if g and g.get("genre") == "rotation" and g.get("angle") is not None:
            import math
            r = self.vers_ecran(g["rect0"])
            c = r.center()
            a = math.radians(-g["angle"])                 # ecran : y vers le bas
            pts = []
            for x, y in ((r.left(), r.top()), (r.right(), r.top()), (r.right(), r.bottom()), (r.left(), r.bottom())):
                dx, dy = x - c.x(), y - c.y()
                pts.append(QPointF(c.x() + dx * math.cos(a) - dy * math.sin(a), c.y() + dx * math.sin(a) + dy * math.cos(a)))
            from PySide6.QtGui import QPolygonF
            p.setPen(QPen(QColor("#1462c2"), 1.5, Qt.DashLine))
            p.setBrush(QColor(20, 98, 194, 30))
            p.drawPolygon(QPolygonF(pts))
            p.setPen(QColor("#1462c2"))
            fo = QFont()
            fo.setBold(True)
            p.setFont(fo)
            p.drawText(QPointF(c.x() + 6, c.y() - 6), f"{g['angle']:+.0f}°")
        g_ = self.glisse
        if g_ and g_.get("genre") in ("lasso", "cadre_img"):        # trace de la zone en cours
            p.setPen(QPen(QColor("#d81b60"), 1.6, Qt.DashLine))
            p.setBrush(QColor(216, 27, 96, 40))
            if g_["genre"] == "cadre_img":
                p.drawRect(QRectF(self.vers_ecran(fitz.Rect(g_["debut"], g_["debut"])).center(),
                                  self.vers_ecran(fitz.Rect(g_["fin"], g_["fin"])).center()).normalized())
            elif len(g_["points"]) > 1:
                from PySide6.QtGui import QPolygonF
                p.drawPolygon(QPolygonF([self.vers_ecran(fitz.Rect(q, q)).center() for q in g_["points"]]))
        if self.glisse and self.glisse.get("fantome") is not None:
            p.setPen(QPen(QColor("#1462c2"), 1.5, Qt.DashLine))
            p.setBrush(QColor(20, 98, 194, 30))
            p.drawRect(self.vers_ecran(self.glisse["fantome"]))
        # apercu de ce qui va etre pose : coin haut gauche sous la souris
        if self.survol is not None and not self.editeur and not self.glisse:
            f = o.fantome(self.num, self.survol)
            if f:
                r, pix, texte, taille = f
                re = self.vers_ecran(r)
                if pix is not None:
                    p.setOpacity(0.55)
                    p.drawPixmap(re.toRect(), pix)
                    p.setOpacity(1.0)
                p.setPen(QPen(QColor("#1462c2"), 1.2, Qt.DashLine))
                p.setBrush(QColor(20, 98, 194, 22))
                p.drawRect(re)
                if texte:
                    fo = QFont()
                    fo.setPixelSize(max(8, int(taille * self.echelle() * 0.95)))
                    p.setFont(fo)
                    p.setPen(QColor(31, 31, 31, 120))
                    p.drawText(re.adjusted(3, 0, 0, 0), Qt.AlignLeft | Qt.AlignVCenter, texte)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor("#1462c2"))
                p.drawEllipse(re.topLeft(), 3, 3)
        if o.mode == "mesure":
            o.dessiner_mesure(p, self)
        if o.mode == "commenter":
            o.dessiner_comm(p, self)
        p.end()

    def leaveEvent(self, e):
        self.survol = None
        self.update()

    def _poignees(self, r):
        h = POIGNEE / 2
        return [QRectF(x - h, y - h, POIGNEE, POIGNEE) for x, y in
                ((r.left(), r.top()), (r.right(), r.top()), (r.left(), r.bottom()), (r.right(), r.bottom()))]

    def _poignee_rotation(self, r):
        obj = self.o.objet
        if not obj or obj["page"] != self.num or obj["type"] not in ("annot", "image", "ligne"):
            return None
        if obj["type"] == "annot" and not obj.get("philpdf"):
            return None
        d = 11
        return QRectF(r.center().x() - d / 2, r.top() - 24 - d / 2, d, d)

    def _sur_rotation(self, pos):
        obj = self.o.objet
        if not obj or obj["page"] != self.num:
            return False
        pr = self._poignee_rotation(self.vers_ecran(obj["rect"]))
        return pr is not None and pr.adjusted(-4, -4, 4, 4).contains(pos)

    def _angle_souris(self, pos, centre):
        import math
        return math.degrees(math.atan2(-(pos.y() - centre.y()), pos.x() - centre.x()))

    def _sur_poignee(self, pos):
        obj = self.o.objet
        if not obj or obj["page"] != self.num or obj["type"] == "ligne":
            return None
        for i, c in enumerate(self._poignees(self.vers_ecran(obj["rect"]))):
            if c.adjusted(-3, -3, 3, 3).contains(pos):
                return i
        return None

    def _bord_champ(self, pos):
        """En mode Formulaire : (widget, axes) si la souris est sur le coin ou un bord du champ (pour agrandir).
        axes : "xy" coin bas droit, "x" bord droit, "y" bord bas. Le champ choisi d'abord (sa poignee depasse)."""
        o = self.o
        cands = []
        if o.champ_choisi and o.champ_choisi[0] == self.num:
            wc = o._widget(o.champ_choisi)
            if wc is not None:
                cands.append(wc)
        cands += [w for w in o.doc[self.num].widgets() if not cands or w.xref != cands[0].xref]
        x, y = pos.x(), pos.y()
        for w in cands:
            r = self.vers_ecran(w.rect)
            if abs(x - r.right()) <= 8 and abs(y - r.bottom()) <= 8:
                return w, "xy"
            if abs(x - r.right()) <= 4 and r.top() <= y <= r.bottom():
                return w, "x"
            if abs(y - r.bottom()) <= 4 and r.left() <= x <= r.right():
                return w, "y"
        return None, None

    # ---- souris
    def mousePressEvent(self, e):
        o = self.o
        o.barre_rapide.hide()
        o.fermer_bulle_aide()
        if self.editeur:
            self.editeur.valider()
        pt = self.vers_pdf(e.position())
        if o.mode == "mesure":
            if e.button() == Qt.RightButton:
                o.menu_mesure(self, pt, e.globalPosition().toPoint())
            elif e.button() == Qt.LeftButton:
                o.clic_mesure(self, pt, e.modifiers())
            return
        if o.mode == "commenter" and e.button() == Qt.LeftButton:
            o.comm_presse(self, pt, e.modifiers())
            return
        if e.button() == Qt.RightButton:
            o.menu_contexte(self, pt, e.globalPosition().toPoint())
            return
        if e.button() != Qt.LeftButton:
            return
        if o.mode in ("poser", "ajout_texte", "ajout_image"):
            f = o.fantome(self.num, pt)
            hg = f[0].tl if f else pt
            self.survol = None
            if o.mode == "poser":
                o.poser_objet(self.num, hg)
            elif o.mode == "ajout_texte":
                self.editeur = EditeurParagraphe(self, None, hg)
            else:
                o.ajouter_image_ici(self.num, hg)
            return
        if o.mode == "formulaire":
            wb, axes = self._bord_champ(e.position())
            if wb is not None:                     # coin ou bord : agrandir / reduire
                o.champ_choisi = (self.num, wb.xref)
                self.glisse = {"genre": "champ", "mode": "redim", "axes": axes, "xref": wb.xref, "debut": pt,
                               "rect0": fitz.Rect(wb.rect), "fantome": None}
                o.rafraichir_pages()
                return
            w = o.champ_sous(self.num, pt)
            if w:
                o.champ_choisi = (self.num, w.xref)
                self.glisse = {"genre": "champ", "mode": "deplacer", "xref": w.xref,
                               "debut": pt, "rect0": fitz.Rect(w.rect), "fantome": None}
                o.rafraichir_pages()
                return
            o.champ_choisi = None
        if o.mode in ("signer_num", "champ_signature"):
            w = o.champ_sous(self.num, pt)
            if w is not None and w.field_type == fitz.PDF_WIDGET_TYPE_SIGNATURE:
                if o.mode == "signer_num":
                    o.clic_champ_signature(self.num, w)
                else:
                    o.regler_champ_signature(self.num, w)
                return
        if o.mode in ("lien", "recadrer", "biffer", "formulaire", "signer_num", "champ_signature"):
            self.glisse = {"genre": "zone", "debut": pt, "fantome": fitz.Rect(pt, pt)}
            return
        if o.mode is None:
            w = o.champ_sous(self.num, pt)
            if w:
                if w.field_type == fitz.PDF_WIDGET_TYPE_SIGNATURE:
                    o.clic_champ_signature(self.num, w)
                else:
                    o.remplir_champ(self, w)
                return
        if self._sur_rotation(e.position()):
            r = self.vers_ecran(o.objet["rect"])
            self.glisse = {"genre": "rotation", "centre": r.center(), "rect0": fitz.Rect(o.objet["rect"]),
                           "depart": self._angle_souris(e.position(), r.center()), "angle": None}
            return
        rt = getattr(o, "retouche", None)
        if rt and rt["page"] == self.num and o.ret_b_baguette.isChecked():
            if o.clic_baguette(pt, bool(e.modifiers() & Qt.ShiftModifier)):
                return
        if rt and rt["page"] == self.num and (o.ret_b_lasso.isChecked() or o.ret_b_cadre.isChecked()):
            self.glisse = {"genre": "lasso" if o.ret_b_lasso.isChecked() else "cadre_img", "debut": pt,
                           "points": [fitz.Point(pt)], "fin": fitz.Point(pt),
                           "ajouter": bool(e.modifiers() & Qt.ShiftModifier)}
            return
        poignee = self._sur_poignee(e.position())
        if poignee is not None:
            self.glisse = {"genre": "redim", "coin": poignee, "debut": pt, "rect0": fitz.Rect(o.objet["rect"]), "fantome": None}
            return
        trouve = o.objet_sous(self.num, pt)
        if trouve:
            o.choisir_objet(trouve)
            self.glisse = {"genre": "deplacer", "debut": pt, "rect0": fitz.Rect(trouve["rect"]), "fantome": None}
            return
        o.choisir_objet(None)
        if o.mode is None:
            o.debut_selection(self.num, pt)

    def mouseMoveEvent(self, e):
        o = self.o
        pt = self.vers_pdf(e.position())
        if o.mode == "mesure":
            self.setCursor(Qt.CrossCursor)
            o.survol_mesure(self, pt, e.modifiers())
            return
        if o.mode == "commenter":
            self.setCursor(Qt.CrossCursor)
            if e.buttons() & Qt.LeftButton:
                o.comm_glisse(self, pt, e.modifiers())
            return
        g = self.glisse
        if g and e.buttons() & Qt.LeftButton:
            d = pt - g["debut"]
            if g["genre"] == "rotation":
                a = self._angle_souris(e.position(), g["centre"]) - g["depart"]
                a = (a + 180) % 360 - 180
                if e.modifiers() & Qt.ShiftModifier:          # Maj : par pas de 15 degres
                    a = round(a / 15) * 15
                g["angle"] = a
                self.update()
                return
            if g["genre"] in ("lasso", "cadre_img"):
                g["fin"] = fitz.Point(pt)
                if g["genre"] == "lasso":
                    g["points"].append(fitz.Point(pt))
                self.update()
                return
            if g["genre"] == "champ":
                r = fitz.Rect(g["rect0"])
                if g["mode"] == "redim":
                    ax = g.get("axes", "xy")
                    if "x" in ax:
                        r.x1 = max(r.x0 + 6, r.x1 + d.x)
                    if "y" in ax:
                        r.y1 = max(r.y0 + 6, r.y1 + d.y)
                elif abs(d.x) + abs(d.y) > 1.5:
                    r = r + (d.x, d.y, d.x, d.y)
                else:
                    return
                g["fantome"] = r
                self.update()
                return
            if g["genre"] == "zone":
                g["fantome"] = fitz.Rect(g["debut"], pt).normalize()
            elif g["genre"] == "deplacer":
                if abs(d.x) + abs(d.y) > 2:
                    g["fantome"] = g["rect0"] + (d.x, d.y, d.x, d.y)
            elif g["genre"] == "redim":
                r = fitz.Rect(g["rect0"])
                if g["coin"] in (1, 3):
                    r.x1 += d.x
                else:
                    r.x0 += d.x
                if o.objet.get("garder_proportions", True):
                    k = r.width / max(1, g["rect0"].width)
                    if g["coin"] in (2, 3):
                        r.y1 = r.y0 + g["rect0"].height * k
                    else:
                        r.y0 = r.y1 - g["rect0"].height * k
                else:
                    if g["coin"] in (2, 3):
                        r.y1 += d.y
                    else:
                        r.y0 += d.y
                g["fantome"] = r.normalize()
            self.update()
            return
        if o.mode is None and e.buttons() & Qt.LeftButton and o.selection:
            o.etendre_selection(self.num, pt)
            return
        # curseurs
        self.survol = pt
        if self.toolTip() and not (o.mode in (None, "formulaire", "signer_num", "champ_signature")
                                   and o.champ_sous(self.num, pt)):
            self.setToolTip("")
        if self._sur_rotation(e.position()):
            self.setCursor(Qt.PointingHandCursor)
            self.setToolTip(_("Glissez pour tourner (Maj : par pas de 15°) ; clic droit : 90°"))
        elif self._sur_poignee(e.position()) is not None:
            self.setCursor(Qt.SizeFDiagCursor)
        elif o.mode == "formulaire" and self._bord_champ(e.position())[0] is not None:
            wb, axes = self._bord_champ(e.position())
            self.setCursor({"xy": Qt.SizeFDiagCursor, "x": Qt.SizeHorCursor, "y": Qt.SizeVerCursor}[axes])
            self.setToolTip(_("Glissez pour agrandir ou réduire « {nom} »", nom=wb.field_name))
        elif o.mode in (None, "formulaire", "signer_num", "champ_signature") and o.champ_sous(self.num, pt):
            w_ = o.champ_sous(self.num, pt)
            re_ = self.vers_ecran(w_.rect)
            coin = abs(e.position().x() - re_.right()) < 9 and abs(e.position().y() - re_.bottom()) < 9
            if o.mode == "formulaire":
                self.setCursor(Qt.SizeAllCursor)
                self.setToolTip(_("« {nom} » : glissez pour déplacer, coin en bas à droite pour agrandir ; "
                                  "double-clic : propriétés ; clic droit : plus d'options", nom=w_.field_name))
            else:
                self.setCursor(Qt.PointingHandCursor)
                if w_.field_type == fitz.PDF_WIDGET_TYPE_SIGNATURE:
                    self.setToolTip(_("Signature : cliquez pour voir qui a signé") if w_.is_signed else
                                    _("Cliquez pour signer avec votre identité numérique"))
                elif o.champ_verrouille(w_):
                    self.setToolTip(_("Champ verrouillé par une signature"))
                elif w_.field_type == fitz.PDF_WIDGET_TYPE_BUTTON:
                    self.setToolTip(_("Bouton « {nom} »", nom=w_.button_caption or w_.field_name))
                else:
                    self.setToolTip((w_.field_label or w_.field_name) +
                                    ("  (" + _("obligatoire") + ")" if w_.field_flags & fitz.PDF_FIELD_IS_REQUIRED else ""))
        elif o.objet_sous(self.num, pt, survol=True):
            self.setToolTip("")
            self.setCursor(Qt.SizeAllCursor)
        elif o.mode in ("poser", "ajout_texte", "ajout_image", "lien", "recadrer", "biffer", "formulaire",
                        "signer_num", "champ_signature"):
            self.setCursor(Qt.CrossCursor)
        elif o.mode is None and o.mot_sous(self.num, pt) is not None:
            self.setCursor(Qt.IBeamCursor)
        else:
            self.setCursor(Qt.ArrowCursor)
        if o.mode in ("modifier", "poser", "ajout_texte", "ajout_image"):
            self.update()

    def mouseReleaseEvent(self, e):
        o = self.o
        if o.mode == "commenter" and e.button() == Qt.LeftButton:
            o.comm_lache(self, self.vers_pdf(e.position()), e.modifiers())
            return
        g, self.glisse = self.glisse, None
        if g:
            if g["genre"] == "rotation":
                if g.get("angle"):
                    o.tourner_objet(g["angle"])
                self.update()
                return
            if g["genre"] == "champ":
                if g["fantome"] is not None:
                    o.placer_champ(self.num, g["xref"], g["fantome"])
                self.update()
                return
            if g["genre"] in ("lasso", "cadre_img"):
                if g["genre"] == "cadre_img":
                    a, b = g["debut"], g["fin"]
                    pts = [fitz.Point(a.x, a.y), fitz.Point(b.x, a.y), fitz.Point(b.x, b.y), fitz.Point(a.x, b.y)]
                else:
                    pts = g["points"]
                o.zone_tracee_image(pts, g["ajouter"])
                self.update()
                return
            if g["genre"] == "zone" and g["fantome"] is not None and g["fantome"].width > 4:
                o.zone_tracee(self.num, g["fantome"])
            elif g["genre"] in ("deplacer", "redim") and g["fantome"] is not None:
                o.appliquer_deplacement(g["fantome"])
            self.update()
            return
        if o.mode is None and o.selection and o.selection["page"] == self.num:
            o.montrer_barre_rapide(self)

    def mouseDoubleClickEvent(self, e):
        pt = self.vers_pdf(e.position())
        o = self.o
        if o.mode == "mesure":
            if e.button() == Qt.LeftButton:
                o.finir_mesure()
            return
        if o.mode == "formulaire" and o.champ_sous(self.num, pt):
            w_ = o.champ_sous(self.num, pt)
            o.proprietes_champ(self.num, w_)
            return
        if o.mode == "modifier":
            if self.ouvrir_paragraphe(pt):
                return
        obj = o.objet_sous(self.num, pt)
        if obj and obj["type"] == "annot":
            o.editer_annotation(obj)

    def keyPressEvent(self, e):
        if self.o.mode == "mesure":
            if e.key() in (Qt.Key_Return, Qt.Key_Enter):
                self.o.finir_mesure()
                return
            if e.key() == Qt.Key_Backspace and self.o.annuler_point_mesure():
                return
            if e.key() == Qt.Key_Escape:
                if not self.o.abandonner_mesure():
                    self.o.changer_mode(None)
                return
        fleches = {Qt.Key_Left: (-1, 0), Qt.Key_Right: (1, 0), Qt.Key_Up: (0, -1), Qt.Key_Down: (0, 1)}
        if e.key() in fleches and self.o.mode == "formulaire" and self.o.champ_choisi:
            w_ = self.o._widget(self.o.champ_choisi)
            if w_ is not None:                     # fleches : deplacer (Maj : de 10) ; Ctrl : agrandir / reduire
                pas = 10 if e.modifiers() & Qt.ShiftModifier else 1
                dx, dy = fleches[e.key()][0] * pas, fleches[e.key()][1] * pas
                r = fitz.Rect(w_.rect)
                r = (fitz.Rect(r.x0, r.y0, max(r.x0 + 6, r.x1 + dx), max(r.y0 + 6, r.y1 + dy))
                     if e.modifiers() & Qt.ControlModifier else r + (dx, dy, dx, dy))
                self.o.placer_champ(self.o.champ_choisi[0], w_.xref, r)
                return
        if e.key() in (Qt.Key_Delete, Qt.Key_Backspace) and self.o.mode == "formulaire" and self.o.champ_choisi:
            self.o.supprimer_champ()
        elif e.key() in (Qt.Key_Delete, Qt.Key_Backspace) and self.o.objet:
            self.o.supprimer()
        elif e.key() == Qt.Key_Escape:
            self.o.choisir_objet(None)
            self.o.changer_mode(None if self.o.mode != "modifier" else "modifier")
        else:
            super().keyPressEvent(e)

    def ouvrir_saisie_champ(self, w):
        """Zone de saisie posee sur le champ ; Entree ou clic ailleurs : la valeur est ecrite dans le PDF."""
        from PySide6.QtWidgets import QLineEdit, QPlainTextEdit, QComboBox
        r = self.vers_ecran(w.rect).toRect()
        n, xref = self.num, w.xref
        multi = bool(w.field_flags & fitz.PDF_TX_FIELD_IS_MULTILINE) if w.field_type == fitz.PDF_WIDGET_TYPE_TEXT else False
        regles = self.o.regles_champ(w)
        fmt = regles.get("format") or {}
        qt_date = {"dd/mm/yyyy": "dd/MM/yyyy", "dd/mm/yy": "dd/MM/yy", "dd.mm.yyyy": "dd.MM.yyyy",
                   "yyyy-mm-dd": "yyyy-MM-dd", "mm/dd/yyyy": "MM/dd/yyyy", "d/m/yyyy": "d/M/yyyy"}.get(fmt.get("date"))
        if w.field_type == fitz.PDF_WIDGET_TYPE_TEXT and fmt.get("genre") == "date":
            from .formulaire_doc import SaisieDate
            self.saisie = SaisieDate(self, self.o, n, xref, fmt.get("date") or "dd/mm/yyyy", w.field_value or "",
                                     self.mapToGlobal(r.bottomLeft()))
            return
        if False:
            pass
        elif w.field_type in (fitz.PDF_WIDGET_TYPE_COMBOBOX, fitz.PDF_WIDGET_TYPE_LISTBOX):
            ed = QComboBox(self)
            ed.addItem("")                          # vide d'abord : rien n'est choisi a votre place
            ed.addItems([c if isinstance(c, str) else c[0] for c in (w.choice_values or [])])
            if w.field_type == fitz.PDF_WIDGET_TYPE_COMBOBOX and w.field_flags & fitz.PDF_CH_FIELD_IS_EDIT:
                ed.setEditable(True)
                ed.lineEdit().returnPressed.connect(lambda: (self.o.valeur_champ(n, xref, ed.currentText()), ed.deleteLater()))
            ed.setCurrentText(w.field_value or "")
            ed.activated.connect(lambda _i: (self.o.valeur_champ(n, xref, ed.currentText()), ed.deleteLater()))
        elif multi:
            ed = QPlainTextEdit(self)
            ed.setPlainText(w.field_value or "")
            ed.focusOutEvent = lambda ev: (self.o.valeur_champ(n, xref, ed.toPlainText()), ed.deleteLater())
        else:
            ed = QLineEdit(self)
            ed.setText(w.field_value or "")
            fini = []

            def valider():
                if not fini:
                    fini.append(1)
                    self.o.valeur_champ(n, xref, ed.text())
                    ed.deleteLater()
            ed.returnPressed.connect(valider)
            ed.editingFinished.connect(valider)
        ed.setGeometry(r.adjusted(-1, -1, 1, 1))
        ed.setStyleSheet("background:#ffffff;border:1.5px solid #0f6cbd")
        ed.show()
        ed.setFocus()
        self.saisie = ed

    def ouvrir_paragraphe(self, pt):
        """Edition du paragraphe sous le point (plusieurs lignes, retours a la ligne). False si pas de texte."""
        try:
            para = Editeur(self.o.doc).paragraphe_a(self.num, pt)
        except Exception:
            para = None
        if not para:
            return False
        if self.editeur:
            self.editeur.valider()
        self.editeur = EditeurParagraphe(self, para)
        return True

    # ---- edition directe dans la page (WYSIWYG)
    def ouvrir_editeur(self, rect, pt, texte=""):
        self.editeur = EditeurEnLigne(self, rect, pt, texte)


class EditeurParagraphe(QFrame):
    """Zone de texte posee sur la page, a la largeur du paragraphe : on tape, Entree fait un retour a la ligne,
    la poignee de droite elargit ou retrecit la zone ; Ctrl+Entree (ou clic ailleurs) valide, Echap annule."""

    def __init__(self, pw, para=None, coin=None):
        from PySide6.QtWidgets import QPlainTextEdit
        super().__init__(pw)
        self.pw, self.para, self.coin = pw, para, coin
        o = pw.o
        e = pw.echelle()
        self.e = e
        self._fini = False
        self.setObjectName("edpar")
        self.setStyleSheet("#edpar{background:transparent}")
        if para:
            r = pw.vers_ecran(fitz.Rect(para["x0"], para["rect"].y0, para["x1"], para["rect"].y1))
            self.taille = para["taille"]
            texte = para["texte"]
        else:
            p = fitz.Point(coin) * pw._mat_texte()
            self.taille = o.format_taille.value()
            r = QRectF(p.x, p.y, 260 * e, self.taille * e * 1.4)
            texte = ""
        self.initial = texte
        self.zone = QPlainTextEdit(self)
        self.zone.setPlainText(texte)
        self.zone.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.zone.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.zone.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.zone.setStyleSheet(self._style_zone(QColor("#000000")))
        self.zone.setPlaceholderText(_("Tapez votre texte"))
        self.zone.document().setDocumentMargin(1)
        f = self._police_affichage()
        f.setPixelSize(max(8, int(self.taille * e * 0.98)))
        self.zone.setFont(f)
        self._police_origine = QFont(f)
        self._orthographe(o.params)
        self.police_choisie = None                    # fichier choisi dans le volet Format pendant la saisie
        self.zone.installEventFilter(self)
        self.poignee = QLabel("↔", self)
        self.poignee.setAlignment(Qt.AlignCenter)
        self.poignee.setCursor(Qt.SizeHorCursor)
        self.poignee.setToolTip(_("Glissez pour élargir ou rétrécir la zone de texte (le bouton … au-dessus ouvre la boîte de dialogue)"))
        self.poignee.setStyleSheet("QLabel{background:#1462c2;color:#fff;border-radius:3px;font-weight:700}")
        self.poignee.installEventFilter(self)
        # aide : posee sur la page mais laisse passer les clics (on peut cliquer la ligne en dessous) ; disparait seule
        self.aide = QLabel(_("Entrée : nouvelle ligne · Ctrl+Entrée ou clic ailleurs : valider · Echap : annuler"), pw)
        self.aide.setStyleSheet("QLabel{background:rgba(20,98,194,200);color:#fff;font-size:10px;padding:1px 6px;border-radius:3px}")
        self.aide.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.aide.show()
        QTimer.singleShot(6000, lambda: self._fini or self.aide.hide())
        self._barre_format(o, para)
        # la barre suit la partie visible quand on fait defiler la page ou qu'on redimensionne la fenetre
        try:
            for barre in (o.zone.horizontalScrollBar(), o.zone.verticalScrollBar()):
                barre.valueChanged.connect(lambda *_a: self._fini or self._ajuster())
            self._suivi_taille = _SurveilleTaille(o.zone.viewport(), lambda: self._fini or self._ajuster())
        except (AttributeError, RuntimeError):
            pass
        self.largeur = max(80.0, r.width() + 6)
        self.x, self.y = r.x() - 3, r.y() - 3
        self.zone.document().contentsChanged.connect(self._ajuster)
        self._ajuster()
        self.show()
        QTimer.singleShot(0, self._ajuster)
        self.zone.setFocus()
        c = self.zone.textCursor()
        c.movePosition(c.MoveOperation.End)
        self.zone.setTextCursor(c)

    def _orthographe(self, params):
        """Fautes soulignees en rouge ; clic droit : suggestions, ajouter au dictionnaire, activer / couper."""
        from . import orthographe

        def activer():
            if getattr(self.zone, "_surligneur", None) is not None:
                self.zone._surligneur.setDocument(None)
            self.zone._surligneur = None
            if params.get("orthographe", True):
                try:
                    try:
                        contexte = self.pw.o.doc[self.pw.num].get_text()[:3000]
                    except Exception:
                        contexte = ""
                    self.zone._surligneur = orthographe.surligneur(self.zone.document(), params, contexte)
                except Exception:
                    self.zone._surligneur = None
        activer()
        self.zone.setContextMenuPolicy(Qt.CustomContextMenu)

        def menu(pos):
            m = self.zone.createStandardContextMenu()
            if self.zone._surligneur is not None:
                orthographe.menu_correction(self.zone, pos, params, m)
            m.addSeparator()
            a = m.addAction(_("Vérifier l'orthographe pendant la saisie"))
            a.setCheckable(True)
            a.setChecked(bool(params.get("orthographe", True)))

            def basculer(c):
                params["orthographe"] = c
                params.enregistrer()
                activer()
            a.toggled.connect(basculer)
            if self.zone._surligneur is not None:
                def langue(k):
                    params["orthographe_langue"] = k
                    params.enregistrer()
                    activer()
                orthographe.menu_langue(m, params, self.zone._surligneur.langue, langue)
            m.exec(self.zone.mapToGlobal(pos))
        self.zone.customContextMenuRequested.connect(menu)

    def _barre_format(self, o, para):
        """Petite barre au-dessus de la zone : police (du document ou toutes), taille, couleur — appliquees en direct."""
        from PySide6.QtWidgets import QDoubleSpinBox
        from .polices import combo as combo_polices
        self.fmt = QFrame(self.pw)
        self.fmt.setObjectName("fmt")
        self.fmt.setStyleSheet("#fmt{background:#ffffff;border:1px solid #1462c2;border-radius:6px}"
                               "QComboBox,QDoubleSpinBox,QPushButton{font-size:11px}")
        self.fmt.setCursor(Qt.ArrowCursor)              # pas la croix de deplacement de la page au-dessus des reglages
        h = FluxLayout(self.fmt, marge=5, espace=4)       # passe sur deux lignes si la fenetre est etroite
        self.cb_police = combo_polices(self.fmt, automatique=True, doc=o.doc)
        self.cb_police.portee.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.cb_police.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.cb_police.setMinimumContentsLength(26)
        self.cb_police.apercu.connect(self.apercu_police)
        if not para and o.format_police.currentData():
            i = self.cb_police.findData(o.format_police.currentData())
            if i < 0:
                self.cb_police.portee.setCurrentIndex(1)
                i = self.cb_police.findData(o.format_police.currentData())
            self.cb_police.setCurrentIndex(max(0, i))
        h.addWidget(self.cb_police.portee)
        h.addWidget(self.cb_police)
        self.sp_taille = QDoubleSpinBox()
        self.sp_taille.setRange(4, 96)
        self.sp_taille.setDecimals(1)
        self.sp_taille.setSuffix(" pt")
        self.sp_taille.setValue(round(self.taille, 1))
        self.taille_depart = round(self.taille, 1)
        self.sp_taille.valueChanged.connect(self._nouvelle_taille)
        h.addWidget(self.sp_taille)
        coul = None
        if para:
            try:
                sp = next(sp for c, sp in para["lignes"][0]["chars"] if c["c"].strip())
                coul = QColor(f"#{sp['color']:06x}")
            except Exception:
                coul = None
        self.couleur = coul or QColor(o.format_couleur)
        self.couleur_modifiee = not para
        self.b_coul = QPushButton(_("Couleur"))
        self.b_coul.setToolTip(_("Couleur du texte"))
        self.b_coul.clicked.connect(self._choisir_couleur)
        h.addWidget(self.b_coul)
        self._styles(o, para, h)
        b_dlg = QPushButton("...")
        b_dlg.setStyleSheet("QPushButton{padding:2px 6px;font-weight:700}")
        b_dlg.setFixedWidth(36)
        b_dlg.setToolTip(_("Ouvrir la boîte de dialogue (texte, police, taille, couleur)"))
        b_dlg.clicked.connect(self._boite_dialogue)
        h.addWidget(b_dlg)
        b_ia = QPushButton(_("✦ IA"))
        b_ia.setObjectName("b_ia_paragraphe")
        b_ia.setToolTip(_("Corriger ou reformuler ce texte avec l'IA : le résultat remplace le texte dans la zone, "
                          "vous le relisez avant de valider (Ctrl+Z dans la zone revient au texte d'avant)"))
        b_ia.setStyleSheet("QPushButton{color:#4338ca;font-weight:700;padding:2px 8px}")
        m_ia = QMenu(b_ia)
        from .ia_texte import ACTIONS
        for cle, lib in ACTIONS:
            m_ia.addAction(lib, lambda c=cle: self._ia(c))
        b_ia.setMenu(m_ia)
        h.addWidget(b_ia)
        self._maj_couleur()
        self.fmt.show()

    # ---- gras, italique, souligne, barre : ce qui a ete mis par clic droit s'enleve aussi ici
    def _styles(self, o, para, h):
        sp = None
        if para:
            try:
                sp = next(sp for c, sp in para["lignes"][0]["chars"] if c["c"].strip())
            except Exception:
                sp = None
        self._span0 = sp
        nom = (sp or {}).get("font", "").lower()
        fl = (sp or {}).get("flags", 0)
        self.gras_depart = bool(fl & 16) or any(x in nom for x in ("bold", "black", "heavy", "semibold"))
        self.italique_depart = bool(fl & 2) or any(x in nom for x in ("italic", "oblique"))
        self.annots_souligne, self.annots_barre = [], []
        if para:
            zone = fitz.Rect(para["x0"], para["rect"].y0, para["x1"], para["rect"].y1)
            page = o.doc[self.pw.num]
            for a in page.annots(types=(fitz.PDF_ANNOT_UNDERLINE, fitz.PDF_ANNOT_SQUIGGLY, fitz.PDF_ANNOT_STRIKE_OUT)):
                inter = fitz.Rect(a.rect) & zone
                if inter.is_empty or inter.get_area() < 0.3 * max(1.0, fitz.Rect(a.rect).get_area()):
                    continue
                (self.annots_barre if a.type[0] == fitz.PDF_ANNOT_STRIKE_OUT else self.annots_souligne).append(a.xref)
        self.b_styles = {}
        for cle, lib, css, aide, actif in (
                ("gras", "G", "font-weight:800", _("Gras"), self.gras_depart),
                ("italique", "I", "font-style:italic;font-family:serif", _("Italique"), self.italique_depart),
                ("souligne", "S", "text-decoration:underline", _("Souligné (s'enlève aussi s'il a été mis par clic droit)"),
                 bool(self.annots_souligne)),
                ("barre", "B", "text-decoration:line-through", _("Barré (s'enlève aussi s'il a été mis par clic droit)"),
                 bool(self.annots_barre))):
            b = QPushButton(lib)
            b.setCheckable(True)
            b.setChecked(actif)
            b.setFixedWidth(30)
            b.setToolTip(aide)
            b.setStyleSheet("QPushButton{padding:2px 4px;%s} QPushButton:checked{background:#dbe8fb;border:1px solid #1462c2}" % css)
            b.toggled.connect(self._style_change)
            h.addWidget(b)
            self.b_styles[cle] = b

    def _style_change(self, *_a):
        f = self.zone.font()
        f.setBold(self.b_styles["gras"].isChecked())
        f.setItalic(self.b_styles["italique"].isChecked())
        f.setUnderline(self.b_styles["souligne"].isChecked())
        f.setStrikeOut(self.b_styles["barre"].isChecked())
        self.zone.setFont(f)
        self._ajuster()

    def _variante(self, gras, italique):
        """Fichier de la meme police en gras / italique (polices du PC), ou None si ce PC ne l'a pas."""
        from . import polices
        if self.police_choisie:
            d = next((p for p in polices.liste() if p["fichier"] == self.police_choisie), None)
            fam = polices._norme(d["famille"]) if d else ""
        else:
            fam = polices._famille_pdf((self._span0 or {}).get("font", ""))
        familles = [fam] + polices.EQUIVALENTS.get(fam, [])
        for f in familles:
            for p in polices.liste():
                if polices._norme(p["famille"]) == f and p["gras"] == gras and p["italique"] == italique:
                    return p["fichier"]
        return None

    def _appliquer_styles(self, o, police):
        """Avant la reecriture : police en gras / italique si demande. Renvoie (police, message ou None)."""
        g, i = self.b_styles["gras"].isChecked(), self.b_styles["italique"].isChecked()
        if (g, i) == (self.gras_depart, self.italique_depart):
            return police, None
        v = self._variante(g, i)
        if v:
            return v, None
        return police, _("Ce PC n'a pas cette police en {s} : choisissez une autre police dans la liste, "
                         "ou installez la version {s} de la police.",
                         s=(_("gras italique") if g and i else _("gras") if g else _("italique") if i else _("normal")))

    def _souligner_apres(self, o, num):
        """Apres la reecriture : souligne / barre retires, ou remis sur les nouvelles lignes (meme couleur)."""
        page = o.doc[num]
        for cle, xrefs, ajout in (("souligne", self.annots_souligne, page.add_underline_annot),
                                  ("barre", self.annots_barre, page.add_strikeout_annot)):
            voulu = self.b_styles[cle].isChecked()
            if not voulu and not xrefs:
                continue
            couleur, ondule = None, False
            for x in xrefs:
                a = page.load_annot(x)
                if a is None:
                    continue
                couleur = couleur or (a.colors or {}).get("stroke")
                ondule = ondule or a.type[0] == fitz.PDF_ANNOT_SQUIGGLY
                page.delete_annot(a)
            if not voulu:
                continue
            try:
                from moteur.modifier import Editeur as _Ed
                para = _Ed(o.doc).paragraphe_a(num, fitz.Point(self.para["x0"] + 2, self.para["lignes"][0]["base"] - 1)) \
                    if self.para else None
            except Exception:
                para = None
            rects = [fitz.Rect(l["x0"], l["base"] - l.get("taille", self.taille) * 0.85, l["x1"], l["base"] + l.get("taille", self.taille) * 0.25)
                     for l in (para or {}).get("lignes", [])] or ([fitz.Rect(self.para["x0"], self.para["rect"].y0,
                                                                          self.para["x1"], self.para["rect"].y1)] if self.para else [])
            if not rects:
                continue
            if cle == "souligne" and (ondule or (not xrefs and o.params.get("style_souligne") == "ondule")):
                ajout = page.add_squiggly_annot
            a = ajout(rects)
            a.set_info(title=o.params.get("auteur") or o.params["machine"])
            a.set_colors(stroke=couleur or _rgb(o.couleurs_annot()["souligner" if cle == "souligne" else "barrer"]))
            a.update()

    def _ia(self, action):
        """Texte de la zone envoye a l'IA (correction, reformulation...) ; la reponse remplace le texte, annulable."""
        from .ia_texte import transformer
        t = self.zone.textCursor().selectedText().replace("\u2029", "\n") or self.zone.toPlainText()
        r = transformer(self.window(), self.pw.o.params, t, action)
        if r is None:
            return
        c = self.zone.textCursor()
        if not c.hasSelection():
            c.select(c.SelectionType.Document)
        c.beginEditBlock()
        c.insertText(r)
        c.endEditBlock()
        self.zone.setFocus()

    def _boite_dialogue(self):
        """La boite d'avant : texte sur plusieurs lignes, police, taille et couleur, puis valider."""
        from PySide6.QtWidgets import QPlainTextEdit, QDoubleSpinBox, QColorDialog
        from .polices import combo as combo_polices
        d = QDialog(self.window())
        d.setWindowTitle(_('Texte'))
        d.resize(520, 360)
        f = QFormLayout(d)
        f.setRowWrapPolicy(QFormLayout.WrapLongRows)
        texte = QPlainTextEdit(self.zone.toPlainText())
        f.addRow(_('Texte'), texte)
        pol = combo_polices(d, automatique=True, doc=self.pw.o.doc)
        if self.police_choisie:
            i = pol.findData(self.police_choisie)
            if i < 0:
                pol.portee.setCurrentIndex(1)
                i = pol.findData(self.police_choisie)
            pol.setCurrentIndex(max(0, i))
        f.addRow(_('Police'), pol.ligne())
        taille = QDoubleSpinBox()
        taille.setRange(4, 96)
        taille.setSuffix(" pt")
        taille.setValue(self.sp_taille.value())
        f.addRow(_('Taille'), taille)
        coul = [QColor(self.couleur)]
        bc = QPushButton(_("Couleur du texte..."))

        def maj_bc():
            pm = QPixmap(18, 18)
            pm.fill(coul[0])
            bc.setIcon(QIcon(pm))

        def choisir():
            c = QColorDialog.getColor(coul[0], d, _("Couleur du texte"))
            if c.isValid():
                coul[0] = c
                maj_bc()
        maj_bc()
        bc.clicked.connect(choisir)
        f.addRow(_('Couleur'), bc)
        bb = boutons_fr(QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel))
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        f.addRow(bb)
        if d.exec() != QDialog.Accepted:
            return
        self.zone.setPlainText(texte.toPlainText())
        self.sp_taille.setValue(taille.value())
        if coul[0] != self.couleur:
            self.couleur, self.couleur_modifiee = coul[0], True
            self._maj_couleur()
        p = pol.police()
        if (p["fichier"] if p else None) != self.police_choisie:
            self.apercu_police(p)
        self.valider()

    def _nouvelle_taille(self, v):
        self.taille = v
        f = self.zone.font()
        f.setPixelSize(max(8, int(v * self.e * 0.98)))
        self.zone.setFont(f)
        self._ajuster()

    def _choisir_couleur(self):
        from PySide6.QtWidgets import QColorDialog
        c = QColorDialog.getColor(self.couleur, self, _("Couleur du texte"))
        if c.isValid():
            self.couleur, self.couleur_modifiee = c, True
            self._maj_couleur()
        self.zone.setFocus()

    def _maj_couleur(self):
        pm = QPixmap(14, 14)
        pm.fill(self.couleur)
        self.b_coul.setIcon(QIcon(pm))
        self.zone.setStyleSheet(self._style_zone(self.couleur))

    @staticmethod
    def _style_zone(couleur):
        """Zone de saisie bien visible : fond blanc opaque (ou sombre si le texte est clair), cadre bleu marque,
        le texte garde sa vraie couleur (ce que l'on voit est ce qui sera ecrit)."""
        lum = (0.299 * couleur.red() + 0.587 * couleur.green() + 0.114 * couleur.blue()) / 255
        fond = "#ffffff" if lum < 0.62 else "#3a3a3a"
        return ("QPlainTextEdit{background:%s;border:2px solid #1462c2;border-radius:3px;padding:0px;color:%s;"
                "selection-background-color:#9cc3f5;selection-color:#000}" % (fond, couleur.name()))

    def _fermer_annexes(self):
        try:                                            # fermer la liste ne doit plus changer la police choisie
            self.cb_police.apercu.disconnect()
        except (RuntimeError, TypeError):
            pass
        for w in (self.aide, self.fmt):
            w.hide()
            w.deleteLater()

    def apercu_police(self, p):
        """Police survolee ou choisie dans la liste : appliquee tout de suite au texte en cours (WYSIWYG)."""
        if p:
            from .polices import qfont
            f = qfont(p)
        else:
            f = QFont(self._police_origine)
        f.setPixelSize(max(8, int(self.taille * self.e * 0.98)))
        self.zone.setFont(f)
        self.police_choisie = p["fichier"] if p else None
        self._ajuster()

    def _police_affichage(self):
        """Police de l'ecran la plus proche de celle du paragraphe (affichage fidele pendant la saisie)."""
        try:
            o = self.pw.o
            if self.para:
                ed = Editeur(o.doc)
                sp = next(sp for c, sp in self.para["lignes"][0]["chars"] if c["c"].strip())
                p = ed._police_du_span(o.doc[self.pw.num], sp)
                r = ed._police_par_nom(p) if p else None
                if r:
                    from .polices import qfont
                    return qfont({"famille": r.nom, "fichier": r.fichier, "gras": "Bold" in r.nom or (p and p.weight >= 600),
                                  "italique": "Italic" in r.nom, "fournie": True})
            elif o.format_police.currentData():
                from .polices import qfont, liste
                pp = next((x for x in liste() if x["fichier"] == o.format_police.currentData()), None)
                if pp:
                    return qfont(pp)
        except Exception:
            pass
        return QFont()

    def _ajuster(self):
        if not hasattr(self, "largeur") or not hasattr(self, "fmt"):
            return
        doc = self.zone.document()
        doc.setTextWidth(self.largeur - 6)
        lignes = 0                                    # hauteur : nombre de lignes affichees x interligne
        b = doc.begin()
        while b.isValid():
            lignes += max(1, b.layout().lineCount() if b.layout() else 1)
            b = b.next()
        h = int(max(doc.size().height(), lignes * self.zone.fontMetrics().lineSpacing()) + 10)
        self.zone.setGeometry(0, 0, int(self.largeur), h)
        self.poignee.setGeometry(int(self.largeur), 0, 10, h)
        self.aide.adjustSize()
        self.aide.move(int(self.x), int(self.y) + h + 2)
        self.setGeometry(int(self.x), int(self.y), int(self.largeur + 12), h)
        # la barre reste dans la partie visible de la fenetre ; trop etroite, elle passe sur deux lignes
        vis = self.pw.visibleRegion().boundingRect()
        if vis.width() < 50:
            vis = self.pw.rect()
        lay = self.fmt.layout()
        pleine = sum(lay.itemAt(i).sizeHint().width() + lay.spacing() for i in range(lay.count())) + 14
        larg = int(min(pleine, max(160, vis.width() - 8)))
        hb = lay.heightForWidth(larg)
        self.fmt.resize(larg, hb)
        yb = self.y - hb - 3 if self.y - hb - 3 >= vis.top() else self.y + h + self.aide.height() + 4
        x = min(max(self.x, vis.left() + 4), vis.right() - larg - 4)
        self.fmt.move(int(max(0, x)), int(yb))
        self.fmt.raise_()

    def eventFilter(self, obj, ev):
        t = ev.type()
        if obj is self.zone and t == ev.Type.KeyPress:
            if ev.key() == Qt.Key_Escape:
                self.annuler()
                return True
            if ev.key() in (Qt.Key_Return, Qt.Key_Enter) and ev.modifiers() & Qt.ControlModifier:
                self.valider()
                return True
        if obj is self.poignee:
            if t == ev.Type.MouseButtonPress:
                self._tire = (ev.globalPosition().x(), self.largeur)
                return True
            if t == ev.Type.MouseMove and getattr(self, "_tire", None):
                self.largeur = max(60.0, self._tire[1] + ev.globalPosition().x() - self._tire[0])
                self._ajuster()
                return True
            if t == ev.Type.MouseButtonRelease:
                self._tire = None
                return True
        return False

    def annuler(self):
        self._fini = True
        self._fermer_annexes()
        self.pw.editeur = None
        self.hide()
        self.deleteLater()
        self.pw.update()

    def valider(self, *_a, **_k):
        if self._fini:
            return
        self._fini = True
        texte = self.zone.toPlainText().rstrip()
        police_choisie = self.police_choisie
        self._fermer_annexes()
        self.police_choisie = police_choisie
        self.pw.editeur = None
        self.hide()
        self.deleteLater()
        o = self.pw.o
        largeur_pt = (self.largeur - 6) / self.e
        taille = self.sp_taille.value() if abs(self.sp_taille.value() - self.taille_depart) > 0.05 else None
        couleur = self.couleur.getRgbF()[:3] if self.couleur_modifiee else None
        police, avis = self._appliquer_styles(o, self.police_choisie)
        souligne_change = (self.b_styles["souligne"].isChecked() != bool(self.annots_souligne)
                           or self.b_styles["barre"].isChecked() != bool(self.annots_barre))
        if self.para:
            elargi = abs(largeur_pt - (self.para["x1"] - self.para["x0"])) > 2
            if texte != self.initial or elargi or police or taille or couleur:
                if elargi:
                    self.para["x1"] = self.para["x0"] + largeur_pt
                o.modifier_paragraphe(self.pw.num, self.para, texte, taille=taille, couleur=couleur, police=police)
                if self.annots_souligne or self.annots_barre or souligne_change:
                    self._souligner_apres(o, self.pw.num)      # suit le nouveau texte, ou s'enleve
                    o.apres_modif()
            elif souligne_change:
                o.memoriser(_("Souligné / barré"))
                self._souligner_apres(o, self.pw.num)
                o.apres_modif()
            if avis:
                o.message(avis)
        elif texte.strip():
            o.ajouter_paragraphe(self.pw.num, self.coin, texte, largeur_pt, taille=self.sp_taille.value(),
                                 couleur=self.couleur.getRgbF()[:3], police=police)
        self.pw.update()


class EditeurEnLigne(QWidget):
    """Champ de saisie pose sur la page, a la taille du texte ; bouton … pour la boite de dialogue."""

    def __init__(self, pw, rect, pt, texte):
        super().__init__(pw)
        self.pw, self.rect, self.pt, self.initial = pw, rect, pt, texte.rstrip()
        o = pw.o
        self.taille = o.format_taille.value() if rect is None else None
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(2)
        self.champ = QLineEdit(self.initial)
        e = pw.echelle()
        if rect is not None:
            r = pw.vers_ecran(rect)
            taille_px = max(9, r.height() * 0.78)
            x, y, w, hh = r.x(), r.y(), max(r.width() + 40, 120), r.height() + 6
        else:
            taille_px = max(9, self.taille * e * 0.95)
            p = fitz.Point(pt) * pw._mat_texte()
            x, y, w, hh = p.x, p.y - taille_px * 0.15, 360, taille_px * 1.6
        f = QFont()
        f.setPixelSize(int(taille_px))
        self.champ.setFont(f)
        self.champ.setStyleSheet("QLineEdit{background:rgba(234,242,253,235);border:1.5px solid #1462c2;border-radius:3px;padding:0 3px}")
        h.addWidget(self.champ, 1)
        plus = QToolButton()
        plus.setText("…")
        plus.setToolTip(_('Ouvrir la boîte de dialogue (texte, taille, couleur)'))
        plus.clicked.connect(self.dialogue)
        h.addWidget(plus)
        self.setGeometry(int(x - 3), int(y - 3), int(w + 30), int(hh))
        self.champ.returnPressed.connect(self.valider)
        self.champ.installEventFilter(self)
        self.show()
        self.champ.setFocus()
        self.champ.selectAll() if rect is None else self.champ.setCursorPosition(len(self.initial))
        self._fini = False

    def eventFilter(self, obj, ev):
        if ev.type() == ev.Type.KeyPress and ev.key() == Qt.Key_Escape:
            self.annuler()
            return True
        return False

    def dialogue(self):
        d = DialogueTexte(self.pw.o, self.champ.text(), self.pw.o)
        if d.exec() == QDialog.Accepted:
            self.champ.setText(d.texte.text())
            self.valider(d.taille.value(), d.couleur.getRgbF()[:3] if d.couleur_modifiee else None, d.police())

    def annuler(self):
        self._fini = True
        self.pw.editeur = None
        self.hide()
        self.deleteLater()
        self.pw.update()

    def valider(self, taille=None, couleur=None, police=None):
        if self._fini:
            return
        self._fini = True
        texte = self.champ.text()
        self.pw.editeur = None
        self.hide()
        self.deleteLater()
        o = self.pw.o
        if self.rect is not None:
            if texte.rstrip() != self.initial or taille or couleur:
                o.modifier_ligne_texte(self.pw.num, self.rect, texte, taille, couleur)
        elif texte.strip():
            t = taille or self.taille
            # self.pt est le coin haut gauche ; le moteur attend la ligne de base
            o.ajouter_texte(self.pw.num, fitz.Point(self.pt.x, self.pt.y + t * 0.8), texte, t, couleur, police)
        self.pw.update()


class DialogueTexte(QDialog):
    def __init__(self, parent, texte, onglet):
        super().__init__(parent)
        self.setWindowTitle(_('Texte'))
        f = QFormLayout(self)
        self.texte = QLineEdit(texte)
        self.texte.setMinimumWidth(420)
        f.addRow(_('Texte'), self.texte)
        self.taille = QDoubleSpinBox()
        self.taille.setRange(4, 96)
        self.taille.setValue(onglet.format_taille.value())
        self.taille.setSuffix(" pt")
        f.addRow(_('Taille'), self.taille)
        self.couleur, self.couleur_modifiee = QColor("#000000"), False
        b = QPushButton(_('Choisir...'))
        b.clicked.connect(self._coul)
        f.addRow(_('Couleur'), b)
        from .polices import combo as combo_polices
        self.combo = combo_polices(self, doc=onglet.doc)
        f.addRow(_('Police'), self.combo.ligne())

        def apercu(p):
            from .polices import qfont
            self.texte.setFont(qfont(p, 11) if p else QFont())
        self.combo.apercu.connect(apercu)
        bb = boutons_fr(QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)

    def _coul(self):
        c = QColorDialog.getColor(self.couleur, self)
        if c.isValid():
            self.couleur, self.couleur_modifiee = c, True

    def police(self):
        return self.combo.currentData()


# ================================================================ barre rapide
def _rgb(c):
    q = QColor(c)
    return (q.redF(), q.greenF(), q.blueF())


class BarreRapide(QFrame):
    """Actions rapides sur le texte selectionne (comme Office et Acrobat)."""

    def __init__(self, onglet, parent):
        super().__init__(parent)
        self.o = onglet
        self.setObjectName("barre")
        self.setStyleSheet("#barre{background:#2b2b2b;border-radius:10px;border:1px solid #111}"
                           "QToolButton{color:#fff;padding:3px 7px;border-radius:6px;font-size:11px}"
                           "QToolButton:hover{background:#4a4a4a}")
        h = QHBoxLayout(self)
        h.setContentsMargins(6, 4, 6, 4)
        h.setSpacing(2)
        for ic, txt, court, f in [("surligner", _('Surligner'), _('Surligner'), lambda: self.o.annoter("surligner")),
                                  ("souligner", _('Souligner'), _('Souligner'), lambda: self.o.annoter("souligner")),
                                  ("barrer", _('Barrer'), _('Barrer'), lambda: self.o.annoter("barrer")),
                                  ("commentaire", _('Note'), _('Note'), lambda: self.o.annoter("note")),
                                  ("copier", _('Copier'), _('Copier'), self.o.copier),
                                  ("modifier", _('Modifier le texte (zone de texte)'), _('Modifier'), self.o.modifier_selection),
                                  ("biffer", _('Biffer (effacer pour de vrai)'), _('Biffer'), self.o.biffer)]:
            b = QToolButton()
            b.setIcon(icone(ic, "#ffffff", 48))
            b.setIconSize(QSize(22, 22))
            b.setText(court)
            b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            b.setToolTip(txt)
            b.setAccessibleName(txt)
            b.setAutoRaise(True)
            b.clicked.connect(f)
            b.clicked.connect(self.hide)
            h.addWidget(b)
        self.b_couleur = QToolButton()
        self.b_couleur.setText(_('Couleur'))
        self.b_couleur.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.b_couleur.setIconSize(QSize(22, 22))
        self.b_couleur.setToolTip(_("Couleur et style du surlignage, du soulignement et du barré"))
        self.b_couleur.clicked.connect(lambda: self.o.menu_style_annotations(self.b_couleur.mapToGlobal(self.b_couleur.rect().bottomLeft())))
        h.addWidget(self.b_couleur)
        self.maj_couleur()
        self.hide()

    def maj_couleur(self):
        from PySide6.QtGui import QPixmap, QPainter
        pm = QPixmap(22, 22)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        c = self.o.couleurs_annot()
        for i, g in enumerate(("surligner", "souligner", "barrer")):
            p.fillRect(2 + i * 7, 4, 6, 14, QColor(c[g]))
        p.end()
        self.b_couleur.setIcon(QIcon(pm))


# ================================================================ vignettes / organiser
class Loupe(QLabel):
    """Apercu agrandi d'une page au survol d'une vignette ; la molette zoome autour du pointeur."""

    def __init__(self):
        super().__init__(None, Qt.ToolTip | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setStyleSheet("QLabel{background:#fff;border:1px solid #9a9a9a;border-radius:4px}")
        self.facteur = 1.0


class BoutonVolet(QPushButton):
    """Bouton des volets dont le texte passe a la ligne au lieu d'etre coupe quand le volet est etroit."""

    def __init__(self, texte, aide=None, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 5, 8, 5)
        self.lib = QLabel(texte)
        self.lib.setWordWrap(True)
        self.lib.setAlignment(Qt.AlignCenter)
        self.lib.setAttribute(Qt.WA_TransparentForMouseEvents)
        lay.addWidget(self.lib)
        self.setToolTip(aide or texte)
        self.setMinimumWidth(40)

    def setText(self, t):
        self.lib.setText(t)

    def text(self):
        return self.lib.text()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        h = self.lib.heightForWidth(max(10, self.width() - 16)) + 12
        if self.minimumHeight() != h:
            self.setMinimumHeight(h)

    def sizeHint(self):
        return QSize(120, self.lib.sizeHint().height() + 12)


class _SurveilleTaille(QObject):
    def __init__(self, w, rappel):
        super().__init__(w)
        self.rappel = rappel
        w.installEventFilter(self)

    def eventFilter(self, obj, ev):
        if ev.type() in (ev.Type.Resize, ev.Type.Show):
            QTimer.singleShot(0, self.rappel)
        return False


class FluxLayout(QLayout):
    """Disposition « en flux » : les elements vont a la ligne quand la place manque (barre d'outils sur plusieurs
    lignes quand la fenetre est etroite, au lieu d'icones cachees)."""

    def __init__(self, parent=None, marge=6, espace=2):
        super().__init__(parent)
        self._items = []
        self.droite = None                            # element colle a droite (volet), hors du flux
        self.setContentsMargins(marge, 2, marge, 2)
        self.setSpacing(espace)

    def addItem(self, item):
        self._items.append(item)

    def set_droite(self, w):
        from PySide6.QtWidgets import QWidgetItem
        if w is None:
            self.droite = None
        else:
            self.addChildWidget(w)
            self.droite = QWidgetItem(w)
        self.invalidate()

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, largeur):
        return self._placer(QRect(0, 0, largeur, 0), simuler=True)

    def setGeometry(self, r):
        super().setGeometry(r)
        self._placer(r, simuler=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        t = QSize()
        for it in self._items:
            t = t.expandedTo(it.minimumSize())
        m = self.contentsMargins()
        return t + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _placer(self, r, simuler):
        m = self.contentsMargins()
        zone = r.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x, y, haut_ligne = zone.x(), zone.y(), 0
        e = self.spacing()
        bas_droite = zone.y()
        if self.droite is not None and not self.droite.widget().isHidden():
            td = self.droite.sizeHint()
            if not simuler:
                self.droite.setGeometry(QRect(QPoint(zone.right() - td.width() + 1, zone.y()), td))
            zone = zone.adjusted(0, 0, -(td.width() + e), 0)
            bas_droite = zone.y() + td.height()
        for it in self._items:
            if it.widget() is not None and it.widget().isHidden():
                continue
            t = it.sizeHint()
            if x + t.width() > zone.right() + 1 and haut_ligne > 0:
                x = zone.x()
                y += haut_ligne + e
                haut_ligne = 0
            if not simuler:
                it.setGeometry(QRect(QPoint(x, y), t))
            x += t.width() + e
            haut_ligne = max(haut_ligne, t.height())
        return max(y + haut_ligne, bas_droite) - r.y() + m.bottom()


def defilable(w):
    """Barre d'outils qui defile horizontalement quand la fenetre est etroite (au lieu d'empecher de la reduire)."""
    from PySide6.QtWidgets import QScrollArea, QFrame as _F
    z = QScrollArea()
    z.setWidget(w)
    z.setWidgetResizable(True)
    z.setFrameShape(_F.NoFrame)
    z.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    z.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    z.setStyleSheet("QScrollArea{background:transparent} QScrollBar:horizontal{height:6px}")

    def ajuster():
        z.setFixedHeight(w.sizeHint().height() + (8 if z.horizontalScrollBar().isVisible() else 0))
    z.horizontalScrollBar().rangeChanged.connect(lambda *_a: ajuster())
    ajuster()
    return z


class GrillePages(QListWidget):
    """Vignettes reordonnables par glisser-deposer (colonne ou grille), avec defilement automatique pres
    des bords pendant le glisser, et loupe au survol (molette = zoom de la loupe)."""
    ordre_change = Signal(list)
    vignettes_agrandies = Signal(int)
    HAUTEUR_LOUPE = 520

    def __init__(self, grille=False):
        super().__init__()
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setAutoScroll(True)
        self.setAutoScrollMargin(48)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setViewMode(QListWidget.ListMode)          # le mode « icones » de Qt deplace les vignettes a sa facon
        self.grille = grille
        from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem

        class Dessus(QStyledItemDelegate):               # numero de page sous la vignette
            def initStyleOption(self, opt, index):
                super().initStyleOption(opt, index)
                opt.decorationPosition = QStyleOptionViewItem.Top
                opt.displayAlignment = Qt.AlignHCenter | Qt.AlignTop
        self.setItemDelegate(Dessus(self))
        if grille:
            self.setFlow(QListWidget.LeftToRight)
            self.setWrapping(True)
            self.setResizeMode(QListWidget.Adjust)
            self.setIconSize(QSize(150, 200))
            self.setGridSize(QSize(176, 226))
            self.setUniformItemSizes(True)
        else:
            self.setIconSize(QSize(96, 128))
            self.setSpacing(4)
        self.rendu = None                  # rendu(n, hauteur_px) -> QImage, fourni par l'onglet
        self.loupe = Loupe()
        self._item_loupe, self._rel = None, (0.5, 0.5)
        self._minuterie = QTimer(self)
        self._minuterie.setSingleShot(True)
        self._minuterie.timeout.connect(self._montrer_loupe)
        self._defil = QTimer(self)
        self._defil.timeout.connect(self._defiler)
        self._vitesse = 0
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if not self.grille:                        # le volet s'elargit : les vignettes grandissent avec lui
            l = max(70, min(420, self.viewport().width() - 18))
            if abs(l - self.iconSize().width()) > 4:
                self.setIconSize(QSize(l, int(l * 1.42)))
                self.vignettes_agrandies.emit(l)

    # ---------------------------------------------------------------- loupe
    def _cacher_loupe(self):
        try:                              # a la fermeture, Qt peut avoir deja detruit la loupe
            self._minuterie.stop()
            self.loupe.hide()
            self.loupe.facteur = 1.0
        except RuntimeError:
            pass

    def mouseMoveEvent(self, e):
        if e.buttons():
            self._cacher_loupe()
            return super().mouseMoveEvent(e)
        it = self.itemAt(e.position().toPoint())
        if it is not self._item_loupe:
            self._cacher_loupe()
            self._item_loupe = it
            if it is not None and self.rendu:
                self._minuterie.start(350)
        if it is not None:
            r = self.visualItemRect(it)
            ic = QRect(r.topLeft(), self.iconSize()) if not self.grille else r
            self._rel = (min(1, max(0, (e.position().x() - ic.x()) / max(1, ic.width()))),
                         min(1, max(0, (e.position().y() - ic.y()) / max(1, ic.height()))))
            if self.loupe.isVisible():
                self._montrer_loupe()
        super().mouseMoveEvent(e)

    def leaveEvent(self, e):
        self._cacher_loupe()
        self._item_loupe = None
        super().leaveEvent(e)

    def hideEvent(self, e):
        self._cacher_loupe()
        super().hideEvent(e)

    def wheelEvent(self, e):
        if self.loupe.isVisible():
            k = 1.25 ** (e.angleDelta().y() / 120)
            self.loupe.facteur = min(5.0, max(1.0, self.loupe.facteur * k))
            self._montrer_loupe()
            e.accept()
            return
        super().wheelEvent(e)

    def _montrer_loupe(self):
        it = self._item_loupe
        if it is None or not self.rendu:
            return
        n = it.data(Qt.UserRole)
        H = self.HAUTEUR_LOUPE
        f = self.loupe.facteur
        img = self.rendu(n, int(H * f))
        if img is None:
            return
        if f > 1.0:                                   # zoom : on recadre autour du pointeur
            w, h = int(img.width() / f), int(img.height() / f)
            x = int(self._rel[0] * img.width() - w / 2)
            y = int(self._rel[1] * img.height() - h / 2)
            x, y = max(0, min(img.width() - w, x)), max(0, min(img.height() - h, y))
            img = img.copy(x, y, w, h)
        self.loupe.setPixmap(QPixmap.fromImage(img))
        self.loupe.adjustSize()
        from PySide6.QtGui import QCursor
        pos = QCursor.pos() + QPoint(28, -self.loupe.height() // 3)
        ecran = self.screen().availableGeometry() if self.screen() else None
        if ecran is not None:
            if pos.x() + self.loupe.width() > ecran.right():
                pos.setX(QCursor.pos().x() - self.loupe.width() - 28)
            pos.setY(max(ecran.top(), min(pos.y(), ecran.bottom() - self.loupe.height())))
        self.loupe.move(pos)
        self.loupe.show()

    # ---------------------------------------------------------------- glisser : defilement automatique
    def dragMoveEvent(self, ev):
        super().dragMoveEvent(ev)
        p = ev.position().toPoint()
        zone = 60
        h = self.viewport().height()
        if p.y() < zone:
            self._vitesse = -max(4, (zone - p.y()) // 2)
        elif p.y() > h - zone:
            self._vitesse = max(4, (p.y() - (h - zone)) // 2)
        else:
            self._vitesse = 0
        if self._vitesse and not self._defil.isActive():
            self._defil.start(30)
        elif not self._vitesse:
            self._defil.stop()
        ev.setDropAction(Qt.MoveAction)
        ev.accept()

    def dragEnterEvent(self, ev):
        self._cacher_loupe()
        super().dragEnterEvent(ev)
        ev.accept()

    def dragLeaveEvent(self, ev):
        self._defil.stop()
        super().dragLeaveEvent(ev)

    def _defiler(self):
        b = self.verticalScrollBar()
        b.setValue(b.value() + self._vitesse)

    def dropEvent(self, ev):
        self._defil.stop()
        # reordonnancement fait a la main : fiable en colonne comme en grille
        cible = self.indexAt(ev.position().toPoint()).row()
        choisis = sorted(self.row(i) for i in self.selectedItems())
        if not choisis:
            return
        ordre = [self.item(i).data(Qt.UserRole) for i in range(self.count())]
        if cible < 0:
            cible = len(ordre)
        else:
            r = self.visualItemRect(self.item(cible))
            p = ev.position().toPoint()
            apres = p.x() > r.center().x() if self.grille else p.y() > r.center().y()
            cible += 1 if apres else 0
        bouges = [ordre[i] for i in choisis]
        reste = [x for i, x in enumerate(ordre) if i not in choisis]
        pos = cible - sum(1 for i in choisis if i < cible)
        nouvel = reste[:pos] + bouges + reste[pos:]
        ev.setDropAction(Qt.IgnoreAction)
        ev.accept()
        if nouvel != ordre:
            self.ordre_change.emit(nouvel)


# ================================================================ onglet
def _signe(doc):
    """Le document contient-il au moins une signature numerique apposee ?"""
    try:
        if not doc.get_sigflags() > 0:
            return False
        for p in doc:
            for w in p.widgets(types=[fitz.PDF_WIDGET_TYPE_SIGNATURE]) or []:
                if w.is_signed:
                    return True
    except Exception:                                     # noqa: BLE001
        pass
    return False


class OngletDocument(MixinSignature, MixinFormulaire, MixinMesure, MixinCommentaires, MixinSignets, QWidget):
    titre_change = Signal()
    outil_demande = Signal(str)
    statut = Signal(str)

    def __init__(self, params, chemin=None, doc=None, nom=None, biblio=None):
        super().__init__()
        self.params, self.biblio = params, biblio
        self.chemin = chemin
        self.mdp_pdf = None
        self.octets_signes = None  # document signe : le fichier tel qu'enregistre ; on ne fait qu'y ajouter
        converti = False
        if doc is None:
            with open(chemin, "rb") as f:
                donnees = f.read()
            if donnees[:5] == b"%PDF-" or b"%PDF-" in donnees[:1024]:
                doc = fitz.open(stream=donnees, filetype="pdf")
            else:
                # image (JPG, PNG, TIFF...) ou autre format lu par le moteur : converti en PDF des l'ouverture,
                # sinon les outils PDF (Modifier, signer...) feraient planter le moteur
                brut = fitz.open(stream=donnees, filetype=os.path.splitext(chemin)[1].lstrip(".").lower() or None)
                doc = brut if brut.is_pdf else fitz.open("pdf", brut.convert_to_pdf())
                converti = not brut.is_pdf
            self.poids_initial = len(donnees)
            if not converti and _signe(doc):
                self.octets_signes = donnees
        else:
            self.poids_initial = 0
        if converti:                                  # l'original n'est jamais ecrase : enregistre en .pdf
            nom = nom or os.path.splitext(os.path.basename(chemin))[0] + ".pdf"
            self.dossier_propose = os.path.dirname(chemin)     # « Enregistrer » propose le dossier de l'image
            chemin = None
            self.chemin = None
        self.doc = doc
        self.nom = nom or os.path.basename(chemin or _('Sans titre.pdf'))
        self.modifie = chemin is None
        self.zoom = params.get("zoom", 1.25)
        self.rotation_vue = {}
        self.selection = None
        self.objet = None
        self.a_poser = None
        self.resultats, self.resultat_courant = [], None
        self.mode = None
        self.annulations, self.retablissements = [], []
        self.chiffrement = None
        self.chiffrement_change = False
        self._cache_lignes, self._cache_mots, self._cache_images = {}, {}, {}
        self.objets_pdf = {}       # xref annotation -> (pdf, nom, genre) pour copier/coller
        self.distant = None        # {"compte", "cle", "chemin", "lieu"} si ouvert depuis un NAS, un FTP, un Drive
        self._construire()
        QTimer.singleShot(0, self._verifier_signatures_tard)
        self.maj_historique()

    # ------------------------------------------------------------ interface
    def _construire(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.barre = self._barre_outils()
        v.addWidget(self.barre)
        self._zone_bandeau = defilable(self._bandeau_modifier())
        self._zone_bandeau.hide()
        v.addWidget(self._zone_bandeau)
        self.bandeau_simple = QLabel()
        self.bandeau_simple.setStyleSheet("background:#f1ebfc;color:#3f2380;padding:8px 16px;border-bottom:1px solid #ddd0f6")
        self.bandeau_simple.hide()
        v.addWidget(self.bandeau_simple)
        self.bandeau_biffer = QFrame()
        self.bandeau_biffer.setObjectName("bandeaubiffer")
        self.bandeau_biffer.setStyleSheet("QFrame#bandeaubiffer{background:#2b2b2b;border-bottom:1px solid #111}"
                                          "QLabel{color:#fff} QPushButton{padding:4px 12px}")
        hb = QHBoxLayout(self.bandeau_biffer)
        hb.setContentsMargins(16, 6, 16, 6)
        self.lbl_biffer = QLabel()
        hb.addWidget(self.lbl_biffer, 1)
        self.b_appliquer_biffage = QPushButton(_("Appliquer le biffage"))
        self.b_appliquer_biffage.setProperty("primaire", True)
        self.b_appliquer_biffage.clicked.connect(self.appliquer_biffage)
        hb.addWidget(self.b_appliquer_biffage)
        b = QPushButton(_("Effacer les marques"))
        b.clicked.connect(lambda: (self.marques_biffage.clear(), self._maj_biffer()))
        hb.addWidget(b)
        b = QPushButton(_("Fermer"))
        b.clicked.connect(lambda: self.changer_mode(None))
        hb.addWidget(b)
        self.bandeau_biffer.hide()
        v.addWidget(self.bandeau_biffer)
        self.bandeau_form = QFrame()
        self.bandeau_form.setObjectName("bandeauform")
        self.bandeau_form.setStyleSheet("QFrame#bandeauform{background:#fdf1e2;border-bottom:1px solid #f0d3a8}"
                                        "QLabel{color:#5c3400} QPushButton{padding:4px 12px}")
        hf = QHBoxLayout(self.bandeau_form)
        hf.setContentsMargins(16, 6, 16, 6)
        self.lbl_form = QLabel()
        self.lbl_form.setWordWrap(True)
        hf.addWidget(self.lbl_form, 1)
        hf.addWidget(QLabel(_("Tracer :")))
        from PySide6.QtWidgets import QComboBox as _QCB
        self.type_trace = _QCB()
        self.type_trace.setObjectName("type_trace")
        from .formulaire_doc import bulles_types
        for k_, t_ in types_a_tracer():
            self.type_trace.addItem(t_, k_)
            if k_ in bulles_types():
                self.type_trace.setItemData(self.type_trace.count() - 1, bulles_types()[k_], Qt.ToolTipRole)
        self.type_trace.setToolTip(_("Type du champ que vous tracez (Automatique : petit carré = case à cocher)"))
        hf.addWidget(self.type_trace)
        b = QPushButton(_("Détecter les champs"))
        b.clicked.connect(self.detecter_champs)
        hf.addWidget(b)
        b = QPushButton(_("Ordre de tabulation..."))
        b.clicked.connect(self.ordre_tabulation)
        hf.addWidget(b)
        b = QPushButton(_("Terminer"))
        b.setProperty("primaire", True)
        b.clicked.connect(lambda: self.changer_mode(None))
        hf.addWidget(b)
        self.bandeau_form.hide()
        v.addWidget(self.bandeau_form)
        self._construire_bandeau_sig(v)
        self._construire_bandeau_mesure(v)
        self._construire_bandeau_comm(v)
        self.champ_choisi = None           # (page, xref) du champ choisi en mode formulaire
        self.marques_biffage = []          # [(page, rect)] a biffer
        self.sp = QSplitter()
        self.sp.setChildrenCollapsible(True)
        self.vignettes = GrillePages()
        self.vignettes.setMinimumWidth(110)
        self.vignettes.setStyleSheet("QListWidget{background:#fafafa;border:none}")
        self.vignettes.itemClicked.connect(lambda it: self.aller_a(it.data(Qt.UserRole)))
        self.vignettes.setContextMenuPolicy(Qt.CustomContextMenu)
        self.vignettes.customContextMenuRequested.connect(lambda p: self._menu_pages(self.vignettes, p))
        self.vignettes.ordre_change.connect(self.reordonner)
        self.vignettes.rendu = self._rendu_loupe
        self._taille_vign = 120
        self._minut_vign = QTimer(self)
        self._minut_vign.setSingleShot(True)
        self._minut_vign.timeout.connect(self._rafraichir_icones_vignettes)
        self.vignettes.vignettes_agrandies.connect(lambda l: (setattr(self, "_taille_vign", max(120, int(l * 1.45))),
                                                               self._minut_vign.start(250)))
        self.sp.addWidget(self._volet_gauche())
        self.centre = QStackedWidget()
        self.zone = QScrollArea()
        self.zone.setWidgetResizable(True)
        self.zone.setStyleSheet("QScrollArea{background:#e6e6e6;border:none}")
        self.conteneur = QWidget()
        self.conteneur.setStyleSheet("background:#e6e6e6")
        self.pages_layout = QVBoxLayout(self.conteneur)
        self.pages_layout.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.pages_layout.setSpacing(16)
        self.pages_layout.setContentsMargins(24, 20, 24, 30)
        self.zone.setWidget(self.conteneur)
        self.zone.verticalScrollBar().valueChanged.connect(self._page_visible)
        self.centre.addWidget(self.zone)
        self.centre.addWidget(self._vue_organiser())
        self.sp.addWidget(self.centre)
        self.volet = self._volet()
        self.sp.addWidget(self.volet)
        self.sp.splitterMoved.connect(self._volet_glisse)
        self.sp.setStretchFactor(1, 1)
        lv_ = int(self.params.get("volet_largeur") or 320)          # largeurs reglees a la souris : gardees
        lg_ = int(self.params.get("vignettes_largeur") or 140)
        self._taille_volet = max(200, lv_)
        self.sp.setSizes([lg_, 900, self._taille_volet])
        v.addWidget(self.sp, 1)
        self.barre_rapide = BarreRapide(self, self.zone.viewport())
        self.construire_pages()
        self.vignettes.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.liste_outils.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.liste_outils.setTextElideMode(Qt.ElideRight)
        if not self.params.get("vignettes", True):
            self.gauche.hide()
        self.maj_onglet_signets()
        QTimer.singleShot(0, lambda: self.mode_volet(self.params.get("volet", "complet"), memoriser=False))

    def _bouton(self, ic, txt, f, coul="#333333", aide=None):
        b = QToolButton()
        b.setIcon(icone(ic, coul))
        b.setIconSize(QSize(22, 22))
        b.setText(txt)
        b.setToolTip(aide or txt)
        b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        b.setAutoRaise(True)
        b.setMinimumWidth(60)
        b.setProperty("texte_dessous", True)          # barre etroite : icone seule (barre moins haute)
        b.clicked.connect(f)
        return b

    def _petit(self, ic, aide, f, checkable=False):
        b = QToolButton()
        b.setIcon(icone(ic, "#444444"))
        b.setIconSize(QSize(18, 18))
        b.setToolTip(aide)
        b.setAutoRaise(True)
        b.setCheckable(checkable)
        b.clicked.connect(f)
        return b

    def _aller_champ(self):
        try:
            n = int(self.champ_page.text()) - 1
        except ValueError:
            n = self.page_courante()
        self.aller_a(max(0, min(len(self.doc) - 1, n)))

    # ------------------------------------------------------------ barre d'outils (personnalisable, sur plusieurs lignes)
    ELEMENTS_BARRE = ["vignettes", "ouvrir", "enregistrer", "imprimer", "rechercher", "annuler", "retablir", "navigation",
                      "zoom", "pivoter", "pivoter_gauche", "|", "volet"]

    def barre_par_defaut(self):
        favoris = [o for o in self.params.get("outils_epingles", []) if o not in ("imprimer", "remplacer", "enregistrer")]
        favoris = [o for o in favoris if o != "courriel"]
        return ["vignettes", "ouvrir", "enregistrer", "imprimer", "courriel", "rechercher", "annuler", "retablir",
                "navigation", "zoom", "pivoter", "|"] + favoris + ["volet"]

    def libelle_element(self, cle):
        fixes = {"vignettes": _("Vignettes (volet gauche)"), "ouvrir": _("Ouvrir"), "enregistrer": _("Enregistrer"),
                 "imprimer": _("Imprimer"), "rechercher": _("Rechercher"), "annuler": _("Annuler|action"),
                 "retablir": _("Rétablir"), "navigation": _("Pages (première, précédente, numéro, suivante, dernière)"),
                 "zoom": _("Zoom − / + "), "pivoter": _("Pivoter (sens horaire)"),
                 "pivoter_gauche": _("Pivoter (sens anti-horaire)"), "|": _("— séparateur —"), "volet": _("Volet de droite")}
        if cle in fixes:
            return fixes[cle]
        o = outil(cle)
        return o[3] if o else cle

    def _barre_outils(self):
        w = QFrame()
        w.setObjectName("barre")
        w.setStyleSheet("QFrame#barre{background:#fff;border-bottom:1px solid #e2e2e2} QToolButton{font-size:11px;color:#444}")
        self.flux_barre = FluxLayout(w, marge=6, espace=2)
        self.barre_w = w
        self._surveille = _SurveilleTaille(w, self._adapter_barre)
        w.setContextMenuPolicy(Qt.CustomContextMenu)
        w.customContextMenuRequested.connect(lambda p: self._menu_barre(w.mapToGlobal(p)))
        # elements toujours crees (d'autres parties de l'onglet s'en servent), places seulement s'ils sont choisis
        self.b_vignettes = self._petit("volet_gauche", _('Afficher / masquer les vignettes des pages'), self.basculer_vignettes, True)
        self.b_vignettes.setChecked(self.params.get("vignettes", True))
        for attr, ic, txt, f in (("b_annuler", "annuler", _("Annuler|action"), lambda: self.annuler()),
                                 ("b_retablir", "retablir", _('Rétablir'), lambda: self.retablir())):
            b = self._bouton(ic, txt, f)
            b.setPopupMode(QToolButton.MenuButtonPopup)
            b.setMenu(QMenu(b))
            b.setMinimumWidth(70)
            setattr(self, attr, b)
        self.nav = QWidget()
        nav = QHBoxLayout(self.nav)
        nav.setContentsMargins(4, 0, 4, 0)
        nav.setSpacing(0)
        for ic, aide, f in (("premiere", _('Première page (Début)'), lambda: self.aller_a(0)),
                            ("precedente", _('Page précédente (Page préc.)'), lambda: self.aller_a(max(0, self.page_courante() - 1)))):
            nav.addWidget(self._petit(ic, aide, f))
        self.champ_page = QLineEdit()
        self.champ_page.setFixedWidth(42)
        self.champ_page.setAlignment(Qt.AlignCenter)
        self.champ_page.setToolTip(_('Tapez un numéro de page puis Entrée'))
        self.champ_page.returnPressed.connect(self._aller_champ)
        nav.addWidget(self.champ_page)
        self.lbl_page = QLabel()
        self.lbl_page.setStyleSheet("color:#555;padding:0 4px")
        nav.addWidget(self.lbl_page)
        for ic, aide, f in (("suivante", _('Page suivante (Page suiv.)'), lambda: self.aller_a(min(len(self.doc) - 1, self.page_courante() + 1))),
                            ("derniere", _('Dernière page (Fin)'), lambda: self.aller_a(len(self.doc) - 1))):
            nav.addWidget(self._petit(ic, aide, f))
        self.zoom_w = QWidget()
        hz = QHBoxLayout(self.zoom_w)
        hz.setContentsMargins(0, 0, 0, 0)
        hz.setSpacing(0)
        hz.addWidget(self._bouton("zoom_moins", _('Zoom −'), lambda: self.changer_zoom(self.zoom / 1.2)))
        self.lbl_zoom = QLabel()
        self.lbl_zoom.setMinimumWidth(44)
        self.lbl_zoom.setAlignment(Qt.AlignCenter)
        hz.addWidget(self.lbl_zoom)
        hz.addWidget(self._bouton("zoom_plus", _('Zoom +'), lambda: self.changer_zoom(self.zoom * 1.2)))
        self.b_volet = self._bouton("volet_droit", _('Volet'), self.basculer_volet,
                                    aide=_('Volet de droite : complet → icônes seules → masqué. '
                                           'Flèche : choisir ce qu\'il affiche (outils, format, tampons, signatures)'))
        mv = __import__("PySide6.QtWidgets", fromlist=["QMenu"]).QMenu(self.b_volet)
        for cle, lib, ic in self.CONTENUS_VOLET():
            mv.addAction(icone(ic, "#444444"), lib, lambda c=cle: self.contenu_volet(c))
        mv.addSeparator()
        for lib, md in ((_('Complet'), "complet"), (_('Icônes seules'), "icones"), (_('Masqué'), "masque")):
            mv.addAction(lib, lambda m=md: self.mode_volet(m))
        self.b_volet.setMenu(mv)
        self.b_volet.setPopupMode(QToolButton.MenuButtonPopup)
        self.zone_favoris = None
        self.construire_barre()
        return w

    def construire_barre(self):
        """Place les elements choisis (Preferences ou clic droit sur la barre), dans l'ordre choisi."""
        fl = self.flux_barre
        permanents = (self.b_vignettes, self.b_annuler, self.b_retablir, self.nav, self.zoom_w, self.b_volet)
        while fl.count():
            it = fl.takeAt(0)
            wd = it.widget()
            if wd is not None:
                wd.hide()
                if wd not in permanents:
                    wd.setParent(None)
                    wd.deleteLater()
        fl.set_droite(None)
        self.b_volet.hide()
        for cle in self.params.get("barre") or self.barre_par_defaut():
            wd = None
            if cle == "vignettes":
                wd = self.b_vignettes
            elif cle == "ouvrir":
                wd = self._bouton("ouvrir", _('Ouvrir'), lambda: self.outil_demande.emit("__ouvrir__"), aide=_('Ouvrir un fichier (Ctrl+O)'))
            elif cle == "enregistrer":
                wd = self._bouton("enregistrer", _('Enregistrer'), lambda: self.outil_demande.emit("enregistrer"), aide=_('Enregistrer (Ctrl+S)'))
            elif cle == "imprimer":
                wd = self._bouton("imprimer", _('Imprimer'), lambda: self.outil_demande.emit("imprimer"), aide=_('Imprimer (Ctrl+P)'))
            elif cle == "rechercher":
                wd = self._bouton("rechercher", _('Rechercher'), lambda: self.outil_demande.emit("remplacer"), aide=_('Rechercher et remplacer (Ctrl+F)'))
            elif cle == "annuler":
                wd = self.b_annuler
            elif cle == "retablir":
                wd = self.b_retablir
            elif cle == "navigation":
                wd = self.nav
            elif cle == "zoom":
                wd = self.zoom_w
            elif cle == "pivoter":
                wd = self._bouton("pivoter", _('Pivoter'), lambda: self.pivoter_courante(90),
                                  aide=_('Pivoter la page affichée de 90° (sens horaire) ; flèche : autres sens'))
                wd.setPopupMode(QToolButton.MenuButtonPopup)
                m = QMenu(wd)
                m.addAction(icone("pivoter"), _("90° sens horaire ↻"), lambda: self.pivoter_courante(90))
                m.addAction(icone("annuler"), _("90° sens anti-horaire ↺"), lambda: self.pivoter_courante(-90))
                m.addAction(_("180°"), lambda: self.pivoter_courante(180))
                wd.setMenu(m)
            elif cle == "pivoter_gauche":
                wd = self._bouton("annuler", _('Pivoter ↺'), lambda: self.pivoter_courante(-90), aide=_('Pivoter de 90° (sens anti-horaire)'))
            elif cle == "|":
                wd = QFrame()
                wd.setFrameShape(QFrame.VLine)
                wd.setFixedSize(8, 40)
                wd.setStyleSheet("color:#e2e2e2")
            elif cle == "volet":                     # toujours a l'extreme droite, en haut
                fl.set_droite(self.b_volet)
                self.b_volet.show()
                continue
            else:
                o = outil(cle)
                if o:
                    _x, _x, coul, _x = famille(o[1])
                    wd = self._bouton(o[2], o[3].split(" ")[0] if len(o[3]) > 12 else o[3],
                                      lambda _x=False, x=cle: self.outil_demande.emit(x), coul, o[3] + " — " + o[5])
            if wd is not None:
                fl.addWidget(wd)
                wd.show()
        self._mode_compact = None
        self._style_barre(False)
        e = fl.spacing()
        m = fl.contentsMargins()
        elems = [fl.itemAt(i).widget() for i in range(fl.count())] + ([fl.droite.widget()] if fl.droite else [])
        self._largeur_pleine = sum(x.sizeHint().width() + e for x in elems if x is not None) + m.left() + m.right() + 4
        self._adapter_barre()
        fl.invalidate()

    def _style_barre(self, compact):
        """compact : True (icone seule), False (icone et nom) ou "nom" (nom seul)."""
        style = {True: Qt.ToolButtonIconOnly, False: Qt.ToolButtonTextUnderIcon, "nom": Qt.ToolButtonTextOnly}[compact]
        for b in self.barre_w.findChildren(QToolButton):
            if b.property("texte_dessous"):
                if b.property("larg_mini") is None:
                    b.setProperty("larg_mini", b.minimumWidth())
                b.setToolButtonStyle(style)
                b.setMinimumWidth(b.property("larg_mini") if compact is False else 0)
                b.setIconSize(QSize(20, 20) if compact is True else QSize(22, 22))

    def _adapter_barre(self):
        """Tout tient sur une ligne : icones avec texte ; sinon icones seules (barre plus basse), puis plusieurs lignes."""
        if not hasattr(self, "_largeur_pleine"):
            return
        choix = self.params.get("barre_style") or "auto"
        compact = {"icone_nom": False, "icone": True, "nom": "nom"}.get(choix)
        if compact is None:                           # automatique : les noms seulement si toute la barre tient
            compact = self.barre_w.width() < self._largeur_pleine
        if (compact, choix) != getattr(self, "_mode_compact", None):
            self._mode_compact = (compact, choix)
            self._style_barre(compact)
            self.flux_barre.invalidate()

    def remplir_favoris(self):
        """Compatibilite : sans barre personnalisee, la barre suit les outils epingles du volet."""
        if not self.params.get("barre"):
            self.construire_barre()

    def _menu_barre(self, pos):
        m = QMenu(self)
        m.addAction(_("Personnaliser la barre d'outils..."), lambda: self.outil_demande.emit("__barre__"))
        m.addSection(_("Affichage des boutons"))
        from PySide6.QtGui import QActionGroup
        g = QActionGroup(m)
        actuel = self.params.get("barre_style") or "auto"
        for cle, txt in (("auto", _("Automatique : noms affichés si toute la barre tient sur une ligne")),
                         ("icone_nom", _("Icône et nom")), ("icone", _("Icône seule")), ("nom", _("Nom seul"))):
            a = m.addAction(txt)
            a.setCheckable(True)
            a.setChecked(cle == actuel)
            g.addAction(a)
            a.triggered.connect(lambda _c=False, k=cle: self.choisir_style_barre(k))
        m.exec(pos)

    def choisir_style_barre(self, cle):
        self.params["barre_style"] = cle
        self.params.enregistrer()
        self._mode_compact = None
        self._adapter_barre()

    def _bandeau_modifier(self):
        self.bandeau = QFrame()
        self.bandeau.setObjectName("bandeau")
        self.bandeau.setStyleSheet("QFrame#bandeau{background:#fbe8f2;border-bottom:1px solid #efc7dc}"
                                   "QToolButton{color:#6b0f41;font-size:11px;padding:2px 6px;border-radius:6px}"
                                   "QToolButton:checked{background:#f3c9df} QToolButton:hover{background:#f6d6e7}")
        h = QHBoxLayout(self.bandeau)
        h.setContentsMargins(12, 2, 12, 2)
        h.setSpacing(2)
        lbl = QLabel(_('<b>Modifier le PDF</b>'))
        lbl.setStyleSheet("color:#6b0f41;margin-right:10px")
        h.addWidget(lbl)
        self.boutons_modif = {}
        for cle, ic, txt, aide in [("modifier", "modifier", _('Modifier'), "Cliquer : sélectionner et déplacer ; double-clic : corriger dans la page"),
                                   ("ajout_texte", "creer", _('Ajouter du texte'), _('Cliquez où écrire')),
                                   ("ajout_image", "exporter", _('Ajouter une image'), _('Choisissez une image puis cliquez où la placer')),
                                   ("lien", "remplacer", _('Lien'), _('Tracez la zone du lien')),
                                   ("recadrer", "organiser", _('Recadrer les pages'), _('Tracez la zone à garder')),
                                   ("entete", "entete", _('En-tête et pied de page'), None),
                                   ("filigrane", "filigrane", _('Filigrane'), None),
                                   ("fond", "nettoyer", _('Arrière-plan'), _('Couleur de fond des pages'))]:
            b = QToolButton()
            b.setIcon(icone(ic, "#b0186b"))
            b.setIconSize(QSize(18, 18))
            b.setText(txt)
            b.setToolTip(aide or txt)
            b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            b.setCheckable(cle in ("modifier", "ajout_texte", "ajout_image", "lien", "recadrer"))
            b.clicked.connect(lambda _x=False, c=cle: self._action_modifier(c))
            self.boutons_modif[cle] = b
            h.addWidget(b)
        h.addStretch()
        fin = QPushButton(_('Terminer'))
        fin.setStyleSheet("QPushButton{background:#b0186b;color:#fff;border:none;border-radius:6px;padding:7px 14px;font-weight:600}")
        fin.clicked.connect(lambda: self.changer_mode(None))
        h.addWidget(fin)
        self.bandeau.hide()
        return self.bandeau

    def _action_modifier(self, cle):
        if cle in ("modifier", "ajout_texte", "lien", "recadrer"):
            self.changer_mode(cle)
        elif cle == "ajout_image":
            f, _x = QFileDialog.getOpenFileName(self, _('Image à ajouter'), "", _('Images (*.png *.jpg *.jpeg *.bmp *.tif *.gif)'))
            if f:
                self.image_a_ajouter = f
                self.changer_mode("ajout_image")
            else:
                self.changer_mode("modifier")
        else:
            self.outil_demande.emit(cle)

    def _vue_organiser(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(16, 10, 16, 10)
        t = QLabel(_("<b>Organiser les pages</b> — glissez pour réordonner, clic droit pour plus d'actions ; "
                     "survolez une page pour la loupe, molette pour zoomer"))
        t.setWordWrap(True)
        v.addWidget(t)
        boutons = QWidget()
        h = QHBoxLayout(boutons)
        h.setContentsMargins(0, 0, 0, 0)
        h.addStretch()
        for txt, f in [(_('Pivoter ↺'), lambda: self._sel_grille(lambda p: self.pivoter(p, -90, demander=False))),
                       (_('Pivoter ↻'), lambda: self._sel_grille(lambda p: self.pivoter(p, 90, demander=False))),
                       (_('Supprimer'), lambda: self._sel_grille(self.supprimer_pages)),
                       (_('Extraire'), lambda: self._sel_grille(self.extraire)),
                       (_('Insérer un fichier...'), self.inserer_fichier)]:
            b = QPushButton(txt)
            b.clicked.connect(f)
            h.addWidget(b)
        fin = QPushButton(_('Terminer'))
        fin.setStyleSheet("QPushButton{background:#c9252d;color:#fff;border:none;border-radius:6px;padding:6px 14px;font-weight:600}")
        fin.clicked.connect(lambda: self.organiser(False))
        h.addWidget(fin)
        v.addWidget(defilable(boutons))
        self.grille = GrillePages(grille=True)
        self.grille.setStyleSheet("QListWidget{background:#ececec;border:none}")
        self.grille.ordre_change.connect(self.reordonner)
        self.grille.rendu = self._rendu_loupe
        self.grille.setContextMenuPolicy(Qt.CustomContextMenu)
        self.grille.customContextMenuRequested.connect(lambda p: self._menu_pages(self.grille, p))
        v.addWidget(self.grille, 1)
        return w

    def _sel_grille(self, f):
        pages = sorted(it.data(Qt.UserRole) for it in self.grille.selectedItems())
        if pages:
            f(pages)
        else:
            self.message(_("Sélectionnez d'abord des pages."))

    def organiser(self, actif=True):
        if actif:
            self._remplir_grille()
            self.centre.setCurrentIndex(1)
        else:
            self.centre.setCurrentIndex(0)

    def _volet(self):
        w = QFrame()
        w.setObjectName("volet")
        w.setMinimumWidth(200)
        w.setStyleSheet("QFrame#volet{background:#fff;border-left:1px solid #e2e2e2}")
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        self.modes_volet = QStackedWidget()
        v.addWidget(self.modes_volet)
        self.pile_volet = QStackedWidget()
        self.modes_volet.addWidget(self.pile_volet)
        self.pile_volet.addWidget(self._volet_outils())
        self.pile_volet.addWidget(self._volet_format())
        self.pile_volet.addWidget(self._volet_bibliotheque())
        self.pile_volet.addWidget(self._volet_retouche())       # 3 : retouche de l'image choisie
        self._idx_volet_comm = self.pile_volet.addWidget(self._volet_commentaires())   # 4 : liste des commentaires
        self.icones_volet = QWidget()
        self.icones_layout = QVBoxLayout(self.icones_volet)
        self.icones_layout.setContentsMargins(4, 10, 4, 10)
        self.icones_layout.setSpacing(4)
        self.modes_volet.addWidget(self.icones_volet)
        self.remplir_icones_volet()
        return w

    def remplir_icones_volet(self):
        while self.icones_layout.count():
            it = self.icones_layout.takeAt(0)
            if it.widget():
                it.widget().hide()
                it.widget().setParent(None)
        for oid in self.params["outils_epingles"]:
            o = outil(oid)
            if o:
                b = QToolButton()
                b.setIcon(icone(o[2], famille(o[1])[2]))
                b.setIconSize(QSize(22, 22))
                b.setToolTip(f"{o[3]} — {o[5]}")
                b.setAutoRaise(True)
                b.clicked.connect(lambda _x=False, x=oid: self.outil_demande.emit(x))
                self.icones_layout.addWidget(b, 0, Qt.AlignHCenter)
        b = QToolButton()
        b.setIcon(icone("plus", "#555555"))
        b.setIconSize(QSize(20, 20))
        b.setToolTip(_('Tous les outils'))
        b.setAutoRaise(True)
        b.clicked.connect(lambda: self.outil_demande.emit("__outils__"))
        self.icones_layout.addWidget(b, 0, Qt.AlignHCenter)
        self.icones_layout.addStretch()
        b = QToolButton()
        b.setIcon(icone("volet_droit", "#555555"))
        b.setToolTip(_('Volet complet'))
        b.setAutoRaise(True)
        b.clicked.connect(lambda: self.mode_volet("complet"))
        self.icones_layout.addWidget(b, 0, Qt.AlignHCenter)

    def mode_volet(self, mode, memoriser=True):
        """'complet', 'icones' ou 'masque' (memorise pour tous les documents)."""
        tailles = self.sp.sizes()
        total = tailles[1] + tailles[2]
        if self.modes_volet.currentIndex() == 0 and tailles[2] >= 200:
            self._taille_volet = tailles[2]
        if mode == "icones":
            self.modes_volet.setCurrentIndex(1)
            self.volet.setMinimumWidth(48)
            self.volet.setMaximumWidth(16777215)       # on peut encore l'elargir a la souris : il redevient complet
            self.volet.show()
            self.sp.setSizes([tailles[0], total - 52, 52])
        elif mode == "masque":
            self.volet.hide()
        else:
            self.modes_volet.setCurrentIndex(0)
            self.volet.setMaximumWidth(16777215)
            self.volet.setMinimumWidth(48)
            self.volet.show()
            t = getattr(self, "_taille_volet", 300)
            self.sp.setSizes([tailles[0], max(300, total - t), t])
        self._mode_volet = mode
        if memoriser:
            self.params["volet"] = mode
            self.params.enregistrer()

    def _memo_largeurs(self):
        t = self.sp.sizes()
        changes = False
        if self.gauche.isVisible() and t[0] >= 60 and t[0] != self.params.get("vignettes_largeur"):
            self.params["vignettes_largeur"] = t[0]
            changes = True
        if getattr(self, "_mode_volet", "complet") == "complet" and self.volet.isVisible() and t[2] >= 200 \
                and t[2] != self.params.get("volet_largeur"):
            self.params["volet_largeur"] = t[2]
            self._taille_volet = t[2]
            changes = True
        if changes:
            self.params.enregistrer()

    def _volet_glisse(self, *_a):
        """En retrecissant le volet a la souris, il passe en icones seules ; en l'elargissant, il redevient complet.
        La largeur choisie est gardee (meme apres fermeture), comme celle des vignettes."""
        if not hasattr(self, "_t_largeurs"):
            from PySide6.QtCore import QTimer
            self._t_largeurs = QTimer(self)
            self._t_largeurs.setSingleShot(True)
            self._t_largeurs.setInterval(600)
            self._t_largeurs.timeout.connect(self._memo_largeurs)
        self._t_largeurs.start()
        if not self.volet.isVisible():
            return
        lv = self.sp.sizes()[2]
        mode = getattr(self, "_mode_volet", "complet")
        if self.pile_volet.currentIndex() != 0:      # volet Format ou Tampons ouvert : il garde son contenu
            if lv < 200:
                t = self.sp.sizes()
                self.sp.setSizes([t[0], t[1] + t[2] - 200, 200])
            return
        if mode == "complet" and lv < 175:
            self._taille_volet = max(200, int(self.params.get("volet_largeur") or 300))
            self.mode_volet("icones")
        elif mode == "icones" and lv > 140:
            self._taille_volet = max(lv, 240)
            self.mode_volet("complet")

    @staticmethod
    def CONTENUS_VOLET():
        return (("outils", _("Mes outils"), "parametres"),
                ("format", _("Format du texte"), "modifier"), ("tampons", _("Mes tampons"), "tampon"),
                ("signatures", _("Mes signatures"), "signer"))

    def contenu_volet(self, quoi):
        """Ce que montre le volet de droite : vos outils, le format du texte, vos tampons ou vos signatures."""
        if quoi in ("tampons", "signatures"):
            self.ouvrir_bibliotheque(quoi)
            return
        self.pile_volet.setCurrentIndex(1 if quoi == "format" else 0)
        self._montrer_volet()
        self.mode_volet("complet", memoriser=False)

    def basculer_volet(self):
        suivant = {"complet": "icones", "icones": "masque", "masque": "complet"}
        self.mode_volet(suivant.get(getattr(self, "_mode_volet", "complet"), "complet"))

    def basculer_vignettes(self, *_x):
        visible = not self.gauche.isVisible()
        self.gauche.setVisible(visible)
        self.b_vignettes.setChecked(visible)
        self.params["vignettes"] = visible
        self.params.enregistrer()

    def _volet_outils(self):
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(14, 16, 14, 16)
        t = QLabel(_('MES OUTILS'))
        t.setStyleSheet("font-size:12px;font-weight:600;color:#555;letter-spacing:1px")
        l.addWidget(t)
        aide = QLabel(_("Glissez pour changer l'ordre (barre du haut comprise)."))
        aide.setStyleSheet("font-size:11px;color:#777")
        aide.setWordWrap(True)
        l.addWidget(aide)
        self.liste_outils = QListWidget()
        self.liste_outils.setDragDropMode(QAbstractItemView.InternalMove)
        self.liste_outils.setStyleSheet("QListWidget{border:none;font-size:14px} QListWidget::item{padding:8px 4px;border-radius:8px}"
                                        "QListWidget::item:hover{background:#f4f7fb}")
        self.liste_outils.setIconSize(QSize(20, 20))
        self.liste_outils.itemClicked.connect(lambda it: self.outil_demande.emit(it.data(Qt.UserRole)))
        self.liste_outils.model().rowsMoved.connect(self._ordre_outils)
        l.addWidget(self.liste_outils, 1)
        tous = QPushButton(_('  +  Tous les outils'))
        tous.setStyleSheet("QPushButton{text-align:left;padding:9px 8px;border:1px dashed #cfcfcf;border-radius:8px;font-size:14px}")
        tous.clicked.connect(lambda: self.outil_demande.emit("__outils__"))
        l.addWidget(tous)
        ia = QLabel(_("✦ <b>Assistant IA</b><br><span style='font-size:12px'>"
                      "<a href='ia_resume'>Résumer</a> · <a href='ia_classer'>Renommer et classer</a> · "
                      "<a href='ia_comparer'>Comparer</a> · <a href='ia_traduire'>Traduire</a><br>Rien n'est envoyé sans votre clic.</span>"))
        ia.setWordWrap(True)
        ia.setTextFormat(Qt.RichText)
        ia.linkActivated.connect(self.outil_demande.emit)
        ia.setStyleSheet("QLabel{background:#f2fafa;border:1px solid #cfe9ea;border-radius:10px;padding:10px;color:#0b5e63}")
        l.addWidget(ia)
        self.lbl_info = QLabel()
        self.lbl_info.setWordWrap(True)
        self.lbl_info.setStyleSheet("font-size:12px;color:#555")
        l.addWidget(self.lbl_info)
        self.remplir_volet()
        return w

    def remplir_volet(self):
        self.liste_outils.blockSignals(True)
        self.liste_outils.clear()
        for oid in self.params["outils_epingles"]:
            o = outil(oid)
            if o:
                it = QListWidgetItem(icone(o[2], famille(o[1])[2]), o[3])
                it.setToolTip(o[5])
                it.setData(Qt.UserRole, oid)
                self.liste_outils.addItem(it)
        self.liste_outils.blockSignals(False)
        self.remplir_favoris()
        if hasattr(self, "icones_layout"):
            self.remplir_icones_volet()
        self.maj_info()

    def _ordre_outils(self, *a):
        ordre = [self.liste_outils.item(i).data(Qt.UserRole) for i in range(self.liste_outils.count())]
        self.params["outils_epingles"] = ordre
        self.params.enregistrer()
        self.remplir_favoris()
        self.remplir_icones_volet()
        self.outil_demande.emit("__epingles__")

    # ------------------------------------------------------------ retouche d'image (volet de droite)
    CURSEURS_RETOUCHE = (("luminosite", "Luminosité", -100, 100, 0), ("contraste", "Contraste", -100, 100, 0),
                         ("gamma", "Tons moyens", 30, 300, 100), ("noir", "Niveau des noirs", 0, 200, 0),
                         ("blanc", "Niveau des blancs", 55, 255, 255), ("saturation", "Saturation", -100, 100, 0),
                         ("temperature", "Température (froid ↔ chaud)", -100, 100, 0), ("teinte", "Teinte", -100, 100, 0),
                         ("nettete", "Flou ↔ netteté", -100, 100, 0), ("bruit", "Réduction du bruit", 0, 100, 0))

    def _volet_retouche(self):
        from PySide6.QtWidgets import QScrollArea, QSlider, QGridLayout
        zone = QScrollArea()
        zone.setWidgetResizable(True)
        zone.setFrameShape(QFrame.NoFrame)
        zone.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)     # le contenu suit la largeur du volet
        w = QWidget()
        w.setMinimumWidth(10)
        zone.setWidget(w)
        v = QVBoxLayout(w)
        v.setContentsMargins(14, 16, 14, 16)
        t = QLabel(_("RETOUCHE DE L'IMAGE"))
        t.setStyleSheet("font-size:12px;font-weight:600;color:#555;letter-spacing:1px")
        v.addWidget(t)
        aide = QLabel(_("Les réglages s'affichent en direct sur l'image de la page. Rien n'est changé dans le PDF "
                        "avant « Appliquer à l'image ». Ctrl+Z annule ensuite."))
        aide.setWordWrap(True)
        aide.setStyleSheet("color:#555;font-size:12px")
        v.addWidget(aide)
        self.ret_auto = QCheckBox(_("Correction automatique"))
        self.ret_auto.setToolTip(_("Niveaux et couleurs corrigés automatiquement"))
        self.ret_auto.toggled.connect(lambda _c: self._maj_retouche())
        v.addWidget(self.ret_auto)
        g = QGridLayout()
        g.setHorizontalSpacing(6)
        g.setVerticalSpacing(2)
        self.ret_curseurs = {}
        libs = {"luminosite": _("Luminosité"), "contraste": _("Contraste"), "gamma": _("Tons moyens"),
                "noir": _("Niveau des noirs"), "blanc": _("Niveau des blancs"), "saturation": _("Saturation"),
                "temperature": _("Température (froid ↔ chaud)"), "teinte": _("Teinte"), "nettete": _("Flou ↔ netteté"),
                "bruit": _("Réduction du bruit")}
        for i, (cle, lib, mini, maxi, defaut) in enumerate(self.CURSEURS_RETOUCHE):
            lb = QLabel(libs.get(cle, lib))
            lb.setStyleSheet("font-size:12px")
            sl = QSlider(Qt.Horizontal)
            sl.setRange(mini, maxi)
            sl.setValue(defaut)
            sl.setObjectName("ret_" + cle)
            val = QLabel(str(defaut))
            val.setFixedWidth(30)
            val.setStyleSheet("color:#777;font-size:11px")
            sl.valueChanged.connect(lambda x, val=val: (val.setText(str(x)), self._maj_retouche()))
            sl.setToolTip(_("Double-clic sur le nom : revenir à la valeur de départ"))
            lb.mouseDoubleClickEvent = lambda _e, sl=sl, d=defaut: sl.setValue(d)
            g.addWidget(lb, 2 * i, 0, 1, 2)
            g.addWidget(sl, 2 * i + 1, 0)
            g.addWidget(val, 2 * i + 1, 1)
            self.ret_curseurs[cle] = (sl, defaut)
        v.addLayout(g)
        self.ret_nb = QCheckBox(_("Noir et blanc"))
        self.ret_nb.toggled.connect(lambda _c: self._maj_retouche())
        v.addWidget(self.ret_nb)
        t2 = QLabel(_("CHOISIR UNE ZONE"))
        t2.setStyleSheet("font-size:12px;font-weight:600;color:#555;letter-spacing:1px;margin-top:8px")
        v.addWidget(t2)
        self.ret_b_baguette = BoutonVolet(_("Baguette magique"),
                                          _("Cliquez sur l'image : la zone de même couleur est choisie (Maj + clic : en ajouter)"))
        self.ret_b_baguette.setCheckable(True)
        v.addWidget(self.ret_b_baguette)
        self.ret_b_lasso = BoutonVolet(_("Entourer à la main"),
                                       _("Dessinez le tour de la zone sur l'image, bouton appuyé (Maj : en ajouter)"))
        self.ret_b_lasso.setCheckable(True)
        v.addWidget(self.ret_b_lasso)
        self.ret_b_cadre = BoutonVolet(_("Tracer un rectangle"), _("Glissez sur l'image (Maj : en ajouter)"))
        self.ret_b_cadre.setCheckable(True)
        v.addWidget(self.ret_b_cadre)
        from PySide6.QtWidgets import QButtonGroup as _QBG
        self._grp_sel = _QBG(self)
        self._grp_sel.setExclusive(False)
        for b_ in (self.ret_b_baguette, self.ret_b_lasso, self.ret_b_cadre):
            b_.setStyleSheet("QPushButton:checked{background:#fde7ef;border:2px solid #c2185b;color:#8a0f3d;"
                             "font-weight:600}")
            self._grp_sel.addButton(b_)
            b_.toggled.connect(lambda on, b_=b_: [x.setChecked(False) for x in (self.ret_b_baguette, self.ret_b_lasso,
                                                                                 self.ret_b_cadre) if on and x is not b_])
        ht = QHBoxLayout()
        ht.addWidget(QLabel(_("Tolérance")))
        self.ret_tol = QSlider(Qt.Horizontal)
        self.ret_tol.setRange(2, 120)
        self.ret_tol.setValue(30)
        ht.addWidget(self.ret_tol, 1)
        v.addLayout(ht)
        cadre_b = QWidget()                            # les boutons passent a la ligne plutot que d'etre tronques
        hb = FluxLayout(cadre_b, marge=0, espace=6)
        for txt, aide_, mode in ((_("Effacer"), _("La zone est remplie à partir de ce qui l'entoure"), "fond"),
                                 (_("Transparent"), _("La zone devient transparente"), "transparent"),
                                 (_("Blanc"), _("La zone devient blanche"), "blanc")):
            b = QPushButton(txt)
            b.setToolTip(aide_)
            b.setMinimumWidth(b.sizeHint().width())
            b.clicked.connect(lambda _c=False, m=mode: self.effacer_zone(m))
            hb.addWidget(b)
        v.addWidget(cadre_b)
        b = QPushButton(_("Désélectionner la zone"))
        b.clicked.connect(lambda: (self.retouche and self.retouche.update(masque=None), self._maj_retouche()))
        v.addWidget(b)
        self.ret_b_ia = BoutonVolet(_("Retouche avec l'IA (Gemini)..."), _("Consigne, styles prêts à l'emploi, zones entourées ; avant / après à valider"))
        self.ret_b_ia.clicked.connect(self.retouche_ia)
        v.addWidget(self.ret_b_ia)
        v.addStretch(1)
        b = QPushButton(_("Appliquer à l'image"))       # pleine largeur : jamais tronque
        b.setStyleSheet("QPushButton{background:#0f6cbd;color:#fff;border:none;border-radius:6px;padding:8px 10px;font-weight:600}")
        b.clicked.connect(self.appliquer_retouche)
        v.addWidget(b)
        b = QPushButton(_("Réinitialiser"))
        b.clicked.connect(self.reinitialiser_retouche)
        v.addWidget(b)
        from PySide6.QtCore import QTimer
        self._t_retouche = QTimer(self)
        self._t_retouche.setSingleShot(True)
        self._t_retouche.setInterval(90)
        self._t_retouche.timeout.connect(self._calcul_apercu)
        return zone

    def reglages_retouche(self):
        r = {k: sl.value() for k, (sl, _d) in self.ret_curseurs.items()}
        r.update(auto=self.ret_auto.isChecked(), noir_blanc=self.ret_nb.isChecked())
        return r

    def ouvrir_retouche(self, obj):
        """Image choisie (mode Modifier) : le volet de retouche s'ouvre, avec ses reglages a zero."""
        from moteur import retouche as R
        try:
            src = R.depuis_pdf(self.doc, obj["xref"])
        except Exception as e:
            self.message(_("Retouche impossible sur cette image : {e}", e=e))
            return
        self.retouche = {"page": obj["page"], "xref": obj["xref"], "src": src, "petit": R.reduire(src),
                         "masque": None, "apercu": None, "geo": Editeur(self.doc).geometrie_image(obj["page"], obj["xref"])}
        for sl, d in self.ret_curseurs.values():
            sl.blockSignals(True)
            sl.setValue(d)
            sl.blockSignals(False)
        for c in (self.ret_auto, self.ret_nb):
            c.blockSignals(True)
            c.setChecked(False)
            c.blockSignals(False)
        for b_ in (self.ret_b_baguette, self.ret_b_lasso, self.ret_b_cadre):
            b_.setChecked(False)
        self.pile_volet.setCurrentIndex(3)
        self._montrer_volet()
        self._calcul_apercu()

    def fermer_retouche(self):
        self.retouche = None
        if self.pile_volet.currentIndex() == 3:
            self.pile_volet.setCurrentIndex(1 if self.mode == "modifier" else 0)
        self.rafraichir_pages()

    def reinitialiser_retouche(self):
        if self.retouche:
            obj = {"page": self.retouche["page"], "xref": self.retouche["xref"]}
            self.ouvrir_retouche(obj)

    def _maj_retouche(self):
        if getattr(self, "retouche", None):
            self._t_retouche.start()

    def _calcul_apercu(self):
        """Apercu rapide sur une copie reduite ; la zone de la baguette apparait en rouge."""
        from moteur import retouche as R
        import numpy as np
        rt = getattr(self, "retouche", None)
        if not rt:
            return
        img = R.appliquer(rt["petit"], self.reglages_retouche())
        if rt["masque"] is not None:
            import cv2
            m = cv2.resize(rt["masque"].astype(np.uint8), (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST) > 0
            rouge = img.copy()
            rouge[m, 0] = np.clip(rouge[m, 0].astype(int) * 0.4 + 255 * 0.6, 0, 255).astype(np.uint8)
            rouge[m, 1] = (rouge[m, 1] * 0.4).astype(np.uint8)
            rouge[m, 2] = (rouge[m, 2] * 0.4).astype(np.uint8)
            img = rouge
        q = QImage(img.data, img.shape[1], img.shape[0], img.shape[1] * 4, QImage.Format_RGBA8888).copy()
        rt["apercu"] = q
        for pw in self.page_widgets:
            if pw.num == rt["page"]:
                pw.update()

    def point_image(self, pt):
        """Point de la page -> pixel de l'image en retouche (rotation comprise), ou None s'il est dehors."""
        import math
        rt = self.retouche
        c, w, h, angle = rt["geo"]
        a = math.radians(angle)
        dx, dy = pt.x - c.x, pt.y - c.y
        x = dx * math.cos(a) - dy * math.sin(a)
        y = dx * math.sin(a) + dy * math.cos(a)
        H, W = rt["src"].shape[:2]
        px, py = (x + w / 2) / w * W, (y + h / 2) / h * H
        return (px, py) if 0 <= px < W and 0 <= py < H else None

    def clic_baguette(self, pt, ajouter=False):
        from moteur import retouche as R
        rt = self.retouche
        p = self.point_image(pt)
        if p is None:
            return False
        base = R.appliquer(rt["src"], self.reglages_retouche()) if any(
            v for k, v in self.reglages_retouche().items() if k not in ("gamma", "blanc")) else rt["src"]
        rt["masque"] = R.baguette(base, p[0], p[1], self.ret_tol.value(), rt["masque"] if ajouter else None)
        self._calcul_apercu()
        return True

    def zone_tracee_image(self, points, ajouter=False):
        """Zone entouree a la main (ou rectangle) sur l'image en retouche : devient la zone choisie."""
        import numpy as np
        import cv2
        rt = getattr(self, "retouche", None)
        if not rt or len(points) < 3:
            return False
        H, W = rt["src"].shape[:2]
        pix = []
        for pt in points:
            q = self.point_image_libre(pt)
            pix.append([int(round(q[0])), int(round(q[1]))])
        m = np.zeros((H, W), np.uint8)
        cv2.fillPoly(m, [np.array(pix, np.int32)], 1)
        m = m.astype(bool)
        rt["masque"] = (rt["masque"] | m) if (ajouter and rt["masque"] is not None) else m
        self._calcul_apercu()
        return bool(m.any())

    def point_image_libre(self, pt):
        """Comme point_image, sans refuser les points hors de l'image (tracé qui deborde)."""
        import math
        rt = self.retouche
        c, w, h, angle = rt["geo"]
        a = math.radians(angle)
        dx, dy = pt.x - c.x, pt.y - c.y
        x = dx * math.cos(a) - dy * math.sin(a)
        y = dx * math.sin(a) + dy * math.cos(a)
        H, W = rt["src"].shape[:2]
        return (min(W - 1, max(0, (x + w / 2) / w * W)), min(H - 1, max(0, (y + h / 2) / h * H)))

    def effacer_zone(self, mode):
        from moteur import retouche as R
        rt = getattr(self, "retouche", None)
        if not rt or rt["masque"] is None:
            self.message(_("Choisissez d'abord une zone : baguette magique, entourer à la main ou rectangle."))
            return
        rt["src"] = R.effacer(rt["src"], rt["masque"], mode)
        rt["petit"] = R.reduire(rt["src"])
        rt["masque"] = None
        rt["modifiee"] = True
        self._calcul_apercu()

    def appliquer_retouche(self):
        from moteur import retouche as R
        rt = getattr(self, "retouche", None)
        if not rt:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            img = R.appliquer(rt["src"], self.reglages_retouche())
            self.memoriser(_("Retouche de l'image"))
            nx = R.remplacer_dans_pdf(self.doc, rt["page"], rt["xref"], img)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.message(_("Retouche impossible : {e}", e=e))
            return
        QApplication.restoreOverrideCursor()
        n = rt["page"]
        self.apres_modif([_("Image retouchée.")])
        r = next((r for x, r in Editeur(self.doc).images(n) if x == nx), None)
        self.objet = {"type": "image", "page": n, "xref": nx, "rect": r, "garder_proportions": True} if r else None
        if self.objet:
            self.ouvrir_retouche(self.objet)
        else:
            self.fermer_retouche()

    def retouche_ia(self):
        rt = getattr(self, "retouche", None)
        if not rt:
            return
        from .dialogues_retouche_ia import DialogueRetoucheIA
        from moteur import retouche as R
        d = DialogueRetoucheIA(self, R.appliquer(rt["src"], self.reglages_retouche()), self.params)
        if d.exec() == QDialog.Accepted and d.resultat is not None:
            rt["src"] = d.resultat
            rt["petit"] = R.reduire(rt["src"])
            for sl, dft in self.ret_curseurs.values():      # les reglages sont deja dans l'image envoyee
                sl.blockSignals(True)
                sl.setValue(dft)
                sl.blockSignals(False)
            for c in (self.ret_auto, self.ret_nb):
                c.blockSignals(True)
                c.setChecked(False)
                c.blockSignals(False)
            self._calcul_apercu()
            self.message(_("Résultat de l'IA dans l'aperçu : « Appliquer à l'image » pour le garder."))

    def _volet_format(self):
        w = QWidget()
        f = QFormLayout(w)
        f.setContentsMargins(14, 16, 14, 16)
        t = QLabel(_('FORMAT'))
        t.setStyleSheet("font-size:12px;font-weight:600;color:#555;letter-spacing:1px")
        f.addRow(t)
        self.format_info = QLabel(_('Cliquez sur une ligne pour la sélectionner, glissez pour la déplacer, double-cliquez pour corriger dans la page.'))
        self.format_info.setWordWrap(True)
        self.format_info.setMinimumHeight(self.format_info.fontMetrics().lineSpacing() * 4)
        self.format_info.setStyleSheet("color:#555;font-size:12px")
        f.addRow(self.format_info)
        from .polices import combo as combo_polices
        self.format_police = combo_polices(doc=lambda: getattr(self, "doc", None))
        f.setRowWrapPolicy(QFormLayout.WrapAllRows)      # libelles au-dessus : les listes gardent toute la largeur
        f.addRow(_('Police'), self.format_police.ligne())
        self.format_police.apercu.connect(self._apercu_police)
        self.format_taille = QDoubleSpinBox()
        self.format_taille.setRange(4, 96)
        self.format_taille.setValue(11)
        self.format_taille.setSuffix(" pt")
        f.addRow(_('Taille'), self.format_taille)
        self.format_couleur = QColor("#000000")
        self.b_couleur = QPushButton(_("Couleur du texte..."))
        self._maj_b_couleur()
        self.b_couleur.clicked.connect(self._choisir_couleur)
        f.addRow(_('Couleur'), self.b_couleur)
        self.b_appliquer = BoutonVolet(_('Appliquer à la ligne sélectionnée'),
                                       _("Applique la taille et la couleur ci-dessus à la ligne choisie sur la page"))
        self.b_appliquer.clicked.connect(self.appliquer_format)
        f.addRow(self.b_appliquer)
        t2 = QLabel(_('OBJETS'))
        t2.setStyleSheet("font-size:12px;font-weight:600;color:#555;letter-spacing:1px;margin-top:12px")
        f.addRow(t2)
        n2 = QLabel(_("Un objet = une image, un tampon, une signature ou une ligne de texte : cliquez-le sur la page "
                      "(il s'entoure de poignées), puis :"))
        n2.setWordWrap(True)
        n2.setStyleSheet("color:#666;font-size:11px")
        f.addRow(n2)
        for txt, aide, fn in [(_("Supprimer l'objet sélectionné"), _("Retire de la page l'objet entouré de poignées (Suppr fait pareil)"), self.supprimer),
                              (_("Remplacer l'image..."), _("Remplace l'image sélectionnée par une autre image de ce PC, à la même place et à la même taille"), self.remplacer_image)]:
            b = BoutonVolet(txt, aide)
            b.clicked.connect(fn)
            f.addRow(b)
        return w

    def _apercu_police(self, p):
        for pw in getattr(self, "page_widgets", []):
            ed = getattr(pw, "editeur", None)
            if isinstance(ed, EditeurParagraphe):
                ed.apercu_police(p)

    def _maj_b_couleur(self):
        pm = QPixmap(18, 18)
        pm.fill(self.format_couleur)
        self.b_couleur.setIcon(QIcon(pm))
        self.b_couleur.setStyleSheet("QPushButton{text-align:left;padding:4px 8px}")

    def _choisir_couleur(self):
        c = QColorDialog.getColor(self.format_couleur, self)
        if c.isValid():
            self.format_couleur = c
            self._maj_b_couleur()

    def _volet_bibliotheque(self):
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(14, 16, 14, 16)
        self.titre_biblio = QLabel()
        self.titre_biblio.setStyleSheet("font-size:12px;font-weight:600;color:#555;letter-spacing:1px")
        l.addWidget(self.titre_biblio)
        aide = QLabel(_("Cliquez un élément, puis cliquez sur la page pour le poser. Il reste déplaçable et redimensionnable (poignées), Suppr pour l'enlever."))
        aide.setWordWrap(True)
        aide.setStyleSheet("color:#555;font-size:12px")
        l.addWidget(aide)
        from PySide6.QtWidgets import QTreeWidget
        self.liste_biblio = QTreeWidget()
        self.liste_biblio.setHeaderHidden(True)
        self.liste_biblio.setIconSize(QSize(120, 44))
        self.liste_biblio.setWordWrap(True)
        self.liste_biblio.setIndentation(12)
        self.liste_biblio.setStyleSheet("QTreeWidget{border:1px solid #e2e2e2;border-radius:6px} QTreeWidget::item{padding:3px}")
        self.liste_biblio.itemClicked.connect(self._choisir_biblio)
        self.liste_biblio.itemExpanded.connect(lambda it: self._memo_groupe(it, True))
        self.liste_biblio.itemCollapsed.connect(lambda it: self._memo_groupe(it, False))
        self.liste_biblio.setContextMenuPolicy(Qt.CustomContextMenu)
        self.liste_biblio.customContextMenuRequested.connect(self._menu_biblio)
        # volet etroit (petit ecran) : apercus plus petits, pour laisser la place aux noms et aux categories
        from PySide6.QtCore import QObject, QEvent

        class _Adapter(QObject):
            def eventFilter(s_, obj, ev):
                if ev.type() == QEvent.Resize:
                    lw = obj.width()
                    iw = int(max(48, min(120, lw * 0.36)))
                    if obj.iconSize().width() != iw:
                        obj.setIconSize(QSize(iw, max(22, int(iw * 0.37))))
                return False
        self._adapter_biblio = _Adapter(self.liste_biblio)
        self.liste_biblio.installEventFilter(self._adapter_biblio)
        l.addWidget(self.liste_biblio, 1)
        b = BoutonVolet(_('Gérer, importer, dessiner...'), _("Ajouter, renommer, classer vos tampons et signatures"))
        b.clicked.connect(self._gerer_biblio)
        l.addWidget(b)
        b = QPushButton(_('Fermer'))
        b.clicked.connect(lambda: self.changer_mode(None))
        l.addWidget(b)
        return w

    def ouvrir_bibliotheque(self, genre):
        self.genre_biblio = genre
        self.titre_biblio.setText(_('MES TAMPONS') if genre == "tampons" else _('MES SIGNATURES'))
        self.liste_biblio.clear()
        from PySide6.QtWidgets import QTreeWidgetItem
        replies = set(self.params.get("biblio_replies", ["predefinis"]))

        def groupe(parent, cle, titre):
            g = QTreeWidgetItem([titre])
            f = g.font(0)
            f.setBold(True)
            g.setFont(0, f)
            g.setData(0, Qt.UserRole + 1, cle)
            g.setToolTip(0, titre)                   # nom complet si le volet est etroit
            (parent.addChild(g) if parent else self.liste_biblio.addTopLevelItem(g))
            g.setExpanded(cle not in replies)
            return g
        from .dialogues import etoile_jaune
        perso = self.biblio.elements(genre)
        favoris = self.biblio.favoris(genre)
        if favoris:                                  # en tete, ouverts : un clic pour poser, categories repliees ou non
            g_fav = groupe(None, "favoris", _("Favoris ({n})", n=len(favoris)))
            g_fav.setIcon(0, QIcon(etoile_jaune(12)))
            for e in favoris:
                self._ajout_item_biblio(g_fav, e["nom"], None, e,
                                        _("Date ajoutée à la pose") if e.get("horodatage", "non") != "non" else None)
        perso = self.biblio.elements(genre)
        titre = _("Mes tampons") if genre == "tampons" else _("Mes signatures")
        g_perso = groupe(None, "perso", f"{titre} ({len(perso)})")
        cats = {}
        for e in perso:                              # meme ordre que dans « Mes tampons » (categorie, puis votre ordre)
            c = e.get("categorie", "")
            parent = g_perso
            if c:
                if c not in cats:
                    nf = sum(1 for x in perso if x.get("categorie", "") == c and x.get("favori"))
                    cats[c] = groupe(g_perso, "cat:" + c, c)
                    if nf:                           # etoile sur la categorie : elle contient des favoris
                        cats[c].setIcon(0, QIcon(etoile_jaune(11)))
                        cats[c].setToolTip(0, _("{n} favori(s) dans cette catégorie, aussi en tête du volet", n=nf))
                parent = cats[c]
            self._ajout_item_biblio(parent, e["nom"], None, e,
                                    _("Date ajoutée à la pose") if e.get("horodatage", "non") != "non" else None)
        if genre == "tampons":
            g_pre = groupe(None, "predefinis", _("Tampons prêts à l'emploi ({n})", n=len(objets.PREDEFINIS)))
            for nom, t, c in objets.PREDEFINIS:
                pdf = objets.tampon_predefini(t, c, self.params.get("auteur", ""))
                self._ajout_item_biblio(g_pre, nom, pdf, {"nom": nom, "dynamique": True, "texte": t, "couleur": list(c)},
                                        _('Tampon daté : la date est choisie au moment de le poser'))
        if getattr(self, "_reconstruction", False):   # simple mise a jour (renommage ailleurs) : rien d'autre
            return
        self.pile_volet.setCurrentIndex(2)
        self._montrer_volet()
        if not getattr(self, "_ecoute_biblio", None):  # renommage, categorie... faits ailleurs : le volet suit
            from . import bibliotheque as _bib
            self._ecoute_biblio = self._maj_volet_biblio
            _bib.CHANGEMENTS.append(self._ecoute_biblio)
            self.destroyed.connect(lambda *_a, f=self._ecoute_biblio: f in _bib.CHANGEMENTS and _bib.CHANGEMENTS.remove(f))
        if genre == "signatures" and not self.biblio.elements("signatures"):
            self._gerer_biblio()

    def _maj_volet_biblio(self):
        if self.pile_volet.currentIndex() != 2 or not getattr(self, "genre_biblio", None):
            return
        haut = self.liste_biblio.verticalScrollBar().value()
        self._reconstruction = True
        try:
            self.ouvrir_bibliotheque(self.genre_biblio)
        finally:
            self._reconstruction = False
        self.liste_biblio.verticalScrollBar().setValue(haut)

    def _ajout_item_biblio(self, parent, nom, pdf, e, aide=None):
        from PySide6.QtWidgets import QTreeWidgetItem
        pdf = pdf or self.biblio.lire(e)
        pm = QPixmap()
        pm.loadFromData(objets.apercu(pdf, 60), "PNG")
        if e.get("favori") and e.get("id"):
            from .dialogues import avec_etoile
            pm = avec_etoile(pm.scaledToHeight(44, Qt.SmoothTransformation), 11)   # petite etoile, l'apercu reste lisible
        it = QTreeWidgetItem([nom])
        it.setIcon(0, QIcon(pm))
        it.setToolTip(0, nom + (f" — {aide}" if aide else ""))
        it.setData(0, Qt.UserRole, e)
        parent.addChild(it)
        return it

    def _menu_biblio(self, pos):
        """Clic droit sur un tampon ou une signature du volet : ajouter aux favoris ou les retirer."""
        it = self.liste_biblio.itemAt(pos)
        e = it.data(0, Qt.UserRole) if it else None
        if not e or not e.get("id"):
            return
        from PySide6.QtWidgets import QMenu, QInputDialog
        from .dialogues import etoile_jaune, PanneauBibliotheque
        m = QMenu(self)
        a = m.addAction(QIcon(etoile_jaune(16)), _("Retirer des favoris") if e.get("favori") else _("Ajouter aux favoris"))
        a_nom = m.addAction(_("Renommer..."))
        a_cat = m.addAction(_("Catégorie et date...") if self.genre_biblio == "tampons" else _("Catégorie..."))
        a_tr = m.addAction(_("Fond blanc transparent"))
        r = m.exec(self.liste_biblio.viewport().mapToGlobal(pos))
        if r == a_tr:
            try:
                self.biblio.rendre_transparent(e)
            except Exception as ex:
                QMessageBox.warning(self, _("Fond blanc transparent"), _("Impossible : {e}", e=ex))
        if r == a:
            self.biblio.basculer_favori(e)
        elif r == a_nom:
            nom, ok = QInputDialog.getText(self, _('Renommer'), _('Nouveau nom :'), text=e["nom"])
            if ok and nom.strip():
                self.biblio.renommer(e, nom.strip())
        elif r == a_cat:
            p = PanneauBibliotheque(self, self.biblio, self.genre_biblio, self.params.get("auteur", ""))
            p.hide()
            p.courant = lambda: e
            p.proprietes()
            p.deleteLater()
        self._maj_volet_biblio()

    def _memo_groupe(self, it, ouvert):
        cle = it.data(0, Qt.UserRole + 1)
        if not cle:
            return
        r = set(self.params.get("biblio_replies", ["predefinis"]))
        (r.discard if ouvert else r.add)(cle)
        self.params["biblio_replies"] = sorted(r)
        self.params.enregistrer()

    def items_biblio(self):
        """Elements posables de la liste (dans l'ordre affiche), sans les titres de groupes."""
        from PySide6.QtWidgets import QTreeWidgetItemIterator
        out, itr = [], QTreeWidgetItemIterator(self.liste_biblio)
        while itr.value():
            if itr.value().data(0, Qt.UserRole):
                out.append(itr.value())
            itr += 1
        return out

    def _choisir_biblio(self, it, *_col):
        e = it.data(0, Qt.UserRole)
        if not e:                                    # titre de groupe : on ouvre ou on replie
            it.setExpanded(not it.isExpanded())
            return
        if e.get("dynamique") or e.get("horodatage", "non") != "non":
            from .dialogues import tampon_a_poser
            pdf = tampon_a_poser(self, e, self.params.get("auteur", ""), self.biblio)
            if not pdf:
                return
        else:
            pdf = self.biblio.lire(e)
        self.a_poser = (pdf, e["nom"], "signature" if self.genre_biblio == "signatures" else "tampon")
        self.mode = "poser"
        self.bandeau_simple.setText(_('<b>{nom}</b> — cliquez sur la page pour le poser.', nom=e['nom']))
        self.bandeau_simple.show()

    def _gerer_biblio(self):
        d = DialogueBibliotheque(self, self.biblio, self.genre_biblio, self.params.get("auteur", ""))
        ok = d.exec() == QDialog.Accepted
        self.ouvrir_bibliotheque(self.genre_biblio)
        if ok:
            e, pdf = d.choisi()
            if pdf:
                self.a_poser = (pdf, e["nom"], "signature" if self.genre_biblio == "signatures" else "tampon")
                self.mode = "poser"
                self.bandeau_simple.setText(_('<b>{nom}</b> — cliquez sur la page pour le poser.', nom=e['nom']))
                self.bandeau_simple.show()

    def _montrer_volet(self):
        """Format ou bibliotheque demandes : le volet doit etre complet."""
        if getattr(self, "_mode_volet", "complet") != "complet" or self.sp.sizes()[2] == 0:
            self.mode_volet("complet", memoriser=False)

    def maj_info(self):
        if hasattr(self, "lbl_info"):
            self.lbl_info.setText(_('{n} page{x}', n=len(self.doc), x='s' if len(self.doc) > 1 else '')
                                  + (_(" · {x} Ko à l'ouverture", x=self.poids_initial // 1024) if self.poids_initial else "")
                                  + (_(' · modifié, non enregistré') if self.modifie else ""))

    # ------------------------------------------------------------ pages
    def construire_pages(self):
        while self.pages_layout.count():
            it = self.pages_layout.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self.page_widgets = []
        for n in range(len(self.doc)):
            pw = PageWidget(self, n)
            self.page_widgets.append(pw)
            self.pages_layout.addWidget(pw, 0, Qt.AlignHCenter)
        self._vider_caches()
        self.construire_vignettes()
        self.lbl_zoom.setText(f"{round(self.zoom * 100)} %")
        self._page_visible()
        self.maj_info()

    def _vider_caches(self):
        self.__dict__.get("_cache_loupe", {}).clear()
        self._cache_lignes.clear()
        self.__dict__.setdefault("_cache_paras", {}).clear()
        self._cache_mots.clear()
        self._cache_images.clear()

    def _vignette(self, n, taille=120):
        page = self.doc[n]
        k = taille / max(page.rect.width, page.rect.height)
        pm = page.get_pixmap(matrix=fitz.Matrix(k, k).prerotate(self.rotation_vue.get(n, 0)), alpha=False)
        return QPixmap.fromImage(QImage(pm.samples, pm.width, pm.height, pm.stride, QImage.Format_RGB888).copy())

    def _rafraichir_icones_vignettes(self):
        """Vignettes redessinees nettes a la nouvelle taille du volet."""
        for i in range(self.vignettes.count()):
            it = self.vignettes.item(i)
            n = it.data(Qt.UserRole)
            if n is not None and n < len(self.doc):
                it.setIcon(QIcon(self._vignette(n, self._taille_vign)))

    def construire_vignettes(self):
        self.vignettes.clear()
        for n in range(len(self.doc)):
            it = QListWidgetItem(QIcon(self._vignette(n, getattr(self, "_taille_vign", 120))), str(n + 1))
            it.setData(Qt.UserRole, n)
            it.setTextAlignment(Qt.AlignHCenter)
            self.vignettes.addItem(it)
        if self.centre.currentIndex() == 1:
            self._remplir_grille()

    def _rendu_loupe(self, n, hauteur):
        """Image de la page n, hauteur en pixels (loupe des vignettes), avec un petit cache."""
        if not (0 <= n < len(self.doc)):
            return None
        cle = (n, hauteur, self.rotation_vue.get(n, 0))
        cache = self.__dict__.setdefault("_cache_loupe", {})
        if cle not in cache:
            if len(cache) > 12:
                cache.clear()
            page = self.doc[n]
            k = hauteur / max(page.rect.height, 1)
            pm = page.get_pixmap(matrix=fitz.Matrix(k, k).prerotate(self.rotation_vue.get(n, 0)), alpha=False)
            cache[cle] = QImage(pm.samples, pm.width, pm.height, pm.stride, QImage.Format_RGB888).copy()
        return cache[cle]

    def _remplir_grille(self):
        self.grille.clear()
        for n in range(len(self.doc)):
            it = QListWidgetItem(QIcon(self._vignette(n, 200)), str(n + 1))
            it.setData(Qt.UserRole, n)
            self.grille.addItem(it)

    def rafraichir_pages(self, refaire=False):
        if refaire:
            self._vider_caches()
        for pw in self.page_widgets:
            if refaire:
                pw.image = None
            pw.update()

    def page_courante(self):
        y = self.zone.verticalScrollBar().value() + self.zone.viewport().height() // 3
        for pw in self.page_widgets:
            if pw.y() + pw.height() >= y:
                return pw.num
        return len(self.page_widgets) - 1

    def _page_visible(self, *_x):
        if getattr(self, "page_widgets", None):
            if not self.champ_page.hasFocus():
                self.champ_page.setText(str(self.page_courante() + 1))
            self.lbl_page.setText(f"/ {len(self.doc)}")

    def aller_a(self, n, rect=None):
        self.organiser(False) if self.centre.currentIndex() == 1 else None
        pw = self.page_widgets[n]
        y = pw.y()
        if rect is not None:
            y += int(pw.vers_ecran(rect).y()) - self.zone.viewport().height() // 3
        self.zone.verticalScrollBar().setValue(max(0, y))
        self.rafraichir_pages()

    def changer_zoom(self, z):
        self.zoom = max(0.25, min(6.0, z))
        self.params["zoom"] = self.zoom
        for pw in self.page_widgets:
            pw.maj_taille()
        self.lbl_zoom.setText(f"{round(self.zoom * 100)} %")

    # ------------------------------------------------------------ texte
    def lignes_page(self, n):
        if n not in self._cache_lignes:
            out = []
            for b in self.doc[n].get_text("dict")["blocks"]:
                for l in b.get("lines", []):
                    t = "".join(s["text"] for s in l["spans"])
                    if t.strip():
                        out.append((tuple(l["bbox"]), t))
            self._cache_lignes[n] = out
        return self._cache_lignes[n]

    def paragraphes_page(self, n):
        """[(rect, ecrit_par_philpdf)] des paragraphes de plusieurs lignes (trait continu a gauche en mode Modifier)."""
        c = self.__dict__.setdefault("_cache_paras", {})
        if n not in c:
            try:
                c[n] = Editeur(self.doc).paragraphes_page(n)
            except Exception:
                c[n] = []
        return c[n]

    def images_page(self, n):
        if n not in self._cache_images:
            try:
                self._cache_images[n] = Editeur(self.doc).images(n)
            except Exception:
                self._cache_images[n] = []
        return self._cache_images[n]

    def mots(self, n):
        if n not in self._cache_mots:
            self._cache_mots[n] = self.doc[n].get_text("words", sort=True)
        return self._cache_mots[n]

    def mot_sous(self, n, pt):
        for i, w in enumerate(self.mots(n)):
            if fitz.Rect(w[:4]).contains(pt):
                return i
        return None

    def _mot_proche(self, n, pt):
        best, bd = None, 1e9
        for i, w in enumerate(self.mots(n)):
            r = fitz.Rect(w[:4])
            dx = 0 if r.x0 <= pt.x <= r.x1 else min(abs(pt.x - r.x0), abs(pt.x - r.x1))
            dy = 0 if r.y0 <= pt.y <= r.y1 else min(abs(pt.y - r.y0), abs(pt.y - r.y1))
            d = dy * 4 + dx
            if d < bd:
                best, bd = i, d
        return best if bd < 40 else None

    def debut_selection(self, n, pt):
        i = self._mot_proche(n, pt)
        self.selection = {"page": n, "debut": i, "fin": i, "lignes": [], "texte": ""} if i is not None else None
        self._calculer_selection()

    def etendre_selection(self, n, pt):
        if not self.selection or self.selection["page"] != n:
            return
        i = self._mot_proche(n, pt)
        if i is not None:
            self.selection["fin"] = i
            self._calculer_selection()

    def tout_selectionner(self):
        n = self.page_courante()
        if self.mots(n):
            self.selection = {"page": n, "debut": 0, "fin": len(self.mots(n)) - 1, "lignes": [], "texte": ""}
            self._calculer_selection()

    def _calculer_selection(self):
        s = self.selection
        if s:
            a, b = sorted((s["debut"], s["fin"]))
            mots = self.mots(s["page"])[a:b + 1]
            groupes, lignes_txt, prec = {}, [], None
            for w in mots:
                cle = (w[5], w[6])
                groupes.setdefault(cle, fitz.Rect(w[:4]))
                groupes[cle] |= fitz.Rect(w[:4])
                if cle != prec:
                    lignes_txt.append([])
                lignes_txt[-1].append(w[4])
                prec = cle
            s["lignes"] = list(groupes.values())
            s["texte"] = "\n".join(" ".join(x) for x in lignes_txt)
        self.rafraichir_pages()

    def montrer_barre_rapide(self, pw):
        if not self.params.get("barre_rapide", True) or not self.selection or not self.selection["lignes"]:
            return
        r = pw.vers_ecran(self.selection["lignes"][0])
        p = pw.mapTo(self.zone.viewport(), QPoint(int(r.x()), int(r.y())))
        self.barre_rapide.adjustSize()
        x = max(4, min(p.x(), self.zone.viewport().width() - self.barre_rapide.width() - 4))
        y = p.y() - self.barre_rapide.height() - 8
        if y < 4:
            y = p.y() + int(r.height()) + 8
        self.barre_rapide.move(x, y)
        self.barre_rapide.show()
        self.barre_rapide.raise_()

    # ------------------------------------------------------------ objets (annotations, lignes, images)
    def objet_sous(self, n, pt, survol=False):
        page = self.doc[n]
        if self.mode in (None, "modifier", "poser"):
            for a in reversed(list(page.annots())):
                if a.type[0] in DEPLACABLES and fitz.Rect(a.rect).contains(pt):
                    return {"type": "annot", "page": n, "xref": a.xref, "rect": fitz.Rect(a.rect),
                            "philpdf": objets.est_objet_philpdf(a), "garder_proportions": a.type[0] == fitz.PDF_ANNOT_STAMP}
        if self.mode == "modifier":
            for r, t in self.lignes_page(n):
                if fitz.Rect(r).contains(pt):
                    return {"type": "ligne", "page": n, "rect": fitz.Rect(r), "texte": t}
            for xref, r in self.images_page(n):
                if r.contains(pt):
                    return {"type": "image", "page": n, "xref": xref, "rect": fitz.Rect(r), "garder_proportions": True}
        return None

    def choisir_objet(self, obj):
        rt = getattr(self, "retouche", None)
        if rt and not (obj and obj.get("type") == "image" and obj.get("xref") == rt["xref"]):
            self.fermer_retouche()
        self.objet = obj
        if obj and obj["type"] == "image" and self.mode == "modifier" and not getattr(self, "retouche", None):
            self.ouvrir_retouche(obj)
        if obj and obj["type"] == "ligne" and self.mode == "modifier":
            try:
                chars, r, t = Editeur(self.doc).ligne_a(obj["page"], obj["rect"])
                s = chars[0][1]
                self.format_taille.setValue(round(s["size"], 1))
                self.format_couleur = QColor.fromRgbF(*fitz.sRGB_to_pdf(s["color"]))
                self._maj_b_couleur()
                self.format_info.setText(_('<b>{x}</b><br>{font}, {size:.1f} pt', x=t.strip()[:40], font=s['font'], size=s['size']))
            except Exception:
                pass
        self.rafraichir_pages()

    def appliquer_deplacement(self, nouveau):
        obj = self.objet
        if not obj:
            return
        self.memoriser()
        n = obj["page"]
        try:
            if obj["type"] == "annot":
                objets.deplacer(self.doc, n, obj["xref"], nouveau)
                if not obj.get("philpdf"):
                    for a in self.doc[n].annots():
                        if a.xref == obj["xref"]:
                            a.set_rect(nouveau)
                            a.update()
                journal = [_('Objet déplacé.')]
            elif obj["type"] == "ligne":
                d = nouveau.tl - obj["rect"].tl
                ed = Editeur(self.doc)
                ed.deplacer_ligne(n, obj["rect"], d.x, d.y)
                journal = ed.journal
            elif obj["type"] == "image":
                ed = Editeur(self.doc)
                ed.deplacer_image(n, obj["xref"], nouveau)
                journal = ed.journal
        except Exception as e:
            (self.annulations.pop(), self.maj_historique())
            self.message(_('Déplacement impossible : {e}', e=e))
            return
        obj["rect"] = fitz.Rect(nouveau)
        if obj["type"] in ("image",):
            self.objet = None
            if getattr(self, "retouche", None):
                self.fermer_retouche()
        self.apres_modif(journal)
        if obj["type"] == "ligne":
            self.objet = {"type": "ligne", "page": n, "rect": nouveau, "texte": obj["texte"]}
            self.rafraichir_pages()

    def tourner_objet(self, delta):
        """Tourne l'objet choisi autour de son centre : delta en degres, sens inverse des aiguilles d'une montre
        (comme la poignee : vers la gauche = positif). None = remettre droit."""
        obj = self.objet
        if not obj:
            return
        n = obj["page"]
        try:
            if delta is None:                             # angle actuel -> on annule
                if obj["type"] == "annot":
                    delta = -objets.angle_objet(self.doc, obj["xref"])
                elif obj["type"] == "image":
                    delta = -Editeur(self.doc).geometrie_image(n, obj["xref"])[3]
                else:
                    import math
                    l = next((l for b in self.doc[n].get_text("dict")["blocks"] for l in b.get("lines", [])
                              if fitz.Rect(l["bbox"]).intersects(obj["rect"])), None)
                    delta = -math.degrees(math.atan2(-l["dir"][1], l["dir"][0])) if l else 0
                if abs(delta) < 0.05:
                    return
            self.memoriser(_("Rotation"))
            if obj["type"] == "annot":
                if not obj.get("philpdf"):
                    self.annulations.pop()
                    return
                objets.tourner(self.doc, n, obj["xref"], delta)
                obj["rect"] = objets.rect_objet(self.doc, n, obj["xref"])
                journal = [_("Objet tourné.")]
            elif obj["type"] == "image":
                ed = Editeur(self.doc)
                ed.tourner_image(n, obj["xref"], delta)
                obj["rect"] = fitz.Rect(next(r for x, r in ed.images(n) if x == obj["xref"]))
                if getattr(self, "retouche", None):
                    self.retouche["geo"] = ed.geometrie_image(n, obj["xref"])
                journal = ed.journal
            else:
                ed = Editeur(self.doc)
                zones = [obj["rect"]]
                for r, _x in self.paragraphes_page(n):        # ligne d'un paragraphe : tout le bloc tourne
                    if fitz.Rect(r).contains(fitz.Rect(obj["rect"]).tl + (1, 1)):
                        zones = [fitz.Rect(r)]
                        break
                obj["rect"] = ed.tourner_lignes(n, zones, delta)
                journal = ed.journal
        except Exception as e:
            if self.annulations:
                self.annulations.pop()
                self.maj_historique()
            self.message(_("Rotation impossible : {e}", e=e))
            return
        self.apres_modif(journal)
        self.objet = obj
        self.rafraichir_pages()

    def supprimer(self):
        obj = self.objet
        if not obj:
            return
        self.memoriser()
        n = obj["page"]
        if obj["type"] == "annot":
            for a in self.doc[n].annots():
                if a.xref == obj["xref"]:
                    self.doc[n].delete_annot(a)
                    break
        elif obj["type"] == "ligne":
            ed = Editeur(self.doc)
            ed.modifier_ligne(n, obj["rect"], "")
        elif obj["type"] == "image":
            Editeur(self.doc).supprimer_image(n, obj["xref"])
        self.objet = None
        self.apres_modif([_('Objet supprimé.')])

    def remplacer_image(self):
        obj = self.objet
        if not obj or obj["type"] != "image":
            self.message(_("Sélectionnez d'abord une image (mode Modifier)."))
            return
        f, _x = QFileDialog.getOpenFileName(self, _('Nouvelle image'), "", _('Images (*.png *.jpg *.jpeg *.bmp *.tif)'))
        if f:
            self.memoriser()
            Editeur(self.doc).remplacer_image(obj["page"], obj["xref"], obj["rect"], f)
            self.objet = None
            self.apres_modif([_('Image remplacée.')])

    def editer_annotation(self, obj):
        for a in self.doc[obj["page"]].annots():
            if a.xref == obj["xref"] and not obj.get("philpdf"):
                t, ok = QInputDialog.getMultiLineText(self, _('Commentaire'), _('Texte :'), a.info.get("content", ""))
                if ok:
                    self.memoriser()
                    a.set_info(content=t)
                    a.update()
                    self.apres_modif()

    def menu_contexte(self, pw, pt, pos_globale):
        if self.mode in (None, "formulaire", "signer_num", "champ_signature"):
            w_ = self.champ_sous(pw.num, pt)
            if w_ is not None:
                self.menu_champ(pw, w_, pos_globale)
                return
        obj = self.objet_sous(pw.num, pt)
        if obj:
            self.choisir_objet(obj)
        m = QMenu(self)
        ax = self.annot_texte_sous(pw.num, pt) if not self.objet else None
        if self.selection and not self.objet:
            s = self.selection
            m.addAction(icone("copier"), _('Copier'), self.copier)
            m.addSeparator()
            m.addAction(icone("surligner"), _('Surligner'), lambda: self.annoter("surligner"))
            m.addAction(icone("souligner"), _('Souligner'), lambda: self.annoter("souligner"))
            m.addAction(icone("souligner"), _('Souligner (ondulé)'), lambda: self.annoter("ondule"))
            m.addAction(icone("barrer"), _('Barrer'), lambda: self.annoter("barrer"))
            m.addAction(icone("commentaire"), _('Ajouter une note'), lambda: self.annoter("note"))
            m.addAction(_('Couleurs et style...'), lambda: self.menu_style_annotations(pos_globale))
            m.addSeparator()
            m.addAction(icone("modifier"), _('Modifier le texte'), self.modifier_selection)
            texte = s["texte"].strip().split("\n")[0][:40]
            if texte:
                m.addAction(icone("rechercher"), _('Rechercher « {t} »', t=texte), lambda: self.rechercher_texte(texte))
            m.addAction(icone("biffer"), _('Biffer (effacer pour de vrai)'), self.biffer)
            m.exec(pos_globale)
            return
        if ax is not None:
            m.addAction(_("Couleur et style de l'annotation..."),
                        lambda: self.menu_style_annotations(pos_globale, ax, pw.num))
            m.addAction(icone("fermer", "#c9252d"), _("Supprimer l'annotation"), lambda: self._supprimer_annot(pw.num, ax))
            m.addSeparator()
        if self.objet:
            m.addAction(icone("copier"), _('Copier'), self.copier)
            m.addAction(_('Couper'), self.couper)
            m.addAction(icone("fermer", "#c9252d"), _('Supprimer'), self.supprimer)
            if self.objet["type"] in ("image", "ligne") or (self.objet["type"] == "annot" and self.objet.get("philpdf")):
                m.addAction(icone("pivoter", "#444444"), _("Tourner de 90° à droite"), lambda: self.tourner_objet(-90))
                m.addAction(_("Tourner de 90° à gauche"), lambda: self.tourner_objet(90))
                m.addAction(_("Remettre droit"), lambda: self.tourner_objet(None))
            if self.objet["type"] == "image":
                m.addAction(_("Remplacer l'image..."), self.remplacer_image)
            if self.objet["type"] == "ligne":
                m.addAction(_('Corriger dans la page'), lambda: pw.ouvrir_editeur(self.objet["rect"], None, self.objet["texte"]))
            m.addSeparator()
        m.addAction(_('Coller'), lambda: self.coller(pw.num, pt))
        m.addAction(_('Ajouter du texte ici'), lambda: pw.ouvrir_editeur(None, pt))
        m.exec(pos_globale)

    def _supprimer_annot(self, n, xref):
        page = self.doc[n]
        a = next((x for x in page.annots() if x.xref == xref), None)
        if a:
            self.memoriser(_("Suppression d'une annotation"))
            page.delete_annot(a)
            self.apres_modif()

    def rechercher_texte(self, texte):
        """Ouvre Rechercher et remplacer avec le texte selectionne (la selection est encore active)."""
        self.outil_demande.emit("remplacer")

    # ---- presse-papiers
    def copier(self):
        if self.objet:
            obj = self.objet
            if obj["type"] == "ligne":
                QGuiApplication.clipboard().setText(obj["texte"].strip())
            elif obj["type"] == "annot":
                pdf = self.objets_pdf.get(obj["xref"])
                if pdf is None:  # objet venu du fichier : on le recopie en image
                    page = self.doc[obj["page"]]
                    pm = page.get_pixmap(clip=obj["rect"], dpi=200, annots=True)
                    pdf = (objets.pdf_depuis_image(pm.tobytes("png"), True), _('Objet'), "tampon")
                self.presse_objet = (pdf, fitz.Rect(obj["rect"]))
            elif obj["type"] == "image":
                info = self.doc.extract_image(obj["xref"])
                self.presse_objet = (("image", info["image"]), fitz.Rect(obj["rect"]))
            self.message(_('Copié.'))
        elif self.selection:
            QGuiApplication.clipboard().setText(self.selection["texte"])
            self.message(_('Texte copié.'))

    def couper(self):
        if self.objet:
            self.copier()
            self.supprimer()

    def coller(self, n=None, pt=None):
        n = self.page_courante() if n is None else n
        po = getattr(self, "presse_objet", None)
        if po:
            data, r = po
            dec = 20
            cible = fitz.Rect(r) + (dec, dec, dec, dec) if pt is None else fitz.Rect(pt.x, pt.y, pt.x + r.width, pt.y + r.height)
            self.memoriser()
            if data[0] == "image":
                self.doc[n].insert_image(cible, stream=data[1])
            else:
                pdf, nom, genre = data
                x = objets.poser(self.doc, n, cible, pdf, nom, self.params.get("auteur", ""), genre)
                self.objets_pdf[x] = data
            self.apres_modif([_('Collé.')])
            return
        t = QGuiApplication.clipboard().text()
        if t:
            page = self.doc[n]
            pt = pt or fitz.Point(page.rect.width * 0.15, page.rect.height * 0.3)
            self.ajouter_texte(n, pt, t.splitlines()[0], self.format_taille.value(), None, None)

    # ------------------------------------------------------------ actions texte
    def annoter(self, genre):
        s = self.selection
        if not s:
            return
        self.memoriser()
        page = self.doc[s["page"]]
        coul = self.couleurs_annot()
        if genre == "surligner":
            a = page.add_highlight_annot(s["lignes"])
        elif genre == "souligner" and self.params.get("style_souligne") == "ondule":
            a = page.add_squiggly_annot(s["lignes"])
        elif genre == "souligner":
            a = page.add_underline_annot(s["lignes"])
        elif genre == "ondule":
            a = page.add_squiggly_annot(s["lignes"])
        elif genre == "barrer":
            a = page.add_strikeout_annot(s["lignes"])
        else:
            txt, ok = QInputDialog.getMultiLineText(self, _('Note'), _('Texte de la note :'))
            if not ok:
                (self.annulations.pop(), self.maj_historique())
                return
            r = s["lignes"][-1]
            a = page.add_text_annot(fitz.Point(r.x1 + 2, r.y0), txt, icon="Comment")
        a.set_info(title=self.params.get("auteur") or self.params["machine"])
        if genre in ("surligner", "souligner", "ondule", "barrer"):
            a.set_colors(stroke=_rgb(coul["souligner" if genre == "ondule" else genre]))
            a.set_opacity(float(self.params.get("opacite_surlignage", 1.0)) if genre == "surligner" else 1.0)
        a.update()
        self.selection = None
        self.apres_modif()

    # ---- couleurs et styles des annotations de texte
    COULEURS_DEFAUT = {"surligner": "#ffe600", "souligner": "#0f6cbd", "barrer": "#d32f2f"}

    def couleurs_annot(self):
        return dict(self.COULEURS_DEFAUT, **(self.params.get("couleurs_annotations") or {}))

    def menu_style_annotations(self, pos, annot_xref=None, n=None):
        """Menu : couleur de chaque genre, style du souligne ; sur une annotation existante : la changer."""
        m = QMenu(self)
        palette = [("#ffe600", _("Jaune")), ("#7ee36e", _("Vert")), ("#6ec8ff", _("Bleu clair")), ("#ff9de0", _("Rose")),
                   ("#ffa94d", _("Orange")), ("#0f6cbd", _("Bleu")), ("#d32f2f", _("Rouge")), ("#000000", _("Noir"))]

        def pastille(c):
            pm = QPixmap(16, 16)
            pm.fill(QColor(c))
            return QIcon(pm)
        if annot_xref is not None:
            for c, nom in palette:
                m.addAction(pastille(c), nom, lambda c=c: self.recolorer_annot(n, annot_xref, c))
            m.addAction(_("Autre couleur..."), lambda: self._autre_couleur(lambda c: self.recolorer_annot(n, annot_xref, c)))
            m.addSeparator()
            for g, lib in (("surligner", _("Surligné")), ("souligner", _("Souligné")), ("ondule", _("Souligné ondulé")),
                           ("barrer", _("Barré"))):
                m.addAction(lib, lambda g=g: self.transformer_annot(n, annot_xref, g))
        else:
            for g, lib in (("surligner", _("Surlignage")), ("souligner", _("Soulignement")), ("barrer", _("Barré"))):
                sm = m.addMenu(pastille(self.couleurs_annot()[g]), lib)
                for c, nom in palette:
                    sm.addAction(pastille(c), nom, lambda g=g, c=c: self._fixer_couleur(g, c))
                sm.addAction(_("Autre couleur..."), lambda g=g: self._autre_couleur(lambda c: self._fixer_couleur(g, c)))
            m.addSeparator()
            st = m.addMenu(_("Style du soulignement"))
            for v, lib in (("droit", _("Trait droit")), ("ondule", _("Ondulé"))):
                a = st.addAction(lib, lambda v=v: (self.params.__setitem__("style_souligne", v), self.params.enregistrer()))
                a.setCheckable(True)
                a.setChecked(self.params.get("style_souligne", "droit") == v)
            op = m.addMenu(_("Opacité du surlignage"))
            for v in (1.0, 0.6, 0.35):
                a = op.addAction(f"{int(v * 100)} %", lambda v=v: (self.params.__setitem__("opacite_surlignage", v), self.params.enregistrer()))
                a.setCheckable(True)
                a.setChecked(abs(float(self.params.get("opacite_surlignage", 1.0)) - v) < 0.01)
        m.exec(pos)

    def _autre_couleur(self, suite):
        from PySide6.QtWidgets import QColorDialog
        c = QColorDialog.getColor(parent=self)
        if c.isValid():
            suite(c.name())

    def _fixer_couleur(self, genre, c):
        d = dict(self.params.get("couleurs_annotations") or {})
        d[genre] = c
        self.params["couleurs_annotations"] = d
        self.params.enregistrer()
        self.barre_rapide.maj_couleur()

    def annot_texte_sous(self, n, pt):
        for a in self.doc[n].annots(types=[fitz.PDF_ANNOT_HIGHLIGHT, fitz.PDF_ANNOT_UNDERLINE, fitz.PDF_ANNOT_STRIKE_OUT,
                                           fitz.PDF_ANNOT_SQUIGGLY]):
            if fitz.Rect(a.rect).contains(pt):
                return a.xref
        return None

    def recolorer_annot(self, n, xref, c):
        page = self.doc[n]
        a = next((x for x in page.annots() if x.xref == xref), None)
        if a:
            self.memoriser(_("Couleur de l'annotation"))
            a.set_colors(stroke=_rgb(c))
            a.update()
            self.apres_modif()

    def transformer_annot(self, n, xref, genre):
        page = self.doc[n]
        a = next((x for x in page.annots() if x.xref == xref), None)
        if not a:
            return
        self.memoriser(_("Style de l'annotation"))
        quads = a.vertices
        coul = a.colors.get("stroke")
        info = a.info
        page.delete_annot(a)
        q = [fitz.Quad(quads[i:i + 4]) for i in range(0, len(quads), 4)] if quads else []
        f = {"surligner": page.add_highlight_annot, "souligner": page.add_underline_annot,
             "ondule": page.add_squiggly_annot, "barrer": page.add_strikeout_annot}[genre]
        b = f(q)
        if coul:
            b.set_colors(stroke=coul)
        b.set_info(title=info.get("title", ""))
        b.update()
        self.apres_modif()

    def biffer(self):
        """Barre rapide : le texte selectionne est marque, puis on propose d'appliquer."""
        self.changer_mode("biffer")
        if self.marques_biffage:
            self.appliquer_biffage()

    def _maj_biffer(self):
        n = len(self.marques_biffage)
        self.lbl_biffer.setText(_("<b>Biffer</b> — tracez un rectangle sur ce qui doit disparaître (texte, image, "
                                  "signature...). {n} zone(s) marquée(s).", n=n))
        self.b_appliquer_biffage.setEnabled(n > 0)
        self.rafraichir_pages()

    def appliquer_biffage(self):
        if not self.marques_biffage:
            return
        if question(self, _('Biffer'), _("Les {n} zone(s) marquée(s) seront supprimées définitivement du fichier (texte, images "
                                         "et dessins) et remplacées par un rectangle noir. Continuer ?",
                                         n=len(self.marques_biffage)),
                    [(_('Biffer'), QMessageBox.AcceptRole), (_('Annuler'), QMessageBox.RejectRole)]) != 0:
            return
        self.memoriser(_("Biffage"))
        pages = sorted({n for n, _r in self.marques_biffage})
        for n, r in self.marques_biffage:
            self.doc[n].add_redact_annot(r, fill=(0, 0, 0))
        for n in pages:
            self.doc[n].apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS,
                                         graphics=getattr(fitz, "PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED", 2))
        nb = len(self.marques_biffage)
        self.marques_biffage.clear()
        self.changer_mode(None)
        self.apres_modif([_("{n} zone(s) biffée(s) : leur contenu n'existe plus dans le fichier.", n=nb)])

    def modifier_selection(self):
        s = self.selection
        if not s:
            return
        n = s["page"]
        self.selection = None
        self.changer_mode("modifier")
        pw = self.page_widgets[n]
        r0 = fitz.Rect(s["lignes"][0])
        if pw.ouvrir_paragraphe(fitz.Point(r0.x0 + 1, (r0.y0 + r0.y1) / 2)):
            return
        for r, t in self.lignes_page(n):
            if fitz.Rect(r).intersects(s["lignes"][0]):
                pw.ouvrir_editeur(fitz.Rect(r), None, t)
                return

    def modifier_ligne_texte(self, n, rect, texte, taille=None, couleur=None):
        self.memoriser()
        ed = Editeur(self.doc)
        try:
            ed.modifier_ligne(n, rect, texte, taille, couleur)
        except ValueError as e:
            (self.annulations.pop(), self.maj_historique())
            self.message(str(e))
            return
        self.objet = None
        self.apres_modif(ed.journal or [_('Aucun changement.')])

    def modifier_paragraphe(self, n, para, texte, taille=None, couleur=None, police=None):
        self.memoriser(_("Modification d'un paragraphe"))
        ed = Editeur(self.doc)
        try:
            res = ed.modifier_paragraphe(n, para, texte, taille, couleur, police)
        except Exception as e:
            (self.annulations.pop(), self.maj_historique())
            self.message(_("Modification impossible : {e}", e=e))
            return
        if res is None:
            (self.annulations.pop(), self.maj_historique())
            return
        self.objet = None
        self.apres_modif(ed.journal)
        if res["en_plus"] > 0:                     # le texte descend : touche-t-il ce qui est en dessous ?
            bas_avant = para["rect"].y1
            dessous = [l for l in ed._infos_lignes(self.doc[n]) if bas_avant + 1 < l["base"] <= res["bas"] + 2
                       and min(l["x1"], para["x1"]) - max(l["x0"], para["x0"]) > 5
                       and not any(abs(l["base"] - b) < 0.5 for b in [para["lignes"][0]["base"] + i * para["interligne"]
                                                                   for i in range(res["lignes"])])]
            if dessous:
                QMessageBox.information(self, _("Modifier"), _(
                    "Le paragraphe a maintenant {n} ligne(s) de plus et déborde sur le texte en dessous. "
                    "Elargissez la zone (poignée à droite), réduisez la taille ou raccourcissez le texte ; Ctrl+Z annule.",
                    n=res["en_plus"]))

    def ajouter_paragraphe(self, n, coin, texte, largeur, taille=None, couleur=None, police=None):
        self.memoriser(_("Ajout de texte"))
        ed = Editeur(self.doc)
        police = police or self.format_police.currentData()
        coul = couleur or self.format_couleur.getRgbF()[:3]
        ed.ajouter_paragraphe(n, coin, texte, largeur, taille or self.format_taille.value(), coul, police)
        self.apres_modif(ed.journal)

    def appliquer_format(self):
        obj = self.objet
        if not obj or obj["type"] != "ligne":
            self.message(_("Sélectionnez d'abord une ligne (mode Modifier)."))
            return
        self.modifier_ligne_texte(obj["page"], obj["rect"], obj["texte"].rstrip(), self.format_taille.value(),
                                  self.format_couleur.getRgbF()[:3])

    def ajouter_texte(self, n, pt, texte, taille=None, couleur=None, police=None):
        self.memoriser()
        ed = Editeur(self.doc)
        police = police or self.format_police.currentData()
        coul = couleur or (self.format_couleur.getRgbF()[:3] if self.format_police.currentData() else None)
        ed.ajouter_texte(n, pt, texte, taille, coul, police)
        self.apres_modif(ed.journal)
        self.changer_mode("modifier")

    def ajouter_image_ici(self, n, pt):
        f = getattr(self, "image_a_ajouter", None)
        if not f:
            return
        self.memoriser()
        pix = fitz.Pixmap(f)
        w = min(200, self.doc[n].rect.width / 3)
        h = w * pix.height / pix.width
        self.doc[n].insert_image(fitz.Rect(pt.x, pt.y, pt.x + w, pt.y + h), filename=f)
        self.image_a_ajouter = None
        self.apres_modif([_('Image ajoutée : sélectionnez-la pour la déplacer ou la redimensionner.')])
        self.changer_mode("modifier")

    def zone_tracee(self, n, r):
        page = self.doc[n]
        if self.mode == "formulaire":
            self.ajouter_champ(n, fitz.Rect(r))
            return
        if self.mode == "champ_signature":
            self.ajouter_champ_signature(n, fitz.Rect(r))
            return
        if self.mode == "signer_num":
            r = fitz.Rect(r)
            if r.width < 40 or r.height < 14:
                r = fitz.Rect(r.x0, r.y0, r.x0 + 180, r.y0 + 45)
            if self.signer_numerique(None, n, r):
                self.changer_mode(None)
            return
        if self.mode == "biffer":
            self.marques_biffage.append((n, fitz.Rect(r)))
            self._maj_biffer()
            return
        if self.mode == "lien":
            choix = question(self, _('Lien'), _('Ce lien mène vers :'), [(_('Un site Internet'), QMessageBox.AcceptRole),
                                                                  (_('Une page du document'), QMessageBox.AcceptRole),
                                                                  (_('Annuler'), QMessageBox.RejectRole)])
            if choix == 0:
                url, ok = QInputDialog.getText(self, _('Lien'), _('Adresse :'), text="https://")
                if ok and url:
                    self.memoriser(_("Ajout d'un lien"))
                    page.insert_link({"kind": fitz.LINK_URI, "from": r, "uri": url})
                    self.apres_modif([_('Lien ajouté.')])
            elif choix == 1:
                num, ok = QInputDialog.getInt(self, _('Lien'), _('Page :'), 1, 1, len(self.doc))
                if ok:
                    self.memoriser(_("Ajout d'un lien"))
                    page.insert_link({"kind": fitz.LINK_GOTO, "from": r, "page": num - 1, "to": fitz.Point(0, 0)})
                    self.apres_modif([_('Lien ajouté.')])
        elif self.mode == "recadrer":
            choix = question(self, _('Recadrer'), _('Recadrer :'), [(_('Cette page'), QMessageBox.AcceptRole),
                                                            (_('Toutes les pages'), QMessageBox.AcceptRole),
                                                            (_('Annuler'), QMessageBox.RejectRole)])
            if choix in (0, 1):
                self.memoriser(_('Recadrage'))
                for p in ([page] if choix == 0 else list(self.doc)):
                    zone = (fitz.Rect(r) + (p.cropbox.x0, p.cropbox.y0, p.cropbox.x0, p.cropbox.y0)) & p.mediabox
                    p.set_cropbox(zone)
                self.apres_modif([_('Pages recadrées.')], reconstruire=True)
        self.changer_mode("modifier")

    # ---- formulaire : creer et remplir des champs
    def champ_sous(self, n, pt):
        page = self.doc[n]
        for w in page.widgets():
            if fitz.Rect(w.rect).contains(pt):
                w._page_vivante = page                 # garde la page en vie tant qu'on utilise le champ
                return w
        return None

    def nb_champs(self):
        return sum(1 for p in self.doc for _w in p.widgets())

    def _maj_form(self):
        self.lbl_form.setText(_("<b>Formulaire</b> — {n} champ(s). Tracez un rectangle pour ajouter un champ du type "
                                "choisi ; double-clic sur un champ : ses propriétés (format, date automatique, calcul, "
                                "listes...) ; clic droit : dupliquer, renommer, supprimer...", n=self.nb_champs()))

    def detecter_champs(self):
        from moteur import formulaire as FO
        trouves = {}
        for i, p in enumerate(self.doc):
            c = FO.detecter(p)
            if c:
                trouves[i] = c
        tous = [c for l in trouves.values() for c in l]
        if not tous:
            QMessageBox.information(self, _("Formulaire"), _("Aucune zone à remplir détectée. Tracez les champs à la main."))
            return
        FO.noms_uniques(tous)
        self.memoriser(_("Création d'un formulaire"))
        typer = self.params.get("formulaire_types_auto", True)
        a_typer, signatures = {}, []
        if typer:
            for num, l in trouves.items():
                for c in list(l):
                    g, reg = FO.deviner(c["nom"])
                    if g == "signature" and c["genre"] == "texte" and c["rect"].height >= 10:
                        l.remove(c)
                        signatures.append((num, c))
                    elif reg and c["genre"] == "texte":
                        a_typer[c["nom"]] = reg
        n = FO.creer(self.doc, trouves)
        for num, c in signatures:                        # « Signature : ____ » -> vrai champ de signature
            r = fitz.Rect(c["rect"])
            if r.height < 30:
                r = fitz.Rect(r.x0, r.y1 - 30, r.x1, r.y1)
            w = fitz.Widget()
            w.field_type = fitz.PDF_WIDGET_TYPE_SIGNATURE
            w.field_name = c["nom"] or "Signature"
            w.rect = r
            self.doc[num].add_widget(w)
            n += 1
        if signatures:
            FO.normaliser(self.doc)
        from moteur import champs as _C
        types = 0
        for nom, reg in a_typer.items():
            w = self._widget_nom(nom)
            if w is not None:
                _C.ecrire(self.doc, w, dict(_C.vide(), **reg))
                types += 1
        if types:
            _C.generer_js(self.doc)
        self.apres_modif([_("{n} champ(s) créé(s) : vérifiez-les, renommez ou supprimez ceux qui ne conviennent pas.", n=n)
                          + ((" " + _("{t} reconnu(s) d'après leur libellé (date, montant, téléphone, e-mail, signature...) : "
                                      "double-clic pour changer.", t=types + len(signatures))) if types or signatures else "")])
        self._maj_form()
        self.verifier_signatures() if signatures else None

    def ajouter_champ(self, n, r):
        genre = self.type_trace.currentData() if hasattr(self, "type_trace") else "auto"
        if genre != "auto":
            self.creer_champ_type(n, fitz.Rect(r), genre)
            return
        from moteur import formulaire as FO
        case = r.width <= 20 and r.height <= 20
        if case:
            cote = max(r.width, r.height)
            r = fitz.Rect(r.x0, r.y0, r.x0 + cote, r.y0 + cote)
        propose = FO._libelle(self.doc[n], r, self.doc[n].get_text("words"), case)
        nom, ok = QInputDialog.getText(self, _("Nouveau champ"), _("Nom du champ :"), text=propose)
        if not ok or not nom.strip():
            return
        g_, reg_ = FO.deviner(nom) if (not case and self.params.get("formulaire_types_auto", True)) else (None, None)
        if g_ == "signature":
            self.ajouter_champ_signature(n, r)
            return
        self.memoriser(_("Ajout du champ « {nom} »", nom=nom.strip()))
        FO.creer(self.doc, {n: [{"genre": "case" if case else "texte", "rect": r, "nom": nom.strip(), "lignes": r.height > 30}]})
        if reg_:
            from moteur import champs as _C
            w_ = self._widget_nom(nom.strip())
            if w_ is not None:
                _C.ecrire(self.doc, w_, dict(_C.vide(), **reg_))
                _C.generer_js(self.doc)
        self.apres_modif([_("Champ « {nom} » ajouté.", nom=nom.strip())])
        self._maj_form()

    def _widget(self, ref):
        if not ref:
            return None
        n, x = ref
        page = self.doc[n]
        w = next((w for w in page.widgets() if w.xref == x), None)
        if w is not None:
            w._page_vivante = page
        return w

    def supprimer_champ(self):
        w = self._widget(self.champ_choisi)
        if not w:
            return
        self.memoriser(_("Suppression du champ « {nom} »", nom=w.field_name))
        self.doc[self.champ_choisi[0]].delete_widget(w)
        self.champ_choisi = None
        self.apres_modif([_("Champ supprimé.")])
        self._maj_form()

    def renommer_champ(self):
        w = self._widget(self.champ_choisi)
        if not w:
            return
        nom, ok = QInputDialog.getText(self, _("Renommer le champ"), _("Nom du champ :"), text=w.field_name)
        if ok and nom.strip() and nom.strip() != w.field_name:
            self.memoriser(_("Renommage du champ « {nom} »", nom=w.field_name))
            w.field_name = nom.strip()
            w.field_label = nom.strip()
            w.update()
            self.apres_modif([_("Champ renommé.")])

    def remplir_champ(self, pw, w):
        """Clic sur un champ hors mode formulaire : case cochee/decochee, texte saisi sur place."""
        w = self._widget((pw.num, w.xref)) or w
        if w.field_type == fitz.PDF_WIDGET_TYPE_BUTTON:
            self.clic_bouton(w)
            return
        if self.champ_verrouille(w):
            self.message(_("Le champ « {x} » est verrouillé par une signature : le modifier invaliderait la signature.",
                           x=w.field_name))
            return
        if w.field_flags & fitz.PDF_FIELD_IS_READ_ONLY:
            self.message(_("Le champ « {x} » est en lecture seule.", x=w.field_name))
            return
        if w.field_type == fitz.PDF_WIDGET_TYPE_RADIOBUTTON:
            self.memoriser(_("Remplissage du formulaire"))
            self.choisir_radio(w)
            self._apres_valeur(w.field_name)
            self.apres_modif([])
            return
        if w.field_type == fitz.PDF_WIDGET_TYPE_CHECKBOX:
            self.memoriser(_("Remplissage du formulaire"))
            on = w.on_state() if hasattr(w, "on_state") else True
            w.field_value = False if w.field_value not in (False, "Off", "", None) else (on or True)
            self._maj_widget(w)
            self._apres_valeur(w.field_name)
            self.apres_modif([])
            return
        if w.field_type in (fitz.PDF_WIDGET_TYPE_TEXT, fitz.PDF_WIDGET_TYPE_COMBOBOX, fitz.PDF_WIDGET_TYPE_LISTBOX):
            if self.regles_champ(w).get("calcul"):
                self.message(_("Le champ « {x} » est calculé automatiquement.", x=w.field_name))
                return
            if self.valeur_auto(w):
                w = self._widget((pw.num, w.xref)) or w
            self.aide_entree(pw, w)
            pw.ouvrir_saisie_champ(w)
            ed = getattr(pw, "saisie", None)
            if ed is not None and getattr(self, "_bulle_aide", None) is not None:
                try:                                       # la bulle part avec la zone de saisie
                    ed.destroyed.connect(self.fermer_bulle_aide)
                except (RuntimeError, AttributeError):
                    pass

    def choisir_radio(self, w):
        """Coche ce bouton radio, decoche les autres du groupe (un seul choix)."""
        etat = w.on_state()
        groupe = self._widgets_nom(w.field_name)
        deja = self.doc.xref_get_key(w.xref, "AS")[1] == "/" + etat
        for x in groupe:
            self.doc.xref_set_key(x.xref, "AS", "/" + etat if (x.xref == w.xref and not deja) else "/Off")
        from moteur import champs as _C
        fx = _C.xref_champ(self.doc, w)
        self.doc.xref_set_key(fx, "V", "/Off" if deja else "/" + etat)

    def valeur_champ(self, n, xref, valeur):
        w = self._widget((n, xref))
        if w is None:
            return
        if w.field_type == fitz.PDF_WIDGET_TYPE_TEXT or w.field_type == fitz.PDF_WIDGET_TYPE_COMBOBOX:
            valeur = self.saisir_valeur(w, valeur)
            if valeur is None:
                return
            if not (valeur or "").strip():                 # message « si on le laisse vide », comme Acrobat
                self.aide_sortie(n, w)
        if (w.field_value or "") == valeur:
            return
        self.memoriser(_("Remplissage du formulaire"))
        self._ecrire_valeur(w, valeur)
        self._apres_valeur(w.field_name)
        self.apres_modif([])

    # cles de presentation que PyMuPDF reecrit au passage (bordure...) : remplir ne doit changer que la valeur et
    # l'apparence, sinon Acrobat compte une « autre modification » apres une signature
    _PRESENTATION = ("BS", "MK", "Border")

    def _maj_widget(self, w):
        avant = {}
        for k in self._PRESENTATION:
            try:
                avant[k] = self.doc.xref_get_key(w.xref, k)
            except Exception:                             # noqa: BLE001
                pass
        from moteur import apparence as _AP
        texte = w.field_type in (fitz.PDF_WIDGET_TYPE_TEXT, fitz.PDF_WIDGET_TYPE_COMBOBOX)
        da0 = _AP.lire_da(self.doc, w) if texte else None
        w.update()
        if texte and da0 and da0[0] not in _AP.PYMUPDF:  # police que PyMuPDF remplacerait par Helvetica
            try:
                _AP.ecrire_da(self.doc, w, *da0)
                _AP.dessiner(self.doc, w)
            except Exception:
                pass
        if w.field_type in (fitz.PDF_WIDGET_TYPE_CHECKBOX, fitz.PDF_WIDGET_TYPE_RADIOBUTTON):
            from moteur import formulaire as _FO           # garde le style et la couleur de la coche, sans police
            try:
                _FO.dessiner_case(self.doc, w)
            except Exception:
                pass
        if w.field_type == fitz.PDF_WIDGET_TYPE_BUTTON:
            from .formulaire_doc import dessiner_bouton
            dessiner_bouton(self.doc, w)
        for k, (t, v) in avant.items():
            try:
                if self.doc.xref_get_key(w.xref, k) != (t, v):
                    self.doc.xref_set_key(w.xref, k, "null" if t == "null" else v)
            except Exception:                             # noqa: BLE001
                pass

    # ---- envoi par e-mail (volet de droite)
    def montrer_envoi(self, fenetre):
        if getattr(self, "panneau_envoi", None) is None:
            from .dialogues_courriel import PanneauEnvoyer
            self.panneau_envoi = PanneauEnvoyer(self, fenetre)
            self._idx_volet_envoi = self.pile_volet.addWidget(self.panneau_envoi)
        else:
            self.panneau_envoi.oublier()
            self.panneau_envoi._maj()
        self.pile_volet.setCurrentIndex(self._idx_volet_envoi)
        self._montrer_volet()
        if self.volet.isHidden():
            self.mode_volet("complet", memoriser=False)
        self.panneau_envoi.a.setFocus()

    # ---- IA sur un paragraphe
    def reformuler_ia(self):
        """Paragraphe selectionne ouvert en edition, menu IA deja deroule ; sinon, explique comment faire."""
        sel = self.selection
        if self.mode != "modifier":
            self.changer_mode("modifier")
        if sel and sel.get("debut") is not None and self.mots(sel["page"]):
            n = sel["page"]
            w = self.mots(n)[sel["debut"]]
            pw = self.page_widgets[n]
            if pw.ouvrir_paragraphe(fitz.Point((w[0] + w[2]) / 2, (w[1] + w[3]) / 2)) and pw.editeur:
                b = pw.editeur.fmt.findChild(QPushButton, "b_ia_paragraphe")
                if b is not None:
                    QTimer.singleShot(150, b.showMenu)
                return
        self.message(_("Cliquez sur le paragraphe à corriger ou reformuler, puis sur « ✦ IA » au-dessus du texte."))

    # ---- paraphe
    def parapher(self):
        from .dialogues_organiser import DialogueParaphe
        from moteur import paraphe as PA
        d = DialogueParaphe(self)
        if not d.exec():
            return
        pdf, pages, position, hauteur, marge = d.resultat
        self.memoriser(_("Paraphe sur {n} page(s)", n=len(pages)))
        avant = {n: {a.xref for a in self.doc[n].annots()} for n in pages}
        PA.parapher(self.doc, pdf, pages, position, hauteur, marge, self.params.get("auteur", ""), _("Paraphe"))
        for n in pages:
            for a in self.doc[n].annots():
                if a.xref not in avant[n]:
                    self.objets_pdf[a.xref] = (pdf, _("Paraphe"), "paraphe")
        self.apres_modif([_("{n} page(s) paraphée(s). Chaque paraphe se déplace ou se supprime comme un tampon ; "
                            "Ctrl+Z annule tout.", n=len(pages))])

    # ---- poser tampon / signature
    def poser_objet(self, n, pt):
        if not self.a_poser:
            return
        pdf, nom, genre = self.a_poser
        w, h = self._taille_objet()
        self.memoriser(_("Pose de « {nom} »", nom=nom))
        r = fitz.Rect(pt.x, pt.y, pt.x + w, pt.y + h)
        x = objets.poser(self.doc, n, r, pdf, nom, self.params.get("auteur", ""), genre)
        self.objets_pdf[x] = (pdf, nom, genre)
        self.mode = None
        self.bandeau_simple.hide()
        self.apres_modif([_("« {nom} » est en place : glissez pour déplacer, poignées pour la taille, Suppr pour enlever.", nom=nom)])
        for a in self.doc[n].annots():
            if a.xref == x:
                self.choisir_objet({"type": "annot", "page": n, "xref": x, "rect": fitz.Rect(a.rect),
                                    "philpdf": True, "garder_proportions": True})

    def _taille_objet(self):
        pdf, nom, genre = self.a_poser
        w, h = objets.taille_naturelle(pdf)
        k = min(1.0, (220 if genre == "signature" else 180) / max(w, 1))
        return w * k, h * k

    def fantome(self, n, pt):
        """(rect, pixmap, texte, taille) de ce qui sera pose en cliquant en pt, ou None.
        Le coin haut gauche suit la souris ; le cadre reste dans la page."""
        page = self.doc[n].rect
        pix = texte = None
        taille = 0
        if self.mode == "poser" and self.a_poser:
            w, h = self._taille_objet()
            cle = id(self.a_poser[0])
            if getattr(self, "_fantome_cle", None) != cle:
                im = QPixmap()
                im.loadFromData(objets.apercu(self.a_poser[0], hauteur=max(40, int(h * 2))))
                self._fantome_cle, self._fantome_pix = cle, im
            pix = self._fantome_pix
        elif self.mode == "ajout_texte":
            taille = self.format_taille.value()
            texte = _('Votre texte')
            w, h = taille * 5.6, taille * 1.25
        elif self.mode == "ajout_image" and getattr(self, "image_a_ajouter", None):
            cle = self.image_a_ajouter
            if getattr(self, "_fantome_cle", None) != cle:
                self._fantome_cle, self._fantome_pix = cle, QPixmap(cle)
            pix = self._fantome_pix
            w = min(200, page.width / 3)
            h = w * pix.height() / max(1, pix.width())
        else:
            return None
        x = max(page.x0, min(pt.x, page.x1 - w))
        y = max(page.y0, min(pt.y, page.y1 - h))
        return fitz.Rect(x, y, x + w, y + h), pix, texte, taille

    def changer_mode(self, mode):
        if mode != "modifier" and getattr(self, "retouche", None):
            self.fermer_retouche()
        if mode != "poser":
            self.a_poser = None if mode is None else self.a_poser
        self.mode = mode
        self.barre_rapide.hide()
        if mode == "biffer" and self.selection:          # le texte deja selectionne devient une marque
            self.marques_biffage += [(self.selection["page"], fitz.Rect(r)) for r in self.selection["lignes"]]
        if mode != "biffer":
            self.marques_biffage.clear()
        self.selection = None
        self.bandeau_simple.hide()
        self.bandeau_biffer.setVisible(mode == "biffer")
        if mode == "biffer":
            self._maj_biffer()
        self.bandeau_form.setVisible(mode == "formulaire")
        if hasattr(self, "bandeau_sig"):
            self.mode = mode
            self._maj_bandeau_sig()
        self.champ_choisi = None
        if mode == "formulaire":
            self._maj_form()
        modif = mode in ("modifier", "ajout_texte", "ajout_image", "lien", "recadrer")
        self._zone_bandeau.setVisible(modif)
        self.bandeau.setVisible(modif)
        for cle, b in self.boutons_modif.items():
            if b.isCheckable():
                b.setChecked(cle == mode)
        if modif:
            self.pile_volet.setCurrentIndex(1)
            self._montrer_volet()
        elif mode == "commenter":
            pass                                        # le volet Commentaires s'ouvre plus bas
        elif self.pile_volet.currentIndex() not in (0, getattr(self, "_idx_volet_comm", -1)):
            self.pile_volet.setCurrentIndex(0)
        if mode is None:
            self.objet = None
        if mode == "mesure":
            self.entrer_mesure()
        elif hasattr(self, "bandeau_mesure"):
            self.sortir_mesure()
        if mode == "commenter":
            self.entrer_commentaires()
        elif hasattr(self, "bandeau_comm"):
            self.sortir_commentaires()
        self.rafraichir_pages()

    # ------------------------------------------------------------ pages : rotation, organisation
    def pivoter_courante(self, angle=90):
        self.pivoter([self.page_courante()], angle)

    def pivoter(self, pages, angle=90, demander=True):
        dans_fichier = True
        if demander:
            dans_fichier = question(self, _('Pivoter'), _("Conserver cette orientation dans le fichier ?\n\nOui : la page reste tournée à l'enregistrement.\nNon : seulement pour l'affichage."),
                                    [(_('Oui, dans le fichier'), QMessageBox.YesRole),
                                     (_("Seulement l'affichage"), QMessageBox.NoRole)]) == 0
        if dans_fichier:
            self.memoriser()
            for n in pages:
                self.doc[n].set_rotation((self.doc[n].rotation + angle) % 360)
            self.apres_modif(reconstruire=True)
        else:
            for n in pages:
                self.rotation_vue[n] = (self.rotation_vue.get(n, 0) + angle) % 360
                self.page_widgets[n].maj_taille()
            self.construire_vignettes()

    def _menu_pages(self, liste, pos):
        pages = sorted(it.data(Qt.UserRole) for it in liste.selectedItems())
        if not pages:
            return
        m = QMenu(self)
        m.addAction(icone("pivoter"), _('Pivoter à droite (90°)'), lambda: self.pivoter(pages, 90, demander=False))
        m.addAction(_('Pivoter à gauche (90°)'), lambda: self.pivoter(pages, -90, demander=False))
        m.addSeparator()
        m.addAction(_('Déplacer au début'), lambda: self.reordonner(pages + [i for i in range(len(self.doc)) if i not in pages]))
        m.addAction(_('Déplacer à la fin'), lambda: self.reordonner([i for i in range(len(self.doc)) if i not in pages] + pages))
        m.addAction(_("Insérer des pages d'un fichier après..."), lambda: self.inserer_fichier(pages[-1] + 1))
        m.addAction(_("Remplacer par les pages d'un fichier..."), lambda: self.remplacer_pages(pages))
        m.addAction(icone("exporter"), _('Extraire dans un nouveau PDF'), lambda: self.extraire(pages))
        m.addSeparator()
        m.addAction(icone("fermer", "#c9252d"), _('Supprimer'), lambda: self.supprimer_pages(pages))
        m.exec(liste.mapToGlobal(pos))

    def reordonner(self, ordre):
        self.memoriser()
        self.doc.select(ordre)
        self.apres_modif([_('Pages réordonnées.')], reconstruire=True)

    def supprimer_pages(self, pages):
        if len(pages) >= len(self.doc):
            self.message(_('Impossible de supprimer toutes les pages.'))
            return
        self.memoriser()
        self.doc.delete_pages(pages)
        self.apres_modif(reconstruire=True)

    def inserer_fichier(self, apres=None):
        f, _x = QFileDialog.getOpenFileName(self, _('Insérer des pages'), "", _('PDF et images (*.pdf *.png *.jpg *.jpeg *.tif)'))
        if not f:
            return
        src = fitz.open(f)
        if not src.is_pdf:
            src = fitz.open("pdf", src.convert_to_pdf())
        self.memoriser()
        self.doc.insert_pdf(src, start_at=len(self.doc) if apres is None else apres)
        self.apres_modif([_('Pages insérées.')], reconstruire=True)

    def remplacer_pages(self, pages):
        f, _x = QFileDialog.getOpenFileName(self, _('Pages de remplacement'), "", _('PDF (*.pdf)'))
        if not f:
            return
        src = fitz.open(f)
        self.memoriser()
        debut = pages[0]
        self.doc.delete_pages(pages)
        self.doc.insert_pdf(src, from_page=0, to_page=min(len(pages), len(src)) - 1, start_at=debut)
        self.apres_modif([_('Pages remplacées.')], reconstruire=True)

    def extraire(self, pages):
        nd = fitz.open()
        for n in pages:
            nd.insert_pdf(self.doc, from_page=n, to_page=n)
        self._extrait = nd
        self.outil_demande.emit("__nouveau__")

    # ------------------------------------------------------------ historique
    LIBELLES = {
        "appliquer_deplacement": _('Déplacement'), "supprimer": _('Suppression'), "remplacer_image": _("Remplacement d'image"),
        "editer_annotation": _("Modification d'un commentaire"), "coller": _('Coller'), "annoter": _('Annotation'),
        "biffer": _('Biffage'), "modifier_ligne_texte": _('Modification du texte'), "ajouter_texte": _('Ajout de texte'),
        "ajouter_image_ici": _("Ajout d'une image"), "poser_objet": _("Pose d'un tampon ou d'une signature"),
        "pivoter": _('Rotation des pages'), "reordonner": _('Nouvel ordre des pages'), "supprimer_pages": _('Suppression de pages'),
        "inserer_fichier": _('Insertion de pages'), "remplacer_pages": _('Remplacement de pages'),
        "remplacer_un": _('Remplacer'), "remplacer_tout": _('Remplacer tout'), "mise_en_page": _('Mise en page'),
        "alleger": _('Allègement du fichier'),
    }

    # ---- document signe : tout en ajout (comme Acrobat), pour ne jamais casser une signature
    def verifier_signe(self, chemin):
        """Apres le mot de passe d'un PDF protege : est-il signe ?"""
        if not self.octets_signes and _signe(self.doc):
            with open(chemin, "rb") as f:
                self.octets_signes = f.read()

    def _octets(self):
        """Etat actuel du document (pour l'historique Annuler : en memoire seulement)."""
        return self.doc.tobytes()

    def octets_en_ajout(self):
        """Signe : le fichier d'origine + une mise a jour avec ce qui a change (signatures intactes)."""
        from moteur import increment
        return increment.ajout(self.octets_signes, self.doc, getattr(self, "mdp_pdf", None))

    def _depuis_octets(self, octets):
        d = fitz.open(stream=octets, filetype="pdf")
        if d.needs_pass:
            d.authenticate(getattr(self, "mdp_pdf", None) or (self.chiffrement or {}).get("owner_pw") or "")
        return d

    def est_signe(self):
        return bool(self.octets_signes)

    def _verifier_signatures_tard(self):
        try:
            if any(True for _n in self.widgets_signature()):
                self.verifier_signatures()
        except Exception:                                 # noqa: BLE001 (document ferme entre-temps)
            pass

    def memoriser(self, libelle=None):
        """Photographie le document avant une modification, avec son nom pour l'historique."""
        if libelle is None:
            libelle = self.LIBELLES.get(sys._getframe(1).f_code.co_name, _('Modification'))
        self.annulations.append((libelle, self._octets()))
        self.annulations = self.annulations[-30:]
        self.retablissements.clear()
        self.maj_historique()

    def _recharger(self, octets):
        self.doc = self._depuis_octets(octets)
        self.objet = None
        self.modifie = True
        self.construire_pages()
        self.titre_change.emit()
        self.maj_historique()
        self.maj_onglet_signets()

    def annuler(self, fois=1):
        if not self.annulations:
            self.message(_('Rien à annuler.'))
            return
        actuel = self._octets()
        for _x in range(min(fois, len(self.annulations))):
            lib, avant = self.annulations.pop()
            self.retablissements.append((lib, actuel))
            actuel = avant
        self._recharger(actuel)
        self.message(_('Annulé : {lib}', lib=lib) + (_(' (et {x} autre{x2})', x=fois - 1, x2='s' if fois > 2 else '') if fois > 1 else ""))

    def remplacer_document(self, octets):
        """Remplace le contenu du document (apres un memoriser()) : allegement, traitement global...
        Un document signe reecrit en entier perd ses signatures : il redevient un document ordinaire."""
        self.octets_signes = None
        self._recharger(octets)
        self.modifie = True
        self.titre_change.emit()

    def retablir(self, fois=1):
        if not self.retablissements:
            self.message(_('Rien à rétablir.'))
            return
        actuel = self._octets()
        for _x in range(min(fois, len(self.retablissements))):
            lib, apres = self.retablissements.pop()
            self.annulations.append((lib, actuel))
            actuel = apres
        self._recharger(actuel)
        self.message(_('Rétabli : {lib}', lib=lib))

    def maj_historique(self):
        """Etat des boutons Annuler / Retablir et de leurs listes deroulantes."""
        if not hasattr(self, "b_annuler"):
            return
        for b, pile, f, verbe in ((self.b_annuler, self.annulations, self.annuler, _("Annuler|action")),
                                  (self.b_retablir, self.retablissements, self.retablir, _('Rétablir'))):
            b.setEnabled(bool(pile))
            b.setToolTip(f"{verbe} : {pile[-1][0]}" if pile else _('Rien à {lower}', lower=verbe.lower()))
            m = b.menu()
            m.clear()
            for k, (lib, _x) in enumerate(reversed(pile)):
                a = m.addAction(_("{verbe} : {action}", verbe=verbe, action=lib) if k == 0 else
                                _("{verbe} jusqu'à : {action}  ({n} actions)", verbe=verbe, action=lib, n=k + 1))
                a.triggered.connect(lambda _x=False, f=f, n=k + 1: f(n))

    def apres_modif(self, journal=None, reconstruire=False):
        self.modifie = True
        if reconstruire or len(self.page_widgets) != len(self.doc):
            self.construire_pages()
        else:
            self.rafraichir_pages(refaire=True)
            self.construire_vignettes()
        self.maj_info()
        self.titre_change.emit()
        if hasattr(self, "liste_comm"):
            self.remplir_volet_commentaires()
        self.maj_onglet_signets()
        if getattr(self, "panneau_envoi", None) is not None:
            self.panneau_envoi.oublier()
        if journal:
            self.message(journal[-1])

    def message(self, t):
        self.statut.emit(t)

    # ------------------------------------------------------------ enregistrement
    def enregistrer(self, chemin):
        if self.params.get("fixer_objets"):
            for page in self.doc:
                for a in list(page.annots()):
                    if objets.est_objet_philpdf(a):
                        r = fitz.Rect(a.rect)
                        pm_doc = self.objets_pdf.get(a.xref)
                        if pm_doc:
                            page.show_pdf_page(r, fitz.open("pdf", pm_doc[0]), 0)
                            page.delete_annot(a)
        tmp = chemin + ".philpdf-tmp"
        if self.octets_signes and not self.chiffrement_change:
            donnees = self.octets_en_ajout()              # signe : ajout seulement, signatures intactes
            with open(tmp, "wb") as f:
                f.write(donnees)
            self.octets_signes = donnees
            self.doc = self._depuis_octets(donnees)
            self.construire_pages()
        else:
            opts = dict(garbage=3, deflate=True)
            if self.chiffrement:
                opts.update(self.chiffrement)
            self.doc.save(tmp, **opts)
            self.octets_signes = None                     # reecrit en entier (protection) : plus de signature valide
        os.replace(tmp, chemin)
        self.chiffrement_change = False
        self.chemin, self.nom, self.modifie = chemin, os.path.basename(chemin), False
        self.poids_initial = os.path.getsize(chemin)
        self.maj_info()
        self.titre_change.emit()


# ================================================================ rechercher et remplacer
class DialogueRemplacer(QDialog):
    def __init__(self, onglet, texte=""):
        super().__init__(onglet)
        self.o = onglet
        self.setWindowTitle(_('Rechercher et remplacer'))
        self.setMinimumWidth(480)
        f = QFormLayout(self)
        self.rech = QLineEdit(texte)
        self.remp = QLineEdit()
        self.compte = QLabel()
        self.compte.setStyleSheet("color:#1462c2;font-weight:600")
        f.addRow(_('Rechercher'), self.rech)
        f.addRow("", self.compte)
        f.addRow(_('Remplacer par'), self.remp)
        self.casse = QCheckBox(_('Respecter la casse (Dupont ≠ DUPONT)'))
        self.accents = QCheckBox(_('Ignorer les accents (e = é = è = ê)'))
        self.accents.setChecked(True)
        f.addRow(self.casse)
        f.addRow(self.accents)
        info = QLabel(_("La police et la mise en forme d'origine sont conservées."))
        info.setStyleSheet("color:#555")
        f.addRow(info)
        bb = QDialogButtonBox()
        self.b_suiv = bb.addButton(_('Suivant ›'), QDialogButtonBox.ActionRole)
        self.b_un = bb.addButton(_('Remplacer'), QDialogButtonBox.ActionRole)
        self.b_tout = bb.addButton(_('Remplacer tout'), QDialogButtonBox.ActionRole)
        bb.addButton(_('Fermer'), QDialogButtonBox.RejectRole)
        f.addRow(bb)
        self.rech.textChanged.connect(self.compter)
        self.casse.toggled.connect(self.compter)
        self.accents.toggled.connect(self.compter)
        self.b_suiv.clicked.connect(self.suivant)
        self.b_un.clicked.connect(self.remplacer_un)
        self.b_tout.clicked.connect(self.remplacer_tout)
        bb.rejected.connect(self.reject)
        self.idx = -1
        self.compter()

    def _occ(self):
        t = self.rech.text()
        if not t:
            return []
        ed = Editeur(self.o.doc)
        out = []
        for n in range(len(self.o.doc)):
            for chars, d, f in ed.occurrences(n, t, self.casse.isChecked(), not self.accents.isChecked()):
                r = fitz.Rect()
                for c, _x in chars[d:f]:
                    r |= fitz.Rect(c["bbox"])
                out.append((n, r))
        return out

    def compter(self):
        occ = self._occ()
        self.o.resultats = occ
        self.compte.setText(_('{n} occurrence{x}', n=len(occ), x='s' if len(occ) > 1 else '') if self.rech.text() else "")
        self.b_tout.setText(_('Remplacer tout ({n})', n=len(occ)))
        self.idx = -1
        self.o.rafraichir_pages()

    def suivant(self):
        occ = self.o.resultats
        if not occ:
            return
        self.idx = (self.idx + 1) % len(occ)
        self.o.resultat_courant = occ[self.idx]
        self.o.aller_a(*occ[self.idx])

    def remplacer_un(self):
        if self.idx < 0:
            self.suivant()
            return
        n, r = self.o.resultats[self.idx]
        self.o.memoriser()
        ed = Editeur(self.o.doc)
        ed.remplacer(n, self.rech.text(), self.remp.text(), zone=r,
                     casse=self.casse.isChecked(), accents=not self.accents.isChecked())
        self.o.apres_modif(ed.journal)
        self.compter()
        self.suivant()

    def remplacer_tout(self):
        self.o.memoriser()
        ed = Editeur(self.o.doc)
        n = ed.remplacer_tout(self.rech.text(), self.remp.text(), self.casse.isChecked(), not self.accents.isChecked())
        self.o.apres_modif(ed.journal)
        self.o.message(_('{n} remplacement{x} effectué{x}.', n=n, x='s' if n > 1 else ''))
        self.compter()
