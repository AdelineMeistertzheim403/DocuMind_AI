# Sprint 3 — Assistant documentaire et BYOK

Le [Sprint 5](sprint-5-accounts.md) remplace les parcours de comptes décrits ci-dessous :
Argon2id, connexion obligatoire pour les documents, invitations, récupération et CSRF.
Les anciennes sections scrypt et espace HTTP partagé constituent l’historique des sprints.

Le Sprint 4 et la [correction des résumés longs](long-document-summary.md) étendent ce socle. Les documents longs utilisent désormais des tâches persistantes et une réduction multi-niveaux, avec confirmation chiffrée ; la limite de cinq étapes du premier résumé ne s’applique plus à ce parcours.

L’analyse classique reste locale et disponible sans IA. Aucun appel OpenAI réel n’a été effectué pendant cette implémentation. `AI_ENABLED=false` est conservé dans la configuration locale. Les résultats des tests sont simulés explicitement, jamais présentés comme une validation du compte OpenAI.

## Architecture retenue après audit

Le moteur `analyseur_documents/`, l’extraction sécurisée, les pages et chunks du Sprint 1 sont conservés. Le BFF du Sprint 2 utilisait un propriétaire partagé : cette clé serveur ne constituait pas une authentification par utilisateur. Les comptes ajoutés sont indépendants des clés OpenAI.

Le parcours HTTPS est : navigateur → Caddy → BFF → FastAPI → fournisseur OpenAI. Le BFF ne transmet que des routes autorisées. Il transforme le cookie de session en authentification interne et ne renvoie jamais le jeton interne au JavaScript. La session utilise un cookie `__Host-documind`, `HttpOnly`, `Secure`, `SameSite=Strict`, sans domaine. Les requêtes de modification vérifient aussi l’origine. Les appels IA depuis le web exigent une session authentifiée et HTTPS.

Les comptes SQL utilisent un mot de passe haché par scrypt avec sel aléatoire. Leur UUID propriétaire isole documents, historiques et consommations. La création est administrative, sans inscription publique. Le coffre serveur garde uniquement en RAM les empreintes des jetons de session, leur propriétaire et, facultativement, la clé personnelle. La durée fixe est de 30 minutes par défaut, sans renouvellement implicite. Les accès expirés sont refusés immédiatement ; un nettoyage toutes les 15 secondes libère aussi les clés des sessions inactives. Le redémarrage ou la déconnexion détruit la session. Aucune clé personnelle n’entre en base.

Cette version exige **un seul processus FastAPI**. Plusieurs workers auraient des coffres différents. La suppression de références Python ne garantit pas l’effacement physique de la mémoire. Un déploiement distribué nécessiterait un coffre éphémère approprié, une gestion des secrets et une politique de révocation explicite.

Deux configurations sont résolues pour chaque requête :

- `OWNER_DEMO` utilise la clé serveur, avec un budget partagé et des quotas. `OWNER_DEMO_ENABLED=false` le désactive.
- `USER_BYOK` exige une clé connectée et validée dans la session courante. Aucun repli sur la clé propriétaire n’est effectué. Le budget est associé à `byok:{owner_uuid}:openai`, indépendamment des sessions et des changements de clé.

`AIProvider` accepte cette configuration propre à l’utilisateur. `OpenAIProvider` utilise le SDK officiel et Responses ; `MockAIProvider` sert aux tests. Les clés ne sont jamais enregistrées dans les réponses, cookies, URL, localStorage, sessionStorage ou journaux applicatifs. Le champ React est temporaire, vidé avant l’envoi et exclu du cache des mutations. Les erreurs de validation retirent les valeurs reçues.

## Installation et premier accès sécurisé

Suivre l’installation du README. Ne pas écraser un `.env` existant avec l’exemple. `API_KEYS` reste nécessaire pour le lien serveur BFF/FastAPI. `DOCUMIND_GATEWAY_TOKEN` doit contenir un secret aléatoire indépendant, identique pour Caddy et le BFF ; il est déjà généré dans l’environnement local utilisé pour les vérifications. Pour une nouvelle installation, générer une valeur avec `secrets.token_urlsafe(48)` et la placer uniquement dans le `.env` serveur, jamais dans une variable `VITE_*`.

```powershell
docker compose --profile https up --build -d
docker compose exec api python -m backend.accounts adeline
```

La commande demande deux fois un mot de passe de 12 caractères minimum, sans l’afficher ni le passer en argument. Elle crée un propriétaire neuf. Pour rattacher administrativement un compte à un espace existant, utiliser `--owner-id UUID_DU_PROPRIETAIRE` : cela donne accès à tous ses documents. Ne pas partager cet UUID entre utilisateurs indépendants.

