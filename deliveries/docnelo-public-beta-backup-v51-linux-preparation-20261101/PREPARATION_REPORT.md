# Docnelo Public Beta — Qualification Linux V5.1 : préparation bloquée

1 novembre 2026. **NO-GO production, Lifecycle 10 et sauvegarde réelle.**
**Aucun lot L1 à L17 exécuté dans un laboratoire Linux.**

## 1. Décision et périmètre réellement réalisé

L'environnement accessible est un poste Windows avec WSL2 et Docker Desktop.
Une distribution Debian est déjà en cours d'exécution ; cela ne constitue
pas une preuve d'environnement dédié, isolé et autorisé pour cette recette.
Aucun laboratoire cible, inventaire de ses ressources, frontière réseau ou
attestation d'absence de données/credentials de production n'est établi.

Conformément à la condition d'arrêt demandée, seul ce dossier de préparation
est produit. Aucune distribution arrêtée n'a été démarrée, aucune commande
n'a été exécutée dans Linux, aucun daemon Docker n'a été interrogé.
Aucune connexion SSH/VPS, installation, pull, build, sauvegarde, restauration,
création de fixture ou manipulation de conteneur n'a été effectuée.
Les scripts V5/V5.1, Compose, env-files et gardes restent inchangés.

Les contrôles locaux réalisés sont limités à la lecture des deux documents
de référence, des métadonnées V5.1 et de sa politique de clés, à l'inventaire
des clients/distributions/contextes et au recalcul des sceaux des releases.
Les commandes Docker utilisées sont uniquement `docker --version` et
`docker context ls` : inventaire client, sans connexion au daemon.
Le programme de hachage utilise uniquement la bibliothèque standard Python
Windows, sans importer les modules de sauvegarde/restauration.

## 2. Preuves disponibles et limites

| Réf. | Observation locale | Ce qu'elle ne prouve pas |
|---|---|---|
| E1 | `wsl --list --verbose` : Debian running WSL2, Ubuntu stopped WSL2, docker-desktop running WSL2 | Dédiation, isolation, autorisation ou versions des outils Linux |
| E2 | Client Docker Windows 29.8.2, build `7fc2dff` ; contexte courant `desktop-linux` sur named pipe local | Version moteur/Compose, contenu du daemon, absence de ressources ou liens de production |
| E3 | Python hôte Windows 3.13.7 | Runtime Python 3.11 Linux, fcntl ou comportement POSIX |
| E4 | V5 : 18/18 entrées SHA-256 conformes au manifeste local | Authenticité externe, installation ou exécution |
| E5 | V5.1 : 18/18 entrées SHA-256 conformes au manifeste local | Même limite ; aucun import Linux vérifié |
| E6 | `RELEASE.json` annonce 101 réussites, 6 ignorés, runtime Linux non exécuté | Aucun de ces résultats historiques n'est réexécuté ou crédité à L1–L17 |
| E7 | Politique V5.1 et audit lus dans les sources conservées | Pas de qualification opérationnelle des archives, lecteurs ou permissions |

Recalcul des sceaux terminé le `2026-11-01T10:57:32.477953+00:00`.
Les valeurs exactes et les empreintes des documents d'entrée figurent dans
`PREPARATION_EVIDENCE.json`. Les observations E1–E3 proviennent de l'appel
d'inventaire précédent ; aucun horodatage plus précis ne leur est attribué.
Les sorties retenues sont limitées aux informations non sensibles utiles :
pas de dump d'environnement, de configuration de credentials ou de clé.

SHA-256 de `SHA256SUMS` V5.1 :
`676d6d3f707c58f4dda150cef5cfd37196b7cf8e162434a7af042357574f6eda`.
La conformité au manifeste local n'est pas une signature d'origine.

## 3. Prérequis manquants : arrêt avant exécution

