# Docnelo V5.1 — Première campagne fonctionnelle de quarantaine in-process

1 novembre 2026. **GO limité à cette campagne fonctionnelle locale exécutée.**
**NO-GO Public Beta, production, S2 et Lifecycle 10 maintenu.**

Ce GO signifie que les assertions de la campagne ci-dessous ont réussi dans
l'environnement décrit. Il ne valide ni une image Docker ni son attachement
au latch restauré, ni la qualification complète de la quarantaine opérationnelle.

## 1. Livrables et périmètre

Fichiers ajoutés :

- `tests\test_recovery_quarantine_inprocess.py` : harness et 42 cas.
- `qualification\quarantine_inprocess\pytest.ini` : profil autonome.
- Le présent rapport.

Aucun code backend, middleware, composant Backup/Restore ou garde n'est modifié.
Les neuf empreintes du rapport de durcissement ont été recontrôlées conformes.
Les releases scellées V5 et V5.1 ont chacune leurs **18/18 entrées inchangées**.
Aucune migration, sauvegarde, restauration, ouverture de port, connexion
PostgreSQL/SMTP/IA, exécution Uvicorn/Docker ou accès VPS n'a été effectué.
Seuls des fichiers temporaires synthétiques et les nouveaux livrables sont créés.

L'audit de référence est `DOCNELO_V51_APPLICATION_QUARANTINE_AUDIT.md`.
Les résultats de laboratoire antérieurs restent distincts : aucun résultat
PostgreSQL, Linux ou round-trip n'est réattribué à cette campagne.

## 2. Méthode d'isolation

### Avant l'import de l'application globale

Le profil utilise `--noconftest` ; les plugins tiers automatiques sont désactivés
par `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` dans la commande d'exécution.
Ni la fixture globale app, ni Alembic, ni TEST_DATABASE_URL ne sont utilisés.
Le module de test refuse explicitement la présence préalable du conftest
global ; le harness refuse un backend.main déjà importé.

Avant le premier import de backend.main :

- Environnement du processus temporairement vidé, restauré après chaque cas.
- Settings synthétiques, sources Pydantic limitées aux arguments init ;
  aucune lecture dotenv ou variable de configuration hôte.
- Factories engine, sessions et authentication_engine remplacées par objets
  factices sans connexion ; toute entrée connect/begin/execute/session échoue.
- Connexions Psycopg/SQLite, clients SMTP/OpenAI, commandes Alembic et Popen
  interdits. Les sockets et le démarrage de vrais threads sont interdits.
- Worker de résumé remplacé avant la création de l'application globale ;
  récupération des jobs et mail remplacés par espions/sentinelles.
- Journalisation de sécurité observée en mémoire, sans thread de sortie.

Les refus d'isolation sont enregistrés puis vérifiés en fin de cas, même
si un handler applicatif devait intercepter une exception. Ils ne deviennent
pas des tests ignorés. Les erreurs d'import ou de dépendance font échouer
la campagne.

L'introspection `platform.machine()` est synthétique : SQLAlchemy peut sinon
appeler un shell Windows pour obtenir cette métadonnée. Ce remplacement
ne touche aucune décision de quarantaine ou de sécurité.

### Transport, boucle et absence d'exposition

Les requêtes sont envoyées via `httpx.ASGITransport` directement à la vraie
application FastAPI et à ses middlewares inchangés. Le nom inprocess.invalid
est un identifiant de transport ASGI, jamais résolu ou contacté.

Une boucle événementielle de test mono-thread utilise un sélecteur qui refuse
tout descripteur d'I/O ; elle ne crée pas le self-pipe socket habituel.
Les appels cross-thread sont interdits. Les synchronisations du scénario
en cours d'exécution utilisent uniquement des événements asyncio en mémoire.
Aucun serveur HTTP ni port d'écoute n'est créé, même pour le contrôle positif.

Seuls les mécanismes d'arrière-plan du lifespan sont isolés :
to_thread exécute directement les espions, Thread.start observe sans lancer
le corps, et la tâche d'expiration est observée puis fermée sans exécution.
Cela teste les décisions de démarrage, pas les vraies boucles de worker.

### Preuve d'absence d'effets métier

Pour les matrices de refus, une sentinelle est placée **en aval de tous les
middlewares**, à l'entrée du routeur. Si une requête fermée y parvient,
le test échoue ; aucune dépendance ou endpoint n'est substitué à une garde.
Les mêmes middlewares sont contrôlés positivement avec une destination
inoffensive quand le latch est ready.

Une AsyncByteStream espionne la consommation du corps : aucun refus testé
ne lit le corps. Les sentinelles DB/auth/document/job/email restent inutilisées.
En démarrage fermé, aucune récupération de job, lancement worker/mail ou
planification d'expiration n'est observée ; le dossier documentaire n'est
pas créé et la file de mail reste vide.

