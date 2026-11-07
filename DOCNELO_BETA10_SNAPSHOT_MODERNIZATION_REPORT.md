# Docnelo Public Beta 10 - Modernisation des snapshots Docker

Date de qualification : 2026-11-07 (UTC).

**Decision : GO pour la qualification du contrat de capture/restauration en laboratoire.**
La campagne finale execute 19 tests, dont 12 scenarios physiques, avec
`--require-no-skips` : **19 passes, 0 echec, 0 erreur, 0 ignore**.
Deux restaurations PostgreSQL et leurs fichiers ont effectivement ete verifies.
Ce resultat ne constitue ni une autorisation de recuperation S2, ni un GO production.

## 1. Perimetre et etat Git

Worktree utilise : `deliveries/docnelo-public-beta-release-20261106/source`.
Branche : `release/docnelo-public-beta-10-20261106`.
HEAD initial et final : `733f224dd7881fbd088e04a23726dc4a07c922c1`.

Ce SHA reste le candidat qualifie par la CI distante de reference. Les nouveaux
tests et leur laboratoire sont une surcouche locale **non commitee**, non publiee,
qui n'a pas encore ete qualifiee par GitHub Actions. L'index reste vide.

Le worktree principal `branding/docnelo` conserve ses 59 fichiers suivis deja
modifies ; aucune intervention n'y a ete effectuee. Les deux rapports locaux
preexistants de qualification distante et de blocage historique sont conserves.

| Fichier de cette mission | Modification |
| --- | --- |
| `tests/test_public_beta_snapshot.py` | Conservation des 7 cas unitaires ; remplacement des 6 variantes Docker obsoletes par 12 cas physiques actuels |
| `tests/snapshot_docker_lab.py` | Fixtures synthetiques, cinq magasins reels, empreintes source, migrations et gestion des bases de quarantaine |
| `ops/testing/compose.snapshot-lab.yaml` | Projet Linux prive, images locales explicites, volumes nouveaux et services non publics |
| `ops/testing/Dockerfile.snapshot-lab` | Image locale d'outils Docker Compose, PostgreSQL 17 et dependances de test |
| `ops/testing/run_snapshot_lab.py` | Controle des ressources, execution zero-skip et nettoyage du projet |
| `DOCNELO_BETA10_SNAPSHOT_MODERNIZATION_REPORT.md` | Present rapport |

`tools/backup_local.py`, `tools/verify_snapshot.py`, `tools/validate_restore.py`,
le code metier, les migrations et les workflows de ce worktree sont inchanges.
Aucun commit, push, merge, workflow distant, publication d'image, acces VPS ou
deploiement n'a ete effectue. Les inscriptions publiques ne sont pas modifiees.

## 2. Audit et nouveau contrat

Les anciens tests ne representaient plus le systeme actuel : import de
`seal_restored_registration` supprime, revision `0007` imposee a une base `0008`,
archives legacy obtenues en modifiant un manifeste de capture moderne, projet
Docker fixe et socket Windows obligatoire. Le client FastAPI pouvait egalement
maintenir une connexion contraire aux gardes de quiescence actuelles.

Les garanties historiques conservees sont le compteur cumulatif, le champ
`closed`, la detection des falsifications et la lecture des inventaires anciens.
Une restauration ne doit plus forcer la fermeture en modifiant les donnees :
elle conserve fidelement le quota et reste en quarantaine, sans API ni
autorisation d'ouverture.

Le contrat qualifie est maintenant :

1. Base source PostgreSQL 17 neuve, reellement migree a Alembic `0008`.
2. Capture reelle format 3, `integrity_version=2`, des quatre charges utiles :
   `database.dump`, `documents.tar.gz`, `lifecycle.sqlite.tar.gz`, `integrity.json`.
3. Verification SHA-256 des charges utiles et des cinq magasins lifecycle,
   schemas SQLite exacts, versions et `PRAGMA integrity_check`.
4. Restauration par le vrai CLI `validate_restore.py` et `pg_restore`, dans une
   nouvelle base `documind_restore_<12 hex>` et un repertoire neuf marque
   `.synthetic-only`.
5. Egalite de toutes les lignes des tables publiques entre source et restauration ;
   verification des octets du document, de ses metadonnees, page et analyse.
6. Conservation de quatre admissions et du quota pour `closed=false` et
   `closed=true`, avec les quatre autorisations de quarantaine toujours fausses.
7. Refus des charges alterees et des archives legacy incompletes avant creation
   de la base ou du repertoire de restauration.
8. Conservation des lignes source et des octets des cinq bases SQLite et du
   document ; aucun changement des charges utiles de la sauvegarde.

