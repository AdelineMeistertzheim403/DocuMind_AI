# Docnelo — Provenance du déploiement API du 31 octobre 2026

Date de recherche : 1 novembre 2026. **NO-GO Lifecycle 10 maintenu.**

## Conclusion

La configuration ayant créé `documind-public-beta-api-1` à
**2026-10-31 01:11:06 UTC** n'est pas identifiée avec une chaîne de preuve
authentifiée. Le hash de configuration communiqué est :

```text
e0559dddd889a8b0af4767c4d14668b32904ea547ac8865f8a2c691e5062aeaf
```

Les archives sources et les objets Git établissent bien l'évolution locale
**280 → 300 → 362 lignes**. Le correctif de propriétaires et de chemins est
conservé dans un checkpoint daté **00:53:53 UTC**, soit 17 min 13 s avant
la création annoncée. Cela rend une intervention intermédiaire plausible,
mais ne prouve ni un transfert, ni une commande de création, ni les octets
présents sur le VPS à cet instant.

Trois précisions nouvelles resserrent les pistes :

- L'image API archivée `4aa850…` porte une date de construction
  **00:10:54.151148168 UTC**, mais aucune variable `LIFECYCLE_*` dans son
  environnement d'image. Les sept chemins ne peuvent donc pas être
  attribués à cet environnement d'image.
- Les exports de 280 lignes ne déclarent les sept chemins ni dans l'API,
  ni dans l'environnement de `lifecycle-init`, ni dans leur modèle
  `.env.public-beta.example`. La piste « sept valeurs fournies par un
  env_file historique » nécessite donc un env_file ou une autre entrée
  effectivement amendée, dont aucune copie réelle n'est retrouvée.
- Les fichiers `IMAGE_INSPECT_api.json` des répertoires d'exports concernent
  une image locale `5433a1…`, pas l'API active `4aa850…`. Ils sont absents
  des archives compressées et de leurs manifestes : ce ne sont pas des
  preuves empaquetées du déploiement VPS.

Aucun calcul Compose, rejeu historique, modification de configuration ou
essai pour atteindre le hash cible n'a été effectué pendant cette recherche.

## 1. Niveaux de preuve et périmètre

| Niveau | Signification dans ce rapport |
|---|---|
| **Preuve authentifiée de déploiement** | Trace dont l'origine est établie et qui relie le conteneur exact à la commande, aux octets et au contexte de création. **Aucune retrouvée.** |
| **V — Contenu local vérifié** | Empreintes recalculées, correspondance archive/manifeste ou identité d'objet Git vérifiée. Cela identifie les octets locaux, sans authentifier leur utilisation sur VPS. |
| **I — Indice** | Rapport narratif, procédure proposée, nom daté, métadonnée d'image ou observation VPS rapportée sans relevé original disponible. |
| **D — Déduction** | Conséquence explicitement conditionnelle des contenus vérifiés et des indices ; pas une action observée. |

Les quatre archives correspondent à leurs fichiers `.sha256` locaux et
toutes les entrées de leurs `MANIFEST.sha256` internes ont été vérifiées.
Ces sommes ne sont pas des signatures ni des reçus de transfert.
Les checkpoints `727b95a…` et `f6e0895…` sont non signés (`%G? = N`) ;
leurs dates auteur/commit sont des métadonnées déclarées, pas des horodatages
externes de déploiement.

Périmètre consulté : `exports`, `deliveries`, `ops\public_beta`,
`docs\docnelo`, rapports Public Beta/Lifecycle à la racine et historique Git
accessible par `--all`. Recherche du hash et de la création dans les textes
pertinents ; recherche Git `-S` du hash sur la fenêtre du 29 octobre au
1 novembre inclus. Aucun journal d'exécution associant le hash cible à
une commande n'a été retrouvé dans ce périmètre.

Les recherches d'historique de sessions disponibles n'ont fourni aucune
conversation de l'intervention initiale ; les identifiants de sessions
inscrits dans Git ne sont pas assimilés à des transcriptions retrouvées.
Aucun accès VPS, lecture d'environnement de production, chargement d'image,
démarrage de conteneur ou extraction sur disque de l'archive API.
Seul ce nouveau rapport est ajouté.

