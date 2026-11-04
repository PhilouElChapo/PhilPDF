PHILPDF - NOUVEAUTES
====================

Ce fichier dit ce qui a change a chaque version (le plus recent en haut).
PhilPDF Windows et Linux ont un numero (0.9.x), PhilPDF Android a le sien (1.x) :
chacun n'est republie que lorsque son propre code change.
Dans PhilPDF : Aide > Nouveautes (Windows, Linux), Accueil > Aide > Nouveautes (Android).


ANDROID
-------

1.12.1
- Code optimise pour Google Play (R8) : application plus legere et plus rapide a demarrer. Les essais sur telephone
  simule tournent desormais sur cette version optimisee, celle qui est distribuee.
- Affichage de bord a bord sur toutes les versions d'Android (comme Android 15 l'impose) ; rien ne passe sous les
  barres d'Android.

1.12.0
- Lecture fluide (comme le « Mode liquide » d'Acrobat) : Plus > Lecture fluide (sur tablette, bouton en haut). Le
  texte de chaque page est remis en colonne a la largeur de l'ecran : titres, paragraphes recousus (mots coupes en fin
  de ligne recolles), gras et italique, images a leur place ; numeros de page et titres courants laisses de cote.
  Reglages gardes : taille du texte (A- / A+), fond clair, sepia ou sombre, texte justifie ou non, police avec ou sans
  empattements. Toucher « Page n » ramene a cette page dans l'affichage normal. Page scannee : son image, avec la
  reconnaissance du texte proposee. Le PDF n'est pas modifie.

1.11.1
- Les derniers messages encore en francais sur un telephone en anglais sont traduits : erreurs de connexion aux
  comptes (Drive, OneDrive, Dropbox, Box), certificats, saisie refusee dans un formulaire, telechargement des
  langues de reconnaissance, page de retour du navigateur apres la connexion.
- Tampons prets a l'emploi dans la langue du telephone (RECEIVED ON, PAID ON... en anglais) ; date et heure
  « at » en anglais, « a » en francais. Noms proposes a l'enregistrement : « (modified) » / « signed » en anglais.

1.11.0
- PhilPDF en anglais sur un telephone qui n'est pas en francais (en francais sinon). Les langues de la
  reconnaissance du texte s'affichent dans la langue du telephone.
- Images de la page, comme sous Windows (Modifier > Texte et images > Images) : toucher une image la choisit ; on la
  glisse pour la deplacer, la poignee carree l'agrandit, la ronde la tourne. Boutons : quart de tour, miroir
  gauche-droite et haut-bas, reconnaitre le texte, remplacer par une autre image, enregistrer l'image, supprimer.
  Avec l'outil « Modifier le texte », toucher une image (une page scannee par exemple) la choisit aussi.
- Formulaires : liste ouverte a plusieurs choix (on coche les choix au remplissage) ; nombres : symbole avant le
  nombre, affichage des nombres negatifs (-12,50, en rouge, entre parentheses), comme sous Windows.

1.10.4
- PDF abimes par les versions 1.10.0 et precedentes (debris dans le contenu d'une page) : Acrobat montrait la page
  vide. Ils sont maintenant repares des l'ouverture, avec un message ; enregistrez pour garder la correction.
- Bouton d'action (e-mail, imprimer...) : changer ses proprietes le redessinait en blanc ; il reste bleu.
- Organiser les pages : toucher deux fois une page y conduit.

1.10.3
- Correction urgente : depuis la 1.10.1, reconnaitre ou modifier le texte d'une page faite d'un seul bloc de contenu
  effacait tout le dessin de la page (images, texte) a l'enregistrement. Repartez du fichier d'origine.
- Modifier le texte a l'envers (livret plie, texte reconnu tourne) : il est trouve sous le doigt et reecrit dans le
  meme sens.
- Nouveaux essais automatiques : la page garde ses images et son texte apres OCR ou modification ; texte a l'envers
  modifiable ; valeur tapee dans une liste a saisie libre.

1.10.2
- Reconnaissance du texte a l'envers (livret plie) : le texte lu a l'endroit (du charabia, « NOISSIN ») prenait la
  place du bon (« MISSION ») ; chaque mot garde maintenant la lecture la plus sure. Plus besoin de retourner la page.
- Liste deroulante a saisie libre : en la remplissant, une zone « Autre valeur » permet de taper la sienne.
- Essais automatiques sur un telephone simule a chaque fabrication (champs, OCR, texte modifie, signature) : une
  version qui en rate un n'est pas publiee.

1.10.1
- Texte reconnu (OCR), texte modifie, champs ajoutes : ils pouvaient disparaitre a l'enregistrement, remplaces par un
  debris (« <00000000B0EC00> ») ; c'est pourquoi le texte du livret ne se selectionnait pas. Cause : une fonction du
  moteur PDF (ajout a une liste) liberait deux fois l'objet ajoute. PhilPDF ne s'en sert plus. Les debris laisses dans
  un PDF par les versions precedentes sont retires a la modification suivante de la page.

1.10.0
- Proprietes d'un champ, comme sous Windows : info-bulle, obligatoire, lecture seule, affichage (visible, masque,
  non imprime, masque mais imprime) ; texte : plusieurs lignes, longueur maximale, alignement, valeur par defaut ;
  police, taille et couleur du texte.
