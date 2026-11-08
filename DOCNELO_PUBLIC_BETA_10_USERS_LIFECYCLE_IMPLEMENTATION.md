# Docnelo Public Beta — Lifecycle durable à dix admissions

31 octobre 2026. Commit 8b11d4daf47bd7c3c6766b9f5231ea8a84fdbf71, référence a323afc5c9d63a8a9f59ac10c365710b58d1c868. **Préparation locale uniquement.**

## Migration additive et capacité signée

La table admissions existante reste intacte, avec sa contrainte séquences 1..5. La migration ajoute dans le témoin une table admissions_extension, bornée à 6..10. La lecture et les réservations vérifient ensemble continuité des séquences et unicité des identités entre les deux tables. Aucun compteur SQL, historique, fichier SQLite ou témoin n’est supprimé, renommé ou réinitialisé.

L’ancre reçoit une table admission_capacity contenant une politique HMAC séparée : domaine documind-admission-capacity-v1, version 3, capacité 10, nombre et empreinte du préfixe historique. Elle utilise la clé d’admission existante ; les clés et leurs permissions ne sont pas modifiées. Le payload/tag de l’ancre pending/settled existante est conservé à l’octet près pendant la migration, avec son domaine/version 2. Les nouvelles réservations continuent à authentifier l’ensemble du témoin.

Les versions SQLite passent de witness=1 / admission_anchor=2 à **3 / 3**. Les trois autres magasins restent inchangés. Une capacité dix exige les deux versions 3, la politique signée et le préfixe historique cohérent ; pas de simple tolérance d’un entier supérieur à cinq.

La migration prend le verrou PostgreSQL du quota fermé puis la barrière lifecycle exclusive. Elle ouvre les deux fichiers existants en mode rw sans création, contrôle leur identité/intégrité et leurs schémas, puis effectue les ajouts dans une transaction SQLite avec base attachée. Le mode de journal DELETE et synchronous=FULL sont exigés ; WAL ou un schéma partiel/inconnu entraînent un refus, sans conversion implicite. Une panne injectée avant commit annule les ajouts dans les deux magasins. Les inodes sont conservés.

## Commandes préparées

```text
python -B -m backend.lifecycle_capacity
python -B -m backend.lifecycle_capacity --execute --confirm MIGRATE-PUBLIC-BETA-CAPACITY-10
python -B -m backend.account_admin public-registration status
python -B -m backend.account_admin public-registration close --execute
python -B -m backend.account_admin public-registration reopen
python -B -m backend.account_admin public-registration reopen --execute --confirm REOPEN-PUBLIC-BETA-10
```

Les deux premières correspondent au dry-run et à la migration explicite, uniquement avec mode disabled, quota fermé et limite 5 ou 10. Une migration déjà complète est vérifiée et non réappliquée. Les commandes de réouverture sont disponibles pour une future phase approuvée ; **elles refusent l’environnement actuellement disabled**. Aucun de ces changements n’a été exécuté sur VPS.

## Garde opérationnelle distincte du laboratoire

Un nouveau paramètre interne, LIFECYCLE_PUBLIC_ADMISSIONS_ENABLED, vaut **false par défaut**. Il ne change aucun contrat BFF et n’est pas ajouté à la configuration active. Sa future activation exige le profil standard, une limite exactement dix, le mode durable, synthétique/IA/demo/legacy désactivés et un mode disabled ou public. Le mode public conserve ses préconditions SMTP/juridiques existantes.

Le circuit historique de mutations synthétiques reste réservé aux laboratoires ; il n’est pas activé pour les nouveaux scénarios d’admission opérationnelle, ni pour l’environnement réel. Le nouveau paramètre ne débloque pas les suppressions expérimentales, Beta Lite ou l’IA. Les tests SaaS historiques qui utilisent des fournisseurs mock restent isolés et n’appellent aucun fournisseur réel.

La réouverture à dix contrôle le latch ready, le quota et son plafond, les reçus de reprise ainsi que la concordance observée entre SQL, témoin et ancre. Le dry-run vérifie ces conditions ; l’exécution requiert aussi la confirmation explicite et prend le verrou de ligne. Elle ne remet jamais issued_count à zéro. Ces contrôles de cohérence **ne prouvent pas une fraîcheur externe** si toutes les copies ont été reculées ensemble : la revue indépendante de reprise reste une précondition opérateur.

## Admissions et pannes

L’UPDATE conditionnel PostgreSQL reste l’autorité de sérialisation : closed=false, compteur non négatif et inférieur à la limite, puis incrément dans la transaction du compte. Les réservations durables sont liées au numéro et à l’identité. À dix, la disponibilité devient full et la onzième demande ne crée aucun compte ; **closed ne passe pas automatiquement à true**.

Si le commit SQL est annulé ou incertain après une réserve durable, les témoins sont conservés en pending. Les tentatives suivantes et la réouverture sont refusées jusqu’à réconciliation indépendante. Aucun code de « réparation » ne supprime le témoin ou ne recycle la place. Les diagnostics distinguent SQL confirmé, réserve incertaine et minimum historique ; les résolutions d’incident nécessitent une décision opérateur, pas un retry automatique ou un settle improvisé.