## 2. Chronologie sourcée, en UTC

| Instant | Fait ou trace | Niveau et source |
|---|---|---|
| 29 octobre, 18:19:09 | Commit `1bc1a4a5bb49395acabdce5e7604d1a6b97dea61`, HEAD déclaré par les quatre exports. Ce commit ne contient pas `compose.public-beta.vps.yaml`. | V : objet Git et `GIT_HEAD.txt:1` des exports. L'export contient donc des fichiers hors de cet arbre HEAD. |
| 30 octobre, suffixes 23:42:13 et 23:43:03Z | Deux archives conservent le même Compose 280 lignes, sans sept déclarations de chemins API. | V pour les octets ; I pour la datation par nom. Archives E1/E2 ci-dessous. |
| 30 octobre, suffixes 23:46:58 et 23:48:18Z | Deux archives conservent le même Compose 300 lignes ; sept chemins explicites ajoutés à l'API, à init et au modèle d'env-file. | V pour les octets ; I pour la datation par nom. Archives E3/E4. |
| 30 octobre, 23:50:10 | Checkpoint `727b95a928d2378d48020ba893463c37a8dcf947`, session `89cc2d63-d830-428d-a670-e828197db389`, turn 6. Conserve les exports et le Compose racine de 300 lignes. | V : date Git auteur/commit `2026-10-31T00:50:10+01:00`, blob `cb2ff689…`. |
| 31 octobre, 00:10:54.151148168 | Date `created` de la configuration d'image API `4aa850…` dans `api-active.tar`. Tag archivé `documind-public-beta-backend:2026-10-31`, utilisateur `app`, linux/amd64. | V pour l'identité du config blob ; I pour sa date de build. E5. Ce n'est pas la date de création du conteneur. |
| 31 octobre, 00:53:52 | Checkpoint « turn 7 start » `df5421fd197474852da2f9d2296200c20400b703` : Compose encore à 300 lignes. | V : objet Git, blob `cb2ff689…`. |
| 31 octobre, 00:53:53 | Checkpoint « turn 7 » `f6e08955b648012ad53355ba033f35d0d35ca71a` : Compose 362 lignes, cinq chemins séparés, init en deux phases et migration des magasins plats. | V : date Git `2026-10-31T01:53:53+01:00`, blob `d712ea8b…`, script de laboratoire ajouté. E6/E7. L'écart d'une seconde entre checkpoints n'est pas la durée mesurée de l'intervention. |
| Suffixe `20261031-005952`, fuseau inconnu | Sauvegarde VPS annoncée de 300 lignes, dans le répertoire applicatif `public-beta-candidate-20261030T234818Z`. | I : `DOCNELO_LIFECYCLE10_HISTORICAL_HASH_ANALYSIS.md:19,50`. Copie réelle et empreinte VPS non disponibles localement. |
| 31 octobre, 01:11:06 | Création annoncée de `documind-public-beta-api-1`, hash cible `e0559d…`. | I : demande opératrice actuelle ; date également rapportée dans `DOCNELO_LIFECYCLE10_HISTORICAL_HASH_ANALYSIS.md:21`. Aucun inspect original contenant ID complet, Created et label cible n'est retrouvé. |
| 31 octobre, 08:20:40 puis 09:02:23 | Checkpoints `3727f4c49f22a0129bb6e41270815b7e5a6d74ec` et `5927e86a3526f0f77935d7f6b8a47b1ba0183a40` : même blob Compose 362 lignes. | V : objets Git ; récapitulatif antérieur `DOCNELO_LIFECYCLE10_HISTORICAL_HASH_ANALYSIS.md:41-46`. Pas deux nouvelles configurations API. |
| 31 octobre, 17:08:17 puis 17:16:30 | Commits `df6db2e7c9106c272d959918d4dad5b4d0a43272` et `8b11d4daf47bd7c3c6766b9f5231ea8a84fdbf71` : lecteurs de clés via ascendance privée, puis namespace signé et disposition partagée des clés. | V : objets Git. Préparation candidate ultérieure ; `DOCNELO_PUBLIC_BETA_10_USERS_API_PROVENANCE.md:38-44`. Ces changements ne prouvent pas la configuration de 01:11:06. |

