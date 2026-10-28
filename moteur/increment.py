"""Enregistrer un PDF signe « en ajout » (mise a jour incrementale), comme Acrobat, sans jamais casser une signature.

On travaille en memoire comme pour tout document ; a l'enregistrement, on compare objet par objet le document modifie
au fichier signe d'origine, et seuls les objets changes ou nouveaux sont ajoutes a la fin du fichier, en une seule
mise a jour. (Enregistrer plusieurs fois en ajout le meme document ouvert par MuPDF corrompt le fichier : la deuxieme
mise a jour s'ecrit par-dessus la premiere. On rouvre donc toujours le fichier d'origine pour l'ajout.)
"""
import os
import tempfile

import pymupdf as fitz


def _brut(doc, x):
    try:
        return doc.xref_stream_raw(x) if doc.xref_is_stream(x) else None
    except Exception:                                     # noqa: BLE001
        return None


def ajout(origine, doc, mot_de_passe=None):
    """Octets du fichier `origine` (signe) suivis d'une mise a jour avec ce qui differe dans `doc` (document PyMuPDF
    ouvert depuis ces memes octets puis modifie). Renvoie `origine` tel quel s'il n'y a rien de change."""
    fd, f = tempfile.mkstemp(prefix="philpdf-ajout-", suffix=".pdf")
    os.close(fd)
    with open(f, "wb") as h:
        h.write(origine)
    base = fitz.open(f)
    try:
        if base.needs_pass:
            base.authenticate(mot_de_passe or "")
        if doc.needs_pass:
            doc.authenticate(mot_de_passe or "")
        n_base, n_doc = base.xref_length(), doc.xref_length()
        while base.xref_length() < n_doc:
            base.get_new_xref()
        change = 0
        for x in range(1, n_doc):
            try:
                nouveau = doc.xref_object(x, compressed=True)
            except Exception:                             # noqa: BLE001
                continue
            ancien = None
            if x < n_base:
                try:
                    ancien = base.xref_object(x, compressed=True)
                except Exception:                         # noqa: BLE001
                    ancien = None
            sn, sa = _brut(doc, x), (_brut(base, x) if x < n_base else None)
            if nouveau == ancien and sn == sa:
                continue
            if nouveau in ("null", "") and ancien in (None, "null", ""):
                continue
            base.update_object(x, nouveau)
            if sn is not None:
                base.update_stream(x, sn, compress=False)
                # le flux brut est deja filtre (meme /Filter qu'a l'origine) : on remet le dictionnaire tel quel
                base.update_object(x, nouveau)
            change += 1
        if not change:
            return origine
        base.save(f, incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
        base.close()
        with open(f, "rb") as h:
            return h.read()
    finally:
        try:
            base.close()
        except Exception:                                 # noqa: BLE001
            pass
        try:
            os.remove(f)
        except OSError:
            pass
