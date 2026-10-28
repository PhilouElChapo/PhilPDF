"""Signature numerique dans un document ouvert : bandeau d'etat, signer, champs de signature, verrouillage.

Melange (mixin) de OngletDocument : utilise self.doc, self.params, self.chemin, self._octets()...
"""
import os
import re
import tempfile

import pymupdf as fitz
from PySide6.QtCore import Qt, QThread, Signal, QEventLoop, QTimer
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton, QFileDialog, QMessageBox, QDialog,
                               QApplication, QProgressDialog)

from .langue import _
from .icones import icone
from moteur import signature_num as S

SIG = fitz.PDF_WIDGET_TYPE_SIGNATURE


class _Tache(QThread):
    fini = Signal(object, object)

    def __init__(self, f):
        super().__init__()
        self.f = f

    def run(self):
        try:
            self.fini.emit(self.f(), None)
        except Exception as e:                            # noqa: BLE001
            self.fini.emit(None, e)


def en_fond(parent, texte, f):
    """Execute f() dans un fil a part, avec une petite fenetre d'attente ; renvoie son resultat ou leve son erreur."""
    if os.environ.get("PHILPDF_SANS_FIL"):                # tests : directement
        return f()
    boucle, res = QEventLoop(), {}
    t = _Tache(f)
    t.fini.connect(lambda r, e: (res.update(r=r, e=e), boucle.quit()))
    prog = QProgressDialog(texte, None, 0, 0, parent)
    prog.setWindowTitle("PhilPDF")
    prog.setWindowModality(Qt.WindowModal)
    prog.setMinimumDuration(400)
    t.start()
    boucle.exec()
    t.wait()
    prog.close()
    if res.get("e") is not None:
        raise res["e"]
    return res.get("r")


def _chaine_pdf(t):
    return "(" + t.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ")"


