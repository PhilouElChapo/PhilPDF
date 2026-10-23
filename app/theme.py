"""Theme plat facon Windows 10/11 (Fluent), identique sous Linux.

Une seule feuille de style pour toute l'appli : boutons, champs, listes, onglets, cases, menus,
barres de defilement. Les couleurs viennent de COULEURS ; les petites images (coche, fleche)
sont ecrites en SVG dans le dossier de donnees au demarrage.
"""
import os

COULEURS = {
    "accent": "#0f6cbd",        # bleu Windows 11
    "accent_survol": "#115ea3",
    "rouge": "#c9252d",         # couleur PhilPDF
    "fond": "#f3f3f3",
    "surface": "#ffffff",
    "bord": "#d1d1d1",
    "bord_leger": "#e5e5e5",
    "survol": "#f5f5f5",
    "appui": "#ebebeb",
    "texte": "#1f1f1f",
    "texte2": "#616161",
    "desactive": "#a0a0a0",
}

_SVG = {
    "coche": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><path d="M3.5 8.5l3 3 6-7" fill="none" '
             'stroke="#ffffff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    "fleche": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><path d="M4 6l4 4 4-4" fill="none" '
              'stroke="#616161" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    "haut": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><path d="M5 10l3-3 3 3" fill="none" '
            'stroke="#616161" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    "bas": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><path d="M5 6l3 3 3-3" fill="none" '
           'stroke="#616161" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    "croix": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><path d="M4.5 4.5l7 7M11.5 4.5l-7 7" fill="none" '
             'stroke="#616161" stroke-width="1.4" stroke-linecap="round"/></svg>',
    "point": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><circle cx="8" cy="8" r="3.5" fill="#ffffff"/></svg>',
}


def _images(dossier):
    d = os.path.join(dossier, "theme")
    os.makedirs(d, exist_ok=True)
    chemins = {}
    for nom, svg in _SVG.items():
        p = os.path.join(d, nom + ".svg")
        try:
            if not os.path.exists(p) or open(p, encoding="utf-8").read() != svg:
                with open(p, "w", encoding="utf-8") as f:
                    f.write(svg)
        except OSError:
            pass
        chemins[nom] = p.replace("\\", "/")
    return chemins


