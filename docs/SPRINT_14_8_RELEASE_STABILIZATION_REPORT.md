# Sprint 14.8 — Stabilisation de la release candidate privée

26 octobre 2026. Branche `preparation/sprint-14-review`, HEAD de départ
`f3c92eb8ba2bb69b83a9798ebc3df8a70f48fbb2`. **Modifications locales non commitées** :
la CI verte de la PR Draft nº 6 sur f3c92eb8 ne valide pas encore cette révision.

Références lues intégralement :
[14.7.11](SPRINT_14_7_11_PRODUCTION_IMAGE_QUALIFICATION_REPORT.md),
[14.7.10](SPRINT_14_7_10_BUILD_MATERIALS_QUALIFICATION_REPORT.md),
[14.7.9](SPRINT_14_7_9_PREMERGE_RISK_REVIEW.md),
[runbook](SPRINT_14_7_PUBLIC_BETA_OPENING_RUNBOOK.md).

**Verdict : Go technique pour soumettre la correction à revue et préparer une
nouvelle révision de PR, après autorisation commit/push.** Les trois Dockerfiles
réels modifiés construisent avec des matériaux publics identifiés, sans chemin
var ni image de qualification nécessaire au build. Les scénarios affectés passent.
**La fusion/publication reste bloquée** par l'absence d'autorisation, de vraie CI
sur le nouveau SHA et de décisions humaines sur les risques résiduels. Une
reproductibilité OCI bit à bit parfaite n'est pas exigée pour cette RC privée.

## 1. Périmètre retenu et adoption locale

Le lot adopte les contrôles nécessaires des expériences précédentes, sans copier
les centaines d'archives, caches ou scripts privés sous var dans Git. Il ne modifie
ni le code métier, ni les migrations, ni les paramètres de quota, ni les mécanismes
SQL-02, sessions, upload ou Landlock/seccomp.

| Fichier ou groupe | Correction réalisée et contrôle de source |
| --- | --- |
| Dockerfile | Deux bases Python par manifeste amd64 vérifié ; builder dédié, outils et 44 dépendances runtime hachés ; wheel projet construite du contexte revu ; runtime séparé sans outils de build ajoutés. |
| requirements.runtime.lock | 44 versions Linux CPython 3.13/amd64 existantes et SHA-256 des wheels officiellement qualifiés ; aucun sdist ou changement fonctionnel. |
| requirements.build.lock | pip 26.2.1, setuptools 84.2.1, wheel 0.48.0, packaging 26.3, hashes exacts ; fermeture externe du builder expérimenté en 14.7.10. |
| requirements.test.lock | Cinq extras Linux ajoutés au runtime pour le stage isolation-tests ; non installés dans l'image finale. |
| frontend/Dockerfile | Les deux FROM Node sont épinglés au digest qualifié. npm ci, lock/SRI, scripts d'installation et omission des devDependencies runtime sont conservés. Aucun miroir/cache privé exigé. |
| Dockerfile.db | Bases Python de téléchargement et PostgreSQL par digest ; source pgvector exacte, 19 APK de compilation hachés/signés, installation sans réseau/index distant, suppression de la toolchain ; compilation portable. |
| build-materials/pgvector.json | Manifest public revu : commit/source 0.8.7, taille/hash, URL officielle et 19 reçus APK nécessaires au compilateur. Aucun index mutable ou archive binaire ajouté au dépôt. |
| tools/fetch_build_materials.py | Téléchargement stdlib HTTPS des seuls chemins officiels autorisés, sans redirection ; tailles/hashes bornés, refus des doublons et chemins dangereux, contrôle du contenu/version de l'archive, nettoyage des .part et refus d'écraser une sortie existante. |
| .github/workflows/ci.yml | Venv neuf par job Python/Windows, bootstrap haché des outils, installation sans résolution PEP 517 implicite ; identité du builder publiée dans les logs avant login Registry ; disponibilité PostgreSQL vérifiée en TCP. |
| tools/build_materials.py | Les nouveaux locks, manifest et downloader entrent dans les hashes de sources des inventaires runners ; format existant conservé. |
| .gitignore / .dockerignore | .ci-venv et build exclus pour éviter d'ajouter ou d'envoyer les artefacts générés par la préparation CI. Rien n'est supprimé. |
| Tests et README des matériaux | Refus des entrées non revues, intégrité, tar sûr, maintien des versions, contrôle des workflows et procédure de mise à jour. |

