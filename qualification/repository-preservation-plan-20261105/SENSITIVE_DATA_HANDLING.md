# Confidentialite, cles et archives

Plan uniquement. Aucun secret exporte, contenu prive inspecte, chiffrement
effectue ou support de sauvegarde cree. Les risques de phase 1 sont repris
comme limites d'inventaire, pas comme vulnerabilites confirmees.

## 1. Regle de classification

Traiter comme sensibles jusqu'a decision privee : `.env` et variantes reelles,
cles/certificats non examines, configurations Git et logs, historique et reflogs,
dumps/SQLite/WAL/SHM, archives de documents, images Docker TAR et livraisons opaques.
L'historique Git comporte un PDF potentiellement personnel identifie en phase 1;
son nom reste masque. Ne pas publier un bundle sous pretexte qu'il ne contient
que de l'historique.

`deliveries\docnelo-signup-e2e-lab\tls\lab.key` est un candidat cle privee non
suivi/non ignore; aucune utilisabilite ni absence de reutilisation n'est attestee.
Le certificat associe n'est pas automatiquement une cle privee.
Les sauvegardes `var\backups` et dumps de roundtrip ne sont pas attestes anonymes.
« test », « lab » ou « synthetic » dans un nom ne prouve pas l'absence de donnees.
Les fichiers modeles suivis ne sont pas certifies sans secrets par cet audit.

## 2. Organisation des protections

| Domaine | Protection requise |
|---|---|
| A/B | Supports physiques independants, chiffrement authentifie du conteneur ou chiffrement de volume qualifie avec controles d'integrite distincts, acces exclusif/restreint |
| E | Conservation privee et independante, replicas separes, protection contre ecriture/suppression accidentelle, ancres externes |
| R et staging | Stockage chiffre et isole, sans partage ou synchronisation; aucun intermediaire en clair sur C par commodite |
| Manifestes/logs | Prives et chiffres aussi : noms, chemins, proprietaires, SDDL, lignes de commande et erreurs peuvent etre sensibles |
| Reprise cryptographique | Cle/passphrase ou recuperation hors sauvegardes, canal/lieu independant, responsable et test reel de recuperation |
| Rapports partageables | Comptages, hashes de conteneurs/manifestes et conclusions expurgees; pas de contenu, identites personnelles ou descripteurs de securite |

Deux dossiers sur un meme disque ou accessibles par une seule session ouverte
ne couvrent pas une perte physique ni une compromission unique.
Preserver les permissions source comme metadonnees chiffrees, sans reproduire
sur les supports ouverts une DACL source autorisant un acces trop large.
La restriction du dossier parent seule ne suffit pas si les enfants portent des
autorisations explicites plus larges; verifier l'acces effectif.

## 3. Chiffrement a choisir avant la capture

Presence observee : `manage-bde`, `cipher`, `icacls`, `gpg`, `tar` et `robocopy`.
`age` et `7z` non trouves dans PATH. Presence n'est ni confiance dans le binaire,
ni preuve de chiffrement actif, ni validation du format; versions/capacites/
droits devront etre controles sans installation ou telechargement automatique.

Voie recommandee : volumes NTFS proteges par BitLocker ou equivalent approuve,
recuperation independante et testee, plus controles SHA-256 exhaustifs et ancres
hors support. Le chiffrement de volume seul ne prouve pas l'authenticite des
fichiers et ne protege plus contre un processus autorise lorsque le volume est
deverrouille. Limiter la duree d'ouverture, les droits et les acces simultanes.

Si un conteneur chiffre par GPG est retenu, valider au prealable outil, format,
integrite cryptographique, reprise et preservation de toutes metadonnees au
niveau du payload. Un simple TAR des fichiers Windows ne garantit ni reparse
Linux, ni ACL/ADS/topologie. Ne jamais utiliser un mode sans controle d'integrite.
Tout staging de payload doit deja etre protege; ne pas fabriquer d'abord une
archive en clair dans le depot. Pas de pipeline binaire natif PowerShell 5.

Saisir une passphrase via interface privee/pinentry, jamais en argument, variable
d'environnement, fichier de rapport ou historique du terminal. Ne pas utiliser
comme unique moyen de reprise un secret protege seulement par le profil Windows
dont on prepare justement la sauvegarde. `cipher`/EFS seul sans cle exportable
et testee n'est pas un protocole de reprise.

## 4. Gestion des cles et des erreurs

Les cles applicatives historiques sont conservees byte pour byte sous chiffrement;
elles ne sont pas remplacees par la cle de sauvegarde, ni tournees ou revoquees
dans ce lot. Les cles de sauvegarde ne sont pas ajoutees aux manifestes de source
ni uniquement rangees dans le conteneur qu'elles ouvrent.
Conserver les materiaux de recuperation hors Git, avec acces prive et procedure
de perte de support/secret; tester sans afficher leur valeur.

Si un outil affiche un secret ou un nom personnel, confiner le log protege et
produire seulement une synthese expurgee. Aucune transmission reseau ni service
tiers n'est prevu. Ne pas ouvrir les archives pour les « assainir » pendant leur
preservation. Toute analyse privee de contenu, rotation ou reecriture d'historique
est une decision separee.

Une preservation partielle, un outil incompatible, un support non protege ou une
cle de reprise non verifiee interdit de declarer `PRESERVATION_VERIFIED=true`.
La conservation ne dispense pas de la revue privee avant un futur ajout Git.
