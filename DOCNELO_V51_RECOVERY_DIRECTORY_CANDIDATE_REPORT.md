# Docnelo V5.1 - Recovery Control Directory : rapport candidat

## Verdict et perimetre

**GO limite a la preparation du candidat local et a sa soumission en
qualification laboratoire.** Les prerequis P0 du protocole doivent etre
attestes avant tout lancement laboratoire Docker ; leur disponibilite
n'est pas demontree ici. Ce n'est pas un GO de qualification Docker reussie.

**Aucun GO Docker operationnel, Backup/Restore global, S2, Lifecycle 10,
Public Beta ou production.** Aucun deploiement, serveur Uvicorn,
conteneur, migration de base, acces VPS ou service externe n'a ete lance.
Aucune transition du latch restaure reel vers ready n'a ete effectuee.

L'espace distinct est :

`candidates/recovery-control-directory-v1/`

Il s'agit d'une copie isolee du working tree courant, deja modifie avant
cette mission, **pas** d'une release scellee ou d'une revision CI attestee.
`ORIGIN.json` conserve HEAD et les empreintes des fichiers copies.
Aucun changement n'a ete applique aux sources actives ou aux releases.

## Resultats effectivement obtenus

| Controle | Resultat |
|---|---|
| Plateforme executee | Windows, CPython 3.13.7 |
| Campagne finale | **119 passed**, 0 skip, 0 xfail ; exit pytest 0 |
| Repartition | 77 tests unitaires/configuration/modeles, 42 tests ASGI |
| Isolation finale | zero evenement d'E/S interdite ; reseau/DNS, processus, threads reels, SQL, SMTP et IA bloques |
| Application | vraie `backend.main.create_app`, routeur conserve, six middlewares inchanges |
| Surface HTTP | 59 couples methode/route enregistres ; health, login, register, documents, docs/redoc/OpenAPI inclus |
| Refus de la matrice principale | 4 484 : 3 382 HTTP 503 et 1 102 HTTP 403 Lite, sans consommation du body ni appel aval |
| Administration | inventaire de l'HTTP effectivement enregistre ; aucune route administrative fictive ajoutee |
| Controles positifs | sentinelle aval HTTP 500 intentionnelle ; aucun traitement metier reel |
| Compose applicatifs | quatre fichiers complets controles par rendu synthetique et comparaison des parametres conserves |
| Lecteur minimal laboratoire | recette preparee : un seul lecteur, network none, aucun port, aucun bind RW |
| Tracabilite patch | verification `git apply --check --whitespace=error-all`, sans appliquer le patch |
| Originaux | 226 fichiers sources et 276 documents Compose historiques verifies byte-identiques |
| Debian / Engine / Compose natif | **non executes** |
| Permissions/UID/GID/lock POSIX | modeles executes sous Windows ; preuves systeme Linux **non obtenues** |
| Frontend D20 | script in-memory prepare, syntaxe Node verifiee ; scenario **non execute** |

Les refus chiffres concernent la matrice principale. Les scenarios de
controle positif/reouverture ont leurs assertions et resultats distincts.
HTTP 500 est uniquement le signal positif volontaire de la sentinelle
devant le routeur, pas une reponse metier attendue en exploitation.

Les preuves finales sont conservees dans :

`qualification/recovery_directory/windows-preparation-final-004/`

Ce repertoire contient JUnit, result.json, cases.json, journal pytest,
inventaire des sources, metadonnees des dependances et SHA256SUMS.
Le verdict machine est `PASS_PREPARATION_ONLY`.

Les essais intermediaires restent conserves, sans etre presentes comme
la qualification finale : le bootstrap initial a bloque une demande
indesirable `socket.gethostname` avant execution ; l'empreinte plateforme
du harness a ete rendue synthetique sans assouplir la garde. Une fixture
de chemin et la generation du patch avec fins de ligne mixtes ont aussi
ete corrigees. Seul `windows-preparation-final-004` est rattache aux
empreintes finales livrees.

## Contrat et correctif

Contrat operateur **Recovery Control Directory v1**, independant du
format JSON historique `{"format":1,"state":...}` :

| Element | Valeur / invariant |
|---|---|
| Source hote | `RECOVERY_CONTROL_DIR`, absolu canonique, repertoire stable et dedie |
| Cible API RO | `/run/documind-control` |
| Chemin Settings | `/run/documind-control/recovery-state.json` via `RECOVERY_STATE_PATH` |
| Version | `RECOVERY_CONTROL_VERSION=1`, imposee dans les Compose et verifiee par les gardes |
| Provenance | `RECOVERY_CONTROL_SOURCE_DIR`, derivee de la variable hote et egale a la source du bind |
| Identite | API non-root ; groupe lecteur numerique explicite, non nul, dans `group_add` |
| DAC proposee | repertoire root:groupe-lecteur 0750 ; enfant root:groupe-lecteur 0440 |
| Publication | enfant uniquement ; jamais remplacement du repertoire |