Le lock build peut servir sous Windows car ses quatre wheels sont purs Python.
Les locks runtime/test sont **Linux amd64 CPython 3.13**, pas une substitution du
`requirements.lock` multiplateforme. Windows et Linux CI utilisent toujours ce
dernier pour les versions fonctionnelles de `.[test]` et tzdata.

### Sources et faisabilité GitHub Actions

Le build Python utilise explicitement PyPI HTTPS, `--only-binary=:all:` et
`--require-hashes`. La wheel du projet utilise `--no-build-isolation
--check-build-dependencies` **dans le builder dédié verrouillé**, pas dans un venv
applicatif existant. Les jobs CI créent aussi un venv neuf avant cette opération.
Setuptools ne résout donc plus silencieusement un nouvel outil PEP 517 pour ce build.
Les copies vendoriées restent couvertes par le hash de leur wheel parent ; ce
contrôle ne vaut pas audit indépendant de chaque source vendoriée.

npm conserve le lock existant de 368 archives et sa vérification SRI par npm ci.
Les fichiers lock frontend et les versions de dépendances fonctionnelles ne sont
pas modifiés ; aucune mise à jour générale ni désactivation des scripts.

Les APK et l'archive source sont téléchargés depuis Alpine officiel et codeload
du dépôt officiel pgvector, avec les hashes publics du manifest. apk vérifie
ensuite les signatures avec les clés de la base officielle. Installation des
fichiers locaux explicites avec `--network=no --repositories-file /dev/null` :
pas d'index courant indispensable, pas de allow-untrusted. Git et ses onze
dépendances supplémentaires ne sont plus nécessaires à partir de l'archive.

Le fichier existe actuellement sur chaque origine : le Dockerfile réel a réussi
ces téléchargements et la compilation. **Le runner n'a besoin ni de var, ni d'une
image locale préalable, ni d'un wheelhouse privé.** BuildKit est nécessaire pour
les mounts entre stages, déjà utilisé par la CI et vérifié localement. Aucun
frontend Dockerfile tiers supplémentaire n'est demandé.

Si une archive est retirée ou ses octets changent, le build échoue fermé ; pas
d'upgrade/fallback automatique ni de recalcul aveugle d'un hash attendu. Cela
appelle une mise à jour revue des matériaux, pas un workflow intrinsèquement
impossible à exécuter. Une politique de conservation et de maintenance doit être
décidée ; ces versions ne sont pas gelées éternellement sans suivi de sécurité.

### APT et portabilité pgvector : deux corrections ciblées

La base Python par digest fournit déjà libseccomp2 **2.6.0-2**, dont la bibliothèque
a été comparée au deb signé en 14.7.11. Le Dockerfile vérifie sa version au lieu
d'exécuter apt-get update/install sur un index flottant. Une future modification
de base devra requalifier cet invariant ; aucune protection native n'est supprimée.

La source pgvector qualifiée contient par défaut **OPTFLAGS=-march=native** et
documente `make OPTFLAGS=""` pour la portabilité. Les premiers logs du Dockerfile
modifié confirmaient ce flag dépendant du CPU du builder. Les deux make utilisent
désormais **OPTFLAGS="" with_llvm=no**. Version et algorithmes restent 0.8.7 ;
le binaire n'exige plus les optimisations sélectionnées implicitement pour le CPU
de compilation. Cette correction justifie une nouvelle compilation et validation
SQL ciblée. Une éventuelle variation de performance est distincte de la correction
métier ; aucun benchmark de charge ou test sur le CPU du VPS n'est revendiqué.

## 2. Ce qui reste inchangé

- Requirements fonctionnels existants, code backend/frontend et configuration
  des comptes, SQL-02, admissions cumulatives et IA globale désactivée.
- Source pgvector **f37c13f68b57d2c3472b2214fbcff699d6d34876**, extension **0.8.7**,
  PostgreSQL **17.11**, schéma cible **0007** ; aucun fichier de migration modifié.
- Jobs obligatoires **python, windows, frontend**, gates needs et condition de
  publish, publication uniquement linux/amd64 ; aucune modification de règles
  GitHub distantes, secrets, environnement production ou mécanisme d'approbation.
- deploy.yml, contrôleurs rollback/backup, registre root, guards et bundle
  **exactement neuf fichiers**. Les manifests de build ne sont pas ajoutés au bundle.

