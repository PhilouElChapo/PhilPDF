"""Proprietes d'un champ de formulaire, en une seule fenetre simple (ce qu'Acrobat range dans six onglets et du
JavaScript) : general, format, valeur automatique, calcul, plage, listes, listes dependantes, afficher / masquer.
Et l'ordre de tabulation."""
import re

import pymupdf as fitz
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit, QComboBox, QCheckBox,
                               QSpinBox, QDoubleSpinBox, QPlainTextEdit, QGroupBox, QListWidget, QListWidgetItem,
                               QDialogButtonBox, QTableWidget, QTableWidgetItem, QHeaderView, QPushButton, QScrollArea,
                               QWidget, QMessageBox, QAbstractItemView)

from PySide6.QtGui import QFont, QFontDatabase, QStandardItem
from .langue import _
from .dialogues import boutons_fr
from moteur import champs as C

T = fitz


def remplir_polices(combo, doc):
    """Liste des polices, chacune ecrite dans sa propre police : standard PDF, puis celles du document, puis celles
    de ce PC (integrees au PDF quand on les choisit)."""
    from moteur import apparence as AP

    def titre(t):
        combo.addItem("— " + t + " —", None)
        it = combo.model().item(combo.count() - 1)
        it.setEnabled(False)
        fo = QFont()
        fo.setBold(True)
        fo.setPointSize(9)
        it.setFont(fo)

    def ajouter(lib, cle, fo):
        combo.addItem(lib, cle)
        fo.setPointSize(12)
        combo.setItemData(combo.count() - 1, fo, Qt.FontRole)
    titre(_("Polices standard du PDF"))
    for k, lib, fam, gras, ital in (("Helv", "Helvetica", "Arial", False, False),
                                    ("HeBo", "Helvetica gras", "Arial", True, False),
                                    ("HeOb", "Helvetica italique", "Arial", False, True),
                                    ("TiRo", "Times", "Times New Roman", False, False),
                                    ("TiBo", "Times gras", "Times New Roman", True, False),
                                    ("TiIt", "Times italique", "Times New Roman", False, True),
                                    ("Cour", "Courier", "Courier New", False, False),
                                    ("CoBo", "Courier gras", "Courier New", True, False)):
        fo = QFont(fam)
        fo.setBold(gras)
        fo.setItalic(ital)
        ajouter(lib, k, fo)
    doc_pol = [(k, x) for k, x in AP.polices_formulaire(doc).items() if k not in AP.STANDARD and k not in ("ZaDb", "Symb")]
    if doc_pol:
        titre(_("Polices du document"))
        for k, x in doc_pol:
            nom = doc.xref_get_key(x, "BaseFont")[1].lstrip("/").split("+")[-1] or k
            fo = QFont()
            prog = AP.programme_police(doc, k)
            if prog:
                i = QFontDatabase.addApplicationFontFromData(prog)
                fams = QFontDatabase.applicationFontFamilies(i) if i >= 0 else []
                if fams:
                    fo = QFont(fams[0])
                    fo.setBold("Bold" in nom or "Gras" in nom)
                    fo.setItalic("Italic" in nom or "Oblique" in nom)
            ajouter(nom, k, fo)
    sys_pol = AP.polices_systeme()
    if sys_pol:
        titre(_("Polices de ce PC (intégrées au PDF)"))
        familles = set(QFontDatabase.families())
        for nom, chemin in sys_pol:
            fam = next((f for f in (nom, nom.rsplit(" ", 1)[0], nom.split(" ")[0]) if f in familles), None)
            fo = QFont(fam) if fam else QFont()
            if fam and ("Bold" in nom or "Gras" in nom):
                fo.setBold(True)
            if fam and ("Italic" in nom or "Italique" in nom):
                fo.setItalic(True)
            ajouter(nom, "fichier:" + chemin, fo)


def genres_format():
    return [("aucun", _("Aucun (texte libre)")), ("nombre", _("Nombre")), ("montant", _("Montant (€)")),
            ("pourcentage", _("Pourcentage")), ("date", _("Date")), ("heure", _("Heure")),
            ("telephone", _("Téléphone (06 12 34 56 78)")), ("code_postal", _("Code postal (06460)")),
            ("nir", _("N° de Sécurité sociale (1 78 09 2A 123 456 78)")),
            ("masque", _("Masque personnalisé (9 = chiffre, A = lettre)"))]


def separateurs():
    return [(2, "1.234,56"), (3, "1234,56"), (0, "1,234.56"), (1, "1234.56"), (4, "1'234.56")]


def type_lisible(w):
    return {T.PDF_WIDGET_TYPE_TEXT: _("Texte"), T.PDF_WIDGET_TYPE_CHECKBOX: _("Case à cocher"),
            T.PDF_WIDGET_TYPE_RADIOBUTTON: _("Bouton radio"), T.PDF_WIDGET_TYPE_COMBOBOX: _("Liste déroulante"),
            T.PDF_WIDGET_TYPE_LISTBOX: _("Liste"), T.PDF_WIDGET_TYPE_SIGNATURE: _("Signature"),
            T.PDF_WIDGET_TYPE_BUTTON: _("Bouton")}.get(w.field_type, "?")


def _choix(w):
    return [c if isinstance(c, str) else c[0] for c in (w.choice_values or [])]


