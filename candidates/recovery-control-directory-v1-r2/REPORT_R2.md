# Docnelo V5.1 - Recovery Control Directory, revision r2

## Decision et perimetre

**GO pour soumission de cette revision a examen uniquement. Aucun GO P3,
Docker operationnel, S2, Lifecycle 10, Public Beta ou production.**
Le candidat v1 reste fige et n'est pas remplace automatiquement.
Aucun conteneur, serveur, service, migration, publication du latch ou
operation sur un namespace Debian n'a ete execute pendant cette preparation.

Nouvel espace : `candidates/recovery-control-directory-v1-r2`.
Les quatre Compose applicatifs, publishers, gardes operationnelles,
backend et middleware restent byte-identiques aux copies v1.
La correction est volontairement limitee au precontrole du lecteur P3.

## Incompatibilite et correction proposee

Constat fourni par l'operateur, non reproduit nativement ici :
Compose 2.26.1-4 rend `bind: {}` alors que le YAML contient explicitement
`create_host_path: false`, y compris avec `--no-normalize`.
La garde v1 refuse ces rendus ; aucun conteneur P3 n'avait ete cree.

Accepter globalement un dictionnaire vide supprimerait une preuve
necessaire. `validate_compose()` reste donc strict et inchange.
Le nouveau `preflight_p3.py` impose les controles conjoints suivants :

1. **Declaration source** : SHA approuve independamment, YAML sans
   ambiguite, sept parametres explicites, profil lecteur complet, deux
   binds longs RO avec `create_host_path: false` booleen present.
2. **Modele rendu** : projet, service, image locale par ID, UID/GID
   non-root, groupe lecteur, chemins, environnement, securites et limites
   conformes a la source. Seuls les rendus bind vide ou false explicite
   sont compatibles ; bind absent/null/true ou options inconnues refusent.
3. **Prerequis hote obligatoires** : source existante sans creation,
   garde v1 root:groupe/0750 et enfant0440, ancetres fiables, absence
   d'alias et montages herites non autorises, exclusion DockerRootDir,
   identite device/inode du marqueur P2, probe regulier et SHA approuve.

Le false perdu a la serialisation est restaure uniquement dans une
copie interne du modele apres validation source ; cette copie repasse
la garde historique. Le rendu brut conserve `bind: {}` dans les preuves.
Un JSON rendu seul ne permet jamais d'obtenir une approbation.
L'acceptation du precontrole signifie exclusivement
`REVIEW_ONLY_SOURCE_RENDER_HOST_PREFLIGHT`, avec `p3_go=false`.

Le precontrole ne lance ni Docker ni un sous-processus, ne lit aucun
dotenv, ne cree aucune source et ne publie jamais ready. Ses sorties
doivent etre neuves, hors candidats, namespaces et artefacts deja scelles.
Les refus sont explicites, avec exit non nul. Il n'existe pas de mode
permettant de sauter le controle source, hote ou P2.

## Changements et conservation

| Fichier r2 | Changement |
|---|---|
| `source/tools/preflight_recovery_compose.py` | Validation source/rendu/hote et collecte de preuves sans action Docker |
| `preflight_p3.py` | Point d'entree isole, verification de l'inventaire avant import |
| `tests/test_compose_source_rendered.py` | 51 cas additionnels |
| `run_local.py` | Ajout des nouveaux tests ; obligation des 119 cas P1 historiques |
| `README.md`, `DEBIAN_OFFLINE_PROTOCOL.md` | Portee r2, reprise sans mutation P2, nouveau preflight et inspections avant start |
| `BASELINE_REVISION.json`, `build_revision_inventory.py` | Ancrage et verification de la conservation v1/preuves |
| `REPORT_R2.md` | Present rapport |
| `REVISION_CHANGES.json`, `revision.patch` | Delta r2 par rapport au candidat v1, pas au depot actif |
| `PRESERVATION_VERIFIED.json`, `INPUTS.json`, `SHA256SUMS` | Conservation et integrite de la nouvelle revision |

Le generateur verifie les **248 fichiers** du candidat v1, son jeu de
fichiers exact et **45 artefacts historiques** de preuves/rapports/transfert.
Les 119 tests P1, le harness ASGI et les actifs P2/P3 sont conserves
byte-identiques, avec assertions supplementaires dans la nouvelle suite.
Les fichiers de provenance v1 herites ne constituent pas les preuves r2.
Le manifeste delta contient les chemins et SHA avant/apres de chaque
changement ; aucune application du patch au candidat fige n'est requise.

