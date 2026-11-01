PHILPDF - NOUVEAUTES
====================

Ce fichier dit ce qui a change a chaque version (le plus recent en haut).
PhilPDF Windows et Linux ont un numero (0.9.x), PhilPDF Android a le sien (1.x) :
chacun n'est republie que lorsque son propre code change.
Dans PhilPDF : Aide > Nouveautes (Windows, Linux), Accueil > Aide > Nouveautes (Android).


ANDROID
-------

1.7.1
- Certificats de signature (identites numeriques) de vos postes : ceux qui ne sont pas encore sur le telephone
  sont montres dans le volet Signer (et pourquoi : a recuperer, ou ranges dans le magasin de Windows) ; la
  phrase secrete peut etre retenue sur le telephone : les certificats ajoutes sous Windows arrivent ensuite tout seuls.

1.7.0
- Regles des champs de formulaire, comme PhilPDF Windows (et compatibles Acrobat : meme JavaScript) :
  type devine d'apres le libelle a la creation (Date, Montant, Quantite, Telephone, Code postal, E-mail,
  N° Secu, IBAN, SIRET, RPPS, Nom en majuscules ; « Signature » devient un champ de signature).
- Appui long sur un champ > « Proprietes » : format (date, heure, nombre, montant, pourcentage, telephone, code
  postal, masque), majuscules, controle (e-mail, N° Secu, IBAN, SIRET, RPPS), valeur automatique (date ou heure au
  toucher), plage permise, calcul (somme, produit, moyenne, min, max, formule, copie, age, ecart en jours,
  date + jours), choix et liste dependante d'un autre champ, afficher d'autres champs selon une case ou une
  valeur, messages d'aide.
- Remplir : ce qui est attendu est dit sous la saisie, clavier adapte (chiffres, e-mail), « Aujourd'hui » /
  « Maintenant » pour les dates ; saisie refusee expliquee (« IBAN incorrect »...) ; montants mis en forme
  (1.234,50 €) ; calculs, listes dependantes et champs affiches mis a jour aussitot.
- Mes tampons : rangez-les comme vous voulez (« Ranger » : fleches, modifier le texte et la categorie, supprimer),
  favoris (etoile) en premier, categories repliables ; un tampon personnalise se garde dans la liste.

1.6.0
- Volet Modifier regroupe : Lire, Modifier le texte, Annoter (surligner, souligner, barrer, note, dessin,
  rectangle, ellipse, fleche), Effacer, Formulaire ; les outils d'un groupe s'affichent sous son bouton.
- Effacer : « Gomme » efface les annotations touchees ou frottees ; « Effacer une zone de la page » retire le
  texte, les images et les traits de la zone tracee (comme la retouche de Windows).
- Formulaire : liste deroulante (choix un par ligne, ou listes toutes pretes : Oui/Non, Madame/Monsieur, mois,
  jours) ; champ de signature vide, a signer ensuite avec un certificat en le touchant. Les champs sont
  montres en bleu clair a l'ecran (comme Acrobat), les champs de signature vides en pointilles orange.
