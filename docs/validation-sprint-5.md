# Validation Sprint 5 — 19 octobre 2026

## Résultat livré

Version locale Docker mise à jour, accès par `https://localhost:8443/login`.
Comptes historiques conservés, connexion par email ou identifiant historique, Argon2id,
invitations, récupération configurable, sessions révocables, CSRF et espace personnel obligatoire.
L’analyse classique et les parcours RAG/BYOK des sprints précédents restent disponibles.
Le Compose de production est préparé et validé, **jamais démarré ni ouvert publiquement**.
Aucun email réel ni appel OpenAI réel n’a été lancé par la validation.

## Fichiers créés

- `backend/account_models.py` : registre des espaces, membres, jetons hachés et demandes d’effacement.
- `backend/account_api.py` : inscription/récupération, profil, sessions, mot de passe, confidentialité.
- `backend/account_admin.py` : inventaire des propriétaires, invitations, email historique et purge administrative.
- `backend/gateway.py` : authentification du BFF et IP de confiance.
- `backend/resource_limits.py` : admission RAM bornée et verrou des quotas documentaires.
- `migrations/versions/0006_accounts_and_personal_workspaces.py`.
- `frontend/src/services/account.ts`, `frontend/src/pages/Account.tsx` et `Account.test.tsx`.
- `frontend/e2e/account-fixture.ts`, `frontend/e2e/accounts.spec.ts`.
- `tests/test_accounts_saas.py`, `tests/test_sprint5_migration.py`.
- `compose.production.yaml`, `.env.production.example`.
- `tools/prepare_production.py`, `tools/validate_restore.py`.
- `docs/sprint-5-accounts.md`, ce rapport.

## Fichiers modifiés

- Backend : `backend/auth.py`, `config.py`, `api.py`, `main.py`, `accounts.py`,
  `services/documents.py`, `ai/settings_api.py`, `ai/service.py`, `rag/billing.py`.
- Migrations/outils : `migrations/env.py`, `tools/backup_local.py`, `tools/verify_snapshot.py`.
- Frontend : `frontend/server/app.mjs`, `server/config.mjs`, `server/app.test.mjs`,
  `src/services/api.ts`, `src/App.tsx`, `src/components/Layout.tsx`, `src/styles.css`,
  `src/test/app.test.tsx`, `playwright.config.ts`, `e2e/byok.spec.ts`, `e2e/documents.spec.ts`, `e2e/rag.spec.ts`.
- Configuration/docs : `pyproject.toml`, `requirements.lock`, `compose.yaml`, `.env.example`,
  `.gitignore`, `.dockerignore`, `frontend/.dockerignore`, `README.md`, `docs/sprint-3-ai-byok.md`.
- Tests existants : `tests/conftest.py` configure le plafond de requêtes de la simulation pour
  le polling accéléré ; les valeurs réelles sont testées séparément et restent inchangées.
- `.env` local uniquement : génération d’une clé interne BFF distincte. Les autres valeurs,
  notamment activation IA, clés et propriétaires historiques, sont préservées. Fichier ignoré,
  aucune valeur secrète publiée dans ce rapport.

## Migration et conservation

Migration unique : `0005 → 0006`, appliquée localement après sauvegarde et restauration de test.
Ajout de deux colonnes facultatives à `users`, de quatre tables et du rattachement des comptes
existants à leurs UUID propriétaires inchangés. Aucune réécriture de texte, de vecteur ou de mot
de passe pendant la migration. Les mots de passe seront migrés seulement à la connexion réussie.

Sauvegarde avant migration : `var/backups/sprint5-20261019-094504`, dump PostgreSQL, archive des
documents, manifeste de colonnes et empreintes. Sauvegarde privée conservée localement.

Restauration dans une base PostgreSQL neuve : comparaison des **18 tables historiques**, montée
à `0006`, retour à `0005`, nouvelle montée et comparaison à chaque étape. Vérification des tailles
et SHA-256 des **six fichiers documentaires**. Copie de restauration réussie retirée ensuite.
Après mise à jour locale puis tests réels, les 18 empreintes historiques sont encore identiques.

Le rollback de schéma est testé ; le rollback applicatif doit conserver le support d’Argon2id.
Une restauration d’une vieille sauvegarde nécessite de traiter séparément les écritures ultérieures.

## Routes

Les routes existent sous `/api/v1` et sont explicitement relayées sous `/bff`.

| Méthode / route | Succès | Contrôle principal |
|---|---:|---|
| GET `/auth/options` | 200 | configuration publique limitée, HTTPS |
| POST `/auth/register` | 201 | invitation email à usage unique, inscription désactivable |
| POST `/auth/login` (étendue) | 200 | email/identifiant, mot de passe, limites IP/identifiant |
| POST `/auth/logout` (existante) | 200 | session personnelle |
| POST `/auth/forgot-password` | 202 | réponse générique, email asynchrone et quotas |
| POST `/auth/reset-password` | 200 | empreinte de jeton, expiration, consommation atomique |
| GET `/account` | 200 | profil du compte courant seulement |
| GET `/account/sessions` | 200 | sessions du compte courant seulement |
| DELETE `/account/sessions/{digest}` | 200 | propriétaire de la session ciblée |
| POST `/account/password` | 200 | ancien mot de passe et révocation générale |
| POST `/account/deletion-request` | 202 | confirmation du mot de passe et désactivation |
| DELETE `/documents/{id}/ai-results` | 204 | propriété, absence de réservation active |
| DELETE `/documents/{id}/embeddings` | 204 | propriété, absence d’indexation active |
| GET `/bff/auth/csrf` (BFF seulement) | 200 | jeton signé lié à la session, cookie HttpOnly |