Les preuves Docker ne reposent sur aucun mock. Les mocks des sept anciens cas
unitaires d'inventaire restent des tests unitaires, distincts des preuves physiques.

## 3. Laboratoire synthetique et quiescence

Chaque campagne recoit un projet unique `documind-snapshot-<12 hex>`. Le lanceur
verifie l'absence de ressources existantes, y compris les noms exacts des volumes
et du reseau, avant toute creation. Les images sont resolues en identifiants
locaux immuables ; Compose interdit leur telechargement implicite.

Le laboratoire ne reprend aucun fichier Compose de production, aucun fichier
`.env` reel, aucun volume externe, aucun port publie et aucun montage de donnees
existantes. Les fichiers `.env*.example` sont les seuls fichiers d'environnement
acceptes a la racine du code monte. Le mot de passe PostgreSQL est une valeur
explicitement fictive ; les deux cles HMAC sont generees pour cette campagne.
IA desactivee, cle OpenAI vide et inscriptions desactivees dans les conteneurs.

La base source utilise un nouveau volume local **tmpfs**. Documents et lifecycle
utilisent deux nouveaux volumes locaux ordinaires, supprimes en fin de campagne.
Ils doivent survivre entre les captures offline successives : un volume tmpfs
perd son contenu apres le dernier demontage. Les deux racines sont initialisees
vides, rendues privees et attribuees a UID/GID 1000 par une operation offline
limitee a `CHOWN`, puis remplies sous cet utilisateur.

La fixture contient quatre comptes `example.test`, un document texte fictif,
une page, une analyse, quatre admissions witness, une ancre HMAC stabilisee,
un watermark registry et un legal hold avec miroir authentifie. Les cinq
magasins physiques independants sont `registry`, `witness`, `authenticated`,
`holds` et `admission_anchor`. Le verificateur synthetique existant controle leur
coherence avant capture et apres restauration.

Pendant une capture :

- Seul `db` tourne comme service Compose ; API et web sont arretes.
- Les one-offs API sont effectivement sans reseau, via l'override existant
  `networks: !reset []` et `network_mode: none`.
- Les connexions de test utilisent `NullPool` et sont fermees avant sauvegarde.
- Aucun autre client PostgreSQL ne doit rester connecte a la base source.
- L'exclusivite des volumes/reseaux et le verrou lifecycle sont controles par
  le code de sauvegarde existant, sans neutraliser ces gardes.

Le runner partage le namespace reseau de `db`, sans ajouter de point d'entree
au reseau protege. Il ne lance aucune application HTTP : le test de service
actif utilise seulement un processus `sleep`, qui doit faire refuser la capture.

**Frontiere de confiance importante :** le runner possede le socket Unix du
daemon Docker. Cela donne un pouvoir administratif sur ce daemon ; les labels,
les racines en lecture seule et les noms uniques ne constituent pas une
isolation de capacite face a un code malveillant ou un administrateur concurrent.
Les commandes mutables executees ici ciblent uniquement les ressources neuves
du laboratoire ; les inspections globales sont en lecture seule. Une garantie
absolue d'inaccessibilite des autres ressources exige un daemon Linux dedie,
jetable et sans donnees sensibles. Cette campagne utilise le moteur Linux local,
pilote depuis Windows, mais le lanceur ne depend d'aucun pipe Windows ni de
Docker Desktop : il est aussi utilisable sur un hote Docker Linux natif.

## 4. Resultats physiques finaux

Campagne : `documind-snapshot-f4b165493944`.
Debut pytest : `2026-11-07T11:06:35.377600+00:00`.
Duree pytest : 87,456 secondes.

| Scenario | Cas | Resultat et preuve |
| --- | --- | --- |
| Capture format 3 / restauration `closed=false` | 1 | PASS : vrai dump, vraie base restauree, toutes lignes egales, document et 5 SQLite verifies ; quota `(4,false)`, quarantaine |
| Capture format 3 / restauration `closed=true` | 1 | PASS : memes verifications physiques ; quota `(4,true)`, aucune reouverture |
| Falsification PostgreSQL `issued_count` / `closed` | 2 | PASS : vraies mises a jour SQL detectees par `Integrity mismatch: public_registration_quota`, puis remise a l'etat synthetique initial |
| Alteration des quatre charges utiles | 4 | PASS : `Backup payload checksum mismatch`, aucune base ni destination restauree creee |
| Archives historiques formats 1 / 2, schema 0007 | 2 | PASS : base historique reellement migree a 0007, dump/tar reels, inventaires coherents ; certificat quota uniquement v2 ; restauration S2 refusee |
| Client PostgreSQL vivant | 1 | PASS : refus `Uncontrolled PostgreSQL client session`, aucune sauvegarde creee |
| Service API vivant | 1 | PASS : refus `Only the database may run`, aucune sauvegarde creee |
| Contrats unitaires d'inventaire conserves | 7 | PASS |
| **Total** | **19** | **0 echec, 0 erreur, 0 ignore** |

