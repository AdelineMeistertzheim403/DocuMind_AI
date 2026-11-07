# Docnelo Public Beta 10 - Permissions du laboratoire snapshots Linux

Date : 2026-11-07, UTC.

**GO local pour le correctif de collecte des preuves.**
La reproduction sur un filesystem Linux ext4 confirme le refus DAC initial,
puis le correctif passe **19 tests snapshots, dont 12 scenarios physiques,
avec 0 echec, 0 erreur et 0 ignore**. Les deux restaurations PostgreSQL,
leurs manifestes/rapports de quarantaine et le JUnit sont effectivement verifies.
Les 19 contrats/regressions cibles passent egalement sans ignore.

Ce resultat concerne le correctif local non commite. Il ne requalifie pas
retroactivement le run distant 42368987363 et ne constitue pas un GO production.
Aucun commit, push, lancement Actions ou deploiement n'est effectue.

## 1. Cause technique et audit

Le candidat publie `11e55670e792af9c6fb08ca7fc3a24be08028be9` creait les
resultats avec `Path.mkdir()` sur l'hote, puis les montait a `/results`.
Le processus pytest tournait en **UID/GID 0:0 avec `--cap-drop ALL`**.
Un dossier hote usuel appartenant au compte runner et de mode 0755 ne donne
pas l'ecriture a cet UID 0 prive de `CAP_DAC_OVERRIDE`.

La micro-reproduction Linux de cette campagne utilise un dossier neuf
UID/GID **1001:1001**, mode **0755**, monte dans un conteneur UID/GID 0:0
sans capacites. L'ecriture de `snapshot-proofs.xml` retourne bien
`PermissionError: [Errno 13] Permission denied`.

Le run distant avait interrompu la generation du JUnit et des traces finales.
Ses deux causes individuelles d'echec ne peuvent pas etre reconstruites a partir
de traces absentes. En revanche, les deux scenarios de restauration passent
maintenant sous DAC Linux natif avec collecte fonctionnelle et code metier
inchange : aucune assertion de restauration n'a ete assouplie.

Docker Desktop Windows presente les bind mounts selon sa couche de partage
et les ACL Windows, sans reproduire necessairement l'ownership/DAC d'un bind
mount ext4 natif. Le precedent succes sous Windows ne prouvait donc pas le
contrat de permissions du runner Linux. Le correctif conserve un controle
reel d'acces sur les deux plateformes, sans presumer de leur equivalence.

## 2. Fichiers modifies

| Fichier | Changement |
| --- | --- |
| `ops/testing/run_snapshot_lab.py` | Preparation privee d'un dossier neuf, GID explicite, preflight ecriture/lecture reel, umask prive de pytest |
| `tests/test_deployment.py` | Deux tests de permissions : parent inchange et refus d'un dossier existant sans mutation |
| `DOCNELO_BETA10_SNAPSHOT_LINUX_PERMISSIONS_FIX_REPORT.md` | Present rapport |

`tests/test_public_beta_snapshot.py`, ses fixtures, les outils de sauvegarde,
verification/restauration, migrations, images, Compose et workflows sont
inchanges. Aucun compte reel ni etat d'inscription publique n'est modifie.
Les comptes et documents de la qualification sont exclusivement synthetiques.

Le rapport distant NO-GO preexistant reste conserve et inchange.

## 3. Contrat UID/GID retenu

Le dossier est cree avec `exist_ok=False`, initialement prive en mode 0700.
Un chemin deja existant provoque une erreur avant tout changement de permission.
Sous POSIX, le lanceur verifie que le nouveau dossier appartient au caller.
Son GID est aligne sur **`os.getegid()`** seulement si necessaire, sans changer
son UID. Seul ce dossier neuf est ensuite rendu **0770**.
Aucun parent, dossier partage, groupe systeme ou socket Docker n'est modifie.

Le processus de preuves reste **UID 0**, mais son GID primaire devient celui
du dossier/runner hote : `--user 0:<GID hote>`.
Il n'a pas besoin d'une capacite DAC pour ecrire : il dispose des droits de
son groupe sur ce seul bind mount. Aucun groupe supplementaire n'est ajoute
au processus de preuves.

