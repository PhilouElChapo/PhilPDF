"""Icones PhilPDF (traits simples, libres de droits, dessinees pour l'appli)."""
from PySide6.QtCore import QByteArray, Qt, QSize
from PySide6.QtGui import QIcon, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer

TRAITS = {
    "ouvrir": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "creer": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M12 18v-6M9 15h6"/>',
    "combiner": '<rect x="8" y="8" width="12" height="14" rx="2"/><path d="M4 16V4a2 2 0 0 1 2-2h10"/>',
    "organiser": '<rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/>',
    "exporter": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M8 15h8M13 12l3 3-3 3"/>',
    "imprimer": '<path d="M6 9V2h12v7"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="8"/>',
    "modifier": '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
    "remplacer": '<circle cx="10" cy="10" r="6"/><path d="M20 20l-5.6-5.6"/><path d="M8 10h4"/>',
    "entete": '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M4 8h16M4 16h16"/>',
    "filigrane": '<path d="M12 2.7l5.7 5.7a8 8 0 1 1-11.4 0z"/>',
    "commentaire": '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/><path d="M8 9h8M8 13h5"/>',
    "tampon": '<path d="M5 22h14"/><path d="M19.3 13.7A2.5 2.5 0 0 0 17.5 13h-11A2.5 2.5 0 0 0 4 15.5V17a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-1.5c0-.7-.3-1.3-.7-1.8z"/><path d="M14 13V8.5C14 7 15 7 15 5a3 3 0 0 0-6 0c0 2 1 2 1 3.5V13"/>',
    "signer": '<path d="M3 17c3-3 4-9 6-9s1 7 3 7 3-4 5-4 2 2 4 2"/><path d="M3 21h18"/>',
    "certificat": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="M9 12l2 2 4-4"/>',
    "formulaire": '<rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="M9 12h6M9 16h6"/>',
    "champ_signature": '<rect x="3" y="7" width="18" height="10" rx="2"/><path d="M6 14c1.5-1.5 2-3 3-3s.5 2 1.5 2 1.5-1 2.5-1"/><path d="M15 14h3"/>',
    "numeriser": '<path d="M3 7V5a2 2 0 0 1 2-2h2M17 3h2a2 2 0 0 1 2 2v2M21 17v2a2 2 0 0 1-2 2h-2M7 21H5a2 2 0 0 1-2-2v-2"/><path d="M7 12h10"/>',
    "ocr": '<path d="M3 7V5a2 2 0 0 1 2-2h2M17 3h2a2 2 0 0 1 2 2v2M21 17v2a2 2 0 0 1-2 2h-2M7 21H5a2 2 0 0 1-2-2v-2"/><path d="M7 8h8M7 12h10M7 16h6"/>',
    "nettoyer": '<path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z"/><path d="M19 3v4M17 5h4"/>',
    "alleger": '<path d="M8 3v3a2 2 0 0 1-2 2H3M21 8h-3a2 2 0 0 1-2-2V3M3 16h3a2 2 0 0 1 2 2v3M16 21v-3a2 2 0 0 1 2-2h3"/>',
    "motdepasse": '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
    "biffer": '<path d="M4 7h16M4 17h10"/><rect x="4" y="10" width="16" height="4" rx="1"/>',
    "archiver": '<rect x="2" y="3" width="20" height="5" rx="1"/><path d="M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8M10 12h4"/>',
    "comparer": '<rect x="3" y="4" width="7" height="16" rx="1"/><rect x="14" y="4" width="7" height="16" rx="1"/><path d="M10 10h4M12 8l2 2-2 2"/>',
    "lot": '<path d="M12 2l10 5-10 5L2 7z"/><path d="M2 12l10 5 10-5M2 17l10 5 10-5"/>',
    "ia": '<path d="M4 6h9M4 12h7M4 18h5"/><path d="M18 8l1.2 2.8L22 12l-2.8 1.2L18 16l-1.2-2.8L14 12l2.8-1.2z"/>',
    "enregistrer": '<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><path d="M17 21v-8H7v8M7 3v5h8"/>',
    "rechercher": '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>',
    "zoom_plus": '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3M8 11h6M11 8v6"/>',
    "zoom_moins": '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3M8 11h6"/>',
    "pivoter": '<path d="M21 12a9 9 0 1 1-3-6.7L21 8"/><path d="M21 3v5h-5"/>',
    "annuler": '<path d="M9 14L4 9l5-5"/><path d="M4 9h11a5 5 0 0 1 0 10h-3"/>',
    "surligner": '<path d="M9 11l-6 6v3h9l3-3"/><path d="M22 12l-4.6 4.6a2 2 0 0 1-2.8 0l-5.2-5.2a2 2 0 0 1 0-2.8L14 4"/>',
    "souligner": '<path d="M6 4v6a6 6 0 0 0 12 0V4"/><path d="M4 21h16"/>',
    "barrer": '<path d="M16 6a4 4 0 0 0-4-2c-3 0-4.5 1.6-4.5 3.5S9 10.5 12 11.5"/><path d="M4 12h16"/><path d="M8 18a4 4 0 0 0 4 2c3 0 4.5-1.6 4.5-3.5"/>',
    "copier": '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
    "parametres": '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M2 12h3M19 12h3M4.9 19.1L7 17M17 7l2.1-2.1"/>',
    "etoile": '<path d="M12 2l3 6.5 7 .8-5.2 4.8 1.4 7L12 17.6 5.8 21l1.4-7L2 9.3l7-.8z"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "synchro": '<path d="M21 12a9 9 0 0 1-15.5 6.2L3 16"/><path d="M3 21v-5h5"/><path d="M3 12a9 9 0 0 1 15.5-6.2L21 8"/><path d="M21 3v5h-5"/>',
    "retablir": '<path d="M15 14l5-5-5-5"/><path d="M20 9H9a5 5 0 0 0 0 10h3"/>',
    "couper": '<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M20 4L8.1 15.9M14.5 14.5L20 20M8.1 8.1L12 12"/>',
    "coller": '<rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>',
    "supprimer": '<path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/>',
    "tout": '<path d="M5 3h2M11 3h2M17 3h2M5 21h2M11 21h2M17 21h2M3 5v2M3 11v2M3 17v2M21 5v2M21 11v2M21 17v2"/><rect x="7" y="7" width="10" height="10" rx="1"/>',
    "aucun": '<path d="M5 3h2M11 3h2M17 3h2M5 21h2M11 21h2M17 21h2M3 5v2M3 11v2M3 17v2M21 5v2M21 11v2M21 17v2"/>',
    "recent": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "enregistrer_sous": '<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v4"/><path d="M7 3v5h8"/><path d="M14 20l6-6 2 2-6 6h-2z"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/>',
    "quitter": '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="M16 17l5-5-5-5M21 12H9"/>',
    "fermer_doc": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M9.5 12.5l5 5M14.5 12.5l-5 5"/>',
    "taille_reelle": '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 9v6M14 9l2 0v6"/>',
    "largeur": '<path d="M3 12h18M7 8l-4 4 4 4M17 8l4 4-4 4"/>',
    "plein_ecran": '<path d="M8 3H5a2 2 0 0 0-2 2v3M21 8V5a2 2 0 0 0-2-2h-3M3 16v3a2 2 0 0 0 2 2h3M16 21h3a2 2 0 0 0 2-2v-3"/>',
    "volet_gauche": '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 3v18"/>',
    "volet_droit": '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M15 3v18"/>',
    "barre": '<rect x="3" y="8" width="18" height="8" rx="2"/><path d="M7 12h2M11 12h2M15 12h2"/>',
    "onglet": '<path d="M3 7h7l2 2h9v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M15 14h4M17 12l2 2-2 2"/>',
    "aide": '<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.7.3-1 .9-1 1.7M12 17v.5"/>',
    "clavier": '<rect x="2" y="6" width="20" height="12" rx="2"/><path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M7 14h10"/>',
    "mise_a_jour": '<path d="M12 3v12M7 10l5 5 5-5"/><path d="M5 21h14"/>',
    "premiere": '<path d="M17 18l-6-6 6-6M7 6v12"/>',
    "precedente": '<path d="M15 18l-6-6 6-6"/>',
    "suivante": '<path d="M9 18l6-6-6-6"/>',
    "derniere": '<path d="M7 18l6-6-6-6M17 6v12"/>',
    "oeil": '<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    "oeil_barre": '<path d="M3 3l18 18"/><path d="M10.6 5.1A10 10 0 0 1 12 5c6.4 0 10 7 10 7a17 17 0 0 1-3.2 4.2M6.6 6.6C3.9 8.4 2 12 2 12s3.6 7 10 7a9.7 9.7 0 0 0 5.4-1.6"/><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"/>',
    "fermer": '<path d="M6 6l12 12M18 6L6 18"/>',
}

