"""Envoyer le document par e-mail.

Trois facons, au choix (memorise) :
- votre logiciel de messagerie (Outlook, Thunderbird...) : nouveau message ouvert avec le PDF deja joint (MAPI,
  sinon Outlook directement) ; vous relisez et cliquez « Envoyer » ;
- un compte d'envoi regle dans PhilPDF (Orange, Gmail, Free, SFR...) : PhilPDF envoie lui-meme, apres votre clic,
  et le message part de votre adresse ; le mot de passe reste dans le coffre de Windows (et suit vos postes,
  chiffre, comme les autres comptes) ;
- la messagerie web (Gmail, Outlook.com) : le message s'ouvre pre-rempli dans le navigateur et le dossier du PDF
  s'ouvre a cote, le fichier selectionne : il reste a le glisser dans le message (le web ne permet pas de joindre
  un fichier tout seul).
Le fichier joint peut etre tel quel, allege pour l'envoi, fige (formulaires et commentaires non modifiables) ou
protege par un mot de passe.
"""
import os
import re
import subprocess
import sys
import tempfile
import threading
import uuid

from .langue import _
from . import coffre

FOURNISSEURS = [  # cle, nom, serveur, port, securite, aide
    ("orange", "Orange / Wanadoo", "smtp.orange.fr", 465, "ssl", _("Votre mot de passe Orange habituel.")),
    ("gmail", "Gmail", "smtp.gmail.com", 465, "ssl",
     _("Gmail demande un « mot de passe d'application » (Compte Google › Sécurité › Validation en deux étapes › "
       "Mots de passe des applications), pas votre mot de passe habituel.")),
    ("free", "Free", "smtp.free.fr", 465, "ssl", _("Votre mot de passe Free.")),
    ("sfr", "SFR", "smtp.sfr.fr", 465, "ssl", _("Votre mot de passe SFR.")),
    ("laposte", "La Poste", "smtp.laposte.net", 465, "ssl", _("Votre mot de passe La Poste.")),
    ("ovh", "OVH (nom de domaine)", "ssl0.ovh.net", 465, "ssl", _("Le mot de passe de la boîte OVH.")),
    ("yahoo", "Yahoo", "smtp.mail.yahoo.com", 465, "ssl", _("Yahoo demande un mot de passe d'application.")),
    ("icloud", "iCloud", "smtp.mail.me.com", 587, "starttls", _("iCloud demande un mot de passe d'application.")),
    ("outlook", "Outlook.com / Hotmail", "smtp-mail.outlook.com", 587, "starttls",
     _("Microsoft refuse souvent l'envoi par mot de passe : si l'essai échoue, choisissez plutôt « Mon logiciel "
       "de messagerie » ou « Outlook.com dans le navigateur ».")),
    ("autre", _("Autre"), "", 465, "ssl", _("Serveur d'envoi (SMTP) indiqué par votre fournisseur.")),
]
# serveur de reception (IMAP) pour deposer un brouillon, et adresse de la messagerie web
IMAP = {"orange": ("imap.orange.fr", "https://messagerie.orange.fr"),
        "gmail": ("imap.gmail.com", "https://mail.google.com/mail/u/0/#drafts"),
        "free": ("imap.free.fr", "https://webmail.free.fr"),
        "sfr": ("imap.sfr.fr", "https://webmail.sfr.fr"),
        "laposte": ("imap.laposte.net", "https://www.laposte.net/accueil"),
        "ovh": ("ssl0.ovh.net", "https://www.ovhcloud.com/fr/mail/"),
        "yahoo": ("imap.mail.yahoo.com", "https://mail.yahoo.com/d/folders/3"),
        "icloud": ("imap.mail.me.com", "https://www.icloud.com/mail"),
        "outlook": ("outlook.office365.com", "https://outlook.live.com/mail/0/drafts")}
LIMITE_MO = 20          # au-dela, beaucoup de messageries refusent (Gmail : 25 Mo encodage compris)


def fournisseur_de(adresse):
    dom = (adresse or "").rsplit("@", 1)[-1].lower()
    for cle, doms in (("orange", ("orange.fr", "wanadoo.fr")), ("gmail", ("gmail.com", "googlemail.com")),
                      ("free", ("free.fr",)), ("sfr", ("sfr.fr", "neuf.fr")), ("laposte", ("laposte.net",)),
                      ("yahoo", ("yahoo.fr", "yahoo.com")), ("icloud", ("icloud.com", "me.com")),
                      ("outlook", ("outlook.fr", "outlook.com", "hotmail.fr", "hotmail.com", "live.fr", "live.com"))):
        if dom in doms:
            return cle
    return "autre"