Pytest est lance par :

```sh
umask 007; exec python -m pytest "$@"
```

Tous ses arguments existants sont conserves, notamment `--require-no-skips`
et les 19 tests du fichier complet. Les nouveaux fichiers de preuve sont donc
crees **0660**, avec GID hote ; le runner hote les lit via son groupe primaire.
Les chmod explicites internes des fichiers de quarantaine/lifecycle restent
regis par les outils metier inchanges.

Mesures effectives de la campagne Linux :

| Ressource/processus | UID | GID | Mode/capacites |
| --- | --- | --- | --- |
| Lanceur Linux synthetique | 1001 | 1001 | CapEff=0, no-new-privileges=1 |
| Dossier de resultats neuf | 1001 | 1001 | 0770 |
| Processus de preuve/preflight | 0 | 1001 | CapEff=0, no-new-privileges=1 |
| JUnit et deux JSON de capture | 0 | 1001 | 0660, lisibles par UID 1001 |
| Bilan du lanceur `lab-resources.json` | 1001 | 1001 | 0644, sous le dossier prive 0770 |

Le GID 1001 est celui de cette reproduction, pas une constante du correctif.
Sur GitHub Actions, le GID effectif du compte runner est automatiquement utilise.
Sous Windows, GID 0 est conserve, sans chown/chmod POSIX ; la creation privee
et le preflight reel evitent de declarer arbitrairement l'acces valide.

## 4. Preflight physique avant les tests

Avant de demarrer PostgreSQL, un conteneur jetable de la meme image :

1. Tourne en UID 0 et GID hote, racine en lecture seule, `cap-drop ALL`,
   `no-new-privileges`, sans reseau et sans socket Docker monte.
2. Cree reellement `results-write-probe.txt` dans le bind mount `/results`,
   avec umask 007, puis relit et compare son contenu.
3. Mesure UID/GID, modes, CapEff et NoNewPrivs depuis le filesystem et `/proc`.
4. Permet au lanceur hote de relire et comparer ces memes octets.

Sous POSIX, ownership et modes 0770/0660 sont aussi controles. Tout refus
d'ecriture, de lecture ou toute incoherence fait echouer la campagne avant
les tests. Le fichier temporaire de probe est supprime.
Les mesures et les deux confirmations de lecture sont preservees dans
`lab-resources.json`, champ `results_permissions`.

Le preflight porte le nom et le label controles du runner de preuves. En cas
d'erreur/timeout, le nettoyage existant peut donc supprimer ce conteneur
exactement comme le runner pytest ; aucune nouvelle ressource non tracee
n'est introduite.

## 5. Qualification Linux native

Un volume Docker Linux neuf a servi de filesystem **ext4**, avec un lanceur
Python Linux UID/GID **1001:1001**. La source y est copiee depuis les seuls
fichiers suivis du worktree, puis rendue en lecture seule pour ce lanceur.
Les chemins de source/resultats sont les memes chemins natifs visibles par
le daemon, sans bind mount NTFS pour les preuves.

Les commandes sont pilotees depuis Windows, mais le caller, les resultats,
les checks DAC et les processus pytest de cette qualification utilisent bien
le kernel/filesystem Linux. Il ne s'agit pas d'une nouvelle VM GitHub distante
ni d'un daemon physiquement dedie : le moteur disponible reste partage.
Les commandes mutables ciblent uniquement les ressources neuves etiquetees.
Le caller synthetique a acces au socket Unix via son groupe de socket, comme
un runner hote administrant Docker ; le conteneur de preuves ne recoit aucune
capacite supplementaire.

Campagne Compose : `documind-snapshot-db4c6db8dc5d`.
Debut pytest : `2026-11-07T12:28:46.093922+00:00`.
Duree snapshots : **98,069 secondes**.