Le suffixe de sauvegarde n'a pas de fuseau. Le nom et le mtime peuvent être
conservés ou choisis lors d'une copie. On ne peut donc pas placer cette
sauvegarde à 00:59:52 UTC comme un événement authentifié.

## 3. Inventaire des archives vérifiées

Les quatre archives sont dans `exports`. Les noms abrégés ci-dessous
désignent `public-beta-candidate-<suffixe>.tar.gz`.

| Référence | Suffixe | SHA-256 de l'archive | Entrées du manifeste vérifiées | Famille Compose |
|---|---|---|---:|---|
| E1 | `20261030T234213Z` | `f78c0fb5de5e727e20fbfdb3c2bcc6e66f68e033f4b333354310cd9a8cb0ffc1` | 101 | 280 |
| E2 | `20261030T234303Z` | `1ff6ca580dd6c9a38724da0cda152e4ba3b5f257a5d93c775c6a1bd65409e2af` | 358 | 280 |
| E3 | `20261030T234658Z` | `131072bf1e2d822e721881c700dc004877c9c7b503e0af6b1d9c38f2f22edecd` | 358 | 300 |
| E4 | `20261030T234818Z` | `480f1c2c8b1a7b8bc97860446f629dc3091b5cff355637a657bb9dec0ba1bf58` | 359 | 300 |

| Contenu | SHA-256 |
|---|---|
| Compose E1/E2, 280 lignes | `8fd28b87a0b03a1fa409e5b63161eaa6134cd705fbb6315dbb45bb3b2cbcb515` |
| Compose E3/E4, 300 lignes | `15f42bf1f3332d2052c0f304994d0fab455fe86a84c627e4749195123d3c0fd0` |
| Compose racine et blob Git f6e0895, 362 lignes | `f46571b71b7a3174c96b15b2848f2b31cdae60339621116eb14be03393dc4ff2` |
| Manifeste interne E1 | `38fd5bb0b42b50cfcc8a12246c2217df0e5bc12f31d0960a452ea0c786aee091` |
| Manifeste interne E2 | `ba2f89a230e004a613731ee718a2164407ae37706278519d1cbb06c2f6796eda` |
| Manifeste interne E3 | `7f0584d04475780c31c8abe159f8b050a54d9e43948278e98f486b7965bd03eb` |
| Manifeste interne E4 | `47143ad4934c2bcc91225c8cfa0f92c1e036707e861514e9142a8ad212e0630b` |

Les Compose des archives correspondent octet pour octet à leurs copies
dans les répertoires locaux d'exports. Pour E4, Compose, manifeste,
modèles d'environnement et GIT_HEAD correspondent aussi aux fichiers
du checkpoint `727b95a…`.

Sources localisables : manifeste E4
`exports\public-beta-candidate-20261030T234818Z\MANIFEST.sha256:27,189,201,227,331` ;
manifeste E2
`exports\public-beta-candidate-20261030T234303Z\MANIFEST.sha256:188,196,201,228,315`.
Les archives ne contiennent aucun fichier nommé `.env`,
`.env.public-beta` ou `.env.public-beta.images` : seulement des modèles.

**Limite HEAD :** les quatre `GIT_HEAD.txt:1` désignent `1bc1a4a…` et les
`GIT_BRANCH.txt:1` désignent `preparation/sprint-14-review`.
Puisque le Compose n'existe pas dans cet arbre HEAD, cette référence ne
suffit pas à reconstruire l'export. Le manifeste et les octets exportés
priment sur une assimilation « export = checkout HEAD ».

## 4. Les sept déclarations et le correctif de propriétaires

