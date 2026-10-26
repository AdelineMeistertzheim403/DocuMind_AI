# Sprint 14.5 — UX, vérification email et protections anti-abus

Date : 25 octobre 2026. Branche locale : `preparation/sprint-14-5-ux-email-abuse`.
Base : `8243e0511c5505a9cc70f76ad02392f7a816590d`, avec les travaux non commités
des phases 14.2 à 14.4 conservés. Les rapports 14.1 à 14.4 ont été relus.

**Aucune ouverture publique, publication, opération VPS ou activation IA.**
Ce dossier distingue les preuves locales des décisions d'exploitation 14.6/14.7.
La production Sprint 13 n'a pas été modifiée. Aucune migration nouvelle.

## 1. Architecture et interfaces

Parcours conservé : React → HTTPS → proxy → BFF Express → FastAPI → PostgreSQL.
Le BFF garde son identité technique dédiée ; le compte utilisateur garde sa session
serveur. Les écritures passent par CSRF, Host/Origin et transport sécurisé. L'API
reste autoritaire pour l'admission, la vérification, le quota et les droits documentaires.

Les routes `/register`, `/verify-email`, `/resend-verification`, `/login`,
`/forgot-password`, `/reset-password` et `/legal` utilisent `AccountAccess` et
`PublicInformationPage`. Le renvoi conserve mot de passe, challenge et limites ;
il reste possible lorsque les nouvelles inscriptions sont fermées, pour un compte
en attente non bloqué. La vérification ne crée pas automatiquement de session.
Les anciens comptes, invitations, workspaces et contrôles de propriétaire restent inchangés.

Améliorations locales :

- Cinq **admissions cumulatives**, et consommation d'une place avant vérification,
  annoncées explicitement ; aucune récupération automatique de place promise.
- Réception de demande distinguée d'une admission ou d'un envoi effectif de mail.
  L'interface ne présente pas le HTTP 202 comme une preuve de livraison.
- Renvoi proposé ; seul le dernier lien émis reste valable, les limites s'appliquent
  aussi sur un réseau partagé. Les réponses restent génériques.
- `options()` fournit un état agrégé additionnel `available`, `closed` ou `full`,
  sans compte, adresse ni compteur individuel. Le booléen historique est conservé.
  Ligne absente ou compteur négatif : fermé. Quota positif épuisé : plafond atteint.
- Disponibilité inconnue ou erreur de chargement affichée comme telle, sans prétendre
  que l'exploitante a fermé les inscriptions. Bouton fermé par défaut.
- Lien invalide/expiré/rejoué ou vérification incorrecte : aide commune pour demander
  un nouveau lien, sans révéler l'existence d'un compte.
- IA annoncée pour ultérieurement ; accès classique des comptes vérifiés préservé.
  Le formulaire annonce son état occupé avec `aria-busy` et ses messages via `status`/`alert`.

Une page ouverte peut conserver des options périmées : ce n'est jamais une autorisation
d'admission. Le SQL conditionnel 14.4 reste le contrôle final. Les erreurs 429/503
restent distinctes d'un refus métier générique, sans promesse d'égalité temporelle.

## 2. Audit SMTP et amélioration minimale

| Point confirmé dans le code | Garantie et limite |
| --- | --- |
| `backend/main.py`, `deliver_mail()` | Un consommateur, file RAM bornée à 100, `put_nowait`, pas d'attente SMTP dans le traitement HTTP. |
| Envoi après commit | Un mail perdu ou refusé ne supprime ni compte en attente ni admission ; aucune remise à zéro du compteur. |
| `send_account_link()` | `SMTP_SSL` ou STARTTLS, contexte TLS vérifié, timeout réseau de 10 secondes, authentification après TLS, aucun repli en clair. |
| Échec SMTP | Événement `system.mail.failed` expurgé, `task_done()` en `finally`, passage au prochain message ; aucune reprise automatique illimitée. |
| File pleine à l'inscription/renvoi | Réponse 202 générique ; compte et jeton déjà committés. Un renvoi ultérieur peut rétablir le parcours. |
| File pleine à la récupération | Était silencieuse ; émet désormais le même événement expurgé, sans modifier la réponse publique. |
| Arrêt/redémarrage | Les messages RAM restants ne sont pas durables. L'arrêt demande la terminaison puis attend le thread jusqu'à 12 secondes ; il ne garantit pas de vider la file. |

