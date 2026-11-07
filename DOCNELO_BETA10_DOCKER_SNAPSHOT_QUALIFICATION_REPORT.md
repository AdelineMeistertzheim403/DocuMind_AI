# Docnelo Public Beta 10 - Qualification des snapshots Docker

Date : 2026-11-07.
Candidat : `733f224dd7881fbd088e04a23726dc4a07c922c1`.
Branche : `release/docnelo-public-beta-10-20261106`.

**NO-GO pour declarer les six scenarios qualifies.** Leur activation
necessite plus qu'un environnement Docker : quatre tests referencent un
contrat de restauration absent du candidat et une migration historique.
Aucune protection n'a ete contournee. Aucun laboratoire avec base ou volume
n'a ete cree ; aucune restauration physique n'est annoncee comme executee.

La CI precedente reste reussie sur ce SHA. Elle ne prouve pas ces six cas,
comme indique dans `DOCNELO_BETA10_REMOTE_CI_QUALIFICATION_REPORT.md`.

## 1. Perimetre et etat Git

Worktree examine :
`deliveries\docnelo-public-beta-release-20261106\source`.
HEAD et branche verifies avant et apres les controles. Aucun fichier suivi,
test, code metier, workflow ou configuration de production n'est modifie.
Aucun commit, push, merge, lancement Actions, acces VPS ou deploiement.

Le rapport de CI distante preexistant reste non suivi et preserve.
Le present rapport est le seul nouveau fichier du worktree release.
Le commit qualifie est inchange ; les travaux du worktree principal ne sont
pas selectionnes.

## 2. Les six scenarios et leurs attentes exactes

Le premier test est parametre par `legacy` et `closed`, soit quatre variantes.
Le second est parametre par le champ PostgreSQL falsifie, soit deux variantes.

| Scenario | Attente du test existant | Resultat de cette mission |
|---|---|---|
| Moderne, source ouverte | Capturer quatre admissions et `closed=false`, restaurer fidelement, puis fermer uniquement la copie | Bloque, non execute |
| Moderne, source fermee | Preserver quatre admissions et `closed=true`, restaurer et conserver la fermeture | Bloque, non execute |
| Legacy synthetique, source ouverte | Rendre une copie ancienne non certifiee pour le quota, restaurer le quota puis fermer la copie | Bloque, non execute |
| Legacy synthetique, source fermee | Meme compatibilite ancienne et conservation du compteur, sans toucher la source | Bloque, non execute |
| Falsification de `issued_count` | Une modification PostgreSQL reelle doit etre refusee avec `Integrity mismatch: public_registration_quota` | Bloque, non execute |
| Falsification de `closed` | Meme detection apres modification reelle du champ de fermeture | Bloque, non execute |

Les quatre variantes de restauration exigent aussi une archive contenant
`documents/fictitious.txt`, la projection complete du quota
`id, issued_count, closed`, une base restauree unique et absente avant
creation, un `pg_restore --no-owner --exit-on-error`, la preservation des
hashes de tous les fichiers du snapshot et l'absence de mutation du quota
source. Elles ne testent pas directement dix admissions : le profil
historique de cette fixture fixe la limite a cinq et en cree quatre.

## 3. Prerequis identifies

| Prerequis | Contrat lu dans le candidat |
|---|---|
| Activation | `TEST_SNAPSHOT_COMPOSE` doit contenir une liste JSON de commande Compose |
| Hote Docker | Prefixe exact `docker --host npipe:////./pipe/dockerDesktopLinuxEngine` |
| Projet | Element exact `documind-s14-4-backup-20261025-f94b` dans la commande |
| Base applicative de test | `TEST_DATABASE_URL` PostgreSQL, base vide dediee a chaque fixture |
| Utilisateur / base du backup | `documind_test` / `documind_beta_backup`, imposes par les commandes des tests |
| Schema de test | La fixture `app` execute Alembic jusqu'a `head` |
| Source documentaire | Volume neuf contenant `documents/fictitious.txt`, exclusivement synthetique |
| Services / volumes | Services `db`, `api`, `web` ; volumes nommes aux cibles PostgreSQL, `/app/var` et `/app/lifecycle` |
| Quiescence | Seul `db` fonctionne ; aucun autre client PostgreSQL ni conteneur non controle sur les volumes/reseaux |
| Capture lifecycle | Cinq magasins SQLite prives et distincts, schemas exacts, verrou exclusif |
| Outils | Docker Compose avec support `!reset`, Python/dependances du candidat, pg_dump/pg_restore PostgreSQL 17 |

