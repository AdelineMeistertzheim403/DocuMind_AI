# Docnelo Public Beta — Qualification lifecycle dix

31 octobre 2026. Source finale : 8b11d4daf47bd7c3c6766b9f5231ea8a84fdbf71. **288 tests réussis, 0 échec final, 0 erreur finale, 0 ignoré**, plus un round-trip physique PostgreSQL/lifecycle en trois processus.

## Résultats finaux

| Groupe | Résultat |
| --- | --- |
| Suite consolidée PostgreSQL 17/API/lifecycle | 227 passed, 0 failed/error/skipped ; 250,83 s |
| BFF réel Web R2 local | 50 passed, 0 failed/skipped ; environ 0,80 s |
| Précontrôle opérateur simulé | 11 tests réussis ; erreurs de quota, image, IA, environnement, configuration ou hash Compose refusées |
| Round-trip PostgreSQL 17 | Vrais pg_dump/pg_restore, dump initial à zéro et dump à dix ; cinq magasins restaurés ; succès |
| Redémarrage | Trois processus Python/API distincts, compteur dix persistant, connexion d’un compte vérifié après fermeture |
| Image candidate réelle | Imports hors réseau, compilation en mémoire, mode disabled/limite cinq/garde opérationnelle false, IA/demo/legacy désactivés dans le conteneur de recette |
| Intégrité de l’image | 104 entrées applicatives conformes, 66 backend finaux, 15 couches héritées + 9 couches de sources, configuration d’image identique |
| Dépendances | 46 métadonnées runtime identiques entre référence/candidate et présentes à l’identique dans l’image de test ; aucun pip install runtime |
| Compatibilité outillage | Grammaire Python 3.11 analysée, y compris les fichiers UTF-8 avec BOM du bundle V5.1 |
| Modèle réel des clés dans la candidate | Douze profils vérifiés sous UID/GID 1000, plus cinq magasins avec deux clés root:app 0440 co-localisées et namespace Public Beta authentifié ; mauvais namespace refusé |

Les reprises ciblées et les suites intermédiaires ne sont pas additionnées aux 287. Le scénario physique et les assertions d’image sont rapportés séparément, sans gonfler le nombre de tests unitaires.

## Environnement et garde-fous

Docker Desktop local, linux/amd64, PostgreSQL 17/vector dans une base neuve en tmpfs, réseaux internes créés par invocation, aucun port publié ni volume réel. Les sources sont montées en lecture seule ; les écritures de test restent dans les tmpfs. Les conteneurs/réseaux de laboratoire sont retirés par leurs IDs capturés, sans volume delete ou prune.

L’image de test 0b82274b92ba84a7d3049dce0f454d091e71b43ed83a317b451ff4b676b22904 utilise Python 3.13.17 et ajoute cryptography 50.0.2 à la fermeture de tests existante, avec roue et SHA-256 verrouillés. La candidate API n’ajoute aucune de ces dépendances. Les 46 métadonnées du runtime actif correspondent exactement à celles du laboratoire ; six distributions supplémentaires sont réservées aux tests. Aucun vrai client OpenAI n’est permis dans pytest, aucun appel IA réel n’est effectué et les nouveaux scénarios durables gardent le flag synthétique false.

Les tests historiques SaaS de fournisseurs mock continuent à tourner dans leurs seules applications fictives. Ils ne changent pas les flags du VPS. Aucun compte, email, document ou secret réel n’est utilisé.

## Matrice de sécurité exécutée

- Admissions 1, 5, 6, 9 et 10 par HTTP, avec témoins/ancre cohérents et vérification email à usage unique aux bornes ; onzième refusée sans nouveau compte/mail, disponibilité full et closed restant false jusqu’à fermeture explicite.
- Course de deux APIs indépendantes pour la dixième place : deux PID PostgreSQL distincts synchronisés sur l’UPDATE, une seule attribution durable, réponse générique pour le perdant.
- Annulation SQL avant commit et exception après commit réel simulant un résultat incertain : pending conservé, compteur respectivement zéro/un, nouvelles admissions et réouverture refusées.
- Migration réelle de fichiers legacy 1/2 vers 3/3 : inodes, anciennes lignes, clés et ancien payload/tag pending ou settled conservés ; deuxième invocation vérifiée idempotente.
- Dry-run et mauvaise confirmation sans changement des octets des magasins ; erreur SQLite injectée avant commit, rollback des deux fichiers ; WAL refusé sans changement de journal.
- Politique HMAC altérée refusée ; témoin ancien refusant un compteur supérieur à cinq ; gardes empêchant un protocole opérationnel sans durabilité ou avec IA/synthétique activés.
- Réouverture à dix : dry-run cohérent, refus sans confirmation, refus en pending ou à capacité pleine, fermeture sans perte d’admissions.
- Captures SQLite par backup API, restauration des copies, vérification HMAC et comparaison avec compteur dix ; compteur ancien cinq signalé à réconcilier.
- V5 avec métadonnées étendues accepté par l’outillage 5.2 candidat et refusé par V5.1. Ce test de structure emploie un manifeste synthétique et des payloads SQL/documentaires factices ; il n’atteste pas une quiescence réelle.
- Le test physique séparé utilise de vrais dumps PostgreSQL avant/après dix admissions, restaure les deux dumps dans des bases neuves et les cinq SQLite dans des chemins séparés. La comparaison du vieux dump à zéro au témoin indépendant à dix impose une réconciliation et ne donne aucune autorisation d’ouverture.
- Parcours existants : expirations/rejeu, renvoi, SMTP TLS fictif, reset, isolation documentaire, quotas, sessions, CSRF/Origin/cookies et routes BFF.

