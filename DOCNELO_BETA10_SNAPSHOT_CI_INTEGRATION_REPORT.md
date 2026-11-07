# Docnelo Public Beta 10 - Integration CI des snapshots Docker

Date : 2026-11-07, UTC.

**GO pour preparer la prochaine qualification GitHub Actions autorisee.**
Integration locale terminee : images construites, 19 tests snapshots passes
sans aucun ignore, 17 contrats/regressions passes sans aucun ignore, Actionlint
et controles syntaxiques valides. Aucune execution distante n'a ete lancee.
Ce rapport ne vaut ni qualification distante du nouveau candidat, ni GO production.

## 1. Architecture et durees

Le workflow existant `ci.yml` recoit un job **`snapshots`**, parallele a
`python` et `frontend`, sur **`ubuntu-24.04` GitHub-heberge**. Il n'a ni `needs`,
ni condition d'exclusion, ni environnement de production, ni service partage.
Il s'execute pour les memes evenements que la CI existante.

`publish.needs` devient exactement `[python, frontend, snapshots]`.
Un echec snapshots empeche donc toute publication. Le corps de `publish`,
sa condition main/hors-PR, les images officielles et leurs regles de publication
sont identiques au commit de reference. `deploy.yml` est inchange.
Les definitions completes des jobs `python` et `frontend` sont egalement
identiques au commit de reference, verification par comparaison YAML.

Le job Python, precedemment mesure a 24 min 35 s avec une limite de 35 min,
ne recoit aucune charge supplementaire et conserve son timeout. Un job parallele
evite de consommer ses 10 min 25 s de marge avec des telechargements et builds.
La duree globale devient celle du plus lent des jobs, pas leur somme.

Le nouveau job snapshots a une limite de **20 minutes** : marge pour les deux
builds et telechargements sur un runner neuf, qualification physique, nettoyage
et conservation des preuves. Le lanceur borne pytest a **600 secondes** au lieu
des 1800 secondes du laboratoire local initial ; demarrage Compose borne a
120 s, suppression du runner a 30 s et arret Compose a 120 s. Les inspections
Docker sont bornees a 30 s. Cela reserve une fenetre de nettoyage avant la
limite du job. Aucun timeout d'un job preexistant n'est augmente.

La campagne physique locale complete prend 92,78 s, dont 85,150 s de pytest.
Le build PostgreSQL mesure prend 19,11 s ; la reverification du build runner,
avec cache local, prend 0,60 s. Ces mesures ne constituent pas un benchmark
de build a froid sur GitHub ; le premier run distant devra confirmer la marge.

## 2. Audit Git et fichiers

Worktree : `deliveries/docnelo-public-beta-release-20261106/source`.
Branche : `release/docnelo-public-beta-10-20261106`.
HEAD initial et final : `733f224dd7881fbd088e04a23726dc4a07c922c1`.
Index conserve vide. Aucun commit, push, merge, publication ou deploiement.

L'audit initial retrouve les changements locaux de modernisation attendus,
sans changement metier. Ils sont integres tels quels au futur candidat ; seuls
les elements CI, reproductibilite et controle des preuves sont ajustes ici.

| Fichier | Etat dans cette phase |
| --- | --- |
| `.github/workflows/ci.yml` | Nouveau job parallele snapshots, artefacts toujours conserves, dependance publish |
| `ops/testing/Dockerfile.snapshot-lab` | Remplacement du tag local de dependances par une construction autonome epinglee |
| `ops/testing/compose.snapshot-lab.yaml` | Healthcheck corrige pour designer la vraie base source |
| `ops/testing/run_snapshot_lab.py` | Verification des 19 resultats et deux preuves physiques, limites temporelles, trace des erreurs de nettoyage |
| `tests/test_deployment.py` | Contrats de gates CI actualises ; tests du job parallele et du refus des preuves incompletes |
| `tests/test_release_security.py` | Contrat `publish.needs` actualise sans affaiblir les autres assertions |
| `DOCNELO_BETA10_SNAPSHOT_CI_INTEGRATION_REPORT.md` | Present rapport |
| `tests/test_public_beta_snapshot.py` | Modernisation preexistante conservee, non modifiee par cette phase |
| `tests/snapshot_docker_lab.py` | Fixtures physiques preexistantes conservees, non modifiees par cette phase |
| `DOCNELO_BETA10_SNAPSHOT_MODERNIZATION_REPORT.md` | Rapport historique conserve sans reecriture |

