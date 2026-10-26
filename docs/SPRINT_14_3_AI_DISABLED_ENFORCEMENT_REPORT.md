# Sprint 14.3 — Désactivation stricte des fonctionnalités IA

Date : 25 octobre 2026. Branche locale :
`preparation/sprint-14-3-ai-disabled-enforcement`, créée depuis le travail non commité
de `preparation/sprint-14-2-public-beta-authorization`, sans retour à `main`.

Les dix fichiers préexistants des Sprints 14.1/14.2 ont été relevés par SHA-256 avant
intervention et sont vérifiés inchangés. Ce lot n'active aucun service en production,
aucune inscription ni fonctionnalité IA. Aucun commit, push, merge, accès VPS,
modification de `.env.production`, migration ou compteur de production.

## 1. Inventaire des points d'appel réels

La recherche des constructions SDK et appels fournisseur dans `backend/` et
`analyseur_documents/` identifie les trois points réseau suivants. Aucun autre
client fournisseur n'a été trouvé dans le moteur documentaire classique.

| Point réseau | Chemins applicatifs qui l'utilisent | Contrôles antérieurs | Renforcement 14.3 |
| --- | --- | --- | --- |
| `backend/ai/settings_api.py:validate_key()` : construction `OpenAI`, puis `models.retrieve()` | Validation BYOK explicite depuis `/api/v1/ai/key/validate` et le BFF. | Passerelle HTTPS, session utilisateur, limite de débit ; **pas de contrôle `ai_enabled`**. | HTTP 403 `disabled` avant lecture de clé, callback de validation, construction SDK ou requête. |
| `backend/ai/providers.py:OpenAIProvider.generate()` : `client.responses.create()` | Résumé court, question documentaire, étapes et synthèse de résumé long, réponse RAG et synthèse de comparaison via `ConfiguredProvider`. | Réservations, configuration, consentement, propriétaire, budgets, schémas et références ; vérification globale en amont pour les réservations fraîches. | Contrôle avant construction SDK et chaque tentative ; vérification du paramètre courant et de la configuration capturée au niveau de `ConfiguredProvider`. |
| `backend/rag/providers.py:OpenAIEmbeddingProvider.embed()` : `client.embeddings.create()` | Indexation par lots et embedding de requête sémantique via `embed()`. | Autorisation documentaire, consentement, configuration, quotas et réservation avant appel ; repli lexical de recherche si IA indisponible. | Contrôle avant construction, avant invocation, dans le wrapper et dans les paramètres du worker. Un ancien snapshot actif ne supplante pas le drapeau courant fermé. |

Les clients de génération et embeddings gardent `max_retries=0` côté SDK. L'unique
retry métier de génération reste limité à un rejet certain 429 ; il revérifie aussi
l'autorisation. Aucun proxy libre vers OpenAI n'est créé, et les URL fournisseur
existantes restent fixes. Le BFF ne construit aucun SDK et ne contacte que FastAPI.

### Chemins sans appel fournisseur

`connect_key()` ne réalisait aucun appel réseau mais acceptait une nouvelle clé
en RAM malgré l'IA fermée : il est désormais refusé dans ce cas. `disconnect_key()`
reste local et enlève les clés des sessions du propriétaire. Connexion utilisateur,
déconnexion, profil, révocation des sessions, préférences locales de budget/mode,
statut, consommation et historiques ne nécessitent pas d'appel fournisseur.

Les plans de résumé, comparaisons déterministes, recherches lexicales et analyses
classiques utilisent seulement les documents et données internes autorisés.
La lecture de résultats existants peut aussi emprunter les chemins de cache déjà
présents dans certains POST : un HTTP 200 ne signifie alors ni appel ni activation IA.

## 2. B14-02 : cause et correction