Les dix erreurs de teardown précédentes sont corrigées dans le code du lifespan, sans modifier ou exclure les tests historiques. Le worker n’est arrêté que s’il avait réellement démarré ; pas d’activation de l’IA pour faire passer la suite.

La dernière recette physique emploie le modèle publié complet : parent lifecycle app-owned, deux clés root:app 0440 dans le même répertoire, namespace documind-public-beta et processus UID/GID 1000 après abandon des privilèges de provisionnement. Le lecteur ancien refuse ce modèle en contrôle négatif ; la candidate le vérifie sans changer les clés ou l’en-tête. Les profils 0444, 0644, 0660, 0777, symlink, hardlink, mauvais groupe et ancêtre group-writable sont refusés. 0400/0600 appartenant à root restent illisibles par app ; les profils privés appartenant au processus restent couverts par les tests historiques. Ces contrôles supplémentaires ne sont pas additionnés aux tests pytest/BFF/opérateur.

## Traces des corrections pendant la qualification

Les tentatives intermédiaires sont conservées : collecte initiale impossible sans cryptography dans l’ancienne image de tests ; fixture de manifeste V5 incomplète ; fixture de migration héritant du plafond de test quatre au lieu de cinq ; harnais de round-trip remplaçant aussi le nom d’utilisateur dans l’URL de la base ; probe de livraison ajoutant des champs au contrat historique. Ces points ont été corrigés explicitement. Le probe conserve son ancien résultat hors capacité dix, et les tests historiques restent inchangés.

La sortie normale unittest sur stderr a aussi nécessité une capture subprocess correcte sous PowerShell ; les onze tests opérateur finaux retournent bien le code zéro. Aucun échec final n’est masqué par un skip ou une exclusion. Les avertissements restants (17 dans la suite principale) concernent Starlette/httpx, Pydantic et le marqueur posix historique non déclaré dans le pyproject exact de l’image ; ils sont consignés.

## Reproduction locale et preuves

```powershell
.venv/Scripts/python.exe -B deliveries/docnelo-lifecycle-10-api/run_lab.py
.venv/Scripts/python.exe -B deliveries/docnelo-lifecycle-10-api/run_lab.py --focused
.venv/Scripts/python.exe -B deliveries/docnelo-lifecycle-10-api/run_operator_guards.py
.venv/Scripts/python.exe -B deliveries/docnelo-lifecycle-10-api/run_roundtrip.py
```

Ces scripts ciblent uniquement le contexte Docker Desktop et des ressources jetables nouvelles. Ne pas transposer le cleanup de tests/conftest.py sur une base réelle : son reset final est réservé aux fixtures neuves. La suite consolidée exécute douze modules pytest ; focused sert à la revue des cas de capacité/autorisation et ne remplace pas le décompte consolidé.

Preuves locales : pytest.log, focused-pytest.log, bff-tests.log, operator-tests.log, roundtrip-result.json et dossier roundtrip référencé, image-proof.json, test-runtime-parity.json. Les dumps et clés synthétiques de laboratoire ne sont pas inclus dans la livraison opérateur. Les archives Docker sont privées et exclues de Git.

## Limites et verdict

La recette n’a pas inspecté le VPS, son SMTP réel, sa fraîcheur indépendante, ses ressources ou ses overrides courants. Un rollback simultané de toutes les preuves locales ne peut pas être détecté par une simple égalité de compteurs : la revue externe reste requise. La capacité juridique et le contenu des pages brouillon ne sont pas approuvés par les tests.

**GO technique local pour la candidate fermée et le plan de migration. Aucun GO d’ouverture publique ni de déploiement automatique.**