Les rapports locaux de qualification distante et de blocage historique restent
egalement presents et inchanges. Le worktree principal et ses 59 modifications
suivies preexistantes sont preserves.

Les fichiers metier `backend`, `tools`, `migrations`, les Dockerfiles officiels,
les verrous de dependances et les configurations de production ne sont pas
modifies. Aucune modification du mode d'inscription.

## 3. Reproductibilite et dependances Docker

L'image de test ne depend plus de `docnelo-ci-fixture-proofs:20261106`,
de `SNAPSHOT_PROOF_IMAGE` ou d'un tag preconstruit sur le poste.

Base Python du laboratoire, identique a la reference du Dockerfile officiel :
`python:3.13-slim@sha256:d879ed88565a7a3c614b980b369d4a5025a9d057b71f93d09fc6d0b2ca823a18`.
Version effectivement observee dans cette image : **Python 3.13.17**.
La precedente image locale de preuves etait distincte ; les 19 scenarios sont
donc reexecutes sur la nouvelle image, et non simplement declares compatibles.

Les sources Debian et Debian security pointent vers l'archive historique
`20261104T212339Z`. Versions directes explicites :

| Paquet | Version qualifiee |
| --- | --- |
| `docker-cli` | `26.1.5+dfsg1-9+deb13u1` |
| `docker-compose` | `2.26.1-4` |
| `postgresql-client-17` | `17.11-0+deb13u1` |

L'archive datee fixe aussi la resolution des dependances Debian transitives.
Seule l'expiration `Check-Valid-Until` des metadonnees historiques est desactivee
pendant `apt-get update` ; les signatures Debian, TLS et empreintes des paquets
restent controles. Aucun `allow-unauthenticated`, `trusted=yes` ou contournement
de verification n'est ajoute.

Les dependances Python utilisent les trois fichiers existants
`requirements.build.lock`, `requirements.runtime.lock`, `requirements.test.lock`,
avec `--only-binary=:all:` et **`--require-hashes`**, index PyPI explicite.
Les modules Python locaux necessaires sont copies depuis le checkout, sans
installation editable ni recuperation de code metier externe.
`pip check` confirme l'absence de dependances cassees.

PostgreSQL/pgvector est construit avec le **Dockerfile.db existant**, sa base
PostgreSQL 17 Alpine epinglee par digest et `build-materials/pgvector.json`.
Les sources et APK sont verifies selon le mecanisme existant ; leur installation
APK/compilation ne recupere aucun paquet mutable hors de ces materiaux.

Les tags `documind-ci-snapshot-runner` et `documind-ci-snapshot-postgres` sont
uniquement des noms locaux crees dans le job. Le lanceur les resout ensuite en
identifiants immuables avant Compose, dont `pull_policy: never` reste actif.
Ils ne sont jamais publies.

Images effectivement utilisees localement :

- Runner : `sha256:f2b7acb468c4584836fe4a0c037e91fa8ad571d6909ab8d2f3754f8f2bd4a33a`.
- PostgreSQL : `sha256:43ee6c6272808d27c724d9f4be925325c40795881451ff24dc41a239da6f933c`.

La reproductibilite signifie ici bases, versions et materiaux controles.
Elle ne promet pas des identifiants d'images bit-a-bit identiques entre builds :
horodatages de couches et compilation peuvent encore differer.

## 4. Commandes exactes du nouveau job

Premiere etape, Bash avec propagation des echecs de pipeline :

