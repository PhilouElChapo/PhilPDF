"""Formulaire dans un document ouvert : proprietes des champs, types a tracer, ordre de tabulation, et dans PhilPDF
le meme comportement que dans Acrobat (formats, date automatique, calculs, listes dependantes, afficher / masquer).

Melange (mixin) de OngletDocument."""
import re

import pymupdf as fitz
from PySide6.QtCore import Qt, QDate, QPoint
from PySide6.QtWidgets import (QDialog, QMessageBox, QInputDialog, QFrame, QVBoxLayout, QHBoxLayout, QLineEdit,
                               QCalendarWidget, QPushButton, QLabel, QMenu)

from .langue import _
from moteur import champs as C
from moteur import formulaire as FO

T = fitz


def types_a_tracer():
    return [("auto", _("Automatique")), ("texte", _("Texte")), ("case", _("Case à cocher")),
            ("radio", _("Bouton radio")), ("liste", _("Liste déroulante")), ("liste_multiple", _("Liste ouverte (plusieurs choix)")),
            ("date", _("Date")), ("montant", _("Montant (€)")), ("signature", _("Signature")),
            ("bouton", _("Bouton (réinitialiser, imprimer, e-mail...)"))]


def bulles_types():
    return {"auto": _("PhilPDF devine le type d'après le texte écrit à gauche du champ (date, montant, e-mail...)"),
            "liste": _("Une ligne : on clique pour dérouler les choix et en prendre un. Prend peu de place."),
            "liste_multiple": _("Plusieurs lignes visibles d'un coup ; on peut cocher plusieurs choix (Ctrl + clic)."),
            "radio": _("Un seul choix parmi plusieurs ronds du même groupe (ex. Oui / Non)."),
            "case": _("Case à cocher indépendante."),
            "bouton": _("Bouton qui fait une action : réinitialiser, imprimer, envoyer par e-mail, aller à une page.")}


def actions_bouton():
    return [("reinitialiser", _("Réinitialiser le formulaire")), ("imprimer", _("Imprimer")),
            ("email", _("Envoyer par e-mail")), ("page", _("Aller à une page"))]


def dessiner_bouton(doc, w, survol=False):
    """Apparence du bouton : bords arrondis, fond bleu, texte blanc centre (vue pareille dans Acrobat)."""
    r = fitz.Rect(w.rect)
    larg, haut = r.width, r.height
    rayon = min(haut / 2.2, 7)
    k = 0.5523 * rayon
    texte = (w.button_caption or w.field_name or "").strip()
    taille = max(6.0, min(haut * 0.5, 13.0))
    while taille > 6 and fitz.get_text_length(texte, "helv", taille) > larg - 10:
        taille -= 0.5
    tl = fitz.get_text_length(texte, "helv", taille)
    x, y = (larg - tl) / 2, (haut - taille * 0.72) / 2

    def chemin(x0, y0, x1, y1, rr):
        kk = 0.5523 * rr
        return (f"{x0 + rr:.2f} {y0:.2f} m {x1 - rr:.2f} {y0:.2f} l {x1 - rr + kk:.2f} {y0:.2f} {x1:.2f} {y0 + rr - kk:.2f} {x1:.2f} {y0 + rr:.2f} c "
                f"{x1:.2f} {y1 - rr:.2f} l {x1:.2f} {y1 - rr + kk:.2f} {x1 - rr + kk:.2f} {y1:.2f} {x1 - rr:.2f} {y1:.2f} c "
                f"{x0 + rr:.2f} {y1:.2f} l {x0 + rr - kk:.2f} {y1:.2f} {x0:.2f} {y1 - rr + kk:.2f} {x0:.2f} {y1 - rr:.2f} c "
                f"{x0:.2f} {y0 + rr:.2f} l {x0:.2f} {y0 + rr - kk:.2f} {x0 + rr - kk:.2f} {y0:.2f} {x0 + rr:.2f} {y0:.2f} c h")
    del k
    fond = "0.165 0.42 0.69" if not survol else "0.11 0.33 0.58"
    contenu = (f"q 0.55 0.65 0.78 rg {chemin(0.6, 0.0, larg - 0.6, haut - 1.2, rayon)} f Q "     # ombre legere
               f"q {fond} rg {chemin(0.6, 1.0, larg - 0.6, haut - 0.4, rayon)} f Q "
               f"BT 1 1 1 rg /Helv {taille:.1f} Tf {x:.2f} {y:.2f} Td {fitz.get_pdf_str(texte)} Tj ET")
    police = doc.get_new_xref()
    doc.update_object(police, "<</Type/Font/Subtype/Type1/BaseFont/Helvetica/Encoding/WinAnsiEncoding>>")
    ap = doc.get_new_xref()
    doc.update_object(ap, f"<</Type/XObject/Subtype/Form/BBox[0 0 {larg:.2f} {haut:.2f}]"
                          f"/Resources<</Font<</Helv {police} 0 R>>>>>>")
    doc.update_stream(ap, contenu.encode("cp1252", "replace"))
    doc.xref_set_key(w.xref, "AP", f"<</N {ap} 0 R>>")
    doc.xref_set_key(w.xref, "MK", f"<</BG[0.165 0.42 0.69]/CA{fitz.get_pdf_str(texte)}>>")
    doc.xref_set_key(w.xref, "DA", "(/Helv 0 Tf 1 g)")


