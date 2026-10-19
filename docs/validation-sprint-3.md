# Validation Sprint 3 et BYOK — 19 octobre 2026

## Résultat livré

Assistant documentaire React avec résumés et questions sourcées, consentement, états d’erreur et historiques. FastAPI utilise un fournisseur interchangeable, le SDK OpenAI Responses, des schémas stricts et des références relues depuis les chunks en base. L’analyse classique et l’application Python de bureau sont conservées.

Le complément BYOK ajoute comptes indépendants, paramètres IA, sessions serveur éphémères, validation volontaire de l’accès au modèle, budgets personnels et consommation par appel. Les clés personnelles restent en mémoire serveur, sans persistance SQL ou navigateur. OWNER_DEMO utilise un budget global distinct. Caddy fournit l’accès HTTPS local, avec un certificat à approuver manuellement avant l’utilisation de vraies clés.

## Vérifications exécutées

| Vérification | Résultat |
|---|---|
| pytest sur SQLite temporaire, migrations réelles | **53 réussis** |
| Même suite sur PostgreSQL 17, base dédiée vide | **53 réussis** |
| Vitest React | **29 réussis** |
| Tests Node du BFF | **18 réussis** |
| Playwright Docker, ordinateur et mobile | **8 réussis** |
| Revalidation BYOK avec dimensions et interactions mobiles | **2 réussis**, inclus dans les parcours précédents |
| Compilation TypeScript et build Vite | Réussis |
| Reconstruction Docker API/web et démarrage HTTPS | Réussis |
| `pip check` | Aucune dépendance incohérente |

Les 53 tests backend couvrent notamment CRUD, PDF/TXT, extraction, limites de ressources, statistiques, migrations, sorties IA incorrectes, sources inventées, cache, idempotence, défaillances ambiguës, budgets et requêtes concurrentes. Les tests BYOK vérifient isolation entre deux propriétaires, absence de repli sur la clé serveur, expiration, révocation, validation sans génération et plafond personnel concurrent.

Les tests BFF vérifient liste de routes autorisées, origines, corps bornés, secrets ajoutés côté serveur, refus HTTP et faux en-têtes HTTPS, suppression du jeton interne dans les réponses et cookie sécurisé. Les tests navigateur utilisent des comptes et clés synthétiques, ne déclenchent jamais le bouton de validation fournisseur et suppriment leurs comptes/fichiers à la fin.

La base de tests PostgreSQL a été créée puis supprimée séparément de la base documentaire. Les tests y appliquent et annulent les migrations à chaque cas. Deux problèmes d’environnement Windows ont été contournés : droits du dossier temporaire pytest et connexion `localhost` bloquée ; un dossier neuf et `127.0.0.1` avec délai de connexion borné ont permis la validation complète.

La suite Python produit un avertissement de dépréciation Starlette concernant son adaptateur TestClient/httpx ; aucun échec. La pile de tests utilise encore cet adaptateur fonctionnel.

## État local et limites pratiques

Les services `db`, `api` et `web` sont sains ; `https` est démarré. API locale : port **8001** ; interface classique : **3000** ; interface sécurisée : **https://localhost:8443**. Les migrations appliquées sont à la révision **0003**.

`AI_ENABLED=false` reste conservé. Aucun appel OpenAI réel, gratuit ou payant, n’a été effectué ; les tests de génération et de validation fournisseur sont simulés. L’accès au modèle, les crédits, les coûts réellement facturés et la qualité des réponses réelles ne sont donc pas validés. Aucun mot de passe utilisateur par défaut n’est créé et aucune autorité de certification n’est installée automatiquement dans Windows/Firefox.

Le [guide de configuration et de révocation](sprint-3-ai-byok.md) indique comment créer son compte, approuver le certificat local, connecter sa propre clé et mener un essai réel volontaire à petit budget. Les plafonds sont estimatifs ; les opérations ambiguës gardent leur réservation, et la révocation locale ne peut annuler un appel déjà transmis.

Le coffre éphémère exige un seul processus API. L’accès HTTP partagé reste local. La production publique et les sessions distribuées nécessitent des travaux supplémentaires explicités dans le guide. Le dépôt n’étant pas initialisé avec Git, aucun commit n’a été créé.
