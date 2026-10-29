from .langue import _
"""Catalogue des outils, par famille (ordre et couleurs de la maquette validee)."""

FAMILLES = [
    ("creer", _('Créer et assembler'), "#c9252d", "#fcebec"),
    ("modifier", _('Modifier'), "#b0186b", "#fbe8f2"),
    ("annoter", _('Annoter et signer'), "#6d3fc6", "#f1ebfc"),
    ("scans", _('Scans et OCR'), "#2a7a3b", "#e7f4ea"),
    ("formulaires", _('Formulaires'), "#a35c00", "#fdf1e2"),
    ("comparer", _('Comparer et automatiser'), "#0b7a80", "#e2f4f4"),
    ("ia", _('Assistant IA'), "#4338ca", "#ecebfd"),
    ("optimiser", _('Optimiser et protéger'), "#1462c2", "#e6f0fc"),
]

# (id, famille, icone, titre, sous-titre, bulle d'aide, disponible en 0.1)
OUTILS = [
    ("creer", "creer", "creer", _('Créer un PDF'), _('Vierge, images, Word, Excel, presse-papiers'),
     _("Créer un PDF : page vierge, images, fichier Word / Excel / PowerPoint (polices intégrées), presse-papiers ou "
       "capture d'écran. Vous pouvez aussi glisser un fichier Office sur PhilPDF."), True),
    ("imprimante", "creer", "imprimer", _('Imprimante PhilPDF'), _('Imprimer vers PDF depuis tout logiciel'),
     _("Comme l'imprimante Adobe PDF : Imprimer › PhilPDF depuis Word, un navigateur... ouvre le PDF dans PhilPDF, "
       "polices intégrées. Qualité, dossier de sortie et affichage réglables."), True),
    ("courriel", "creer", "courriel", _('Envoyer par e-mail'), _('Tel quel, allégé, figé ou protégé'),
     _("Joindre le PDF à un e-mail : votre logiciel de messagerie (PDF déjà joint), votre adresse Orange, Gmail, "
       "Free... (envoi direct ou brouillon dans votre messagerie web) ; poids de chaque version affiché."), True),
    ("combiner", "creer", "combiner", _('Combiner des fichiers'), _('Fusionner plusieurs fichiers en un seul PDF'),
     _("Assembler plusieurs fichiers en un seul PDF, dans l'ordre de votre choix."), True),
    ("organiser", "creer", "organiser", _('Organiser les pages'), _('Réordonner, pivoter, extraire, supprimer'),
     _('Clic droit sur une vignette : pivoter, supprimer, extraire. Glissez les vignettes pour réordonner.'), True),
    ("fractionner", "creer", "fractionner", _('Fractionner'), _('Par pages, signets ou taille'),
     _("Découper le PDF en plusieurs fichiers : toutes les N pages, à chaque signet, sous une taille maximale "
       "(pour un envoi par e-mail) ou selon vos plages. La liste des fichiers s'affiche avant de les créer."), True),
    ("exporter", "creer", "exporter", _('Exporter'), _('Vers Word, JPG, PNG ou texte'),
     _('Convertir le PDF en document Word (.docx), en images JPG ou PNG, ou en texte.'), True),
    ("excel", "creer", "excel", _('Tableaux vers Excel'), _('Relevés, factures, bordereaux'),
     _("Repère les tableaux du PDF, vous montre exactement ce qui sera mis dans chaque cellule (nombres et dates "
       "reconnus), puis crée le fichier Excel. Un tableau manquant se trace à la souris."), True),
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
    ("mesure", "annoter", "mesure", _('Mesurer'), _('Distances, périmètres, surfaces'),
     _("Mesurer sur un plan ou le cadastre : réglez l'échelle de la page (1:100, 1 cm = 1 m, ou une cote connue), "
       "puis cliquez. Les mesures restent dans le PDF, lisibles dans Acrobat, et s'exportent vers Excel."), True),
    ("commentaires", "annoter", "commentaire", _('Commentaires'), _('Formes, flèches, dessin, notes, liste'),
     _("Rectangle (aussi arrondi), ellipse, ligne, flèche, dessin à main levée, note, texte libre ; couleur, épaisseur "
       "et type de stylo. Liste des commentaires à droite : un clic va dessus. Pour surligner : sélectionnez du texte."), True),
    ("paraphe", "annoter", "paraphe", _('Parapher'), _('Initiales sur toutes les pages'),
     _("Vos initiales (dans la police de votre choix) ou votre tampon « paraphe », posées en un clic au même "
       "endroit de chaque page ; toutes sauf la dernière si elle est signée. Aperçu avant de valider."), True),
    ("tampons", "annoter", "tampon", _('Tampons'), _('"Reçu le", "Payé", vos tampons'),
     _("Tampons prêts à l'emploi (Reçu, Validé, Payé...) avec la date, ou les vôtres importés d'une image ou d'un PDF. Sauvegardés sur votre Drive."), True),
    ("remplir_signer", "annoter", "signer", _('Remplir et signer'), _('Signature manuscrite, coches, dates'),
     _('Vos signatures (dessinées ou importées), posées puis déplaçables et redimensionnables. Sauvegardées sur votre Drive.'), True),
    ("certificat", "annoter", "certificat", _('Signature numérique'), _('Certificat, reconnue par Acrobat'),
     _("Signature PAdES avec votre identité exportée d'Acrobat (.pfx) ou créée dans PhilPDF ; vérification des signatures reçues."), True),
    ("numeriser", "scans", "numeriser", _('Numériser'), _('Depuis le scanner'),
     _('Numériser avec choix du mode, de la résolution et estimation de la taille.'), True),
    ("ocr", "scans", "ocr", _('Reconnaître le texte'), _('OCR français, texte recherchable'),
     _('Redresse les pages, nettoie le scan et ajoute le texte reconnu (nécessite Tesseract).'), True),
    ("nettoyer", "scans", "nettoyer", _('Nettoyer un scan'), _('Redresser, effacer traits et taches'),
     _('Remettre au format, redresser, effacer traits et taches, noir et blanc net.'), True),
    ("formulaire", "formulaires", "formulaire", _('Créer un formulaire'), _('Champs détectés ou tracés'),
     _("Repère les zones à remplir (pointillés, traits, cases, cadres) et en fait de vrais champs, remplissables "
       "ici, dans Acrobat ou tout lecteur PDF. Tracez texte, case, radio, liste, date, montant ou signature ; "
       "double-clic : format, date automatique, calculs, listes dépendantes, champs affichés selon une case."), True),
    ("champ_signature", "formulaires", "champ_signature", _('Champ de signature'), _("Faire signer quelqu'un d'autre"),
     _('Poser un emplacement de signature que le destinataire remplira dans Acrobat ou PhilPDF.'), True),
    ("comparer", "comparer", "comparer", _('Comparer deux fichiers'), _('Différences surlignées, sans IA'),
     _('Deux versions côte à côte, différences de texte surlignées. Sans IA, tout reste sur votre PC.'), True),
    ("lot", "comparer", "lot", _('Traitement par lot'), _('Une action sur tout un dossier'),
     _("OCR, allègement, filigrane, numérotation Bates, PDF/A et renommage sur tout un dossier ; vous voyez les "
       "noms des fichiers produits avant de lancer, les originaux restent intacts."), True),
    ("ia_resume", "ia", "ia", _("Résumer avec l'IA"), _('Résumé, points clefs, échéances'),
     _('Envoie le texte à Claude ou Gemini avec votre clef API, seulement quand vous cliquez.'), True),
    ("ia_classer", "ia", "archiver", _('Renommer et classer'), _('Nom et dossier proposés, appris'),
     _("L'IA lit le document et propose un nom (date, expéditeur, objet) et le dossier où le ranger ; "
       "PhilPDF retient vos choix pour chaque expéditeur, sur tous vos postes."), True),
    ("ia_comparer", "ia", "comparer_ia", _('Comparer avec explication'), _('Différences surlignées et expliquées'),
     _("Deux versions d'un document : différences surlignées, puis expliquées en français par l'IA."), True),
    ("ia_traduire", "ia", "langue", _('Traduire le document'), _('Mise en page conservée'),
     _("Traduit le texte de chaque page et le remet à sa place, dans un nouveau fichier (ex. « Contrat (EN).pdf »). "
       "Si la traduction est plus longue, sa taille est réduite pour tenir."), True),
    ("ia_reformuler", "ia", "modifier", _('Corriger ou reformuler'), _('Un paragraphe, mise en page gardée'),
     _("Mode Modifier : cliquez sur un paragraphe puis « ✦ IA » : corriger les fautes, reformuler, plus formel, plus "
       "court ou votre consigne. Le résultat s'affiche dans la zone ; vous le relisez avant de valider."), True),
    ("ia_mise_en_page", "ia", "nettoyer", _('Remettre en page un scan'), _('Document propre, texte net'),
     _("L'IA relit chaque page scannée et la recompose proprement (titres, paragraphes, listes, tableaux) dans un "
       "nouveau document A4 ; le scan d'origine reste intact."), True),
    ("ia_donnees", "ia", "excel", _('Extraire les données'), _('Facture, relevé, courrier → tableau'),
     _("Montants, dates, numéros, lignes d'une facture ou d'un relevé : l'IA les range dans un tableau que vous "
       "vérifiez, puis copiez ou enregistrez en Excel. Vos propres champs possibles."), True),
    ("ocr_ia", "ia", "ocr", _('OCR IA comparé'), _("Deux lectures, vous validez, PhilPDF apprend"),
     _("Compare la lecture de Tesseract et celle de l'IA ; vos corrections validées améliorent les lectures suivantes, sur tous vos postes."), True),
    ("ia_recherche", "ia", "rechercher", _('Rechercher dans tous mes PDF'), _('NAS, Drive, dossiers'),
     _("Une question en français (« le courrier de l'URSSAF du dernier trimestre ») et PhilPDF retrouve les PDF "
       "correspondants, sur ce PC, le NAS ou un Drive. Seule la question est envoyée à l'IA."), True),
    ("alleger", "optimiser", "alleger", _('Alléger le fichier'), _('Même rendu, poids réduit'),
     _('Recompresse les images trop lourdes et nettoie le fichier.'), True),
    ("motdepasse", "optimiser", "motdepasse", _('Mot de passe'), _('Ouverture, impression, copie'),
     _("Protéger l'ouverture, interdire l'impression ou la copie."), True),
    ("biffer", "optimiser", "biffer", _('Biffer'), _('Effacer pour de vrai un passage'),
     _('Sélectionnez un passage : il est supprimé du fichier, pas seulement masqué.'), True),
    ("archiver", "optimiser", "archiver", _('Archiver (PDF/A)'), _('Format exigé par les administrations'),
     _("Conversion au format d'archivage PDF/A-2b : polices intégrées, couleurs, métadonnées ; PhilPDF montre ce "
       "qui change et vérifie le résultat avant d'enregistrer."), True),
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