| Variable | Famille 280 : déclaration API | Famille 300 | Famille 362 |
|---|---|---|---|
| `LIFECYCLE_REGISTRY_PATH` | Absente | `/app/lifecycle/registry.sqlite` | `/app/lifecycle/registry/registry.sqlite` |
| `LIFECYCLE_CONFIRMATION_PATH` | Absente | `/app/lifecycle/confirmation.sqlite` | `/app/lifecycle/confirmation/confirmation.sqlite` |
| `LIFECYCLE_AUTHENTICATED_CONFIRMATION_PATH` | Absente | `/app/lifecycle/authenticated-confirmation.sqlite` | `/app/lifecycle/authenticated/authenticated-confirmation.sqlite` |
| `LIFECYCLE_HOLDS_PATH` | Absente | `/app/lifecycle/holds.sqlite` | `/app/lifecycle/holds/holds.sqlite` |
| `LIFECYCLE_ADMISSION_ANCHOR_PATH` | Absente | `/app/lifecycle/admission-anchor.sqlite` | `/app/lifecycle/admissions/admission-anchor.sqlite` |
| `LIFECYCLE_AUTHENTICATION_KEY_PATH` | Absente | `/app/lifecycle/keys/authentication.key` | Identique à 300 |
| `LIFECYCLE_ADMISSION_KEY_PATH` | Absente | `/app/lifecycle/keys/admission.key` | Identique à 300 |

Sources : Compose E2 `:158-185`, Compose E4 `:167-197`,
`compose.public-beta.vps.yaml:227-257`. Les sept ajouts sont également
présents dans l'environnement d'init de la famille 300 (`E4:53-60`).
Ses modèles `.env.public-beta.example:60-66` contiennent les anciens
chemins plats. Ceux de 280 ne contiennent aucune de ces sept affectations.
Le modèle racine `.env.public-beta.example:60-66` conserve lui aussi les
chemins plats ; il ne doit pas être assimilé au `.env` VPS.

E6 : `f6e0895…:compose.public-beta.vps.yaml`, blob
`d712ea8b6a138a4077feedf7b59fd48fde7cd03b`. Son diff contre le blob 300
`cb2ff689ecb483d58dba7388baabad610bcf4a4b` montre les cinq remplacements
API ci-dessus. Dans init : capacités SETUID/SETGID, corrections des artefacts
root-owned, déplacement des magasins plats, puis initialisation après
abandon des privilèges ; clés conservées en root:app.

E7 : `ops\public_beta\lab\test_lifecycle_owner_mismatch_fix.ps1:20-38,112-130`
et son ajout dans `f6e0895…`. Les projets sont `pubbeta-lab-fresh` et
`pubbeta-lab-partial`, avec image `documind-s14-6-api:local`. Les commandes
créent DB et exécutent init en laboratoire : elles ne créent pas
`documind-public-beta-api-1`.

Le rapport
`DOCUMIND_PUBLIC_BETA_LIFECYCLE_INIT_OWNER_MISMATCH_FIX_REPORT.md:5-18,20-56,58-96`
relate `Confirmation storage owner mismatch`, les deux phases et les
résultats de laboratoire. Il est un indice cohérent avec le code.
Ce rapport et `DOCUMIND_PUBLIC_BETA_LIGHT_DEPLOYMENT_PLAN.md` ne figurent
pas dans le checkpoint f6e0895 : leur date locale « 31 octobre » ne prouve
pas que leur texte courant était disponible avant 01:11:06.

**D :** une création ordinaire depuis la famille 300 seule impose les
anciens cinq chemins explicites, même si un env_file contient les nouveaux.
La famille 362 impose les nouveaux. Pour 280, une origine externe des sept
valeurs reste à établir. Les observations antérieures annoncent cinq
nouveaux chemins effectifs, sans relevé original disponible ici
(`DOCNELO_LIFECYCLE10_HISTORICAL_HASH_ANALYSIS.md:19-24,55-74`).
Ces éléments ne suffisent pas à choisir une famille de création.

## 5. Environnement, ordre des fichiers et commandes de création

Il faut distinguer les fichiers `--env-file` du CLI, servant au contexte
d'interpolation, et le `env_file` du service, chargeant l'environnement
API. Une égalité de valeurs effectives n'atteste pas leur origine déclarative.

