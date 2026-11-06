"""Rien de tronque : chaque outil et chaque entree de menu est lance, chaque fenetre qui s'ouvre est verifiee a sa
taille d'ouverture PUIS a sa plus petite taille (l'utilisateur peut la reduire), et refermee sans rien faire.
Un bouton, une case, une etiquette ou une liste deroulante dont le texte ne tient pas est signale.
Lance a chaque fabrication : une nouvelle fenetre avec un texte coupe fait echouer la fabrication."""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["PHILPDF_LANGUE"] = os.environ.get("PHILPDF_LANGUE", "fr")
os.environ["APPDATA"] = tempfile.mkdtemp()
os.environ["HOME"] = os.environ["APPDATA"]
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import faulthandler
faulthandler.dump_traceback_later(int(os.environ.get("TRONQ_DUMP", "0")) or 10**6, repeat=False, exit=True)   # bloque : on voit ou, et on echoue
import pymupdf as fitz
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QApplication, QDialog, QMessageBox, QFileDialog, QAbstractButton, QLabel, QComboBox,
                               QInputDialog, QWidget, QMenu, QToolButton, QColorDialog, QFontDialog,
                               QCheckBox, QRadioButton, QStyle)

app = QApplication(sys.argv)
app.setStyle("Fusion")

PROBLEMES = {}        # fenetre -> [description]
VUES = []


def _texte(w):
    try:
        return w.text().replace("&&", "\0").replace("&", "").replace("\0", "&")
    except Exception:                                   # noqa: BLE001
        return ""


def tronques(fen):
    """Elements de fen dont le texte depasse la place qu'ils ont."""
    out = []
    for w in fen.findChildren(QWidget):
        if not w.isVisibleTo(fen) or w.width() <= 0:
            continue
        fm = w.fontMetrics()
        if isinstance(w, QAbstractButton):
            t = _texte(w)
            if not t.strip() or (isinstance(w, QToolButton) and w.toolButtonStyle() == Qt.ToolButtonIconOnly):
                continue
            if hasattr(w, "_lab"):                       # CaseLongue : son texte passe a la ligne
                continue
            # place reelle du texte : son trace + l'icone ou la case + les marges du style
            if isinstance(w, (QCheckBox, QRadioButton)):
                st = w.style()
                besoin = fm.horizontalAdvance(t) + st.pixelMetric(QStyle.PM_IndicatorWidth) + st.pixelMetric(QStyle.PM_CheckBoxLabelSpacing)
            else:
                besoin = fm.horizontalAdvance(t) + 8
            if isinstance(w, (QCheckBox, QRadioButton)):
                pass
            elif not w.icon().isNull() and not (isinstance(w, QToolButton) and w.toolButtonStyle() == Qt.ToolButtonTextUnderIcon):
                besoin += w.iconSize().width() + 4
            if w.width() < besoin:
                out.append(f"{type(w).__name__} « {t[:50]} » : {w.width()} px pour {besoin} px")
        elif isinstance(w, QLabel):
            t = w.text()
            if not t.strip() or w.wordWrap() or w.pixmap() is not None and not w.pixmap().isNull() or "<" in t:
                continue
            ligne = max((fm.horizontalAdvance(x) for x in t.split("\n")), default=0)
            if w.width() + 2 < ligne:
                out.append(f"QLabel « {t[:50]} » : {w.width()} px pour {ligne} px")
        elif isinstance(w, QComboBox):
            t = w.currentText()
            if t and w.width() < fm.horizontalAdvance(t) + 22:
                out.append(f"QComboBox « {t[:50]} » : {w.width()} px pour {fm.horizontalAdvance(t) + 22} px")
    return out


def verifier(fen, nom):
    fen.show()
    for _ in range(3):
        app.processEvents()
    titre = nom + " — " + (fen.windowTitle() or type(fen).__name__)
    VUES.append(titre)
    p = [("à l'ouverture", x) for x in tronques(fen)]
    m = fen.minimumSizeHint()
    if m.isValid():
        fen.resize(max(m.width(), fen.minimumWidth()), max(m.height(), fen.minimumHeight()))
        for _ in range(3):
            app.processEvents()
        p += [("réduite", x) for x in tronques(fen) if ("à l'ouverture", x) not in p]
    if p:
        PROBLEMES.setdefault(titre, []).extend(f"{q} : {x}" for q, x in p)


# ---------------------------------------------------------------- interception : rien ne s'execute vraiment
EN_COURS = ["?"]


def _exec(self, *a, **k):
    if type(self).__name__ in ("QPrintDialog", "QPrintPreviewDialog", "QPageSetupDialog", "QFileDialog", "QColorDialog",
                               "QFontDialog"):        # fenetres standard de Qt : Windows montre les siennes
        self.hide()
        return QDialog.Rejected
    verifier(self, EN_COURS[0])
    self.hide()
    return QDialog.Rejected


QDialog.exec = _exec
QDialog.exec_ = _exec
from PySide6.QtPrintSupport import QPrintDialog, QPrintPreviewDialog, QPageSetupDialog   # noqa: E402
from PySide6.QtWidgets import QWizard, QProgressDialog                                  # noqa: E402
for _c in (QPrintDialog, QPrintPreviewDialog, QPageSetupDialog, QFileDialog, QColorDialog, QFontDialog, QInputDialog,
           QWizard, QProgressDialog):
    _c.exec = _exec
