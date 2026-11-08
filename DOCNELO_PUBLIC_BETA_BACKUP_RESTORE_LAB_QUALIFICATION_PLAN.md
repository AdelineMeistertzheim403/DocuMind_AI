# Docnelo — Plan de qualification isolée backup/restore V5.1

1 novembre 2026. **Plan non exécuté ; NO-GO production.**
Complément de `DOCNELO_PUBLIC_BETA_BACKUP_RESTORE_COMPATIBILITY_AUDIT.md`.
Ne lancer ni le laboratoire combiné ni les CLI de backup/restore pendant
cette étude. Aucun correctif de script n'est inclus.

## 1. Périmètre et prérequis d'une future recette

Utiliser une machine Linux dédiée ou un environnement explicitement isolé,
sans socket/daemon VPS, tunnel SSH, volume, réseau, credential ou fichier
de production monté. Choisir IDs de projet, DB, volumes, réseaux et dossiers
uniques, contrôler les collisions et inventorier les ressources avant/après.
Seules les ressources nommées de ce laboratoire peuvent être interrompues.

Qualifier la release V5.1 scellée et ses imports depuis ce répertoire,
pas un mélange du workspace. Identifier Python 3.11 effectif, SQLAlchemy,
Psycopg, sqlite3, tar, Docker/Compose, Restic et pg_dump/pg_restore.
Vérifier le support `!reset` sur la version exacte envisagée.
Pas d'installation, pull ou build opportuniste sur VPS.

L'orchestrateur fixe le projet `documind-public-beta`, les noms des volumes,
le root parent, le latch et le fichier Restic. Un simple `-p lab` n'est
pas son interface. Pour le tester intégralement **sans patch**, prévoir
une VM jetable isolée reproduisant ces chemins avec données/credentials
synthétiques et un dépôt de recette séparé. Ne jamais employer le daemon
ou dépôt réels pour satisfaire ses chemins fixes.

Une nouvelle recette ou un harness peut être nécessaire dans un lot
autorisé ultérieur. Le script `combined_restore_lab.py` actuel est une
référence de mécanisme V4, pas une commande déjà qualifiée pour cet exercice
V5.1. Ne pas lui attribuer une garantie qu'il ne teste pas.

## 2. Jeux de données et états à reproduire

Préparer exclusivement des fixtures : PostgreSQL 17 avec schéma/extension
pertinents, documents PDF/TXT, cinq stores aux versions 1/1/2/2/2 et
répertoires distincts, deux clés HMAC synthétiques de 32 octets distinctes,
namespace de recette documenté, lock préexistant, latch validé.
L'API de recette doit utiliser l'identité applicative prévue, pas root
uniquement pour contourner des permissions.

Étudier séparément les chemins effectifs de la famille 362, les chemins
plats refusés, les overrides Web R2 synthétiques et un override API
modifiant un chemin. Env-files synthétiques CLI/service distincts et
ordonnés ; include/chemins relatifs et dollars littéraux si présents.
Le rapprochement de ces fixtures ne sera jamais nommé provenance H0.

Aucun seeding, init, migration ou création de clé ne doit toucher des
ressources existantes. Ces mutations préparatoires sont limitées aux
nouvelles ressources du laboratoire autorisé.

## 3. Séquence et matrice de tests requise

| Lot | Scénario | Attendu / preuve |
|---|---|---|
| L1 — Identité | Sceaux, imports, runtime Linux réel, UID/GID et bibliothèques | Versions, paths et empreintes exacts ; aucun import hors release |
| L2 — Clés | `0400/0440/0600/0640`, mauvais UID/GID, bits spéciaux, vide, doublons, liens, SHA altéré | Politique V5.1 exacte ; comparer au refus V5 connu sans toucher de vraie clé |
| L3 — Usage HMAC | Copies 32 octets distinctes, tailles non conformes, clés identiques, namespace/header divergent | Distinguer acceptation d'archive et refus du lecteur applicatif ; aucune signature corrigée pour passer |
| L4 — Compose | Deux env-files ordonnés, overrides Web/API, variables de session, chemins relatifs et `!reset` | Rapports des différences entre chaîne de référence et orchestrateur ; refus de qualification si couverture effective non prouvée |
| L5 — Identité Docker | Image exacte disponible, autre tag/ID, mauvais daemon, réseau privé parasite | Aucun mélange de daemon ou image ; documenter les limites du code et exiger le précontrôle manquant, pas un PASS artificiel |
| L6 — Quiescence | API/Web ou init actif, client SQL supplémentaire, consommateur/one-off sur volume sensible | Refus existants vérifiés ; identité DB conservée pendant la capture |
| L7 — Capture V5 | `include_lifecycle_keys=True`, stores sous répertoires distincts, clé root:groupe lisible | Format entier 5, cinq stores, deux clés, latch et dump, manifeste complet |
| L8 — Mutations physiques | Lock présent/absent, permissions sans espace d'écriture, WAL/SHM et temporaires | Inventaires des fichiers/inodes/modes avant/après ; tracer création possible du lock et nettoyage temporaire, SQL source conservé |
| L9 — Vérification | Copies SQLite et `DOCUMIND_VERIFY_SQLITE=always`, tables/digests SQL, quota, documents, archives altérées | Validation indépendante, refus de membres/empreintes/schema/capture_id incohérents ; pas d'assimilation à HMAC/fraîcheur |
| L10 — Échecs | Espace insuffisant, tar/dump interrompu, verrou occupé, délai dépassé, échec upload/réponse Restic | Captures partielles conservées, pas de reprise automatique ni manifeste « réparé » ; état et délai observés |
| L11 — Distant recette | ID complet, tags/paths, récupération de l'ID exact et altération distante simulée | Comparaison des octets récupérés et vérification ; simple `snapshots` insuffisant |
| L12 — Restore V5.1 | Nouvelle DB/root marqués, quota source fermé, cinq stores/deux clés et documents | Comparaison SQL/files ; latch copie quarantined ; clés restaurateur 0400 ; rapport et inventaire réels |
| L13 — Refus de restore | Format <5 pour ce lot, cible existante, URL/cluster non isolé, dump/extension incompatible | Arrêt avant mutation lorsque possible ; conserver DB/arbre partiels si échec post-création, nouvelle cible pour rejouer |
| L14 — Quota ouvert | Fixture source `closed=false`, appel du chemin CLI inchangé | Constater que `_restore` ne ferme pas le quota ; aucune API attachée/exposée, aucun faux certificat de fermeture |
| L15 — Anti-résurrection | Tombstone, receipt non lié, pending, fichier manquant ou non référencé | `blocked` ou échec, rapport et copies conservés ; ni reset ni reconciliation automatique |
| L16 — Lecteurs après restore | Noms logiques vs chemins API, UID du restaurateur vs app, preuves HMAC cohérentes | Tester sur copies privées une configuration de lecture explicitement revue ; pas de promotion API ni chown des originaux |
| L17 — Délais et repli | Quiescence, capture, récupération, restore et reprise des ressources synthétiques | RPO/RTO et durée d'arrêt mesurés ; modèle prospectif de repli qualifié séparément de H0 |