Les versions historiques ne sont pas obtenues en relabellisant une capture
moderne : leurs lignes sont copiees dans une vraie base `0007` selon ses colonnes,
puis ses inventaires sont calcules sur cette base. La politique actuelle refuse
leur restauration car les cinq magasins lifecycle manquent. Aucune restauration
legacy n'est donc declaree qualifiee.

Les deux restaurations modernes produisent un vrai `quarantine.json` avec :
`status=quarantined`, un document verifie, cinq magasins restaures, aucun
document manquant ou non reference et `api_attached=false`,
`critical_mutations_allowed=false`, `opening_authorized=false`,
`s2_recovery_authorized=false`. La conservation de `closed=false` ne signifie
pas l'ouverture d'un service public.

Les lignes PostgreSQL source sont comparees pour toutes les tables publiques.
Les octets source verifies couvrent le document et les cinq fichiers SQLite ;
ce n'est pas une affirmation d'identite des fichiers operationnels temporaires
de verrouillage ni des fichiers internes du serveur PostgreSQL.

## 5. Preuves conservees et nettoyage

Les petits fichiers de preuve sont hors depot, dans le dossier de session :
`C:\Users\Adeline\.copilot\session-state\12ffa574-cb17-4a50-a650-3af684ea07ab\files\snapshot-native-05`.

| Fichier | SHA-256 |
| --- | --- |
| `snapshot-proofs.xml` | `196b743062676036af182cbe4fa299a57e46bf7672870a824872047df7a9c1c5` |
| `lab-resources.json` | `2e248b2c6525870cc5d0fe15cdd94a5104f6016aa8698bb26892057e3518c264` |
| `capture-closed-false.json` | `366c9a9fb2a67bfe742153f482cfa00028ffe4980eb43e1e458bdbf81db7946a` |
| `capture-closed-true.json` | `9ecedf5237caed6a5b0086bdac8ecba6d9bae286fda747e777225a8c8ce9d345` |

Les deux JSON de capture conservent les vrais manifestes, les SHA-256 des quatre
charges utiles et des cinq SQLite, les preuves de quiescence et les rapports
de quarantaine. Ils ne conservent ni cle HMAC ni mot de passe.

Capture ouverte synthetique : `729ea74c-7e57-4adc-9f9d-8ca0765415b6`,
base restauree `documind_restore_ef355e64bf80`.
Capture fermee synthetique : `fef3bc9a-b041-4a00-bf49-a6636dd62916`,
base restauree `documind_restore_434c1618db0a`.

Les contextes de test suppriment chaque base de restauration/historique et
verifient son absence. En fin de fixture, l'inventaire est exactement
`postgres`, `documind_restore_admin`, `snapshot_source`.
Le lanceur retire ensuite le runner, tous les conteneurs Compose, les trois
volumes et le reseau du projet. `lab-resources.json` confirme
`before={containers:[],volumes:[],networks:[]}` et le meme etat vide apres
nettoyage. Ces controles sont egalement passes pour les quatre campagnes
precedentes. Aucun nettoyage global Docker n'a ete utilise.

Les dumps, archives et repertoires de restauration temporaires etaient dans
le tmpfs du runner et ont disparu avec lui. Seuls les petits rapports de preuve,
les journaux de campagne et une image locale d'outils non publiee subsistent.

## 6. Difficultes et autres validations

Deux constructions initiales ont echoue : identifiant `sha256:` interprete
comme nom de registre par BuildKit dans `FROM`, puis CLI Docker manquante
dans Debian avec `docker.io --no-install-recommends`.
La construction finale utilise le tag local inspecte et les paquets
`docker-cli`, `docker-compose`, `postgresql-client-17` ; controle des versions
pendant la construction. Aucun daemon Docker n'est installe dans cette image.

| Campagne | Resultat initial | Correction du laboratoire |
| --- | --- | --- |
| `snapshot-native-01` | 7 passes, 12 erreurs de preparation, 0 ignore | Citation YAML du montage tmpfs contenant des virgules |
| `snapshot-native-02` | 7 passes, 12 erreurs de preparation, 0 ignore | Volumes documents/lifecycle persistants entre one-offs, initialisation privee |
| `snapshot-native-03` | 10 passes, 9 echecs, 0 ignore | `POSTGRES_DB` doit designer la source a sauvegarder, pas la base administrative de quarantaine |
| `snapshot-native-04` | 19 passes, 0 echec/erreur/ignore | Premiere qualification physique complete |
| `snapshot-native-05` | 19 passes, 0 echec/erreur/ignore | Campagne finale avec export des manifestes et quarantaines verifies |

