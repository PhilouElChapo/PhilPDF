"""Case a cocher (CaseLongue) et bouton radio (RadioLong) dont le texte passe a la ligne au lieu d'etre coupe
(fenetres etroites, langues plus longues). S'utilisent comme QCheckBox / QRadioButton : isChecked, setChecked,
toggled, setToolTip, text..."""
from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import QCheckBox, QRadioButton, QLabel, QHBoxLayout, QSizePolicy, QStyle, QStyleOptionButton


class _Long:
    def __init__(self, texte="", parent=None):
        super().__init__(parent)
        self._lab = QLabel(texte, self)
        self._lab.setWordWrap(True)
        self._lab.setTextFormat(Qt.PlainText)
        o = QStyleOptionButton()
        o.initFrom(self)
        retrait = (self.style().pixelMetric(self._indicateur, o, self)
                   + self.style().pixelMetric(self._espace, o, self) + 2)
        h = QHBoxLayout(self)
        h.setContentsMargins(retrait, 1, 0, 1)
        h.addWidget(self._lab)
        sp = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        sp.setHeightForWidth(True)
        self.setSizePolicy(sp)

    def text(self):                                       # noqa: D401
        return self._lab.text()

    def setText(self, t):
        self._lab.setText(t)
        self.updateGeometry()

    def setToolTip(self, t):
        super().setToolTip(t)
        self._lab.setToolTip(t)

    def _marge(self):
        m = self.layout().contentsMargins()
        return m.left() + m.right(), m.top() + m.bottom()

    def sizeHint(self):
        mx, my = self._marge()
        s = self._lab.sizeHint()
        return QSize(s.width() + mx, max(s.height() + my, super().sizeHint().height()))

    def minimumSizeHint(self):
        mx, my = self._marge()
        mots = max((self.fontMetrics().horizontalAdvance(w) for w in self._lab.text().split()), default=0)
        return QSize(mots + mx, super().minimumSizeHint().height())

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        mx, my = self._marge()
        return max(self._lab.heightForWidth(max(10, w - mx)) + my, super().sizeHint().height())

    def resizeEvent(self, e):                             # assez haut pour toutes ses lignes a cette largeur
        super().resizeEvent(e)
        h = self.heightForWidth(self.width())
        if h != self.minimumHeight():
            self.setMinimumHeight(h)

    def hitButton(self, pos):                             # un clic sur le texte coche aussi
        return self.rect().contains(pos)


class CaseLongue(_Long, QCheckBox):
    _indicateur, _espace = QStyle.PM_IndicatorWidth, QStyle.PM_CheckBoxLabelSpacing


class RadioLong(_Long, QRadioButton):
    _indicateur, _espace = QStyle.PM_ExclusiveIndicatorWidth, QStyle.PM_RadioButtonLabelSpacing
