# Lifecycle 10 — Diagnostic de l’empreinte API résiduelle

Date : 31 octobre 2026. Verdict : **NO-GO pour poursuivre vers migration ou bascule**.

## Ce qui est établi

Le relevé opérateur `/opt/documind-public-beta/compose-review-r1-20261031T183619Z` établit la première erreur réelle du garde historique : `effective_environment_drift`. Après gel des deux anciennes valeurs, H reste différent du label API déployé ; Web et DB restent conformes. Aucun accès VPS n’a été effectué pour cette analyse.

Un défaut de raisonnement de la méthode r1 est maintenant démontré avec le **véritable binaire Compose 2.35.1** : préserver l’environnement effectif ne garantit pas de reconstituer les déclarations ayant produit son hash. En particulier, déplacer une valeur d’`env_file` vers `environment` modifie le hash, même si sa valeur effective est strictement identique.

Ce défaut peut expliquer pourquoi H ne rejoint pas le label déployé. **Il n’explique pas à lui seul pourquoi C diffère déjà de ce label.** L’écart initial demande une autre preuve. Les données reçues ne permettent pas encore d’identifier tous ses champs exacts ; aucune troisième modification n’est réputée autorisée.

Dans ce document, **D désigne uniquement l’empreinte déployée**, conformément à la nouvelle demande. Le D du précédent runbook désignait le modèle candidat : ce ne sont pas les mêmes objets. Ici le modèle candidat est nommé « candidate ».

## 1. Calcul officiel en version 2.35.1

