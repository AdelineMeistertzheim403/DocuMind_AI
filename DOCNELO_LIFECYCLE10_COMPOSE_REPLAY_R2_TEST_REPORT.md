# Lifecycle 10 — Qualification du diagnostic indépendant r2

Date : 31 octobre 2026. Release : `docnelo-lifecycle10-hash-diagnostic-r2`.

## Résultats finaux

| Suite | Réussis | Échecs | Erreurs | Ignorés |
|---|---:|---:|---:|---:|
| Scénarios ciblés avec Compose 2.35.1 | 16 | 0 | 0 | 0 |
| Logique et contraintes du diagnostic | 11 | 0 | 0 | 0 |
| Collecte complète sur conteneurs simulés et Compose réel | 11 | 0 | 0 | 0 |
| **Total** | **38** | **0** | **0** | **0** |

Preuve détaillée : `test-results.json`, avec journal de chaque test et matrice d’un exemple synthétique. Les sous-assertions ne sont pas comptées comme tests supplémentaires.

Python exécuté : **3.13.17**. Les deux fichiers Python passent aussi l’analyse syntaxique ciblée Python 3.11 et utilisent des API standard disponibles en 3.11. Aucun interpréteur 3.11 local n’a exécuté ces tests ; ce point reste explicite. L’opératrice dispose du Python 3.11 déjà validé sur son VPS, à vérifier avec `--version`/`--help` selon la procédure.

## Environnement de qualification

Image locale existante figée par ID :

```text
sha256:0b82274b92ba84a7d3049dce0f454d091e71b43ed83a317b451ff4b676b22904
```

Conteneur jetable, sans réseau, sans socket Docker, racine en lecture seule, capacités supprimées, no-new-privileges, tmpfs de 32 Mio. Code r2 et binaire Compose sont montés en lecture seule. **Aucune release parent ou r1 n’est montée dans ce laboratoire.** Aucune base, clé, volume ou donnée réelle n’est utilisé.

Binaire autonome `docker-compose-linux-x86_64` de la [release officielle v2.35.1](https://github.com/docker/compose/releases/tag/v2.35.1), déjà conservé dans le laboratoire local. SHA-256 vérifié avant exécution :

```text
7bdb2ce2916e5dd0354e5d129892bf96fdcdb1a9ab8eed69b9173e131db4c230
```

Ce binaire est exclu de Git et du bundle. Il n’est pas envoyé au VPS. Les commandes exécutées par les tests sont uniquement `version` et `config`/`config --hash` ; le moteur autonome n’a pas besoin d’un daemon dans le laboratoire.

## Défauts reproduits et corrections vérifiées

* Chemin absolu obtenu par interpolation dans un env_file ou bind : le rendu r1 prématurément résolu produit un autre hash au rejeu.
* Ajout de `--no-path-resolution` lors du rendu : hashes natifs reproduits pour les trois services dans ces scénarios.
* Modèle de forme Public Beta avec trois montages, trois réseaux, image interpolée, limites, délai d’arrêt, healthcheck, logging et tmpfs : même défaut r1, même restauration du rejeu fidèle.
* API fidèle mais DB infidèle : les résultats par service détectent l’ambiguïté masquée par l’ancien booléen agrégé.
* Fichiers env_file relatifs, absolus, multiples et ordonnés : déclarations conservées ; permutation sensible au hash ; aucun remplacement par des valeurs effectives.
* Anciennes valeurs chargées depuis env_file : changement du contenu sans modification du hash dans le scénario testé ; ajout explicite d’une ancienne valeur modifiant le hash.
* Overrides successifs et référence textuelle d’image : sensibilité au modèle et conservation de la chaîne.
* Dollar littéral : décodage du rendu effectif et rejeu fidèle ; valeur nulle inexploitable refusée.

## Collecte et refus

Les tests de collecte complète vérifient : NO-GO systématique, distinction entre déclarations et conservation effective, absence des valeurs fictives dans le rapport, comparaison des anciens triplets de hashes, absence d’approbation quand un historique rejoint D, dérive C/D persistante, comparaison de sources historiques originales sans gel, mauvaise version refusée, troisième variable inexpliquée non approuvée, modification en cours de collecte refusée et vue déclarative indisponible rapportée comme inconnue plutôt que comme absence.

La logique indépendante vérifie aussi les JSON Pointers, l’ordre des listes, les environnements sous forme liste/mapping, l’absence d’import de code scellé, la syntaxe 3.11, le refus des opérations Docker/Compose mutantes, les doublons d’environnement et l’absence d’appels d’écriture de fichiers dans le diagnostic.

## Reproduction locale

Avec l’image de laboratoire et le binaire officiel déjà présents sur le poste :

```powershell
& .\deliveries\docnelo-lifecycle10-hash-diagnostic-r2\run_local_tests.ps1
```

Le script vérifie l’empreinte du binaire, exécute les tests sans monter les releases précédentes et écrit uniquement le résultat local. Après scellement, rejouer dans une copie de qualification pour ne pas réécrire `test-results.json` du bundle livré. Aucun script de test n’est à lancer sur le VPS actif.

## Limites et verdict

L’exemple de chemins démontre un mécanisme exact, pas son occurrence dans les fichiers réels du VPS. Le rapport opérateur communiqué ne permet pas de choisir entre les causes possibles du `false` agrégé. Les sources historiques de création restent à authentifier ; un hash égal obtenu par une hypothèse n’est pas une provenance.

Les contrôles lifecycle, quotas, flags, HMAC et latch ne sont pas exécutés par ce diagnostic ; leurs garde-fous existants restent inchangés et obligatoires pour une future intervention. Aucun probe, migration, redémarrage, déploiement ou ouverture réalisé.

**NO-GO maintenu pour la suite du déploiement fermé.** Les 38 tests réussis qualifient l’outil r2 et ses refus, sans valider le VPS ou autoriser une bascule.
