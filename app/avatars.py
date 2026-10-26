"""Icone de chaque compte (Drive, OneDrive, Dropbox, Box, NAS...).

Trois facons de les distinguer, au choix dans Preferences > Comptes (reglage « comptes_icone ») :
  - « photo »    : la photo du compte (celle du profil Google, Microsoft, Dropbox ou Box), dans la roue de synchro ;
                   sans photo, la pastille ci-dessous ;
  - « pastille » : une pastille de couleur avec l'initiale du service, dans la roue de synchro ;
  - « simple »   : la roue seule, comme avant.
Chaque compte peut aussi recevoir sa propre image (n'importe quel fichier : logo, photo...) et sa couleur ;
l'image choisie voyage avec les reglages (petite, en base64) pour etre la meme sur tous les postes.
Les photos de profil, elles, sont gardees sur chaque poste (dossier « avatars ») et redemandees au bout d'une semaine.
"""
import base64, os, time

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt, QSize
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QPainter, QPainterPath, QPen, QPixmap

from .langue import _

def modes():
    return {"photo": _("Photo du compte (sinon pastille du service)"), "pastille": _("Pastille du service (initiale et couleur)"),
            "simple": _("Roue seule, comme avant")}
# initiale et couleur par defaut de chaque service (simple reperage, pas les logos des marques)
PASTILLES = {"gdrive": ("G", "#2e7d32"), "onedrive": ("O", "#0f6cbd"), "dropbox": ("D", "#3949ab"), "box": ("B", "#00838f"),
             "synology": ("S", "#5d4037"), "webdav": ("W", "#6a1b9a"), "ftp": ("F", "#ad1457"), "reseau": ("R", "#455a64")}
SEMAINE = 7 * 24 * 3600      # delai avant de redemander une photo absente


def dossier():
    from .config import dossier_donnees
    d = os.path.join(dossier_donnees(), "avatars")
    os.makedirs(d, exist_ok=True)
    return d


def chemin_photo(compte):
    return os.path.join(dossier(), compte["id"] + ".img")


def _marque_absente(compte):
    return os.path.join(dossier(), compte["id"] + ".aucune")


def photo_a_demander(compte):
    from . import distant
    if compte.get("type") not in distant.NUAGES or os.path.exists(chemin_photo(compte)):
        return False
    try:
        return time.time() - os.path.getmtime(_marque_absente(compte)) > SEMAINE
    except OSError:
        return True


def recuperer_photo(compte, emplacement=None, forcer=False):
    """Demande la photo du profil au service (une fois ; sans photo, on reessaie au bout d'une semaine).
    Renvoie True si une photo est disponible. Jamais d'erreur : une icone ne doit rien bloquer."""
    if not forcer and not photo_a_demander(compte):
        return os.path.exists(chemin_photo(compte))
    try:
        from . import distant
        e = emplacement or distant.emplacement(compte)
        octets = e.photo() if hasattr(e, "photo") else None
    except Exception:
        octets = None
    img = QImage.fromData(octets) if octets else QImage()
    if img.isNull():
        try:
            with open(_marque_absente(compte), "w") as f:
                f.write(time.strftime("%Y-%m-%d"))
        except OSError:
            pass
        return False
    img = img.scaled(96, 96, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    img.save(chemin_photo(compte), "PNG")
    _cache.clear()
    return True


def oublier_photo(compte):
    for p in (chemin_photo(compte), _marque_absente(compte)):
        try:
            os.remove(p)
        except OSError:
            pass
    _cache.clear()


def image_en_texte(chemin, taille=96):
    """Image choisie par l'utilisateur -> petit PNG en base64 (pour voyager avec les reglages)."""
    img = QImage(chemin)
    if img.isNull():
        return None
    img = img.scaled(taille, taille, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    return base64.b64encode(bytes(buf.data())).decode("ascii")


def _image_perso(compte):
    b = compte.get("image")
    if not b:
        return None
    try:
        img = QImage.fromData(QByteArray(base64.b64decode(b)))
    except (ValueError, TypeError):
        return None
    return None if img.isNull() else img


_cache = {}


def couleur(compte):
    return compte.get("couleur") or PASTILLES.get(compte.get("type"), ("?", "#0f6cbd"))[1]


def icone_compte(compte, params=None, taille=48):
    """QIcon du compte selon le reglage choisi."""
    from . import distant
    from .icones import icone
    from .dialogues_distant import ICONES
    mode = (params or {}).get("comptes_icone", "photo") if params is not None else "photo"
    nuage = compte.get("type") in distant.NUAGES
    perso = _image_perso(compte)
    cle = (compte.get("id"), compte.get("type"), mode, compte.get("couleur"), len(compte.get("image") or ""), taille,
           os.path.exists(chemin_photo(compte)) if compte.get("id") else False)
    if cle in _cache:
        return _cache[cle]
    if perso is None and mode == "simple":
        ic = icone(ICONES.get(compte.get("type"), "ouvrir"), "#0f6cbd", taille)
    elif perso is None and not nuage and mode != "pastille":
        ic = icone(ICONES.get(compte.get("type"), "ouvrir"), couleur(compte) if compte.get("couleur") else "#0f6cbd", taille)
    else:
        img = perso
        if img is None and mode == "photo" and compte.get("id") and os.path.exists(chemin_photo(compte)):
            img = QImage(chemin_photo(compte))
            if img.isNull():
                img = None
        ic = QIcon(dessiner(compte, img, taille, roue=nuage))
    _cache[cle] = ic
    return ic


def dessiner(compte, img, taille, roue=True):
    """Roue de synchro autour, et au centre la photo / l'image ou la pastille avec l'initiale."""
    from .icones import TRAITS
    from PySide6.QtSvg import QSvgRenderer
    pm = QPixmap(QSize(taille, taille))
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    c = couleur(compte)
    if roue:
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="1.6 1.6 20.8 20.8" fill="none" stroke="{c}" '
               f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{TRAITS["synchro"]}</svg>')
        QSvgRenderer(QByteArray(svg.encode())).render(p, QRectF(0, 0, taille, taille))
        r = taille * 0.30                       # disque central, a l'interieur des fleches
    else:
        r = taille * 0.48
    centre = taille / 2
    disque = QRectF(centre - r, centre - r, 2 * r, 2 * r)
    chemin = QPainterPath()
    chemin.addEllipse(disque)
    if img is not None:
        p.save()
        p.setClipPath(chemin)
        p.fillPath(chemin, QColor("white"))
        src = img.scaled(int(2 * r * 2), int(2 * r * 2), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        p.drawImage(disque, src, QRectF((src.width() - min(src.width(), src.height())) / 2,
                                        (src.height() - min(src.width(), src.height())) / 2,
                                        min(src.width(), src.height()), min(src.width(), src.height())))
        p.restore()
    else:
        p.fillPath(chemin, QColor(c))
        lettre = (compte.get("lettre") or PASTILLES.get(compte.get("type"), ("?", c))[0])[:2]
        f = QFont()
        f.setBold(True)
        f.setPixelSize(max(6, int(r * (1.25 if len(lettre) == 1 else 0.95))))
        p.setFont(f)
        p.setPen(QPen(QColor("white")))
        p.drawText(disque, Qt.AlignCenter, lettre)
    p.end()
    return pm
