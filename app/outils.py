"""Catalogue des outils, par famille (ordre et couleurs de la maquette validee)."""

FAMILLES = [
    ("creer", "Créer et assembler", "#c9252d", "#fcebec"),
    ("modifier", "Modifier", "#b0186b", "#fbe8f2"),
    ("annoter", "Annoter et signer", "#6d3fc6", "#f1ebfc"),
    ("scans", "Scans et OCR", "#2a7a3b", "#e7f4ea"),
    ("formulaires", "Formulaires", "#a35c00", "#fdf1e2"),
    ("comparer", "Comparer et automatiser", "#0b7a80", "#e2f4f4"),
    ("ia", "Assistant IA", "#0b5e63", "#e2f0f0"),
    ("optimiser", "Optimiser et protéger", "#1462c2", "#e6f0fc"),
]

# (id, famille, icone, titre, sous-titre, bulle d'aide, disponible en 0.1)
OUTILS = [
    ("creer", "creer", "creer", "Créer un PDF", "Page vierge ou images",
     "Créer un PDF à partir d'une page vierge ou d'images. Word, scanner et presse-papiers arrivent ensuite.", True),
    ("combiner", "creer", "combiner", "Combiner des fichiers", "Fusionner plusieurs fichiers en un seul PDF",
     "Assembler plusieurs fichiers en un seul PDF, dans l'ordre de votre choix.", True),
    ("organiser", "creer", "organiser", "Organiser les pages", "Réordonner, pivoter, extraire, supprimer",
     "Clic droit sur une vignette : pivoter, supprimer, extraire. Glissez les vignettes pour réordonner.", True),
    ("exporter", "creer", "exporter", "Exporter", "Vers Word, JPG, PNG ou texte",
     "Convertir le PDF en document Word (.docx), en images JPG ou PNG, ou en texte.", True),
    ("imprimer", "creer", "imprimer", "Imprimer", "Un ou plusieurs documents d'un coup",
     "Imprimer le document ouvert, ou plusieurs PDF d'un coup sur la même imprimante.", True),
    ("modifier", "modifier", "modifier", "Modifier texte et images", "Corriger en gardant la police d'origine",
     "Cliquez sur une ligne pour la corriger : PhilPDF réutilise les lettres d'origine du fichier.", True),
    ("remplacer", "modifier", "remplacer", "Rechercher et remplacer", "Une par une ou tout d'un coup",
     "Comme dans Word : nombre d'occurrences, casse et accents au choix, police conservée.", True),
    ("entete", "modifier", "entete", "En-tête et pied de page", "Numéros de page, dates",
     "Ajouter numéros de page, date ou numérotation Bates.", True),
    ("filigrane", "modifier", "filigrane", "Filigrane et fond", "Modèles prêts ou les vôtres, synchronisés",
     "Copie, Confidentiel, Brouillon, Payé, date automatique, ou vos propres modèles.", True),
    ("commentaires", "annoter", "commentaire", "Commentaires", "Notes, surligner, barrer",
     "Sélectionnez du texte : la barre rapide propose surligner, souligner, barrer, note.", True),
    ("tampons", "annoter", "tampon", "Tampons", "\"Reçu le\", \"Payé\", vos tampons",
     "Tampons prêts à l'emploi (Reçu, Validé, Payé...) avec la date, ou les vôtres importés d'une image ou d'un PDF. Sauvegardés sur votre Drive.", True),
    ("remplir_signer", "annoter", "signer", "Remplir et signer", "Signature manuscrite, coches, dates",
     "Vos signatures (dessinées ou importées), posées puis déplaçables et redimensionnables. Sauvegardées sur votre Drive.", True),
    ("certificat", "annoter", "certificat", "Signature numérique", "Certificat, reconnue par Acrobat",
     "Signature PAdES avec votre identité exportée d'Acrobat (.pfx).", False),
    ("numeriser", "scans", "numeriser", "Numériser", "Depuis le scanner",
     "Numériser avec choix du mode, de la résolution et estimation de la taille.", True),
    ("ocr", "scans", "ocr", "Reconnaître le texte", "OCR français, texte recherchable",
     "Redresse les pages, nettoie le scan et ajoute le texte reconnu (nécessite Tesseract).", True),
    ("nettoyer", "scans", "nettoyer", "Nettoyer un scan", "Redresser, effacer traits et taches",
     "Remettre au format, redresser, effacer traits et taches, noir et blanc net.", True),
    ("formulaire", "formulaires", "formulaire", "Préparer un formulaire", "Champs détectés ou créés",
     "Détecter ou créer des champs : texte, case, liste.", False),
    ("champ_signature", "formulaires", "champ_signature", "Champ de signature", "Faire signer quelqu'un d'autre",
     "Poser un emplacement de signature que le destinataire remplira dans Acrobat ou PhilPDF.", False),
    ("comparer", "comparer", "comparer", "Comparer deux fichiers", "Différences surlignées, sans IA",
     "Deux versions côte à côte, différences de texte surlignées. Sans IA, tout reste sur votre PC.", False),
    ("lot", "comparer", "lot", "Traitement par lot", "Une action sur tout un dossier",
     "OCR, allègement, tampon ou archivage sur tout un dossier.", False),
    ("ia_resume", "ia", "ia", "Résumer avec l'IA", "Résumé, points clefs, remise en page",
     "Envoie le texte à Claude ou Gemini avec votre clef API, seulement quand vous cliquez.", False),
    ("alleger", "optimiser", "alleger", "Alléger le fichier", "Même rendu, poids réduit",
     "Recompresse les images trop lourdes et nettoie le fichier.", True),
    ("motdepasse", "optimiser", "motdepasse", "Mot de passe", "Ouverture, impression, copie",
     "Protéger l'ouverture, interdire l'impression ou la copie.", True),
    ("biffer", "optimiser", "biffer", "Biffer", "Effacer pour de vrai un passage",
     "Sélectionnez un passage : il est supprimé du fichier, pas seulement masqué.", True),
    ("archiver", "optimiser", "archiver", "Archiver (PDF/A)", "Format exigé par les administrations",
     "Conversion au format d'archivage PDF/A.", False),
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