La fermeture reste disponible sans modifier les admissions attribuées. Les comptes vérifiés peuvent se connecter après fermeture et après redémarrage. La vérification email ne crée pas une seconde admission.

## Sauvegarde et reprise

L’API capture les nouveaux schémas explicitement. Un **outillage séparé 5.2-capacity-10-candidate**, dérivé du bundle V5.1 vérifié, est préparé ; format de sauvegarde toujours V5. Seuls backend/lifecycle_snapshot.py et tools/verify_snapshot.py modifient la sélection des schémas dans les neuf modules hérités. Les magasins étendus doivent apparaître ensemble ; les autres tables et versions restent strictes. La politique de livraison Public Beta est ajoutée séparément depuis le commit qualifié.

La politique de clés V5.1, les contrôles de fichiers/liens/chemins/tailles/empreintes, l’orchestration Restic et les scripts de restauration restent inchangés. Le validateur ancien V5.1 refuse les nouvelles tables : installer l’outillage compatible dans une release distincte avant toute capture postmigration. Aucun forget/prune ou nettoyage local n’est prévu.

Le laboratoire réalise un vrai pg_dump/pg_restore à dix, restaure les cinq SQLite et vérifie leurs HMAC avec les seules clés synthétiques. Un ancien dump à zéro, confronté au témoin indépendant à dix, impose une réconciliation. Une capture complète n’autorise jamais automatiquement S2 ou une ouverture.

## Correction des dix teardowns

Le worker IA n’est arrêté que s’il a effectivement été démarré par le lifespan. Une modification tardive du flag dans une fixture ne provoque plus join() sur un thread non démarré. Les tests historiques ne sont ni exclus ni modifiés pour masquer l’erreur. Le fichier main.py est aussi normalisé en LF dans ce worktree ; aucune autre logique de démarrage IA n’est changée.

## Lecteur de clés et modèle réel de provisionnement

Le modèle documenté conserve le parent lifecycle privé appartenant à app, keys root:app 0750 et les clés root:app 0440. Le lecteur hérité réutilisait une règle d’ascendance exclusivement root prévue pour une autre autorité : il refusait ce modèle, reproduit dans l’image active avec un enfant UID/GID 1000 et des fichiers entièrement synthétiques.

Le lecteur spécifique lifecycle accepte désormais une ascendance root ou appartenant au processus applicatif de confiance, sans lien ni écriture de groupe/autres (exception sticky root pour les répertoires temporaires). Il exige le répertoire de clés root:groupe 1000, l’appartenance du processus au groupe approuvé, des clés root:groupe 1000 en 0440 ou 0640, régulières, à lien unique et de 32 octets. Ouverture O_NOFOLLOW et contrôle d’identité/métadonnées avant/après lecture sont maintenus. 0444, 0644, 0660, 0777, mauvais groupe, liens et ancêtre group-writable sont refusés. Les clés appartenant au processus restent limitées aux profils privés historiques ; 0400/0600 root ne sont pas lisibles par app et ne deviennent pas artificiellement accessibles.

Aucune clé réelle n’est lue ou modifiée ici, aucun chmod/chown de production n’est proposé. La fonction globale de l’autorité Lite n’est pas élargie. L’UID applicatif et l’opérateur restent dans le périmètre de confiance : cette politique ne prétend pas rendre une clé déjà lisible par l’application inviolable face à sa compromission, ni prouver une fraîcheur indépendante.

Les deux fichiers peuvent partager le répertoire de clés approuvé ; les cinq magasins restent dans des répertoires indépendants, et les chemins de clés doivent rester distincts. Le lecteur de reçus possède maintenant un namespace explicite, avec défaut historique documind-local-v2 préservé. L’override fermé Public Beta propose documind-public-beta, conformément au provisionnement publié ; le probe doit authentifier l’en-tête existant avec cette valeur avant toute migration. Aucun en-tête ni tag n’est réécrit pour résoudre un écart. Le laboratoire physique couvre ce modèle complet : deux clés root:app 0440 co-localisées, parent app-owned, API UID/GID 1000 et en-tête Public Beta signé, puis dix admissions et restauration.

## Inventaire source exact

| Rôle | Fichiers |
| --- | --- |
| Migration et garde | backend/lifecycle_capacity.py, backend/config.py |
| Témoin et ancre | backend/lifecycle_durability.py, backend/lifecycle_admissions.py |
| Admission/options | backend/public_registration.py, backend/account_api.py |
| Administration | backend/account_admin.py |
| Capture | backend/lifecycle_snapshot.py |
| Teardown worker | backend/main.py |
| Politique Public Beta | tools/public_beta_policy.py |
| Tests ajoutés | tests/test_public_beta_capacity_ten.py, tests/test_public_beta_capacity_failures.py, tests/test_public_beta_capacity_backup.py, tests/capacity_roundtrip.py, tests/lifecycle_group_key_probe.py |

Aucun frontend, fichier .env, migration Alembic, Compose existant, outil de Production ou donnée réelle n’est modifié. L’image Web R2 est conservée. Les empreintes exactes figurent dans source-release.json et le manifeste de livraison.

**GO technique local pour une livraison fermée**, sous réserve des précontrôles VPS et de l’approbation distincte d’une intervention. L’ouverture publique reste hors de cette phase et bloquée par les conditions juridiques/opérateur.