La provenance supplementaire empeche Compose de masquer une entree
relative en la normalisant en source absolue. Ce n'est ni un secret ni
un second chemin configurable. Le backend continue a lire son champ
Settings existant ; aucun changement de middleware ou parseur n'est requis.

Les binds fichiers sont retires dans les quatre copies completes :
dev, production, VPS Beta et recette Beta. Aucun override additif n'est
livre. Les autres volumes, reseaux, limites et securites sont compares
a une projection des configurations originales. Les deux merges YAML
de relais de recette sont explicites, a valeurs equivalentes ; la
variable recovery inutilisee de lifecycle-init est retiree.

La garde partagee refuse : anciennes cibles/fichier, doublons, masques
imbriques ou tmpfs, chemins ambigus, aliases parents/enfants y compris
RO, `volumes_from`, nouveaux montages configs/secrets non revus, volumes
nommes externes ou driver-bind. L'inspection modele verifie aussi
USER, groupes, environnement, source exacte et RW=false.

La garde hote Linux exige proprietaires/modes, ancetres fiables sans
symlink, enfant regulier single-link borne, repertoire dedie et identite
device/inode stable. Elle exclut deployments, donnees Docker et sources
persistantes. Les validations de configuration et d'inspection restent
distinctes ; aucune preuve de l'une n'est substituee a l'autre.

Les copies deployment/backup conservent leurs autres controles, et
ajoutent le helper a l'inventaire du controleur, du bundle atteste et du
garde installe. Les anciens bundles restent diagnostiquables mais ne
peuvent plus autoriser une operation candidate, meme via rollback.
Les points d'entree `main`/`execute` deployment et backup sont bloques
par **CANDIDATE_ONLY**, sans option pour deployer ce paquet.

Le publisher general ajoute ferme **uniquement vers quarantined** :
verrou operateur externe preexistant ; temporaire exclusif/no-follow ;
fchown/fchmod avant publication ; flush/fsync fichier ; os.replace
relatif au descripteur du repertoire ; fsync parent ; controle de
l'identite et relecture. Aucun publisher general ready n'est ajoute.

Les transitions ready/fautes de `lab/control.py` sont limitees a un
**nouveau namespace synthetique marque root** sous `/var/tmp`, avec
autorisation explicite. Cet outil refuse le chemin du latch restaure.

## Verrou Beta et restauration

Le verrou reste exactement :

`/opt/documind-public-beta/.public-beta-backup.lock`

Son inode ne doit jamais etre remplace ou supprime. DEPLOYMENT_BASE et
OPERATOR_LOCK ne dependent plus de CONTROL.parent. Le nouveau controle
runtime propose est son voisin `recovery-control/recovery-state.json`,
pas son nouveau parent de verrou. Les generations anciennes doivent
etre gelees pendant migration, meme si elles partagent ce verrou.

Le mode/proprietaire du verrou existant et la confiance de ses ancetres
restent a verifier dans le laboratoire ; aucune correction automatique
de leur ownership n'est proposee. Le publisher refuse un verrou absent
ou non conforme plutot que de le remplacer.

Les restores copies restent des producteurs d'artefacts quarantine
0600, pas du controle vivant. La migration conserve archive et latch
restaure comme preuves immuables, puis publie q dans un repertoire
runtime neuf. Aucun chmod ni ecriture dans le dossier du latch reel :

`/home/adeline/docnelo-lab/artifacts/qualification/capture-v51/roundtrip-restore/files/recovery-state.json`

Son SHA fourni reste une reference historique, **non revalidee par une
lecture Debian dans cette mission Windows** :

`0a01b17bf9de4fe0d4eccdbae2da89f3345c261622bb8f11a2777c2f53229565`

## Inventaire livre et empreintes

Dans le candidat : **12 sources existantes modifiees uniquement dans
leur copie**, 2 helpers ajoutes et 214 sources conservees identiques.

| Fichiers dans `source/` | Objet |
|---|---|
| compose.yaml, compose.production.yaml, compose.public-beta.vps.yaml, compose.public-beta-test.yaml | remplacement complet du bind et groupe lecteur explicite |
| .env.example, .env.production.example, .env.public-beta.example | contrat v1, anciens parametres de fichier retires |
| tools/deploy_production.py | gardes config/inspect/host, identite stable, inventaires du helper, blocage execution |
| tools/backup_production.py | gardes directory et DockerRootDir/inspect, blocage execution |
| tools/public_beta_backup.py | base/verrou independants, contrat directory et gardes, blocage execution |
| tools/backup_local.py | validation avant travail externe, entrypoint bloque |
| tools/release_security.py | helper atteste obligatoire ; historique diagnostic-only |
| tools/recovery_control_directory.py | contrat, refus, metadonnees, verrou et publisher q |
| tools/validate_recovery_candidate.py | chargeur YAML strict et modele synthetique sans environnement reel |