## Resultats effectivement obtenus

**Windows / CPython 3.13.7 : 170 tests reussis, 0 echec, 0 skip,
0 xfail ; aucune tentative d'E/S interdite enregistree.**
Soit les **119 cas P1 inchanges + 51 nouveaux cas r2**.
Campagne executee : `qualification/recovery_directory/windows-r2-preparation-002`.
Ses fichiers `junit.xml`, `result.json`, `pytest.log`, `cases.json`,
`dependencies.json`, `inputs.json` et `SHA256SUMS` sont conserves.
La campagne initiale 001 (169 cas, avant ajout du dernier controle de
protection des artefacts scelles) reste conservee sans modification.

Les nouveaux cas couvrent notamment : false source absent/true/0/chaine,
bind manquant, bind direct du latch, alias, RW, source absente, mauvais
UID/GID/groupe, chemins divergents, ressources heritees, modele et source
contradictoires, empreintes et record P2 invalides, declarations dupliquees,
conservation du rendu brut, refus d'ecrasement et de sortie sous preuve scellee.
Le cas source absente execute la garde hote originale avec stat Linux
synthetique ; il ne cree ni ne consulte un namespace reel.

La syntaxe des cinq fichiers Python nouveaux/modifies est analysee
avec la grammaire Python 3.11. Ce n'est pas une execution CPython 3.11.
Les tests de metadonnees Linux/UID/GID sont des modeles sous Windows,
pas une demonstration des permissions ou du bind effectif sous Debian.

## Protocole Debian et limites restantes

`DEBIAN_OFFLINE_PROTOCOL.md`, section P3-r2, remplace le controle rendu
seul par source + rendu + parametres + marqueur P2 + source hote existante.
Le YAML original est conserve sans fusion d'overrides ; le rendu JSON
vide ne doit jamais devenir lui-meme un nouveau fichier Compose.
Les preuves doivent etre creees sous un nouveau repertoire de
`/home/adeline/docnelo-lab/development/v5.1-hardening/quarantine-debian-evidence/`.
Le preflight est en lecture seule sur le LAB et sur les preuves P2.
Ne pas relancer provision/publish/chmod ni une transition du latch pour
la seule reprise r2. Aucun acces au latch restaure reel n'est necessaire.

La suite Docker reste **NON EXECUTEE** : rendu natif complet 2.26.1-4,
Debian13/CPython3.11.18, identites effectives, userns/remap, DAC et RO
Engine, propagation atomique et campagne D01-D20. Une fermeture offline
CP311 complete, PyYAML compatible et images locales revues restent requis ;
aucun wheel ni image supplementaire n'est fourni par cette revision.

Le profil rendu est intentionnellement exact : une normalisation native
supplementaire non revue fera refuser, et ne doit pas etre contournee.
Le DockerRootDir est fourni explicitement ; le preflight ne prouve pas
son origine et exige une preuve locale Docker info revue separement.
La concordance documentaire ne prouve pas le comportement de creation
du daemon ni l'absence d'alias dans les autres conteneurs locaux.

Un rename/suppression entre le preflight et create reste un risque TOCTOU.
Apres une autorisation future distincte seulement : gel operateur,
reverification des sources/empreintes/identites avant et apres create,
inspection de tous les mounts et protections **avant tout start**.
Le test negatif D11 natif reste indispensable et doit utiliser un
nouveau namespace autorise, jamais un namespace P2 existant.
Rien de ces actions n'est execute ou autorise automatiquement ici.

## Integrite et proposition de transfert

`INPUTS.json` et `SHA256SUMS` couvrent la revision ; les locks de
dependances herites sont inventories et la campagne capture ses versions
installees. Les SHA ne constituent pas une signature : verifier l'ancre
du transfert par un canal de confiance independant.
Le paquet r2 doit etre extrait dans un nouvel emplacement de development,
sans remplacement du candidat v1, d'une release ou d'une evidence.
La revision est proposee pour examen ; toute qualification Docker
supplementaire exige une decision et une evidence distinctes.