Compose calcule SHA-256 du JSON Go du `ServiceConfig`, après retrait de `build`, `pull_policy`, `scale`, `deploy.replicas`, `depends_on` et `profiles`. Le hash n’est ni celui du fichier YAML brut ni celui de `docker inspect`. L’image sous sa référence textuelle, les déclarations d’environnement et les autres champs sérialisés du service peuvent participer. [Source officielle : ServiceHash 2.35.1](https://github.com/docker/compose/blob/v2.35.1/pkg/compose/hash.go).

Le chemin CLI `config --hash` utilise `WithoutEnvironmentResolution` puis `applyPlatforms`. Le rendu ordinaire JSON résout en revanche les environnements de service. Comparer uniquement ce rendu et les variables du conteneur perd donc une partie de l’information nécessaire au hash. [Source officielle : runHash et runConfigInterpolate](https://github.com/docker/compose/blob/v2.35.1/cmd/compose/config.go).

Le label de configuration est inscrit à partir de `ServiceHash` lors de la création. Les labels techniques ajoutés par Compose ne constituent pas un modèle historique exportable ; les labels utilisateur déclarés restent distincts. L’environnement runtime peut aussi combiner des sources absentes de la déclaration explicite. [Source officielle : prepareLabels et getCreateConfigs](https://github.com/docker/compose/blob/v2.35.1/pkg/compose/create.go).

Les valeurs héritées, valeurs explicites, valeurs par défaut, chemins et listes ne peuvent donc pas être reconstruits sans ambiguïté depuis les seules propriétés finales du conteneur. Le typage et les omissions JSON participent à cette distinction. Compose 2.35.1 dépend de compose-go 2.6.0. [ServiceConfig](https://github.com/compose-spec/compose-go/blob/v2.6.0/types/types.go), [dépendance officielle](https://github.com/docker/compose/blob/v2.35.1/go.mod).

## 2. Vérification de r1

Le code r1 lit bien les deux valeurs **exécutées** dans `Config.Env`, puis crée :

```text
services.api.environment.PUBLIC_CONTACT_EMAIL
services.api.environment.PUBLIC_OPERATOR_NAME
```

Il ajoute cet override en dernier, avec les mêmes fichiers d’environnement, ordre de fichiers de base et répertoire de projet. Il compare aussi le JSON H au JSON C modifié uniquement sur ces deux champs. Les résultats fournis n’indiquent pas d’échec de `historical_only_two_public_values` ni de `desired_effective_environment` : ils sont compatibles avec une injection effective correcte.

En revanche, r1 ne retrouve pas l’origine historique de chaque déclaration. Le Compose local `compose.public-beta.vps.yaml` charge les champs publics via `env_file` et ne les déclare pas explicitement dans le bloc `api.environment`. Si le fichier réellement utilisé sur le VPS a cette structure, le freeze ajoute deux nouvelles entrées hachées. Le nouveau diagnostic vérifie cette condition sur les fichiers réels ; la copie locale seule n’est pas une preuve de leur contenu historique.

Les tests 2.35.1 démontrent que :

* Modifier seulement le contenu d’un `env_file`, à chemin constant, conserve `config --hash` dans le cas testé.
* Ajouter l’ancienne valeur dans `environment` change ce hash.
* Changer le chemin d’`env_file` change le hash, même à contenu identique.
* Une référence d’image textuellement différente, un `user` explicite, un délai d’arrêt ou une healthcheck peuvent changer le hash malgré d’autres contrôles runtime conformes.

Il serait donc incorrect de supprimer les deux champs de la comparaison, d’adopter le hash H, ou d’autoriser une bascule sur la seule égalité des environnements. Le garde r1 et ses attentes sont conservés, sans modification.

## 3. Pourquoi le garde historique refuse H

Le garde scellé vérifie d’abord les variables, puis l’empreinte API, puis celle du Web. Dès lors que les anciennes valeurs sont effectivement restituées et que les étapes précédentes passent, son refus se déplace vers `compose_config_hash_drift` sur l’API. Le contrôle r1 l’enveloppe en `sealed_guard_still_refuses_historical_model`. Ce second échec est la conséquence du désaccord H/API, pas une preuve d’un échec HMAC supplémentaire. Le nouveau diagnostic n’exécute ni ne contourne ce garde pour obtenir un PASS.

## 4. Pistes pour C ≠ D

| Piste | Preuve nécessaire |
|---|---|
| Référence image tag/ID/digest différente, même image finale | Comparer `Config.Image` et la référence résolue de C, puis rejouer uniquement la déclaration observée |
| Paramètre auparavant explicite ou hérité | Modèle historique ou hypothèse fondée sur inspect, hash rejoué égal au label d’origine |
| Chemin/format/ordre `env_file` modifié | Anciennes déclarations conservées dans un relevé ou historique source authentifié |
| Interpolation utilisée hors environnement API | Comparer les champs déclaratifs ; même variable peut alimenter image, montage, commande ou healthcheck |
| Override API oublié, modifié ou ordre changé | Labels API/Web/DB, historique des fichiers et ordre de fusion exact |
| Healthcheck, timeout, labels utilisateur ou options non projetées par r1 | Comparaison structurelle de la préimage historique avec le modèle courant |
| Variables shell, compatibilité, plateforme ou contexte de lancement | Retrouver la commande et le contexte historiques ; les labels de version seuls ne prouvent pas ces entrées |

La modification de `.env.public-beta` après création démontre une chronologie, sans identifier tous ses effets sur le modèle. Web/DB conformes limitent le périmètre, sans expliquer les propriétés propres à l’API.

Le hash est irréversible : il n’existe pas de fonction permettant de comparer les champs de H à ceux de D sans retrouver une préimage. Un inspect conforme ne remplace pas cette préimage. Une recherche arbitraire sur des valeurs secrètes n’est pas proposée.

## 5. Diagnostic supplémentaire livré

Release distincte : `deliveries/docnelo-lifecycle10-hash-diagnostic-r1/`. Elle contient un outil autonome `diagnose_hash.py`, les tests, les preuves, ce rapport et la procédure opérateur. Le manifeste `SHA256SUMS` couvre tous ses fichiers hors lui-même. Aucun binaire téléchargé, secret, relevé réel, image Docker ou donnée n’est livré.

L’outil épingle le manifeste r1 `56c448a98858cc54e226c298bde042d159451c12b2380a5535ac3a7d45dc1431`, vérifie ses 12 entrées et les dépendances parent utilisées. Il ne modifie ni r1 ni le parent. Il n’écrit aucun fichier ; son rapport expurgé est émis sur stdout. Les seules commandes Docker permises sont les inspections et les rendus/hashes Compose. Pas de `run`, `up`, `exec`, pull, build, migration ou recréation.

Il reconstitue le freeze r1 en mémoire, le fournit via `-f -`, compare les trois jeux de hashes au premier audit et vérifie la stabilité des conteneurs/fichiers pendant la collecte. Il produit les noms des champs, jamais leurs valeurs.

Pour préserver les déclarations `env_file`, il utilise une vue d’entrée `config --no-interpolate --no-env-resolution` et exige que son rejeu reproduise les hashes H. **Cette vue n’est pas le JSON Go interne de ServiceHash** : les expressions sont encore présentes. Le moteur Compose exact reste l’autorité pour le rejeu. `--no-env-resolution` seul ne suffit pas dans les tests 2.35.1 : le rendu observé contient encore les valeurs résolues.

Les hypothèses testées sont limitées aux observations Docker : référence image, user/commande/entrypoint/workdir explicites ou hérités, timeout, healthcheck, labels utilisateur et présence de valeurs héritées d’image. Elles partent séparément de C et H, afin que les déclarations ajoutées par le freeze ne masquent pas une explication de C/D. Aucun secret n’est deviné. Si le rejeu des deux bases n’est pas fidèle, ces hypothèses ne sont pas exploitées. Elles ne couvrent pas toutes les combinaisons possibles.

Une hypothèse qui rejoint D identifie une modification déclarative suffisante pour reproduire le hash. Elle ne prouve pas automatiquement sa provenance ni son autorisation. Un modèle historique authentifié peut être fourni ; seules les différences de chemins JSON et l’égalité des hashes sont rapportées.

Les tests révèlent aussi un piège distinct avec les dollars : Compose interpole les valeurs d’overrides et échappe les dollars dans son rendu. Le rejeu doit préserver cet encodage. Ce piège n’est pas attribué au VPS sans preuve ; les contrôles d’injection r1 conformes ne vont pas dans ce sens.

## Verdict

**NO-GO.** Le comportement env_file/environment de r1 est démontré sur Compose 2.35.1, mais l’ensemble des causes réelles de C ≠ D et H ≠ D n’est pas encore démontré sur le VPS. Le prochain résultat attendu est un diagnostic stable, une préimage historique vérifiée ou une explication déclarative complète reproduisant D, puis une revue explicite. Aucun contrôle n’est retiré et aucune approbation n’est créée automatiquement. Aucune migration, ouverture ou intervention VPS effectuée.