Hors source : deux fichiers de tests candidats, lanceur securise, profil
pytest, generateur d'inventaires, README/contrat, protocole Debian D01-D20,
lecteur Docker, outil synthetique Linux, test ASGI monte, scenario BFF
in-memory et Compose minimal sans reseau.

`CHANGES.json` contient chaque fichier source modifie/ajoute avec SHA
original et candidat, la liste des copies identiques et les assets de
campagne. `ORIGIN.json` couvre les originaux ; `INPUTS.json` et
`SHA256SUMS` couvrent tous les fichiers candidats, tests et protocoles.
`DEPENDENCIES.json` couvre les fichiers de dependances Python/npm et les
versions/empreintes RECORD de l'environnement Windows utilise.
Ces empreintes ne sont pas des signatures ni une verification de tous
les binaires installes.

Ancre du candidat fige - SHA-256 de son fichier `SHA256SUMS` :

`c1099170790274d9a0bfc813d44f17afb907e1d68eb101a9c5fc887022030eba`

`candidate.patch` est un diff des sources sur la base de travail
inventoriee ; il ne doit **pas** etre applique aux releases scellees.
Les tests/protocoles et le snapshot complet sont fournis separement du
diff et couverts par les inventaires.

Le transfert local est prepare dans :

`deliveries/docnelo-v51-recovery-directory-candidate-v1/`

Il contient une archive neuve du candidat fige, le present rapport, les
preuves Windows finales et un inventaire de paquet. Il ne contient pas
d'image Docker ni de wheelhouse Debian ; aucun ancien transfert n'est
modifie. Verifier son SHA256SUMS externe avant extraction, puis celui du
paquet et du candidat.

## Migration et conditions de qualification

Le protocole detaille est :

`candidates/recovery-control-directory-v1/DEBIAN_OFFLINE_PROTOCOL.md`

Il fournit P0-P4, la matrice D01-D20 et les oracles, les scripts/cas
prepares, et distingue explicitement les sous-preuves Windows des
campagnes Linux/Docker **non executees**.

La migration exige une barriere de trafic independante prouvee,
gel des writers/timers/backups, verrou stable, drainage/arret des anciens
lecteurs, nouveau controle q, rendu sans anciennes fusions, recreation
controlee et inspection de tous les consommateurs. Aucun restart seul,
aucun remplacement du parent, aucune reouverture ou rollback dangereux.
Le demarrage q peut bloquer le BFF via depends_on healthy : ne pas
contourner cette condition pour obtenir un resultat favorable.

Conditions restant a satisfaire :

1. Fermeture CP311 Linux **complete, approuvee et hashee**, dont PyYAML
   compatible, images deja chargees par digest, runtime et dependances
   revus. Les locks Docker CP313 ne valent pas une fermeture CP311.
2. Rendus Compose natifs et tests de refus des overrides/aliases ;
   inspect Engine reel et inventaire des autres conteneurs locaux,
   absence d'alias RW, sous-montage ou propagation non revue.
3. UID/GID effectifs, groupes, traverse/lecture et refus d'ecriture sous
   l'identite API ; proprietaires/permissions/lock reels, userns/remap,
   rootless et controles de securite du noyau.
4. Executer D01-D20 selon leurs prerequis, sans skip/xfail ; conserver
   JUnit, commit barriers, logs de readers/ASGI et hashes avant/apres.
   Une simulation de metadonnees n'est pas une preuve DAC.
5. Valider interruptions et cas de parent remplace, FD ancien et
   lecteurs multiples. Un open ou travail admis avant publication peut
   survivre ; le latch n'annule ni requete ni worker deja demarre.
6. Revoir separement les writers Lite 0644 et leurs autorites signees :
   ils restent inchanges et **non declares compatibles** avec la
   nouvelle politique 0440. Aucun manifeste signe n'est deplace.
7. Produire ensuite un vrai bundle/controleur/installation de helper
   coherents, de nouvelles attestations CI et approbations administrateur,
   et une qualification des images effectivement destinees a usage.
   Ce paquet n'effectue ni ce packaging operationnel ni son activation.

**Conclusion : preparation candidate demontree ; campagnes Docker et
Debian a realiser. Aucune autorisation operationnelle ou de passage
automatique a ready n'est accordee.**