| ID | Prérequis à établir | Preuve requise avant tout lot mutateur |
|---|---|---|
| P1 | Cible Linux dédiée et explicitement autorisée | Identité de VM/machine, responsable, périmètre et ressources autorisées |
| P2 | Isolation physique et réseau | Inventaire des montages et sockets ; aucun volume/dossier/donnée/clé/credential de production ; aucun tunnel, route ou accès vers VPS |
| P3 | Daemon exclusivement de recette | Endpoint documenté, inventaire avant/après, absence de collisions et aucun daemon de production ; ne pas provoquer un test contre un mauvais daemon réel |
| P4 | Permissions et outillage Linux représentatifs | Python 3.11 effectif, fcntl, sqlite3, SQLAlchemy, Psycopg, tar, Docker moteur/Compose, Restic, pg_dump/pg_restore ; versions, chemins et SHA exacts |
| P5 | Image de capture synthétique contrôlée | Image ID/digest et provenance ; mêmes modules snapshot/lock que V5.1, comportement réel non remplacé par un stub ; UID/GID applicatifs documentés |
| P6 | Schéma PostgreSQL et fixtures | PostgreSQL 17 et extensions nécessaires, cinq magasins 1/1/2/2/2, documents synthétiques et états HMAC cohérents ; zéro donnée réelle |
| P7 | Frontière de restore | Cluster `documind-restore-lab`, admin DB `documind_restore_admin`, loopback/port explicite sans tunnel, root `.synthetic-only`, nouvelles cibles uniques, aucune API attachée |
| P8 | Orchestrateur et destination de recette | VM jetable pouvant reproduire les chemins/projet fixes ; dépôt Restic de recette et credentials uniquement synthétiques, destination indépendante autorisée |
| P9 | Mesures et pannes bornées | Instrumentation fichiers/verrous, limites externes approuvées, espace, durée maximale, arrêt des seuls PID/ressources identifiés ; conservation des partiels |
| P10 | Conservation et reprise | Dossier privé, manifestes et journaux expurgés, politique de rétention, repli des seules ressources de recette ; RPO/RTO et seuils approuvés |

Ne pas supposer Docker Desktop ou Debian WSL sûrs sur la seule base de leur
nom. Un examen d'isolation dans une cible désignée est une prochaine barrière,
pas une autorisation implicite d'utiliser l'environnement partagé courant.
Ne pas modifier globalement le contexte Docker pour « rendre » le poste isolé.

## 4. Résultats détaillés par lot : tous NON EXÉCUTÉS

Statut unique des scénarios Linux ci-dessous : **NON EXÉCUTÉ — P1/P2/P3
non établis**. Les sous-scénarios sont préparés, pas passés ni échoués.
L1 bénéficie seulement des contrôles locaux E4/E5 ; son résultat Linux
reste NON EXÉCUTÉ. Aucun délai, mutation ou RPO/RTO n'a été mesuré.