- Listes deroulantes : tri par ordre alphabetique, choix montre par defaut (le 3e par exemple), saisie libre.
- Cases a cocher : signe (coche, croix, rond, carre, losange, etoile), couleur, valeur quand c'est coche, cochee par
  defaut ; le caractere ZapfDingbats d'Acrobat est garde pour les autres lecteurs.
- Boutons d'action (outil « Bouton » du groupe Formulaire) : reinitialiser le formulaire, imprimer, envoyer par
  e-mail, aller a une page ; ils marchent dans PhilPDF et dans Acrobat.
- Ordre de tabulation de la page (groupe Formulaire) : fleches pour ranger les champs, ou ordre automatique.
- JavaScript du champ, evenement par evenement : le code produit par PhilPDF, et le votre.
- Modifier le texte : un paragraphe qui melange gras et normal (« Mode de paiement : » en gras, la suite normale)
  garde ses styles ; le texte tape prend le style du texte qu'il remplace.

1.9.0
- Reconnaissance du texte (OCR) dans les images d'une page qui a deja du texte (affiche, livret, photo avec
  legende) : seules les images sont lues, le texte deja present n'est pas double. Proposee aussi quand on touche une
  image avec « Modifier le texte ».
- Option « Chercher aussi le texte couche ou a l'envers » (livret plie, texte vertical) : la page est lue dans les
  quatre sens (plus lent) ; le texte reconnu est pose dans le bon sens.
- Message clair quand rien n'est reconnu (page deja lisible, texte trop petit ou decore, texte a l'envers).
- « Modifier le texte » sur une page avec images : l'image n'est effacee sous la ligne que pour le texte reconnu.

1.8.9
- Icones en couleur : volet ouvert et outil choisi en rouge, disquette rouge quand il y a des modifications a
  enregistrer, annuler / retablir grises quand il n'y a rien a annuler (elles restaient toutes noires).

1.8.8
- Ecran des comptes (pastille en haut de l'accueil) : version installee et bouton « Rechercher une mise a jour »,
  sans attendre le prochain demarrage.

1.8.7
- Plantage a la reouverture d'un PDF signe : corrige (une autre fonction du moteur PDF, « modifie depuis la
  signature », est absente de la bibliotheque livree ; PhilPDF le calcule lui-meme).
- Tampons et signatures en favori : etoile jaune pleine (elle restait grise).

1.8.6
- Plantage a l'ouverture d'un PDF signe (donc juste apres « Enregistrer » une signature) : corrige. Le nom du
  signataire est lu directement dans le certificat (la fonction du moteur PDF prevue pour cela plantait).
