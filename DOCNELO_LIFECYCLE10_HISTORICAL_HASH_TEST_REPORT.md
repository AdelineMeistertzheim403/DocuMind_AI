# Lifecycle 10 — Qualification de l’analyse historique

Date : 31 octobre 2026. Dossier : `deliveries/docnelo-lifecycle10-historical-analysis-r1/`.

## Résultat

**14 tests réussis, 0 échec, 0 erreur, 0 ignoré.** Journal et comparaison expurgée : `test-results.json`.

Les tests utilisent trois vrais fichiers **locaux** : export 280 lignes SHA-256 `8fd28b87a0b03a1fa409e5b63161eaa6134cd705fbb6315dbb45bb3b2cbcb515`, export 300 lignes SHA-256 `15f42bf1f3332d2052c0f304994d0fab455fe86a84c627e4749195123d3c0fd0` et source 362 lignes SHA-256 `f46571b71b7a3174c96b15b2848f2b31cdae60339621116eb14be03393dc4ff2`. La sauvegarde réelle VPS n’est pas disponible localement et n’est pas réputée identique à l’export.

## Conditions

* Docker Compose officiel **2.35.1**, binaire vérifié SHA-256 `7bdb2ce2916e5dd0354e5d129892bf96fdcdb1a9ab8eed69b9173e131db4c230`.
* Python **3.13.17**, image locale de laboratoire `sha256:0b82274b92ba84a7d3049dce0f454d091e71b43ed83a317b451ff4b676b22904`.
* Aucun réseau ni socket Docker dans le laboratoire, racine en lecture seule, capacités supprimées, no-new-privileges.
* Sources Compose, code r2 et binaire montés en lecture seule. Aucun fichier Compose existant modifié. Contexte et données d’environnement fictifs créés uniquement dans un nouveau tmpfs privé.
* Aucun conteneur applicatif créé depuis les modèles : seules les commandes `version` et `config`/`config --hash` sont utilisées.

Le code r2 scellé est réutilisé pour les tests, sans modification. Aucun nouvel outil VPS n’est livré : la procédure utilise r2 déjà qualifié. Le binaire Compose et les sources Compose ne sont pas recopiés dans ce nouveau dossier.

## Cas vérifiés

1. Identification et intégrité des trois sources locales.
2. Version exacte du moteur 2.35.1.
3. Différence API limitée aux cinq déclarations de chemins lifecycle.
4. Égalité des déclarations DB/Web.
5. Différences présentes dans lifecycle-init.
6. Hash API différent entre les deux sources, hashes DB/Web conservés dans le même contexte.
7. Substitution en mémoire du seul service lifecycle-init : hash API et hashes DB/Web inchangés.
8. Substitution en mémoire des seuls cinq chemins API anciens par les valeurs courantes : hashes API/DB/Web courants retrouvés.
9. Environnement **synthétique** de forme courante : comparaison des chemins 0/5 pour ancien et 5/5 pour courant.
10. Rejeu `defer_paths` fidèle des trois sources.
11. Rapport ne contenant pas les valeurs d’environnement fictives servant de marqueurs sensibles.
12. Différence API 280→362 limitée exactement aux sept déclarations lifecycle.
13. Même environnement effectif possible pour 280 et 362, mais hash différent, quand env_file fournit les sept valeurs.
14. Omission en mémoire des sept déclarations : modèle et hash API 280 retrouvés, sans changement des hashes DB/Web courants.

Les substitutions sont des expériences d’attribution sur des objets en mémoire. Elles ne produisent aucun fichier Compose hybride et ne sont pas proposées comme déploiement. L’égalité du cas 8 n’est pas une preuve de provenance et n’est jamais utilisée pour lever le garde.

## Reproduction locale

Depuis le poste de qualification où le moteur et r2 scellé sont déjà présents :

```powershell
& .\deliveries\docnelo-lifecycle10-historical-analysis-r1\run_local_tests.ps1
```

La réexécution écrit `test-results.json` local ; pour conserver un dossier déjà scellé, qualifier dans une copie et ne pas écraser les résultats livrés. Ces tests ne sont pas à lancer sur le VPS actif.

## Inventaire

Le dossier contient `test_history.py`, `run_local_tests.ps1`, `test-results.json`, `RELEASE.json`, les trois documents `DOCNELO_LIFECYCLE10_HISTORICAL_HASH_ANALYSIS.md`, `DOCNELO_LIFECYCLE10_HISTORICAL_HASH_OPERATOR_PROCEDURE.md`, `DOCNELO_LIFECYCLE10_HISTORICAL_HASH_TEST_REPORT.md`, et `SHA256SUMS`. Le manifeste couvre les sept fichiers précédents, sans se référencer lui-même. Aucun secret, fichier .env, Compose, image, donnée ou relevé réel VPS n’est inclus.

## Limites et verdict

Les hashes du résultat sont **synthétiques** et ne doivent pas être comparés directement au label D du VPS. La configuration locale et les déclarations du fichier réel `.bak` doivent encore être rapprochées. Le contexte de création et la provenance ne sont pas établis par les tests.

**NO-GO maintenu**, malgré les tests réussis. Aucun accès VPS, garde modifié, migration, redémarrage, ouverture ou action sur les clés/témoins.
