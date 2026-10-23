from .langue import _
"""Catalogue des outils, par famille (ordre et couleurs de la maquette validee)."""

FAMILLES = [
    ("creer", _('Créer et assembler'), "#c9252d", "#fcebec"),
    ("modifier", _('Modifier'), "#b0186b", "#fbe8f2"),
    ("annoter", _('Annoter et signer'), "#6d3fc6", "#f1ebfc"),
    ("scans", _('Scans et OCR'), "#2a7a3b", "#e7f4ea"),
    ("formulaires", _('Formulaires'), "#a35c00", "#fdf1e2"),
    ("comparer", _('Comparer et automatiser'), "#0b7a80", "#e2f4f4"),
    ("ia", _('Assistant IA'), "#0b5e63", "#e2f0f0"),
    ("optimiser", _('Optimiser et protéger'), "#1462c2", "#e6f0fc"),
]

# (id, famille, icone, titre, sous-titre, bulle d'aide, disponible en 0.1)
OUTILS = [
    ("creer", "creer", "creer", _('Créer un PDF'), _('Page vierge ou images'),
     _("Créer un PDF à partir d'une page vierge ou d'images. Word, scanner et presse-papiers arrivent ensuite."), True),
    ("combiner", "creer", "combiner", _('Combiner des fichiers'), _('Fusionner plusieurs fichiers en un seul PDF'),
     _("Assembler plusieurs fichiers en un seul PDF, dans l'ordre de votre choix."), True),
    ("organiser", "creer", "organiser", _('Organiser les pages'), _('Réordonner, pivoter, extraire, supprimer'),
     _('Clic droit sur une vignette : pivoter, supprimer, extraire. Glissez les vignettes pour réordonner.'), True),
    ("exporter", "creer", "exporter", _('Exporter'), _('Vers Word, JPG, PNG ou texte'),
     _('Convertir le PDF en document Word (.docx), en images JPG ou PNG, ou en texte.'), True),
    ("imprimer", "creer", "imprimer", _('Imprimer'), _("Un ou plusieurs documents d'un coup"),
     _("Imprimer le document ouvert, ou plusieurs PDF d'un coup sur la même imprimante."), True),
    ("modifier", "modifier", "modifier", _('Modifier texte et images'), _("Corriger en gardant la police d'origine"),
     _("Cliquez sur une ligne pour la corriger : PhilPDF réutilise les lettres d'origine du fichier."), True),
    ("remplacer", "modifier", "remplacer", _('Rechercher et remplacer'), _("Une par une ou tout d'un coup"),
     _("Comme dans Word : nombre d'occurrences, casse et accents au choix, police conservée."), True),
    ("entete", "modifier", "entete", _('En-tête et pied de page'), _('Numéros de page, dates'),
     _('Ajouter numéros de page, date ou numérotation Bates.'), True),
    ("filigrane", "modifier", "filigrane", _('Filigrane et fond'), _('Modèles prêts ou les vôtres, synchronisés'),
     _('Ajouter (Copie, Confidentiel, Brouillon, Payé, date automatique, vos modèles texte ou image) ou retirer un filigrane.'), True),
    ("commentaires", "annoter", "commentaire", _('Commentaires'), _('Notes, surligner, barrer'),
     _('Sélectionnez du texte : la barre rapide propose surligner, souligner, barrer, note.'), True),
    ("tampons", "annoter", "tampon", _('Tampons'), _('"Reçu le", "Payé", vos tampons'),
     _("Tampons prêts à l'emploi (Reçu, Validé, Payé...) avec la date, ou les vôtres importés d'une image ou d'un PDF. Sauvegardés sur votre Drive."), True),
    ("remplir_signer", "annoter", "signer", _('Remplir et signer'), _('Signature manuscrite, coches, dates'),
     _('Vos signatures (dessinées ou importées), posées puis déplaçables et redimensionnables. Sauvegardées sur votre Drive.'), True),
    ("certificat", "annoter", "certificat", _('Signature numérique'), _('Certificat, reconnue par Acrobat'),
     _("Signature PAdES avec votre identité exportée d'Acrobat (.pfx)."), False),
    ("numeriser", "scans", "numeriser", _('Numériser'), _('Depuis le scanner'),
     _('Numériser avec choix du mode, de la résolution et estimation de la taille.'), True),
    ("ocr", "scans", "ocr", _('Reconnaître le texte'), _('OCR français, texte recherchable'),
     _('Redresse les pages, nettoie le scan et ajoute le texte reconnu (nécessite Tesseract).'), True),
    ("nettoyer", "scans", "nettoyer", _('Nettoyer un scan'), _('Redresser, effacer traits et taches'),
     _('Remettre au format, redresser, effacer traits et taches, noir et blanc net.'), True),
    ("formulaire", "formulaires", "formulaire", _('Préparer un formulaire'), _('Champs détectés ou créés'),
     _('Détecter ou créer des champs : texte, case, liste.'), False),
    ("champ_signature", "formulaires", "champ_signature", _('Champ de signature'), _("Faire signer quelqu'un d'autre"),
     _('Poser un emplacement de signature que le destinataire remplira dans Acrobat ou PhilPDF.'), False),
    ("comparer", "comparer", "comparer", _('Comparer deux fichiers'), _('Différences surlignées, sans IA'),
     _('Deux versions côte à côte, différences de texte surlignées. Sans IA, tout reste sur votre PC.'), False),
    ("lot", "comparer", "lot", _('Traitement par lot'), _('Une action sur tout un dossier'),
     _('OCR, allègement, tampon ou archivage sur tout un dossier.'), False),
    ("ia_resume", "ia", "ia", _("Résumer avec l'IA"), _('Résumé, points clefs, remise en page'),
     _('Envoie le texte à Claude ou Gemini avec votre clef API, seulement quand vous cliquez.'), False),
    ("alleger", "optimiser", "alleger", _('Alléger le fichier'), _('Même rendu, poids réduit'),
     _('Recompresse les images trop lourdes et nettoie le fichier.'), True),
    ("motdepasse", "optimiser", "motdepasse", _('Mot de passe'), _('Ouverture, impression, copie'),
     _("Protéger l'ouverture, interdire l'impression ou la copie."), True),
    ("biffer", "optimiser", "biffer", _('Biffer'), _('Effacer pour de vrai un passage'),
     _('Sélectionnez un passage : il est supprimé du fichier, pas seulement masqué.'), True),
    ("archiver", "optimiser", "archiver", _('Archiver (PDF/A)'), _('Format exigé par les administrations'),
     _("Conversion au format d'archivage PDF/A."), False),
]


def famille(fid):
    for f in FAMILLES:
        if f[0] == fid:
            return f
    return FAMILLES[0]


def outil(oid):
    for o in OUTILS:
        if o[0] == oid:
            return o
    return None
