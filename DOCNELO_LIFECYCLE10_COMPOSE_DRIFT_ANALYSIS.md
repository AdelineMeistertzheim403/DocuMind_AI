# Lifecycle 10 — Analyse de la dérive Compose

Date : 31 octobre 2026. Périmètre : préparation fermée, sans accès VPS.

## Conclusion et niveau de preuve

Le code scellé vérifie l’environnement effectif **avant** les empreintes Compose. Les deux différences signalées par l’opératrice suffisent donc à provoquer `effective_environment_drift`, si les conditions précédentes passent. Elles ne démontrent pas que toute la dérive de l’empreinte API est expliquée.

Nous n’avons pas exécuté le diagnostic sur le VPS. Le message générique reçu ne révèle pas la première exception réelle. La première condition sur les témoins réels reste à enregistrer par l’opératrice ; il serait inexact d’affirmer qu’elle a déjà été observée par ce travail. Le nouveau garde appelle la fonction originale scellée, avec les mêmes entrées, et conserve son premier motif dans `legacy_first_failure`. Il contrôle ensuite les autres conditions indépendamment, lorsque les entrées nécessaires sont lisibles.

## Références inchangées

| Élément | Référence |
|---|---|
| API active | `sha256:4aa850b6fb8d16b32fd731d94b232b2f817f461892b3f39a28e7557a25a5eb3d` |
| Candidate | `sha256:32a1516206d9e648e3741b54dc0543c0b455f22cdf676e7d69d9a971e1f4213d` |
| Web R2 | `sha256:ebdbc7fba1c61c03349088ca093470c78eec9dd91c5e2aa92ab1d8c0db5be362` |
| Application physique | `/opt/documind-public-beta/public-beta-candidate-20261030T234818Z` |
| Projet / namespace signé | `documind-public-beta` |
| Bundle parent | `lifecycle10-8b11d4daf47b` |
| SHA-256 du manifeste parent | `9d077ca43a8995429e6a471f30e9cd12d7724292a56dd6a74332c4f0954497c5` |

Les constats de santé, UID/GID 1000, trois montages, trois réseaux, Web conforme, API non conforme et date de modification de `.env.public-beta` sont des constats opérateur fournis. Aucune valeur publique ancienne ou actuelle n’a été demandée, copiée dans ce dépôt ou incluse dans les rapports.

## Ordre réel du garde historique

Source : `deliveries/docnelo-lifecycle-10-api/payload/check_closed_compose.py`, conservée sans modification.

| Ordre | Condition bloquante |
|---|---|
| 1 | Preuve initiale : 0007, quota 0/fermé, disabled/cinq, flags sûrs, latch ready, observation cohérente, namespace Beta |
| 2 | Projet et santé des conteneurs |
| 3 | Images API active et Web R2 |
| 4 | Chemins Compose physiques revus ; inclusion des overrides actifs API/Web |
| 5 | Modèles courant et candidat : projet, tag, namespace autorisé, absence d’autre delta structurel |
| 6 | Namespace effectif autorisé |
| 7 | Environnement attendu comparé à celui de l’API : `effective_environment_drift` |
| 8 | Garde opérationnelle maintenue fermée |
| 9 | Empreinte API, puis empreinte Web : `compose_config_hash_drift` |
| 10 | ID du tag candidat |

Le garde historique s’arrête à la première exception, puis masque son motif dans son CLI. Un échec à l’étape 7 empêche donc toute conclusion issue de son étape 9. Le nouveau garde importe cette fonction originale après vérification cryptographique des fichiers utilisés ; il ne réimplémente pas approximativement son ordre.

## Rapprochement de trois états

* **C** : configuration actuelle rendue avec tous les fichiers actifs dans leur ordre, les deux fichiers d’environnement existants et le répertoire de projet physique.
* **H** : C plus un nouvel override privé ne conservant que les anciennes valeurs effectives des deux champs publics en différence.
* **D** : H plus l’override candidat scellé : image, `pull_policy=never`, namespace authentifié explicite.

La méthode retenue conserve l’identité publique actuellement exécutée. Elle n’adopte pas les nouvelles valeurs du `.env`. Toute adoption de ces nouvelles valeurs demanderait une autre revue, notamment juridique, et un autre changement qualifié.

H doit reproduire **exactement** les empreintes déployées API, Web et DB. Les empreintes C du Web et de DB doivent déjà correspondre à leurs labels. Le label API existant reste la référence, sans réécriture. Un désaccord résiduel H/API signifie NO-GO, même si les deux champs publics ont été rapprochés et approuvés.

Cette approche est démontrée localement sur des modèles synthétiques avec le vrai Compose 5.5.1 : le gel restaure l’empreinte API historique, conserve Web R2/DB et ne masque pas une troisième variable. Elle reste à démontrer sur les fichiers réels, avec la version Compose ayant créé les conteneurs. Une version différente ou des versions historiques divergentes restent bloquantes ; aucune dérogation automatique n’est prévue.

## Autres conditions à vérifier

Le nouveau rapport distingue : inclusion et ordre des overrides pour les trois services ; images résolues et ID fixes API/Web/candidate ; configuration d’image candidate inchangée ; environnement complet issu de l’image et de Compose ; UID/GID ; commande, utilisateur et répertoire hérités ; droits Docker, ressources déclarées, redémarrage, tmpfs, logging, labels ; noms physiques des montages et réseaux, leurs ID résolus, alias et adresses statiques déclarées.

Les six variables supplémentaires ne sont jamais réputées normales sur la seule base de leur nombre : leur origine et leur valeur doivent correspondre à `image inspect Config.Env`. Toute variable supplémentaire inexpliquée ou troisième différence est refusée. Les valeurs restent en mémoire ; le rapport n’expose que les noms et des empreintes.

Les paramètres lifecycle sont contrôlés séparément. Le contrôle final relance le probe candidat scellé, sans serveur applicatif, worker ou migration, puis compare les preuves, les neuf empreintes de modules, le namespace HMAC, quota, flags et latch. Un JSON historique seul ne suffit pas au contrôle final.

## Verdict

**GO pour préparer et livrer le correctif local qualifié. NO-GO pour poursuivre la migration ou la bascule sur le VPS tant que le diagnostic exhaustif réel, l’empreinte H identique au label API, l’approbation opératrice liée au relevé et la nouvelle preuve authentifiée ne sont pas obtenus. Aucune autorisation d’ouverture publique.**