Le timeout SMTP est **par opération réseau**, pas une borne totale de dix secondes
pour toute la conversation TLS/login/envoi. Une succession d'attentes peut dépasser
les douze secondes du join. Aucun drainage durable, retry garanti ou remise en file
après crash n'est revendiqué. La perte brutale de processus n'est pas injectée dans
la recette ; cette limite est confirmée par le cycle de vie en mémoire.

Pas de nouvelle infrastructure de messagerie, dépendance ou stockage de token brut.
Pour cinq admissions, la proposition est de conserver le mécanisme borné, le renvoi
protégé et l'information honnête, avec surveillance préalable du SMTP et des échecs.
L'exploitante doit accepter explicitement le risque de place consommée sans mail
avant ouverture. Une file durable exigerait une étude séparée : chiffrement des
destinataires/liens, contrôle d'accès, expiration, invalidation et effacement des
copies, idempotence, migrations, sauvegardes et exploitation. Elle n'est pas implémentée.

Le reset possède des limites IP/adresse propres, mais pas de limite globale dédiée
comparable aux dix créations/renvois par minute. Sa file est partagée avec la
vérification : des demandes distribuées sur des adresses éligibles peuvent la
saturer. Le nouveau signal d'échec améliore l'observation, pas cette capacité.
Mesurer ce cas en recette locale 14.6 et décider d'un plafond global/séparation de
files si nécessaire ; ne pas déduire une résistance DDoS de cette bêta à cinq places.

Le renvoi invalide les liens précédents avant d'émettre le nouveau jeton ; un ancien
mail arrivé tardivement peut donc contenir un lien inutilisable. Le TTL de vérification
reste 3 600 secondes par défaut, celui du reset 900 secondes, avec consommation atomique
et usage unique. Un blocage administratif n'est levé ni par renvoi ni par vérification.

## 3. Preuves email/TLS locales

`tests/fake_smtp.py` fournit un serveur **loopback uniquement**, sans relais ni
destinataire externe. Un certificat et une clé de test éphémères sont générés avec
OpenSSL dans le répertoire temporaire ; aucun certificat privé n'est versionné.
Le serveur capture le message en mémoire et ne conserve que les noms de commandes,
jamais les charges AUTH dans son historique technique.

Les tests exercent réellement `smtplib` et la négociation TLS :

- Vérification et récupération en TLS direct et STARTTLS, destinataire fictif et
  lien dans le fragment attendu ; authentification après établissement TLS.
- Certificat non approuvé refusé dans les deux modes ; aucun AUTH ou DATA envoyé.
- Refus SMTP 451 injecté dans la chaîne HTTP complète, puis renvoi réussi.
- Exception du consommateur contenant des sentinelles sensibles : événement expurgé,
  traitement suivant disponible et vérification réussie après renvoi.
- Saturation simulée au point producteur `put_nowait`, puis récupération. La file
  consommateur reste intacte ; ce n'est pas une charge de cent mails simultanés.
- Saturation du reset : événement désormais présent ; réponses publiques génériques.

Une première exécution des nouveaux tests a donné 13 réussites et 2 échecs de harnais :
`capsys` ne capturait pas le writer SEC10-04, qui utilise `os.write` asynchrone. Les
assertions utilisent désormais le collecteur de records existant, sans modifier le
logger ni relâcher ses contrôles. Les 15 tests passent ensuite.

## 4. Preuve de travail et limites

Les nouveaux scénarios anti-abus remettent les **paramètres de fixture** aux défauts
réels : difficulté 12, trois demandes/heure par IP et par email, plafond cinq.
Les scénarios de quota/concurrence 14.4 gardent leurs fixtures explicitement distinctes.
Aucun paramètre de production n'est augmenté pour faire réussir cinq inscriptions
depuis une même IP.