L’URL est **https://localhost:8443/settings/ai**. Caddy crée une autorité locale ; son certificat n’est pas automatiquement approuvé par Windows ou Firefox. Exporter uniquement le certificat public :

```powershell
New-Item -ItemType Directory -Force var/tls
docker compose cp https:/data/caddy/pki/authorities/local/root.crt ./var/tls/documind-local-root.crt
```

Importer ce certificat de votre propre instance dans les autorités de confiance du navigateur, puis vérifier l’accès sans avertissement **avant de saisir une vraie clé**. Ne jamais copier ou partager `root.key`. Les tests ignorent l’avertissement uniquement pour des identifiants synthétiques. Pour une publication, utiliser un domaine et un certificat public appropriés.

L’accès HTTP `http://127.0.0.1:3000` conserve les fonctions classiques dans l’espace partagé du BFF ; il refuse la saisie de clés et les nouveaux appels IA. Les comptes personnels utilisent HTTPS. Les ports restent liés à la boucle locale : ne pas exposer l’espace HTTP partagé publiquement.

Si « Ouvrez la connexion HTTPS locale pour gérer votre compte et votre clé » apparaît même sur `https://localhost:8443`, vérifier que `DOCUMIND_GATEWAY_TOKEN` n’est pas vide dans `.env`. Caddy et le BFF doivent recevoir la même valeur. Après une modification de cette variable, recréer les deux services ensemble :

```powershell
docker compose --profile https up -d --no-deps --force-recreate web https
```

Un simple redémarrage ne recharge pas les variables d’environnement des conteneurs. Ne pas remplacer un `.env` configuré par `.env.example`, dont les secrets sont volontairement vides.

Dans « Paramètres IA » : se connecter, choisir `USER_BYOK`, fixer le plafond, connecter la clé, puis cliquer explicitement sur **Valider la clé**. La connexion seule ne contacte pas OpenAI. La validation appelle `models.retrieve` pour le modèle configuré : aucune génération de tokens ; cela ne garantit ni crédits disponibles ni accès effectif à toutes les opérations. Les réponses ne contiennent que des indicateurs de connexion et de validation.

## Configuration IA

Toutes les variables sont décrites dans `.env.example`. Principaux réglages :

| Variable | Valeur initiale | Rôle |
|---|---|---|
| `AI_ENABLED` | `false` | Interrupteur de génération, également pour BYOK |
| `AI_PROVIDER` | `openai` | Fournisseur interchangeable ; `mock` réservé aux simulations |
| `OPENAI_API_KEY` | vide | Clé serveur pour OWNER_DEMO uniquement |
| `OWNER_DEMO_ENABLED` | `true` | Autoriser le mode propriétaire |
| `OPENAI_MODEL` | `gpt-5.6-luna` | Modèle de génération |
| `AI_BUDGET_USD` | `4` | Plafond estimatif partagé OWNER_DEMO |
| `AI_SUMMARY_QUOTA` / `AI_QUESTION_QUOTA` | `20` / `100` | Quotas cumulés par propriétaire |
| `AI_MAX_INPUT_TOKENS` / `AI_MAX_OUTPUT_TOKENS` | `16000` / `1200` | Bornes par appel |
| `AI_MAX_SUMMARY_STEPS` | `5` | Nombre maximal d’appels par résumé, réduction incluse |
| `AI_MAX_QUESTION_CHUNKS` | `5` | Passages maximum pour une question |
| `AI_TIMEOUT_SECONDS` | `30` | Délai d’un appel fournisseur |
| `AI_MAX_CONCURRENT_REQUESTS` | `2` | Réservations actives maximum |
| `AI_REQUESTS_PER_MINUTE` | `6` | Limitation par propriétaire |
| `AI_SESSION_TTL_SECONDS` | `1800` | Session fixe ; maximum 3600 secondes |

Le plafond BYOK est modifiable par l’utilisateur entre 0 et 100 USD. Les quotas sont cumulatifs, sans remise à zéro quotidienne ; une opération acceptée puis échouée consomme son quota. Les compteurs de tokens et quotas regroupent les modes du propriétaire, tandis que le budget affiché correspond au mode courant. La liste de consommation précise le mode de chaque appel.