```bash
set -euo pipefail
evidence="$RUNNER_TEMP/documind-snapshot-qualification"
mkdir -p "$evidence"
docker info --format '{{.OSType}}' | tee "$evidence/engine.txt"
test "$(cat "$evidence/engine.txt")" = linux
test -z "$(docker ps -aq)"
test -z "$(docker volume ls -q)"
docker version > "$evidence/docker-version.txt"
docker compose version > "$evidence/compose-version.txt"
docker build --pull --file ops/testing/Dockerfile.snapshot-lab \
  --tag documind-ci-snapshot-runner . 2>&1 | tee "$evidence/runner-build.log"
docker build --pull --file Dockerfile.db \
  --tag documind-ci-snapshot-postgres . 2>&1 | tee "$evidence/postgres-build.log"
docker image inspect documind-ci-snapshot-runner documind-ci-snapshot-postgres \
  > "$evidence/images.json"
sha256sum requirements.build.lock requirements.runtime.lock requirements.test.lock \
  ops/testing/Dockerfile.snapshot-lab Dockerfile.db build-materials/pgvector.json \
  > "$evidence/source-materials.sha256"
```

Deuxieme etape :

```bash
set -euo pipefail
evidence="$RUNNER_TEMP/documind-snapshot-qualification"
python ops/testing/run_snapshot_lab.py \
  --runner-image documind-ci-snapshot-runner \
  --database-image documind-ci-snapshot-postgres \
  --results "$evidence/lab" 2>&1 | tee "$evidence/qualification.log"
```

Le lanceur execute dans le runner Docker :
`python -m pytest -q -rs -p no:cacheprovider --require-no-skips
--basetemp=/tmp/snapshot-proofs --junitxml=/results/snapshot-proofs.xml
tests/test_public_beta_snapshot.py`.

Il exige ensuite un XML avec exactement 19 tests, zero erreur/echec/ignore,
les deux JSON de capture verifiee, les deux quotas conserves, cinq magasins,
un document et toutes les autorisations de quarantaine fausses.
Une preuve absente ou incoherente fait echouer le lanceur.

Le nettoyage reste dans `finally`. Tout echec est propage, et les champs
`qualification_error` ou `cleanup_error` sont conserves dans le bilan lorsque
necessaire. Un runner residuel ou une ressource du projet restante fait echouer
la qualification. Aucun `continue-on-error` ni `|| true` n'est ajoute.

## 5. Isolation et protections

Le socket Docker donne un pouvoir administratif sur le daemon ; une racine
de conteneur en lecture seule n'annule pas ce pouvoir. L'isolation appropriee
retenue est donc un **job dedie sur une VM GitHub-hebergee jetable**, pas un
runner self-hosted partage ou un daemon contenant des ressources de production.
Le preflight refuse un daemon contenant deja des conteneurs ou volumes.

Le job n'utilise aucun secret de production ni connexion registry. Permissions
du workflow conservees a `contents: read`, checkout epingle sans credentials
persistants. Aucun token GitHub n'est passe au runner de preuves.
L'authentification registry reste exclusivement dans le job publish inchange.

Le laboratoire conserve ses projets aleatoires, images explicites, reseau
interne, aucun port public, volumes nouveaux et aucun `.env` reel/externe.
Base source tmpfs ; documents et lifecycle dans des volumes locaux neufs
supprimes a la fin. Code monte en lecture seule, donnees fictives et cles HMAC
generees pour la campagne. IA et inscriptions sont desactivees.

Les gardes de quiescence, checksum, schemas SQLite, migrations et restauration
ne sont pas modifies. Les one-offs de capture restent sans reseau ; les pools
PostgreSQL de test sont fermes avant capture. La restauration reste en quarantaine,
sans API et sans autorisation S2 ou ouverture publique.

La VM jetable borne les consequences d'une compromission du code teste au job
de test, mais ne transforme pas ses preuves en execution inviolable face a un
code malveillant possedant le socket. Revue du code, chaine de confiance et
absence de secrets demeurent necessaires.

