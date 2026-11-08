# Docnelo V5.1 - Audit du montage Docker du recovery latch

## 1. Decision et limites

**NO-GO pour conserver le montage direct du fichier comme garantie de
fermeture apres remplacement atomique. GO limite a la proposition de
conception et a la preparation d'une future qualification en laboratoire.**

Aucune migration, modification Compose, modification du middleware ou
execution Docker n'est appliquee par cet audit. Aucun acces VPS,
production, base ou secret reel ; aucun service demarre. Les fichiers
`.env` reels ne sont pas consultes, et aucune interpolation Compose n'est
executee. Les releases scellees V5/V5.1 et les preuves existantes restent
intactes. **Aucune autorisation S2, Lifecycle 10, Public Beta ou production.**

L'experience Debian suivante est **rapportee par l'operatrice**, non
reexecutee ici et non verifiee dans ses fichiers de preuve :

| Vue apres remplacement atomique | Inode rapporte | Etat lu |
|---|---:|---|
| Conteneur, bind du fichier | 1997427 | `ready` obsolete |
| Hote, nouveau fichier | 1997429 | `quarantined` |
| Conteneur, bind du repertoire, essai distinct | 1997430 | `quarantined` |

Elle demontre le probleme de resolution du chemin dans le montage teste,
pas encore son integration dans les images, utilisateurs, procedures et
applications Docnelo. L'audit present est statique, sur le poste Windows.
Les qualifications ASGI precedentes ne prouvent pas la propagation Docker.

## 2. Perimetre et inventaire des montages

Le parcours a inclus les YAML/YML et les JSON Compose presents dans
l'arborescence, **y compris les fichiers ignores par Git**, les exports,
livraisons et recettes `var`. Les dossiers de dependances `.venv`,
`node_modules`, `.git` et caches ne sont pas des sources de deploiement
et ont ete exclus. Les archives binaires n'ont pas ete extraites :
leur contenu interne n'est pas assimile a un Compose present sur disque.
Les tags Compose `!reset` et `!override` ont ete lus statiquement, sans
execution, interpolation, lecture d'env_file ou contact avec un daemon.

**276 documents Compose/overrides/fixtures trouves**, dont 18 JSON :
**97 fichiers declarent 99 montages de latch, tous directs sur le fichier**.
Les 179 autres documents n'en declarent pas ; cela ne signifie ni qu'un
override supprime le montage de sa base, ni que sa recette est qualifiee.
Les fixtures de rendu/hash sont comptees comme artefacts, pas comme
deploiements effectifs.

### 2.1 Sources a la racine

| Fichier et service | Chemin hote declare | Chemin conteneur / Settings | Protection declaree |
|---|---|---|---|
| `compose.yaml`, `api` | `${RECOVERY_CONTROL_FILE:?...}` | `/run/documind/recovery-state.json` | bind fichier RO ; `create_host_path: false` |
| `compose.production.yaml`, `api` | `${RECOVERY_CONTROL_FILE:?...}` | `/run/documind/recovery-state.json` | bind fichier RO ; `create_host_path: false` |
| `compose.public-beta.vps.yaml`, `api` | `${RECOVERY_CONTROL_FILE:?...}` | `/run/documind/recovery-state.json` | bind fichier RO ; `create_host_path: false` |
| `compose.public-beta-test.yaml`, `api` | `${BETA_RECIPE_DIR:?}/recovery-state.json` | `/app/recovery-state.json` | syntaxe courte `:ro`, sans refus explicite d'autocreation du chemin |
| `compose.public-beta-test.yaml`, `lifecycle-init` | aucun montage du latch | env `/app/recovery-state.json` | variable presente mais fichier non fourni a ce service |
| `compose.public-beta.vps.registration-gate.override.yaml` | aucun ajout | herite de sa base | gate d'inscription, pas gate de quarantaine |
| `compose.pdf-isolation-test.yaml` | aucun | pas de chemin explicite | recette de tests distincte |
| `compose.upload-test.yaml` | aucun | pas de chemin explicite | pas de preuve de recovery ; un Settings non configure reste ferme |
| `compose.upload-test.windows.yaml` | aucun ajout | herite de sa base | override reseau uniquement |

References : `compose.yaml:26-41`, `compose.production.yaml:51-63`,
`compose.public-beta.vps.yaml:246-266`,
`compose.public-beta-test.yaml:39-40,78-79`.
La ligne `lifecycle-init` decrit un service supplementaire du meme fichier,
pas un neuvieme Compose ni un montage additionnel.

### 2.2 Livraisons et exports presents sur disque