Les cinq magasins sont `registry`, `witness`, `authenticated`, `holds`,
`admission_anchor`. `backend\lifecycle_snapshot.py` exige
`LIFECYCLE_DATA_ROOT` et les cinq variables de chemins correspondantes,
des repertoires prives, des fichiers reguliers sans liens, schemas et
integrite SQLite valides. Leur archive et son identite de capture sont
verifiees dans le backup complet de format 3.

Un laboratoire conforme demanderait des ressources neuves identifiees par
des labels uniques, images locales controlees, identifiants fictifs,
reseaux isoles, aucun volume externe ni bind de donnees existantes,
sources du candidat en lecture seule et nettoyage cible des seules
ressources creees. Aucun socket Docker ne doit etre rendu accessible a
un service applicatif non controle.

## 4. Compose et outils examines

`compose.yaml` n'est pas utilisable tel quel pour cette qualification :
il charge `.env`, utilise des noms/identifiants par defaut, expose des ports
locaux et depend d'un fichier de controle de restauration fourni.
Ce fichier `.env` n'a pas ete ouvert ni charge par une commande Compose.

`compose.public-beta-test.yaml` est explicitement synthetique et exige un
projet unique et un env fictif, mais ne satisfait pas le contrat de backup :
sa base se nomme `documind_beta_recipe`, PostgreSQL utilise un tmpfs plutot
que le volume nomme attendu, et le service API n'a pas le montage persistant
`/app/lifecycle` requis. Son profil SMTP/TLS ne remplace pas celui du backup.
Aucune de ces configurations n'a ete lancee ou modifiee.

`tools\backup_local.py::create_backup` controle la configuration resolue,
les conteneurs attaches aux volumes et les reseaux prives, refuse les
clients PostgreSQL actifs, puis capture le dump, les documents et les cinq
magasins lifecycle avec des conteneurs de capture sans reseau.
Il produit un manifeste de format 3 avec SHA-256 et preuves de quiescence.

`tools\verify_snapshot.py` verifie les archives, hashes, schemas SQLite
et empreintes de tables PostgreSQL. Un backup complet n'est jamais une
autorisation de reprise : `s2_recovery_authorized` doit rester faux.

`tools\validate_restore.py` utilise desormais un laboratoire marque
`.synthetic-only`, `DOCUMIND_RESTORE_LAB=isolated`, un endpoint loopback
explicite avec base administrative `documind_restore_admin`, un cluster
`documind-restore-lab`, des noms `documind_restore_<12 hex>` et une
restauration en quarantaine. Il verifie notamment les documents, les
tombstones et les risques de resurrection, sans autoriser ouverture ou API.

## 5. Blocages confirmes et incompatibilites supplementaires

**Fonction absente.** Les quatre variantes importent
`seal_restored_registration` depuis `tools.validate_restore` des leur entree.
L'inspection Python confirme `hasattr(...)=False`.
Une base Docker ne peut pas satisfaire cet import. Aucune fonction de
compatibilite, monkeypatch ou ancienne implementation n'a ete injectee.

**Migration obsolete.** Alembic confirme `head=['0008']`.
La fixture de test migre a head, mais les quatre variantes exigent un
manifeste `migration=='0007'`. `create_backup` lit la revision reelle dans
`alembic_version`. Downgrader, falsifier cette revision ou forcer une ancienne
fixture ne qualifierait pas le candidat beta dix comptes.

**Copies legacy incompatibles avec le format 3.** Les deux variantes legacy
modifient `integrity.json` en retirant le quota, mais conservent le SHA-256
initial de ce fichier dans `manifest.sha256`. `verify_capture` verifie ce
hash avant les tables ; la copie ainsi construite serait refusee pour
checksum incoherent, avant le controle historique attendu.
Il s'agit d'une deduction directe du code, pas d'une restauration executee.

**Contrat de plateforme historique.** Le socket nomme Windows est exige
dans les six cas ; ils ne sont pas portables tels quels sur le runner Linux.
Le projet historique est fixe, contrairement au besoin d'un identifiant
jetable unique. Son absence locale a ete verifiee par les labels Compose
des conteneurs, volumes et reseaux ; aucune ressource portant ce projet
n'a ete creee ou reutilisee.