class MixinSignature:
    # ------------------------------------------------------------ bandeau
    def _construire_bandeau_sig(self, v):
        self.signatures, self.champs_sig_vides, self.champs_verrouilles = [], [], set()
        self.bandeau_sig = QFrame()
        self.bandeau_sig.setObjectName("bandeausig")
        h = QHBoxLayout(self.bandeau_sig)
        h.setContentsMargins(16, 5, 16, 5)
        self.ico_sig = QLabel()
        h.addWidget(self.ico_sig)
        self.lbl_sig = QLabel()
        self.lbl_sig.setObjectName("lbl_sig")
        self.lbl_sig.setWordWrap(True)
        h.addWidget(self.lbl_sig, 1)
        self.b_sig_signer = QPushButton(_("Signer"))
        self.b_sig_signer.setObjectName("b_sig_signer")
        self.b_sig_signer.clicked.connect(self.signer_prochain)
        h.addWidget(self.b_sig_signer)
        self.b_sig_envoyer = QPushButton(_("Envoyer pour signature..."))
        self.b_sig_envoyer.clicked.connect(self.envoyer_pour_signature)
        h.addWidget(self.b_sig_envoyer)
        b = QPushButton(_("Volet Signatures"))
        b.setObjectName("b_volet_signatures")
        b.clicked.connect(self.volet_signatures)
        h.addWidget(b)
        self.b_sig_fin = QPushButton(_("Terminer"))
        self.b_sig_fin.setProperty("primaire", True)
        self.b_sig_fin.clicked.connect(lambda: self.changer_mode(None))
        h.addWidget(self.b_sig_fin)
        self.bandeau_sig.hide()
        v.addWidget(self.bandeau_sig)

    def _maj_bandeau_sig(self):
        from .dialogues_signature import resume
        mode = getattr(self, "mode", None)
        texte, couleur = resume(self.signatures, self.champs_sig_vides)
        if mode == "signer_num":
            texte = (_("Signature numérique : cliquez dans un champ de signature, ou tracez un rectangle pour signer "
                       "ailleurs.") + ("  " + texte if texte else ""))
            couleur = "#e8f1fb"
        elif mode == "champ_signature":
            texte = _("Champs de signature : tracez un rectangle là où l'autre personne signera ; double-clic sur un "
                      "champ pour le régler (signataire, ordre, verrouillage). {n} champ(s) à signer.",
                      n=len(self.champs_sig_vides))
            couleur = "#e8f1fb"
        if not texte:
            self.bandeau_sig.hide()
            return
        mauvais = couleur == "#fdecea"
        self.ico_sig.setPixmap(icone("erreur" if mauvais else "attention" if couleur == "#fff4e0" else
                                     "valide" if couleur == "#e6f4ea" else "certificat",
                                     "#b00020" if mauvais else "#b26a00" if couleur == "#fff4e0" else
                                     "#2e7d32" if couleur == "#e6f4ea" else "#1462c2").pixmap(20, 20))
        self.bandeau_sig.setStyleSheet(f"QFrame#bandeausig{{background:{couleur};border-bottom:1px solid #d6dde6}}"
                                       "QPushButton{padding:4px 12px}")
        self.lbl_sig.setText(texte)
        self.b_sig_signer.setVisible(bool(self.champs_sig_vides) and mode != "champ_signature")
        self.b_sig_envoyer.setVisible(mode == "champ_signature" and bool(self.champs_sig_vides))
        self.b_sig_fin.setVisible(mode in ("signer_num", "champ_signature"))
        self.bandeau_sig.show()

    # ------------------------------------------------------------ lecture
    def _fichier_temp(self, octets=None):
        fd, p = tempfile.mkstemp(prefix="philpdf-sig-", suffix=".pdf")
        os.close(fd)
        with open(p, "wb") as f:
            f.write(octets if octets is not None else self._octets_pour_signer())
        return p

    def _octets_pour_signer(self):
        if self.est_signe():
            return self._octets()
        from moteur import formulaire as FO
        try:
            FO.normaliser(self.doc)                       # champs comme Acrobat, avant la premiere signature
        except Exception:                                 # noqa: BLE001
            pass
        if self.chiffrement:
            p = tempfile.mktemp(suffix=".pdf")
            self.doc.save(p, garbage=3, deflate=True, **self.chiffrement)
            with open(p, "rb") as f:
                b = f.read()
            os.remove(p)
            return b
        return self.doc.tobytes(garbage=3, deflate=True)

    def widgets_signature(self):
        """[(page, widget)] des champs de signature, dans l'ordre des pages."""
        out = []
        for n, p in enumerate(self.doc):
            for w in p.widgets(types=[SIG]) or []:
                w._page_vivante = p
                out.append((n, w))
        return out

    def xref_champ(self, w):
        """Dictionnaire du champ (le parent quand le widget n'est qu'un « enfant »)."""
        try:
            t = self.doc.xref_get_key(w.xref, "T")
            par = self.doc.xref_get_key(w.xref, "Parent")
            if t[0] == "null" and par[0] == "xref":
                return int(par[1].split()[0])
        except Exception:                                 # noqa: BLE001
            pass
        return w.xref

    def infos_champ_sig(self, w):
        """{signataire, ordre, verrou: (mode, [champs])} d'un champ de signature."""
        fx = self.xref_champ(w)
        signataire = ""
        try:
            tu = self.doc.xref_get_key(fx, "TU")
            if tu[0] == "string":
                signataire = tu[1]
        except Exception:                                 # noqa: BLE001
            pass
        ordre = 0
        try:
            o = self.doc.xref_get_key(fx, "PhilPDF_Ordre")
            ordre = int(float(o[1])) if o[0] in ("int", "float") else 0
        except Exception:                                 # noqa: BLE001
            pass
        verrou = ("aucun", [])
        for x in (fx, w.xref):
            try:
                t, val = self.doc.xref_get_key(x, "Lock")
            except Exception:                             # noqa: BLE001
                continue
            if t == "xref":
                val = self.doc.xref_object(int(val.split()[0]), compressed=True)
            if t in ("dict", "xref") and val:
                m = re.search(r"/Action\s*/(\w+)", val)
                noms = [n.replace("\\(", "(").replace("\\)", ")").replace("\\\\", "\\")
                        for n in re.findall(r"\(((?:[^()\\]|\\.)*)\)", val)]
                act = (m.group(1) if m else "All").lower()
                verrou = ({"all": "tous", "include": "ceux", "exclude": "tous_sauf"}.get(act, "tous"), noms)
                break
        return {"signataire": signataire, "ordre": ordre, "verrou": verrou}

    def verifier_signatures(self):
        """Lit les signatures (validite, signataire), les champs vides, et ce qui est verrouille."""
        self.signatures, vides, self.champs_verrouilles = [], [], set()
        sigs = self.widgets_signature()
        signes = [w for _n, w in sigs if w.is_signed]
        if signes:
            p = self._fichier_temp(self._octets() if self.est_signe() else self.doc.tobytes())
            try:
                from . import identites as ID
                self.signatures = S.verifier(p, ID.approuves_der(self.params), getattr(self, "mdp_pdf", None))
            except Exception as e:                        # noqa: BLE001
                self.signatures = [{"champ": "?", "intacte": False, "erreur": str(e), "nom": "?"}]
            finally:
                os.remove(p)
        tous = [w.field_name for p in self.doc for w in (p.widgets() or []) if w.field_type != SIG]
        for _n, w in sigs:
            if not w.is_signed:
                vides.append(w.field_name)
                continue
            mode, noms = self.infos_champ_sig(w)["verrou"]
            if mode == "tous":
                self.champs_verrouilles.update(tous)
            elif mode == "ceux":
                self.champs_verrouilles.update(noms)
            elif mode == "tous_sauf":
                self.champs_verrouilles.update(n for n in tous if n not in noms)
        if any(s.get("certification") == "rien" for s in self.signatures):
            self.champs_verrouilles.update(tous)
        self.champs_sig_vides = vides
        self._maj_bandeau_sig()

    def volet_signatures(self):
        from .dialogues_signature import DialogueSignatures
        self.verifier_signatures()
        DialogueSignatures(self, self.signatures, self.champs_sig_vides).exec()

    def aller_champ_signature(self, nom):
        for n, w in self.widgets_signature():
            if w.field_name == nom:
                self.aller_a(n)
                return True
        return False

    # ------------------------------------------------------------ signer
    def signer_prochain(self):
        """Bouton « Signer » : le premier champ vide (dans l'ordre prevu), sinon le mode signature."""
        vides = [(n, w) for n, w in self.widgets_signature() if not w.is_signed]
        if not vides:
            self.changer_mode("signer_num")
            return
        vides.sort(key=lambda x: (self.infos_champ_sig(x[1])["ordre"] or 99, x[0], x[1].rect.y0))
        n, w = vides[0]
        self.aller_a(n)
        self.signer_numerique(w.field_name, n, fitz.Rect(w.rect))

    def clic_champ_signature(self, n, w):
        if w.is_signed:
            self.volet_signatures()
        else:
            self.signer_numerique(w.field_name, n, fitz.Rect(w.rect))

    def signer_numerique(self, champ=None, page=0, rect=None):
        from .dialogues_signature import DialogueSigner, message_erreur
        infos = []
        if champ:
            w = next((w for _n, w in self.widgets_signature() if w.field_name == champ), None)
            if w is not None:
                i = self.infos_champ_sig(w)
                if i["signataire"]:
                    infos.append(_("Champ prévu pour : {x}", x=i["signataire"]))
                avant = [(x.field_name, self.infos_champ_sig(x)) for _n, x in self.widgets_signature()
                         if not x.is_signed and x.field_name != champ]
                manquants = [nm for nm, ii in avant if i["ordre"] and ii["ordre"] and ii["ordre"] < i["ordre"]]
                if manquants:
                    infos.append(_("Attention : prévu après « {x} », qui n'est pas encore signé.", x=", ".join(manquants)))
                mode, noms = i["verrou"]
                if mode == "tous":
                    infos.append(_("A la signature, tous les champs du formulaire seront verrouillés."))
                elif mode == "ceux" and noms:
                    infos.append(_("A la signature, ces champs seront verrouillés : {x}", x=", ".join(noms)))
                elif mode == "tous_sauf":
                    infos.append(_("A la signature, tous les champs seront verrouillés sauf : {x}", x=", ".join(noms) or "-"))
        d = DialogueSigner(self, champ, rect, page, infos, premiere=not self.signatures)
        if d.exec() != QDialog.Accepted or not d.resultat:
            return False
        r = d.resultat
        dest, _x = QFileDialog.getSaveFileName(self, _("Enregistrer le document signé"), self.chemin or self.nom,
                                               _("Documents PDF (*.pdf)"))
        if not dest:
            return False
        if not dest.lower().endswith(".pdf"):
            dest += ".pdf"
        src = self._fichier_temp()
        app_pdf = None
        try:
            if rect is not None:
                app_pdf = S.apparence_pdf(rect.width, rect.height, "" if r["genre"] == "texte" else r["nom"], r["png"],
                                          r["lignes"])
            from .journal import ecrire as log
            res = en_fond(self, _("Signature en cours..."), lambda: S.signer(
                src, dest, r["pfx"], r["mdp"], champ=champ, page=page, rect=(tuple(rect) if rect is not None else None),
                apparence=app_pdf, raison=r["motif"], lieu=r["lieu"], certifier=r["certifier"],
                horodatage=r["horodatage"], mot_de_passe_pdf=getattr(self, "mdp_pdf", None), signataire=r.get("signataire"),
                journal=lambda t: log("signature", t)))
        except Exception as e:                            # noqa: BLE001
            QMessageBox.warning(self, _("Signature numérique"), _("Signature impossible : {e}", e=message_erreur(e)))
            return False
        finally:
            for p in (src, app_pdf):
                if p and os.path.exists(p):
                    os.remove(p)
        self.recharger_signe(dest)
        msg = _("Signé ({nom}) et enregistré : {f}", nom=r["nom"], f=os.path.basename(dest))
        if r["horodatage"] and not res.get("horodatage"):
            msg += "  " + _("(sans horodatage : pas de réponse du serveur)")
        self.message(msg)
        fen = self.window()
        if getattr(self, "distant", None) and hasattr(fen, "_renvoyer") and os.path.abspath(dest) == os.path.abspath(self.chemin):
            fen._renvoyer(self)
        if hasattr(fen, "params"):
            fen.params.ajouter_recent(dest)
        return True

    def recharger_signe(self, chemin):
        """Apres la signature : le document est celui du fichier signe ; l'historique repart de zero."""
        with open(chemin, "rb") as f:
            octets = f.read()
        self.travail = None
        self.doc = self._ouvrir_travail(octets)
        self.chemin, self.nom = chemin, os.path.basename(chemin)
        self.modifie = False
        self.chiffrement, self.chiffrement_change = None, False
        self.poids_initial = len(octets)
        self.annulations.clear()
        self.retablissements.clear()
        self.maj_historique()
        self.construire_pages()
        self.verifier_signatures()
        self.titre_change.emit()

    # ------------------------------------------------------------ champs de signature pour d'autres
    def _noms_champs(self):
        return [w.field_name for p in self.doc for w in (p.widgets() or []) if w.field_type != SIG]

    def ajouter_champ_signature(self, n, r):
        from .dialogues_signature import DialogueChampSignature
        if r.width < 30 or r.height < 12:
            r = fitz.Rect(r.x0, r.y0, r.x0 + max(r.width, 150), r.y0 + max(r.height, 40))
        pris = {w.field_name for p in self.doc for w in (p.widgets() or [])}
        i = 1
        while f"Signature{i}" in pris:
            i += 1
        d = DialogueChampSignature(self, f"Signature{i}", self._noms_champs(), ordre=0)
        if d.exec() != QDialog.Accepted:
            return
        v = d.valeurs()
        if not v["nom"] or v["nom"] in pris:
            QMessageBox.warning(self, _("Champ de signature"), _("Un champ porte déjà ce nom.") if v["nom"] else _("Indiquez un nom."))
            return
        self.memoriser(_("Ajout du champ de signature « {nom} »", nom=v["nom"]))
        w = fitz.Widget()
        w.field_type = SIG
        w.field_name = v["nom"]
        w.rect = fitz.Rect(r)
        if v["signataire"]:
            w.field_label = v["signataire"]
        self.doc[n].add_widget(w)
        if not self.est_signe():
            from moteur import formulaire as FO
            FO.normaliser(self.doc)
        w = next(x for x in self.doc[n].widgets(types=[SIG]) if x.field_name == v["nom"])
        self._ecrire_infos_champ_sig(w, v)
        self.apres_modif([_("Champ de signature « {nom} » ajouté.", nom=v["nom"])])
        self.verifier_signatures()

    def regler_champ_signature(self, n, w):
        from .dialogues_signature import DialogueChampSignature
        if w.is_signed:
            self.volet_signatures()
            return
        i = self.infos_champ_sig(w)
        d = DialogueChampSignature(self, w.field_name, self._noms_champs(), i["signataire"], i["ordre"], i["verrou"])
        if d.exec() != QDialog.Accepted:
            return
        v = d.valeurs()
        self.memoriser(_("Réglage du champ de signature « {nom} »", nom=w.field_name))
        w = self._widget((n, w.xref))
        if v["nom"] and v["nom"] != w.field_name:
            w.field_name = v["nom"]
        w.field_label = v["signataire"] or None
        w.update()
        w = self._widget((n, w.xref))
        self._ecrire_infos_champ_sig(w, v)
        self.apres_modif([_("Champ de signature réglé.")])
        self.verifier_signatures()

    def _ecrire_infos_champ_sig(self, w, v):
        fx = self.xref_champ(w)
        self.doc.xref_set_key(fx, "TU", _chaine_pdf(v["signataire"]) if v["signataire"] else "null")
        self.doc.xref_set_key(fx, "PhilPDF_Ordre", str(int(v["ordre"])) if v["ordre"] else "null")
        if w.xref != fx:
            self.doc.xref_set_key(w.xref, "Lock", "null")
        mode, noms = v["verrou"]
        if mode == "aucun" or (mode in ("ceux", "tous_sauf") and not noms):
            self.doc.xref_set_key(fx, "Lock", "null")
        else:
            act = {"tous": "All", "ceux": "Include", "tous_sauf": "Exclude"}[mode]
            champs = "" if mode == "tous" else "/Fields[" + "".join(_chaine_pdf(x) for x in noms) + "]"
            self.doc.xref_set_key(fx, "Lock", f"<</Type/SigFieldLock/Action/{act}{champs}>>")

    def envoyer_pour_signature(self):
        """Enregistre le document, ouvre la messagerie avec un message pret, et montre le fichier a joindre."""
        fen = self.window()
        if (self.modifie or not self.chemin) and hasattr(fen, "enregistrer"):
            if not fen.enregistrer(self):
                return
        vides = [(self.infos_champ_sig(w), w.field_name) for _n, w in self.widgets_signature() if not w.is_signed]
        vides.sort(key=lambda x: x[0]["ordre"] or 99)
        lignes = [f"- {nom}" + (f" ({i['signataire']})" if i["signataire"] else "") for i, nom in vides]
        corps = _("Bonjour,\n\nVous trouverez ci-joint le document « {doc} » à signer.\n\nChamp(s) de signature :\n{champs}\n\n"
                  "Dans Acrobat ou Acrobat Reader : cliquez sur le champ de signature, choisissez votre identité "
                  "numérique, puis enregistrez et renvoyez-moi le fichier.\n\nMerci,\n{auteur}",
                  doc=self.nom, champs="\n".join(lignes), auteur=self.params.get("auteur", ""))
        from . import agenda
        agenda.ouvrir(agenda.lien_message(self.params.get("messagerie") or "gmail",
                                          _("Document à signer : {doc}", doc=self.nom), corps))
        try:
            from .fenetre import montrer_dans_explorateur
            montrer_dans_explorateur(self.chemin)
        except Exception:                                 # noqa: BLE001
            pass
        QMessageBox.information(self, _("Envoyer pour signature"),
                                _("Le message est prêt dans votre messagerie. Joignez-y le fichier, montré dans "
                                  "l'explorateur :\n{f}", f=self.chemin))

    def champ_verrouille(self, w):
        return w.field_name in getattr(self, "champs_verrouilles", set())
