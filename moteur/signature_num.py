"""Signature numerique PAdES (reconnue par Acrobat), avec pyHanko.

- Identites : un fichier .pfx (PKCS#12) = certificat + clef privee, protege par un mot de passe. On peut importer celui
  exporte d'Acrobat, ou en creer un (certificat autosigne, comme les « ID numeriques » d'Acrobat).
- Signer : dans un champ de signature existant ou dans un rectangle trace ; apparence fournie en PDF d'une page
  (dessinee par PhilPDF) ; certification au choix (ce qui reste permis apres) ; horodatage si Internet.
- Champs de signature pour d'autres personnes, avec verrouillage de champs a la signature (FieldMDP).
- Verifier : integrite, signataire, date, certificat approuve ou non, modifications faites apres.

Toujours en ajout incremental : une signature ne casse jamais les precedentes.
"""
import datetime as _dt
import io
import os
import tempfile

from asn1crypto import x509 as _ax509
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID, ObjectIdentifier

# Serveurs d'horodatage gratuits (RFC 3161), essayes dans l'ordre
HORODATEURS = ["http://timestamp.digicert.com", "http://timestamp.sectigo.com", "https://freetsa.org/tsr"]

# Ce qui reste permis apres une signature de certification
CERTIFIER = {"rien": 1, "formulaires": 2, "annotations": 3}
# Verrouillage de champs quand un champ de signature est signe
VERROU = ("aucun", "tous", "tous_sauf", "ceux")

_EKU_ADOBE = ObjectIdentifier("1.2.840.113583.1.1.5")      # « Authentic Documents » d'Adobe


import logging as _logging
for _n in ("pyhanko", "pyhanko_certvalidator", "pyhanko.sign.validation"):
    _logging.getLogger(_n).setLevel(_logging.CRITICAL)


class ErreurSignature(Exception):
    pass


# ------------------------------------------------------------------ identites
def creer_identite(nom, mot_de_passe, organisation="", service="", email="", pays="FR", annees=5):
    """Certificat autosigne RSA 2048 / SHA-256, comme un ID numerique d'Acrobat. Renvoie les octets du .pfx."""
    if not nom.strip():
        raise ErreurSignature("nom vide")
    clef = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    attrs = [x509.NameAttribute(NameOID.COMMON_NAME, nom.strip())]
    if organisation.strip():
        attrs.append(x509.NameAttribute(NameOID.ORGANIZATION_NAME, organisation.strip()))
    if service.strip():
        attrs.append(x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, service.strip()))
    if email.strip():
        attrs.append(x509.NameAttribute(NameOID.EMAIL_ADDRESS, email.strip()))
    if pays and len(pays.strip()) == 2:
        attrs.append(x509.NameAttribute(NameOID.COUNTRY_NAME, pays.strip().upper()))
    sujet = x509.Name(attrs)
    maintenant = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(minutes=5)
    b = (x509.CertificateBuilder().subject_name(sujet).issuer_name(sujet).public_key(clef.public_key())
         .serial_number(x509.random_serial_number()).not_valid_before(maintenant)
         .not_valid_after(maintenant + _dt.timedelta(days=365 * annees + annees // 4))
         .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
         .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=True, key_encipherment=False,
                                      data_encipherment=True, key_agreement=False, key_cert_sign=False,
                                      crl_sign=False, encipher_only=False, decipher_only=False), critical=False)
         .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.EMAIL_PROTECTION, _EKU_ADOBE]), critical=False)
         .add_extension(x509.SubjectKeyIdentifier.from_public_key(clef.public_key()), critical=False))
    if email.strip():
        b = b.add_extension(x509.SubjectAlternativeName([x509.RFC822Name(email.strip())]), critical=False)
    cert = b.sign(clef, hashes.SHA256())
    return pkcs12.serialize_key_and_certificates(nom.strip().encode("utf-8"), clef, cert, None,
                                                 _chiffrement(mot_de_passe))