| Trace conservée | Chaîne décrite | Valeur probante |
|---|---|---|
| Compose E2/E4/courant, `api.env_file` | Un fichier `${PUBLIC_BETA_ENV_FILE:-.env.public-beta}` ; image `${BACKEND_IMAGE:?…}` ; bind `${RECOVERY_CONTROL_FILE:?…}` | V pour les expressions locales ; valeurs et chemins réellement résolus à la création inconnus |
| Plan initial `DOCUMIND_PUBLIC_BETA_LIGHT_DEPLOYMENT_PLAN.md:208,316-338` | Un `--env-file .env.public-beta`, un `-f compose.public-beta.vps.yaml`, `-p documind-public-beta` ; propose `up -d api` à la ligne 335 | I : le plan dit explicitement « proposées pour revue », aucune exécution attestée |
| Rapport owner mismatch `:108-134` | Export de `PUBLIC_BETA_ENV_FILE=.env.public-beta`, un `--env-file`, DB puis `run --rm lifecycle-init` | I : procédure de correction ; l'étape API est expressément laissée hors périmètre en fin de procédure |
| `docs\docnelo\DOCNELO_PUBLIC_BETA_DEPLOYMENT.md:32-44` | Un env-file, un Compose, `up -d` global après config/pull | I : commandes indicatives d'un plan « No Auto-Deploy », pas journal |
| `DOCNELO_PUBLIC_BETA_10_USERS_API_DEPLOYMENT_RUNBOOK.md:3,78-100` | Deux env-files ordonnés : `.env.public-beta`, puis `.env.public-beta.images` ; project-directory physique, fichiers actifs ordonnés, latch fourni au processus | I : préparation Lifecycle 10 ultérieure, explicitement non exécutée sur VPS |
| `ops\public_beta\VPS_BACKUP_RESTORE_RUNBOOK.md:48-50` | Deux env-files dans le même ordre | I : procédure d'exploitation, pas preuve de la création initiale |

La présence d'un modèle `.env.public-beta.images.example` dans les exports
ne démontre pas l'utilisation de deux `--env-file` à 01:11:06.
La référence d'image apparaît aussi dans
`exports\public-beta-candidate-20261030T234818Z\.env.public-beta.example:7`.
Une variable shell ou un second env-file peut la remplacer ; le contexte
de lancement réel manque.

Le fichier
`compose.public-beta.vps.registration-gate.override.yaml` figure dans le
checkpoint initial. Les procédures Web ultérieures parlent aussi d'overrides
actifs. Leur présence dans le dépôt n'atteste ni leur ordre ni leur inclusion
dans la commande ayant créé l'API.

**Aucune commande exécutée de création/recréation**, avec date, code retour,
ID du conteneur et entrées exactes, n'a été retrouvée. Les commandes
historiques citées dans les sources ne doivent pas être réexécutées.

## 6. Image API : preuve de contenu, pas de lancement Compose

E5 : `deliveries\docnelo-10-users\api-active.tar`, 305131008 octets,
SHA-256 recalculé :

```text
2ee6ab4f9a5eee4e6dad475e0a2988745472e12a918e186580a36e2e6c631081
```

Son `manifest.json` désigne le config blob
`blobs/sha256/4aa850b6fb8d16b32fd731d94b232b2f817f461892b3f39a28e7557a25a5eb3d`.
Le SHA-256 des octets de ce blob correspond exactement à l'ID d'image
annoncé. Métadonnées sélectionnées vérifiées : `created` à 00:10:54,
linux/amd64, `User=app`, aucune entrée Env `LIFECYCLE_*`, aucun label OCI
de provenance. L'archive n'est pas chargée dans Docker.

Le rapport `DOCNELO_PUBLIC_BETA_10_USERS_API_PROVENANCE.md:7-28` atteste
une correspondance de contenus applicatifs, puis une référence composite
Git. Il précise que cette référence n'est pas la chaîne CI historique.
Ni cette correspondance, ni le tag archivé, ni la date de build ne
restituent le fichier Compose, son cwd ou la commande de création.

