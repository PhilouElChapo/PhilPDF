"""Proprietes d'un champ de formulaire, en une seule fenetre simple (ce qu'Acrobat range dans six onglets et du
JavaScript) : general, format, valeur automatique, calcul, plage, listes, listes dependantes, afficher / masquer.
Et l'ordre de tabulation."""
import pymupdf as fitz
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit, QComboBox, QCheckBox,
                               QSpinBox, QDoubleSpinBox, QPlainTextEdit, QGroupBox, QListWidget, QListWidgetItem,
                               QDialogButtonBox, QTableWidget, QTableWidgetItem, QHeaderView, QPushButton, QScrollArea,
                               QWidget, QMessageBox, QAbstractItemView)

from .langue import _
from .dialogues import boutons_fr
from moteur import champs as C

T = fitz


def genres_format():
    return [("aucun", _("Aucun (texte libre)")), ("nombre", _("Nombre")), ("montant", _("Montant (€)")),
            ("pourcentage", _("Pourcentage")), ("date", _("Date")), ("heure", _("Heure")),
            ("telephone", _("Téléphone (06 12 34 56 78)")), ("code_postal", _("Code postal (06460)")),
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
        self.resize(620, 640)
        ext = QVBoxLayout(self)
        zone = QScrollArea()
        zone.setWidgetResizable(True)
        zone.setFrameShape(QScrollArea.NoFrame)
        fond = QWidget()
        self.v = QVBoxLayout(fond)
        zone.setWidget(fond)
        ext.addWidget(zone, 1)
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
        if self.est_texte or ft == T.PDF_WIDGET_TYPE_COMBOBOX:
            self._format()
        if self.est_texte:
            self._auto()
            self._calcul()
        if self.est_texte or ft == T.PDF_WIDGET_TYPE_COMBOBOX:
            self._plage()
        if self.est_liste:
            self._depend()
        if self.est_case or self.est_liste:
            self._affiche()
        self.v.addStretch(1)
        bb = boutons_fr(QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel))
        bb.accepted.connect(self.valider)
        bb.rejected.connect(self.reject)
        ext.addWidget(bb)

    def _groupe(self, titre):
        g = QGroupBox(titre)
        f = QFormLayout(g)
        self.v.addWidget(g)
        return f

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
        self.taille = QSpinBox()
        self.taille.setRange(0, 72)
        self.taille.setSpecialValueText(_("automatique"))
        self.taille.setValue(int(w.text_fontsize or 0))
        f.addRow(_("Taille du texte"), self.taille)

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
                     ("formule", _("Formule"))):
            self.c_genre.addItem(t, k)
        self.c_genre.setCurrentIndex(max(0, self.c_genre.findData(c.get("genre"))))
        f.addRow(self.c_genre)
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
        self.l_items = QPlainTextEdit("\n".join(_choix(w)))
        self.l_items.setObjectName("ch_items")
        self.l_items.setPlaceholderText(_("un choix par ligne"))
        self.l_items.setMaximumHeight(120)
        f.addRow(self.l_items)
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
            r["calcul"] = ({"genre": "formule", "formule": self.c_formule.text().strip()} if g == "formule"
                           else {"genre": g, "champs": self._coches(self.c_champs)})
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
                         "lecture": self.lecture.isChecked(), "affichage": self.affichage.currentData(), "regles": r}
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