Il s'agit d'une preuve de non-entrée dans les effets métier sur ces requêtes,
pas d'une exécution de ces opérations ni d'une preuve d'annulation d'un commit.

## 3. Scénarios et résultats exécutés

**Résultat final : 42 réussites, 0 échec, 0 erreur, 0 ignoré ; 5,14 s.**
JUnit : 42 cas, 0 skipped ; durée enregistrée 5,097 s.
Début JUnit : `2026-11-01T20:35:37.011249+01:00`.

| Groupe | Cas | Résultat et assertions |
|---|---:|---|
| Refus au démarrage | 24 | 12 états × sans headers / identité gateway synthétique valide ; 503 sur toutes les routes, zéro corps consommé et zéro entrée métier |
| Refus à chaud après démarrage ready | 12 | Même matrice de latch ; readiness initiale réellement acquise puis nouvelles requêtes 503 sans effets métier |
| Frontière Lite | 1 | Six requêtes : 403 pour IA/recherche/vérification email avant quarantaine ; 503 pour health/inscription/compte |
| Transitions et workers | 2 | Départ quarantined puis ready reste fermé ; départ ready puis quarantined puis ready ferme puis rouvre ; contrôle positif des espions worker |
| Chemin effectif | 1 | Startup et middleware ouvrent le chemin des Settings, pas le fichier ready leurre indiqué par l'environnement |
| Contrôle positif du downstream | 1 | Ready transmet réellement au downstream inoffensif, réponse 204 et un appel observé |
| Requête déjà engagée | 1 | Première requête suspendue après admission ; seconde refusée 503 après quarantaine ; première termine 200 une fois libérée |

### Matrice des douze états

`quarantined`, fichier absent, PermissionError simulée, JSON invalide,
UTF-8 invalide, clé state dupliquée, champ supplémentaire, format booléen,
état inconnu, fichier supérieur à 1 024 octets, répertoire au lieu du fichier,
chemin non configuré.

L'illisibilité est simulée au niveau de l'ouverture du fichier exact, pour
être discriminante même sous root ; ce n'est pas une qualification des
permissions POSIX de la VM.

### Routes couvertes

L'inventaire dynamique couvre **59 couples route/méthode** par scénario de
la matrice, incluant la documentation FastAPI. Les six modules de routeurs
réellement inclus sont vérifiés :

| Module | Surface |
|---|---|
| backend.api | Santé, préflight interne, documents, téléchargement, analyse, suppression |
| backend.account_api | Inscription/email/reset, comptes/sessions et mutations de compte |
| backend.ai.settings_api | Login/logout, préférences et BYOK |
| backend.ai.api | Statut, consommation et opérations IA |
| backend.rag.api | Indexation, recherche et comparaison |
| backend.ai.long_api | Plans, jobs, reprise et annulation |

Les routes documentaires à identifiants utilisent des UUID synthétiques.
Toutes les méthodes déclarées sont parcourues ; pour HEAD, le 503 est vérifié
avec un corps vide conformément au transport HTTPX, pas avec une attente JSON.
OPTIONS documents, chemin inconnu et `/api/v1/admin` sont ajoutés à la matrice
de démarrage : ce sont des requêtes fermées, pas des endpoints inventés.

**Administration :** aucun routeur issu de backend.account_admin n'est
enregistré. Le chemin `/api/v1/admin` testé ne prouve donc pas un contrôle
des CLI administratives. Ces programmes restent hors périmètre HTTP.
Les routes account réellement enregistrées sont couvertes.

La collecte prend en charge les routeurs inclus différés de FastAPI 0.146.0
via leurs candidats effectifs. Toute représentation de route inconnue
provoque un échec explicite, pas une omission silencieuse.

## 4. Résultats qui bornent la garantie

### Transitions

Le test confirme le contrat courant, sans le modifier :

- Démarrage quarantiné : écrire ready ne suffit pas à ouvrir ce processus.
- Démarrage ready : le passage quarantined refuse les nouvelles requêtes.
- Même processus initialement prêt : le retour ready peut les rouvrir.

La troisième assertion n'est pas un durcissement ajouté : elle caractérise
la réversibilité dynamique existante. Si l'opérateur exige une fermeture
irréversible jusqu'à redémarrage/réautorisation, une décision et un correctif
distincts seront nécessaires.

### Workers et contrôle positif

Avec ai_enabled=true dans le profil standard synthétique :
ready déclenche exactement une récupération d'index, une récupération de
résumé, un démarrage du worker résumé, un démarrage mail et une planification
de nettoyage. L'arrêt du worker est observé à la fermeture du lifespan.
Les mêmes branches restent non exécutées en quarantaine initiale.

Les espions ne lancent ni thread mail ni worker IA réel. Les corps de boucle,
les fournisseurs, la livraison SMTP et les vrais jobs ne sont pas qualifiés.
Le profil Lite utilise sa configuration valide sans IA et un adaptateur
Python synthétique explicite ; aucun ledger d'autorité n'est provisionné.