def feuille(dossier):
    c = dict(COULEURS)
    c.update(_images(dossier))
    return """
QWidget { color: %(texte)s; }
QDialog, QMainWindow { background: %(fond)s; }
QToolTip { background: #2b2b2b; color: #fff; border: none; padding: 6px 8px; border-radius: 6px; }

/* ---------- boutons */
QPushButton {
    background: %(surface)s; border: 1px solid %(bord)s; border-bottom-color: #b9b9b9;
    border-radius: 4px; padding: 5px 14px; min-height: 20px;
}
QPushButton:hover { background: %(survol)s; }
QPushButton:pressed { background: %(appui)s; color: %(texte2)s; border-bottom-color: %(bord)s; }
QPushButton:disabled { color: %(desactive)s; background: %(fond)s; border-color: %(bord_leger)s; }
QPushButton:default, QPushButton[primaire="true"] {
    background: %(accent)s; color: #ffffff; border: 1px solid %(accent)s;
}
QPushButton:default:hover, QPushButton[primaire="true"]:hover { background: %(accent_survol)s; }
QPushButton:flat { background: transparent; border: none; }
QPushButton:flat:hover { background: %(appui)s; }
QPushButton::menu-indicator { image: url(%(fleche)s); subcontrol-position: right center; width: 12px; }
QToolButton { background: transparent; border: 1px solid transparent; border-radius: 4px; padding: 3px; }
QToolButton:hover { background: %(appui)s; }
QToolButton:pressed, QToolButton:checked { background: #e0e0e0; }
QToolButton::menu-indicator { image: none; }
QToolButton[popupMode="1"] { padding-right: 14px; }
QToolButton::menu-button { border: none; width: 12px; }
QToolButton::menu-arrow { image: url(%(fleche)s); width: 10px; height: 10px; }

/* ---------- champs */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QDateEdit, QTimeEdit, QPlainTextEdit, QTextEdit {
    background: %(surface)s; border: 1px solid %(bord)s; border-bottom: 1px solid #8a8a8a;
    border-radius: 4px; padding: 4px 8px; selection-background-color: %(accent)s;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus, QTextEdit:focus {
    border-bottom: 2px solid %(accent)s;
}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled { background: %(fond)s; color: %(desactive)s; }
QComboBox { padding-right: 24px; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox::down-arrow { image: url(%(fleche)s); width: 12px; height: 12px; }
QComboBox QAbstractItemView {
    background: %(surface)s; border: 1px solid %(bord)s; border-radius: 6px; padding: 4px; outline: none;
    selection-background-color: #e8f0fa; selection-color: %(texte)s;
}
QSpinBox::up-button, QDoubleSpinBox::up-button { border: none; width: 18px; subcontrol-position: top right; }
QSpinBox::down-button, QDoubleSpinBox::down-button { border: none; width: 18px; subcontrol-position: bottom right; }
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow { image: url(%(haut)s); width: 10px; height: 10px; }
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow { image: url(%(bas)s); width: 10px; height: 10px; }

/* ---------- cases et boutons radio */
QCheckBox, QRadioButton { spacing: 8px; background: transparent; }
QCheckBox::indicator, QRadioButton::indicator {
    width: 16px; height: 16px; border: 1px solid #8a8a8a; background: %(surface)s;
}
QCheckBox::indicator { border-radius: 4px; }
QRadioButton::indicator { border-radius: 9px; }
QCheckBox::indicator:hover, QRadioButton::indicator:hover { background: %(survol)s; }
QCheckBox::indicator:checked { background: %(accent)s; border-color: %(accent)s; image: url(%(coche)s); }
QRadioButton::indicator:checked { background: %(accent)s; border-color: %(accent)s; image: url(%(point)s); }
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled { border-color: %(bord)s; background: %(fond)s; }
QCheckBox:disabled, QRadioButton:disabled { color: %(desactive)s; }

/* ---------- listes, tableaux, arbres */
QListWidget, QListView, QTableWidget, QTableView, QTreeWidget, QTreeView {
    background: %(surface)s; border: 1px solid %(bord_leger)s; border-radius: 6px; outline: none;
    alternate-background-color: #fafafa; gridline-color: %(bord_leger)s;
}
QListView::item, QTreeView::item { padding: 3px; border-radius: 4px; }
QListView::item:hover, QTreeView::item:hover, QTableView::item:hover { background: %(survol)s; }
QListView::item:selected, QTreeView::item:selected, QTableView::item:selected { background: #e8f0fa; color: %(texte)s; }
QHeaderView::section {
    background: %(surface)s; border: none; border-bottom: 1px solid %(bord_leger)s; border-right: 1px solid %(bord_leger)s;
    padding: 5px 8px; font-weight: 600; color: %(texte2)s;
}
QTableCornerButton::section { background: %(surface)s; border: none; }

/* ---------- onglets de dialogue */
QTabWidget::pane { border: 1px solid %(bord_leger)s; border-radius: 6px; background: %(surface)s; top: -1px; }
QTabBar::tab {
    background: transparent; border: none; padding: 7px 14px; margin-right: 2px; color: %(texte2)s;
    border-bottom: 3px solid transparent;
}
QTabBar::tab:hover { color: %(texte)s; background: %(appui)s; border-top-left-radius: 4px; border-top-right-radius: 4px; }
QTabBar::tab:selected { color: %(texte)s; font-weight: 600; border-bottom: 3px solid %(accent)s; }
QTabBar::close-button { image: url(%(croix)s); subcontrol-position: right; margin: 2px; border-radius: 4px; }
QTabBar::close-button:hover { background: #e0e0e0; }

/* ---------- groupes, curseurs, barres */
QGroupBox { border: 1px solid %(bord_leger)s; border-radius: 6px; margin-top: 14px; padding: 10px 8px 8px 8px; background: %(surface)s; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: %(texte2)s; font-weight: 600; }
QSlider::groove:horizontal { height: 4px; background: #c4c4c4; border-radius: 2px; }
QSlider::sub-page:horizontal { background: %(accent)s; border-radius: 2px; }
QSlider::handle:horizontal {
    background: %(surface)s; border: 5px solid %(accent)s; width: 10px; height: 10px; margin: -8px 0; border-radius: 10px;
}
QProgressBar { border: none; background: %(bord_leger)s; border-radius: 3px; height: 6px; text-align: center; color: transparent; }
QProgressBar::chunk { background: %(accent)s; border-radius: 3px; }
QSplitter::handle { background: transparent; }
QSplitter::handle:hover { background: %(bord)s; }

/* ---------- barres de defilement fines */
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #c2c2c2; border-radius: 3px; min-height: 30px; margin: 0 2px; }
QScrollBar::handle:horizontal { background: #c2c2c2; border-radius: 3px; min-width: 30px; margin: 2px 0; }
QScrollBar::handle:hover { background: #8a8a8a; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

/* ---------- menus */
QMenuBar { background: %(surface)s; border-bottom: 1px solid %(bord_leger)s; }
QMenuBar::item { padding: 6px 10px; background: transparent; border-radius: 4px; }
QMenuBar::item:selected { background: %(appui)s; }
QMenu { background: %(surface)s; border: 1px solid %(bord)s; border-radius: 8px; padding: 4px; }
QMenu::item { padding: 6px 28px 6px 12px; border-radius: 4px; }
QMenu::item:selected { background: #e8f0fa; color: %(texte)s; }
QMenu::item:disabled { color: %(desactive)s; }
QMenu::icon { padding-left: 8px; }
QMenu::separator { height: 1px; background: %(bord_leger)s; margin: 4px 8px; }
QStatusBar { background: %(fond)s; color: %(texte2)s; }
""" % c