| Prefixe | Documents / fichiers avec latch | Montages concernes |
|---|---:|---|
| `deliveries\docnelo-10-users` | 10 / 4 | `source` et `candidate-source` : `compose.yaml`, `compose.production.yaml`, bind fichier RO `/run/documind/recovery-state.json` |
| `deliveries\docnelo-lifecycle-10-api` | 29 / 14 | `source` : les quatre fichiers avec latch de la racine ; `source\exports` : les dix copies listees ci-dessous ; les deux overrides `payload` n'ajoutent pas de latch |
| `deliveries\docnelo-signup-e2e-lab` | 6 / 3 | deux fichiers `source\compose{,.production}.yaml` ; `compose.json` monte `./recovery.json:/control/recovery.json:ro` dans `api`, `lifecycle-init` et `migrate` |
| `deliveries\docnelo-web-branding-r1` | 7 / 0 | sources anterieures sans latch et overrides web ; ne pas en deduire une protection |
| `deliveries\docnelo-web-branding-r2` | 8 / 2 | `source\compose.yaml`, `source\compose.production.yaml` ; overrides web et fixture hash sans latch |
| `exports\public-beta-candidate-20261030T234213Z` | 1 / 1 | `compose.public-beta.vps.yaml` |
| `exports\public-beta-candidate-20261030T234303Z` | 6 / 3 | `compose.yaml`, `compose.production.yaml`, `compose.public-beta.vps.yaml` |
| `exports\public-beta-candidate-20261030T234658Z` | 6 / 3 | memes trois noms |
| `exports\public-beta-candidate-20261030T234818Z` | 7 / 3 | memes trois noms ; override inscription sans ajout |

Les dix fichiers avec latch sous `source\exports` de la livraison
Lifecycle sont les copies des quatre lignes `exports` ci-dessus.
Leur montage est egalement direct, RO, cible
`/run/documind/recovery-state.json`. Les copies historiques
`compose.public-beta-test.yaml` sans latch ne sont pas retroactivement
equivalentes au fichier actuellement a la racine.

### 2.3 Recettes et copies historiques sous `var`

Le parcours de `var` a trouve **188 documents, dont 60 fichiers avec
latch**. Ils ne constituent pas une configuration de production observee.
Toutes les cibles de latch y sont `/run/documind/recovery-state.json`.
Les familles suivantes identifient les 60 chemins, sans modifier ces preuves.

