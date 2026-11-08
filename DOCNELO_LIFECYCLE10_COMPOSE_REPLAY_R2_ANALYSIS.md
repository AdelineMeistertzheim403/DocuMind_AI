# Lifecycle 10 — Analyse du rejeu historique Compose r2

Date : 31 octobre 2026. **Verdict : NO-GO.**

Release indépendante : `docnelo-lifecycle10-hash-diagnostic-r2`. Aucun correctif des releases scellées précédentes, aucune commande VPS exécutée.

## 1. Causes confirmées et limites

| Question | État de preuve |
|---|---|
| Pourquoi le gel des valeurs effectives n’établit-il pas l’historique ? | Confirmé par l’opératrice et les tests : les deux champs publics n’étaient pas explicites dans C ; r1 ajoute des déclarations `environment` |
| L’injection r1 reprend-elle les bonnes valeurs ? | Oui selon le relevé réel : `r1_exact_two_field_injection=true` ; cela ne prouve pas la fidélité déclarative |
| Pourquoi le rejeu peut-il être infidèle ? | Mécanisme reproduit sur Compose 2.35.1 : résolution des chemins avant interpolation, puis seconde interpolation au rejeu |
| Ce mécanisme est-il la cause exacte du `false` sur le VPS ? | Pas encore établi : le résumé fourni ne contient pas les résultats de rejeu par modèle/service ni leurs différences |
| Quelle déclaration a produit D sur l’API ? | Inconnue : aucune chaîne de création authentifiée n’a été fournie ou retrouvée localement |
| Les tests autorisent-ils un déploiement ? | Non ; ils qualifient uniquement le diagnostic |

Le rapport réel `/home/debian/docnelo-hash-evidence.evPkFKul/diagnostic.json` n’est pas disponible sur ce poste. Son résumé fourni par l’opératrice est traité comme une observation, sans accès VPS pour le récupérer. Aucune valeur sensible n’a été demandée ou recopiée.

## 2. Calcul exact de Compose 2.35.1