def _chiffrement(mot_de_passe):
    if not mot_de_passe:
        raise ErreurSignature("mot de passe vide")
    # AES-256 + PBKDF2 : lisible par Acrobat recent et Windows 10/11
    return (serialization.PrivateFormat.PKCS12.encryption_builder().kdf_rounds(100000)
            .key_cert_algorithm(pkcs12.PBES.PBESv2SHA256AndAES256CBC).hmac_hash(hashes.SHA256())
            .build(mot_de_passe.encode("utf-8")))


def ouvrir_pfx(octets, mot_de_passe):
    """(clef, certificat, autres certificats) ; ErreurSignature si mot de passe faux ou fichier illisible."""
    try:
        clef, cert, autres = pkcs12.load_key_and_certificates(octets, (mot_de_passe or "").encode("utf-8"))
    except ValueError as e:
        raise ErreurSignature("mot_de_passe") from e
    if clef is None or cert is None:
        raise ErreurSignature("pas_de_clef")
    return clef, cert, autres or []


def _nom(n, oid):
    v = n.get_attributes_for_oid(oid)
    return v[0].value if v else ""


def infos_certificat(cert):
    """Ce qu'on montre a l'utilisateur."""
    s, e = cert.subject, cert.issuer
    try:
        debut, fin = cert.not_valid_before_utc, cert.not_valid_after_utc
    except AttributeError:                                   # cryptography ancienne
        debut, fin = cert.not_valid_before.replace(tzinfo=_dt.timezone.utc), cert.not_valid_after.replace(tzinfo=_dt.timezone.utc)
    return {"nom": _nom(s, NameOID.COMMON_NAME), "organisation": _nom(s, NameOID.ORGANIZATION_NAME),
            "service": _nom(s, NameOID.ORGANIZATIONAL_UNIT_NAME), "email": _nom(s, NameOID.EMAIL_ADDRESS),
            "emetteur": _nom(e, NameOID.COMMON_NAME) or _nom(e, NameOID.ORGANIZATION_NAME),
            "autosigne": s == e, "debut": debut, "fin": fin,
            "expire": fin < _dt.datetime.now(_dt.timezone.utc),
            "empreinte": cert.fingerprint(hashes.SHA256()).hex().upper()}


def _infos_asn1(c):
    """Comme infos_certificat, depuis un certificat asn1crypto (accepte aussi les numeros de serie negatifs que
    produit Acrobat, refuses par les versions recentes de cryptography)."""
    import hashlib
    s, e = c.subject.native, c.issuer.native
    return {"nom": s.get("common_name", ""), "organisation": s.get("organization_name", ""),
            "email": s.get("email_address", ""), "emetteur": e.get("common_name", "") or e.get("organization_name", ""),
            "autosigne": c.subject == c.issuer, "empreinte": hashlib.sha256(c.dump()).hexdigest().upper(),
            "fin": c["tbs_certificate"]["validity"]["not_after"].native}


def infos_pfx(octets, mot_de_passe):
    return infos_certificat(ouvrir_pfx(octets, mot_de_passe)[1])


def exporter_cer(octets, mot_de_passe):
    """Certificat seul (.cer, sans la clef) a donner a vos correspondants pour qu'ils l'approuvent dans Acrobat."""
    return ouvrir_pfx(octets, mot_de_passe)[1].public_bytes(serialization.Encoding.DER)


def changer_mot_de_passe(octets, ancien, nouveau):
    clef, cert, autres = ouvrir_pfx(octets, ancien)
    nom = _nom(cert.subject, NameOID.COMMON_NAME).encode("utf-8") or None
    return pkcs12.serialize_key_and_certificates(nom, clef, cert, autres or None, _chiffrement(nouveau))


def lire_cer(octets):
    """Certificat .cer / .crt / .pem (DER ou PEM)."""
    try:
        return x509.load_der_x509_certificate(octets)
    except ValueError:
        return x509.load_pem_x509_certificate(octets)