- Signature numerique : choix du certificat dans la fenetre de signature ; un champ de signature touche est signe.
- Signer : tampons, signatures et paraphes de vos postes avec favoris (etoile), categories repliables et
  « Ranger » (changer l'ordre) ; paraphe de vos postes sur toutes les pages ; tampons centres (« VALIDE » seul).

1.5.0
- Signature numerique (volet Signer) : signer avec un certificat (.pfx), reconnue par Acrobat comme sous Windows ;
  on trace le cadre sur la page, on tape le mot de passe du certificat (raison, lieu, image de signature au choix) ;
  horodatage gratuit si Internet ; le PDF signe est enregistre tel quel (meme fichier ou autre nom) puis rouvert.
- Certificats : importer un fichier .pfx / .p12, ou « Recuperer ceux de vos postes » (certificats de PhilPDF Windows,
  lus dans le fichier chiffre des mots de passe partages, avec votre phrase secrete) ; gardes chiffres sur le
  telephone, mot de passe demande a chaque signature.
- Verifier les signatures (Plus, ou a l'ouverture d'un PDF signe) : intacte ou non, modifiee depuis, certificat
  approuve (les votres et ceux approuves sous Windows) ou non.

1.4.0
- Creer un formulaire (volet Modifier) : « Detecter les champs du formulaire » repere les zones a remplir de tout
  le document (pointilles, soulignes, traits, cases, cadres vides), comme PhilPDF Windows ; chaque champ prend le
  nom du texte voisin ; vous decochez, renommez, puis « Creer ». Outils « Champ texte » et « Case a cocher » pour
  dessiner un champ a la main. Appui long sur un champ : le renommer ou le supprimer. Tout s'annule avec « Annuler ».

1.3.1
- Fenetres (modifier le texte, organiser les pages, comptes, aide, signature au doigt) : elles s'arretent
  toujours au-dessus des boutons d'Android et du clavier ; « Appliquer » et les barres d'actions ne passent plus
  dessous. Modifier le texte : le texte defile, les boutons restent fixes en bas.

1.3.0
- Partager : « Envoyer le fichier » (piece jointe, comme avant) ou « Envoyer un lien » : le PDF (avec vos
  modifications) est depose dans PhilPDF/Partages de votre compte de synchronisation (Google Drive, OneDrive,
  Dropbox, Box), un lien en lecture seule est cree et part dans le texte du message ; il est aussi copie.

1.2.3
- Organiser les pages : la barre d'actions s'arrete au-dessus des boutons d'Android (retour, accueil) ;
  « Alleger » et « Mot de passe » ne sont plus caches dessous.

1.2.2
- Apres un enregistrement ou « Alleger », les modifications suivantes (texte, surlignage, soulignement...)
  n'apparaissaient plus : l'ecriture du fichier reorganisait le document ouvert. Il n'est plus touche (une copie
  est nettoyee, allegee et protegee a sa place). Un PDF protege par mot de passe le reste a l'enregistrement.
- Modifier le texte : police d'origine retrouvee quand son nom porte un prefixe (« WWIXJF+SourceSansPro... ») ;
  police de remplacement sans empattement pour les polices « Sans » (plus de Times a la place).
- Journal : une page qui ne peut pas s'afficher entierement y est notee.

1.2.1
- Modifier le texte : polices « Type3 » decoupees en morceaux (factures faites depuis un navigateur ou un site) :
  la police d'origine est gardee, en reprenant chaque lettre dans le morceau qui la contient (plus de passage
  en Helvetica) ; le gras reste du gras.
- « Alleger » remplace « Compresser » : comme PhilPDF Windows, photos et scans trop fins ramenes a la resolution
  choisie (qualite ecran, impression, tres leger pour l'e-mail, ou sans toucher aux images), taille avant et apres
  annoncee ; le texte et les images noir et blanc ne sont pas touches. « Annuler » remet tout.
- Barre du bas : « Commenter » devient « Modifier » (plus court, jamais coupe).

1.2.0
- Organiser les pages (volet Pages, ou Plus) : vignettes en grille ; toucher choisit une page, appui long puis
  glisser la deplace (avec toutes les pages choisies). Pivoter a gauche ou a droite, supprimer (avec confirmation),
  extraire dans un nouveau PDF, inserer une page blanche, ajouter les pages d'un autre PDF, compresser (sans perte,
  taille avant et apres annoncee), proteger par un mot de passe (AES 256) ou le retirer. Tout s'annule avec « Annuler ».

1.1.3
- Prete pour Google Play : vise Android 16 ; la version installee depuis Google Play est mise a jour par
  Google Play (elle ne cherche plus de nouvelle version sur GitHub). L'APK de GitHub continue de le faire.

1.1.2
- Modifier le texte : polices sans table de caracteres classique (OCR-B des releves bancaires, polices
  decrites par noms de lettres) reconnues : la police d'origine est gardee au lieu d'une police de
  remplacement ; une autre police de la page n'est plus jamais prise a sa place.

1.1.1
- Modifier le texte : la police d'origine est mieux reconnue (Helvetica et Helvetica-Bold ne sont plus
  confondues) ; polices standard sans table : seulement les lettres sures, sinon police de remplacement.

1.1.0
- Modifier le texte de la page (Commenter > « Modifier le texte », puis toucher une ligne) :
  seules les lettres sont remplacees (fond, cadres, traits et images restent, aucun rectangle blanc),
  avec la police d'origine du PDF quand elle a toutes les lettres tapees ; sinon la police standard
  la plus proche, annoncee avant d'appliquer. Taille, gras, italique, couleur, aligner a droite
  (montants, dates). « Annuler » defait la modification.