class SaisieDate(QFrame):
    """Saisie d'une date, simple : un calendrier qui s'ouvre sous le champ, la date tapee au clavier (28/10/26,
    281026, 28.10.2026...), et deux boutons : Aujourd'hui, Effacer. Entree ou un clic sur un jour : c'est ecrit."""

    def __init__(self, page, onglet, n, xref, fmt, valeur, pos):
        super().__init__(page.window(), Qt.Popup)
        import datetime as dt
        self.o, self.n, self.xref, self.fmt, self.fini = onglet, n, xref, fmt, False
        self.setObjectName("saisie_date")
        self.setStyleSheet("QFrame#saisie_date{background:#fff;border:1px solid #9bb4d6;border-radius:6px}")
        v = QVBoxLayout(self)
        v.setContentsMargins(8, 8, 8, 8)
        self.texte = QLineEdit((valeur or "").strip())
        self.texte.setObjectName("date_texte")
        self.texte.setPlaceholderText(C.ecrire_date(fmt))
        self.texte.returnPressed.connect(lambda: self.valider(self.texte.text()))
        v.addWidget(self.texte)
        self.cal = QCalendarWidget()
        self.cal.setGridVisible(False)
        self.cal.setFirstDayOfWeek(Qt.Monday)
        self.cal.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        d = C.lire_date(fmt, (valeur or "").strip())
        if d:
            self.cal.setSelectedDate(QDate(d.year, d.month, d.day))
        self.cal.clicked.connect(lambda q: self.valider(C.ecrire_date(fmt, dt.datetime(q.year(), q.month(), q.day()))))
        v.addWidget(self.cal)
        h = QHBoxLayout()
        b = QPushButton(_("Aujourd'hui"))
        b.setObjectName("date_aujourdhui")
        b.clicked.connect(lambda: self.valider(C.ecrire_date(fmt)))
        h.addWidget(b)
        b = QPushButton(_("Effacer"))
        b.clicked.connect(lambda: self.valider(""))
        h.addWidget(b)
        h.addStretch(1)
        aide = QLabel(_("format : {f}", f=C.ecrire_date(fmt)))
        aide.setStyleSheet("color:#777")
        h.addWidget(aide)
        v.addLayout(h)
        self.move(pos + QPoint(0, 2))
        self.show()
        self.texte.setFocus()

    def valider(self, texte):
        if self.fini:
            return
        t = (texte or "").strip()
        if t and t.isdigit() and len(t) in (6, 8):            # 281026 ou 28102026
            t = f"{t[:2]}/{t[2:4]}/{t[4:]}"
        self.fini = True
        self.close()
        self.o.valeur_champ(self.n, self.xref, t)