Les tests négatifs doivent produire un **refus ou une lacune explicitement
constatée**, selon ce que le code fait réellement. Ne pas transformer
une absence de garde en résultat « passed ». Les helpers de test nouveaux
ne doivent pas remplacer la logique des scripts audités.

La reprise fonctionnelle d'une copie restaurée nécessite un autre lot :
chemins et identités revus, mêmes données, image compatible, gardes et
tests applicatifs. La recette backup/restore seule reste sans API exposée.

## 4. Dossier de preuves

Conserver, dans un nouveau dossier sans écrasement :

- Inventaire d'isolation, images/versions/runtime, release et manifeste.
- Recette synthétique, ordre Compose/env-files et contexte non sensible.
- Chronologie UTC, argv non secret, codes retour, IDs de conteneurs et
  état avant/après ; liste précise des ressources créées/interrompues.
- Capture V5 exacte, clé/DB/documents de recette privés, manifests,
  snapshot ID distant de recette et preuves de récupération.
- Logs expurgés, rapports SQL/SQLite/HMAC indépendants, mutation physique,
  durées et résultats nominaux/négatifs.
- Restore et captures partielles conservés ; rapport des lacunes,
  limites de repli et gardes applicables non franchis.

Les preuves de recette ne certifient pas les valeurs/chemins/keys du VPS.
Une future récupération de sauvegarde réelle dans un laboratoire privé
nécessiterait une autorisation distincte de transfert de données et de
traitement des clés, chiffrement, accès et rétention. Elle doit conserver
les originaux et ne monter aucun volume actif.

## 5. Critères d'une future décision de sauvegarde réelle

| Barrière | Critère obligatoire | État actuel |
|---|---|---|
| Autorisation | Fenêtre backup explicitement autorisée, interruptions/écritures temporaires admises, aucun garde applicable contourné | Non établie par cet audit |
| Linux/outils | Lots L1/L2/L5/L8/L10 qualifiés sur environnement représentatif, release exacte identifiée | Documentation/simulations antérieures seulement |
| Chaîne H0 | Image, fichiers, overrides, contextes et chemins effectifs inventoriés ; mécanisme de capture compatible sans omission | Couverture complète non démontrée |
| Lifecycle | Cinq stores, deux clés valides et accessibles, lock, namespace/HMAC, quota fermé et état cohérent attestés fraîchement | Aucun probe VPS dans cet audit |
| Sauvegarde/repli | Backup antérieur dans RPO récupéré/restauré ; récupération V5.1 et reprise synthétique éprouvées | Aucune preuve d'ID réel restauré fournie |
| Quiescence | DB seule, clients et consommateurs exclus, fenêtre privilégiée exclusive | À établir avant et après la future capture |
| Confidentialité | Dossiers et espace privés, secrets non journalisés, destination indépendante et repo ID existant vérifiés | À établir sans modifier les `.env` |
| Délais | RPO/RTO, limites d'arrêt/lock/upload et traitement sûr d'interruption chiffrés/approuvés | Non chiffrés |
| Traçabilité | Entrées/approbation authentifiées, capture liée à la fenêtre, manifeste et copie privée hors VPS | À préparer |

Un éventuel GO serait **limité à la sauvegarde réelle autorisée**.
Le succès ne redémarre pas API/Web, ne remplace pas H0 et ne lance pas
Lifecycle 10. Après capture : exiger validation, `remote_verified` puis
récupération/contrôle de l'ID exact ; la reprise des conteneurs existants
est une décision distincte et reste interdite pendant cette étude.

**NO-GO actuel pour toute intervention sur la production.**
Les scripts, releases et gardes restent inchangés. Aucun laboratoire,
backup, restore, conteneur ou service lancé/redémarré pendant cet audit.