Le contrôle de configuration des réservations de génération ne couvre pas le
parcours indépendant de validation de clé. `validate_key()` pouvait donc contacter
OpenAI pour lire les métadonnées d'un modèle avec `AI_ENABLED=false`, sans génération
de texte. La connexion de clé restait proposée et acceptée. La présence d'une clé
BYOK ou l'absence de clé serveur n'est pas une politique de fermeture.

Correction : refus dans les deux handlers après vérification de session, avant
extraction de la nouvelle clé, écriture en session ou accès à un validateur.
La réponse réutilise le contrat d'erreur existant `403 / detail.code=disabled`.
Les schémas, passerelle, autorisations et contrôles CSRF ne sont pas supprimés.
Un corps invalide peut toujours être refusé par son schéma avec 422 avant le handler,
sans appel fournisseur ; aucune règle de validation n'est relâchée.

`ensure_ai_enabled()` produit un `ProviderError('disabled',403,False,attempts)`
sans contenu ni secret. Il est également appliqué aux adaptateurs de génération et
d'embeddings, indépendamment de l'admission d'une requête ou de la validation d'une clé.
Les wrappers vérifient à la fois le paramètre courant de l'application et les
paramètres capturés. Les fournisseurs construits pour un appel disposent d'un
callback de vérification courant avant l'émission SDK, y compris au retry de génération.
Les fournisseurs injectés en test passent également par le contrôle du wrapper.

Un blocage avant toute tentative porte `attempts=0`. Si une première tentative 429
a réellement eu lieu et que l'IA est ensuite fermée, l'arrêt avant retry conserve
`attempts=1`, sans déclarer une consommation ambiguë ou effacer cette tentative.
Le registre des usages, la tarification, les plafonds et les réservations ne sont
pas réécrits par ce lot.

## 3. BYOK et traitements asynchrones

- IA fermée : aucune nouvelle connexion ni validation distante de clé, pour un
  compte public comme historique, avec ou sans clé préexistante.
- Une clé existante n'est ni renvoyée ni utilisée. Elle peut être supprimée ; logout,
  expiration et révocation conservent leurs règles de nettoyage RAM.
- Une session personnelle reste nécessaire ; une clé BFF ne devient pas une session.
- `runtime_settings()` bloque un worker avant dispatch fournisseur si l'application
  est fermée, même si son admission ou sa configuration enregistrée était active.
- Le worker de résumé conserve ses étapes validées et sa réservation selon les
  règles existantes. La reprise active est refusée ; la lecture et l'annulation
  restent possibles.
- Une indexation interrompue par `disabled` est mise en pause, sans nouvelle facture
  simulée ni reprise automatique. Les embeddings déjà enregistrés ne sont pas supprimés.
- Une réponse reçue pour un appel déjà envoyé reste comptabilisée. L'arrêt avant la
  prochaine étape ne gomme pas une consommation réelle, et l'annulation libère la
  réservation restante selon le mécanisme existant.

## 4. Fichiers modifiés pour ce lot

| Fichier | Rôle |
| --- | --- |
| `backend/ai/settings_api.py` | Refus de connexion et validation BYOK quand l'IA est fermée. |
| `backend/ai/providers.py` | Garde commune, constructeur, appels SDK et retry. |
| `backend/ai/api.py` | Garde des paramètres courants/capturés dans `ConfiguredProvider`. |
| `backend/rag/providers.py` | Garde du worker, wrapper, constructeur et appel embeddings. |
| `backend/rag/indexing.py` | État `paused` pour une interruption `disabled`. |
| `frontend/src/pages/AISettings.tsx` | Désactivation des actions clé tant que le statut n'est pas confirmé actif, conservation de suppression/compte/historiques. |
| `frontend/src/components/Assistant.tsx` | Disponibilité explicitement liée à `enabled`, reprise comprise ; message d'indisponibilité. |
| `frontend/src/pages/IntelligentLibrary.tsx` | Indexation, réponse et vecteurs désactivés ; recherche explicitement lexicale conservée. |
| `frontend/src/pages/CompareDocuments.tsx` | Synthèse externe désactivée, comparaison locale conservée. |
| `frontend/server/app.mjs` | Message d'erreur `disabled` compréhensible ; pas de deuxième flag BFF susceptible de diverger. |
| `frontend/server/app.test.mjs` | Relais du refus assaini, identité de session, suppression/lecture locale et CSRF. |
| `frontend/src/pages/AISettings.test.tsx` | Trois scénarios : fermé, statut indisponible, activé avec mocks. |
| `frontend/src/pages/Rag.test.tsx` | Deux scénarios supplémentaires de fermeture sans régression locale. |
| `tests/test_ai_disabled_enforcement.py` | Matrice comptes/clé/fonctions/worker/cache et espions SDK. |
| `tests/test_byok.py` | Fixture positive explicitement activée, avec validateur fictif ; les tests négatifs forcent eux-mêmes false. |
| `tests/test_openai_provider.py` | Tests positifs explicitement activés, toujours avec client fictif injecté. |
| Ce rapport | Inventaire, résultats et limites. |