class DialogueChamp(QDialog):
    def __init__(self, onglet, n, w):
        super().__init__(onglet)
        self.o, self.n, self.w, self.doc = onglet, n, w, onglet.doc
        self.r = C.lire(self.doc, w)
        self.setWindowTitle(_("Propriétés du champ « {x} »", x=w.field_name))
        self.resize(860, 720)
        ext = QVBoxLayout(self)
        corps = QHBoxLayout()
        ext.addLayout(corps, 1)
        self.sommaire = QListWidget()
        self.sommaire.setObjectName("ch_sommaire")
        self.sommaire.setFixedWidth(200)
        self.sommaire.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.sommaire.setWordWrap(True)
        self.sommaire.setToolTip(_("Cliquez pour aller à une partie des propriétés"))
        self.sommaire.setStyleSheet("QListWidget{border:none;background:#f3f5f8;font-size:13px}"
                                    "QListWidget::item{padding:7px 10px}"
                                    "QListWidget::item:selected{background:#dbe6f5;color:#123;border-left:3px solid #1462c2}")
        corps.addWidget(self.sommaire)
        zone = self.zone = QScrollArea()
        zone.setWidgetResizable(True)
        zone.setFrameShape(QScrollArea.NoFrame)
        zone.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        fond = QWidget()
        self.v = QVBoxLayout(fond)
        zone.setWidget(fond)
        corps.addWidget(zone, 1)
        self._sections = []
        def _suivre(_v):                       # la partie visible en haut est surlignee dans le sommaire
            haut = zone.verticalScrollBar().value()
            i = max((k for k, g in enumerate(self._sections) if g.y() <= haut + 20), default=0)
            self.sommaire.blockSignals(True)
            self.sommaire.setCurrentRow(i)
            self.sommaire.blockSignals(False)
        zone.verticalScrollBar().valueChanged.connect(_suivre)
        self.sommaire.currentRowChanged.connect(
            lambda i: zone.ensureWidgetVisible(self._sections[i], 0, 0) if 0 <= i < len(self._sections) else None)
        ft = w.field_type
        self.est_texte = ft == T.PDF_WIDGET_TYPE_TEXT
        self.est_liste = ft in (T.PDF_WIDGET_TYPE_COMBOBOX, T.PDF_WIDGET_TYPE_LISTBOX)
        self.est_case = ft in (T.PDF_WIDGET_TYPE_CHECKBOX, T.PDF_WIDGET_TYPE_RADIOBUTTON)
        autres = [x.field_name for _n, x in C.tous_les_champs(self.doc)
                  if x.field_name != w.field_name and x.field_type != T.PDF_WIDGET_TYPE_SIGNATURE]
        self.autres = list(dict.fromkeys(autres))
        self._general()
        if self.est_texte:
            self._texte()
        if self.est_liste:
            self._liste()
        if self.est_texte or self.est_liste:
            self._police()
        if self.est_texte or ft == T.PDF_WIDGET_TYPE_COMBOBOX:
            self._format()
        self.est_bouton = ft == T.PDF_WIDGET_TYPE_BUTTON
        if self.est_texte:
            self._controle()
            self._auto()
            self._calcul()
        if self.est_texte or ft == T.PDF_WIDGET_TYPE_COMBOBOX:
            self._plage()
        if self.est_liste:
            self._depend()
        if self.est_case:
            self._case()
        if self.est_case or self.est_liste:
            self._affiche()
        if self.est_bouton:
            self._bouton()
        if not self.est_bouton:
            self._aide()
        self.v.addStretch(1)
        self.sommaire.setCurrentRow(0)
        self._sans_molette()
        bb = boutons_fr(QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel))
        bb.accepted.connect(self.valider)
        bb.rejected.connect(self.reject)
        bas = QHBoxLayout()
        b_js = QPushButton(_("JavaScript..."))
        b_js.setObjectName("ch_javascript")
        b_js.setToolTip(_("Voir le code produit par ces réglages, ou ajouter le vôtre (pour Acrobat)"))
        b_js.clicked.connect(self.ouvrir_js)
        bas.addWidget(b_js)
        bas.addStretch(1)
        bas.addWidget(bb)
        ext.addLayout(bas)
        self.js_perso = None

    def _sans_molette(self):
        """La molette fait defiler la fenetre : elle ne change plus une liste ou un nombre survole par hasard
        (seulement celui dans lequel on a clique)."""
        from PySide6.QtCore import QObject, QEvent
        from PySide6.QtWidgets import QAbstractSpinBox

        class _Filtre(QObject):
            def eventFilter(self, obj, ev):
                if ev.type() == QEvent.Wheel and not obj.hasFocus():
                    ev.ignore()
                    return True
                return False
        self._filtre_molette = _Filtre(self)
        for w in self.findChildren(QComboBox) + self.findChildren(QAbstractSpinBox):
            w.setFocusPolicy(Qt.StrongFocus)
            w.installEventFilter(self._filtre_molette)

    def ouvrir_js(self):
        d = DialogueJavaScript(self, self.doc, self.w, self.r.get("js_seul") or [])
        if d.exec() == QDialog.Accepted:
            self.js_perso, self.js_seul = d.perso, d.seul

    def _groupe(self, titre):
        g = QGroupBox(titre)
        g.setStyleSheet("QGroupBox{font-weight:600;margin-top:14px} QGroupBox::title{subcontrol-origin:margin;left:6px}")
        f = QFormLayout(g)
        self.v.addWidget(g)
        self._sections.append(g)
        court = titre.split(" — ")[0].split(" (")[0]
        self.sommaire.addItem(court if len(court) <= 24 else court[:23].rstrip() + "…")
        self.sommaire.item(self.sommaire.count() - 1).setToolTip(titre)
        return f

    @staticmethod
    def _explication(f, texte):
        l = QLabel(texte)
        l.setWordWrap(True)
        l.setStyleSheet("color:#555;font-weight:normal")
        f.addRow(l)
        return l

    # ---------------------------------------------------------------- sections
    def _general(self):
        w = self.w
        f = self._groupe(_("Général") + " — " + type_lisible(w))
        self.nom = QLineEdit(w.field_name)
        self.nom.setObjectName("ch_nom")
        if w.field_type == T.PDF_WIDGET_TYPE_RADIOBUTTON:
            f.addRow(_("Groupe"), self.nom)
            self.valeur_radio = QLineEdit(w.on_state() if hasattr(w, "on_state") else "")
            self.valeur_radio.setReadOnly(True)
            f.addRow(_("Valeur de ce bouton"), self.valeur_radio)
        else:
            f.addRow(_("Nom"), self.nom)
        self.info = QLineEdit(w.field_label or "")
        self.info.setPlaceholderText(_("texte affiché au survol (facultatif)"))
        f.addRow(_("Info-bulle"), self.info)
        self.obligatoire = QCheckBox(_("Obligatoire"))
        self.obligatoire.setObjectName("ch_obligatoire")
        self.obligatoire.setChecked(bool(w.field_flags & T.PDF_FIELD_IS_REQUIRED))
        self.lecture = QCheckBox(_("Lecture seule"))
        self.lecture.setChecked(bool(w.field_flags & T.PDF_FIELD_IS_READ_ONLY))
        h = QHBoxLayout()
        h.addWidget(self.obligatoire)
        h.addWidget(self.lecture)
        h.addStretch(1)
        f.addRow("", h)
        self.affichage = QComboBox()
        for v, t in ((0, _("Visible")), (1, _("Masqué")), (2, _("Visible, non imprimé")), (3, _("Masqué, imprimé"))):
            self.affichage.addItem(t, v)
        self.affichage.setCurrentIndex(max(0, self.affichage.findData(w.field_display or 0)))
        f.addRow(_("Affichage"), self.affichage)

    def _case(self):
        from moteur import formulaire as FO
        w = self.w
        f = self._groupe(_("Coche"))
        self.c_style = QComboBox()
        self.c_style.setObjectName("ch_style_coche")
        noms = {"coche": _("Coche"), "croix": _("Croix"), "rond": _("Rond"), "carre": _("Carré"),
                "losange": _("Losange"), "etoile": _("Étoile")}
        for k, (_c, sym) in FO.STYLES_COCHE.items():
            self.c_style.addItem(f"{sym}   {noms[k]}", k)
        self.c_style.setCurrentIndex(max(0, self.c_style.findData(FO.style_coche(self.doc, w))))
        f.addRow(_("Signe quand c'est coché"), self.c_style)
        self.c_couleur = QComboBox()
        for k, t in (("0 0 0", _("Noir")), ("0.08 0.38 0.76", _("Bleu")), ("0.79 0.15 0.18", _("Rouge")),
                     ("0.13 0.52 0.24", _("Vert"))):
            self.c_couleur.addItem(t, k)
        f.addRow(_("Couleur"), self.c_couleur)
        if w.field_type == T.PDF_WIDGET_TYPE_CHECKBOX:
            self.c_valeur = QLineEdit(w.on_state() if hasattr(w, "on_state") and w.on_state() not in (True, None) else "Oui")
            self.c_valeur.setObjectName("ch_valeur_case")
            self.c_valeur.setToolTip(_("Ce que vaut la case cochée (lu par les calculs et quand on exporte les "
                                       "données) : Oui, X, Positif..."))
            f.addRow(_("Valeur quand c'est coché"), self.c_valeur)
            self.c_defaut = QCheckBox(_("Cochée par défaut (et remise cochée par « Réinitialiser »)"))
            self.c_defaut.setChecked(self.doc.xref_get_key(C.xref_champ(self.doc, w), "DV")[1] not in ("null", "/Off"))
            f.addRow(self.c_defaut)

    def _texte(self):
        w = self.w
        f = self._groupe(_("Texte"))
        self.multi = QCheckBox(_("Plusieurs lignes"))
        self.multi.setChecked(bool(w.field_flags & T.PDF_TX_FIELD_IS_MULTILINE))
        f.addRow("", self.multi)
        self.maxlen = QSpinBox()
        self.maxlen.setRange(0, 10000)
        self.maxlen.setSpecialValueText(_("illimitée"))
        self.maxlen.setValue(w.text_maxlen or 0)
        f.addRow(_("Longueur maximale"), self.maxlen)
        self.alignement = QComboBox()
        for v, t in ((0, _("A gauche")), (1, _("Centré")), (2, _("A droite"))):
            self.alignement.addItem(t, v)
        tq, q = self.doc.xref_get_key(C.xref_champ(self.doc, w), "Q")
        self.alignement.setCurrentIndex(max(0, self.alignement.findData(int(q) if tq == "int" else 0)))
        f.addRow(_("Alignement"), self.alignement)
        t_dv, dv = self.doc.xref_get_key(C.xref_champ(self.doc, w), "DV")
        self.defaut = QLineEdit(dv if t_dv == "string" else "")
        self.defaut.setObjectName("ch_defaut")
        self.defaut.setPlaceholderText(_("ce qui est écrit d'avance (et remis par « Réinitialiser »)"))
        f.addRow(_("Valeur par défaut"), self.defaut)

    def _police(self):
        """Police, taille et couleur du texte du champ (comme l'onglet Aspect d'Acrobat)."""
        from moteur import apparence as AP
        w = self.w
        f = self._groupe(_("Police du texte"))
        police, taille, couleur = AP.lire_da(self.doc, w)
        self.police = QComboBox()
        self.police.setObjectName("ch_police")
        self.police.setMaxVisibleItems(18)
        remplir_polices(self.police, self.doc)
        if self.police.findData(police) < 0:
            self.police.addItem(police, police)
        self.police.setCurrentIndex(self.police.findData(police))
        self.police.currentIndexChanged.connect(lambda _i: self._police_apercu())
        self._police_apercu()
        f.addRow(_("Police"), self.police)
        self.taille = QSpinBox()
        self.taille.setObjectName("ch_taille")
        self.taille.setRange(0, 96)
        self.taille.setSuffix(" pt")
        self.taille.setSpecialValueText(_("automatique (s'adapte au champ)"))
        self.taille.setValue(int(round(taille or 0)))
        f.addRow(_("Taille"), self.taille)
        self.couleur_txt = QComboBox()
        self.couleur_txt.setObjectName("ch_couleur")
        choix = [((0, 0, 0), _("Noir")), ((0.08, 0.38, 0.76), _("Bleu")), ((0, 0, 0.55), _("Bleu foncé")),
                 ((0.79, 0.15, 0.18), _("Rouge")), ((0.13, 0.52, 0.24), _("Vert")), ((0.4, 0.4, 0.4), _("Gris"))]
        for c, lib in choix:
            self.couleur_txt.addItem(lib, c)
        i = next((k for k, (c, _l) in enumerate(choix) if all(abs(a - b) < 0.02 for a, b in zip(c, couleur))), None)
        if i is None:
            self.couleur_txt.addItem(_("Couleur actuelle"), tuple(couleur))
            i = self.couleur_txt.count() - 1
        self.couleur_txt.setCurrentIndex(i)
        f.addRow(_("Couleur"), self.couleur_txt)

    def _police_apercu(self):
        """La liste fermee montre aussi le nom dans sa police (WYSIWYG)."""
        fo = self.police.itemData(self.police.currentIndex(), Qt.FontRole)
        if fo is not None:
            f2 = QFont(fo)
            f2.setPointSize(11)
            self.police.setFont(f2)

    def _format(self):
        fmt = self.r.get("format") or {"genre": "aucun"}
        f = self._groupe(_("Format"))
        self.f_genre = QComboBox()
        self.f_genre.setObjectName("ch_format")
        for k, t in genres_format():
            self.f_genre.addItem(t, k)
        genre = fmt.get("genre", "aucun")
        if genre == "nombre" and (fmt.get("symbole") or "").strip() == "€":
            genre = "montant"
        if genre == "masque":
            genre = next((k for k, m in C.MASQUES.items() if m == fmt.get("masque")), "masque")
        self.f_genre.setCurrentIndex(max(0, self.f_genre.findData(genre)))
        f.addRow(_("Type de valeur"), self.f_genre)
        self.f_dec = QSpinBox()
        self.f_dec.setRange(0, 6)
        self.f_dec.setValue(int(fmt.get("decimales", 2)))
        self.l_dec = QLabel(_("Décimales"))
        f.addRow(self.l_dec, self.f_dec)
        self.f_sep = QComboBox()
        for v, t in separateurs():
            self.f_sep.addItem(t, v)
        self.f_sep.setCurrentIndex(max(0, self.f_sep.findData(int(fmt.get("separateur", 2)))))
        self.l_sep = QLabel(_("Séparateurs"))
        f.addRow(self.l_sep, self.f_sep)
        self.f_sym = QLineEdit((fmt.get("symbole") or "").strip())
        self.f_avant = QCheckBox(_("avant le nombre"))
        self.f_avant.setChecked(bool(fmt.get("symbole_avant")))
        h = QHBoxLayout()
        h.addWidget(self.f_sym)
        h.addWidget(self.f_avant)
        self.l_sym = QLabel(_("Symbole"))
        self.w_sym = QWidget()
        self.w_sym.setLayout(h)
        h.setContentsMargins(0, 0, 0, 0)
        f.addRow(self.l_sym, self.w_sym)
        self.f_neg = QComboBox()
        for v, t in ((0, "-12,50"), (1, _("-12,50 en rouge")), (2, "(12,50)"), (3, _("(12,50) en rouge"))):
            self.f_neg.addItem(t, v)
        self.f_neg.setCurrentIndex(max(0, self.f_neg.findData(int(fmt.get("negatif", 0)))))
        self.l_neg = QLabel(_("Nombres négatifs"))
        f.addRow(self.l_neg, self.f_neg)
        self.f_date = QComboBox()
        self.f_date.setEditable(True)
        for d in C.DATES:
            self.f_date.addItem(f"{d}   ({C.ecrire_date(d)})", d)
        self.f_date.setCurrentText(fmt.get("date") or "dd/mm/yyyy")
        i = self.f_date.findData(fmt.get("date") or "dd/mm/yyyy")
        if i >= 0:
            self.f_date.setCurrentIndex(i)
        self.l_date = QLabel(_("Format de date"))
        f.addRow(self.l_date, self.f_date)
        self.f_heure = QComboBox()
        for d in C.HEURES:
            self.f_heure.addItem(f"{d}   ({C.ecrire_date(d)})", d)
        self.f_heure.setCurrentIndex(max(0, self.f_heure.findData(fmt.get("heure") or "HH:MM")))
        self.l_heure = QLabel(_("Format d'heure"))
        f.addRow(self.l_heure, self.f_heure)
        self.f_masque = QLineEdit(fmt.get("masque") or "")
        self.f_masque.setPlaceholderText("99 99 99 99 99")
        self.l_masque = QLabel(_("Masque"))
        f.addRow(self.l_masque, self.f_masque)
        self.f_genre.currentIndexChanged.connect(self._maj_format)
        self._maj_format()

    def _maj_format(self, *_a):
        g = self.f_genre.currentData()
        num = g in ("nombre", "montant", "pourcentage")
        for wdg in (self.l_dec, self.f_dec, self.l_sep, self.f_sep):
            wdg.setVisible(num)
        for wdg in (self.l_sym, self.w_sym, self.l_neg, self.f_neg):
            wdg.setVisible(g in ("nombre", "montant"))
        if g == "montant" and not self.f_sym.text():
            self.f_sym.setText("€")
        for wdg in (self.l_date, self.f_date):
            wdg.setVisible(g == "date")
        for wdg in (self.l_heure, self.f_heure):
            wdg.setVisible(g == "heure")
        for wdg in (self.l_masque, self.f_masque):
            wdg.setVisible(g == "masque")

    def _controle(self):
        f = self._groupe(_("Contrôle de la saisie"))
        self.majuscules = QComboBox()
        self.majuscules.setObjectName("ch_majuscules")
        for k, t in ((False, _("Laisser tel que tapé")), ("tout", _("TOUT EN MAJUSCULES (noms, villes...)")),
                     ("premiere", _("Première lettre en majuscule (Jean philippe)")),
                     ("mots", _("Première Lettre De Chaque Mot (Jean Philippe, Jean-Pierre)"))):
            self.majuscules.addItem(t, k)
        m_ = self.r.get("majuscules")
        self.majuscules.setCurrentIndex(max(0, self.majuscules.findData("tout" if m_ is True else (m_ or False))))
        f.addRow(_("Majuscules"), self.majuscules)
        self.controle = QComboBox()
        self.controle.setObjectName("ch_controle")
        for k, t in ((None, _("Aucun")), ("email", _("Adresse e-mail")), ("nir", _("N° de Sécurité sociale (avec la clef)")),
                     ("iban", _("IBAN")), ("siret", _("SIRET")), ("rpps", _("N° RPPS"))):
            self.controle.addItem(t, k)
        self.controle.setCurrentIndex(max(0, self.controle.findData(self.r.get("controle"))))
        f.addRow(_("Vérifier que c'est un"), self.controle)

    def _aide(self):
        a = self.r.get("aide") or {}
        f = self._groupe(_("Aide pour la personne qui remplit"))
        self.aide_entree = QLineEdit(a.get("entree", ""))
        self.aide_entree.setObjectName("ch_aide_entree")
        self.aide_entree.setPlaceholderText(_("ex. Indiquez la date de la dernière injection"))
        f.addRow(_("Message à l'entrée dans le champ"), self.aide_entree)
        self.aide_vide = QLineEdit(a.get("vide", ""))
        self.aide_vide.setObjectName("ch_aide_vide")
        self.aide_vide.setPlaceholderText(_("ex. Ce champ est obligatoire"))
        f.addRow(_("Message si on le laisse vide"), self.aide_vide)

    def _bouton(self):
        from .formulaire_doc import actions_bouton
        a = self.r.get("action") or {}
        f = self._groupe(_("Action du bouton"))
        self.b_legende = QLineEdit(self.w.button_caption or "")
        f.addRow(_("Texte du bouton"), self.b_legende)
        self.b_action = QComboBox()
        self.b_action.setObjectName("ch_action")
        for k, t in actions_bouton():
            self.b_action.addItem(t, k)
        self.b_action.setCurrentIndex(max(0, self.b_action.findData(a.get("genre"))))
        f.addRow(_("Quand on clique"), self.b_action)
        self.b_email = QLineEdit(a.get("email", ""))
        self.b_sujet = QLineEdit(a.get("sujet", ""))
        self.b_page = QSpinBox()
        self.b_page.setRange(1, max(1, len(self.doc)))
        self.b_page.setValue(int(a.get("page", 1)))
        self.l_email, self.l_sujet, self.l_page = QLabel(_("Destinataire")), QLabel(_("Objet")), QLabel(_("Page"))
        f.addRow(self.l_email, self.b_email)
        f.addRow(self.l_sujet, self.b_sujet)
        f.addRow(self.l_page, self.b_page)

        def maj(*_x):
            g = self.b_action.currentData()
            for wdg in (self.l_email, self.b_email, self.l_sujet, self.b_sujet):
                wdg.setVisible(g == "email")
            for wdg in (self.l_page, self.b_page):
                wdg.setVisible(g == "page")
        self.b_action.currentIndexChanged.connect(maj)
        maj()

    def _auto(self):
        f = self._groupe(_("Valeur automatique"))
        self.auto = QComboBox()
        self.auto.setObjectName("ch_auto")
        for k, t in ((None, _("Aucune")), ("date_clic", _("Date du jour quand on clique dans le champ (s'il est vide)")),
                     ("date_heure_clic", _("Date et heure quand on clique (s'il est vide)")),
                     ("heure_clic", _("Heure quand on clique (s'il est vide)"))):
            self.auto.addItem(t, k)
        self.auto.setCurrentIndex(max(0, self.auto.findData(self.r.get("auto"))))
        f.addRow(self.auto)

    def _calcul(self):
        c = self.r.get("calcul") or {}
        f = self._groupe(_("Calcul"))
        self.c_genre = QComboBox()
        self.c_genre.setObjectName("ch_calcul")
        for k, t in ((None, _("Aucun : la valeur est saisie")), ("somme", _("Somme (+) des champs cochés")),
                     ("produit", _("Produit (×) des champs cochés")), ("moyenne", _("Moyenne des champs cochés")),
                     ("min", _("Minimum des champs cochés")), ("max", _("Maximum des champs cochés")),
                     ("formule", _("Formule")), ("copie", _("Même valeur qu'un autre champ (champs liés)")),
                     ("age", _("Age d'après une date de naissance")), ("ecart_jours", _("Nombre de jours entre deux dates")),
                     ("date_plus", _("Date + un nombre de jours"))):
            self.c_genre.addItem(t, k)
        self.c_genre.setCurrentIndex(max(0, self.c_genre.findData(c.get("genre"))))
        f.addRow(self.c_genre)
        self.c_source, self.c_fin = QComboBox(), QComboBox()
        self.c_source.setObjectName("ch_calcul_source")
        self.c_fin.setObjectName("ch_calcul_fin")
        for cb in (self.c_source, self.c_fin):
            for nm in self.autres:
                cb.addItem(nm, nm)
        self.c_source.setCurrentIndex(max(0, self.c_source.findData(c.get("source") or c.get("debut"))))
        self.c_fin.setCurrentIndex(max(0, self.c_fin.findData(c.get("fin"))))
        self.c_jours = QSpinBox()
        self.c_jours.setRange(-3650, 3650)
        self.c_jours.setValue(int(c.get("jours", 30)))
        self.c_jours.setSuffix(" " + _("jours"))
        self.l_source, self.l_fin, self.l_jours = QLabel(_("Champ")), QLabel(_("jusqu'au champ")), QLabel(_("Ajouter"))
        f.addRow(self.l_source, self.c_source)
        f.addRow(self.l_fin, self.c_fin)
        f.addRow(self.l_jours, self.c_jours)
        self.c_champs = QListWidget()
        self.c_champs.setObjectName("ch_calcul_champs")
        self.c_champs.setMaximumHeight(130)
        for nm in self.autres:
            it = QListWidgetItem(nm)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if nm in (c.get("champs") or []) else Qt.Unchecked)
            self.c_champs.addItem(it)
        f.addRow(self.c_champs)
        h = QHBoxLayout()
        self.c_formule = QLineEdit(c.get("formule", ""))
        self.c_formule.setObjectName("ch_formule")
        self.c_formule.setPlaceholderText(_("ex. [Quantité] * [Prix unitaire]"))
        h.addWidget(self.c_formule, 1)
        self.c_inserer = QComboBox()
        self.c_inserer.addItem(_("Insérer un champ..."), None)
        for nm in self.autres:
            self.c_inserer.addItem(nm, nm)
        self.c_inserer.activated.connect(self._inserer)
        h.addWidget(self.c_inserer)
        self.w_formule = QWidget()
        self.w_formule.setLayout(h)
        h.setContentsMargins(0, 0, 0, 0)
        f.addRow(self.w_formule)
        self.c_aide = QLabel(_("Opérations : + − × (*) ÷ (/) et parenthèses. Les noms de champs entre crochets."))
        self.c_aide.setStyleSheet("color:#666")
        f.addRow(self.c_aide)
        self.c_explique = self._explication(f, "")
        self.c_explique.setObjectName("ch_calcul_explication")
        self.c_explique.setStyleSheet("color:#1d4f86;background:#eef4fb;border-radius:4px;padding:6px;font-weight:normal")
        self.c_genre.currentIndexChanged.connect(self._maj_calcul)
        self._maj_calcul()

    def _inserer(self, i):
        nm = self.c_inserer.itemData(i)
        if nm:
            self.c_formule.insert(f"[{nm}]")
        self.c_inserer.setCurrentIndex(0)

    def _maj_calcul(self, *_a):
        g = self.c_genre.currentData()
        self.c_champs.setVisible(g in C.CALCULS)
        self.w_formule.setVisible(g == "formule")
        self.c_aide.setVisible(g == "formule")
        for wdg in (self.l_source, self.c_source):
            wdg.setVisible(g in ("copie", "age", "ecart_jours", "date_plus"))
        self.l_source.setText(_("Du champ") if g == "ecart_jours" else _("Champ"))
        for wdg in (self.l_fin, self.c_fin):
            wdg.setVisible(g == "ecart_jours")
        for wdg in (self.l_jours, self.c_jours):
            wdg.setVisible(g == "date_plus")
        self.c_explique.setText({
            None: _("Le champ se remplit à la main."),
            "somme": _("Additionne les champs cochés ci-dessous. Exemple : Total = Ligne 1 + Ligne 2 + Ligne 3."),
            "produit": _("Multiplie les champs cochés. Exemple : Montant = Quantité × Prix."),
            "moyenne": _("Moyenne des champs cochés. Exemple : la note moyenne de trois notes."),
            "min": _("Garde la plus petite valeur parmi les champs cochés."),
            "max": _("Garde la plus grande valeur parmi les champs cochés."),
            "formule": _("Votre calcul, avec les noms des champs entre crochets. Exemple : [Quantité] * [Prix] * 1,2 "
                         "pour un prix TTC. Utilisez « Insérer un champ... » pour ne pas faire de faute de nom."),
            "copie": _("Recopie tout seul la valeur d'un autre champ. Exemple : le nom du patient tapé page 1 réapparaît "
                       "page 3."),
            "age": _("Calcule l'âge à partir d'un champ « date de naissance »."),
            "ecart_jours": _("Nombre de jours entre deux champs date. Exemple : du début à la fin d'un traitement."),
            "date_plus": _("Une date plus un nombre de jours. Exemple : date du vaccin + 30 jours = date du rappel."),
        }.get(g, ""))

    def _plage(self):
        p = self.r.get("plage") or {}
        f = self._groupe(_("Valeurs autorisées"))
        self.p_min_on = QCheckBox(_("au moins"))
        self.p_min = QDoubleSpinBox()
        self.p_max_on = QCheckBox(_("au plus"))
        self.p_max = QDoubleSpinBox()
        for sp in (self.p_min, self.p_max):
            sp.setRange(-1e12, 1e12)
            sp.setDecimals(2)
        self.p_min_on.setChecked(p.get("min") is not None)
        self.p_max_on.setChecked(p.get("max") is not None)
        self.p_min.setValue(p.get("min") or 0)
        self.p_max.setValue(p.get("max") or 0)
        h = QHBoxLayout()
        for x in (self.p_min_on, self.p_min, self.p_max_on, self.p_max):
            h.addWidget(x)
        h.addStretch(1)
        f.addRow(h)

    def _liste(self):
        w = self.w
        f = self._groupe(_("Choix de la liste"))
        self._explication(f, _("Liste déroulante : une seule ligne, on clique pour voir les choix et en prendre un. "
                               "Liste ouverte : plusieurs lignes visibles d'un coup, utile pour voir tous les choix sans cliquer, "
                               "et la seule qui permet de cocher plusieurs choix."))
        self.l_items = QPlainTextEdit("\n".join(_choix(w)))
        self.l_items.setObjectName("ch_items")
        self.l_items.setPlaceholderText(_("un choix par ligne"))
        self.l_items.setMaximumHeight(120)
        f.addRow(self.l_items)
        t_dv, dv = self.doc.xref_get_key(C.xref_champ(self.doc, w), "DV")
        self.l_defaut = QComboBox()
        self.l_defaut.setObjectName("ch_liste_defaut")
        self.l_defaut.addItem(_("(aucun : vide)"), "")
        for c in _choix(w):
            self.l_defaut.addItem(c, c)
        self.l_defaut.setCurrentIndex(max(0, self.l_defaut.findData(dv if t_dv == "string" else "")))
        self.l_items.textChanged.connect(self._maj_defaut_liste)
        f.addRow(_("Choix montré par défaut"), self.l_defaut)
        self.l_trier = QCheckBox(_("Trier par ordre alphabétique"))
        self.l_trier.setChecked(bool(w.field_flags & T.PDF_CH_FIELD_IS_SORT))
        f.addRow(self.l_trier)
        if w.field_type == T.PDF_WIDGET_TYPE_COMBOBOX:
            self.l_libre = QCheckBox(_("Autoriser une saisie libre"))
            self.l_libre.setChecked(bool(w.field_flags & T.PDF_CH_FIELD_IS_EDIT))
            f.addRow(self.l_libre)
        else:
            self.l_multi = QCheckBox(_("Plusieurs choix possibles"))
            self.l_multi.setChecked(bool(w.field_flags & T.PDF_CH_FIELD_IS_MULTI_SELECT))
            f.addRow(self.l_multi)

    def _maj_defaut_liste(self):
        garde = self.l_defaut.currentData()
        self.l_defaut.blockSignals(True)
        self.l_defaut.clear()
        self.l_defaut.addItem(_("(aucun : vide)"), "")
        for c in [x.strip() for x in self.l_items.toPlainText().splitlines() if x.strip()]:
            self.l_defaut.addItem(c, c)
        self.l_defaut.setCurrentIndex(max(0, self.l_defaut.findData(garde)))
        self.l_defaut.blockSignals(False)

    def _depend(self):
        d = self.r.get("depend") or {}
        f = self._groupe(_("Liste dépendante (ex. Ville selon le Pays)"))
        self.d_parent = QComboBox()
        self.d_parent.setObjectName("ch_depend")
        self.d_parent.addItem(_("Ne dépend d'aucun champ"), None)
        for _n, x in C.tous_les_champs(self.doc):
            if x.field_name != self.w.field_name and x.field_type in (T.PDF_WIDGET_TYPE_COMBOBOX, T.PDF_WIDGET_TYPE_LISTBOX,
                                                                        T.PDF_WIDGET_TYPE_RADIOBUTTON) \
                    and self.d_parent.findData(x.field_name) < 0:
                self.d_parent.addItem(_("Dépend de « {x} »", x=x.field_name), x.field_name)
        self.d_parent.setCurrentIndex(max(0, self.d_parent.findData(d.get("parent"))))
        f.addRow(self.d_parent)
        self.d_table = QTableWidget(0, 2)
        self.d_table.setObjectName("ch_depend_table")
        self.d_table.setHorizontalHeaderLabels([_("Si le champ vaut"), _("proposer (séparés par ;)")])
        self.d_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.d_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.d_table.verticalHeader().hide()
        self.d_table.setMinimumHeight(130)
        f.addRow(self.d_table)
        self._listes_dep = dict(d.get("listes") or {})
        self.d_parent.currentIndexChanged.connect(self._maj_depend)
        self._maj_depend()

    def _valeurs_parent(self, nom):
        vals = []
        for _n, x in C.tous_les_champs(self.doc):
            if x.field_name == nom:
                if x.field_type == T.PDF_WIDGET_TYPE_RADIOBUTTON:
                    try:
                        vals.append(x.on_state())
                    except Exception:                     # noqa: BLE001
                        pass
                else:
                    vals += _choix(x)
        return list(dict.fromkeys(v for v in vals if v and v != "Off"))

    def _maj_depend(self, *_a):
        self._lire_table()
        nom = self.d_parent.currentData()
        self.d_table.setVisible(bool(nom))
        self.d_table.setRowCount(0)
        if not nom:
            return
        for val in self._valeurs_parent(nom):
            r = self.d_table.rowCount()
            self.d_table.insertRow(r)
            a = QTableWidgetItem(val)
            a.setFlags(a.flags() & ~Qt.ItemIsEditable)
            self.d_table.setItem(r, 0, a)
            self.d_table.setItem(r, 1, QTableWidgetItem("; ".join(self._listes_dep.get(val, []))))

    def _lire_table(self):
        if not hasattr(self, "d_table"):
            return
        for r in range(self.d_table.rowCount()):
            a, b = self.d_table.item(r, 0), self.d_table.item(r, 1)
            if a is not None:
                self._listes_dep[a.text()] = [x.strip() for x in (b.text() if b else "").split(";") if x.strip()]

    def _affiche(self):
        a = self.r.get("affiche") or {}
        f = self._groupe(_("Afficher d'autres champs selon ce champ"))
        self.a_on = QCheckBox(_("Afficher les champs cochés ci-dessous seulement si"))
        self.a_on.setObjectName("ch_affiche")
        self.a_on.setChecked(bool(a.get("cibles")))
        f.addRow(self.a_on)
        if self.w.field_type == T.PDF_WIDGET_TYPE_CHECKBOX:
            self.a_valeur = None
            f.addRow(QLabel("    " + _("cette case est cochée")))
        else:
            self.a_valeur = QComboBox()
            self.a_valeur.setEditable(True)
            vals = self._valeurs_parent(self.w.field_name)
            self.a_valeur.addItems(vals)
            self.a_valeur.setCurrentText(a.get("valeur", vals[0] if vals else ""))
            f.addRow(_("la valeur est"), self.a_valeur)
        self.a_cibles = QListWidget()
        self.a_cibles.setObjectName("ch_affiche_cibles")
        self.a_cibles.setMaximumHeight(130)
        for nm in self.autres:
            it = QListWidgetItem(nm)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if nm in (a.get("cibles") or []) else Qt.Unchecked)
            self.a_cibles.addItem(it)
        f.addRow(self.a_cibles)

    # ---------------------------------------------------------------- valider
    @staticmethod
    def _coches(lst):
        return [lst.item(i).text() for i in range(lst.count()) if lst.item(i).checkState() == Qt.Checked]

    def regles(self):
        r = C.vide()
        r["js_seul"] = list(getattr(self, "js_seul", self.r.get("js_seul") or []))
        if hasattr(self, "f_genre"):
            g = self.f_genre.currentData()
            if g in ("nombre", "montant"):
                r["format"] = {"genre": "nombre", "decimales": self.f_dec.value(), "separateur": self.f_sep.currentData(),
                               "negatif": self.f_neg.currentData(), "symbole": self.f_sym.text().strip(),
                               "symbole_avant": self.f_avant.isChecked()}
            elif g == "pourcentage":
                r["format"] = {"genre": "pourcentage", "decimales": self.f_dec.value(), "separateur": self.f_sep.currentData()}
            elif g == "date":
                r["format"] = {"genre": "date", "date": self.f_date.currentData() or self.f_date.currentText().split("   ")[0].strip()}
            elif g == "heure":
                r["format"] = {"genre": "heure", "heure": self.f_heure.currentData()}
            elif g in C.MASQUES:
                r["format"] = {"genre": "masque", "masque": C.MASQUES[g]}
            elif g == "masque" and self.f_masque.text().strip():
                r["format"] = {"genre": "masque", "masque": self.f_masque.text()}
        if hasattr(self, "auto"):
            r["auto"] = self.auto.currentData()
            if r["auto"] and r["format"]["genre"] == "aucun":
                r["format"] = ({"genre": "heure", "heure": "HH:MM"} if r["auto"] == "heure_clic" else
                               {"genre": "date", "date": "dd/mm/yyyy HH:MM" if r["auto"] == "date_heure_clic" else "dd/mm/yyyy"})
        if hasattr(self, "c_genre") and self.c_genre.currentData():
            g = self.c_genre.currentData()
            if g == "formule":
                r["calcul"] = {"genre": "formule", "formule": self.c_formule.text().strip()}
            elif g in ("copie", "age"):
                r["calcul"] = {"genre": g, "source": self.c_source.currentData()}
            elif g == "ecart_jours":
                r["calcul"] = {"genre": g, "debut": self.c_source.currentData(), "fin": self.c_fin.currentData()}
            elif g == "date_plus":
                r["calcul"] = {"genre": g, "source": self.c_source.currentData(), "jours": self.c_jours.value()}
                if r["format"]["genre"] != "date":
                    r["format"] = {"genre": "date", "date": "dd/mm/yyyy"}
            else:
                r["calcul"] = {"genre": g, "champs": self._coches(self.c_champs)}
        if hasattr(self, "majuscules"):
            r["majuscules"] = self.majuscules.currentData() or False
            r["controle"] = self.controle.currentData()
        if hasattr(self, "f_genre") and self.f_genre.currentData() == "nir" and not r.get("controle"):
            r["controle"] = "nir"                          # le format N° SS verifie aussi la clef
        c_ = r.get("calcul") or {}
        if c_.get("genre") in C.CALCULS and not c_.get("champs"):
            r["calcul"] = None                             # aucun champ coche : pas de calcul
        if hasattr(self, "aide_entree") and (self.aide_entree.text().strip() or self.aide_vide.text().strip()):
            r["aide"] = {"entree": self.aide_entree.text().strip(), "vide": self.aide_vide.text().strip()}
        if hasattr(self, "b_action"):
            g = self.b_action.currentData()
            r["action"] = {"genre": g}
            if g == "email":
                r["action"].update(email=self.b_email.text().strip(), sujet=self.b_sujet.text().strip())
            elif g == "page":
                r["action"]["page"] = self.b_page.value()
        if hasattr(self, "p_min_on") and (self.p_min_on.isChecked() or self.p_max_on.isChecked()):
            r["plage"] = {"min": self.p_min.value() if self.p_min_on.isChecked() else None,
                          "max": self.p_max.value() if self.p_max_on.isChecked() else None}
        if hasattr(self, "d_parent") and self.d_parent.currentData():
            self._lire_table()
            vals = self._valeurs_parent(self.d_parent.currentData())
            r["depend"] = {"parent": self.d_parent.currentData(),
                           "listes": {k: v for k, v in self._listes_dep.items() if k in vals}}
        if hasattr(self, "a_on") and self.a_on.isChecked() and self._coches(self.a_cibles):
            r["affiche"] = {"cibles": self._coches(self.a_cibles),
                            "quand": "coche" if self.a_valeur is None else "valeur",
                            "valeur": self.a_valeur.currentText() if self.a_valeur is not None else ""}
        return r

    def valider(self):
        nom = self.nom.text().strip()
        if not nom:
            QMessageBox.warning(self, self.windowTitle(), _("Indiquez un nom."))
            return
        if nom != self.w.field_name and self.w.field_type != T.PDF_WIDGET_TYPE_RADIOBUTTON and nom in self.autres:
            QMessageBox.warning(self, self.windowTitle(), _("Un champ porte déjà ce nom."))
            return
        r = self.regles()
        c = r.get("calcul")
        if c and c.get("genre") == "formule":
            try:
                inconnus = [v for t, v in C.jetons_formule(c["formule"]) if t == "champ" and v not in self.autres]
            except ValueError:
                QMessageBox.warning(self, self.windowTitle(), _("Formule incorrecte : vérifiez les crochets et les opérations."))
                return
            if inconnus:
                QMessageBox.warning(self, self.windowTitle(), _("Champ inconnu dans la formule : {x}", x=", ".join(inconnus)))
                return
        self.resultat = {"nom": nom, "info": self.info.text().strip(), "obligatoire": self.obligatoire.isChecked(),
                         "lecture": self.lecture.isChecked(), "affichage": self.affichage.currentData(), "regles": r,
                         "js_perso": self.js_perso}
        if self.est_bouton:
            self.resultat["legende"] = self.b_legende.text().strip()
        if getattr(self, "police", None) is not None:
            from moteur import apparence as AP
            self.resultat["police"] = {"nom": self.police.currentData() or AP.lire_da(self.doc, self.w)[0],
                                       "taille": self.taille.value(),
                                       "couleur": tuple(self.couleur_txt.currentData())}
        if getattr(self, "c_style", None) is not None:
            self.resultat["coche"] = {"style": self.c_style.currentData(),
                                      "couleur": tuple(float(x) for x in self.c_couleur.currentData().split()),
                                      "valeur": self.c_valeur.text().strip() if hasattr(self, "c_valeur") else None,
                                      "defaut": self.c_defaut.isChecked() if hasattr(self, "c_defaut") else None}
        if self.est_texte:
            self.resultat["defaut"] = self.defaut.text()
        if self.est_liste:
            self.resultat["defaut"] = self.l_defaut.currentData() or ""
        if self.est_texte:
            self.resultat.update(multi=self.multi.isChecked(), maxlen=self.maxlen.value(),
                                 alignement=self.alignement.currentData(), taille=self.taille.value())
        if self.est_liste:
            items = [x.strip() for x in self.l_items.toPlainText().splitlines() if x.strip()]
            self.resultat.update(items=items, trier=self.l_trier.isChecked(),
                                 libre=getattr(self, "l_libre", None) is not None and self.l_libre.isChecked(),
                                 multiple=getattr(self, "l_multi", None) is not None and self.l_multi.isChecked())
        self.accept()