Les tarifs doivent correspondre exactement au modèle et dater de moins de 90 jours. Changer de modèle exige de vérifier capacités et tarifs, puis de mettre à jour `AI_PRICING_MODEL`, les deux prix et `AI_PRICING_VERIFIED_ON`. Le tarif d’entrée configuré à 0,25 USD/million est volontairement prudent pour les écritures de cache ; la sortie est à 1,20 USD/million. La configuration borne le contexte en dessous du seuil de contexte long. Ces hypothèses proviennent de la [fiche du modèle](https://developers.openai.com/api/docs/models/gpt-5.6-luna) et des [tarifs officiels](https://developers.openai.com/api/docs/pricing), consultés le 19 octobre 2026 ; l’accès de votre compte reste à vérifier.

## Résumés, questions et sources

Les requêtes utilisent des sorties JSON strictes validées par Pydantic. Un résumé comporte synthèse générale, points clés, informations importantes, limites et identifiants de sources. Une question renvoie réponse, indicateur d’information insuffisante et sources. Les identifiants doivent appartenir aux passages réellement fournis ; les extraits et numéros de page affichés sont relus depuis PostgreSQL. Le contenu est rendu comme du texte, sans HTML exécuté.

Un résumé court utilise tous les chunks. Un document plus long est réparti en groupes contigus, résumés puis réduits dans la limite d’appels autorisée. Un dépassement détecté avant lancement renvoie 413 sans appel. Une réduction devenue trop volumineuse peut échouer après des étapes déjà facturables : celles-ci restent comptabilisées. Aucun tronquage silencieux n’est présenté comme un résumé intégral.

Les questions utilisent une recherche lexicale locale bornée et indépendante des conversations précédentes. Sans passage pertinent, l’application répond « informations insuffisantes » sans génération. Ce MVP ne fait ni embeddings, ni recherche web, ni exécution du document. Les instructions distinguent contenu documentaire et instructions système ; un document hostile reste un risque pour la qualité de réponse. Des références valides ne prouvent pas la fidélité de toutes les affirmations : vérifier les passages.

L’utilisateur doit autoriser l’envoi avant une nouvelle génération. `store=false` est transmis à Responses. Cela ne signifie pas absence de toute rétention chez OpenAI : consulter les [règles de traitement des données](https://developers.openai.com/api/docs/guides/your-data). Ne pas envoyer de données confidentielles sans autorisation.

## Budgets, concurrence et idempotence

Avant tout appel, une transaction verrouille le budget et vérifie plafond, réservations actives, quota et limitation de débit. La réservation couvre la borne entrée/sortie, le nombre maximal d’étapes et deux tentatives éventuelles. PostgreSQL utilise des verrous de lignes ; SQLite utilise une transaction immédiate pour les tests. Changer de clé, se reconnecter ou supprimer un document ne réinitialise pas les consommations.

Les tokens d’usage retournés par OpenAI donnent les coûts estimés, avec les tarifs utilisés à cet instant. Les tokens de raisonnement sont compris dans les tokens de sortie et ne sont pas facturés deux fois dans le calcul. Un 429 explicite peut être réessayé une seule fois ; les reprises automatiques du SDK sont désactivées. Une erreur réseau, un délai ou une erreur serveur ambiguë conserve la réservation : une facturation a pu avoir lieu. Une même clé d’idempotence ne relance pas l’appel ; réutiliser cette clé avec un autre contenu produit 409.

Les plafonds DocuMind **ne garantissent pas un plafond absolu de facturation OpenAI** : tarifs, usages extérieurs, différences de mesure et appels déjà transmis peuvent produire des écarts. Configurer aussi les contrôles disponibles dans le compte fournisseur. Une clé déconnectée ne peut plus lancer d’appel, mais ne peut pas annuler un appel déjà transmis.

Les réservations interrompues par un arrêt serveur restent bloquées par prudence. Procédure administrative, API arrêtée :

```powershell
docker compose stop api
docker compose run --rm --no-deps api python -m backend.ai.maintenance
# Après examen : comptabiliser tout le maximum réservé, sans rembourser une charge inconnue.
docker compose run --rm --no-deps api python -m backend.ai.maintenance --charge-reservation UUID
docker compose up -d api
```

Cette procédure ne contacte pas OpenAI. Le coût devient une estimation conservatrice du maximum ; elle ne permet pas de contourner un plafond par remboursement d’une charge incertaine.

## API et données

Swagger FastAPI reste accessible sur le port API local (`8001` dans la configuration de développement actuelle). Les routes documentaires classiques restent inchangées. Les nouvelles routes sont :

| Méthode et route `/api/v1` | Fonction |
|---|---|
| `GET /ai/status` | Configuration, disponibilité, budget et compteurs |
| `GET /ai/usage` | Consommations du propriétaire, pagination `offset` / `limit` |
| `POST /documents/{id}/summarize` | Résumé avec consentement et UUID d’idempotence |
| `GET /documents/{id}/summaries` | Résumés persistés, pagination |
| `POST /documents/{id}/ask` | Question autonome avec consentement et UUID |
| `GET /documents/{id}/ai-history` | Questions/réponses persistées, pagination |
| `POST /auth/login`, `POST /auth/logout` | Connexion et révocation de session |
| `GET /ai/settings`, `PUT /ai/settings` | Mode, indicateurs de clé et plafond personnel |
| `POST /ai/key`, `DELETE /ai/key` | Connexion ou retrait de la clé |
| `POST /ai/key/validate` | Vérification explicite du modèle, sans génération |

Connexion, paramètres et clés passent par le BFF HTTPS ; ils refusent l’accès sans liaison serveur de confiance. Swagger permet toujours les opérations documentaires avec `X-API-Key`, et le mode propriétaire si activé. Il ne remplace pas le parcours BYOK sécurisé du navigateur.

Réponses principales : 200 succès ou cache ; 401 session absente/expirée ; 403 accès interdit ou configuration désactivée ; 404 document d’un autre propriétaire ou absent ; 402 plafond insuffisant ; 409 conflit d’idempotence ou traitement actif ; 413 contexte trop volumineux ; 422 requête invalide ; 429 quota/débit/concurrence ; 502/503 fournisseur invalide ou indisponible. Les erreurs IA exposent un code contrôlé et un message, jamais l’exception brute du fournisseur.

Les migrations `0002` et `0003` ajoutent budgets, réservations, usages, résumés, interactions, sources et comptes. `0001` est conservée. La suppression d’un document supprime ses textes et historiques, mais garde les écritures financières sans contenu ni lien vers le document supprimé. Elle est refusée pendant une réservation active. Un UUID propriétaire n’est jamais accepté depuis le corps d’une requête documentaire.

## Révocation et limites

« Déconnecter la clé » retire toutes les clés des sessions de ce propriétaire dans le processus courant. La déconnexion utilisateur révoque sa session courante. L’expiration et le redémarrage retirent aussi les clés. Ces actions ne révoquent pas la clé chez OpenAI : pour une révocation définitive, supprimer la clé depuis le tableau de bord OpenAI, notamment après exposition ou suspicion de compromission.

Pour une production publique, il reste notamment à prévoir une authentification gérée et sa récupération de compte, des sessions distribuées sécurisées, une politique de conservation et de supervision, des sauvegardes et une protection d’infrastructure. Le MVP local ne comporte ni inscription publique, ni récupération de mot de passe, ni MFA. Le coffre ne doit pas être remplacé par une colonne de clé en clair.

## Vérifications et essai réel volontaire

```powershell
.\.venv\Scripts\python.exe -m pytest -q
cd frontend
npm.cmd test
npm.cmd run build
$env:BYOK_E2E='1'
npm.cmd run test:e2e
Remove-Item Env:BYOK_E2E
```

Les tests automatisés utilisent des fournisseurs simulés. Ils couvrent sorties structurées, sources, budgets concurrents, idempotence, isolation, erreurs sans fuite, expiration, révocation et transport BFF. Playwright crée puis supprime ses propres comptes et fichiers ; son test BYOK ne valide jamais une vraie clé. Pour PostgreSQL, `TEST_DATABASE_URL` doit désigner une **base dédiée vide** : le jeu de tests applique puis annule les migrations, et refuse une base contenant des tables métier.

Pour un essai OpenAI réel, après validation du certificat et création du compte :

1. Régler `AI_PROVIDER=openai`, `AI_ENABLED=true`, quotas résumé/question à 1, `AI_MAX_OUTPUT_TOKENS=800`. En BYOK, laisser `OPENAI_API_KEY` vide et fixer son plafond personnel à 0,05 USD. En mode propriétaire, fournir uniquement la clé serveur et régler `AI_BUDGET_USD=0.05`.
2. Recréer API et web avec `docker compose --profile https up -d --force-recreate api web https`, puis se reconnecter : le redémarrage invalide les sessions.
3. En BYOK, connecter puis valider volontairement la clé. Importer un TXT fictif : « Le projet Atlas commence en novembre. Son budget est de 120 euros. Camille est responsable. »
4. Autoriser et générer un résumé, vérifier sources, tokens, coût et libération de réservation. Poser une question sur le budget, vérifier la source, puis vérifier qu’une deuxième question différente est bloquée par le quota. Consulter aussi la consommation dans le compte OpenAI.
5. Remettre `AI_ENABLED=false`, recréer l’API, puis retirer/révoquer les clés de test selon les besoins.

Cet essai est volontaire, potentiellement payant et n’a pas été lancé par l’agent. Les tarifs, permissions et crédits réels du compte restent donc à confirmer.
