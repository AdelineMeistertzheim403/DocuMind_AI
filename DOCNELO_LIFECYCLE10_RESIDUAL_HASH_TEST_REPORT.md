# Lifecycle 10 — Tests du diagnostic résiduel

Date : 31 octobre 2026. Release : `docnelo-lifecycle10-hash-diagnostic-r1`.

## Résultat final

| Suite | Réussis | Échecs | Erreurs | Ignorés |
|---|---:|---:|---:|---:|
| Diagnostic Python synthétique | 20 | 0 | 0 | 0 |
| Intégration avec Compose **2.35.1** | 17 | 0 | 0 | 0 |
| Total | **37** | **0** | **0** | **0** |

Preuve détaillée livrée : `test-results.json`. Python de qualification : 3.13.17. Analyse syntaxique des trois fichiers Python ciblant Python 3.11 réussie ; pas d’exécution par un interpréteur 3.11 local. Le diagnostic utilise uniquement la bibliothèque standard compatible 3.11.

Image de laboratoire existante : `sha256:0b82274b92ba84a7d3049dce0f454d091e71b43ed83a317b451ff4b676b22904`. Racine en lecture seule, aucun réseau, aucune capacité Linux, no-new-privileges. Données fictives uniquement en tmpfs. Nouveau code, r1, parent et binaire officiel montés en lecture seule. **Aucun socket Docker dans le laboratoire.** Le binaire autonome Compose calcule uniquement des configurations/hashes, sans daemon et sans créer de conteneurs applicatifs.

## Provenance du moteur testé

Binaire `docker-compose-linux-x86_64` téléchargé depuis la [release officielle v2.35.1](https://github.com/docker/compose/releases/tag/v2.35.1). Son SHA-256 a été comparé au fichier officiel `checksums.txt` avant exécution :

```text
7bdb2ce2916e5dd0354e5d129892bf96fdcdb1a9ab8eed69b9173e131db4c230
```

Le binaire reste dans `deliveries/.docnelo-compose-2351-lab/`, exclu de Git et du bundle. Aucun téléchargement ou changement de version Compose n’est nécessaire sur le VPS, déjà en 2.35.1. La qualification précédente de r1 avec Compose 5.5.1 ne remplaçait pas ces tests ciblés.

## Vingt tests du diagnostic

Couverture : injection exacte des anciennes valeurs au niveau attendu ; statut toujours NO-GO ; absence des marqueurs sensibles dans les rapports ; différence de référence image textuelle expliquant synthétiquement un hash ; troisième variable signalée ; hash résiduel non expliqué ; audit périmé ; référence historique conforme/non conforme ; version incorrecte ; présence/absence d’une valeur héritée ; utilisateur explicite/hérité ; chemins JSON et listes ; dollars littéraux ; intégrité r1 ; refus des commandes mutantes ; changement en cours de collecte ; hypothèses bornées sans recherche de secrets ; syntaxe Python 3.11.

Les simulations réutilisent uniquement les fixtures synthétiques du bundle r1 vérifié. Elles ne modifient pas ses scripts. Le programme de diagnostic ne relance pas le probe, ne lit aucune base réelle et ne fait pas d’authentification HMAC contre le VPS.

## Dix-sept tests du moteur 2.35.1

1. Version exacte vérifiée.
2. Anciennes valeurs explicites rétablies : hash historique reproduit dans le cas où elles étaient explicitement déclarées.
3. `user` explicite : hash différent.
4. Référence image textuelle différente : hash différent.
5. `stop_grace_period` différent : hash différent.
6. Healthcheck déclarée : hash différent.
7. Présence d’une variable égale à une valeur héritée : hash différent.
8. Ordre des clés de mapping environnement : hash conservé.
9. Build, pull_policy et depends_on : exclusions confirmées dans le scénario testé.
10. Label utilisateur déclaré : hash différent.
11. Dollar d’override réinterpolé et échappement du rendu : comportement confirmé.
12. Rejeu d’un rendu explicite correctement échappé : hash conservé.
13. Modification du contenu d’`env_file` à chemin constant : hash conservé.
14. Gel r1 ajoutant une déclaration auparavant uniquement dans `env_file` : hash différent malgré l’ancienne valeur.
15. Chemin d’`env_file` différent à contenu égal : hash différent.
16. Vue `--no-interpolate --no-env-resolution` conservant l’origine `env_file` : rejeu fidèle du hash.
17. Valeur gagnante d’un override différente : hash différent.

Les premières expériences ont invalidé deux hypothèses du banc d’essai : doubler une seconde fois les dollars d’un rendu et croire que `--no-env-resolution` seul produisait une vue déclarative suffisante. Le diagnostic final utilise la vue d’entrée non interpolée et contrôle son rejeu avant d’exploiter une hypothèse. Ces constats ne sont pas présentés comme des causes prouvées sur le VPS.

## Reproduction locale

Sur le poste de qualification, avec le binaire officiel vérifié déjà présent :

```powershell
& .\deliveries\docnelo-lifecycle10-hash-diagnostic-r1\run_local_tests.ps1
```

Le script fixe l’image de laboratoire par ID, vérifie le hash du binaire et enregistre le résultat local. Pour rejouer après scellement sans modifier les preuves livrées, utiliser une copie de qualification ; réécrire `test-results.json` peut invalider le manifeste.

## Intégrité et limites

Le manifeste r1 reste `56c448a98858cc54e226c298bde042d159451c12b2380a5535ac3a7d45dc1431`. Le parent reste `9d077ca43a8995429e6a471f30e9cd12d7724292a56dd6a74332c4f0954497c5`. Les fichiers scellés sont vérifiés sans écrasement. La procédure opérateur conserve les preuves précédentes et produit un nouveau dossier privé uniquement à la demande de l’opératrice.

Ces résultats démontrent les mécanismes et les refus du diagnostic. Ils n’identifient pas encore le champ réel responsable de C ≠ D sur le VPS. **Verdict NO-GO pour poursuivre le déploiement fermé, malgré la réussite des tests locaux.** Aucune migration, ouverture, modification réelle de configuration ou intervention VPS effectuée.