Une future fusion main peut toujours déclencher les trois publications privées
automatiques. L'ajout de logs d'identité du builder n'est pas une attestation ou
un verrou du binaire BuildKit. Le mode publish reste séquentiel et RF10-04 subsiste.

## 3. Vérifications directement affectées

| Vérification | Résultat réel du lot |
| --- | --- |
| Nouveaux contrôles, inventaire, déploiement et release security, Windows | **168 réussis, 4 ignorés**, 4,22 s après adaptation de l'assertion CI. |
| Bootstrap CI dans un venv Windows neuf, installation `.[test]` et inventaire contraint | Réussis avec les outils hachés ; même sélection : **168 réussis, 4 ignorés**, 8,36 s. |
| Dernier contrôle des tests de build/workflow après flag portable et readiness TCP | **109 réussis**, 0 ignoré/échec, 1,87 s. |
| Dockerfile backend réel, sources publiques | Construction réussie ; étape de recapture des logs backend avec cache après erreur de décodage du pilote, expliquée ci-dessous. |
| Dockerfile frontend réel, sources publiques | Construction sans cache réussie ; TypeScript/Vite réussi. |
| Dockerfile.db réel, sources publiques | Construction sans cache réussie ; après ajout OPTFLAGS portable, nouvelle compilation réussie en réutilisant seulement les matériaux déjà vérifiés. |
| Stage isolation-tests réellement construit : Linux/protocole et SQL-02 | **88 réussis, 1 ignoré, 5 désélectionnés**, 30,62 s. |
| Nouveau laboratoire HTTPS interne | **13 contrôles réussis**, backend/frontend des Dockerfiles réels et PG avant seule correction OPTFLAGS ; pas de port publié. |
| pgvector final portable, base neuve sans réseau | CREATE EXTENSION 0.8.7, L2=1, cosinus=0, produit scalaire négatif=-32, insertion et HNSW réussis. |

Les campagnes se recouvrent : ne pas sommer en tests uniques. L'avertissement
Starlette/httpx TestClient reste visible. Aucune suite complète historique Windows,
Linux ou PostgreSQL n'est prétendue relancée, aucun rerun GitHub.

Images finales locales, sans tag de release ni publication :

| Tag local | Image ID |
| --- | --- |
| documind-s14-8-backend:local | sha256:481500d27a1ccb333685de8500663559b44dc4368f5e461206760bd21d9fd0ca |
| documind-s14-8-frontend:local | sha256:98a2e853f9f48d56f19b0a1ddc9a817679d8777961e1d2b71b4a82cd71e6294e |
| documind-s14-8-postgres:local, portable | sha256:02be687f3378450482ec61fd0c902f02ac65daf1ca7fbbd7bc4a801f74d8e46d |

Le vector.so portable final porte le SHA-256
`b0563ae6512fc7d83f1b47c9285edb43589ea44884b1624c71f976303f0502f8`.
Ce sont des identités de laboratoire, pas des références de manifeste Registry
ou des candidats approuvés pour le VPS.

Les quatre ignorés Windows sont un contrôle exigeant PostgreSQL et trois preuves
d'ownership/root exigeant Linux. Les tests portables existants gardent leurs
fixtures locales habituelles, dont la préparation Alembic de bases SQLite neuves
lorsqu'une fixture l'utilise : **pas de migration de production ni modification
de migration**. Ce ne sont pas des preuves de sandbox Linux.

La campagne de conteneur conserve la fixture privée forte de 14.7.11 : sandbox
strict, schémas ORM neufs, sans Alembic. Ses 72 tests Linux/protocole sont revalidés ;
la partie intégrité ajoute 16 succès, un contrôle de fence PostgreSQL ignoré car
cette campagne utilise SQLite, et cinq cas d'arrêt brutal non relancés. Les fautes
de commit documentaire sélectionnées restent vérifiées. L'absence de changement
métier évite de répéter la campagne complète de concurrence/rollback historique.

### Scénarios critiques sur les images construites

Projet temporaire **documind-s14-8-9e1187ef**, réseau interne, aucun port publié,
données, TLS et comptes entièrement fictifs. Réutilisation du harnais 14.7.11 en
copie, pas modification de ses preuves. Ses contrôles : santé HTTPS, refus anonyme,
CSRF, cookie Secure/HttpOnly sans token renvoyé, imports PDF/TXT, analyse classique,
texte extrait, propriétaire isolé, refus IA et connexion BYOK, cinq admissions et
pas de sixième compte/mail, vérification email unique, connexion et révocation.