La validation locale utilise le moteur Linux disponible sur l'hote partage,
avec ressources neuves strictement scopees ; elle ne prouve pas l'isolation
de la future VM GitHub. Aucune ressource existante n'est utilisee ou supprimee.

## 6. Resultats locaux et preuves

Campagne : `documind-snapshot-ffb3a81bc808`.
Debut pytest : `2026-11-07T11:26:23.096370+00:00`.

| Validation | Resultat |
| --- | --- |
| Builds runner autonome et PostgreSQL/pgvector | PASS |
| Snapshots complets, quota ferme/ouvert synthetique, restaurations physiques | 2 PASS |
| Falsifications PostgreSQL compteur/fermeture | 2 PASS |
| Alterations des quatre charges utiles | 4 PASS |
| Legacy reels 0007 formats 1/2, inventaire et refus S2 | 2 PASS |
| Refus client PostgreSQL actif et API active | 2 PASS |
| Cas unitaires d'inventaire conserves | 7 PASS |
| **Suite snapshots** | **19 passes, 0 erreur/echec/ignore**, 85,150 s |
| Gates CI, preuves incompletes, integrite/offline/quarantaine | **17 passes, 0 erreur/echec/ignore**, 1,717 s |
| Actionlint sur ci.yml et deploy.yml | PASS |
| `bash -n` sur les deux nouveaux scripts | PASS |
| Compose resolu par les clients hote et Linux, puis execute | PASS |
| Analyse syntaxique Python et `git diff --check` | PASS |
| Python/frontend et publish hors needs compares au HEAD | Identiques |

Les 17 contrats sont :
`test_deployment.py::{test_workflows_are_pinned_gated_and_never_deploy_on_push,
test_linux_ci_preserves_full_suites_and_required_production_proofs,
test_snapshot_ci_is_parallel_secretless_and_preserves_failure_evidence,
test_snapshot_runner_rejects_incomplete_physical_evidence,
test_new_registry_images_are_limited_to_certified_amd64}`,
`test_release_security.py::test_workflows_use_current_controller_and_bind_ci_statement`,
et les fichiers `test_snapshot_backup_integrity.py`, `test_backup_offline_compose.py`,
`test_restore_quarantine.py`, avec `--require-no-skips`.
Les tests de preuves incompletes ne remplacent aucune restauration physique.

Un avertissement Starlette/httpx preexistant reste visible dans chaque suite.
L'inventaire `pip check` en racine Docker non modifiable affiche aussi un
avertissement de cache non inscriptible, sans dependance cassee.
La premiere collecte Windows du journal de build a echoue sur un decodage
cp1252 ; les builds ont ete reverifies et la collecte corrigee pour conserver
les octets du journal. Aucun echec de test n'a ete masque.

Les deux vrais rapports de quarantaine identifient
`documind_restore_836acba0eb61` et `documind_restore_d3f478e3fa50`.
Ils confirment un document, cinq magasins, quota `(4,false)` / `(4,true)`,
aucun document manquant/non reference et aucune autorisation d'ouverture.
Les lignes de toutes les tables publiques et les fichiers restaures sont
verifies ; les donnees source restent identiques apres les operations.

Chaque base historique/restauree est supprimee et son absence verifiee.
Le bilan final indique exactement :
`before={containers:[],volumes:[],networks:[]}` et
`after={containers:[],volumes:[],networks:[]}`, sans erreur de qualification
ni de nettoyage. Les archives et repertoires temporaires disparaissent avec
le tmpfs du runner. Aucun prune ou nettoyage de ressources etrangeres.

Les preuves locales sont conservees hors depot dans le dossier de session
`C:\Users\Adeline\.copilot\session-state\12ffa574-cb17-4a50-a650-3af684ea07ab\files`.