| Scénario exécuté | Vérification |
| --- | --- |
| Quatre demandes, même IP, emails fictifs distincts | Trois 202 et un 429 ; trois admissions, pas cinq. |
| Même adresse, quatre IP de test authentifiées par la passerelle | Trois 202 et un 429 ; un seul compte et une seule admission. |
| Onze demandes multi-IP/email avec preuves invalides | Dix 202 génériques et un 429 global ; aucun compte. |
| Honeypot puis rejeu du nonce corrigé | Même 202 générique, aucun compte : nonce déjà consommé. |
| WebCrypto React | Vrai calcul SHA-256 à difficulté 12, vérifié indépendamment ; pas de mock du calcul. |
| Chromium ordinateur et mobile simulé | Vraie preuve 12 pendant chacun des deux parcours HTTPS complets. |

Les tests publics existants couvrent aussi expiration de challenge, liaison IP,
réutilisation, capacité mémoire, consentement et entrées invalides. Ils sont relancés.
La preuve navigateur reste bornée à vingt secondes et au nombre d'essais existant,
avec restitution périodique de la main. Aucun changement d'algorithme ni de timeout.

Autres limites conservées : challenge cinq/minute/IP et soixante/minute global,
magasin RAM 1 024, création dix/minute globale et sémaphore 1, vérification dix/minute/IP.
Les valeurs configurables et limites de mots de passe/JSON/upload restent inchangées.
Les limiteurs et sessions restent locaux au processus : aucun scaling n'est autorisé.

**NAT :** trois demandes de création/renvoi partagent la limite horaire de l'IP.
Cinq personnes d'un même réseau ne peuvent pas toutes s'inscrire en une heure.
Un abus ciblé peut aussi épuiser la limite d'une adresse. Ne pas lever ces limites
en production pour une démonstration ; prévoir information/support sans identifier
publiquement les comptes. La PoW ne prouve pas l'humanité et cinq adresses contrôlées
peuvent consommer les cinq admissions.

L'émulation iPhone 13 utilise Chromium sur Windows, pas Safari ni un téléphone réel.
Les limites de vingt secondes ne sont pas certifiées sur du matériel mobile lent.
Aucun test de saturation contre un service public n'est réalisé.

## 5. Consentement, confidentialité et accessibilité

Tests React : labels email/mot de passe, minimum de longueur, consentement requis
et **non précoché**, envoi de la version des conditions et du booléen explicite,
liens HTTPS seulement, absence de demande d'invitation en mode public, liens de
récupération persistants lorsque la capacité est fermée. Le backend refuse une
ancienne version ou un consentement absent ; les compteurs ne changent pas.

Les tokens restent dans le fragment initial, nettoyé immédiatement par l'UI, puis
en mémoire ; aucune vérification par simple ouverture automatique du lien. Aucun
stockage local/sessionStorage. Le mot de passe est effacé du champ lors de la
soumission. Les cookies de session restent Secure, HttpOnly et SameSite Strict.

Les logs sont testés avec les records SEC10-04 et le flux technique du BFF : pas de
token, mot de passe, clé BFF ni adresse fictive dans ces preuves. Ce contrôle ne
certifie pas les journaux Traefik/SMTP réellement configurés sur le VPS.

La page `/legal` existe mais renvoie vers les URLs configurées de mentions, conditions
et confidentialité. **Les textes juridiques réels, leur publication, leur contenu et
leur approbation ne sont pas vérifiés.** Les coordonnées `.test` servent exclusivement
aux tests. Aucun numéro d'entreprise, donnée d'exploitante ou texte réglementaire
n'est inventé. `PUBLIC_LEGAL_READY` n'est qu'une attestation de configuration.

Les tests sémantiques et la recette mobile ne constituent pas un audit WCAG complet
ni une validation lecteur d'écran/clavier, contraste ou zoom à 200 %. Ces contrôles
et la revue juridique de l'exploitante restent nécessaires avant ouverture.

## 6. Chaîne complète réellement exécutée

Deux parcours Chromium, ordinateur et iPhone 13 simulé :

1. React construit par Vite, formulaire réel, consentement et PoW 12.
2. Proxy HTTPS loopback de recette → **vrai BFF**, CSRF et identité technique dédiée.
3. **Vraie API FastAPI** → PostgreSQL 17.11 / pgvector 0.8.7 neuf.
4. File et worker réels → **faux serveur SMTP via STARTTLS réel** ; capture du mail.
5. Extraction du jeton du mail capturé, vérification via formulaire avec mot de passe.
6. Connexion via formulaire, cookie sécurisé, tableau de bord accessible.
7. Dans cette même session navigateur, import TXT via HTTP multipart et analyse 201.
8. Connexion d'une clé IA fictive refusée 403 ; aucun vrai client OpenAI permis.