# ------------------------------------------------------------------ apparence
def lignes_apparence(nom, quand=None, motif="", lieu="", date=True, libelles=None):
    """Texte de droite, comme Acrobat : « Signature numérique de / Nom / Date : 2026.10.27 / 23:39:47 +01'00' ».
    libelles : textes dans la langue de l'interface {entete, date, motif, lieu}."""
    lb = dict({"entete": "Signature numérique de", "date": "Date : {x}", "motif": "Motif : {x}", "lieu": "Lieu : {x}"},
              **(libelles or {}))
    l = [lb["entete"], nom]
    if date:
        d = date_affichee(quand)
        jour, _e, heure = d.partition(" ")
        l += [lb["date"].replace("{x}", jour), heure]
    if motif:
        l.append(lb["motif"].replace("{x}", motif))
    if lieu:
        l.append(lb["lieu"].replace("{x}", lieu))
    return l


def apparence_pdf(largeur, hauteur, nom, image_png=None, lignes=(), gauche_seule=False):
    """Apparence facon Acrobat : a gauche la signature manuscrite (ou le nom en grand sur deux lignes), a droite les
    lignes de texte. Sans lignes : tout le cadre pour la gauche. Renvoie le chemin d'un PDF d'une page (temporaire)."""
    import pymupdf as fitz
    doc = fitz.open()
    page = doc.new_page(width=largeur, height=hauteur)
    if lignes and not gauche_seule:
        coupe = largeur * (0.46 if image_png else 0.42)
        gauche, droite = fitz.Rect(0, 0, coupe, hauteur), fitz.Rect(coupe + 2, 0, largeur, hauteur)
    else:
        gauche, droite = fitz.Rect(0, 0, largeur, hauteur), None
    if image_png:
        page.insert_image(gauche + (1, 1, -1, -1), stream=image_png, keep_proportion=True)
    elif nom:
        mots = nom.split()
        texte = (mots[0] + "\n" + " ".join(mots[1:])) if len(mots) > 1 else nom
        _ajuste(page, gauche + (1, 0, -1, 0), texte, plafond=hauteur * 0.42, centre_v=True)
    if droite is not None:
        _ajuste(page, droite, "\n".join(lignes), plafond=min(11.0, hauteur / max(len(lignes), 1) * 0.86), centre_v=True)
    f = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    f.close()
    doc.save(f.name)
    doc.close()
    return f.name


def _ajuste(page, r, texte, plafond=12.0, centre_v=False):
    """Texte le plus grand possible (plafonne) qui tient dans r, en Helvetica (accents compris), centre en hauteur."""
    import pymupdf as fitz
    taille = plafond
    n = texte.count("\n") + 1
    while taille > 2.5:
        largeur_max = max(fitz.get_text_length(l, "helv", taille) for l in texte.split("\n"))
        if largeur_max <= r.width and n * taille * 1.18 <= r.height:
            break
        taille -= 0.25
    h = n * taille * 1.18
    y0 = r.y0 + max(0.0, (r.height - h) / 2) if centre_v else r.y0
    for i, l in enumerate(texte.split("\n")):
        page.insert_text((r.x0, y0 + taille * (i + 0.92) * 1.18 - taille * 0.18), l, fontsize=taille,
                         fontname="helv", color=(0, 0, 0))


def date_affichee(quand=None):
    """Comme Acrobat : 2026.10.27 23:45:12 +01'00'."""
    d = (quand or _dt.datetime.now().astimezone())
    z = d.strftime("%z") or "+0000"
    return d.strftime("%Y.%m.%d %H:%M:%S ") + f"{z[:3]}'{z[3:]}'"


# ------------------------------------------------------------------ signer
def _signataire(pfx, mot_de_passe):
    from pyhanko.sign import signers
    ouvrir_pfx(pfx, mot_de_passe)                         # message clair si le mot de passe est faux
    s = signers.SimpleSigner.load_pkcs12_data(pfx, other_certs=[], passphrase=(mot_de_passe or "").encode("utf-8"))
    if s is None:
        raise ErreurSignature("mot_de_passe")
    return s


def _horodateur(journal=None):
    """Premier serveur d'horodatage qui repond (sinon None : signature sans horodatage)."""
    from pyhanko.sign import timestamps
    import urllib.request
    for url in HORODATEURS:
        try:
            urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=5)
        except Exception as e:                            # noqa: BLE001
            code = getattr(e, "code", None)
            if code is None:                              # aucune reponse : serveur ou Internet absent
                if journal:
                    journal(f"horodatage : {url} ne repond pas ({e})")
                continue
        return timestamps.HTTPTimeStamper(url, timeout=15), url
    return None, None