### Traitement déjà engagé

La première requête, admise en ready, reste en cours après changement du latch.
La nouvelle requête est fermée ; la première peut finir une fois libérée.
Le middleware **ne possède pas de capacité d'annulation globale**.
Ce scénario utilise un endpoint async synthétique, pas une transaction SQL,
un vrai téléchargement ou une preuve de quiescence.

## 5. Environnement et reproduction

Exécution locale **Windows / Python 3.13.7**, pas Debian/Python 3.11.

| Dépendance | Version exécutée |
|---|---|
| pytest | 9.1.1 |
| FastAPI | 0.146.0 |
| Starlette | 1.9.0 |
| HTTPX | 0.28.1 |
| SQLAlchemy | 2.0.55 |
| Pydantic | 2.14.1 |
| pydantic-settings | 2.16.0 |

Commande PowerShell exécutée depuis la racine du dépôt :

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
python -m pytest -c qualification\quarantine_inprocess\pytest.ini -q --tb=short -o junit_family=legacy --basetemp '<DOSSIER_TEMPORAIRE_NEUF>' --junitxml '<RESULTATS_TEMPORAIRES.xml>' tests\test_recovery_quarantine_inprocess.py
```

Le dossier temporaire était neuf et contrôlé avant lancement ; ne jamais
réutiliser un chemin contenant des preuves existantes comme basetemp.
Le profil autonome et la désactivation des plugins sont nécessaires.
Une exécution via le profil global est refusée : ne pas retirer cette garde
pour réutiliser les fixtures applicatives.

Les résultats structurés de cette session sont conservés dans
`files\quarantine-inprocess-results.xml` de l'espace de session, sans données
réelles. Les propriétés JUnit indiquent le nombre de routes/méthodes et les
modules couverts. Aucun test ignoré : aucune raison d'exclusion à masquer.

Historique des adaptations du harness, avant la campagne finale :

- 29 erreurs initiales : introspection Windows de SQLAlchemy tentant un
  subprocess, explicitement interdit ; métadonnée plateforme ensuite isolée.
- 29 échecs : représentation différée des routeurs non prise en charge et
  select Windows sans descripteur ; inventaire et boucle sans I/O adaptés.
- 24 échecs : attente JSON sur HEAD malgré corps vide ; assertion HEAD corrigée,
  statut 503 et absence d'effets maintenus.
- Première version validée : 29 réussites. Extension aux défaillances à chaud
  et au contrôle positif downstream : **42 réussites**.

Aucun de ces ajustements n'a changé les gardes backend ou accepté une opération
DB/réseau pour faire passer la campagne. Aucun test refusé n'a été ignoré.

## 6. Limites et prochaines preuves nécessaires

| Limite | Étape distincte requise |
|---|---|
| Image Docker réellement utilisée | Identifier image/modules/Settings et comparer à la révision testée |
| Chemin du latch restauré monté dans le conteneur | Vérifier le bind effectif et la propagation des changements/remplacements d'inode en laboratoire autorisé |
| Runtime Debian/Python 3.11 | Rejouer la campagne autonome, sans extrapoler le résultat Windows |
| Ownership, chmod, symlinks et parent symlink | Compléter les tests de lecteur sur POSIX ; PermissionError simulée ne qualifie pas ces profils |
| serving_closed et preuve de release | Pas de startup/gate cryptographique/SQL exécuté ; campagne distincte nécessaire |
| Workers en vol, mail, téléchargement/SQL en cours | Leur annulation/arrêt n'est pas garanti ; qualification spécifique ou contrat de quiescence |
| Autorité Lite avant lifespan | L'adaptateur est synthétique ; ses éventuelles écritures d'initialisation ne sont pas qualifiées |
| Frontend/BFF et CLI administration | Non testés ici ; un refus backend ne ferme pas nécessairement le shell Web ou un outil local |
| Sessions valides de comptes restaurés | Aucun login réel ni session DB vérifiée ; identité gateway synthétique et non-entrée dans auth suffisent seulement au contrat du refus |
| Backup/Restore complet, HMAC/fraîcheur, S2 | Non qualifiés par des requêtes in-process |

**Aucun correctif backend nécessaire n'a été établi pour le refus des nouvelles
requêtes dans les scénarios exécutés.** Les décisions sur irréversibilité,
arrêt des traitements en cours et initialisations Lite restent celles de
l'audit statique ; elles ne sont ni implémentées ni éludées par ce GO de campagne.

## 7. Décision

**GO pour cette première campagne de tests fonctionnels in-process seulement :
42/42 cas exécutés réussis, aucune exclusion.**

**NO-GO pour déclarer la quarantaine opérationnelle intégralement qualifiée.**
La liaison à l'image, au véritable fichier restauré et au runtime Debian
doit être démontrée séparément. Aucune admission, ouverture de Public Beta,
autorisation S2 ou Lifecycle 10 n'est accordée.
