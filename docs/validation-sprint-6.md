# Validation Sprint 6 — CI/CD et VPS

## Livré dans le dépôt

- Adaptation de `compose.production.yaml` et `.env.production.example` aux paramètres confirmés
  `web`, `websecure`, `letsencrypt`, domaine DocuMind et Registry privée.
- `.github/workflows/ci.yml` : tests SQLite/PostgreSQL-pgvector/React/BFF, TypeScript, images
  multiarchitecture et publication après succès des tests sur `main`.
- `.github/workflows/deploy.yml` : lancement manuel, reviewers de `production` vérifiés,
  sélection d’un run CI réussi et du SHA exact, SSH épinglé, déploiement et rapport.
- `tools/release_manifest.py`, `tools/check_registry_tags.py` : identité de release, références
  par digest, révision supportée et refus de réutilisation accidentelle d’un tag SHA.
- `tools/deploy_production.py` : contrôles TLS/Registry/disque/volumes, sauvegarde, migration
  contrôlée, santé/HTTPS et retour applicatif compatible. Aucun downgrade de base automatique.
- Réutilisation et extension de `tools/backup_local.py` : appel par le déployeur, options de
  release, contrôles d’archives et SHA-256. `tools/prepare_production.py` ne génère plus un
  deuxième Traefik ; il valide les entrées et matérialise les références des images.
- Adaptation de `frontend/server/app.mjs`, `config.mjs`, `app.test.mjs` : confiance dans l’IP
  TCP exacte du Traefik, refus des en-têtes forgés, conservation de CSRF et des cookies sécurisés.
- `tests/test_deployment.py` et garde globale contre les clients OpenAI réels dans `tests/conftest.py`.
- [Guide complet](sprint-6-cicd.md), README et avertissement d’obsolescence de la préparation
  de proxy autonome du Sprint 5.

Les modifications locales antérieures du Sprint 5 ont été conservées. Aucun commit, push,
secret GitHub, paramètre serveur ou enregistrement DNS n’a été créé à distance par l’agent.
Les fichiers `.env` et `.env.production` ne sont pas suivis par Git.

## Vérifications locales exécutées

| Vérification | Résultat |
|---|---|
| Suite complète SQLite | 114 tests passent |
| Suite complète PostgreSQL 17/pgvector, base dédiée | 114 tests passent |
| Tests ciblés finaux de déploiement | 13 passent, dont le contrôle TLS ajouté après les suites complètes |
| React/Vitest | 37 tests passent |
| BFF/Node | 23 tests passent |
| TypeScript et Vite production | Réussite |
| Build local Docker backend et frontend | Réussite, aucune publication |
| Compose de production avec références fictives par digest | `config --quiet` valide |
| Syntaxe/sécurité des deux workflows | actionlint 1.7.12 valide |
| Intégrité de l’outil actionlint | SHA-256 vérifié contre la release officielle |
| Point d’accès HTTPS de la Registry, sans identifiants | Certificat vérifié ; HTTP 401 attendu |
| Restauration locale isolée de la sauvegarde existante | 18 tables et six fichiers vérifiés ; upgrade/rollback vérifiés |

Les 114 cas comprennent douze tests de déploiement ; le treizième test ciblé, indépendant de
la base, vérifie ensuite le refus d’une Registry marquée insecure ou couverte par un CIDR
insecure. Au total, **115 cas Python distincts validés**, sans annoncer une seconde exécution
complète de 115 cas. Les suites couvrent les régressions des comptes, documents, RAG, BYOK,
budgets, expiration, isolation, migrations et reprises.

Les nouveaux tests simulent une sauvegarde échouée, un démarrage échoué, une migration
nécessitant approbation et un rollback incompatible. Ils vérifient que la sauvegarde précède
la migration, que la release n’est activée qu’après contrôles et que le schéma n’est jamais
automatiquement rétrogradé. Les simulations ne sont pas présentées comme un déploiement VPS.

Les tests BFF supplémentaires exercent le vrai serveur Express avec un pair réseau autorisé
ou refusé, `X-Forwarded-Proto`, la propagation contrôlée de l’IP, les cookies et les jetons CSRF.
La compatibilité Caddy locale reste couverte par les tests précédents.

## Données et infrastructure préservées

Les tests PostgreSQL ont utilisé `documind_sprint6_test`, distincte de la base locale.
La restauration a utilisé `documind_restore_sprint6`, supprimée après vérification. Le test
porte sur la sauvegarde locale préexistante, pas sur une sauvegarde du VPS non déployé.
Aucun arrêt de la stack locale ni déploiement production n’a été requis. Aucune migration
nouvelle, aucune modification des UUID, des budgets ou des documents existants.

Le projet Compose et les noms logiques des deux volumes sont conservés. Le réseau Traefik
est déclaré externe ; aucune commande ne le crée ni ne le modifie. Aucun service Registry,
Traefik ou application tierce n’est inclus dans les opérations de déploiement.

Les mots de passe applicatifs/Registry ne sont pas inscrits dans les labels, dans les
arguments des processus, dans les rapports ou dans les bundles. Les commandes capturent
leurs erreurs sans publier leur sortie brute. Les étapes de téléchargement/push réels n’ont
pas été lancées ; l’essai HTTPS 401 ne valide pas les droits Registry.

## Reste à configurer par l’administratrice

1. Les neuf secrets GitHub et la variable `VPS_DEPLOY_PATH` listés dans le guide.
2. L’environnement GitHub `production`, ses reviewers et ses restrictions à `main`.
3. Reporter `TRAEFIK_CONTAINER=traefik` dans `.env.production` sur le VPS (nom confirmé) ; le déployeur relèvera son IP sur `web`.
4. Le compte SSH, sa clé hôte vérifiée et le répertoire privé du VPS.
5. Les secrets applicatifs de production, le DNS et les droits réels des comptes Registry.
6. La capacité RAM/CPU restante avec les autres applications ; seul le disque libre a été confirmé.
7. La sauvegarde chiffrée hors VPS, sa rotation et son exercice de restauration indépendant.

Le code du dépôt doit être revu et commité avant que GitHub puisse exécuter ces workflows.
Le premier lancement manuel et son approbation restent nécessaires ; aucune connexion SSH
au VPS ni publication authentifiée n’a eu lieu dans cette session.

## Validation réelle restant à faire après approbation

Publication/pull authentifiés des trois images, démarrage de la stack, TLS par le Traefik réel,
login d’un compte contrôlé, import PDF/TXT et analyse classique, second compte isolé,
connexion/révocation BYOK sans appel fournisseur, SMTP, reprise après interruption et
restauration d’une sauvegarde VPS dans une instance indépendante. Les sondes automatiques
post-déploiement vérifient santé, HTTPS, cookie CSRF et refus des documents anonymes.

Les limites RAM des sessions nécessitent une instance unique. Une recréation de Traefik
peut changer son IP : rafraîchir le BFF par déploiement approuvé. L’autorisation par dépôt et
l’immutabilité serveur de la Registry ne sont pas présumées. Les protections d’environnement
dépendent du plan GitHub ; le workflow reste fermé si les reviewers obligatoires manquent.

Aucun appel OpenAI payant, aucun email réel et aucune ouverture publique n’ont été déclenchés.
