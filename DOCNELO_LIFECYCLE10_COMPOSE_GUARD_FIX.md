# Lifecycle 10 — Correctif du garde Compose

## Livraison distincte

Release : `docnelo-lifecycle10-compose-guard-r1`.

Répertoire : `deliveries/docnelo-lifecycle10-compose-guard-r1/`. Le garde corrigé porte son nom attendu `check_closed_compose.py` dans cette nouvelle release seulement. Le garde parent, son manifeste, ses archives, ses worktrees et ses autres fichiers ne sont pas modifiés. Aucune image API/Web/DB n’est reconstruite ou retaguée.

Le nouveau garde utilise uniquement la bibliothèque standard Python. Il épingle le SHA-256 du manifeste parent, puis vérifie les six fichiers parent qu’il consomme avant de charger le garde original et le probe. Les neuf empreintes source de la candidate proviennent du `source-release.json` scellé.

L’écriture de caches bytecode est désactivée dans le garde : son import du module parent ne crée pas de `__pycache__` auprès des artefacts scellés.

## Fonctionnement

| Action | Effet | Limite |
|---|---|---|
| `audit` | Inspecte Docker, rend C/H/D, appelle le garde historique, collecte les contrôles indépendants, écrit rapport et modèle d’approbation privé | Ne crée aucun conteneur ; n’approuve rien |
| `prepare` | Réévalue le relevé ; exige l’approbation si différence ; crée le nouvel override privé H | N’édite jamais un fichier existant ; ne déploie rien |
| `check` | Réévalue tous les contrôles ; relance le probe candidat en conteneur temporaire ; vérifie l’approbation et le contenu exact du freeze persistant | Aucun serveur applicatif, worker, migration ou bascule |

`audit` retourne 2 pour NO-GO **et** REVIEW_REQUIRED. Un script appelant ne peut donc interpréter une attente d’approbation comme un succès. `prepare` ne signifie que fichier privé préparé. Seul `check` peut produire `status=passed`, toujours avec `opening_authorized=false`.

Un probe inaccessible ou non authentifié est bloquant et reste visible dans le rapport. Une entrée illisible ou structurellement inexploitable arrête le contrôle avec un motif générique sûr ; les contrôles dépendants ne sont jamais présentés comme réussis. Le rapport exhaustif est produit lorsque le relevé de base est exploitable.

## Approbation humaine

Le modèle est généré depuis le relevé réel, avec `approved=false`, opérateur et justification vides. Il comprend exactement :

```json
{
  "binding": "empreinte générée par audit, jamais inventée",
  "variables": ["PUBLIC_CONTACT_EMAIL", "PUBLIC_OPERATOR_NAME"],
  "decision": "preserve_active",
  "approved": false,
  "operator": "",
  "reason": ""
}
```

La liste contient seulement les champs effectivement différents. L’opératrice doit examiner l’ancien et le nouveau contenu dans le dossier privé, justifier la conservation de l’identité exécutée et remplir personnellement l’approbation. Ce fichier d’exemple n’est pas une approbation exploitable.

L’empreinte d’approbation couvre : identités/images/configuration effective des conteneurs, état de santé et début d’exécution, modèles C/H/D, version Compose, ordre et contenu des fichiers Compose, contenu des deux fichiers d’environnement, override candidat et preuve lifecycle. Les journaux et dates volatiles des sondes de santé ainsi que les exécutions de diagnostic terminées sont exclus ; l’état healthy et StartedAt restent contrôlés. Les fichiers et conteneurs sont relus en fin d’audit pour refuser une modification en cours de collecte.

Le contrôle final exige de nouveau cette empreinte. Un changement de fichier, conteneur, image, preuve ou modèle invalide l’approbation. Cela ne remplace pas une fenêtre opérateur exclusive : le garde n’est pas un verrou distribué empêchant un administrateur de modifier Docker après son retour.

## Confidentialité et permissions