def comptes(params):
    return list(params.get("comptes_mail") or [])


def ident_coffre(compte):
    return "mail_" + compte["id"]


def nouveau_compte():
    return {"id": uuid.uuid4().hex[:10], "nom": "", "adresse": "", "identifiant": "", "serveur": "", "port": 465,
            "securite": "ssl", "signature": ""}


def adresses(texte):
    return [a.strip() for a in re.split(r"[;,\s]+", texte or "") if "@" in a]


# ------------------------------------------------------------------ fichier joint
def preparer_fichier(onglet, version, nom, mdp=""):
    """Ecrit la piece jointe dans un dossier temporaire ; renvoie son chemin."""
    import pymupdf as fitz
    if onglet.octets_signes:                      # document signe : on n'y touche pas (signatures valides)
        octets = onglet.octets_en_ajout()
    else:
        octets = onglet.doc.tobytes(garbage=3, deflate=True)
    if version == "allege" and not onglet.octets_signes:
        from .alleger import alleger, PREREGLAGES
        _n, dpi, qual, seuil = PREREGLAGES[0]
        octets = alleger(octets, {"images": True, "dpi": dpi, "qualite": qual, "seuil": seuil, "gris": False,
                                  "polices": True, "nettoyer": True, "infos": False, "jbig2": True,
                                  "noir_blanc": False, "polices_formulaire": True})
    elif version == "fige" and not onglet.octets_signes:
        d = fitz.open("pdf", octets)
        d.bake(annots=True, widgets=True)
        octets = d.tobytes(garbage=3, deflate=True)
    if version == "protege" and mdp and not onglet.octets_signes:
        d = fitz.open("pdf", octets)
        octets = d.tobytes(garbage=3, deflate=True, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw=mdp, owner_pw=mdp,
                           permissions=-1)
    nom = re.sub(r'[\\/:*?"<>|]+', "-", nom or "document.pdf").strip() or "document.pdf"
    if not nom.lower().endswith(".pdf"):
        nom += ".pdf"
    chemin = os.path.join(tempfile.mkdtemp(prefix="philpdf-envoi-"), nom)
    with open(chemin, "wb") as f:
        f.write(octets)
    return chemin


# ------------------------------------------------------------------ logiciel de messagerie
def _mapi(chemin, a, sujet, corps):
    """Nouveau message du logiciel de messagerie par defaut, PDF joint. 0 = ouvert ; autre = code d'erreur MAPI."""
    import ctypes
    from ctypes import wintypes as W

    class Recip(ctypes.Structure):
        _fields_ = [("ulReserved", W.ULONG), ("ulRecipClass", W.ULONG), ("lpszName", W.LPWSTR),
                    ("lpszAddress", W.LPWSTR), ("ulEIDSize", W.ULONG), ("lpEntryID", ctypes.c_void_p)]

    class Fichier(ctypes.Structure):
        _fields_ = [("ulReserved", W.ULONG), ("flFlags", W.ULONG), ("nPosition", W.ULONG),
                    ("lpszPathName", W.LPWSTR), ("lpszFileName", W.LPWSTR), ("lpFileType", ctypes.c_void_p)]

    class Message(ctypes.Structure):
        _fields_ = [("ulReserved", W.ULONG), ("lpszSubject", W.LPWSTR), ("lpszNoteText", W.LPWSTR),
                    ("lpszMessageType", W.LPWSTR), ("lpszDateReceived", W.LPWSTR),
                    ("lpszConversationID", W.LPWSTR), ("flFlags", W.ULONG), ("lpOriginator", ctypes.POINTER(Recip)),
                    ("nRecipCount", W.ULONG), ("lpRecips", ctypes.POINTER(Recip)), ("nFileCount", W.ULONG),
                    ("lpFiles", ctypes.POINTER(Fichier))]
    dests = adresses(a)
    recips = (Recip * max(1, len(dests)))()
    for i, x in enumerate(dests):
        recips[i] = Recip(0, 1, x, "SMTP:" + x, 0, None)
    fichiers = (Fichier * 1)(Fichier(0, 0, 0xFFFFFFFF, chemin, os.path.basename(chemin), None))
    m = Message(0, sujet, corps.replace("\n", "\r\n"), None, None, None, 0, None, len(dests),
                recips if dests else None, 1, fichiers)
    mapi = ctypes.WinDLL("mapi32.dll")
    f = mapi.MAPISendMailW
    f.argtypes = [ctypes.c_size_t, ctypes.c_size_t, ctypes.POINTER(Message), W.ULONG, W.ULONG]
    f.restype = W.ULONG
    return f(0, 0, ctypes.byref(m), 0x1 | 0x8, 0)          # MAPI_LOGON_UI | MAPI_DIALOG