Six autres scénarios parcourent réellement HTTPS/BFF/API/PG et le SMTP quand un
envoi est prévu : verrou fermé, quota déjà épuisé, doublon, expiration puis renvoi,
panne SMTP puis renvoi, file pleine simulée puis renvoi. Les vieux liens et replays
sont refusés, le compteur n'augmente pas au renvoi. Les états de quota sont préparés
uniquement dans les bases fictives, sans reset métier.

Le test vérifie aussi les refus CSRF absent et Origin hostile, les healthchecks,
ainsi que les attributs du cookie. Le proxy de test remplace les en-têtes de transfert
et le BFF n'accorde sa confiance qu'à l'IP loopback explicitement autorisée.

TLS de recette : contexte Python approuvant uniquement le certificat temporaire ;
Chromium accepte son SPKI explicitement épinglé. Pas de désactivation globale de la
validation TLS ni d'option `ignoreHTTPSErrors` pour ces parcours. Les requêtes du
navigateur vers d'autres origines sont bloquées. Le faux SMTP ne relaie jamais.

**Portée :** applications API/BFF/proxy exécutées localement sur Windows ; seul PG
est dans Docker. Le proxy de recette est Node HTTPS, **pas Traefik**. Les tests
applicatifs réutilisent le mode d'extraction portable explicite des fixtures Windows ;
ils ne recertifient pas Landlock/seccomp ni les images Linux de production.
Le confinement et la configuration de production n'ont pas été modifiés. Une stack
Docker complète proche production, avec sandbox obligatoire et vrai Traefik, relève
encore de 14.6. Ce rapport ne confond pas ces preuves avec cette recette restante.

## 7. Campagnes et commandes

| Campagne terminée | Réussis | Ignorés | Échoués |
| --- | --- | --- | --- |
| Windows, tests SMTP/TLS/anti-abus/disponibilité ciblés | 15 | 0 | 0 |
| Windows Python 3.13.7, suite complète finale | 710 | 64 | 0 |
| Deux parcours Chromium complets, première recette | 2 | 0 | 0 |
| PostgreSQL, huit E2E + SMTP/anti-abus + régressions 14.2–14.4 | 231 | 6 | 0 |
| WSL Python 3.12.3, SMTP/anti-abus/public/identité/IA/inventaire | 74 | 6 | 0 |
| React/Vitest, suite complète | 52 | 0 | 0 |
| Node/BFF, suite complète | 50 | 0 | 0 |

Les sélections se recouvrent : ne pas additionner ces totaux comme des tests distincts.
La campagne PostgreSQL dure 216,08 s ; celle WSL 212,72 s. Les six ignorés des deux
sélections sont les quatre restaurations Docker et deux altérations réelles de
snapshot sans `TEST_SNAPSHOT_COMPOSE` ; ils ne sont pas attribués à cette phase.
Le rapport 14.4 conserve leurs preuves d'exécution précédentes (13 tests du fichier,
dont les six opérations Docker), non relancées ici. Les neuf tests de concurrence PG
et le verrou PG 14.2 sont bien exécutés dans la campagne PostgreSQL.

`npm run build` réussit (TypeScript et Vite), ainsi que les analyses AST Python,
`node --check` des deux helpers et `git diff --check`. L'avertissement préexistant
Starlette/httpx reste visible. Le premier lancement Vitest sous sandbox a échoué
avant chargement en lecture de répertoire (`Access is denied`) ; l'exécution locale
autorisée réussit sans changement de dépendance ou de configuration de sécurité.

La suite complète Windows dure 706,88 s. Ses 64 ignorés sont les 40 cas natifs Linux,
les dix cas spécifiques PostgreSQL (verrou 14.2 et neuf courses 14.4), les six tests
Docker de snapshot et les huit E2E opt-in. Ces huit E2E et les dix cas PG passent
réellement dans la campagne PostgreSQL ci-dessus. Les suites complètes Linux/PG et
les tests natifs du sandbox ne sont pas revendiqués à partir de ces sélections.