def signer(source, destination, pfx, mot_de_passe, champ=None, page=0, rect=None, apparence=None,
           raison="", lieu="", contact="", certifier=None, horodatage=True, mot_de_passe_pdf=None,
           verrou=None, journal=None):
    """Signe `source` vers `destination` (ajout incremental).

    champ : nom d'un champ de signature vide existant, ou d'un nouveau champ a creer dans `rect` (page `page`).
    rect  : (x0, y0, x1, y1) en points, origine en HAUT a gauche (comme PyMuPDF) ; None = signature invisible.
    apparence : chemin d'un PDF d'une page (voir apparence_pdf) ; None = cadre Acrobat par defaut de pyHanko.
    certifier : None, « rien », « formulaires » ou « annotations ».
    verrou : pour un nouveau champ, (mode, [champs]) avec mode dans VERROU.
    Renvoie {"horodatage": url ou None, "champ": nom}.
    """
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.sign import signers, fields
    from pyhanko.stamp import StaticStampStyle
    from pyhanko.sign.fields import MDPPerm
    from pyhanko.sign.signers.pdf_byterange import BuildProps
    s = _signataire(pfx, mot_de_passe)
    tsa, url = (None, None)
    if horodatage:
        tsa, url = _horodateur(journal)
    with open(source, "rb") as f:
        donnees = f.read()
    w = IncrementalPdfFileWriter(io.BytesIO(donnees), strict=False)
    if w.prev.encrypted:
        if not mot_de_passe_pdf:
            raise ErreurSignature("pdf_protege")
        w.encrypt(mot_de_passe_pdf)
    existants = {n for n, _v, _r in fields.enumerate_sig_fields(w.prev)}
    vides = {n for n, v, _r in fields.enumerate_sig_fields(w.prev, filled_status=False)}
    nouveau = None
    if not champ:
        i = 1
        while f"Signature{i}" in existants:
            i += 1
        champ = f"Signature{i}"
    if champ in existants and champ not in vides:
        raise ErreurSignature("deja_signe")
    if champ not in existants:
        box = _boite_pdf(donnees, page, rect, mot_de_passe_pdf) if rect else None
        nouveau = fields.SigFieldSpec(champ, on_page=page, box=box, **_spec_verrou(verrou))
    meta = signers.PdfSignatureMetadata(
        field_name=champ, reason=raison or None, location=lieu or None, contact_info=contact or None,
        md_algorithm="sha256", subfilter=fields.SigSeedSubFilter.PADES, certify=bool(certifier),
        docmdp_permissions=MDPPerm(CERTIFIER.get(certifier or "formulaires", 2)),
        app_build_props=BuildProps(name="PhilPDF", revision=_version()))
    style = StaticStampStyle.from_pdf_file(apparence, border_width=0) if apparence else None
    ps = signers.PdfSigner(meta, s, timestamper=tsa, stamp_style=style, new_field_spec=nouveau)
    sortie = io.BytesIO()
    try:
        ps.sign_pdf(w, output=sortie)
    except Exception as e:                                # noqa: BLE001
        if tsa is not None:                               # horodateur en panne au dernier moment : sans
            if journal:
                journal(f"horodatage refuse ({e}) : signature sans horodatage")
            w = IncrementalPdfFileWriter(io.BytesIO(donnees), strict=False)
            if w.prev.encrypted:
                w.encrypt(mot_de_passe_pdf)
            ps = signers.PdfSigner(meta, s, timestamper=None, stamp_style=style, new_field_spec=nouveau)
            sortie = io.BytesIO()
            ps.sign_pdf(w, output=sortie)
            url = None
        else:
            raise
    _ecrire(destination, sortie.getvalue())
    if journal:
        journal(f"signe : champ {champ}, horodatage {url or 'aucun'}, certification {certifier or 'non'}")
    return {"horodatage": url, "champ": champ}


def _version():
    try:
        from app.config import VERSION
        return VERSION
    except Exception:                                     # noqa: BLE001
        return None


def _ecrire(chemin, octets):
    tmp = chemin + ".philpdf-tmp"
    with open(tmp, "wb") as f:
        f.write(octets)
    os.replace(tmp, chemin)