`config --hash` charge le projet avec `WithoutEnvironmentResolution`, applique les plateformes, puis utilise `ServiceHash`. Celui-ci sérialise le modèle Go du service après retrait de build, pull_policy, scale, deploy.replicas, depends_on et profiles. Le hash n’est pas celui du YAML brut ni du runtime inspecté. [runHash](https://github.com/docker/compose/blob/v2.35.1/cmd/compose/config.go), [ServiceHash](https://github.com/docker/compose/blob/v2.35.1/pkg/compose/hash.go).

Les déclarations `env_file`, leur ordre et leurs chemins ne peuvent donc pas être remplacés par une copie de l’environnement effectif. Les valeurs chargées uniquement depuis le contenu d’un `env_file` n’ont pas le même statut que les entrées explicitement déclarées dans `environment`. Les tests 2.35.1 reproduisent cette différence. Toute future conservation de valeurs effectives doit faire l’objet d’un rapprochement séparé et approuvé.

## 3. Deux défauts du diagnostic r1

### Le booléen ne localise pas l’échec

Le code r1 calcule en substance :

```text
rendered_H_roundtrip_hashes_match =
    égalité des trois hashes de H au rejeu
    ET égalité des trois hashes de C au rejeu
```

`false` peut donc venir de C, H, DB, API, Web, ou de plusieurs éléments. Les égalités directes Web/DB entre C, H et D ne prouvent pas que leur **rejeu** est fidèle. Un test r2 reproduit précisément un cas API fidèle mais DB infidèle, qui aurait été masqué par ce booléen agrégé.

R2 publie chaque égalité par modèle et service. Il ne renomme jamais une hypothèse H1 en « configuration historique démontrée ».

### Le rendu non interpolé résout encore les chemins

R1 rend avec `--no-interpolate --no-env-resolution`, tout en laissant la résolution des chemins et la normalisation actives. Dans compose-go 2.6.0 utilisé par Compose 2.35.1, les chemins relatifs d’env_file et de montages bind peuvent être préfixés par le répertoire de projet. Une expression `${VARIABLE}` n’est pas encore un chemin absolu à ce stade. [Options config](https://github.com/docker/compose/blob/v2.35.1/cmd/compose/config.go), [résolveur de chemins](https://github.com/compose-spec/compose-go/blob/v2.6.0/paths/resolve.go).

Exemple **fictif** reproduit dans le laboratoire :

```text
Déclaration : source: ${RECOVERY_CONTROL_FILE}
Contexte : cette variable fournit un chemin absolu synthétique
Source native : interpolation, puis résolution du chemin
Vue r1 : expression préfixée par le projet avant interpolation
Rejeu : interpolation de cette expression déjà préfixée
Résultat : autre source bind et autre hash
```

Le même défaut est testé avec un chemin absolu fourni par `PUBLIC_BETA_ENV_FILE`. Un rendu résolu peut même devenir impossible à relire si le rejeu cherche un env_file à un mauvais emplacement ; R2 distingue cet échec de rendu de la disponibilité du hash.

**Correction r2 :** conserver les expressions et différer aussi la résolution des chemins lors de la production de la vue à rejouer. La normalisation est testée séparément. Ce changement concerne uniquement la construction d’une entrée de diagnostic. Les hashes de référence et de rejeu sont toujours calculés par le moteur natif, avec ses options normales ; aucun champ n’est retiré du contrôle.

## 4. Matrice r2 de preuve

R2 calcule d’abord les hashes directement depuis les fichiers d’origine, sans aplatissement. Il compare ensuite trois rendus rejoués via stdin, avec le même projet, répertoire physique, ordre d’env-files et environnement de processus figé en mémoire :

| Mode de rendu | Options supplémentaires | Objet |
|---|---|---|
| `r1` | no-interpolate, no-env-resolution | Reproduire le diagnostic précédent |
| `defer_paths` | mêmes options + no-path-resolution | Isoler l’effet de la résolution des chemins |
| `defer_paths_and_normalization` | mêmes options + no-normalize | Tester aussi l’étape de normalisation |

Cette matrice est exécutée séparément sur C et sur **H1, hypothèse r1 de gel**, jamais sur un historique présumé. Chaque entrée indique ses hashes et égalités par service, les chemins JSON Pointer différents du rendu résolu, et les chemins de l’entrée différents de la vue r1. Les valeurs ne sont pas affichées.

Lorsque seule l’option différant les chemins restaure l’égalité, l’effet de cette étape est démontré pour les entrées analysées. Si une étape supplémentaire est nécessaire, elle est distinguée. Si aucun rejeu ne correspond, la cause reste `unexplained_replay_divergence`. R2 n’utilise pas une vue infidèle pour tester des hypothèses historiques.

Les tests sur un modèle de forme Public Beta — trois montages, trois réseaux, image interpolée, env_file, bind de latch interpolé, healthcheck, délai d’arrêt, ressources et tmpfs — reproduisent le défaut r1 et l’égalité avec `defer_paths`. **Ils ne prouvent pas que les fichiers du VPS sont identiques à ce modèle.**

## 5. Historique déclaratif et conservation effective séparés

**Historique déclaratif :** R2 accepte une chaîne de fichiers Compose historiques et ses fichiers d’interpolation historiques, fournis explicitement en lecture seule. Il calcule leurs hashes natifs, leurs rejouements et leurs différences déclaratives avec C. Aucun `environment` de gel n’est ajouté à ce chemin. Les déclarations env_file et leur ordre restent des entrées originales.

**Conservation effective future :** R2 compare l’environnement actuel résolu de C, les valeurs héritées de l’image et l’environnement de l’API active. Il rapporte uniquement les noms différents et une empreinte de l’ensemble de l’environnement actif. Cette observation reste `approved=false`. Elle ne génère aucun override, fichier d’environnement ou approbation. Le gel H1 est seulement calculé en mémoire pour expliquer le précédent diagnostic.

Un hash historique égal à D est nécessaire, mais n’établit pas la provenance. Un fichier joint intitulé « preuve » ne suffit pas davantage. L’origine, la date, la chaîne de création et le contexte d’interpolation doivent être vérifiés humainement. R2 conserve toujours `status=NO-GO`, `opening_authorized=false` et `deployment_authorized=false`.

## 6. Recherche locale de C ≠ D

Les quatre révisions du Compose présentes dans l’historique Git local ont été identifiées, sans modifier le dépôt :

```text
5927e86a3526f0f77935d7f6b8a47b1ba0183a40
3727f4c49f22a0129bb6e41270815b7e5a6d74ec
f6e08955b648012ad53355ba033f35d0d35ca71a
727b95a928d2378d48020ba893463c37a8dcf947
```

La première contient notamment image et env_file interpolés, source du latch interpolée et délai d’arrêt de 150 s. Ce sont des **candidats source**, pas une attestation de leur utilisation lors de la création du conteneur. Le `source-release.json` parent atteste des références source applicatives, pas d’une commande Compose historique complète.

L’image API active déjà présente localement sous l’ID `4aa850…` a été inspectée uniquement pour ses labels OCI de révision et source : tous deux sont absents. Une image et son code source ne permettent pas de déduire l’ancienne référence textuelle fournie à Compose ni les fichiers externes utilisés pour sa création.

Restent nécessaires côté opératrice : ordre et contenu exacts des fichiers de création ; référence image textuelle ; chemins/format/ordre env_file ; options explicites ou héritées ; variables shell et fichiers d’interpolation ; éventuels modes de compatibilité et plateforme. Les labels config_files sont un indice des chemins, sans copie historique de leur contenu. Le hash D est une empreinte, pas une liste de champs récupérable.

Une différence synthétique qui rejoint D n’est plus présentée comme preuve historique. Aucune recherche brute de secrets ou modification des références n’est proposée.

## 7. Inventaire et protections

Bundle `deliveries/docnelo-lifecycle10-hash-diagnostic-r2/` :

| Fichier | Rôle |
|---|---|
| `diagnose_replay.py` | Diagnostic indépendant, bibliothèque standard uniquement |
| `test_replay.py` | Tests unitaires, Compose réel, collecte complète sur fixtures |
| `run_local_tests.ps1` | Qualification locale sans réseau/socket ni dépendance r1/parent |
| `test-results.json` | Journal final et exemple synthétique expurgé |
| `RELEASE.json` | Périmètre, versions, tests, verdict NO-GO |
| `DOCNELO_LIFECYCLE10_COMPOSE_REPLAY_R2_ANALYSIS.md` | Cette analyse |
| `DOCNELO_LIFECYCLE10_COMPOSE_REPLAY_R2_TEST_REPORT.md` | Résultats et limites de qualification |
| `DOCNELO_LIFECYCLE10_COMPOSE_REPLAY_R2_OPERATOR_PROCEDURE.md` | Procédure opérateur reproductible |
| `SHA256SUMS` | Empreintes des huit fichiers précédents |

Le diagnostic n’importe aucun code de release scellée précédente. Un ancien rapport peut être lu en option comme donnée de comparaison, sans dépendance d’exécution. Aucune écriture de fichier ni de cache bytecode. Commandes permises : inspections Docker et config/version/hash Compose. Aucun run, exec, up, pull, build, migration, clé, témoin, quota, inscription ou probe applicatif.

Les fichiers d’entrée et conteneurs sont revérifiés pendant la collecte. Cela ne crée pas de verrou global contre une action administrative concurrente : une fenêtre opérateur exclusive reste nécessaire. Un échec de lecture, une entrée modifiée ou une version autre que 2.35.1 reste un NO-GO.

## Verdict

**NO-GO maintenu.** Les défauts de méthode r1 et un mécanisme précis de rejeu infidèle sont démontrés localement. La cause exacte du rejeu du VPS reste à localiser avec la matrice r2 ; la chaîne déclarative historique produisant D reste à authentifier. Les succès locaux ne valent ni validation de la préparation finale sur VPS, ni autorisation de migration, déploiement ou ouverture publique.
