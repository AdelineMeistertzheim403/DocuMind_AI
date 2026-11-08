# Lifecycle 10 — Rapport de tests du garde Compose

Date : 31 octobre 2026. Release : `docnelo-lifecycle10-compose-guard-r1`.

## Résultats

| Qualification | Réussis | Échecs | Erreurs | Ignorés |
|---|---:|---:|---:|---:|
| Tests Python synthétiques | 62 | 0 | 0 | 0 |
| Vérifications d’intégration du moteur Compose | 6 | 0 | 0 | 0 |

Les résultats détaillés sont livrés dans `unit-test-result.json` et `compose-hash-test-result.json`. Les sous-cas de flags et d’approbation ne sont pas comptés comme tests supplémentaires.

Le laboratoire utilise l’image locale existante `sha256:0b82274b92ba84a7d3049dce0f454d091e71b43ed83a317b451ff4b676b22904`, Python 3.13.17, utilisateur app. Le conteneur est temporaire, sans réseau, racine en lecture seule, capacités supprimées, no-new-privileges, répertoires de travail synthétiques en tmpfs. Le nouveau correctif et le parent sont montés en lecture seule. Aucun socket Docker n’est monté dans ce laboratoire ; les opérations du garde sont simulées.

Les trois fichiers Python livrés passent aussi l’analyse syntaxique ciblant Python 3.11. Le code opérateur utilise uniquement des API de bibliothèque standard disponibles en 3.11. Les tests n’ont pas été exécutés ici par un interpréteur Python 3.11 ; cette limite est explicite. Le `--help` et les précontrôles du runbook doivent être exécutés avec l’interpréteur 3.11 opérateur avant toute intervention.

Les six tests d’intégration utilisent le véritable Docker Compose local **5.5.1**, via `config --hash` uniquement, avec un fichier d’environnement synthétique vide et des services fictifs. Aucun service de ces modèles n’est lancé et aucune image n’est tirée.

## Couverture des 62 tests Python

| Domaine | Cas couverts |
|---|---|
| Référence historique | Tous les contrôles passent, garde scellé passé et nouvelle preuve en contrôle final |
| Deux champs publics | Premier refus historique `effective_environment_drift`, C/API différent, H/API identique, attente humaine obligatoire |
| Dérive résiduelle | Deux champs ne suffisent pas à expliquer un hash inconnu : NO-GO |
| Environnement | Troisième variable, variable supplémentaire inexpliquée, héritage image prouvé et faux héritage refusé |
| Overrides | Web R2 conservé, manquant et réordonné |
| Images et services | API/Web/candidate différentes, configuration d’image candidate modifiée, DB et Web divergents |
| Montages | Noms physiques, bind normalisé, remplacement de volume et passage RO/RW |
| Réseaux | Réseau ajouté, ID physique divergent, alias supplémentaire |
| Runtime | User app hérité, user/commande/capacité modifiés, restart, tmpfs normalisé ou divergent, logging divergent, version Compose divergente |
| Structure candidate | Modification du Web par l’override candidat refusée |
| Lifecycle | Namespace erroné ou existant non approuvé, compteur/closed/limite/mode, booléen abusif au lieu d’un entier, latch, tous les flags dangereux |
| Preuves | Statut d’authentification, observation indépendante et sources incorrects, preuve ancienne changée lors du probe frais, échec du probe |
| Approbation | False, liaison périmée, identité/justification vides, décision d’adoption actuelle et scope incorrect refusés |
| CLI | Audit retourne non-zéro en attente de revue ; prepare sans accord refusé ; prepare approuvé conserve seulement l’ancienne valeur ; check approuvé revalide la preuve |
| Confidentialité | Marqueurs fictifs absents des rapports/logs, modes 0600, aucun écrasement, liens et accès groupe refusés |
| Stabilité | Changement pendant l’audit refusé ; changement `.env` après approbation refusé ; dates des sondes sans effet sur la liaison |
| Exhaustivité | Plusieurs erreurs indépendantes sont rapportées malgré le refus d’environnement historique |

Le parent est vérifié intégralement : **37 entrées SHA-256 conformes, plus le manifeste lui-même épinglé** ; soit 38 fichiers scellés préservés. Les quatre rapports et le garde existants ne sont pas remplacés.

Les 12 entrées du nouveau manifeste ont également été vérifiées avec GNU `sha256sum --check --strict` sous Linux. Les six blocs Bash du runbook passent `bash -n`, sans exécuter leurs commandes.

## Preuve d’intégration Compose

| Cas synthétique | Résultat |
|---|---|
| Deux valeurs publiques changées | Hash API différent |
| Nouvel override restituant les deux anciennes valeurs | Hash API historique reproduit exactement |
| Troisième variable changée malgré ce freeze | Hash toujours différent, refus maintenu |
| Web R2 avec freeze API | Hash Web conservé |
| Override Web R2 omis | Hash Web différent |
| DB avec freeze API | Hash DB conservé |

Empreintes **synthétiques**, sans rapport avec les labels réels du VPS :

```text
API historique     d989573465aadadfa8ab3d96eb37f515b320e536cd3e9281f6b08b33bf7984ac
API courante       aa1e16a9a2e26a3dccd1f05fd1249c244cdd80d2bd9fb21191766f4408ac7c82
API reconstruite   d989573465aadadfa8ab3d96eb37f515b320e536cd3e9281f6b08b33bf7984ac
```

## Reproduction locale

Depuis PowerShell, avec les images locales déjà présentes :

```powershell
& .\deliveries\docnelo-lifecycle10-compose-guard-r1\run_local_tests.ps1
& .\deliveries\docnelo-lifecycle10-compose-guard-r1\qualify_compose_hash.ps1
```

Ces scripts produisent des preuves locales ; leur réexécution peut changer les dates ou chemins temporaires de résultat et invalider le manifeste de livraison. Qualifier dans une copie de laboratoire si l’on souhaite conserver un bundle déjà scellé.

## Limites et verdict

Aucun accès VPS, SQL réel, fichier `.env` réel, clé ou volume applicatif n’a été utilisé dans ces tests. Pas de migration, de sauvegarde relancée, de bascule, d’IA ou d’ouverture. Pas de reconstruction d’image. Le jeu de tests vérifie la logique de refus et le rapprochement synthétique ; il ne prétend pas vérifier de vraies signatures HMAC dans les magasins du VPS. Cette authentification reste imposée par le probe candidat scellé lors du contrôle opérateur final.

**GO pour la préparation locale du correctif. NO-GO pour poursuivre sur le VPS sans preuves et approbation réelles.**