def _boite_pdf(donnees, page, rect, mot_de_passe_pdf=None):
    """Rectangle PyMuPDF (origine en haut a gauche, page tournee comprise) -> boite PDF (x0, y0, x1, y1)."""
    import pymupdf as fitz
    d = fitz.open(stream=donnees, filetype="pdf")
    if d.needs_pass:
        d.authenticate(mot_de_passe_pdf or "")
    r = fitz.Rect(rect) * ~d[page].transformation_matrix
    d.close()
    r.normalize()
    return (round(r.x0, 2), round(r.y0, 2), round(r.x1, 2), round(r.y1, 2))


def _spec_verrou(verrou):
    from pyhanko.sign import fields
    if not verrou or verrou[0] in (None, "aucun"):
        return {}
    mode, noms = verrou[0], list(verrou[1] or [])
    action = {"tous": fields.FieldMDPAction.ALL, "tous_sauf": fields.FieldMDPAction.EXCLUDE,
              "ceux": fields.FieldMDPAction.INCLUDE}[mode]
    if action != fields.FieldMDPAction.ALL and not noms:
        return {}
    return {"field_mdp_spec": fields.FieldMDPSpec(action, None if action == fields.FieldMDPAction.ALL else noms)}


def poser_champ(source, destination, nom, page, rect, verrou=None, mot_de_passe_pdf=None):
    """Champ de signature vide pour quelqu'un d'autre (signable dans Acrobat ou PhilPDF), avec verrou au choix."""
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.sign import fields
    with open(source, "rb") as f:
        donnees = f.read()
    w = IncrementalPdfFileWriter(io.BytesIO(donnees), strict=False)
    if w.prev.encrypted:
        if not mot_de_passe_pdf:
            raise ErreurSignature("pdf_protege")
        w.encrypt(mot_de_passe_pdf)
    if nom in {n for n, _v, _r in fields.enumerate_sig_fields(w.prev)}:
        raise ErreurSignature("nom_pris")
    fields.append_signature_field(w, fields.SigFieldSpec(nom, on_page=page, box=_boite_pdf(donnees, page, rect, mot_de_passe_pdf),
                                                         **_spec_verrou(verrou)))
    sortie = io.BytesIO()
    w.write(sortie)
    _ecrire(destination, sortie.getvalue())


# ------------------------------------------------------------------ verifier
def _contexte(approuves):
    from pyhanko_certvalidator import ValidationContext
    racines = []
    for c in approuves or []:
        try:
            der = c if isinstance(c, bytes) else c.public_bytes(serialization.Encoding.DER)
            racines.append(_ax509.Certificate.load(der))
        except Exception:                                 # noqa: BLE001
            pass
    return ValidationContext(trust_roots=racines, allow_fetching=False, revocation_mode="soft-fail")


def _politique():
    """Regles d'Acrobat pour juger les modifications apres une signature (celles de pyHanko), sans la tolerance
    des apparences reecrites « sur place » : PhilPDF et Acrobat ecrivent toujours une nouvelle apparence, et cette
    tolerance faisait compter a tort un champ verrouille comme modifie."""
    from pyhanko.sign.diff_analysis import policies as P
    from pyhanko.sign.diff_analysis.rules import form_field_rules as R
    from pyhanko.sign.diff_analysis.form_rules_api import FormUpdatingRule
    from pyhanko.sign.diff_analysis.rules.file_structure_rules import (CatalogModificationRule, ObjectStreamRule,
                                                                       XrefStreamRule)
    from pyhanko.sign.diff_analysis.rules.metadata_rules import DocInfoRule, MetadataUpdateRule
    from pyhanko.sign.diff_analysis import ModificationLevel as M
    try:
        return P.StandardDiffPolicy(
            global_rules=[CatalogModificationRule(), DocInfoRule().as_qualified(M.LTA_UPDATES),
                          XrefStreamRule().as_qualified(M.LTA_UPDATES), ObjectStreamRule().as_qualified(M.LTA_UPDATES),
                          R.DSSCompareRule().as_qualified(M.LTA_UPDATES), MetadataUpdateRule().as_qualified(M.LTA_UPDATES)],
            form_rule=FormUpdatingRule(field_rules=[
                R.SigFieldCreationRule(),
                R.SigFieldModificationRule(allow_in_place_appearance_stream_changes=False),
                R.GenericFieldModificationRule(allow_in_place_appearance_stream_changes=False)]))
    except Exception:                                     # noqa: BLE001 (autre version de pyHanko)
        return P.DEFAULT_DIFF_POLICY


