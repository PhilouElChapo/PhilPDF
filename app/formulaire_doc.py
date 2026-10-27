"""Formulaire dans un document ouvert : proprietes des champs, types a tracer, ordre de tabulation, et dans PhilPDF
le meme comportement que dans Acrobat (formats, date automatique, calculs, listes dependantes, afficher / masquer).

Melange (mixin) de OngletDocument."""
import re

import pymupdf as fitz
from PySide6.QtWidgets import QDialog, QMessageBox, QInputDialog

from .langue import _
from moteur import champs as C
from moteur import formulaire as FO

T = fitz


def types_a_tracer():
    return [("auto", _("Automatique")), ("texte", _("Texte")), ("case", _("Case à cocher")),
            ("radio", _("Bouton radio")), ("liste", _("Liste déroulante")), ("liste_multiple", _("Liste")),
            ("date", _("Date")), ("montant", _("Montant (€)")), ("signature", _("Signature"))]


class MixinFormulaire:
    # ------------------------------------------------------------ creer
    def creer_champ_type(self, n, r, genre):
        """Champ du type choisi dans le bandeau du formulaire ; renvoie False si annule."""
        if genre == "signature":
            self.ajouter_champ_signature(n, r)
            return True
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
            self._maj_widget(x)
            if "alignement" in res:
                self.doc.xref_set_key(C.xref_champ(self.doc, x), "Q", str(res["alignement"]) if res["alignement"] else "null")
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
        if aff != brut:
            self.doc.xref_set_key(C.xref_champ(self.doc, w), "V", fitz.get_pdf_str(brut) if brut else "null")

    def valeur_auto(self, w):
        """Date ou heure du moment si le champ le demande et qu'il est vide (comme Acrobat a l'entree du champ)."""
        r = self.regles_champ(w)
        if not r.get("auto") or (w.field_value or ""):
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
                   "plage": self._message_plage(r)}.get(err, err)
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
            val = C.valeur_brute(C.calculer(r, self.valeurs()))
            if (x.field_value or "") != val:
                self._ecrire_valeur(x, val, r)

    def champs_obligatoires_vides(self):
        out = []
        for _n, w in C.tous_les_champs(self.doc):
            if w.field_flags & T.PDF_FIELD_IS_REQUIRED and w.field_type != T.PDF_WIDGET_TYPE_SIGNATURE:
                if (w.field_value or "") in ("", "Off"):
                    out.append(w.field_name)
        return list(dict.fromkeys(out))
