"""Choisir un dossier, y compris une Bibliotheque de Windows (Documents, Telechargements, Images...) :
la bibliotheque est remplacee par son vrai dossier (celui ou Windows enregistre)."""
import os
import sys
from urllib.parse import unquote

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QFileDialog

GUIDS = {"documents": "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}", "downloads": "{374DE290-123F-4565-9164-39C4925E467B}",
         "pictures": "{33E28130-4E1E-4676-835A-98395C3BC3BB}", "music": "{4BD8D571-6D19-48D3-BE97-422220080E43}",
         "videos": "{18989B1D-99B5-455B-841C-AB7C74E4DDFC}", "desktop": "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}"}
NOMS = {"documents": ("documents",), "downloads": ("downloads", "téléchargements", "telechargements"),
        "pictures": ("pictures", "images"), "music": ("music", "musique"), "videos": ("videos", "vidéos"),
        "desktop": ("desktop", "bureau")}


def _connu(guid):
    from .session import _dossier_windows
    return _dossier_windows(guid)


def resoudre(texte):
    """Chemin reel d'un choix : dossier ordinaire tel quel ; bibliotheque (« Downloads.library-ms »,
    « ::{...}\\Téléchargements »...) -> son dossier."""
    if not texte:
        return ""
    if os.path.isdir(texte) and not texte.lower().endswith(".library-ms"):
        return texte
    bas = unquote(texte).replace("\\", "/").lower().rstrip("/")
    dernier = bas.split("/")[-1].replace(".library-ms", "")
    for cle, noms in NOMS.items():
        if dernier in noms or any(bas.endswith("/" + n) for n in noms):
            if sys.platform == "win32":
                try:
                    p = _connu(GUIDS[cle])
                    if p and os.path.isdir(p):
                        return p
                except Exception:                    # noqa: BLE001
                    pass
            p = os.path.join(os.path.expanduser("~"), {"downloads": "Downloads"}.get(cle, cle.capitalize()))
            if os.path.isdir(p):
                return p
    return ""


def choisir_dossier(parent, titre, depart=""):
    """Comme QFileDialog.getExistingDirectory, en acceptant aussi les Bibliotheques de Windows."""
    depart = resoudre(depart) or depart or os.path.expanduser("~")
    if sys.platform != "win32":
        return QFileDialog.getExistingDirectory(parent, titre, depart)
    url = QFileDialog.getExistingDirectoryUrl(parent, titre, QUrl.fromLocalFile(depart),
                                              QFileDialog.ShowDirsOnly, ["file", "clsid", "shell"])
    if url.isEmpty():
        return ""
    local = url.toLocalFile()
    return resoudre(local) or resoudre(url.toString()) or local