Lecture SQL : **5 comptes publics fictifs, issued_count=5, AIUsage=0 et
AIReservation=0**, extension 0.8.7 et distance 1. La configuration publique ne
concerne que ce laboratoire inaccessible à l'extérieur ; aucune inscription
réelle n'est ouverte. Certificat fictif validé, proxy de tests utilisant le vrai
code BFF ; pas une inspection de Traefik/VPS ou un envoi SMTP réel.

Le changement final OPTFLAGS ne modifie que le code machine de l'extension. Il
est testé séparément dans un second conteneur PostgreSQL neuf, sans réseau et
sans API attachée. Ne pas présenter les 13 étapes HTTPS comme une seconde recette
complète après ce seul changement, ni comme la qualification de futures images CI.

### Incidents identifiés, sans correction applicative pour obtenir du vert

1. La première assertion de test attendait littéralement l'ancienne commande pip.
   Elle a été adaptée pour exiger venv neuf, hashes, codes de sortie PowerShell,
   tzdata et vérification des dépendances de build : pas d'attente de sécurité retirée.
2. Un pilote de capture Windows a échoué à décoder les logs Docker en CP1252.
   Capture UTF-8, inspection puis recapture du build backend avec cache, code 0 ;
   aucune exception de l'application masquée ou timeout augmenté.
3. Le premier probe PostgreSQL portable a pris le serveur Unix temporaire
   d'initialisation pour le serveur prêt ; la socket était absente lors de psql.
   La vérification exige maintenant **pg_isready -h 127.0.0.1**, qui attend le
   serveur TCP final. Même correction de critère dans la CI, boucle de 60 essais
   conservée. Ce constat ne démontre pas la cause du HTTP 503 historique SQL-01.

## 4. Preuves antérieures réutilisables

Comparaisons ciblées, pas nouvelle campagne d'acquisition :

- Backend : mêmes **46 distributions**, hashes des **24 bibliothèques natives**
  et des **84 fichiers source Python** que 14.7.11, après construction publique.
- Frontend : mêmes hashes des **14 fichiers dist/server** livrés ; base Node,
  lock et code identiques aux tests 52 React/50 BFF de 14.7.11. Ces comptes restent
  des résultats historiques, pas des tests nouvellement exécutés.
- PostgreSQL : mêmes **45 versions de paquets installés** que 14.7.11 avant le
  changement de flag ; les octets de métadonnées APK diffèrent, sans dérive de version.
  Les entrées restent identiques après changement OPTFLAGS, et la fonctionnalité
  vectorielle finale est testée séparément. Le hash du binaire change volontairement.
- Archives npm et Python, vérifications Debian/APK et provenances reçues restent
  celles de 14.7.10/11. Les reçus publics contrôlés sont adoptés dans des manifests
  propres, sans recopier leurs caches ou données privées.
- Snapshot/restauration **23 tables / 4 documents** et tests de sauvegarde/guards
  antérieurs sont conservés. Pas de nouvelle restauration, aucun accès B2/SMTP/VPS.
  Les contrôleurs de sauvegarde et rollback n'ont pas changé ; tests unitaires
  de release directement affectés réussis, preuves privilégiées ignorées signalées.

Aucune garantie générale de non-régression n'est déduite de ces comparaisons : la
**vraie CI du nouveau SHA** demeure obligatoire avant toute décision de fusion.
L'inventaire garde `pep517_environment_verified=false` : versions installées et
hashes connus ne sont pas une attestation indépendante de toute la provenance.

## 5. Tableau de décisions humaines