Les `IMAGE_INSPECT_api.json` présents dans les répertoires E2/E3/E4 ont
le même SHA-256 :
`17eb40918fbfd5491b9db0f603a2f698d49a9f92d3e7c63df2fe7ebd6dc6110a`.
Ils désignent `sha256:5433a167dba0cf1230ba967994e6d49bb5c50fbfe8afc64f1fbab646b5a19231`,
tag `documind-s14-6-api:local`, Created
`2026-10-30T18:40:51.704667657Z` (`IMAGE_INSPECT_api.json:3-9`).
Ils sont absents des quatre tar.gz et de leurs manifestes internes.
Ils sont donc des métadonnées locales supplémentaires, sans attestation
d'empaquetage ni lien avec la création du conteneur VPS recherché.

## 7. Hypothèses restantes et informations manquantes

| Hypothèse | État | Élément discriminant manquant |
|---|---|---|
| 362 transféré après le correctif puis utilisé à 01:11:06 | Chronologiquement compatible, non prouvé | Reçu de transfert et copie des octets utilisés ; commande de création et contexte expliquant le hash cible |
| 300 utilisé avec un override ou une modification intermédiaire | Plausible, non documenté | Octets de chaque entrée intermédiaire, ordre et journal ; les cinq corrections seules ne prouvent pas le hash |
| 280 utilisé, sept valeurs issues d'un env-file amendé | Hypothèse bornée, pas démontrée | Env-file réel à la création ; les modèles 280 et l'environnement d'image ne fournissent pas ces sept valeurs |
| Autre ordre d'env-files, chemin de service env_file, variable shell ou option Compose | Non exclu | Contexte d'interpolation de création et options/version effectives ; pas d'essais arbitraires |
| Init seul explique le hash du service API | Non établi ; insuffisant sans delta API | Le diff local montre aussi cinq modifications API ; les expériences antérieures isolant init ne valent pas preuve VPS (`DOCNELO_LIFECYCLE10_HISTORICAL_HASH_ANALYSIS.md:9,77-81`) |
| Sauvegarde nommée 005952 ou HEAD d'export suffit à prouver le déploiement | Insuffisant | Fuseau, journal de copie, identité des octets et preuve d'utilisation manquent |

Pour fermer la provenance, il manque une chaîne cohérente réunissant :

1. L'inspect original expurgé avec **ID complet**, Created, StartedAt, image,
   référence textuelle et labels Compose, dont le hash cible, project,
   working_dir, config_files et version. Un nom réutilisable ne suffit pas.
2. Une trace opératrice datée de la création/recréation à 01:11:06 :
   commande exacte, cwd, options, ordre des `-f` et des `--env-file`,
   résultat et rattachement à cet ID de conteneur.
3. Les copies privées authentifiées des Compose/overrides et des contextes
   d'environnement utilisés à cet instant, avec empreintes, provenance et
   disposition physique expliquant les chemins relatifs. Ne pas publier les
   valeurs sensibles ni demander une histoire shell brute.
4. La sauvegarde VPS de 300 lignes et son empreinte, plus la trace de
   copie/remplacement et son fuseau. Son égalité éventuelle avec E4
   identifierait son contenu, pas son utilisation lors de la création.
5. Un rejeu fidèle des **entrées originales attestées** avec la version
   Compose de création, reproduisant séparément le hash API cible et les
   références Web/DB. Un match obtenu par une hypothèse reste distinct de
   la preuve de provenance.

Les journaux Docker/systemd ou un reçu de transfert peuvent compléter cette
chaîne s'ils ont été conservés. Aucun n'est disponible localement pour
la fenêtre recherchée ; le rapport ne suppose pas leur disponibilité
ultérieure ni la persistance d'événements Docker anciens.

## Verdict

**NO-GO Lifecycle 10.** La recherche identifie les sources conservées et
leur évolution, mais ne relie pas encore une configuration exacte au
conteneur créé à 01:11:06 UTC et au hash `e0559d…`.

Aucun fichier de production, clé, conteneur, label ou témoin lifecycle
modifié. Aucune migration, ouverture, restauration, intervention VPS ni
configuration fabriquée. Les releases et diagnostics scellés restent intacts.
