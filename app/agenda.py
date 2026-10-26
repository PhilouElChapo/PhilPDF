"""Envoi d'une date (rendez-vous, echeance) vers l'agenda de l'utilisateur, et d'un message vers sa messagerie.

Rien n'est ajoute ni envoye en silence : PhilPDF ouvre l'agenda ou la messagerie avec tout pre-rempli, et c'est
vous qui cliquez sur « Enregistrer » ou « Envoyer ». Aucune autorisation supplementaire n'est demandee.
Agendas : Google Agenda, Outlook.com, Outlook (Microsoft 365) ou un fichier .ics (Outlook de bureau, Thunderbird,
agenda Apple...). Messageries : Gmail, Outlook.com, Outlook (Microsoft 365) ou la messagerie par defaut (mailto).
"""
import datetime, os, tempfile, urllib.parse

AGENDAS = [("google", "Google Agenda"), ("outlook", "Outlook.com"), ("office", "Outlook (Microsoft 365)"),
           ("ics", "Fichier .ics (autre agenda)")]
MESSAGERIES = [("gmail", "Gmail"), ("outlook", "Outlook.com"), ("office", "Outlook (Microsoft 365)"),
               ("mailto", "Messagerie par défaut")]


def _bornes(date_iso, heure=None, duree_min=60):
    j = datetime.date.fromisoformat(date_iso[:10])
    if heure:
        h, m = (int(x) for x in heure.split(":")[:2])
        debut = datetime.datetime(j.year, j.month, j.day, h, m)
        return debut, debut + datetime.timedelta(minutes=duree_min), False
    return j, j + datetime.timedelta(days=1), True


def lien_agenda(agenda, titre, date_iso, heure=None, details=""):
    """Adresse web (ou chemin d'un fichier .ics) qui ouvre l'evenement pre-rempli."""
    debut, fin, journee = _bornes(date_iso, heure)
    if agenda == "google":
        f = "%Y%m%d" if journee else "%Y%m%dT%H%M%S"
        q = {"action": "TEMPLATE", "text": titre, "dates": f"{debut.strftime(f)}/{fin.strftime(f)}", "details": details}
        return "https://calendar.google.com/calendar/render?" + urllib.parse.urlencode(q)
    if agenda in ("outlook", "office"):
        base = "https://outlook.live.com" if agenda == "outlook" else "https://outlook.office.com"
        q = {"path": "/calendar/action/compose", "rru": "addevent", "subject": titre, "body": details,
             "startdt": debut.isoformat(), "enddt": fin.isoformat(), "allday": "true" if journee else "false"}
        return base + "/calendar/0/deeplink/compose?" + urllib.parse.urlencode(q)
    return fichier_ics(titre, debut, fin, journee, details)


def _ics_echapper(t):
    for a, b in (("\\", "\\\\"), (";", "\\;"), (",", "\\,"), ("\n", "\\n")):
        t = t.replace(a, b)
    return t


def fichier_ics(titre, debut, fin, journee, details=""):
    if journee:
        d, f = f"DTSTART;VALUE=DATE:{debut.strftime('%Y%m%d')}", f"DTEND;VALUE=DATE:{fin.strftime('%Y%m%d')}"
    else:
        d, f = f"DTSTART:{debut.strftime('%Y%m%dT%H%M%S')}", f"DTEND:{fin.strftime('%Y%m%dT%H%M%S')}"
    uid = f"{datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')}@philpdf"
    texte = "\r\n".join(["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//PhilPDF//FR", "BEGIN:VEVENT", f"UID:{uid}",
                         f"DTSTAMP:{datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}", d, f,
                         f"SUMMARY:{_ics_echapper(titre)}", f"DESCRIPTION:{_ics_echapper(details)}",
                         "BEGIN:VALARM", "TRIGGER:-P1D", "ACTION:DISPLAY", f"DESCRIPTION:{_ics_echapper(titre)}",
                         "END:VALARM", "END:VEVENT", "END:VCALENDAR", ""])
    p = os.path.join(tempfile.mkdtemp(prefix="philpdf_"), "rendez-vous.ics")
    with open(p, "w", encoding="utf-8", newline="") as fh:
        fh.write(texte)
    return p


def lien_message(messagerie, sujet, corps, a=""):
    if messagerie == "gmail":
        return "https://mail.google.com/mail/?" + urllib.parse.urlencode({"view": "cm", "fs": "1", "to": a, "su": sujet, "body": corps})
    if messagerie in ("outlook", "office"):
        base = "https://outlook.live.com" if messagerie == "outlook" else "https://outlook.office.com"
        return base + "/mail/deeplink/compose?" + urllib.parse.urlencode({"to": a, "subject": sujet, "body": corps})
    return f"mailto:{urllib.parse.quote(a)}?" + urllib.parse.urlencode({"subject": sujet, "body": corps}, quote_via=urllib.parse.quote)


def ouvrir(cible):
    """Ouvre une adresse web ou un fichier (.ics) avec l'application par defaut. Renvoie True si lance."""
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices
    url = QUrl(cible) if "://" in cible or cible.startswith("mailto:") else QUrl.fromLocalFile(cible)
    return QDesktopServices.openUrl(url)