| Point | Risque et preuves | Mesures / arrêt | Correction ou acceptation envisageable |
| --- | --- | --- | --- |
| 122 paquets npm, dont 60 runtime, liés seulement à une clé historique expirée | Signatures mathématiquement vérifiées, SRI/archives contrôlés ; confiance temporelle non démontrée. L'expiration actuelle ne prouve pas qu'une ancienne signature était invalide. | Même lock, bytes contrôlés, registre HTTPS, CI et usages confinés. Arrêt sur hash/version différent, clé inconnue, signature réellement invalide ou indice de compromission. | Ne pas accepter rétroactivement la clé sans preuve temporelle. L'exploitante peut envisager d'accepter **l'insuffisance de cette preuve** pour une publication privée bornée, en s'appuyant sur les autres garanties, sans certifier la signature historique ni autoriser le public. Aucune acceptation faite ici. |
| Provenances PyPI et SLSA partielles | Origines HTTPS et hashes revus ; certains documents disponibles ; signatures/identités/transparence non vérifiées intégralement. | Locks hachés, FROM par digest, sources officielles bornées, signatures APK, provenance réellement émise à lire après publication. Arrêt sur entrée non identifiée ou écart non expliqué. | Vérification approfondie si exigée par la politique ; sinon décision explicite de risque limitée au privé. Pas de certification ou d'audit CVE inventés. |
| Builder et runners | Identité locale connue ; action Buildx par SHA, mais binaire/matériaux BuildKit du runner pas intégralement qualifiés. Les Python/Node de tests restent dans leur série CI. | Venvs propres et outils Python hachés, logs builder avant authentification, runners temporaires, gates inchangés. Arrêt sur builder/architecture inattendus ou provenance obligatoire absente. | Acceptation bornée envisageable du service de build ; ne pas confondre enregistrement de version et attestation. Pas de nouvelle image de builder choisie sans qualification. |
| OCI non bit-identique | Différences déjà documentées malgré contenus/configs comparés égaux. | Identité des entrées, versions, provenance et tests ; digests des sorties pour livraison. Arrêt sur écart fonctionnel ou matériel inexpliqué, pas sur un simple horodatage. | **Pas de correction indispensable pour une RC privée fonctionnellement qualifiée.** Ne pas conditionner ce lot à une perfection bit à bit ni promettre cette propriété. |
| R14-SQL-01 | Origine du GET 503 historique toujours inconnue ; aucune correction revendiquée. | Journalisation expurgée, tests affectés, arrêt si réapparition, état durable incohérent ou autorisation erronée. | Acceptation humaine éventuellement limitée à une RC privée/fermée avec seuil d'arrêt ; reproduction implique diagnostic ciblé, pas retry SQL/timeout aveugle. |
| R14-SQL-03 | Inscription peut être commitée malgré erreur et mail absent ; compteur cumulatif conservé. | Renvoi protégé, comptes non vérifiés bloqués, fermeture disponible ; aucune compensation/reset automatique. | Décision distincte ; plus facile à borner pour livraison fermée sans admission que pour public. Réconciliation/email réels nécessaires avant ouverture ; outbox éventuelle hors de ce lot. |
| RF10-04 | Trois pushes séquentiels : sortie partielle possible même si les tests passent. | Gates CI, tags SHA non écrasés, bundle final neuf fichiers, arrêt de livraison et conservation des diagnostics si partiel. | Procédure déjà retenue ; aucune relance/suppression/retagging automatiques. Nouvelle autorisation obligatoire avant intervention après échec. |

Les acceptations envisagées ne sont pas des décisions. Les exceptions historiques
Sprint 10 ne se reportent pas sur cette version. Une éventuelle décision privée
doit préciser SHA, événement/run/attempt, une seule publication, durée, preuves
et conditions d'arrêt ; aucun rerun, déploiement ou usage public inclus par défaut.

## 6. État RF10-03 après stabilisation

Les correctifs minimaux techniques sont désormais dans les fichiers destinés à
la PR : bases, fermeture runtime hachée, outils de build, commit/source pgvector,
APK exacts/signés, absence d'APT flottant nécessaire, npm verrouillé et portabilité
CPU. Le build ne dépend plus des variantes privées de laboratoire.

**RF10-03 reste partiellement ouvert sur la confiance/provenance et les décisions
humaines**, pas sur une nécessité de répéter les doubles builds historiques.
Aucune exigence de bit-identité OCI n'est ajoutée. Les 19 URL APK peuvent être
retirées à terme par l'origine : échec fermé et requalification, pas gel éternel
de versions vulnérables. Aucun audit de vulnérabilités actualisé réalisé ici.

## 7. Inventaire à examiner avant commit

**16 chemins du lot 14.8**, sans indexation automatique :

```text
.dockerignore
.github/workflows/ci.yml
.gitignore
Dockerfile
Dockerfile.db
frontend/Dockerfile
tests/test_deployment.py
tools/build_materials.py
build-materials/README.md
build-materials/pgvector.json
requirements.build.lock
requirements.runtime.lock
requirements.test.lock
tests/test_pinned_builds.py
tools/fetch_build_materials.py
docs/SPRINT_14_8_RELEASE_STABILIZATION_REPORT.md
```