| Qualification | Resultat |
| --- | --- |
| Ancien contrat UID/GID 0:0, dossier 1001:1001/0755 | Refus DAC reproduit |
| Nouveau preflight, dossier 1001:1001/0770, writer 0:1001 | Ecriture et lectures conteneur/hote reelles PASS |
| Deux captures format 3, Alembic 0008 et restaurations PostgreSQL | 2 PASS |
| Detection SQL des falsifications compteur/fermeture | 2 PASS |
| Refus des quatre charges utiles alterees | 4 PASS |
| Inventaires historiques coherents et refus S2 | 2 PASS |
| Refus client PostgreSQL/API actifs | 2 PASS |
| Contrats unitaires d'inventaire conserves | 7 PASS |
| **Suite snapshots complete** | **19 passes, 0 echec, 0 erreur, 0 ignore** |
| Permissions, gates CI et regressions capture/quarantaine | **19 passes, 0 echec, 0 erreur, 0 ignore**, 0,830 s |
| Preflight de compatibilite Windows, dossier neuf | Ecriture/lecture reelles PASS, UID/GID 0:0, CapEff=0, NNP=1 |

Les commandes de tests conservent `--require-no-skips`. Les deux nouvelles
preuves unitaires verifient que le parent conserve ses UID/GID/mode et que
le dossier preexistant conserve ses UID/GID/mode et son contenu sentinelle.
Les autres contrats sont ceux deja qualifies lors de l'integration CI.

Un premier lancement du pilote de diagnostic hors depot a rencontre une
erreur de syntaxe de quoting, avant tout test. Son volume a ete nettoye.
Le pilote corrige a ensuite execute la campagne complete ci-dessus ; aucun
test n'a ete masque, desactive ou modifie pour devenir vert.
L'avertissement Starlette/httpx preexistant reste visible dans les deux suites.

## 6. Restaurations et preuves conservees

Les deux scenarios physiques auparavant en echec passent integralement,
avec les outils reels `backup_local`, `verify_snapshot` et `validate_restore`.
Les assertions comparent toutes les lignes des tables publiques, les octets
du document et ses metadonnees, schemas/versions/integrite des cinq SQLite,
empreintes SHA-256 et coherence lifecycle authentifiee.
Les donnees source et les charges utiles du snapshot restent inchangees.

| Source synthetique | Capture | Base restauree |
| --- | --- | --- |
| Quota `(4,false)` | `2eb03b9b-3298-43b5-a7fc-77af7be18a0d` | `documind_restore_d88cbfd7dfb7` |
| Quota `(4,true)` | `6c631c77-dfa8-4a78-92a2-decaade9e3f2` | `documind_restore_fcfe734cdc9f` |

Chaque vrai rapport de quarantaine confirme `status=quarantined`, un document
verifie, cinq magasins restaures, zero document manquant/non reference et :
`api_attached=false`, `critical_mutations_allowed=false`,
`opening_authorized=false`, `s2_recovery_authorized=false`.
Les quotas sont conserves, sans reouverture d'une API publique.

Les deux JSON conservent les vrais manifestes et rapports de quarantaine,
avec leurs SHA-256 de charges utiles et magasins. Le JUnit certifie les
19 cas sans echec/erreur/ignore. Le caller Linux UID 1001 a effectivement
ouvert et lu chacun de ces fichiers avant leur export vers le dossier de session.
Les snapshots/restaurations temporaires eux-memes ne sont pas conserves.

Dossier des preuves, hors depot :
`C:\Users\Adeline\.copilot\session-state\12ffa574-cb17-4a50-a650-3af684ea07ab\files\snapshot-permissions-native-proofs-02`.