| Lot | Sous-scénarios à exécuter sans modifier les releases | Attendu et preuve discriminante |
|---|---|---|
| L1 | Sceaux avant/après ; imports depuis release seule ; Python 3.11/Linux ; UID/GID et versions de chaque outil | Entrées exactes, modules réellement importés et hashes ; aucune dépendance importée du workspace ; versions hôte/image distinguées |
| L2 | Deux clés : 0400, 0440, 0600, 0640 ; 0440/0640 avec UID/GID incorrects ou non entiers ; modes publics/exécutables/spéciaux ; vide, doublons, liens, membre absent ; SHA/métadonnées discordants | Propriétaire-seul sans ajout de restriction 0:1000 ; profils groupe exclusivement 0:1000 ; refus des cas invalides ; capture/verify/restore testés, pas seulement le helper |
| L3 | Deux clés distinctes de 32 octets ; taille incorrecte ; clés identiques ; namespace/header/signature incohérents | Distinguer acceptation d'archive et contrôle du lecteur ; aucune correction de signature ou clé pour forcer le PASS |
| L4 | Deux env-files CLI ordonnés et service env_file ; override Web seul puis API-path ; variables de session ; chemins relatifs ; dollars littéraux ; `!reset` | Comparer la chaîne synthétique complète et celle réellement construite par l'orchestrateur ; conserver différences, pas retirer un override pour réussir |
| L5 | Image ID attendu ; tag autre image ; image absente/politique de pull ; contexte différent exclusivement de recette ; endpoint réseau parasite de recette | Résolution et limites d'identité observées ; aucun daemon réel utilisé comme test négatif ; absence de garde documentée comme lacune |
| L6 | API/Web/init actif ; connexion SQL supplémentaire ; consommateur de volume ; one-off conservé même arrêté ; nominal DB seule | Refus existants et inventaires des consommateurs ; pas d'ignorance du refus ni de conteneur supprimé pour masquer le scénario |
| L7 | Capture `include_lifecycle_keys=True` ; cinq stores séparés ; deux clés root:groupe lisibles ; DB/documents/latch synthétiques | Capture réellement au format 5 ; fichiers, métadonnées, hashes, stores et deux clés ; pas de laboratoire V4 présenté comme V5.1 |
| L8 | Lock préexistant/absent/occupé ; parent sans droit d'écriture ; magasins WAL/SHM ; temporaires | Tracer créations/suppressions, UID/GID/modes/inodes et SQL avant/après ; surveiller aussi pendant la capture, pas seulement après nettoyage |
| L9 | `DOCUMIND_VERIFY_SQLITE=always` ; intégrité/table versions/SQL quota/documents ; altération de copie, manifestes, capture_id et membres | Refus réel et journal expurgé ; conserver original et variantes séparées ; SHA valide non assimilé à HMAC valide |
| L10 | Espace insuffisant ; interruption dump/tar ; verrou bloqué ; délai ; erreur/réponse Restic | Temps et point d'arrêt, ressources résiduelles et partiels ; pas de manifeste réparé ; enveloppe de délai distincte d'un timeout natif |
| L11 | Upload sur dépôt de recette ; snapshot ID complet/tags/paths ; récupération exacte ; altération contrôlée de copie du dépôt | Octets récupérés identiques et vérifiés ; `snapshots` seul insuffisant ; original du dépôt témoin conservé, aucun dépôt réel |
| L12 | Restore V5.1 fermé ; nouvelle DB/root marqués ; cinq stores/deux clés/documents ; latch | Inventaires SQL/files indépendants, ownership effectif, clés copies 0400, latch quarantiné ; absence d'API établie physiquement |
| L13 | Format <5 ; cible existante ; marqueur/URL/cluster non conforme de recette ; dump/extensions incompatibles | Distinguer refus natif et exigence supplémentaire V5 de recette ; constater acceptation V4 éventuelle, sans patch ; préserver partiels après CREATE |
| L14 | Quota source `closed=false` ; chemin CLI inchangé ; lecture SQL de la copie restaurée | Vérifier le constat documentaire de quota non fermé ; ne pas appeler le sealer pour faire réussir ce scénario ; aucune API attachée |
| L15 | Tombstone ; receipt sans lien ; pending ; document manquant ; fichier non référencé | Échec ou `blocked` suivant code réel ; copies et anomalies conservées, aucun reset/reconciliation |
| L16 | Paths famille 362 contre noms logiques restaurés ; restaurateur autre UID qu'app ; accès et preuves HMAC | Lecteurs sur copies privées seulement ; matrice des trois paths différents ; aucun chown ou renommage des originaux pour masquer l'incompatibilité |
| L17 | Durée quiescence/capture/upload/récupération/restore ; pannes puis reprise de ressources de recette | Mesures RPO/RTO avec seuils approuvés ; reprise explicitement autorisée et tracée ; aucune promesse de rollback de l'instance H0 |

Les fixtures nominales et négatives doivent avoir des identités séparées.
Une fixture négative altérée est voulue, documentée et conservée ; elle ne
devient jamais la nouvelle fixture nominale pour effacer une anomalie.
Les outils de mesure ne doivent pas changer le code testé ni remplacer
les sorties PostgreSQL, SQLite, HMAC ou Restic par des réponses simulées.

## 5. Matrice des incompatibilités : source confirmée, Linux non confirmé

Aucune incompatibilité n'est confirmée **par exécution Linux dans ce dossier**.
Les constats suivants proviennent de la lecture des sources et de l'audit
scellé par empreinte en E7 ; ils restent à discriminer opérationnellement.
Les références abrégées désignent les fichiers de la release V5.1
`deliveries\docnelo-public-beta-backup-v5.1-20261031`.