class MixinFormulaire:
    # ------------------------------------------------------------ creer
    def creer_champ_type(self, n, r, genre):
        """Champ du type choisi dans le bandeau du formulaire ; renvoie False si annule."""
        if genre == "signature":
            self.ajouter_champ_signature(n, r)
            return True
        if genre == "bouton":
            return self.creer_bouton(n, r)
        if genre == "auto":
            genre = "case" if r.width <= 20 and r.height <= 20 else "texte"
        if genre in ("case", "radio"):
            cote = max(min(r.width, r.height), 10)
            r = fitz.Rect(r.x0, r.y0, r.x0 + cote, r.y0 + cote)
        elif r.height < 12:
            r = fitz.Rect(r.x0, r.y0, max(r.x1, r.x0 + 80), r.y0 + 18)
        propose = FO._libelle(self.doc[n], r, self.doc[n].get_text("words"), genre in ("case", "radio"))
        if genre == "radio":
            groupes = sorted({w.field_name for _n, w in C.tous_les_champs(self.doc)
                              if w.field_type == T.PDF_WIDGET_TYPE_RADIOBUTTON})
            groupe, ok = QInputDialog.getItem(self, _("Bouton radio"), _("Groupe (un seul choix coché par groupe) :"),
                                              groupes + ([] if groupes else [_("Choix")]), 0, True)
            if not ok or not groupe.strip():
                return False
            valeur, ok = QInputDialog.getText(self, _("Bouton radio"), _("Valeur de ce bouton :"), text=propose or _("Oui"))
            if not ok or not valeur.strip():
                return False
            self.memoriser(_("Ajout du bouton radio « {nom} »", nom=valeur.strip()))
            FO.creer_radio(self.doc, n, r, groupe.strip(), valeur.strip())
            FO.normaliser(self.doc) if not self.est_signe() else None
            self.apres_modif([_("Bouton « {v} » ajouté au groupe « {g} ».", v=valeur.strip(), g=groupe.strip())])
            self._maj_form()
            return True
        nom, ok = QInputDialog.getText(self, _("Nouveau champ"), _("Nom du champ :"), text=propose)
        if not ok or not nom.strip():
            return False
        nom = nom.strip()
        choix = []
        if genre in ("liste", "liste_multiple"):
            t, ok = QInputDialog.getMultiLineText(self, _("Liste"), _("Choix proposés (un par ligne) :"), "")
            if not ok:
                return False
            choix = [x.strip() for x in t.splitlines() if x.strip()]
        self.memoriser(_("Ajout du champ « {nom} »", nom=nom))
        base = {"date": "texte", "montant": "texte"}.get(genre, genre)
        FO.creer(self.doc, {n: [{"genre": base, "rect": r, "nom": nom, "lignes": r.height > 30 and base == "texte",
                                 "choix": choix}]})
        w = self._widget_nom(nom)
        if w is not None and genre in ("date", "montant"):
            reg = C.vide()
            reg["format"] = ({"genre": "date", "date": "dd/mm/yyyy"} if genre == "date" else
                             {"genre": "nombre", "decimales": 2, "separateur": 2, "negatif": 0, "symbole": "€",
                              "symbole_avant": False})
            C.ecrire(self.doc, w, reg)
            C.generer_js(self.doc)
        self.apres_modif([_("Champ « {nom} » ajouté.", nom=nom)])
        self._maj_form()
        return True

    def placer_champ(self, n, xref, r):
        """Champ deplace ou redimensionne a la souris ou aux fleches."""
        w = self._widget((n, xref))
        if w is None:
            return
        r = fitz.Rect(r) & self.doc[n].rect
        if r.is_empty or (abs(r.x0 - w.rect.x0) < 0.2 and abs(r.y0 - w.rect.y0) < 0.2
                          and abs(r.x1 - w.rect.x1) < 0.2 and abs(r.y1 - w.rect.y1) < 0.2):
            return
        if not getattr(self, "_placement_en_cours", False):
            self.memoriser(_("Champ « {nom} » déplacé ou redimensionné", nom=w.field_name))
        w = self._widget((n, xref))
        w.rect = r
        self._maj_widget(w)
        if w.field_type == T.PDF_WIDGET_TYPE_BUTTON:
            dessiner_bouton(self.doc, w)
        self.champ_choisi = (n, xref)
        self.apres_modif([])

    def creer_bouton(self, n, r):
        """Bouton dans le PDF (marche aussi dans Acrobat) : reinitialiser, imprimer, envoyer par e-mail, aller a une page."""
        acts = actions_bouton()
        lib, ok = QInputDialog.getItem(self, _("Bouton"), _("Action du bouton :"), [t for _k, t in acts], 0, False)
        if not ok:
            return False
        genre = next(k for k, t in acts if t == lib)
        action = {"genre": genre}
        if genre == "email":
            a, ok = QInputDialog.getText(self, _("Bouton"), _("Adresse e-mail du destinataire :"))
            if not ok:
                return False
            sujet, ok = QInputDialog.getText(self, _("Bouton"), _("Objet du message :"), text=self.nom)
            action.update(email=a.strip(), sujet=sujet.strip())
        elif genre == "page":
            num, ok = QInputDialog.getInt(self, _("Bouton"), _("Page :"), 1, 1, len(self.doc))
            if not ok:
                return False
            action["page"] = num
        legende, ok = QInputDialog.getText(self, _("Bouton"), _("Texte du bouton :"), text=lib)
        if not ok or not legende.strip():
            return False
        pris = {x.field_name for _k, x in C.tous_les_champs(self.doc)}
        k = 1
        while f"Bouton{k}" in pris:
            k += 1
        nom = f"Bouton{k}"
        if r.width < 40 or r.height < 14:
            r = fitz.Rect(r.x0, r.y0, r.x0 + max(r.width, 110), r.y0 + max(r.height, 22))
        self.memoriser(_("Ajout du bouton « {nom} »", nom=legende.strip()))
        w = fitz.Widget()
        w.field_type = T.PDF_WIDGET_TYPE_BUTTON
        w.field_name = nom
        w.rect = fitz.Rect(r)
        w.button_caption = legende.strip()
        w.fill_color = (0.9, 0.93, 0.98)
        w.border_color = (0.36, 0.5, 0.72)
        w.border_width = 1
        w.text_fontsize = 0
        w.field_flags |= 1 << 2                           # bouton-poussoir, pas une case
        self.doc[n].add_widget(w)
        FO.normaliser(self.doc) if not self.est_signe() else None
        w = self._widget_nom(nom)
        dessiner_bouton(self.doc, w)
        reg = C.vide()
        reg["action"] = action
        C.ecrire(self.doc, w, reg)
        C.generer_js(self.doc)
        self.apres_modif([_("Bouton « {nom} » ajouté.", nom=legende.strip())])
        self._maj_form()
        return True

    def clic_bouton(self, w):
        """Dans PhilPDF, le bouton fait la meme chose que dans Acrobat."""
        a = self.regles_champ(w).get("action") or {}
        g = a.get("genre")
        fen = self.window()
        if g == "reinitialiser":
            if QMessageBox.question(self, _("Formulaire"), _("Effacer tout le formulaire ?")) != QMessageBox.Yes:
                return
            self.memoriser(_("Réinitialisation du formulaire"))
            for _n, x in C.tous_les_champs(self.doc):
                if x.field_type in (T.PDF_WIDGET_TYPE_BUTTON, T.PDF_WIDGET_TYPE_SIGNATURE) or self.champ_verrouille(x):
                    continue
                if x.field_type in (T.PDF_WIDGET_TYPE_CHECKBOX, T.PDF_WIDGET_TYPE_RADIOBUTTON):
                    x.field_value = False
                    self._maj_widget(x)
                else:
                    t_dv, dv = self.doc.xref_get_key(C.xref_champ(self.doc, x), "DV")
                    self._ecrire_valeur(x, dv if t_dv == "string" else "")
            self.recalculer()
            self.apres_modif([_("Formulaire réinitialisé.")])
        elif g == "imprimer" and hasattr(fen, "imprimer"):
            fen.imprimer([self])
        elif g == "email":
            if (self.modifie or not self.chemin) and hasattr(fen, "enregistrer") and not fen.enregistrer(self):
                return
            from . import agenda
            agenda.ouvrir(agenda.lien_message(self.params.get("messagerie") or "gmail", a.get("sujet") or self.nom,
                                              _("Ci-joint : {f}", f=self.nom), a.get("email", "")))
            try:
                from .fenetre import montrer_dans_explorateur
                montrer_dans_explorateur(self.chemin)
            except Exception:                             # noqa: BLE001
                pass
        elif g == "page":
            self.aller_a(max(0, min(len(self.doc) - 1, int(a.get("page", 1)) - 1)))

    def aide_entree(self, pw, w):
        """Message d'aide du champ, montre a l'entree (comme Acrobat, sans fenetre a fermer)."""
        aide = (self.regles_champ(w).get("aide") or {}).get("entree")
        if aide:
            from PySide6.QtWidgets import QToolTip
            r = pw.vers_ecran(w.rect).toRect()
            QToolTip.showText(pw.mapToGlobal(r.bottomLeft()), aide, pw)
            self.message(aide)

    def avant_enregistrer(self):
        """Champs obligatoires vides : on le dit (avec leurs messages), on enregistre si vous le voulez."""
        vides = self.champs_obligatoires_vides()
        if not vides:
            return True
        lignes = []
        for nom in vides:
            w = self._widget_nom(nom)
            msg = ((self.regles_champ(w).get("aide") or {}).get("vide") if w is not None else "") or ""
            lignes.append(f"• {nom}" + (f" : {msg}" if msg else ""))
        return QMessageBox.question(self, _("Formulaire"),
                                    _("Champs obligatoires encore vides :\n{x}\n\nEnregistrer quand même ?",
                                      x="\n".join(lignes[:15]))) == QMessageBox.Yes

    def _widget_nom(self, nom, n=None):
        for k, p in enumerate(self.doc):
            if n is not None and k != n:
                continue
            for w in p.widgets() or []:
                if w.field_name == nom:
                    w._page_vivante = p
                    return w
        return None

    def _widgets_nom(self, nom):
        out = []
        for p in self.doc:
            for w in p.widgets() or []:
                if w.field_name == nom:
                    w._page_vivante = p
                    out.append(w)
        return out

    # ------------------------------------------------------------ clic droit sur un champ
    def menu_champ(self, pw, w, pos):
        """Tout ce qu'on peut faire d'un champ, au clic droit (en mode Formulaire ou en remplissant)."""
        n = pw.num
        m = QMenu(self)
        sig = w.field_type == T.PDF_WIDGET_TYPE_SIGNATURE
        if self.mode != "formulaire" and not sig:
            r = self.regles_champ(w)
            if (r.get("format") or {}).get("genre") == "date":
                m.addAction(_("Mettre la date du jour"),
                            lambda: self.valeur_champ(n, w.xref, C.ecrire_date(r["format"].get("date") or "dd/mm/yyyy")))
            if w.field_value not in (None, "", "Off", False):
                m.addAction(_("Effacer la valeur"), lambda: self.effacer_valeur(n, w))
            m.addSeparator()
        m.addAction(_("Propriétés du champ..."), lambda: self.proprietes_champ(n, w))
        if not sig:
            m.addAction(_("Renommer..."), lambda: (setattr(self, "champ_choisi", (n, w.xref)), self.renommer_champ()))
            m.addAction(_("Dupliquer (juste en dessous)"), lambda: self.dupliquer_champ(n, w))
        m.addAction(_("Supprimer le champ"), lambda: (setattr(self, "champ_choisi", (n, w.xref)), self.supprimer_champ()))
        m.addSeparator()
        m.addAction(_("Ordre de tabulation..."), self.ordre_tabulation)
        if self.mode != "formulaire":
            m.addAction(_("Passer en mode Formulaire (créer, déplacer, régler les champs)"),
                        lambda: self.changer_mode("formulaire"))
        m.exec(pos)

    def effacer_valeur(self, n, w):
        self.memoriser(_("Remplissage du formulaire"))
        w = self._widget((n, w.xref)) or w
        if w.field_type in (T.PDF_WIDGET_TYPE_CHECKBOX, T.PDF_WIDGET_TYPE_RADIOBUTTON):
            w.field_value = False
            self._maj_widget(w)
        else:
            self._ecrire_valeur(w, "")
        self._apres_valeur(w.field_name)
        self.apres_modif([])

    def dupliquer_champ(self, n, w):
        """Copie du champ (meme type, memes regles, memes choix) juste en dessous, avec un nom libre."""
        pris = {x.field_name for _k, x in C.tous_les_champs(self.doc)}
        base = re.sub(r"\s*\d+$", "", w.field_name) or w.field_name
        k = 2
        while f"{base} {k}" in pris:
            k += 1
        nom = f"{base} {k}"
        r = fitz.Rect(w.rect)
        r = r + (0, r.height + 4, 0, r.height + 4)
        genre = {T.PDF_WIDGET_TYPE_CHECKBOX: "case", T.PDF_WIDGET_TYPE_COMBOBOX: "liste",
                 T.PDF_WIDGET_TYPE_LISTBOX: "liste_multiple"}.get(w.field_type, "texte")
        if w.field_type == T.PDF_WIDGET_TYPE_RADIOBUTTON:
            self.memoriser(_("Ajout du bouton radio « {nom} »", nom=w.field_name))
            FO.creer_radio(self.doc, n, r, w.field_name, f"Choix{k}")
        else:
            self.memoriser(_("Ajout du champ « {nom} »", nom=nom))
            FO.creer(self.doc, {n: [{"genre": genre, "rect": r, "nom": nom, "info": w.field_label or "",
                                     "lignes": bool(w.field_flags & T.PDF_TX_FIELD_IS_MULTILINE),
                                     "choix": [c if isinstance(c, str) else c[0] for c in (w.choice_values or [])]}]})
            regles = self.regles_champ(w)
            nouveau = self._widget_nom(nom)
            if nouveau is not None and regles.get("_philpdf"):
                C.ecrire(self.doc, nouveau, regles)
                C.generer_js(self.doc)
        self.apres_modif([_("Champ dupliqué : « {nom} ».", nom=nom)])
        self._maj_form()

    # ------------------------------------------------------------ proprietes
    def proprietes_champ(self, n, w):
        from .dialogues_champ import DialogueChamp
        if w.field_type == T.PDF_WIDGET_TYPE_SIGNATURE:
            self.regler_champ_signature(n, w)
            return
        d = DialogueChamp(self, n, w)
        if d.exec() != QDialog.Accepted:
            return
        self.memoriser(_("Propriétés du champ « {nom} »", nom=w.field_name))
        res = d.resultat
        ancien = w.field_name
        for x in self._widgets_nom(ancien):
            if res["nom"] != ancien:
                x.field_name = res["nom"]
            x.field_label = res["info"] or None
            fl = x.field_flags
            fl = (fl | T.PDF_FIELD_IS_REQUIRED) if res["obligatoire"] else (fl & ~T.PDF_FIELD_IS_REQUIRED)
            fl = (fl | T.PDF_FIELD_IS_READ_ONLY) if res["lecture"] else (fl & ~T.PDF_FIELD_IS_READ_ONLY)
            if "multi" in res:
                fl = (fl | T.PDF_TX_FIELD_IS_MULTILINE) if res["multi"] else (fl & ~T.PDF_TX_FIELD_IS_MULTILINE)
                x.text_maxlen = res["maxlen"]
                x.text_fontsize = res["taille"]
            if "items" in res:
                fl = (fl | T.PDF_CH_FIELD_IS_SORT) if res["trier"] else (fl & ~T.PDF_CH_FIELD_IS_SORT)
                if x.field_type == T.PDF_WIDGET_TYPE_COMBOBOX:
                    fl = (fl | T.PDF_CH_FIELD_IS_EDIT) if res["libre"] else (fl & ~T.PDF_CH_FIELD_IS_EDIT)
                else:
                    fl = (fl | T.PDF_CH_FIELD_IS_MULTI_SELECT) if res["multiple"] else (fl & ~T.PDF_CH_FIELD_IS_MULTI_SELECT)
                x.choice_values = sorted(res["items"], key=str.lower) if res["trier"] else res["items"]
            x.field_flags = fl
            x.field_display = res["affichage"]
            if res.get("legende"):
                x.button_caption = res["legende"]
                self._maj_widget(x)
                dessiner_bouton(self.doc, x)
            self._maj_widget(x)
            if "alignement" in res:
                self.doc.xref_set_key(C.xref_champ(self.doc, x), "Q", str(res["alignement"]) if res["alignement"] else "null")
        if "defaut" in res:                               # valeur par defaut (/DV), et valeur si le champ est vide
            for x in self._widgets_nom(res["nom"] if res["nom"] != ancien else ancien) or self._widgets_nom(ancien):
                fx = C.xref_champ(self.doc, x)
                self.doc.xref_set_key(fx, "DV", fitz.get_pdf_str(res["defaut"]) if res["defaut"] else "null")
                if res["defaut"] and not (x.field_value or "").strip():
                    x.field_value = res["defaut"]
                    self._maj_widget(x)
                break
        if res["nom"] != ancien:                          # les regles des autres champs suivent le nouveau nom
            self._renommer_dans_regles(ancien, res["nom"])
        w = self._widget_nom(res["nom"])
        C.ecrire(self.doc, w, res["regles"])
        C.generer_js(self.doc)
        if w.field_value:                                 # reaffiche la valeur avec son format
            self._ecrire_valeur(w, w.field_value, res["regles"])
        self.recalculer()
        self.apres_modif([_("Propriétés du champ enregistrées.")])
        self._maj_form()

    def _renommer_dans_regles(self, ancien, nouveau):
        for _n, x in C.tous_les_champs(self.doc):
            r = C.lire(self.doc, x)
            if not r.get("_philpdf"):
                continue
            change = False
            c = r.get("calcul")
            if c and ancien in (c.get("champs") or []):
                c["champs"] = [nouveau if v == ancien else v for v in c["champs"]]
                change = True
            if c and c.get("genre") == "formule" and f"[{ancien}]" in c.get("formule", ""):
                c["formule"] = c["formule"].replace(f"[{ancien}]", f"[{nouveau}]")
                change = True
            if (r.get("depend") or {}).get("parent") == ancien:
                r["depend"]["parent"] = nouveau
                change = True
            a = r.get("affiche")
            if a and ancien in (a.get("cibles") or []):
                a["cibles"] = [nouveau if v == ancien else v for v in a["cibles"]]
                change = True
            if change:
                C.ecrire(self.doc, x, r)

    def ordre_tabulation(self):
        from .dialogues_champ import DialogueTabulation
        n = self.page_courante()
        if not list(self.doc[n].widgets() or []):
            QMessageBox.information(self, _("Ordre de tabulation"), _("Aucun champ sur cette page."))
            return
        d = DialogueTabulation(self, n)
        if d.exec() != QDialog.Accepted:
            return
        self.memoriser(_("Ordre de tabulation"))
        self.poser_ordre_tabulation(n, d.ordre())
        self.apres_modif([_("Ordre de tabulation enregistré.")])

    def poser_ordre_tabulation(self, n, xrefs):
        """Range les widgets de la page dans cet ordre (les autres annotations gardent leur place)."""
        page = self.doc[n]
        t, arr = self.doc.xref_get_key(page.xref, "Annots")
        if t == "xref":
            ax = int(arr.split()[0])
            arr = self.doc.xref_object(ax, compressed=True)
        elif t != "array":
            return
        refs = [int(x) for x in re.findall(r"(\d+)\s+0\s+R", arr)]
        places = [i for i, r in enumerate(refs) if r in xrefs]
        suite = iter([x for x in xrefs if x in refs])
        for i in places:
            refs[i] = next(suite)
        nouveau = "[" + " ".join(f"{r} 0 R" for r in refs) + "]"
        if t == "xref":
            self.doc.update_object(ax, nouveau)
        else:
            self.doc.xref_set_key(page.xref, "Annots", nouveau)
        self.doc.xref_set_key(page.xref, "Tabs", "null")

    # ------------------------------------------------------------ remplir (comme Acrobat)
    def regles_champ(self, w):
        try:
            return C.lire(self.doc, w)
        except Exception:                                 # noqa: BLE001
            return C.vide()

    def _ecrire_valeur(self, w, brut, regles=None):
        """Valeur gardee = brute (comme Acrobat) ; apparence = texte formate (1.234,50 €)."""
        regles = regles if regles is not None else self.regles_champ(w)
        aff = C.formater(regles, brut)
        w.field_value = aff
        self._maj_widget(w)
        if aff != brut or not brut:
            self.doc.xref_set_key(C.xref_champ(self.doc, w), "V", fitz.get_pdf_str(brut) if brut else "null")

    def valeur_auto(self, w):
        """Date ou heure du moment si le champ le demande et qu'il est vide (comme Acrobat a l'entree du champ)."""
        r = self.regles_champ(w)
        if not r.get("auto") or (w.field_value or "").strip():
            return False
        fmt = r.get("format") or {}
        f = fmt.get("date") if fmt.get("genre") == "date" else fmt.get("heure") if fmt.get("genre") == "heure" else None
        if not f:
            f = {"date_clic": "dd/mm/yyyy", "heure_clic": "HH:MM"}.get(r["auto"], "dd/mm/yyyy HH:MM")
        self.memoriser(_("Remplissage du formulaire"))
        self._ecrire_valeur(w, C.ecrire_date(f), r)
        self._apres_valeur(w.field_name)
        self.apres_modif([])
        return True

    def saisir_valeur(self, w, valeur):
        """Controle et met en forme la saisie ; renvoie la valeur a garder, ou None (message deja affiche)."""
        r = self.regles_champ(w)
        val, err = C.saisie(r, valeur)
        if err:
            fmt = r.get("format") or {}
            msg = {"nombre": _("« {v} » n'est pas un nombre.", v=valeur),
                   "date": _("Date attendue au format {f}.", f=fmt.get("date", "jj/mm/aaaa").replace("yyyy", "aaaa").replace("dd", "jj")),
                   "heure": _("Heure attendue au format {f}.", f=fmt.get("heure", "HH:MM")),
                   "masque": _("Saisie attendue : {f}", f=fmt.get("masque", "")),
                   "plage": self._message_plage(r),
                   "controle": {"email": _("Adresse e-mail incorrecte."),
                                "nir": _("Numéro de Sécurité sociale incorrect (vérifiez la clef)."),
                                "iban": _("IBAN incorrect."), "siret": _("Numéro SIRET incorrect."),
                                "rpps": _("Numéro RPPS incorrect.")}.get(r.get("controle"), _("Valeur incorrecte."))}.get(err, err)
            QMessageBox.warning(self, _("Formulaire"), msg)
            return None
        return val

    def _message_plage(self, r):
        p = r.get("plage") or {}
        if p.get("min") is not None and p.get("max") is not None:
            return _("La valeur doit être comprise entre {a} et {b}.", a=C.valeur_brute(p["min"]), b=C.valeur_brute(p["max"]))
        if p.get("min") is not None:
            return _("La valeur doit être au moins {a}.", a=C.valeur_brute(p["min"]))
        return _("La valeur doit être au plus {b}.", b=C.valeur_brute(p.get("max") or 0))

    def valeurs(self):
        return {w.field_name: (w.field_value or "") for _n, w in C.tous_les_champs(self.doc)}

    def _apres_valeur(self, nom):
        """Une valeur a change : listes dependantes, champs affiches / masques, puis calculs."""
        v = self.valeurs().get(nom, "")
        for _n, x in C.tous_les_champs(self.doc):
            r = self.regles_champ(x)
            dep = r.get("depend")
            if dep and dep.get("parent") == nom:
                items = list((dep.get("listes") or {}).get(v, []))
                x.choice_values = items
                if (x.field_value or "") not in items:
                    x.field_value = ""
                self._maj_widget(x)
            if x.field_name == nom and r.get("affiche"):
                a = r["affiche"]
                vis = (v not in ("", "Off", None, False)) if a.get("quand") == "coche" else (v == a.get("valeur"))
                for cible in a.get("cibles") or []:
                    for y in self._widgets_nom(cible):
                        y.field_display = 0 if vis else 1
                        self._maj_widget(y)
        self.recalculer()

    def recalculer(self):
        """Champs calcules, dans l'ordre de calcul (somme, produit, moyenne, min, max, formule)."""
        calc = []
        for _n, x in C.tous_les_champs(self.doc):
            r = self.regles_champ(x)
            if r.get("calcul") and x.field_name not in [c[0].field_name for c in calc]:
                calc.append((x, r))
        if not calc:
            return
        noms = [x.field_name for x, _r in calc]
        deps = {x.field_name: set(C.sources(r["calcul"])) & set(noms) for x, r in calc}
        ordre, vus = [], set()

        def visiter(nm, pile=()):
            if nm in vus or nm in pile:
                return
            for d in deps.get(nm, ()):
                visiter(d, pile + (nm,))
            vus.add(nm)
            ordre.append(nm)
        for nm in noms:
            visiter(nm)
        par = {x.field_name: (x, r) for x, r in calc}
        for nm in ordre:
            x, r = par[nm]
            formats = {}
            for src in C.sources(r["calcul"]):
                y = self._widget_nom(src)
                if y is not None:
                    f = (self.regles_champ(y).get("format") or {})
                    formats[src] = f.get("date") if f.get("genre") == "date" else None
            v = C.calculer(r, self.valeurs(), formats)
            val = v if isinstance(v, str) else C.valeur_brute(v)
            if (x.field_value or "") != val:
                self._ecrire_valeur(x, val, r)

    def champs_obligatoires_vides(self):
        out = []
        for _n, w in C.tous_les_champs(self.doc):
            if w.field_flags & T.PDF_FIELD_IS_REQUIRED and w.field_type != T.PDF_WIDGET_TYPE_SIGNATURE:
                if (w.field_value or "") in ("", "Off"):
                    out.append(w.field_name)
        return list(dict.fromkeys(out))