LOGO = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><rect width="24" height="24" rx="5" fill="#c9252d"/>'
        '<path d="M7.5 3h6.8L18 6.7V19a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 6 19V4.5A1.5 1.5 0 0 1 7.5 3z" fill="#fff"/>'
        '<path d="M14.3 3v3.7H18z" fill="#f4b9bc"/><path d="M8.3 9.2h5M8.3 11.4h7.4" stroke="#c9252d" stroke-width="1.1" stroke-linecap="round"/>'
        '<rect x="4" y="13.6" width="13.6" height="5.4" rx="1.2" fill="#8f1218"/>'
        '<text x="10.8" y="17.85" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" font-size="4.6" font-weight="800" fill="#fff">PDF</text>'
        '<path d="M19.5 9.5l1.6 1.6-4.8 4.8-2.1.5.5-2.1z" fill="#fff" stroke="#8f1218" stroke-width=".7" stroke-linejoin="round"/></svg>')

_cache = {}


def _svg_icon(svg, taille=48):
    r = QSvgRenderer(QByteArray(svg.encode()))
    pm = QPixmap(QSize(taille, taille))
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    r.render(p)
    p.end()
    return QIcon(pm)


def icone(nom, couleur="#333333", taille=48, rempli=False):
    cle = (nom, couleur, taille, rempli)
    if cle not in _cache:
        fill = couleur if rempli else "none"
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="{fill}" stroke="{couleur}" '
               f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{TRAITS[nom]}</svg>')
        _cache[cle] = _svg_icon(svg, taille)
    return _cache[cle]


def logo(taille=64):
    return _svg_icon(LOGO, taille)