def _outlook(chemin, a, sujet, corps):
    import pythoncom
    import win32com.client as wc
    pythoncom.CoInitialize()
    try:
        ol = wc.Dispatch("Outlook.Application")
        m = ol.CreateItem(0)
        m.To = "; ".join(adresses(a))
        m.Subject = sujet
        m.Display()                                  # affiche d'abord : la signature d'Outlook est ajoutee
        import html
        texte = html.escape(corps).replace("\n", "<br>")
        h = m.HTMLBody or ""
        i = h.lower().find("<body")
        j = h.find(">", i) + 1 if i >= 0 else 0
        m.HTMLBody = h[:j] + f"<div style='font-family:Calibri,Arial;font-size:11pt'>{texte}</div>" + h[j:]
        m.Attachments.Add(chemin)
    finally:
        pythoncom.CoUninitialize()


def par_logiciel(chemin, a, sujet, corps, rappel):
    """Ouvre le message dans le logiciel de messagerie (en arriere-plan : MAPI attend la fermeture du message).
    rappel(ok, message) est appele depuis un autre fil : a relayer vers l'interface."""
    def travail():
        if sys.platform != "win32":
            ok = _xdg_email(chemin, a, sujet, corps)
            rappel(ok, "" if ok else _("Aucun logiciel de messagerie trouvé."))
            return
        try:
            code = _mapi(chemin, a, sujet, corps)
        except Exception as e:                       # noqa: BLE001
            code = str(e)
        if code in (0, 1):                           # 1 = message ferme sans l'envoyer : rien a signaler
            rappel(True, "")
            return
        try:
            _outlook(chemin, a, sujet, corps)
            rappel(True, "")
        except Exception as e:                       # noqa: BLE001
            rappel(False, _("Le logiciel de messagerie n'a pas répondu (code MAPI {c} ; Outlook : {e}). Le « nouvel "
                            "Outlook » et le courrier de Windows ne savent pas recevoir une pièce jointe d'un autre "
                            "logiciel : utilisez un compte d'envoi PhilPDF ou la messagerie web.", c=code, e=str(e)[:120]))
    threading.Thread(target=travail, daemon=True).start()


def _xdg_email(chemin, a, sujet, corps):
    try:
        args = ["xdg-email", "--subject", sujet, "--body", corps, "--attach", chemin] + adresses(a)
        return subprocess.run(args, timeout=30).returncode == 0
    except Exception:                                # noqa: BLE001
        return False


def montrer_fichier(chemin):
    """Ouvre le dossier du fichier, le fichier selectionne (pour le glisser dans un message web)."""
    if sys.platform == "win32":
        subprocess.Popen(["explorer", "/select,", os.path.normpath(chemin)])
    else:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(chemin)))


# ------------------------------------------------------------------ envoi direct (SMTP)
def _connexion(compte, mdp, delai=40):
    import smtplib
    import ssl
    ctx = ssl.create_default_context()
    try:
        import truststore
        ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except Exception:                                # noqa: BLE001
        pass
    port = int(compte.get("port") or 465)
    if compte.get("securite") == "ssl":
        s = smtplib.SMTP_SSL(compte["serveur"], port, timeout=delai, context=ctx)
    else:
        s = smtplib.SMTP(compte["serveur"], port, timeout=delai)
        s.ehlo()
        if compte.get("securite") == "starttls":
            s.starttls(context=ctx)
            s.ehlo()
    if mdp:
        s.login(compte.get("identifiant") or compte["adresse"], mdp)
    return s


def expliquer(e):
    import smtplib
    t = str(e)
    if isinstance(e, smtplib.SMTPAuthenticationError):
        return _("Identifiant ou mot de passe refusé par le serveur. ") + t[:200]
    if isinstance(e, smtplib.SMTPRecipientsRefused):
        return _("Adresse du destinataire refusée : {a}", a=", ".join(e.recipients))
    if isinstance(e, (TimeoutError, OSError)) and not isinstance(e, smtplib.SMTPException):
        return _("Serveur injoignable ({e}). Vérifiez le serveur et le port, ou la connexion Internet.", e=t[:150])
    return t[:300]