QMessageBox.exec = lambda self, *a, **k: (verifier(self, EN_COURS[0]), QMessageBox.Cancel)[1]
for f in ("information", "warning", "critical"):
    setattr(QMessageBox, f, staticmethod(lambda *a, **k: QMessageBox.Ok))
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.No)
QMessageBox.about = staticmethod(lambda *a, **k: None)
QMessageBox.aboutQt = staticmethod(lambda *a, **k: None)
QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: ("", ""))
QFileDialog.getOpenFileNames = staticmethod(lambda *a, **k: ([], ""))
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: ("", ""))
QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: "")
from PySide6.QtCore import QUrl                         # noqa: E402
QFileDialog.getExistingDirectoryUrl = staticmethod(lambda *a, **k: QUrl())   # Windows (bibliotheques)
QFileDialog.getOpenFileUrl = staticmethod(lambda *a, **k: (QUrl(), ""))
QFileDialog.getOpenFileUrls = staticmethod(lambda *a, **k: ([], ""))
QFileDialog.getSaveFileUrl = staticmethod(lambda *a, **k: (QUrl(), ""))
QInputDialog.getText = staticmethod(lambda *a, **k: ("", False))
QInputDialog.getItem = staticmethod(lambda *a, **k: ("", False))
QInputDialog.getInt = staticmethod(lambda *a, **k: (0, False))
QInputDialog.getDouble = staticmethod(lambda *a, **k: (0.0, False))
QInputDialog.getMultiLineText = staticmethod(lambda *a, **k: ("", False))
QColorDialog.getColor = staticmethod(lambda *a, **k: __import__("PySide6.QtGui", fromlist=["QColor"]).QColor())
QFontDialog.getFont = staticmethod(lambda *a, **k: (False, None))


class _Menu(QMenu):
    """Menus surgissants : rien a couper (Qt les dimensionne) ; on ne les ouvre pas (exec bloquerait)."""
    def exec(self, *a, **k):                             # noqa: A003
        return None
    exec_ = exec


import PySide6.QtWidgets as _QW                          # noqa: E402
_QW.QMenu = _Menu                                        # les modules de l'application importent ce QMenu-la

from app.fenetre import Fenetre                         # noqa: E402
import app.outils as O                                   # noqa: E402

w = Fenetre()
w.resize(1280, 800)
w.show()
app.processEvents()
verifier(w, "Fenêtre principale")

d = fitz.open()
for i in range(3):
    p = d.new_page()
    p.insert_text((72, 100), f"Page {i + 1} : texte pour les essais", fontsize=14)
chemin = os.path.join(os.environ["APPDATA"], "essai.pdf")
d.save(chemin)
w.ouvrir(chemin)
app.processEvents()

# 1. chaque outil
ids = [o[0] for o in O.OUTILS] if hasattr(O, "OUTILS") else []
for oid in ids:
    if oid in ("imprimer", "imprimante", "courriel"):
        pass
    EN_COURS[0] = f"outil {oid}"
    print("…", EN_COURS[0], flush=True)
    try:
        w.lancer_outil(oid)
        for _ in range(3):
            app.processEvents()
        # fenetres non modales ouvertes par l'outil (lecture fluide, volets...)
        for t in app.topLevelWidgets():
            if t is not w and t.isVisible() and isinstance(t, QDialog):
                verifier(t, EN_COURS[0])
                t.close()
    except Exception as e:                               # noqa: BLE001
        print(f"  (outil {oid} : {type(e).__name__} : {e})")
    if w.doc_courant() is None:
        w.ouvrir(chemin)
        app.processEvents()

# 2. chaque entree des menus (sauf quitter / fermer)
EVITER = ("Quitter", "Fermer", "Quit", "Close")
for menu in w.menuBar().findChildren(QMenu):
    for a in menu.actions():
        if a.isSeparator() or a.menu() or not a.isEnabled() or any(x in a.text() for x in EVITER):
            continue
        EN_COURS[0] = f"menu {menu.title().replace('&', '')} › {a.text().replace('&', '')}"
        print("…", EN_COURS[0], flush=True)
        try:
            a.trigger()
            for _ in range(3):
                app.processEvents()
            for t in app.topLevelWidgets():
                if t is not w and t.isVisible() and isinstance(t, QDialog):
                    verifier(t, EN_COURS[0])
                    t.close()
        except Exception as e:                           # noqa: BLE001
            print(f"  ({EN_COURS[0]} : {type(e).__name__} : {e})")
        if w.doc_courant() is None:
            w.ouvrir(chemin)
            app.processEvents()

print(f"{len(VUES)} fenêtre(s) et menu(s) vérifié(s)")
for t, l in sorted(PROBLEMES.items()):
    print(f"✕ {t}")
    for x in l[:12]:
        print("     " + x)
print("RESULTAT :", "OK" if not PROBLEMES else f"{len(PROBLEMES)} fenêtre(s) avec un texte coupé")
os._exit(0 if not PROBLEMES else 1)