# ================================================================ ordre de tabulation
class DialogueTabulation(QDialog):
    """Ordre dans lequel la touche Tab passe d'un champ a l'autre, page par page."""

    def __init__(self, onglet, n):
        super().__init__(onglet)
        self.o, self.n = onglet, n
        self.setWindowTitle(_("Ordre de tabulation — page {n}", n=n + 1))
        self.resize(420, 480)
        v = QVBoxLayout(self)
        v.addWidget(QLabel(_("Glissez les champs dans l'ordre voulu :")))
        self.liste = QListWidget()
        self.liste.setObjectName("tab_liste")
        self.liste.setDragDropMode(QAbstractItemView.InternalMove)
        v.addWidget(self.liste, 1)
        self.widgets = [w for w in (onglet.doc[n].widgets() or [])]
        for w in self.widgets:
            it = QListWidgetItem(f"{w.field_name}  ({type_lisible(w)})")
            it.setData(Qt.UserRole, w.xref)
            self.liste.addItem(it)
        h = QHBoxLayout()
        b = QPushButton(_("Ordre automatique (lignes, de gauche à droite)"))
        b.setObjectName("tab_auto")
        b.clicked.connect(self.auto)
        h.addWidget(b)
        h.addStretch(1)
        v.addLayout(h)
        bb = boutons_fr(QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def auto(self):
        par_xref = {w.xref: w for w in self.widgets}
        items = [self.liste.takeItem(0) for _i in range(self.liste.count())]

        def cle(it):
            r = par_xref[it.data(Qt.UserRole)].rect
            return (round(r.y0 / 8), r.x0)
        for it in sorted(items, key=cle):
            self.liste.addItem(it)

    def ordre(self):
        return [self.liste.item(i).data(Qt.UserRole) for i in range(self.liste.count())]


class DialogueJavaScript(QDialog):
    """Le JavaScript du champ, evenement par evenement : ce que PhilPDF produit (suit les reglages, en lecture seule)
    et votre code, garde tel quel. « Mon code seul » : PhilPDF n'ecrit plus rien pour cet evenement."""

    def __init__(self, parent, doc, w, seul):
        super().__init__(parent)
        from PySide6.QtWidgets import QTabWidget
        from PySide6.QtGui import QFont
        self.setWindowTitle(_("JavaScript du champ « {nom} »", nom=w.field_name))
        self.resize(820, 600)
        v = QVBoxLayout(self)
        l = QLabel(_("En haut, le code que PhilPDF écrit d'après vos réglages (il se refait tout seul). En bas, votre "
                     "code : il est gardé tel quel. Il marche dans Acrobat et les lecteurs qui gèrent le JavaScript ; "
                     "PhilPDF, lui, applique ses propres réglages sans exécuter votre code."))
        l.setWordWrap(True)
        l.setStyleSheet("color:#555")
        v.addWidget(l)
        self.onglets = QTabWidget()
        v.addWidget(self.onglets, 1)
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.Monospace)
        self.editeurs, self.cases = {}, {}
        codes = C.js_du_champ(doc, w)
        noms = {"K": _("Frappe"), "F": _("Mise en forme"), "V": _("Validation"), "C": _("Calcul"),
                "Fo": _("Entrée dans le champ"), "Bl": _("Sortie du champ"), "U": _("Clic")}
        aides = {"K": _("A chaque touche tapée (event.change, event.willCommit)."),
                 "F": _("Pour afficher la valeur (event.value), sans la changer."),
                 "V": _("Quand la valeur est validée ; event.rc = false la refuse."),
                 "C": _("Pour calculer la valeur à partir d'autres champs (this.getField(\"Nom\").value)."),
                 "Fo": _("Quand on entre dans le champ."), "Bl": _("Quand on quitte le champ."),
                 "U": _("Quand on clique (boutons, cases).")}
        for k, _l in C.EVENEMENTS:
            philpdf, perso = codes.get(k, ("", ""))
            page = QWidget()
            pv = QVBoxLayout(page)
            a = QLabel(aides[k])
            a.setStyleSheet("color:#555")
            pv.addWidget(a)
            pv.addWidget(QLabel("<b>" + _("Produit par PhilPDF") + "</b>"))
            g = QPlainTextEdit(philpdf or _("(rien pour cet événement)"))
            g.setReadOnly(True)
            g.setFont(mono)
            g.setStyleSheet("background:#f4f4f4;color:#444")
            g.setMaximumHeight(140)
            pv.addWidget(g)
            pv.addWidget(QLabel("<b>" + _("Votre code") + "</b>"))
            e = QPlainTextEdit(perso)
            e.setFont(mono)
            e.setObjectName("js_" + k)
            e.setPlaceholderText(_("Exemple : if (event.value == \"\") app.alert(\"Champ à remplir\");"))
            pv.addWidget(e, 1)
            c = QCheckBox(_("Mon code seul : ne plus écrire le code PhilPDF de cet événement"))
            c.setChecked(k in seul)
            pv.addWidget(c)
            if philpdf:
                bc = QPushButton(_("Reprendre le code PhilPDF pour le modifier"))
                bc.clicked.connect(lambda _x=False, e=e, c=c, code=philpdf: (
                    e.setPlainText((e.toPlainText().strip() + "\n" + code).strip()), c.setChecked(True)))
                pv.addWidget(bc)
            self.editeurs[k], self.cases[k] = e, c
            self.onglets.addTab(page, noms[k] + (" ●" if philpdf or perso else ""))
        bb = boutons_fr(QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel))
        bb.accepted.connect(self.valider)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def valider(self):
        for k, e in self.editeurs.items():           # controle simple : accolades et parentheses equilibrees
            t = re.sub(r"(\"(?:\\.|[^\"])*\"|'(?:\\.|[^'])*'|//[^\n]*|/\*.*?\*/)", "", e.toPlainText(), flags=re.S)
            if t.count("{") != t.count("}") or t.count("(") != t.count(")"):
                QMessageBox.warning(self, self.windowTitle(),
                                    _("Onglet « {e} » : une accolade ou une parenthèse n'est pas refermée.",
                                      e=self.onglets.tabText(list(self.editeurs).index(k)).rstrip(" ●")))
                self.onglets.setCurrentIndex(list(self.editeurs).index(k))
                return
        self.perso = {k: e.toPlainText() for k, e in self.editeurs.items()}
        self.seul = [k for k, c in self.cases.items() if c.isChecked()]
        self.accept()