Les cinq rapports 14.7.7–14.7.11 déjà non suivis sont conservés. Pour publier aussi
les preuves référencées et éviter des liens cassés, la proposition de revue porte
sur **21 chemins**, sous réserve de validation explicite de ces cinq documents :

```text
docs/SPRINT_14_7_7_GITHUB_DRAFT_PR_REPORT.md
docs/SPRINT_14_7_8_GITHUB_CI_REVIEW_REPORT.md
docs/SPRINT_14_7_9_PREMERGE_RISK_REVIEW.md
docs/SPRINT_14_7_10_BUILD_MATERIALS_QUALIFICATION_REPORT.md
docs/SPRINT_14_7_11_PRODUCTION_IMAGE_QUALIFICATION_REPORT.md
```

Exclus : var, archives npm/APK/wheels, venvs, dumps, captures mail, certificats/clés
fictifs, logs, images et répertoire build généré. Les fichiers publics nouveaux
sont uniquement du texte contrôlé ; aucun secret réel ou donnée utilisateur ajouté.
Les éléments sous var ne sont ni effacés ni proposés au commit.

## 8. Matrice Go / No-Go et chemin court

| Étape | Verdict et condition |
| --- | --- |
| 1. Révision locale à soumettre en PR | **Go technique pour revue**, avec les résultats et limites ci-dessus ; pas une RC publiée/certifiée. |
| 2. Commit puis push sur la branche de revue | **Préparables, non autorisés** : validation du périmètre, inspection de chaque index, arbre/base cohérents, autorisations explicites. Aucun commit/push effectué. |
| 3. Fusion main et publication privée automatique | **Bloquées** : vraie CI nouvelle révision, revue/risques statués, protections et base revérifiées, autorisation couvrant l'effet publish et RF10-04. |
| 4. Qualification des images publiées | **Non réalisée** : relever run/attempt, trois digests amd64/labels, provenance/inventaires, bundle neuf fichiers cohérent ; recette des sorties réelles. Pas de comparaison aveugle avec une Image ID locale. |
| 5. Déploiement fermé | **Non autorisé** : images recettées, approbation root, guards/bootstrap, sauvegarde et secours sûr/correction en avant, fermeture/IA off ; pas d'accès VPS dans ce lot. |
| 6. Ouverture publique | **No-Go distinct** : décision opératrice, SMTP/B2/alertes/textes/quota/fermeture et risques d'inscription validés. Aucun changement de configuration publique ou IA. |

Voie la plus courte proposée :

1. Revue du diff des 16 chemins et des cinq rapports, puis décisions de risque
   bornées. Autoriser séparément un commit sur la branche de revue et son push.
   Message proposé : `build: stabiliser les matériaux de la release privée`.
2. Mettre à jour **la PR nº 6 existante, encore Draft**, après autorisation, et
   laisser sa CI automatique python/windows/frontend valider le nouveau SHA.
   Ne pas déclencher publish/deploy manuellement ni réexécuter les audits clos.
3. Si CI verte et décisions approuvées, demander une autorisation distincte de
   fusion couvrant une unique publication privée. Observer celle-ci, contrôler
   les sorties/bundle et appliquer RF10-04 si partielle. Déploiement et ouverture
   restent deux décisions ultérieures, même après une publication réussie.

Seule une modification nouvelle, un échec ou une preuve invalide justifie de
rouvrir une campagne concernée. Les validations manquantes se font sur les images
réellement publiées, pas par accumulation de nouveaux audits locaux identiques.

## 9. Préservation et clôture

Les conteneurs/réseau/volume du seul nouveau laboratoire sont retirés après
vérification de leur project/labels et de leur absence de l'inventaire initial ;
les conteneurs PostgreSQL portables sont aussi retirés. Aucun down -v, aucune
destruction de ressource préexistante. **8 conteneurs, 328 volumes et les réseaux
préexistants sont préservés** dans leur identité/état observable. Les images et
preuves locales restent conservées. Cela ne constitue pas une inspection interne
de toutes les autres applications ou de la production.

Les contrôles Git de clôture, inventaire des chemins, index vide et blancs UTF-8
du rapport sont vérifiés. Aucun commit, push, merge, PR modifiée, workflow lancé,
publication Registry, accès VPS/B2, modification de secrets ou .env.production.
Les modifications non commitées antérieures sont conservées.

**Arrêt après ce dossier local. Attente des autorisations explicites de
commit/push et des décisions de risque ; aucune publication ou adoption en
production déduite des tests.**