Les journaux et XML des echecs restent conserves hors depot. Aucune erreur
n'a ete masquee, aucun test n'a ete rendu vert en contournant les controles.
Les corrections concernent uniquement le laboratoire, pas les outils metier.

Regressions Linux ciblees : les sept cas unitaires conserves et
`tests/test_snapshot_backup_integrity.py`, `tests/test_backup_offline_compose.py`,
`tests/test_restore_quarantine.py`, avec `--require-no-skips` :
**17 passes, 0 ignore**, 1,584 seconde.
Preuve `snapshot-unit-regression.xml`, SHA-256
`2fbcc1c8ba07289e55500dc9b5441cc37fe356a0371bbfd460fe03f69c206db5`.
Les sept cas communs ne sont pas des scenarios physiques supplementaires.

Les deux executions reussies et les regressions affichent un avertissement
Starlette/httpx preexistant, non masque. Les trois fichiers Python passent
l'analyse syntaxique AST ; Compose est effectivement resolu/controle par
les clients hote et Linux et execute ; le Dockerfile est effectivement construit.
`git diff --check` passe. Aucun formatter/linter n'est configure dans
`pyproject.toml` pour ces fichiers.

Images locales utilisees :

- Base de dependances : `docnelo-ci-fixture-proofs:20261106`,
  `sha256:3fa1e6edeec428f942ea32820a9abcc273542df7a4bb4a03ef3530080417b585`.
- Outils du laboratoire : `docnelo-snapshot-lab:733f224-local`,
  `sha256:8b0fc36c74ebb528728f074cf9e213e79ed400868199cca25c75de1c29eda4f3`.
- PostgreSQL/pgvector : `docnelo-ci-fixes-postgres:20261106`,
  `sha256:02be687f3378450482ec61fd0c902f02ac65daf1ca7fbbd7bc4a801f74d8e46d`.

## 7. Reexecution et recommandation CI

Depuis le worktree release, avec ces deux images deja construites localement
et une destination de resultats **nouvelle** :

```powershell
python ops\testing\run_snapshot_lab.py --runner-image docnelo-snapshot-lab:733f224-local --database-image docnelo-ci-fixes-postgres:20261106 --results C:\chemin\laboratoire-synthetique-neuf
```

Sur Linux natif, utiliser les chemins natifs equivalents. Le lanceur fournit
tous les prerequis et execute `tests/test_public_beta_snapshot.py` avec
`--require-no-skips`. Un pytest ordinaire sans activation du laboratoire laisse
volontairement les 12 cas physiques ignores ; il ne vaut pas qualification.
`TEST_SNAPSHOT_COMPOSE` n'est plus le contrat d'activation.

Recommandation : integrer ulterieurement les 12 preuves physiques dans une
etape bloquante du job Linux `python`, sur un runner/daemon jetable reserve
a cette campagne, avec preservation des XML, manifestes, quarantaines et
preuves de nettoyage meme en cas d'echec. Maintenir `frontend` obligatoire.
Ne pas accepter les skips physiques comme substitut a cette etape.

Cette integration necessite une autorisation distincte pour les workflows.
La preparation des images et dependances Linux devra etre rendue reproductible,
avec versions/digests controles, au lieu de dependre des seuls tags locaux
disponibles dans cette session. Pour l'instant, conserver cette campagne comme
qualification de release obligatoire separee ; la CI du SHA de reference reste
inchangee dans son perimetre.

## 8. Risques residuels et decision

Le laboratoire valide quatre admissions, pas une campagne de saturation a dix.
Il contient un seul document et un legal hold synthetique ; les tombstones,
receipts d'effacement et operations pendantes sont vides. Les controles de
resurrection sont executes, mais cette campagne ne prouve pas leurs refus sur
un corpus peuple de suppressions. Les autres preuves lifecycle/effacement de
la CI de reference ne sont pas remplacees par ces tests.

La quarantaine restauree ne constitue pas une remise en service : aucun test
de fraicheur independante externe, reprise operateur, ouverture publique,
RPO/RTO de production, sauvegarde a grande echelle, perte d'hote ou exercice
sur VPS n'a ete realise. Les manifestes de capture eux-memes ne sont pas
presentes comme signatures de provenance resistantes a un administrateur
malveillant. La limite de confiance du daemon partage demeure explicite.

**GO** : contrat moderne de sauvegarde/restauration physique et refus critiques
qualifies en laboratoire, sans tests ignores.
**NO-GO pour un deploiement ou une recuperation S2 sur cette seule preuve** :
revue, integration CI autorisee et qualification operationnelle distincte restent
necessaires. Aucun changement metier indispensable n'a ete identifie.