| Prefixe sous `var\` | Documents / fichiers avec latch | Chemins relatifs avec latch |
|---|---:|---|
| `documind-opcompat-df0056f895` | 4 / 2 | `source\compose.yaml`, `source\compose.production.yaml` |
| `documind-restore-lab-074e2cbf2f58` | 2 / 2 | `compose.json`, `source\compose.production.yaml` |
| `documind-restore-lab-13f751a5d8a5` | 2 / 1 | `source\compose.production.yaml` |
| `documind-restore-lab-24c4b66265c8` | 2 / 1 | meme nom sous `source` |
| `documind-restore-lab-57159b74aa17` | 2 / 2 | `compose.json`, `source\compose.production.yaml` |
| `documind-restore-lab-b09148a814c4` | 2 / 1 | `source\compose.production.yaml` |
| `documind-restore-lab-d66203d51b11` | 2 / 1 | meme nom sous `source` |
| `lite-step2-74152cc207` | 13 / 10 | deux fichiers `source\compose{,.production}.yaml` et huit copies de regression A |
| `lite-step3a-dfb9c9eb30` | 13 / 10 | memes noms et huit copies de regression A |
| `lite-step3b-ed676f397b` | 5 / 2 | `source\compose{,.production}.yaml` |
| `lite-step3c-7c3296b180` | 5 / 2 | memes noms |
| `lite-step3c2-80a92d718f` | 5 / 2 | memes noms |
| `lite-step3c3-a9d4072f18` | 5 / 2 | memes noms |
| `pr9-second-ci-992954e27c` | 5 / 2 | memes noms |
| `pr9-two-tests-056817d561` | 13 / 10 | `compose.yaml`, `compose.production.yaml` et huit copies de regression B |
| `public-prep-efcb28b8dd` | 5 / 2 | `source\compose{,.production}.yaml` |
| `rc-ci-consistency-117f23f9e9` | 5 / 2 | memes noms |
| `rc-postgres-public-66e41d44d4` | 5 / 2 | memes noms |
| `whitespace-validation-456a1eafb3` | 6 / 2 | `compose.yaml`, `compose.production.yaml` |
| `windows-timeout-profile-fb1065ffc9` | 5 / 2 | memes noms |

Les huit copies de regression A se trouvent chacune dans
`tmp-windows-regression\<cas>\vps\releases\candidate\compose.production.yaml`.
Pour B, le prefixe est `tmp-modules` a la place de
`tmp-windows-regression`. Les huit noms de cas sont :

```text
test_authorized_deployment_pre0
test_changed_quota_blocks_acti0
test_effective_image_settings_0
test_effective_image_settings_1
test_open_quota_refuses_before0
test_public_first_installation0
test_public_mode_cannot_be_com0
test_public_rollback_keeps_gat0
```

Les 19 autres prefixes `var` n'ont aucun montage de latch :

```text
documind-restore-lab-2c87a82b5473  documind-restore-lab-41d667b3cf01
documind-restore-lab-4cf0d467223a  documind-restore-lab-602ea0315f4d
documind-restore-lab-8c9952c6133b  documind-restore-lab-9593dc006e98
pytest-s14-8-fresh-ci             s13-a7b75801
s13-ci-8dd8f6fa                  s14-4-backup-test
s14-7-1-flat-bundle              s14-7-10-clean-context
s14-7-10-materials               s14-7-11
s14-8                           sec1003-f988dd887e
sec1004-8c2cec37b8               sec1004-final-ea5afba1
sprint10-rf01-rf02
```

Le decompte global 188/60 ci-dessus est celui des fichiers, non celui
des prefixes.

### 2.4 Synthese des protections declarees

| Forme | Nombre de montages |
|---|---:|
| bind fichier long, cible `/run/documind/recovery-state.json`, RO, `create_host_path: false` | 92 |
| meme cible, bind fichier long RO sans option explicite d'autocreation, deux recettes restore-lab JSON | 2 |
| syntaxe courte RO, `/app/recovery-state.json` | 2 |
| syntaxe courte RO, `/control/recovery.json`, trois services d'un seul JSON signup | 3 |

**RO ne garantit pas la fraicheur.** Les 99 montages restent sensibles au
remplacement de leur fichier source. Un chemin affiche dans `docker inspect`
ne prouve pas l'inode effectivement lu.

## 3. Lecteurs backend et frontend

### Backend

`backend/config.py:12,50,133-141` configure les Settings depuis les sources
habituelles, avec `recovery_state_path: Path | None = None` ; le profil Lite
exige un chemin, mais ce champ ne certifie pas a lui seul le montage,
l'UID, le mode ou la fraicheur. Les Compose examines imposent la variable
de leur section `environment`, prioritaire sur les valeurs de leur env_file.
Hors Compose, `.env.example:8` propose encore un chemin relatif :
le lecteur le resout depuis le repertoire courant, pas depuis l'env_file.
Le futur contrat Docker doit exiger le chemin absolu attendu, sans
dependre d'un `WORKDIR` ou de la decouverte d'un dotenv.

`backend/recovery_quarantine.py:13-49` ouvre de nouveau le chemin a chaque
lecture : rejet des symlinks, `O_NOFOLLOW` si disponible, fichier regulier,
taille maximale 1024, UTF-8/JSON strict, cles uniques, format entier 1,
etats `ready`, `quarantined`, `serving_closed`. Absence/inaccessibilite :
`unavailable` ; contenu invalide : `invalid`. Ces etats refusent le trafic.
Le lecteur ne verifie pas un mode exact 0600 ni le proprietaire : un fichier
lisible mal protege n'est pas automatiquement juge invalide par ce code.

`backend/main.py:87-105` memorise l'aptitude **au demarrage**.
`backend/recovery_quarantine.py:57-77` relit ensuite le latch pour chaque
nouvelle requete HTTP, sous reserve d'une frontiere Lite qui peut deja
refuser certaines routes en 403. Sinon le refus de quarantaine est 503.

| Etat initial du processus | Transition visible | Comportement attendu du code actuel |
|---|---|---|
| `ready` | `ready -> quarantined` | nouvelles admissions HTTP refusees |
| `ready` | `quarantined -> ready` | peut readmettre sans redemarrage : decision operateur explicite indispensable |
| `quarantined`, absent ou invalide | puis `ready` | reste ferme car `recovery_ready_at_start == False` |
| nouveau processus, `ready` autorise | demarrage | peut admettre apres les autres controles de demarrage |

`serving_closed` appartient au protocole de reprise Lite supervise et signe
(`backend/lite_release.py:401-473`). Ce n'est pas un alias a remplacer
arbitrairement par `ready`, ni une autorisation S2.

**Le latch n'annule pas les traitements deja admis et n'arrete pas les
workers ou mails deja demarres.** Les branches de `backend/main.py:104-146`
ne sont sautees qu'au demarrage ferme. La migration doit donc maitriser
les anciens processus et les travaux en cours, pas seulement les nouvelles
requetes.

### Frontend

`frontend/server/config.mjs:7-63` ne lit pas `RECOVERY_STATE_PATH`.
Aucun des Compose examines ne le fournit au service web pour en faire un
lecteur du latch. `frontend/Dockerfile:17` execute le BFF en `USER node` ;
cela ne lui donne aucun controle local de recovery.

Le BFF relaie les appels metier a l'API et leurs refus. Son healthcheck
applicatif `/bff/health` transforme toute non-reussite de l'API en 503
(`frontend/server/app.mjs:160-175`). D'autres gardes locaux peuvent refuser
plus tot en 400/401/403/404. Les reponses locales `/bff/config`, CSRF,
et les fichiers statiques ne consultent pas le latch
(`app.mjs:156,194-198,360-363`).

**Ne pas promettre que tout HTTP du frontend devient 503.** Le perimetre
est le refus d'admission metier par l'API. Il n'est pas recommande d'ajouter
un second lecteur de latch au BFF pour ce correctif : cela serait une
extension fonctionnelle distincte. Un ecran de maintenance ou une fermeture
totale du web releve d'une barriere de trafic independante.

## 4. Auteurs du latch et nature des ecritures

Les lignes ci-dessous concernent les sources actuelles a la racine,
sauf prefixe explicite. Les copies sous exports, livraisons, `var\...\source`
et fixtures reprennent ces familles a des revisions parfois anterieures ;
elles ne doivent pas etre corrigees en place ni supposees identiques.

| Auteur / appelant | Ecriture du latch |
|---|---|
| `backend/lite_authority.py:99-120`, `write` | temporaire dans le meme parent, `O_EXCL/O_NOFOLLOW`, mode 0600 ou 0644 si `public=True`, fsync fichier ; `os.replace` si remplacement, sinon link sans ecrasement ; fsync parent et relecture |
| `backend/lite_release.py:250-261` | `state()` appelle ce helper avec `replace=True, public=True`, donc **remplacement atomique**, root et 0644 ; creation du runtime initial `quarantined` avec le meme helper sans ecrasement |
| `backend/lite_release.py:394-398,520-548` | transition vers `serving_closed` apres autorisation specifique ; retour `quarantined` en erreur/fin de supervision ; pas de publication standard de `ready` dans ce parcours |
| `tools/lite_restore.py:86-98,144-166` | points d'entree restore/recovery deleguant aux modules Lite ; ne pas executer ici |
| `backend/lite_snapshot.py:438-464` | creation initiale `quarantined` sur destination neuve ; helper prive, 0600 ; pas de remplacement d'un latch vivant |
| `tools/validate_restore.py:320-328,385-390` | creation puis reecriture directe `write_text` de `quarantined`, 0600 POSIX, dans une nouvelle destination de restauration ; capture originale preservee sous `source-recovery-state.json` |
| `ops/testing/prepare_beta_recipe.py:59-61` | cree un `ready` synthetique par `write_text`, puis 0600 ; recette neuve, pas un protocole operateur |
| `ops/testing/combined_restore_lab.py:45-48,84-90` | cree `quarantined` directement et genere un bind fichier ; mode du latch non fixe explicitement a cet endroit |
| `ops/testing/combined_restore_payload.py:165-166` | latch synthetique `quarantined` par ecriture directe, puis 0600 |
| `deliveries/docnelo-signup-e2e-lab/prepare_lab.py:20-21,53,82-91` | cree `recovery.json` synthetique `ready`, sans chmod explicite ; genere trois binds directs du meme fichier |
| `tools/backup_local.py:225-243,249-255` | lit le latch via un conteneur one-off `cat`, puis ecrit le payload de sauvegarde ; **ce payload n'est pas une autorite de readiness restauree** |
| `tests/conftest.py`, `tests/test_recovery_quarantine*.py`, `tests/test_deployment.py`, tests Lite et leurs copies | creations/reecritures, suppressions et transitions sur temporaires de tests ; `tests/test_lite_release.py:428,443` utilise aussi le helper atomique |
| `qualification/restored_latch/run_campaign.py:222-226` | cree uniquement le latch synthetique en mode preparation ; le mode reel lit le latch fourni sans l'ecrire |

Les outils des livraisons scellees
`docnelo-public-beta-backup-v5-20261031` et
`docnelo-public-beta-backup-v5.1-20261031`, ainsi que les copies
`tooling-v5.2` de la livraison Lifecycle, contiennent aussi la capture
et l'ecriture de restauration de ces familles. Leurs archives restent
intactes ; les chemins internes et lignes peuvent differer des sources
racine. En particulier, ne pas supposer que toute revision ancienne cree
le latch au meme instant du parcours de restauration.

`tools/deploy_production.py` et `tools/backup_production.py` valident le
montage mais ne publient pas une transition du latch. Le remplacement de
`quarantine.json` dans `tools/validate_restore.py:271-281` concerne un
**rapport**, pas `recovery-state.json`. Les scripts `.tmp_patch_*` sont
des outils de modification de sources, pas des controleurs de latch.
Aucun script shell/PowerShell dedie a la publication operateur
`ready <-> quarantined` n'a ete trouve dans les sources parcourues.

## 5. Risque d'inode obsolete et limites d'atomicite

Un bind direct du fichier attache le fichier resolu lors du montage.
Un `os.replace(temp, latch)` publie un autre inode sous le meme nom sur
l'hote, sans transformer l'objet deja monte. Le lecteur peut rouvrir
son chemin dans le conteneur a chaque requete et continuer a obtenir
l'ancien fichier. L'absence de cache Python ne corrige donc pas ce risque.

Cas dangereux : processus initialement pret, inode monte encore `ready`,
nouveau fichier hote `quarantined` ; le middleware peut continuer a
laisser passer. Cas inverse : une ancienne quarantaine peut demeurer
visible et empecher une reprise. Suppression ou remplacement invalide
sur l'hote ne doivent pas non plus laisser un ancien `ready` utilisable.

Monter le **repertoire stable** permet a chaque nouvel open du nom enfant
de resoudre l'entree publiee dans ce repertoire. Cela corrige le probleme
teste, sous plusieurs invariants :

- ne pas remplacer, permuter ou remonter le repertoire source lui-meme ;
  ses ancetres et son identite restent sous controle operateur ;
- fermer le descripteur apres lecture, comme le fait le lecteur actuel ;
  un descripteur deja ouvert avant le rename peut encore lire l'ancien inode ;
- definir les assertions sur les opens effectues **apres** la publication
  achevee, et non sur les requetes deja admises avant celle-ci ;
- utiliser un stockage local et un comportement de montage qualifies ;
  ne pas extrapoler aux fichiers reseau, Docker Desktop, rootless ou
  userns-remap sans repetition adaptee.

L'ecriture en place, le truncate et les symlinks ne sont pas un correctif :
risque de lecture partielle, interruption de publication ou rejet par le
lecteur. Conserver une publication atomique, mais corriger le montage.

## 6. Proposition de montage dedie - NON APPLIQUEE

Choix propose : nouvelle variable hote `RECOVERY_CONTROL_DIR`, repertoire
ne contenant **que le latch et les temporaires de sa publication**.
Chemin hote illustratif, non cree et non approuve pour une machine reelle :
`/opt/documind-public-beta/recovery-control`.
Chemin conteneur propose : `/run/documind-control/recovery-state.json`.

**Ne pas monter le parent actuel entier**
`/opt/documind-public-beta` : il peut aussi contenir releases, parametres,
captures et verrous. Ne pas monter un dossier de restauration ou de
preuves contenant d'autres fichiers. Le controle runtime doit etre
distinct du latch restaure conserve comme preuve en mode 0600.

Extrait propose pour le service API des futurs candidats dev/production/VPS :

```yaml
services:
  api:
    environment:
      RECOVERY_STATE_PATH: /run/documind-control/recovery-state.json
    volumes:
      # Conserver ici les volumes documents/lifecycle propres a cette recette.
      # REMPLACER l'ancien bind du fichier par l'entree suivante.
      - type: bind
        source: ${RECOVERY_CONTROL_DIR:?Provide a preprovisioned absolute control directory}
        target: /run/documind-control
        read_only: true
        bind:
          create_host_path: false
    # Conserver USER non-root, options de securite, ressources et reseaux existants.