Erreurs contrôlées : 400 invitation/jeton invalide ou expiré ; 401 identifiants/session invalides ;
403 HTTPS/CSRF/inscription désactivée ; 404 ressource absente pour cet utilisateur ;
409 traitement en cours ; 413 taille ou quota de stockage ; 422 saisie invalide ; 429 limitation ;
503 base ou capacité indisponible. Le BFF masque les erreurs internes et ne transmet aucun secret.

## Vérifications exécutées

| Vérification | Résultat |
|---|---|
| Backend PostgreSQL 17 + pgvector | **102 tests passent** |
| Backend SQLite | **102 tests passent** |
| React/Vitest | **37 tests passent** |
| BFF/Node | **21 tests passent** |
| TypeScript + Vite production | Réussite, y compris dans l’image Docker |
| Playwright desktop/mobile | **14 scénarios distincts validés** |
| Compose local et production `config --quiet` | Valides avec secrets fictifs pour la production |
| Build des images API et web | Réussi |
| Migration/retour arrière sur restauration PostgreSQL | Réussite, empreintes inchangées |
| Restauration documentaire | Six tailles et SHA-256 vérifiés |
| Santé locale et connexion HTTPS | HTTP 200, services métier sains |

Les tests couvrent invitation désactivée/expirée/consommée, email et identifiants historiques,
mise à niveau scrypt, mauvais mot de passe, récupération générique, reset expiré/non réutilisable,
révocation et expiration des sessions, CSRF absent/faux/lié à une autre session, isolation des
comptes et documents, suppression, vecteurs filtrés par propriétaire, comparaisons interdites,
BYOK, budgets concurrents et imports concurrents soumis au quota. La suppression des embeddings
est testée avec de vrais vecteurs simulés, et la réindexation fonctionne après le nettoyage sans
effacer les écritures de consommation.

Les 14 scénarios Playwright ont été validés en deux passages : 10 parcours de pages/documents,
puis les quatre cas BYOK/RAG corrigés pour attendre la nouvelle navigation après connexion.
Les PDF/TXT, analyses, graphiques, clavier, écrans mobiles/tablette, sessions et clé éphémère
sont vérifiés dans les conteneurs réels. Aucun bouton de validation OpenAI ni génération confirmé.
Les comptes/documents de test sont retirés ; les données de l’utilisateur restent intactes.

Problèmes de validation résolus : permissions Windows du répertoire temporaire global de pytest
(répertoire dédié au projet), contrôle du nom `sha256` dans le manifeste de restauration, et
polling accéléré des tests qui atteignait le limiteur réel. Un test spécifique conserve la
vérification du plafond utilisateur effectif. Avertissement connu : dépréciation Starlette du
transport httpx du TestClient, sans échec de test.

## Sécurité vérifiée et limites

Accès documentaire du BFF fermé sans session ; nouvelle clé interne distincte ; droits toujours
calculés depuis le compte/les UUID serveur ; aucune attribution client. Cookies sécurisés et
CSRF signé ; CSP et origine vérifiées ; Argon2id, mémoire/concurrence de dérivation bornées ;
limitations IP/utilisateur et quotas atomiques ; stockage privé et extraction bornée conservés.
Les secrets, textes, prompts et réponses confidentielles ne sont pas journalisés. Les tests
utilisent des fournisseurs injectés et un expéditeur mail simulé.

Restent volontaires pour le MVP : un seul processus API et un seul BFF, sessions/limiteurs en RAM,
pas de MFA ni SSO, email SMTP à configurer, email historique vérifié administrativement,
espaces partagés désactivés, suppression des comptes traitée par l’administrateur. Les budgets
sont estimatifs ; une demande déjà envoyée au fournisseur peut finir après révocation.

Les limites de fichiers ne remplacent pas un antivirus ou une sandbox de production ; il n’y a
pas d’analyse antivirus ajoutée. Les volumes Docker exigent quotas/alertes disque externes. La
rétention, le chiffrement des sauvegardes hors machine et la réapplication des demandes d’effacement
après restauration restent à organiser avant SaaS. Aucune conformité RGPD garantie.

## Validation manuelle

1. Recharger `https://localhost:8443/login` avec Ctrl+F5, se connecter avec le compte existant.
2. Vérifier les documents personnels, importer un TXT/PDF, lancer l’analyse classique puis supprimer
   uniquement le document de test. Ne pas confirmer d’appel IA pour ce contrôle gratuit.
3. Ouvrir Profil, Sécurité, Paramètres IA et Confidentialité ; vérifier clavier et petit écran.
4. Ouvrir un navigateur privé : la bibliothèque ne doit pas être accessible sans connexion.
5. Créer une invitation administrative pour un compte de test après activation volontaire du mode
   `invite` ; vérifier que ses documents sont isolés. Ne pas rattacher un propriétaire historique
   sans vérification administrative et sauvegarde.
6. Configurer un expéditeur SMTP de test autorisé pour vérifier le parcours réel de récupération.
   Sans SMTP, le message reste générique et aucun email ne part.
7. Tester la révocation d’une seconde session et la disparition de sa clé BYOK. Ne jamais utiliser
   un vrai secret OpenAI pour un test qui n’a pas besoin du fournisseur.
8. Sur un compte de test seulement, demander la suppression puis utiliser la purge administrative.
   Vérifier l’absence des contenus et la conservation de la comptabilité sans texte.

## Avant toute production

Voir [le guide d’exploitation](sprint-5-accounts.md) : secrets distincts, domaine/certificat,
réseau/serveur, stockage chiffré, SMTP, quotas disque, sauvegardes chiffrées hors machine et
rotation, supervision, tests de charge, audit indépendant, gestion d’incidents et validation
juridique/organisationnelle de la politique de confidentialité. Le Compose fourni reste lié à
la boucle locale ; aucune publication n’a été effectuée.