| ID audit | Constat documentaire | Lots nécessaires | État opérationnel / impact |
|---|---|---|---|
| B1 | Politique groupe 0440/0640 limitée à 0:1000, ownership-seul distinct (`tools\lifecycle_key_policy.py:5-30`) | L2/L3/L7/L16 | Non exécuté ; accès root:app et lecteurs non qualifiés |
| B2 | Orchestrateur un seul Compose, env réduit, pas de contrôle complet image/hash/overrides (`tools\public_beta_backup.py:139-164`) | L4/L5/L7 | Non exécuté ; fidélité chaîne effective non démontrée |
| B3 | `O_CREAT` lock et `.snapshot-*` dans parents sources (`backend\lifecycle_backup_lock.py:25-59`, `backend\lifecycle_snapshot.py:109-193`) | L8/L10 | Non exécuté ; effets et délais non mesurés |
| B4 | Restore witness/authenticated/admission_anchor différent des paths API de référence (`tools\validate_restore.py:91-179`) | L12/L16 | Non exécuté ; aucun rebranchement API autorisé |
| B5 | Sealer défini hors chemin `_restore` (`tools\validate_restore.py:27-50,249-365`) | L14 | Non exécuté ; latch quarantiné ne certifie pas SQL fermé |
| B6 | Validation SHA/schema pas authentification HMAC/fraîcheur (`tools\verify_snapshot.py:34-222`) | L3/L9/L15/L16 | Non exécuté ; preuve applicative manquante |
| B7 | Vérification distante de métadonnées seulement dans l'orchestrateur (`tools\public_beta_backup.py:59-96,139-198`) | L10/L11 | Non exécuté ; récupération des octets non prouvée |
| B8 | Restore données, pas instance/image/chaîne H0 (`tools\validate_restore.py:249-365`) | L12/L16/L17 | Aucun rollback exact H0 démontré |
| B9 | Daemon implicite, appels/lock sans délai global, pas de reprise API/Web automatique | L1/L5/L10/L17 | Non exécuté ; interruptions non qualifiées |
| B10 | Aucune capture/récupération/restauration réelle qualifiée dans cet exercice | L7/L11/L12/L17 | Blocage inchangé ; sceau local seul insuffisant |

Paths à comparer sans les normaliser silencieusement :

| Store | Famille API 362 de référence | Sortie actuelle du restore |
|---|---|---|
| Registry | `registry/registry.sqlite` | `registry/registry.sqlite` |
| Confirmation | `confirmation/confirmation.sqlite` | `witness/witness.sqlite` |
| Authenticated | `authenticated/authenticated-confirmation.sqlite` | `authenticated/authenticated.sqlite` |
| Holds | `holds/holds.sqlite` | `holds/holds.sqlite` |
| Admissions | `admissions/admission-anchor.sqlite` | `admission_anchor/admission_anchor.sqlite` |

Les paths source sont une référence documentaire locale, pas une nouvelle
attestation de la configuration VPS ou de la provenance historique H0.

## 6. Recommandations de correctifs futurs — non implémentés

Après exécution des lots et revue des échecs, envisager une **nouvelle release
distincte** ; ne jamais modifier les bundles V5/V5.1 existants :

- Rendre la chaîne Compose/env/contextes et l'identité image/daemon explicites
  et vérifiables ; préserver les contrôles actuels, refuser omissions/dérives.
- Définir un contrat de mapping des cinq stores et des lecteurs/permissions
  restaurés, validé avant reprise ; ne pas élargir implicitement la politique
  de clés ni réattribuer les originaux.
- Traiter explicitement le quota restauré fermé et vérifier son résultat SQL
  sur copie ; ne pas confondre latch quarantiné et fermeture réelle.
- Ajouter une récupération et vérification des octets du snapshot distant
  exact ; conserver les contrôles de dépôt existants et la preuve d'origine.
- Borner capture, attente de lock et transfert avec états d'échec/partiels
  traçables ; prévoir une décision séparée de reprise, jamais un démarrage
  automatique après échec.
- Formaliser les effets temporaires/lock et l'exclusivité de capture ;
  ajouter des contrôles HMAC/namespace/fraîcheur applicatifs indépendants,
  sans modifier les témoins pour satisfaire ces contrôles.

Ces recommandations ne sont ni des garanties acquises ni une procédure
permettant de contourner un garde. Une approbation ne transforme pas
un refus existant en PASS.

## 7. Prochaine barrière et verdict

Pour commencer une qualification ultérieure : établir P1–P10, consigner
l'autorisation de la cible et des mutations de recette, vérifier les sceaux
avant imports, puis exécuter les lots avec preuves privées et expurgées.
Conserver les non-exécutés, refus natifs et lacunes séparément des succès.

Pour envisager ensuite une sauvegarde réelle : résultats Linux obtenus,
blocages levés dans un mécanisme approuvé, fidélité à la chaîne effective,
quiescence/clé/HMAC/paths démontrés, récupération/restaurabilité éprouvées,
délais/reprise approuvés et autorisation de production **distincte**.
Le laboratoire synthétique seul ne certifiera pas une sauvegarde réelle
non récupérée, ni la provenance H0.

**Verdict : NO-GO pour toute intervention de production et pour Lifecycle 10.**
**Qualification Linux bloquée avant exécution ; aucun scénario déclaré PASS.**
Les seules mutations réalisées sont la création de ce nouveau dossier
documentaire de préparation et de son manifeste, sans écrasement d'existant.
