"""Fenetres adaptees a la taille de l'ecran (ex. 1024 × 768) : aucune fenetre ne depasse l'ecran.

Un filtre pose sur toute l'application regarde chaque fenetre au moment ou elle s'affiche : si elle est plus grande
que la place disponible, elle est reduite et centree ; si son contenu ne tient pas, il est mis dans une zone qui
defile (les boutons OK / Annuler restent visibles en bas)."""
from PySide6.QtCore import QObject, QEvent, Qt, QTimer
from PySide6.QtWidgets import (QDialog, QMainWindow, QScrollArea, QWidget, QVBoxLayout, QDialogButtonBox,
                               QFrame, QApplication)


def place(w):
    ecr = w.screen() or QApplication.primaryScreen()
    return ecr.availableGeometry() if ecr else None


def _defilant(d, dispo):
    """Met le contenu de la fenetre dans une zone qui defile ; les boutons du bas restent hors de la zone."""
    lay = d.layout()
    if lay is None or getattr(d, "_defilant", False):
        return
    d._defilant = True
    boutons = None
    if lay.count():                                   # derniere ligne = boutons OK / Annuler : gardee visible
        it = lay.itemAt(lay.count() - 1)
        if it.widget() is not None and isinstance(it.widget(), QDialogButtonBox):
            boutons = it.widget()
            lay.removeWidget(boutons)
    interieur = QWidget()
    interieur.setLayout(lay)                          # le layout passe dans le widget qui defile
    zone = QScrollArea()
    zone.setWidgetResizable(True)
    zone.setFrameShape(QFrame.NoFrame)
    zone.setWidget(interieur)
    nouveau = QVBoxLayout(d)
    nouveau.setContentsMargins(0, 0, 0, 0)
    nouveau.addWidget(zone, 1)
    if boutons is not None:
        h = QWidget()
        hv = QVBoxLayout(h)
        hv.setContentsMargins(10, 4, 10, 10)
        hv.addWidget(boutons)
        nouveau.addWidget(h)


def ajuster(w):
    dispo = place(w)
    if dispo is None:
        return
    maxw, maxh = int(dispo.width() * 0.96), int(dispo.height() * 0.94)
    trop = w.minimumSizeHint().width() > maxw or w.minimumSizeHint().height() > maxh or \
        w.minimumWidth() > maxw or w.minimumHeight() > maxh
    if isinstance(w, QDialog) and trop:
        w.setMinimumSize(min(w.minimumWidth(), maxw), min(w.minimumHeight(), maxh))
        _defilant(w, dispo)
    if w.width() > maxw or w.height() > maxh or trop:
        w.setMinimumSize(min(w.minimumWidth(), maxw), min(w.minimumHeight(), maxh))
        w.resize(min(w.width(), maxw), min(w.height(), maxh))
        if not isinstance(w, QMainWindow) or not w.isMaximized():
            g = w.frameGeometry()
            g.moveCenter(dispo.center())
            w.move(max(dispo.left(), g.left()), max(dispo.top(), g.top()))


class _Filtre(QObject):
    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Show and isinstance(obj, (QDialog, QMainWindow)) and obj.isWindow():
            try:
                ajuster(obj)
                QTimer.singleShot(0, lambda o=obj: _encore(o))
            except RuntimeError:
                pass
        return False


def _encore(o):
    try:
        ajuster(o)
    except RuntimeError:
        pass


_filtre = None


def installer(app):
    global _filtre
    _filtre = _Filtre(app)
    app.installEventFilter(_filtre)