def tester(compte, mdp):
    """None si la connexion et l'identification marchent, sinon l'explication."""
    try:
        s = _connexion(compte, mdp, 20)
        s.quit()
        return None
    except Exception as e:                           # noqa: BLE001
        return expliquer(e)


def _message(compte, a, cc, sujet, corps, chemin, copie_moi=False):
    from email.message import EmailMessage
    from email.utils import formataddr, formatdate, make_msgid
    m = EmailMessage()
    m["From"] = formataddr((compte.get("nom") or "", compte["adresse"]))
    m["To"] = ", ".join(adresses(a))
    if adresses(cc):
        m["Cc"] = ", ".join(adresses(cc))
    if copie_moi:
        m["Bcc"] = compte["adresse"]
    m["Subject"] = sujet
    m["Date"] = formatdate(localtime=True)
    m["Message-ID"] = make_msgid(domain=compte["adresse"].rsplit("@", 1)[-1])
    sig = (compte.get("signature") or "").strip()
    m.set_content(corps + (("\n\n-- \n" + sig) if sig else ""))
    with open(chemin, "rb") as f:
        m.add_attachment(f.read(), maintype="application", subtype="pdf", filename=os.path.basename(chemin))
    return m


def envoyer(compte, mdp, a, cc, sujet, corps, chemin, copie_moi=False):
    """Envoie le message ; leve une exception (a expliquer()) en cas d'echec."""
    m = _message(compte, a, cc, sujet, corps, chemin, copie_moi)
    s = _connexion(compte, mdp)
    try:
        s.send_message(m)
    finally:
        try:
            s.quit()
        except Exception:                            # noqa: BLE001
            pass


def imap_de(compte):
    return compte.get("imap") or IMAP.get(compte.get("fournisseur") or fournisseur_de(compte.get("adresse")), ("",))[0]


def webmail_de(compte):
    return compte.get("webmail") or IMAP.get(compte.get("fournisseur") or fournisseur_de(compte.get("adresse")),
                                             ("", ""))[1]


def brouillon(compte, mdp, a, cc, sujet, corps, chemin):
    """Depose le message (PDF joint) dans le dossier Brouillons de la messagerie (IMAP), comme Acrobat ;
    renvoie le nom du dossier. Il reste a l'ouvrir dans la messagerie web et cliquer « Envoyer »."""
    import imaplib
    import ssl
    import time
    serveur = imap_de(compte)
    if not serveur:
        raise RuntimeError(_("Serveur de réception (IMAP) inconnu pour ce compte : indiquez-le dans le compte."))
    m = _message(compte, a, cc, sujet, corps, chemin)
    del m["Bcc"]
    try:
        import truststore
        ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except Exception:                                # noqa: BLE001
        ctx = ssl.create_default_context()
    im = imaplib.IMAP4_SSL(serveur, 993, ssl_context=ctx, timeout=40)
    try:
        im.login(compte.get("identifiant") or compte["adresse"], mdp)
        dossier = None
        typ, lignes = im.list()
        noms = []
        for l in lignes or []:
            t = l.decode("utf-8", "replace") if isinstance(l, bytes) else str(l)
            mm = re.match(r'\((?P<f>[^)]*)\) "?(?P<sep>[^" ]*)"? (?P<n>.+)$', t)
            if not mm:
                continue
            nom = mm.group("n").strip().strip('"')
            noms.append(nom)
            if "\\drafts" in mm.group("f").lower():
                dossier = nom
        if not dossier:
            dossier = next((n for n in noms if n.split("/")[-1].split(".")[-1].lower() in
                            ("drafts", "brouillons", "draft", "brouillon")), "Drafts")
        cible = '"' + dossier.replace('"', '\\"') + '"'
        r = im.append(cible, "(\\Draft \\Seen)", imaplib.Time2Internaldate(time.time()), m.as_bytes())
        if r[0] != "OK":
            raise RuntimeError(str(r[1])[:200])
        return dossier
    finally:
        try:
            im.logout()
        except Exception:                            # noqa: BLE001
            pass


def logiciel_par_defaut():
    """Nom du logiciel de messagerie par defaut de Windows (Outlook, Thunderbird...), ou ""."""
    if sys.platform != "win32":
        return ""
    try:
        import winreg
        for racine in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                with winreg.OpenKey(racine, r"SOFTWARE\Clients\Mail") as k:
                    v = winreg.QueryValueEx(k, "")[0]
                    if v:
                        return v
            except OSError:
                continue
    except Exception:                                # noqa: BLE001
        pass
    return ""


def mot_de_passe(compte):
    return coffre.lire(ident_coffre(compte)) or ""