Les modifications Git de préparation/livraison/administration et leurs tests,
visibles dans l'arbre de travail, proviennent du Sprint 14.2 et restent inchangées.
Pas de nouvelle variable, migration, règle de confinement ou politique de compteur.

## 5. Matrice fonctionnelle avec `AI_ENABLED=false`

| Opération | Politique et résultat attendu |
| --- | --- |
| Login/logout, compte/workspace, révocation | Autorisés selon session et autorisations existantes ; aucun SDK. |
| Import PDF/TXT, extraction, analyse déterministe, statistiques, suppression | Autorisés dans les limites existantes ; aucun SDK. |
| Nouvelle clé ou validation de modèle | Refus 403 `disabled`, avant mutation de clé ou client. |
| Suppression d'une clé, lecture des préférences et consommation | Autorisées pour le propriétaire ; aucun SDK. |
| Nouvelle génération de résumé court/long ou question | Refus, sans nouveau dispatch fournisseur. Les caches déjà existants peuvent être retournés localement. |
| Démarrage/reprise d'indexation, embedding externe | Refus pour nouvelle admission ; worker déjà admis arrêté avant dispatch. |
| Recherche sémantique | Repli lexical sans embedding externe, conformément au comportement existant. |
| Question RAG ou synthèse IA de différences | Refus de nouvelle génération ; résultat déjà en cache/strictement local éventuellement conservé. |
| Comparaison locale et sources documentaires | Autorisées, avec contrôles de propriétaire. |
| Historiques, plans et résultats existants | Lecture autorisée ; aucune génération automatique. |
| Annulation de résumé | Autorisée ; consommation déjà reçue conservée et réservation restante traitée normalement. |

Le frontend considère aussi un statut inconnu/indisponible comme insuffisant pour
autoriser une connexion de clé ou une action fournisseur. L'API reste l'autorité :
une requête forgée ne dépend pas de l'état des boutons. Les pages signalent que les
fonctionnalités IA seront disponibles ultérieurement, sans bloquer l'usage local.

## 6. Preuves de zéro appel dans les scénarios couverts

La fixture de tests distingue utilisateurs `legacy` et `public` déjà vérifiés.
Ces comptes sont fictifs, préparés directement en base de test ; elle ne remplace
pas une recette complète d'inscription publique, prévue dans les phases suivantes.
Elle simule une clé déjà attachée/validée en RAM, sans connexion à un fournisseur.

Les espions sont positionnés sur :

1. `openai.OpenAI` : toute construction SDK pendant un scénario interdit échoue et
   le compteur doit rester à zéro.
2. `app.state.ai_key_validator` : zéro invocation, même si ce hook de test est présent.
3. `app.state.ai_provider.calls` et `embedding_provider.calls` : aucune génération
   ou embedding injecté ne doit être invoqué pendant les opérations interdites.
4. Les méthodes `responses.create` et `embeddings.create` d'un client fictif déjà
   construit : zéro appel après désactivation.