```

Pour une **nouvelle** recette Beta de laboratoire, remplacement equivalent :

```yaml
services:
  api:
    environment:
      RECOVERY_STATE_PATH: /run/documind-control/recovery-state.json
    volumes:
      # Ajouter aux volumes metier/TLS de la nouvelle recette.
      # Supprimer l'ancien ${BETA_RECIPE_DIR}/recovery-state.json:...:ro.
      - type: bind
        source: ${BETA_RECIPE_DIR:?}/recovery-control
        target: /run/documind-control
        read_only: true
        bind:
          create_host_path: false
```

Ces fragments ne sont **pas des overrides additifs prets a lancer**.
Compose fusionne les volumes notamment par cible : changer la cible sans
retirer l'ancienne entree peut conserver les deux montages. Produire un
nouveau Compose candidat complet, ou un remplacement explicite de liste
compatible avec la version Compose cible ; verifier le resultat final.
Ne pas ajouter simplement un second bind, surtout avec une cible imbriquee.

Pour le frontend : aucune variable recovery ni aucun volume supplementaire
propose. Pour `lifecycle-init` de la recette : supprimer la variable
inutilisee ou documenter explicitement son besoin et son montage RO dans
le futur candidat, sans lui donner le droit de publier le latch.
Les recettes signup et combined-restore doivent etre **regenerees dans
de nouveaux dossiers**, pas corrigees dans leurs preuves historiques.

### Permissions et utilisateur

`Dockerfile:26-29` cree `app` puis fixe `USER app`, sans UID/GID numerique
contractuel explicite. Les images externes choisies par les Compose ne
sont pas inspectees ici : leur utilisateur effectif reste a verifier.
Les UID/GID 1000 de certaines recettes ne prouvent pas ceux d'une autre
image. Les init root ne sont pas l'utilisateur de l'API.
La racine du conteneur API est declaree `read_only: true` en production,
VPS et recette Beta ; ce n'est pas le cas du Compose de developpement.
Cette protection est distincte du RO du bind et ne rafraichit aucun inode.

Proposition DAC distincte des artefacts restaures :

| Objet runtime neuf | Proprietaire / mode proposes |
|---|---|
| repertoire de controle | root:RECOVERY_READERS, 0750 ; aucun droit d'ecriture API |
| latch publie | root:RECOVERY_READERS, 0440 |
| API | UID non-root, groupe de lecture explicite verifie dans le namespace |
| montage du repertoire | RO ; pas d'alias RW, sous-montage ou chemin alternatif vers sa source |

Un `group_add` numerique pourrait etre necessaire, **uniquement apres
verification** des groupes, mappages d'identites et permissions de traverse.
Ne pas supposer qu'un bind traduit les proprietaires numeriques.
Root:0600 serait illisible par l'API non-root ; le resultat serait ferme,
mais inutilisable pour une ouverture autorisee. Ne pas resoudre cela
en executant l'API comme root ni en ouvrant le repertoire en ecriture.
Ne jamais chmod le latch restaure qui sert deja de preuve.

Le mode 0440 n'est pas une exigence actuelle du parseur : c'est une
politique proposee de provisioning et de garde operateur. L'ecrivain
privilegie doit appliquer UID/GID/mode au **temporaire avant publication**,
fsync le fichier, effectuer le replace dans le meme repertoire, puis
fsync le repertoire et verifier la relecture. La meme politique doit
s'appliquer a chaque transition, pas uniquement a la creation initiale.
Ne pas reutiliser tel quel le helper Lite `public=True` qui publie en 0644
et valide d'autres invariants d'autorite.

Attention a la recette historique
`ops/testing/combined_restore_lab.py:85-90` : elle execute un runner root,
monte le latch RO mais aussi son parent via `/evidence` **RW**. Ce chemin
alternatif permettrait de modifier le latch ; ce montage de preuves
synthetiques n'est pas un modele de cloisonnement pour l'API future.

## 7. Contrats et restauration : adaptation indissociable

Un changement Compose seul n'est pas compatible avec les gardes actuelles :

| Source | Hypothese a faire evoluer dans un NOUVEAU candidat |
|---|---|
| `tools/deploy_production.py:219-263,580-607` | trois montages attendus, cible fichier exacte ; source obligatoirement fichier regulier hors release et DockerRootDir ; inspect des conteneurs sur cette cible |
| `tools/backup_production.py:198-225,285-300` | memes hypotheses fichier/cible lors du preflight et de l'inspection reelle |
| `tools/public_beta_backup.py:25,60-80,121-149` | `CONTROL` fige, validation du bind fichier et injection `RECOVERY_CONTROL_FILE` |
| `tools/backup_local.py:225-243` | capture le chemin absolu de Settings ; peut conserver ce mecanisme avec le nouveau chemin interne |
| `tests/test_deployment.py:54-61,140-169`, `tests/test_production_backups.py:283-331`, `tests/test_public_beta_backup.py:19-40` | expectations et simulations du bind fichier ; nouveaux tests de refus et de propagation indispensables |
| `.env.example:7-9`, `.env.production.example:11-13`, `.env.public-beta.example:54-55` | exemples de chemins fichier a remplacer dans les futures versions, pas dans les releases scellees |

Le garde futur doit verifier **le couple repertoire monte + fichier
Settings enfant**, la source absolue canonique, l'identite stable du
repertoire, l'absence de symlink, proprietaires/modes, RO effectif,
absence de montage fichier residuel et d'alias RW, emplacement hors
donnees/restaurations et absence de contenu secret dans ce repertoire.
Ne pas assouplir les gardes en acceptant n'importe quel bind RO.
Versionner explicitement le contrat de montage ; un ancien contrat peut
etre reconnu pour diagnostic historique, pas autorise silencieusement
comme nouveau deploiement corrige.

Effet secondaire important dans `tools/public_beta_backup.py` :
`CONTROL.parent` sert aussi a valider le parent du repertoire de release
(`execute`) et a placer `.public-beta-backup.lock` (`operator_lock`).
Deplacer seulement `CONTROL` dans un sous-repertoire casserait le premier
controle et deplacerait le verrou, permettant a des versions anciennes et
nouvelles de prendre des verrous differents. Separer explicitement base
de deploiement, repertoire de controle et **verrou operateur stable**,
sans changer l'inode de ce verrou ni autoriser deux generations en parallele.

La capture peut continuer a appeler le fichier archive
`recovery-state.json` sans transformer le format V5/V5.1. Le chemin de
lecture interne et les controles de provenance du montage, eux, changent.
Une capture one-off fraiche peut voir le nouvel inode alors qu'une API
ancienne voit encore l'ancien : comparer les octets de sauvegarde a
l'hote ne suffit pas a prouver la fermeture des processus deja en cours.

En restauration, conserver la capture originale comme preuve et publier
un **nouveau controle runtime `quarantined`**, sans recopier aveuglement
un `ready` archive. Ne jamais restaurer par-dessus le repertoire de
controle operateur vivant ni le remplacer atomiquement lui-meme.
Une restauration de fichiers ne doit pas reintroduire un bind fichier
via un ancien Compose/override. Les protocoles Lite qui lient
`root/recovery-state.json`, Settings et empreintes de manifestes ne sont
pas deplacables par simple changement de variable : requalification
separee, sans reemission ou contournement de leur autorisation signee.

## 8. Strategie de migration sans ouverture intempestive - proposition

1. Preparer un nouveau candidat versionne et ses gardes, hors releases
   scellees. Geler les ecrivains, identifier tous les lecteurs/API et
   outils one-off susceptibles d'utiliser l'ancien fichier.
2. Etablir une barriere de trafic independante du latch suspect, arreter
   les anciens API/BFF et maitriser les traitements en cours selon une
   procedure approuvee. **Ne pas compter sur un rename du latch pour
   fermer un conteneur deja attache a l'ancien `ready`.**
3. Conserver hashes, proprietaires, modes, images, chemins et montages
   anciens comme preuves ; ne pas modifier les artefacts restaures.
   Provisionner un nouveau repertoire dedie, stable, et un latch runtime
   neuf `quarantined`. Pas de symlink entre ancien et nouveau controle.
4. Verifier statiquement le Compose final du candidat et ses contrats,
   avec configuration synthetique dans le laboratoire ; en operation
   future, traiter tout rendu contenant des variables sensibles comme
   confidentiel. Ne pas publier de DSN ou d'environnement dans les preuves.
5. **Recreer les conteneurs consommateurs** pour changer leurs montages.
   Modifier le YAML, `docker restart` ou `compose restart` ne leur
   applique pas un nouveau contrat de montage. Un stop/start ou une
   recreation avec l'ancien bind fichier ne corrige pas les futurs
   remplacements ; ne pas supposer un comportement de rafraichissement
   d'inode au redemarrage sans mesure.
6. Garder la barriere de trafic fermee. Demarrer les lecteurs candidats
   en quarantaine uniquement dans le cadre autorise, verifier sous leur
   UID reel le chemin/inode/hash, les refus et l'absence de demarrage
   metier. Un healthcheck 503 est attendu, pas un incident a contourner :
   `web depends_on: service_healthy` peut volontairement bloquer sa creation.
7. Qualifier la matrice ci-dessous. Si une ouverture future est autorisee
   separement, publier `ready` apres validation. Un processus demarre
   ferme restera ferme : prevoir un **nouveau demarrage controle** avec
   readiness explicitement autorisee, toujours derriere la barriere.
8. En echec, rester ferme : arreter les consommateurs, conserver preuves
   et ancienne release ; aucune reprise automatique avec `ready`, aucune
   bascule sur le bind fichier defectueux comme solution de disponibilite.

La proposition n'est pas une commande autorisant d'appliquer ces etapes
au VPS. Les conteneurs effectivement deployes, leurs versions et leurs
montages n'ont pas ete observes par cet audit.

## 9. Matrice Docker a executer dans le laboratoire isole

**Aucun de ces essais Docker n'est execute ici.** Utiliser un nouveau
repertoire de preuves, images deja presentes/pinnees, `--pull never`,
aucun port publie, `network_mode: none`, aucun socket Docker monte.
Pas de Compose production/dev complet : certaines recettes lancent DB,
migrations, mail et reseaux. Le controleur hote et les donnees sont
exclusivement synthetiques ; aucun latch restaure ni preuve anterieure
n'est modifie. Les temporaires/proofs restent hors du repertoire monte.

Deux couches : lecteur statique de fichiers, puis vraie application
FastAPI en ASGI in-process **a l'interieur du conteneur**, avec isolation
SQL/SMTP/IA/workers du harness existant, chemins explicitement ajustes
dans un nouveau harness laboratoire. Pas d'Uvicorn ni de serveur HTTP.
Un controle positif peut laisser passer vers une sentinelle inoffensive,
jamais vers un traitement metier reel. Ne pas reutiliser en le modifiant
le lanceur scelle qui exige le chemin absolu du latch restaure.

| ID | Montage / processus | Manipulation synthetique et resultat exige |
|---|---|---|
| D01 | bind fichier, lecteur continu | reproduire le temoin `ready -> quarantined` atomique : documenter l'ancien inode/etat, attendu comme **echec de ce montage**, pas comme succes applicatif |
| D02 | bind repertoire stable, lecteur continu | meme replace : inode enfant nouveau et hash `quarantined` visibles apres barriere de commit ; inode repertoire stable |
| D03 | repertoire, app initialement `ready` | `ready -> quarantined` : toutes les nouvelles requetes post-publication refusent, zero appel downstream ; Lite peut refuser 403 avant les autres 503 |
| D04 | repertoire, meme processus initialement `ready` | `quarantined -> ready` autorise pour le test : nouvelles requetes admises seulement vers sentinelle ; prouver que cette reaperture est possible et doit rester une decision operateur |
| D05 | repertoire, app demarree `quarantined` | puis replace vers `ready` : le fichier change mais le meme processus reste 503, zero demarrage worker/job/mail/cleanup |
| D06 | repertoire, nouveau processus apres D05 | demarrage synthetique `ready` explicitement autorise : controle positif des spies et du routage ; aucune execution externe |
| D07 | repertoire, app initialement `ready` | supprimer le fichier : opens suivants ENOENT, health et routes metier refuses, repertoire jamais recree par l'application |
| D08 | repertoire, app initialement `ready` | remplacer par JSON malforme, UTF-8 invalide, doublon de cle, format booleen, etat inconnu, cle supplementaire, fichier >1024 octets : refus sans body downstream |
| D09 | repertoire, droits reels API | nouveau fichier illisible ou parent non traversable : refus ; un processus demarre dans cet etat reste ferme apres retablissement des droits, contrairement a un processus initialement pret qui relit un `ready` valide |
| D10 | repertoire, non-root | lire le latch autorise ; tentatives write/truncate/unlink/rename/create refusees par RO/DAC ; verifier absence d'alias RW |
| D11 | source absente ou mauvaise nature | repertoire source absent : creation du conteneur refusee avec `create_host_path: false` ; fichier absent dans un repertoire existant : refus applicatif |
| D12 | chemin ou enfant symlink | provisioning refuse ; lecteur refuse le latch symlink. Refuser aussi FIFO/device au provisioning : ne pas promettre un 503 borne pour un FIFO, car open precede fstat |
| D13 | plusieurs lecteurs deja ouverts / nouvelles lectures | replace en concurrence : descripteur ouvert avant commit peut conserver l'ancien contenu ; chaque nouvel open apres commit voit nouveau hash, aucune lecture partielle |
| D14 | plusieurs consommateurs | lecteurs/app replicas synthetiques voient tous la nouvelle entree ; inclure capture one-off sans la confondre avec l'API existante |
| D15 | variation des modes/UID apres replace | chaque nouveau temporaire publie conserve root/groupe lecteur/mode proposes ; root:0600 bloque l'API ; mode trop permissif rejete par le garde propose, pas suppose rejete par le parseur actuel |
| D16 | recreation et surcharges Compose | rendu final sans ancien bind fichier ni cible masquee ; inspect reel : source repertoire exact, destination exacte, `RW=false`, utilisateur attendu ; restart seul ne vaut pas migration |
| D17 | remplacement du repertoire source lui-meme | essai negatif sous barriere : montrer le risque de repertoire monte obsolete ; refuser cette operation dans le protocole et exiger reprovisioning/recreation controlee |
| D18 | interruption du publisher | avant/apres fsync fichier, replace, fsync parent : aucun contenu partiel ; echec bloque la reouverture. Avant publication, l'ancien `ready` peut subsister : la fermeture de maintenance exige aussi la barriere independante |
| D19 | restauration synthetique | payload archive `ready`, copie runtime forcee `quarantined`, origine archivee conservee ; pas d'ecrasement du controle vivant, pas de retour au bind fichier |
| D20 | frontend et demarrage ferme | BFF upstream simule/injecte sans reseau : API 503 -> health BFF 503 ; gardes locales/statique observes separement ; dependance Compose healthy documentee, jamais contournee pour obtenir un faux succes |

Pour D03/D05/D07/D08 : couvrir health, auth, inscription, documents,
administration HTTP **si reellement enregistree**, docs/OpenAPI et les
deux modes d'en-tetes synthetiques. Ne pas inventer une route admin.
`serving_closed` exige une campagne specifique aux preuves Lite ;
sa seule visibilite dans Docker n'autorise aucun passage de son serving gate.

Conserver pour chaque cas : version Debian/kernel/Engine/Compose, mode
rootless/userns, ID/digest d'image, UID/GID/groupes effectifs, montage
inspecte et si utile mountinfo, dev/inode/mode/proprietaire/hash hote et
conteneur avant/apres, evenements de publication avec barriere de commit,
reponses ASGI, compteurs downstream/workers et JUnit/exit code.
Inventorier les sources/harness/scripts, resultats et fichiers synthetiques
par SHA-256 dans un **nouveau** sous-repertoire de
`/home/adeline/docnelo-lab/development/v5.1-hardening/quarantine-debian-evidence/`.
Aucun skip/xfail ; tout resultat ambigu interdit le GO technique.

## 10. Garanties acquises et restant a etablir

**Acquis dans cette phase :** inventaire statique et tracage des lecteurs,
auteurs et gardes ; identification du bind fichier dans 99 declarations ;
explication compatible avec l'observation Debian fournie ; proposition
de montage et migration qui preserve le verrou de demarrage fail-closed.

**Rapporte, non reproduit ici :** propagation par repertoire et inode
obsolete par fichier dans l'experience Debian synthetique de l'operatrice.

**Non etabli :** integration Docker de l'application reelle, propagation
inverse/suppression/invalide, contrat DAC propose, compatibilite des gardes
de backup/deploiement, comportement des images et UID effectifs,
recreation et restauration completes. Aucun resultat d'une qualification
ASGI Windows ou Debian precedente ne remplace ces essais de montage.

Le GO de cette phase est **documentaire et de conception uniquement**.
NO-GO pour appliquer le correctif ou declarer la chaine qualifiee tant
que nouveau candidat, revue et matrice isolee ne sont pas valides.
S2, Lifecycle 10, Public Beta et production restent non autorises.