Commandes principales, lancées depuis le dépôt sauf `npm` depuis `frontend` :

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_public_beta_email_abuse.py -q -p no:cacheprovider --basetemp=var/pytest-14-5-email-second --tb=short
npm.cmd run test:ui
npm.cmd run test:bff
npm.cmd run build
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp=var/pytest-14-5-windows-full --tb=short
```

Recette opt-in, exclusivement après création d'une **base PostgreSQL vide dédiée**,
build frontend et présence locale de Node, OpenSSL et Chromium Playwright :

```powershell
# Fournir uniquement l'URL loopback de cette nouvelle base jetable dans TEST_DATABASE_URL.
$env:TEST_PUBLIC_BETA_E2E='1'
try {
  .\.venv\Scripts\python.exe -m pytest tests/test_public_beta_email_e2e.py -q -p no:cacheprovider --basetemp=var/pytest-14-5-recipe-NEW --tb=short
} finally {
  Remove-Item Env:TEST_PUBLIC_BETA_E2E -ErrorAction SilentlyContinue
}
```

Sans opt-in, les huit tests E2E sont explicitement ignorés, jamais présentés comme
passés. Avec opt-in, une absence de build, navigateur, Node ou PG ne devient pas un
succès silencieux. Les tests TLS ignorent explicitement la génération si OpenSSL
n'est pas disponible ; il l'était sur les deux environnements testés ici.

La campagne PostgreSQL exécutée utilise cette sélection, avec les deux variables
de test définies exclusivement dans son processus puis retirées en `finally` :

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_public_beta_email_e2e.py tests/test_public_beta_email_abuse.py tests/test_public_beta_postgresql_concurrency.py tests/test_public_beta_state.py tests/test_public_beta.py tests/test_public_beta_authorization.py tests/test_ai_disabled_enforcement.py tests/test_deployment.py tests/test_public_beta_snapshot.py -q -p no:cacheprovider --basetemp=var/pytest-14-5-pg-final --tb=short
```

Sous WSL, depuis le dépôt monté, le venv local existant est réutilisé sans installation :

```bash
env -u TEST_DATABASE_URL -u TEST_PUBLIC_BETA_E2E -u TEST_SNAPSHOT_COMPOSE \
  /var/tmp/documind-s13-a7b75801/.venv/bin/python -m pytest \
  tests/test_public_beta_email_abuse.py tests/test_public_beta.py \
  tests/test_public_beta_state.py tests/test_ai_disabled_enforcement.py \
  tests/test_public_beta_snapshot.py -q -p no:cacheprovider \
  --basetemp=/tmp/documind-s14-5-linux-20261025 --tb=short
```

Le PostgreSQL créé pour cette mission utilise le pipe Docker Desktop local explicite,
image locale `documind-postgres-vector:17`, `--pull never`, réseau neuf sans masquerading,
port loopback éphémère, tmpfs neuf, utilisateur 70:70, capacités supprimées,
`no-new-privileges`, mémoire 768 Mio, deux CPU et 96 processus. Aucun réseau/volume
existant, socket Docker monté ou image téléchargée. Les fixtures refusent une base
non vide à l'entrée ; leur destruction de données fictives ne change aucun compteur
de production, de sauvegarde ou de restauration.

Le conteneur `s14-5-email-pg-6f9b` et le réseau `s14-5-email-6f9b` ont été arrêtés
puis supprimés après contrôle de leurs labels `documind.test=sprint-14-5` et de
l'absence de montage persistant. Les filtres sur ce label ne retournent plus de
conteneur ni réseau. Les processus API/BFF/proxy/Chromium de recette sont terminés.
Les artefacts fictifs restent sous `var/`, ignoré par Git ; aucun fichier existant
n'est supprimé pour nettoyer le projet.

## 8. Fichiers de ce lot et préservation