5. `AIUsage`/`AIReservation` : absence de nouvelles consommations pour les refus et
   stabilité des usages lors des lectures/caches ; conservation d'une étape déjà reçue.

Pour les historiques/index existants et checkpoints, le setup actif est **uniquement
en mémoire de test et avec fournisseurs simulés**. Les compteurs sont relevés ou
remis à zéro dans les mocks avant les actions fermées ; on ne prétend pas que le
setup lui-même n'a pas utilisé le mock. Aucun flag de production n'est changé.
Le test positif de métadonnées utilise un faux gestionnaire SDK et vérifie un seul
`models.retrieve`, sans réseau. Les anciens tests positifs contrôlent les générations,
les références, budgets, reprises et l'isolation quand l'IA est volontairement active
dans leurs fixtures.

## 7. Résultats des validations locales

Résultats réels des campagnes terminées, sur les sources finales pour les
confirmations Linux, PostgreSQL et Windows complète :

| Campagne | Réussis | Ignorés | Échoués |
| --- | --- | --- | --- |
| Windows : première sélection désactivation + BYOK + adaptateur | 31 | 0 | 0 |
| Windows : sélection élargie, sept fichiers Python | 93 | 0 | 0 |
| Windows Python 3.13.7 : suite complète finale | 678 | 41 | 0 |
| WSL Ubuntu / Python 3.12.3 : sélection finale désactivation + BYOK + adaptateur | 35 | 0 | 0 |
| PostgreSQL 17.11 / pgvector 0.8.7 : mêmes sept fichiers Python | 93 | 0 | 0 |
| React/Vitest : suite complète | 47 | 0 | 0 |
| Node/BFF : suite complète | 50 | 0 | 0 |

La suite complète Windows a duré 613,42 secondes ; les 41 ignorés correspondent aux
40 cas natifs Linux et au test PostgreSQL de fermeture du Sprint 14.2 exécuté ici
avec SQLite. Aucun des 21 cas de désactivation n'est ignoré. La sélection Windows
élargie a duré 394,67 secondes, celle PostgreSQL 276,16 secondes, et la confirmation
Linux ciblée 103,28 secondes. Les sélections se recouvrent : ne pas additionner ces
totaux pour prétendre à autant de tests distincts. Aucune régression observée dans
ces campagnes. L'avertissement préexistant de dépréciation Starlette/httpx reste visible.

`npm run build` réussit : TypeScript et build Vite. Les premières tentatives React
et Vite dans le bac à sable ont échoué en lecture de répertoires avec `Access is
denied`, avant chargement des tests ; leur réexécution locale autorisée réussit,
sans changement de dépendances ni configuration de sécurité.

Les premières reproductions négatives avaient montré les connexions BYOK acceptées
et des adaptateurs non bloqués. Deux préconditions des nouveaux tests ont ensuite
été corrigées : l'analyse locale crée bien une ressource avec HTTP 201, et la reprise
attend un `SummaryRequest` valide avec consentement/idempotence. Aucun contrat métier
n'a été changé pour transformer ces 201/422 en succès artificiels.

Commandes de référence exécutées, avec dossiers temporaires propres :

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_ai_disabled_enforcement.py tests/test_ai.py tests/test_byok.py tests/test_openai_provider.py tests/test_rag.py tests/test_long_summary.py tests/test_accounts_saas.py -q -p no:cacheprovider --basetemp=var/pytest-14-3-regressions --tb=short
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp=var/pytest-14-3-windows-full --tb=short
# Dans frontend :
npm.cmd run test:ui
npm.cmd run test:bff
npm.cmd run build
```

```bash
# Commande WSL exécutée depuis les sources du dépôt local :
env -u TEST_DATABASE_URL /var/tmp/documind-s13-a7b75801/.venv/bin/python -m pytest \
  tests/test_ai_disabled_enforcement.py tests/test_byok.py tests/test_openai_provider.py \
  -q -p no:cacheprovider --basetemp=/tmp/documind-s14-3-linux-20261025 --tb=short