| Fichier | SHA-256 |
| --- | --- |
| `fixed-results/snapshot-proofs.xml` | `dafc3ae134172d92d392c690ae84b727987db548a14c46cd13e4a96a50226ab3` |
| `fixed-results/capture-closed-false.json` | `5dd505de8293751191df941d862343f21229a16fa44ea4d444e8d1d1ec30aa8e` |
| `fixed-results/capture-closed-true.json` | `4c48f53f6a07905a3e1744d6dbfc494bf20e3ee8a67d9874f16bfff8e52553ad` |
| `fixed-results/lab-resources.json` | `c593c0d1f18d066810f432421e4b9cb77221ebed58537a7db1d8110d23a09ac2` |
| `contracts.xml` | `a05ae867ed1b21a3d8fdf4cb0e0c8fe8c5e505e83843a35d37c3a8ddff30b24e` |
| `native-host.json` | `80fd7539b284b56746b3b39c114aee4f4099985d48985cc19c837b636bf33413` |
| `old-dac.log` | `2714bdfbe49d6cf90fb115e2b7c105086347fd5e2a14bfc3717c07aa5a0eeda8` |

Les metadonnees Linux d'ownership/modes sont conservees dans les JSON :
elles sont mesurees avant l'export, sans deduire ces modes des fichiers NTFS.

Images locales reutilisees, non modifiees et non publiees :

- Runner : `sha256:f2b7acb468c4584836fe4a0c037e91fa8ad571d6909ab8d2f3754f8f2bd4a33a`.
- PostgreSQL : `sha256:43ee6c6272808d27c724d9f4be925325c40795881451ff24dc41a239da6f933c`.

## 7. Nettoyage et protections

Le bilan Compose confirme `before` et `after` avec listes vides de conteneurs,
volumes et reseaux, `pytest_exit=0`, sans erreur de qualification/nettoyage.
Chaque base historique/restauree est supprimee et son absence verifiee par
les fixtures. Le runner, la base, les trois volumes et le reseau sont supprimes.
Le volume natif du caller, les conteneurs de copie/diagnostic et le dossier
temporaire du probe Windows sont aussi nettoyes. Aucun prune global.

Les protections du runner de preuves sont conservees :
`cap-drop ALL`, `no-new-privileges`, racine/source en lecture seule, limites
memoire/PID, tmpfs, namespace reseau db et reseau Compose interne sans ports.
Le preflight est encore plus limite : aucun reseau ni socket Docker.
La seule modification d'identite du worker est son GID primaire, pour acceder
au dossier de resultats prive ; aucun chmod 777 ni ajout de capacite.

Les gardes de checksum, quiescence, ownership metier, migration et quarantaine
ne sont pas modifies. Les fichiers de production et les workflows sont inchanges.
L'analyse syntaxique Python et `git diff --check` passent.

Le socket Docker conserve sa frontiere de confiance administrative existante :
le correctif DAC ne transforme pas un daemon partage en isolation de capacite.
La prochaine CI doit toujours utiliser le job GitHub-heberge jetable deja prevu,
sans secrets ni donnees de production.

## 8. Etat Git et prochaine qualification

Worktree release : `deliveries/docnelo-public-beta-release-20261106/source`.
Branche : `release/docnelo-public-beta-10-20261106`.
HEAD initial et final : **`11e55670e792af9c6fb08ca7fc3a24be08028be9`**.
Le correctif et ce rapport restent non commites ; l'index reste vide.
Le rapport distant NO-GO preexistant reste un fichier local inchange.
Le worktree principal et ses 59 modifications suivies preexistantes sont preserves.

Aucun commit, push, lancement distant, merge, acces VPS, deploiement,
modification de protection GitHub ou inscription publique.

La prochaine qualification necessite revue et autorisation pour commiter le
correctif, publier un **nouveau SHA**, puis lancer uniquement `ci.yml` sur la
branche release. Relancer le SHA publie actuel sans nouveau commit executerait
encore l'ancien contrat de permissions.

Le futur run devra confirmer les 19 cas sans ignores, les deux restaurations,
les trois preuves JUnit/captures lisibles par le runner hote, le bilan de
nettoyage et la conservation des protections. Python/frontend devront rester
verts, publish ignore sur release et Windows absent.

**Decision : GO pour preparer une nouvelle CI autorisee avec le correctif ;
pas de qualification distante acquise ni d'autorisation de production.**
Le corpus reste synthetique et limite a quatre admissions et un document :
ce correctif ne certifie ni saturation a dix, ni RPO/RTO, fraicheur externe
ou remise en service S2.