| Fichier | Modification 14.5 |
| --- | --- |
| `backend/account_api.py` | Disponibilité agrégée additionnelle et événement expurgé de file reset pleine. |
| `frontend/src/services/account.ts` | Type optionnel de disponibilité ; compatibilité du booléen antérieur. |
| `frontend/src/pages/Account.tsx` | Messages, disponibilité, renvoi, erreur de lien, accessibilité et information IA. |
| `frontend/src/pages/PublicBeta.test.tsx` | Consentement non précoché et quatre nouveaux scénarios UX. |
| `frontend/src/services/registration.test.ts` | Calcul WebCrypto réel difficulté 12. |
| `tests/fake_smtp.py` | Serveur SMTP/TLS local sans relais, certificat temporaire. |
| `tests/test_public_beta_email_abuse.py` | Quinze cas SMTP, anti-abus, disponibilité et non-fuite. |
| `tests/test_public_beta_email_e2e.py` | Huit cas opt-in HTTPS/PG/SMTP, dont deux vrais navigateurs. |
| `tests/fixtures/public_beta_gateway.mjs` | BFF réel et proxy TLS loopback de test, sans lecture du `.env`. |
| `tests/fixtures/public_beta_browser.mjs` | Parcours réel navigateur ordinateur/mobile, sans mocks HTTP. |
| Ce rapport | Preuves, limites, préparation 14.6 et verdict. |

Les 37 fichiers déjà modifiés/non suivis ont été relevés par SHA-256 en début de lot.
**36 restent identiques** ; seul `backend/account_api.py` est étendu comme décrit,
en préservant ses protections 14.4 de blocage/récupération et compteur non négatif.
Les fichiers des sauvegardes, restauration, verrou de maintenance, simulation de
conservation, autorisation de déploiement, quotas et gardes IA restent inchangés.
Pas de modification de migration, workflow, Compose, Dockerfile, secret ou politique
Landlock/seccomp. Les artefacts et certificats de tests restent hors suivi Git.

## 9. Préparation 14.6 et limites avant ouverture

Opérations proposées, **non autorisées et non exécutées ici** :

1. Valider les textes légaux publiés, leur version et accessibilité, coordonnées et
   politique de conservation/effacement ; aucune donnée fictive dans l'information réelle.
2. Après autorisation explicite, tester le SMTP réel avec une boîte de recette
   maîtrisée : chaîne TLS vérifiée, authentification, From, SPF/DKIM/DMARC, réception,
   indésirables et délai ; lien sur le bon domaine, pas de jeton dans des logs publics.
   Ne pas attribuer cette délivrabilité à la réussite du faux SMTP.
3. Tester en Docker jetable proche production : images candidates, réseau fermé,
   PG neuf, faux SMTP, TLS local, BFF seul derrière Traefik, compte/document fictifs,
   Landlock ABI ≥3 et seccomp obligatoires. Aucun accès à des volumes réels.
4. Vérifier localement puis selon autorisations futures les alertes mail, la capacité,
   les limites NAT, le contrôle des journaux et la procédure de renvoi après restart.
   Accepter explicitement la perte possible d'un mail RAM et la place cumulative consommée.
5. Revalider restauration indépendante et quota/verrou, fermeture d'urgence sans reset,
   rollback applicatif incluant les correctifs 14.4, et CI de la version candidate.
   Un code ancien compatible `0007` n'est pas automatiquement un rollback sûr.
6. Relever les flags IA/demo/legacy fermés, cinq admissions cumulatives et verrou fermé
   avant toute préparation de livraison. Déploiement public préparé et réouverture SQL
   restent deux décisions séparées ; rien ici ne réouvre le verrou.

Le protocole actuel ne certifie ni charge distribuée, appareil mobile réel, toutes
les analyses temporelles anti-énumération, réseau Traefik du VPS, ni remise des mails
par un fournisseur externe. Les retours 202 génériques et les erreurs bornées sont
préservés sans prétendre résoudre tous ces risques.

## 10. Verdict

**Go technique pour la revue locale du lot 14.5 et la préparation de 14.6.**
Les messages et états sont clarifiés, la saturation du reset est observable,
les échanges SMTP/TLS et les deux parcours navigateur complets sont démontrés,
les protections par défaut et les régressions ciblées PG/Linux passent, ainsi que
la suite complète Windows, React, BFF et le build. `git diff --check` est sans erreur.

Ce Go n'est ni une acceptation définitive du risque de file RAM ni une certification
de production : délivrabilité réelle, textes légaux, matériel mobile, capacité,
restauration et stack Docker/Traefik/sandbox complète restent à traiter ou approuver
en 14.6. Aucun fichier n'a été indexé ou commité ; aucun push, merge, déploiement,
accès VPS, email externe, appel IA réel ou changement de secret n'a été réalisé.
**L'ouverture publique reste interdite jusqu'aux validations distinctes 14.6 et 14.7.**