```

WSL réutilise le venv local `/var/tmp/documind-s13-a7b75801/.venv/bin/python`, sans
copie de fichier privé et avec `TEST_DATABASE_URL` retirée pour sa campagne SQLite.
PostgreSQL utilise une base neuve `documind_ai_disabled_test`, un compte fictif et un
port éphémère **127.0.0.1**, jamais une URL existante. La variable de test est restaurée
en `finally`, et la fixture refuse une base non vide à l'entrée.

Docker cible explicitement le pipe local Desktop, réutilise l'image disponible
`documind-postgres-vector:17` avec `--pull never`, un réseau neuf sans masquerading
et un tmpfs neuf. Aucun volume persistant ni réseau existant. Conteneur non root,
capacités supprimées, `no-new-privileges`, mémoire 512 Mio, CPU 1, 64 processus.
Ce test de base ne constitue pas un déploiement de l'application.
Le conteneur `documind-s14-3-pg-20261025-c39f` et son réseau dédié ont été arrêtés puis
supprimés après vérification de leur label `documind.test=sprint-14-3` et de leurs
montages exclusivement tmpfs. Les filtres Docker sur ce label ne montrent aucune
ressource restante. Aucun conteneur ou volume préexistant n'a été modifié.

## 8. Risques résiduels et portée du verdict

- Le drapeau est chargé par `Settings` au démarrage ; éditer un env ne désactive pas
  un processus vivant. Aucun endpoint de bascule IA publique ou automatique n'est ajouté.
- Un appel déjà transmis ne peut pas être rappelé par une vérification booléenne.
  Il peut terminer et être comptabilisé. Les gardes s'appliquent avant les nouveaux
  dispatchs et les nouvelles tentatives ; ce n'est pas un mécanisme d'arrêt atomique
  de toutes les connexions réseau en cours.
- Les tests démontrent l'absence d'invocation aux points instrumentés et pour les
  scénarios listés, pas l'impossibilité absolue de toute communication dans un futur
  plugin fournisseur. Tout nouvel adaptateur doit appliquer la même politique avant
  construction et émission, et étendre la matrice de tests.
- Aucun appel réel OpenAI, donnée utilisateur, document réel, secret ou service de
  production n'est utilisé. La délivrabilité SMTP, les textes légaux, la configuration
  réelle Traefik et l'activation opérateur ne sont pas vérifiés par ce lot.
- Les suites complètes Linux et PostgreSQL, les tests navigateur E2E et une recette
  complète de stack HTTPS ne sont pas assimilés aux sélections exécutées ici.
- Aucun changement du confinement PDF/TXT ; les tests natifs Landlock/seccomp et
  l'image de production ne sont pas recertifiés par les tests portables locaux.

## 9. Préparation du Sprint 14.4

Conserver les contrôles du Sprint 14.2 et le drapeau IA fermé. Compléter les preuves
à cinq admissions cumulatives, les courses inscription/vérification/renvoi/fermeture
sous PostgreSQL, la politique de blocage administratif d'un compte en attente et
la restauration du compteur/verrou. Les comptes déjà admis, leur historique et les
fonctionnalités documentaires locales doivent garder la même isolation.

**Verdict : B14-02 corrigé localement pour les points d'appel et scénarios instrumentés ;
lot prêt pour revue Git, pas pour une ouverture publique.** La suite complète Windows,
les sélections Linux/PostgreSQL, React, BFF et le build sont réussis. Les fonctions
documentaires locales et historiques contrôlés restent accessibles sans nouveau
fournisseur. Les dix fichiers du périmètre préexistant 14.1/14.2 restent identiques.

**L'ouverture publique reste No-Go** tant que les phases restantes et les validations
d'exploitation ne sont pas approuvées. La production Sprint 13 n'a pas reçu ce
correctif pendant cette mission. Aucun commit, push ou déploiement ne découle de ce rapport.
