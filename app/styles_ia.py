"""Styles prets a l'emploi pour la retouche d'image par l'IA (Gemini) : un clic remplit la consigne,
que l'on peut completer avant l'envoi. Aucun style au nom d'un studio, d'un artiste ou d'une marque.

Chaque style : (groupe, nom, consigne). La consigne decrit le rendu voulu ; l'intensite et « garder les visages
et le cadrage » sont ajoutes au moment de l'envoi. Les styles personnels (params « ia_styles_perso ») suivent sur
vos autres postes comme les autres reglages.
"""
from .langue import _

DETOURER = "detourer"            # style special : fond rendu transparent apres coup


def styles():
    return [
        (_("Epoques"), _("Années 1900"), _("Transforme la photo comme un tirage des années 1900 : sépia, grain fin, léger vignettage, contraste doux d'une plaque de verre.")),
        (_("Epoques"), _("Années 1950"), _("Donne à la photo l'aspect d'une diapositive couleur des années 1950 : couleurs vives et denses, rouges profonds, léger grain.")),
        (_("Epoques"), _("Années 1970"), _("Donne à la photo l'aspect d'une pellicule des années 1970 : tons chauds, couleurs un peu passées, grain visible, noirs légèrement délavés.")),
        (_("Epoques"), _("Années 1980"), _("Donne à la photo l'aspect d'une photo des années 1980 au flash : couleurs saturées, légère surexposition, contraste fort.")),
        (_("Epoques"), _("Années 1990"), _("Donne à la photo l'aspect d'un appareil jetable des années 1990 : couleurs un peu froides, flash direct, grain, date orange dans le coin.")),
        (_("Epoques"), _("Années 2000"), _("Donne à la photo l'aspect d'un des premiers appareils numériques des années 2000 : bruit numérique, netteté moyenne, couleurs un peu criardes.")),
        (_("Photo"), _("Noir et blanc contrasté"), _("Convertis en noir et blanc très contrasté, noirs profonds, blancs francs, comme un tirage argentique.")),
        (_("Photo"), _("Noir et blanc doux"), _("Convertis en noir et blanc doux et lumineux, gris nuancés, peu de contraste.")),
        (_("Photo"), _("Sépia"), _("Applique un virage sépia chaleureux, comme une photo ancienne bien conservée.")),
        (_("Photo"), _("Polaroid"), _("Donne l'aspect d'une photo instantanée : couleurs douces, légère dominante, cadre blanc avec une bande plus large en bas.")),
        (_("Photo"), _("Cinéma"), _("Etalonnage de cinéma : ombres bleu-vert, peaux et lumières orangées, contraste maîtrisé.")),
        (_("Photo"), _("Film noir"), _("Noir et blanc de film noir : clair-obscur marqué, ombres profondes, ambiance dramatique.")),
        (_("Photo"), _("HDR"), _("Rendu HDR naturel : détails visibles dans les ombres et les hautes lumières, sans effet exagéré.")),
        (_("Photo"), _("Lumière de fin de journée"), _("Lumière dorée et rasante de fin de journée, ombres longues et chaudes.")),
        (_("Photo"), _("Studio"), _("Rendu de photo de studio : éclairage doux et uniforme, fond neutre gris clair.")),
        (_("Dessin"), _("Fusain"), _("Transforme en dessin au fusain sur papier : traits charbonneux, estompe, noirs veloutés, grain du papier.")),
        (_("Dessin"), _("Crayon graphite"), _("Transforme en dessin au crayon graphite : hachures fines, gris argentés, papier blanc.")),
        (_("Dessin"), _("Encre et plume"), _("Transforme en dessin à l'encre et à la plume : traits noirs nets, hachures croisées, aucun gris.")),
        (_("Dessin"), _("Croquis d'architecte"), _("Transforme en croquis d'architecte : traits fins à main levée, lavis léger, quelques lignes de construction.")),
        (_("Dessin"), _("Pastel"), _("Transforme en dessin au pastel sec : couleurs tendres, matière poudreuse, papier teinté.")),
        (_("Dessin"), _("Sanguine"), _("Transforme en dessin à la sanguine : tons brun-rouge sur papier crème, comme une étude ancienne.")),
        (_("Peinture"), _("Aquarelle"), _("Transforme en aquarelle : couleurs transparentes, fondus, bords irréguliers, papier visible.")),
        (_("Peinture"), _("Huile"), _("Transforme en peinture à l'huile : touches épaisses visibles, couleurs riches, texture de toile.")),
        (_("Peinture"), _("Impressionniste"), _("Transforme en peinture impressionniste : petites touches de couleur pure, lumière vibrante.")),
        (_("Peinture"), _("Pointilliste"), _("Transforme en peinture pointilliste : image faite de petits points de couleur juxtaposés.")),
        (_("Peinture"), _("Gouache"), _("Transforme en gouache : aplats mats et opaques, couleurs franches.")),
        (_("Peinture"), _("Art naïf"), _("Transforme en peinture naïve : formes simples, couleurs vives, perspective libre, détails minutieux.")),
        (_("Illustration"), _("Bande dessinée ligne claire"), _("Transforme en case de bande dessinée ligne claire : contours noirs réguliers, aplats de couleur, pas d'ombres dégradées.")),
        (_("Illustration"), _("Cartoon"), _("Transforme en dessin cartoon : formes arrondies et exagérées, couleurs vives, contours épais.")),
        (_("Illustration"), _("Manga"), _("Transforme en illustration manga : grands yeux expressifs, trames, contours fins, noir et blanc.")),
        (_("Illustration"), _("Comics"), _("Transforme en illustration de comics : encrage puissant, ombres franches, couleurs saturées, points de trame.")),
        (_("Illustration"), _("Dessin animé 3D"), _("Transforme en image de dessin animé en 3D : volumes doux, matières lisses, éclairage chaleureux.")),
        (_("Illustration"), _("Livre pour enfants"), _("Transforme en illustration de livre pour enfants : formes douces, couleurs pastel, ambiance tendre.")),
        (_("Illustration"), _("Affiche rétro"), _("Transforme en affiche rétro : aplats de couleurs limitées, formes simplifiées, papier vieilli.")),
        (_("Illustration"), _("Pop art"), _("Transforme en pop art : couleurs primaires éclatantes, contours noirs, trame de points.")),
        (_("Illustration"), _("Vitrail"), _("Transforme en vitrail : morceaux de verre colorés lumineux séparés par des plombs noirs.")),
        (_("Illustration"), _("Mosaïque"), _("Transforme en mosaïque : petites tesselles de pierre ou de verre, joints visibles.")),
        (_("Graphique"), _("Pixel art"), _("Transforme en pixel art : gros pixels visibles, palette réduite, contours nets.")),
        (_("Graphique"), _("Low poly"), _("Transforme en image low poly : surfaces faites de triangles à facettes, couleurs unies.")),
        (_("Graphique"), _("Isométrique"), _("Redessine en vue isométrique simplifiée, comme une illustration technique en 3D.")),
        (_("Graphique"), _("Plan technique"), _("Transforme en plan technique : traits blancs fins sur fond bleu, cotes et lignes de construction.")),
        (_("Graphique"), _("Néon"), _("Transforme en enseigne au néon : contours lumineux colorés sur fond sombre, halo.")),
        (_("Graphique"), _("Papier découpé"), _("Transforme en illustration de papier découpé en couches superposées, ombres portées douces.")),
        (_("Graphique"), _("Origami"), _("Transforme les sujets en origami de papier plié, plis nets, papier mat.")),
        (_("Graphique"), _("Gravure ancienne"), _("Transforme en gravure ancienne : tailles-douces, hachures régulières, encre noire sur papier ivoire.")),
        (_("Pratiques"), _("Détourer (fond transparent)"), DETOURER),
        (_("Pratiques"), _("Fond blanc propre"), _("Remplace tout l'arrière-plan par un fond blanc uni et propre ; le sujet reste identique, contours nets.")),
        (_("Pratiques"), _("Agrandir et rendre net"), _("Rends l'image plus nette et plus détaillée, sans changer son contenu ni ses couleurs.")),
        (_("Pratiques"), _("Coloriser"), _("Colorise cette photo noir et blanc avec des couleurs naturelles et réalistes.")),
        (_("Pratiques"), _("Restaurer une vieille photo"), _("Restaure cette vieille photo : retire rayures, taches et plis, corrige la décoloration, garde son caractère.")),
        (_("Pratiques"), _("Effacer un élément"), _("Efface l'élément entouré (zone 1) et reconstitue naturellement ce qu'il y avait derrière.")),
        (_("Pratiques"), _("Remplacer le fond"), _("Remplace l'arrière-plan par : (décrivez le nouveau fond). Le sujet reste identique.")),
        (_("Pratiques"), _("Prolonger l'image"), _("Prolonge l'image au-delà de ses bords de façon cohérente, sans changer le centre.")),
    ]


def consigne_complete(texte, intensite="marquee", garder=True, zones=None):
    """Texte final envoye a Gemini : consigne + intensite + fidelite + zones + format de reponse."""
    morceaux = [texte.strip()]
    if intensite == "legere":
        morceaux.append(_("Effet léger et subtil : l'image doit rester proche de l'original."))
    if garder:
        morceaux.append(_("Garde exactement le cadrage, la composition, les proportions et les visages (traits, expressions)."))
    if zones:
        lignes = [_("La deuxième image montre des zones entourées et numérotées. Ne modifie que ces zones, comme suit :")]
        for i, z in enumerate(zones, 1):
            lignes.append(f"  {_('zone')} {i} ({z['couleur_nom']}) : {z['consigne'] or texte.strip()}")
        lignes.append(_("Le reste de l'image doit rester strictement identique."))
        morceaux.append("\n".join(lignes))
    morceaux.append(_("Renvoie seulement l'image modifiée (la première image, sans les contours des zones), même cadrage."))
    return "\n\n".join(m for m in morceaux if m)