| Preuve | SHA-256 |
| --- | --- |
| `snapshot-ci-contracts.xml` | `a398455bf30297845e5d108ae78b69554338514f5b4aac2329573fe510ef7602` |
| `snapshot-ci-native-01/snapshot-proofs.xml` | `bf8df4ea14a2a3a9c41670a6e348643fb393619584101aa2d3f118e295d68fee` |
| `snapshot-ci-native-01/lab-resources.json` | `382feb0b057938ccd072c7680cf7feb7b4226697dd2d7a4c0b598d3771411c4d` |
| `snapshot-ci-native-01/capture-closed-false.json` | `06c0361d98a8f23eee472a6338472c9ad28d0c51ce5d05e7f7c5aea5a5175a04` |
| `snapshot-ci-native-01/capture-closed-true.json` | `4a28b11b8cd12ac803eb28d93f3005a823ffd40d0733e13cfddf50bc2d12acff` |

## 7. Artefacts GitHub Actions prepares

Upload SHA-epingle, `if: always()`, `if-no-files-found: error`, retention 90 jours.
Nom : `documind-snapshot-proofs-${{ github.sha }}`.
Repertoire : `${{ runner.temp }}/documind-snapshot-qualification/`.

Il contient les journaux des builds/qualification, versions du moteur et
Compose hote, inventaire des images et empreintes des fichiers de materiaux,
puis dans `lab/` : JUnit, bilan des ressources et deux JSON comportant
les vrais manifestes de capture et rapports de quarantaine.
Les manifestes comprennent les SHA-256 des archives et des cinq SQLite.
Aucun dump volumineux, archive de donnees ou cle HMAC n'est conserve comme artefact.

Une erreur ordinaire de build/test/preuve/nettoyage n'empeche pas la tentative
d'upload. Une annulation brutale ou un timeout global peut interrompre le
nettoyage applicatif ou l'upload ; la VM reste jetable et le job n'est pas vert.
L'absence de preuves ne doit jamais etre acceptee comme qualification.

## 8. Risques residuels et prochaine qualification distante

L'archive Debian, PyPI et les materiaux epingles doivent rester accessibles.
Une indisponibilite ou un hash divergent fait echouer le build, sans fallback
mutable. Les versions Docker/Compose du runner heberge evoluent ; leur inventaire
est conserve et le premier run distant devra confirmer leur compatibilite.
Les materiaux Linux/amd64 et leur chaine de confiance existante sont conserves.

Le corpus reste volontairement petit : quatre admissions, un document,
un legal hold. Les tombstones/receipts d'effacement et operations pendantes
ne sont pas peuples. Aucune preuve de saturation a dix, RPO/RTO de production,
fraicheur externe ou remise en service operateur n'est ajoutee par cette CI.
La quarantaine n'autorise aucune recuperation S2.

Le nouveau job est bloquant pour **publish** et pour la conclusion globale
du workflow. Cela ne modifie pas automatiquement les required checks de
protection de `main`. Si cette protection ne requiert encore que `python`
et `frontend`, un administrateur devra ajouter manuellement **`snapshots`**
apres sa premiere qualification, pour rendre aussi les merges dependants
de ce controle. Aucune protection GitHub n'a ete modifiee ou presumee reconfiguree.

Etapes restantes, soumises a autorisation :

1. Revoir les changements et autoriser un commit coherent de la modernisation
   et de cette integration, sans inclure les artefacts du laboratoire.
2. Autoriser un push normal du nouveau candidat sur la branche release,
   relever son SHA complet et verifier le SHA distant.
3. Autoriser uniquement le lancement de `ci.yml` sur cette branche ; verifier
   `headSha`, les jobs `python`, `frontend`, `snapshots`, et `publish` ignore
   sur release, sans job Windows ni image officielle publiee.
4. Examiner les 19 cas sans ignores, deux restaurations, cinq magasins,
   refus critiques, preuves de nettoyage et artefacts avant tout GO distant.
5. Confirmer les protections `main` et effectuer, si necessaire et explicitement
   autorise, l'ajout manuel du required check `snapshots`.

**Decision finale : GO pour une prochaine CI distante autorisee ; aucune
qualification distante, publication, inscription publique ou production
n'est autorisee par ce seul resultat local.**