- Avant de signer, les restes laisses dans le PDF par les versions precedentes (copie d'un ancien champ, debris) sont
  retires.

1.8.5
- Champs de formulaire et de signature poses sur le telephone : ils etaient enregistres en double dans le PDF (defaut
  du moteur PDF utilise, contourne). Ils sont maintenant ecrits une seule fois ; ceux deja poses sont repares au moment
  de signer.

1.8.4
- Signature dans un champ ecrit en double : correction refaite (le champ est recree proprement, une seule fois, avant
  de signer ; s'il reste illisible, un message le dit au lieu de produire un PDF mal signe).
- PDF signe par une version precedente avec ce defaut : son ouverture ne tente plus de verifier ce champ.

1.8.3
- Signature avec un certificat dans un champ de signature deja pose : le document restait « non signe » (le champ
  existait en deux exemplaires dans le PDF, la signature allait dans celui qu'on ne voit pas). Le champ est remis en un
  seul exemplaire avant de signer.
- PDF signe plus leger (l'image de signature est compressee).

1.8.2
- Mise a jour automatique : telecharge l'APK fait pour ce telephone (environ 30 Mo) au lieu de la version universelle
  (environ 80 Mo, qui contient les trois types de processeur).

1.8.1
- Certificats : ceux qu'on ne peut pas utiliser (retires sur vos postes, ou ancien doublon d'un autre, affiches
  « Certificat » sans nom) ne sont plus repris de Windows, et ceux deja la sont retires tout seuls.
- Reconnaissance du texte : choix de la langue du document (francais, anglais, espagnol, italien, allemand,
  portugais, neerlandais), plusieurs a la fois pour un document mixte. Le francais est livre avec l'appli ; les autres
  sont telechargees une seule fois (1 a 4 Mo), a la premiere utilisation. Au depart : francais et langue du telephone.

1.8.0
- Signature avec un certificat : l'application ne bloque plus (la lecture du document a signer tournait sans fin).
  « Annuler » reste possible pendant la signature.
- Creer un certificat sur le telephone (Signer > Signature numerique > Creer un certificat) : nom, e-mail,
  organisation, duree, mot de passe. Il est depose dans le dossier PhilPDF synchronise : vos postes Windows le
  reprennent (PhilPDF Windows 0.9.53 ou plus).
- Certificats : « Ranger » pour les mettre dans l'ordre voulu (fleches) ou en retirer un ; un certificat retire
  n'est plus remis par la synchronisation. Deux certificats du meme nom se distinguent (e-mail ou date).
- Reconnaissance du texte (OCR) des pages scannees, sur le telephone : proposee quand on touche une page sans texte
  avec « Modifier le texte », ou par Plus > Reconnaitre le texte. Le texte est pose invisible sous l'image : on peut
  chercher, copier, et le modifier (les lettres de l'image sont alors effacees sous la ligne).

1.7.3
- Certificats (identites numeriques) crees ou ajoutes dans PhilPDF Windows : repris tout seuls depuis le dossier
  PhilPDF synchronise, sans phrase secrete (il faut PhilPDF Windows 0.9.52 ou plus) ; leur mot de passe reste
  demande a chaque signature. La phrase secrete est aussi essayee sans espace autour et sous ses deux formes d'accents.
- Plantage : sa cause est notee dans le journal (Accueil > Aide > Journal) pour pouvoir le corriger.

1.7.2
- Mots de passe (certificat, phrase secrete, PDF protege, nouveau mot de passe) : un oeil a droite du champ montre
  ou cache ce qui est tape.

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

0.9.63
- Modifier le texte et les images : les petites images posees sur un fond de page (image pleine page, comme dans les
  rapports d'expertise avec photos) se choisissent enfin ; avant, le clic prenait toujours le fond. Quand plusieurs
  images se superposent, c'est la plus petite (celle que l'on vise) qui est choisie.
- Curseur : une main sur un objet que l'on peut choisir (texte, image, dessin), les quatre fleches sur l'objet deja
  choisi, que l'on peut deplacer.

0.9.62
- Dessins vectoriels : deplacer, agrandir, tourner, retourner ou supprimer un dessin garde ses degrades, ses motifs
  (quadrillages, trames) et ses transparences. PhilPDF deplace le dessin tel qu'il est ecrit dans le PDF au lieu de le
  redessiner ; il reste a sa place dans l'empilement (le texte pose dessus reste visible). Si le dessin n'est pas
  ecrit en morceaux separables, ou s'il sortirait de la zone ou le PDF le decoupe, l'ancienne methode prend le relais.
- Un degrade seul (sans contour) se choisit maintenant comme un dessin.
- Les boutons et champs de formulaire ne sont plus pris pour des dessins de la page.

0.9.61
- Retouche d'image : « Effacer » sur une grande zone (le fond blanc d'un scan choisi a la baguette magique) faisait
  planter PhilPDF ou noircissait toute l'image. La zone prend maintenant sa couleur dominante, en un instant ; les
  petites zones (une tache, un mot) sont reconstituees seulement autour d'elles, bien plus vite.
- Volet de retouche plus clair : rubrique « L'IMAGE » (tourner a gauche ou a droite, miroir, Recadrer..., Remplacer...,
  Enregistrer...) puis « RETOUCHE ». « Recadrer... » : un premier clic prepare le rectangle, on trace la partie a
  garder, un second clic recadre. Plus aucun bouton tronque (verifie par les essais automatiques).
- IA : une consigne tapee (resume, consigne libre d'un paragraphe) n'est plus gardee d'office : cochez « Garder cette
  consigne dans la liste » pour la retrouver. Les consignes deja gardees se suppriment (bouton « Supprimer »), y
  compris celles de la consigne libre ; « Mes styles » de la retouche d'image par l'IA ont un bouton « Supprimer ce
  style ».

0.9.60
- Ouvrir ou enregistrer sur un emplacement (NAS, FTP, WebDAV, Google Drive, OneDrive, Dropbox, Box) : colonnes Nom,
  Date de modification et Taille ; un clic sur un titre trie la liste (un second clic : sens inverse), les dossiers
  restent en tete. Le tri choisi est retenu.

0.9.59
- Texte d'un scan modifie : il disparaissait de l'ecran tant que le mode Modifier restait ouvert (l'apercu de
  retouche de l'image le recouvrait) et ne revenait qu'avec « Terminer ». L'apercu ne s'affiche plus que si un
  reglage de retouche est en cours, et il reprend l'image modifiee.

0.9.58
- Texte reconnu d'un scan (OCR) modifie : les lettres de l'image sont effacees sous la ligne et le nouveau texte est
  ecrit, visible, a la meme place. Avant, l'ancien texte restait a l'ecran et le nouveau, invisible ou decale, ne se
  voyait pas. La police est choisie en comparant l'image des lettres (avec ou sans empattements, normale ou grasse) ;
  taille et couleur sont celles du scan.
- Preferences > Tampons et signatures, « Mes tampons » : la liste des tampons prets a l'emploi suit l'ordre choisi.

0.9.57
- Reconnaissance du texte (OCR) : l'image de la page n'est plus tassee (elle etait aplatie dans un carre, et le texte
  reconnu ne tombait plus sur les mots). Lecture plus sure : plusieurs lectures faites en meme temps (image nettoyee,
  image d'origine, scan peu fin agrandi), le mot le plus sur est garde. Texte a l'envers ou couche (livret plie,
  page retournee) reconnu aussi. Une page en couleur garde son image d'origine (avant : passee en noir et blanc).
- Bouton « Envoyer par e-mail » d'un formulaire : il ouvre le volet d'envoi, comme Acrobat, avec le choix : logiciel
  de messagerie (PDF deja joint, carnet d'adresses), adresse e-mail reglee dans PhilPDF, ou messagerie web.
- PDF abime par PhilPDF Android 1.10.0 ou precedent (Acrobat montrait une page vide) : repare a l'ouverture, avec un
  message. Bouton d'Android affiche en blanc : redessine en bleu.
- Images : celles rangees dans un sous-objet de la page (PDF faits sur Mac, InDesign...) se tournent, se deplacent,
  se retournent maintenant comme les autres. Nouveau : miroir gauche-droite et haut-bas, recadrage (garder la zone
  tracee), enregistrer l'image dans un fichier ; boutons en haut du volet de retouche et au clic droit.
- Dessins (schemas, illustrations tracees, sans image) : en mode Modifier, un clic les choisit comme un objet ; on
  peut les deplacer, les agrandir, les tourner, les retourner, les copier ou les supprimer.
- Organiser les pages : un double-clic sur une page y conduit.

0.9.56
- Plantage signale par Windows (« pyside6.abi3.dll », c0000005) quand on ouvre un PDF alors que PhilPDF est deja
  ouvert : le second lancement, qui confie le fichier a la fenetre ouverte, s'arrete maintenant sans planter.
- Journal : la verification de la synchronisation faite chaque minute n'y ecrit plus que ses erreurs (une quinzaine de
  lignes par minute en chassaient les informations utiles, dont les plantages).

0.9.55
- Langue : en automatique, PhilPDF prend la langue du systeme s'il la connait (francais, anglais, espagnol, italien,
  allemand), sinon l'anglais. L'installateur fait de meme (francais ou anglais).

0.9.54
- Tampons prets a l'emploi (Recu, Valide, Paye...) : rangez-les dans l'ordre voulu, par clic droit dans le volet
  (En premier, Monter, Descendre, En dernier) ou dans Preferences > Tampons et signatures > « Ordre des tampons prets
  a l'emploi » (on les glisse). L'ordre suit sur vos autres postes.
- Volet des tampons et signatures : clic droit sur un de vos tampons ou un favori pour le monter ou le descendre.

0.9.53
- Certificats crees sur le telephone (PhilPDF Android 1.8.0) : repris tout seuls depuis le dossier PhilPDF
  synchronise.

0.9.52
- Identites numeriques (.pfx) : deposees dans le dossier PhilPDF synchronise (sous-dossier « identites ») ; vos
  autres postes et PhilPDF Android les reprennent sans phrase secrete. Chaque .pfx reste protege par son propre mot
  de passe, demande a chaque signature ; une identite retiree est effacee du dossier.

0.9.51
- E-mail : le mot de passe de l'adresse d'envoi (et celui d'ouverture du PDF envoye) a lui aussi son oeil pour
  voir ce qui est tape, comme les autres mots de passe de PhilPDF.

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