1.0.2
- Appui long sur une signature, un paraphe ou un tampon deja pose : « Deplacer » (le faire glisser,
  puis « Ici »), « - » et « + » pour la taille, « Changer » (en mettre un autre a sa place, meme endroit,
  meme largeur). Titre « Signature ou tampon » ; plus de couleur proposee pour une image.

1.0.1
- Ecran « Synchronisation avec vos postes » simplifie : un seul emplacement (celui de PhilPDF Windows),
  « Changer d'emplacement », « Deconnecter ». Les PDF s'ouvrent et s'enregistrent par le gestionnaire
  de fichiers d'Android (« Ouvrir un fichier », « Autre nom... »), qui voit deja tous vos comptes.
- Signer : la signature ou le tampon pose apparait tout de suite (il n'apparaissait qu'a l'action suivante).
- Signer : boutons « - » et « + » pour choisir la taille avant « Poser ici ».
- Signatures et tampons de vos postes : fond blanc rendu transparent (le texte de la page reste visible) ;
  touchez « Recuperer » une fois pour refaire ceux deja recuperes.

1.0.0
- Numero de version propre a Android (les versions 0.9.35 a 0.9.42 sont les premieres versions Android).
- Journal sur le telephone (Accueil > Aide > Journal) : connexions aux comptes, synchronisation,
  mises a jour proposees, erreurs ; bouton « Partager » pour l'envoyer. Jetons et codes masques.
- Nouveautes (ce fichier) consultables dans l'application.
- « Ouvrir un fichier » garde aussi le droit d'ecriture : « Meme fichier » fonctionne encore
  plusieurs jours apres sur un PDF du Drive ou d'un autre compte.

0.9.42
- Plusieurs comptes : Google Drive, OneDrive, Dropbox, Box ; puces sur l'Accueil pour parcourir
  leurs dossiers et ouvrir leurs PDF ; « Meme fichier » renvoie le PDF a sa place sur le compte.
- Un compte au choix sert a la synchronisation avec vos postes PhilPDF (autres postes,
  signatures et tampons) ; « Synchroniser avec ce compte », « Retirer ».
- Connexion par le navigateur fiabilisee : PhilPDF reste eveille (notification), termine la
  connexion une fois revenu, bouton « Revenir a PhilPDF » (plus de redirection automatique).

0.9.41
- Compte de synchronisation au choix : Google Drive du telephone, OneDrive, Dropbox, Box.

0.9.40
- Signer : apercu a faire glisser avant de poser une signature ou un tampon (« Poser ici » / « Annuler »).
- Tampons : choix « Heure » seule ; boutons « + date », « + heure », « + date et heure » dans votre texte.

0.9.39
- Rond du compte en haut a droite de l'Accueil ; lecture du dossier PhilPDF de vos postes ;
  recuperation des signatures et tampons de PhilPDF Windows (Signer > De vos postes).
- Barre du bas : les libelles rapetissent au lieu d'etre coupes (grands caracteres du telephone).

0.9.38
- Tampons : texte et cadre de la couleur choisie, fond transparent ; dates et heures pretes.
- Appui long : type de l'annotation en titre, « Supprimer » en haut, « Changer en ».
- « Annoter » devient « Commenter ».

0.9.37
- Remplir et signer : champs de formulaire, signature et paraphe dessines au doigt, tampons.

0.9.36
- Commenter : surligner, souligner, barrer, notes, dessin, formes, gomme ; annuler / retablir ;
  enregistrer dans le meme fichier ou sous un autre nom.

0.9.35
- Premiere version Android : lecture, recherche, signets, commentaires, partage, impression,
  disposition tablette (volets) et telephone (barre du bas, tiroirs).


WINDOWS ET LINUX
----------------

0.9.50
- Fermeture : plus d'« APPCRASH pyside6.abi3.dll » dans le Moniteur de fiabilite de Windows (Qt ecrivait encore
  au journal de PhilPDF pendant l'arret du programme) : PhilPDF s'arrete maintenant en une fois.
- Adresses d'envoi d'e-mails reglees sur un autre poste : reprises automatiquement (au demarrage, dans
  Preferences > E-mail et dans la fenetre d'envoi), mot de passe compris s'il voyage avec vos postes.
- Carnet d'adresses : groupes repliables d'un clic (par lettre, ou par serie A-C, D-F...), lettre affichee dans
  la colonne de gauche ; une personne avec plusieurs adresses = une seule ligne, l'adresse voulue se choisit a
  l'envoi (ou toutes) ; noms composes gardes entiers (Saint Martin, Dal Moro, Le Goff...).

0.9.49
- Fermeture (et fermeture pour mise a jour) : PhilPDF ne figure plus en « Fonctionnement arrete » (Qt6Core.dll)
  dans le Moniteur de fiabilite de Windows. Une tache encore active a la fermeture (verification de mise a jour,
  apercus, index, synchronisation) faisait arreter PhilPDF par Qt alors que tout etait deja enregistre.
  Si Qt signale encore un probleme grave, il est note dans Aide > Journal (ligne « qt »).

0.9.48
- Modifier un paragraphe : polices sans table de caracteres classique (OCR-B des releves bancaires,
  polices decrites par noms de lettres) reconnues : le texte ne passe plus en gras (police de
  remplacement) ; idem avec le bouton « ↻ ».

0.9.47
- Fermeture pendant une synchronisation lente (le Drive tarde a repondre) : PhilPDF ne se ferme plus
  « brutalement » (ni message de plantage au lancement suivant) ; l'envoi est reporte au demarrage suivant
  et c'est note dans Aide > Journal.

0.9.46
- Modifier un paragraphe : apres la modification, un bouton rond « ↻ » apparait a cote du paragraphe
  pendant 45 s. Si le resultat ne convient pas, il propose de refaire la modification autrement (methode
  de PhilPDF Android : chaque ligne a sa place, police d'origine, seules les lettres retirees, fond et
  cadres gardes). Ctrl+Z revient au texte d'origine dans les deux cas. La methode habituelle reste celle
  par defaut.

0.9.45
- Ouvrir depuis NAS, FTP, Drive : dossiers d'abord (en gras), puis les PDF ; bouton « Dossier parent » bien
  visible, ligne « .. » en tete, touche Retour arriere. Google Drive : si l'autorisation enregistree n'est que
  la limitee alors que « Voir tout mon Google Drive » est coche, un bandeau le dit et propose de reautoriser.
- Petit ecran : l'Accueil defile au lieu d'etre coupe en bas ; volet des tampons et signatures : apercus
  et etoiles a la taille du volet, nom complet des categories en bulle.
- Preferences > Imprimante : « Imprimer depuis PhilPDF sur » une autre imprimante que celle de Windows
  (ex. la couleur alors que Windows a la laser noir et blanc), ou la derniere utilisee dans PhilPDF.
- Carnet d'adresses en tableau : colonnes Nom, Prenom, Adresse deplacables (glisser l'en-tete) et triables
  (clic sur l'en-tete), contacts groupes par la premiere lettre de la colonne de gauche.
- Compte (NAS, FTP, Drive) ajoute sur un poste : repris automatiquement sur vos autres postes, et son
  autorisation y est demandee tout de suite.

0.9.44
- Mes tampons, mes signatures (clic droit) : « Fond blanc transparent » retire le fond blanc d'un tampon
  ou d'une signature scannes, qui cachait le texte de la page ; vos autres postes et Android le recoivent.

0.9.43
- Aide > Journal (echanges, mises a jour) : chaque etape des mises a jour y est notee
  (verification, version trouvee, acceptee ou refusee, telechargement, installation,
  nouvelle version lancee).
- Aide > Nouveautes (readme.txt).

0.9.38 a 0.9.41
- Numerotation de Bates : reprise des reglages, 8 positions, inclinaison, remplacement.
- Modifier un paragraphe : gras, italique, souligne, barre conserves.
- Retouche « effacer » : fond uni ou transparent rendu proprement (plus de flou).
- Ouvrir ou glisser une image ou un document Office : converti en PDF a l'ouverture.
- Carnet d'adresses : nettoyage des doublons, prenom et nom, tri.
- Nouveau poste : reprend la largeur des volets, l'imprimante et le compte de synchronisation.
- Accueil : recents affiches tout de suite puis completes ; rien de tronque sur petit ecran.
- Licence AGPL v3 ; version Linux (Flatpak et archive).