Le dossier d’état est nouveau, canonique, sous `/opt/documind-public-beta`, détenu par l’utilisateur courant et en 0700. Les nouveaux fichiers sont créés exclusivement, sans écrasement, en 0600. Liens symboliques, fichiers d’approbation multi-liens, mauvais propriétaire et permissions de groupe/autres sont refusés. Le freeze persistant doit appartenir directement au dossier d’état.

Le rapport contient noms, motifs bornés et empreintes, jamais valeurs d’environnement, `.env`, clé ou inspect complet. Le fichier optionnel `--private-review` contient uniquement les deux valeurs publiques à comparer ; il reste privé, hors bundle et hors Git. Ne pas le publier. Le freeze contient seulement le sous-ensemble approuvé des deux valeurs **exécutées**. Toute autre clé, service ou structure y est refusé.

Le dossier d’état et son freeze deviennent des entrées de déploiement conservées s’ils sont ultérieurement utilisés par Compose. Ils ne doivent pas être supprimés après bascule.

## Protections conservées

* Comparaison des empreintes API/Web d’origine, par réexécution du garde scellé sur H ; DB est aussi contrôlée.
* Comparaison stricte de C→H (deux champs seulement) et H→D (image/pull_policy/namespace seulement).
* Refus des images, overrides, montages, réseaux, paramètres runtime et variables inexpliquées.
* État fermé initial 0007, quota zéro/fermé, limite cinq, disabled, IA/demo/legacy/synthétique et garde opérationnelle false, durabilité active, namespace Beta, latch ready.
* Probe scellé : transaction SQL READ ONLY, lecteurs HMAC existants, aucune initialisation de clé ou magasin ; challenge éphémère et comparaison des sources et du relevé.
* `operator_runtime.py` parent reste inchangé : aucune exclusion des deux variables publiques de ses fingerprints. Le freeze préserve donc leur valeur avant/après.

Le contrôle préalable projette explicitement les champs Docker pris en charge ; il ne prétend pas être un équivalent universel de tous les champs internes Docker. Les empreintes Compose complètes et les fingerprints runtime parent restent obligatoires. Toute variante non qualifiée demande une revue, sans adaptation opportuniste des attentes.

## Inventaire livré

| Fichier | Rôle |
|---|---|
| `check_closed_compose.py` | Garde corrigé, isolé du parent |
| `RELEASE.json` | Identifiant, parent épinglé, périmètre, résultats, aucune autorisation |
| `test_compose_guard.py` | Cas synthétiques Linux |
| `run_tests.py` | Exécuteur et preuve JSON ; vérification des 37 entrées du manifeste parent |
| `run_local_tests.ps1` | Lancement local, réseau désactivé, montages en lecture seule |
| `qualify_compose_hash.ps1` | Six vérifications avec le vrai Compose local, sans conteneur |
| `unit-test-result.json` | Résultats et journal des tests synthétiques |
| `compose-hash-test-result.json` | Résultats des empreintes Compose synthétiques |
| `DOCNELO_LIFECYCLE10_COMPOSE_DRIFT_ANALYSIS.md` | Analyse et limites de preuve |
| `DOCNELO_LIFECYCLE10_COMPOSE_GUARD_FIX.md` | Ce document et inventaire |
| `DOCNELO_LIFECYCLE10_COMPOSE_GUARD_TEST_REPORT.md` | Rapport de qualification |
| `DOCNELO_LIFECYCLE10_UPDATED_DEPLOYMENT_RUNBOOK.md` | Installation distincte, diagnostic, approbation, limites |
| `SHA256SUMS` | Empreintes des 12 fichiers précédents ; ne se référence pas lui-même |

Exclus : images Docker, archives de sauvegarde, `.env`, données, clés, relevés/approbations réels, modifications applicatives et frontend. L’unique ajustement Git local est l’exclusion privée du nouveau dossier de livraison, en complément des exclusions existantes ; aucun `.gitignore` partagé n’est modifié.

**GO local pour préparer ce correctif. NO-GO VPS jusqu’aux validations du runbook ; aucune ouverture autorisée.**