**Quiescence a preparer explicitement.** Les tests appellent le backup alors
que la fixture FastAPI est ouverte et que ses engines utilisent leurs pools.
La garde du backup refuse tout autre client PostgreSQL. L'absence de
sessions n'a pas ete prouvee par execution ; un futur laboratoire doit
etablir cette quiescence reellement, sans desactiver la garde.

Ces constats ne demontrent pas un echec du moteur actuel de backup en
production. Ils demontrent que les tests dormants ne constituent pas,
en l'etat, une qualification executable de ce candidat.

## 6. Controle execute : aucun faux succes

Depuis le worktree release, les deux fonctions ont ete selectionnees
explicitement avec :

```text
python -m pytest -q -rs -p no:cacheprovider --require-no-skips
  tests\test_public_beta_snapshot.py::test_real_backup_and_independent_restore_preserve_then_seal_quota
  tests\test_public_beta_snapshot.py::test_actual_postgresql_field_tampering_is_detected
```

Un `--basetemp` dedie et un JUnit hors Git ont ete fournis.
Les variables `TEST_SNAPSHOT_COMPOSE`, `TEST_DATABASE_URL` et `DATABASE_URL`
ont ete retirees uniquement de ce processus de controle ; IA desactivee,
cle OpenAI vide, inscriptions desactivees.

**Resultat : 6 cas collectes, 6 ignores, 0 execute, code pytest 1.**
La garde `--require-no-skips` affiche
`Required qualification contains skipped tests` et refuse la qualification.
Le JUnit contient six elements skipped ; son absence de failures/errors
ne signifie pas succes. Ce controle de blocage ne remplace pas l'execution
des scenarios avec preconditions satisfaites.

Preuve conservee hors Git :
`files\snapshot-preflight.xml`, session
`12ffa574-cb17-4a50-a650-3af684ea07ab`,
SHA-256 `57b6719bbe54242a6b209dce2e6ba797aba960fdcff8d2eb222cd7708c038ebf`.
L'avertissement Starlette/httpx preexistant reste visible.

## 7. Garanties reellement verifiees et nettoyage

Aucun conteneur, reseau, volume, serveur PostgreSQL ou secret de laboratoire
n'a ete cree. Les marqueurs de saut ont empeche l'execution des fixtures
applicatives des six cas : aucune commande backup/restore n'a ete appelee.
Les inspections Docker restent en lecture seule.

Le repertoire temporaire propre au controle a ete nettoye s'il existait ;
le JUnit est conserve comme preuve. Aucun nettoyage global Docker,
`prune`, suppression de volume existant ou arret de service preexistant.
L'inventaire des conteneurs en cours reste vide, comme au debut.
Les fichiers suivis et HEAD restent inchanges.

Ne sont pas verifies par cette mission : creation physique d'un snapshot,
fidelite de restauration PostgreSQL, conservation documentaire/lifecycle,
refus de falsification sur une base reelle et nettoyage d'un laboratoire
Compose execute. Ces garanties demeurent non qualifiees ici.

## 8. Recommandation de qualification

**Conserver pour l'instant une qualification de release separee et
bloquante**, avec rapport et `--require-no-skips`. Ne pas ajouter tels quels
ces tests historiques a la CI Linux obligatoire : ils ne sont ni portables
ni alignes sur le contrat actuel.

Une intervention autorisee distincte devra aligner les tests sur la
restauration actuelle en quarantaine, la migration 0008, la provenance
legacy coherente et un projet Docker synthetique unique ; elle devra
preserver les assertions d'integrite, de compteur, de fermeture/refus et
de non-mutation de la source, et couvrir les cinq magasins lifecycle.
Ce n'est pas une autorisation de modifier les tests dans cette mission.

Apres qualification native reussie de ce laboratoire, recommander
l'integration de son noyau portable dans le job Linux obligatoire ou une
etape Linux requise, afin de ne plus laisser ces contrats vieillir derriere
des skips opt-in. Toute modification CI exige une autorisation distincte ;
aucun workflow n'a ete ajoute ou declenche.

**NO-GO pour la qualification snapshots et toute decision de production
reposant sur ces six scenarios.** Le blocage doit etre resolu et les preuves
reelles obtenues avant de les annoncer qualifies. Aucun contournement,
deploiement ou ouverture publique n'est autorise par ce rapport.