def verifier(chemin, approuves=(), mot_de_passe_pdf=None):
    """Liste des signatures du fichier, dans l'ordre :
    {champ, nom, intacte, approuve, date, horodatee, certification, modifs (« aucune », « formulaires »,
     « annotations », « autres »), couvre_tout, raison, lieu, empreinte, emetteur, autosigne, page, rect}"""
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.validation import validate_pdf_signature
    with open(chemin, "rb") as f:
        r = PdfFileReader(io.BytesIO(f.read()), strict=False)
    if r.encrypted:
        if not mot_de_passe_pdf:
            raise ErreurSignature("pdf_protege")
        r.decrypt(mot_de_passe_pdf)
    res = []
    for sig in r.embedded_signatures:
        d = {"champ": sig.field_name, "raison": "", "lieu": "", "intacte": False, "approuve": False,
             "date": None, "horodatee": False, "certification": None, "modifs": "autres", "couvre_tout": False,
             "nom": "", "emetteur": "", "autosigne": False, "empreinte": "", "erreur": "", "der": None}
        try:
            so = sig.sig_object
            d["raison"] = str(so.get("/Reason", "") or "")
            d["lieu"] = str(so.get("/Location", "") or "")
            st = validate_pdf_signature(sig, _contexte(approuves), diff_policy=_politique())
            d["intacte"] = bool(st.intact and st.valid)
            d["approuve"] = bool(st.trusted)
            d["date"] = st.timestamp_validity.timestamp if st.timestamp_validity else st.signer_reported_dt
            d["horodatee"] = st.timestamp_validity is not None
            mod = getattr(st, "modification_level", None)
            nommod = getattr(mod, "name", "OTHER")
            d["modifs"] = {"NONE": "aucune", "LTA_UPDATES": "aucune", "FORM_FILLING": "formulaires",
                           "ANNOTATIONS": "annotations"}.get(nommod, "autres")
            dr = getattr(st, "diff_result", None)
            if dr is not None and not hasattr(dr, "modification_level"):
                d["detail_modifs"] = str(dr)[:500]
            cov = getattr(st, "coverage", None)
            d["couvre_tout"] = getattr(cov, "name", "") == "ENTIRE_FILE"
            if sig.docmdp_level is not None:
                d["certification"] = {1: "rien", 2: "formulaires", 3: "annotations"}.get(int(sig.docmdp_level.value))
            d["der"] = sig.signer_cert.dump()
            d.update(_infos_asn1(sig.signer_cert))
        except Exception as e:                            # noqa: BLE001
            d["erreur"] = str(e)
        res.append(d)
    return res


def champs_signature(chemin, mot_de_passe_pdf=None):
    """[(nom, signe ?)] dans l'ordre du document."""
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign import fields
    with open(chemin, "rb") as f:
        r = PdfFileReader(io.BytesIO(f.read()), strict=False)
    if r.encrypted and mot_de_passe_pdf:
        r.decrypt(mot_de_passe_pdf)
    return [(n, v is not None) for n, v, _r in fields.enumerate_sig_fields(r)]


def a_des_signatures(doc):
    """Le document PyMuPDF ouvert contient-il des signatures (alors : enregistrer en ajout seulement) ?"""
    try:
        for p in doc:
            for w in p.widgets() or []:
                if w.field_type == 7 and w.is_signed:      # PDF_WIDGET_TYPE_SIGNATURE
                    return True
    except Exception:                                     # noqa: BLE001
        pass
    try:
        return bool(doc.get_sigflags() > 0 and any(
            w.field_type == 7 and w.is_signed for p in doc for w in (p.widgets() or [])))
    except Exception:                                     # noqa: BLE001
        return False
