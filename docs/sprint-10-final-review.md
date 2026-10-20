# Sprint 10 — Revue finale avant publication

> Complément ultérieur : [corrections et validation RF10-01/RF10-02](sprint-10-rf01-rf02-validation.md).
> Le nouveau job Windows obligatoire et la limitation des nouvelles publications à amd64
> sont implémentés localement. Les constats ci-dessous décrivent l'état avant ces corrections.

## 1. Synthèse et verdict

**Verdict : prêt sous conditions pour une publication contrôlée ; aucun accord de commit,
push ou déploiement n'est donné par ce rapport.** Le confinement actuel répond au modèle
retenu et les preuves locales passent. Aucun contournement confirmé de sa frontière n'a
été identifié dans les changements examinés. Cela ne constitue pas une preuve d'absence
de vulnérabilité native, noyau ou de toute possibilité de déni de service.

Conditions avant publication sur `main` : valider l'inventaire ci-dessous, décider du
traitement de la couverture Windows absente de la CI, limiter la portée des garanties
arm64 aux preuves réellement disponibles, et examiner/accepter les risques supply chain
déjà ouverts dans l'audit. Aucun correctif de code n'a été appliqué pendant cette revue.
L'ajout d'un job Windows, s'il est retenu, doit être autorisé et validé avant publication.

Le diagnostic communiqué par l'administratrice établit Debian 12, Linux
`6.12.95+deb12-cloud-amd64`, ABI 6 sur l'hôte et dans Docker, avec restriction effective.
Il lève le précédent blocage ABI 2. **La nouvelle image Sprint 10 doit encore passer
la recette ABI 6 avant déploiement** : les preuves locales portent sur ABI 7.

Base Git locale : `5ac8d3f1ce4474d1d4742637beb22192194dfbe2`.
L'identité de la release active de production n'est pas déduite de ce commit.
Aucun accès VPS, workflow distant, commit, push, installation ou déploiement effectué.

## 2. Revue de sécurité

| Garantie | Constat dans le code et les tests | Limite explicite |
| --- | --- | --- |
| ABI minimale | `sandbox.py` refuse ABI < 3 ; masque incluant `TRUNCATE` ; test injectant ABI 2 | Aucune adaptation ABI 2 ni reprise automatique |
| Ordre d'installation | Limites, no-new-privileges/dumpable, Landlock, puis seccomp avant import PyMuPDF et lecture du protocole | Le bootstrap Python et les modules de confiance sont chargés avant les politiques |
| Fichiers | Règles lecture seule sur le runtime ; aucun accès accordé à `/app/var`, `/tmp`, `/proc`, HOME ou à `/etc` entier | Certaines métadonnées restent observables ; chemins runtime à maintenir sans secrets |
| Documents et secrets | Octets du seul document transmis ; tests de refus d'autres fichiers et marqueurs de secrets | API/courtier restent des composants de confiance |
| Descripteurs | Exec neuf, `close_fds=True`, environnement limité à la locale, trois flux dédiés ; FD hérités testés | Landlock ne révoque pas rétroactivement tous les droits d'un FD préouvert |
| Troncature | Droit Landlock traité sans l'accorder ; `open`/`openat` avec `O_RDONLY|O_TRUNC` refusés ; `truncate`/`ftruncate` absents de l'allowlist seccomp | La fermeture des FD demeure essentielle pour les lectures/écritures déjà autorisées |
| Réseau, PostgreSQL, Docker | Sockets/connexions IPv4/IPv6/Unix interdits par seccomp, aucun socket applicatif hérité ou montage Docker | L'API a légitimement ses réseaux ; ce sont les politiques du parseur qui interdisent leur usage |
| Processus et privilèges | Fork/clone/exec, ptrace, process_vm, pidfd, namespaces, mount, capacités, ioctl/fcntl refusés ; NPROC=1 | Même UID et noyau que l'API, sans VM ni changement d'UID revendiqué |
| Ressources | AS ≤ 512 Mio, CPU ≤ 30 s, FSIZE/CORE=0, NOFILE=32 ; syscalls de changement des limites refusés | AS et cgroups n'interdisent pas tout incident global de mémoire ou de charge |
| Temps et flux | Parent : délai ≤ 30 s, sortie ≤ 8 Mio, arrêt du groupe si nécessaire et récupération du processus | Une sortie typée ne garantit pas l'exactitude sémantique de l'extraction |
| Protocole | En-tête ≤ 1024 octets, entrée ≤ 10 Mio, 200 pages, 1 million de caractères ; UTF-8, doublons, types, champs et job contrôlés | Analyse du JSON borné effectuée dans le parent |
| Fail-closed | Sonde native au lifespan ; ABI insuffisante/échec seccomp ⇒ runner code 78 et refus ; pas de fallback | L'indisponibilité peut empêcher le redémarrage de l'API : diagnostic, pas contournement |
| Production | Compose impose sandbox, deux slots, 512 Mio/30 s ; un processus API ; racine read-only et no-new-privileges | L'env local development reste un choix explicite hors production |

Le contrôle de troncature n'est pas fourni par `RLIMIT_FSIZE=0` seul. Les preuves le
distinguent de Landlock et seccomp. Les appels `write`/`writev` restent autorisés pour
les pipes de sortie ; un ajout ultérieur de FD applicatif transmis au parseur nécessiterait
une nouvelle revue. Ne pas accorder un répertoire runtime inscriptible ou contenant des secrets.

PDF/TXT : le moteur reprend l'extraction existante depuis des octets, préserve les pages,
refuse fichiers vides, malformés/réparés, binaires déguisés, PDF à mot de passe et dépassements.
L'analyse classique conserve ses processus et ses algorithmes. Aucun changement de schéma SQL.

### Problèmes et corrections proposés, non appliqués

| Référence | Constat | Proposition avant publication |
| --- | --- | --- |
| RF10-01 | Aucun job `windows-*` dans les deux workflows. La CI n'automatise donc pas les régressions Windows annoncées localement. | Autoriser un job Python 3.13/Windows pour la suite portable, données temporaires, IA désactivée et dépendances de test explicites, notamment tzdata si nécessaire. Ajouter ce job aux dépendances de `publish`. Alternative à accepter explicitement : contrôle Windows manuel comme exception temporaire documentée. |
| RF10-02 | Images publiées amd64 **et arm64**, preuves d'isolation exécutées seulement en amd64. QEMU/build réussi ne certifie pas un noyau arm64. | Certifier arm64 séparément ou autoriser une limitation explicite des plateformes publiées ; ne pas présenter arm64 comme validée en attendant. Non bloquant pour une recette et un usage exclusivement amd64 déclarés. |
| RF10-03 | Entrées de build mutables, lock Python sans couverture intégrale/hashes, alertes d'outillage déjà relevées par SEC10-05/06. | Reprendre le lot supply chain séparément ou documenter une acceptation bornée pour cette publication privée. Aucun nouvel audit CVE distant réalisé ici ; aucun avis historique n'est présenté comme réactualisé. |
| RF10-04 | `publish` pousse trois images séquentiellement : publication non atomique. Une panne peut laisser des tags SHA partiels et aucun bundle final ; le contrôle de réutilisation refusera alors une relance identique. | Conserver les preuves d'échec ; ne pas retaguer silencieusement. Nouvelle version ou réparation administrative de Registry explicitement approuvée. Ce risque préexiste au lot. |

Aucune correction applicative indispensable n'est démontrée par cette revue. RF10-01
est un écart de couverture demandé par la mission ; son traitement attend la décision
de l'administratrice. Les autres constats Sprint 10, notamment admission HTTP précoce,
traçabilité et politique réseau/BFF, ne sont pas clos par ce lot. L'ouverture publique reste exclue.

### Secrets et fichiers générés

Les 52 fichiers candidats ont été lus ou analysés selon leur rôle. Contrôle local de
signatures : clés privées, tokens OpenAI/GitHub, identifiants AWS et identifiants dans
URL HTTP. **Aucune alerte** dans ce périmètre. Les exemples contiennent des valeurs
de développement explicites ou des champs secrets vides ; les tests utilisent des marqueurs.
Ce contrôle ciblé ne prouve pas l'absence universelle de secret, ne couvre pas l'historique
Git et ne lit pas les `.env` privés. Aucun secret réel n'a été consulté pour le comparer.

Tous les candidats sont des sources/configurations/docs texte, maximum 37 168 octets
avant ce rapport. Aucun PDF, archive, dump, certificat ou binaire généré ne figure dans
la liste candidate. `.dockerignore` exclut env, Git, var, venv, PDF et bases ; les tests
entrent seulement dans la cible `isolation-tests`. La cible finale n'inclut ni tests ni pytest.

## 3. Inventaire Git proposé

État initial de revue : **15 fichiers suivis modifiés + 37 fichiers non suivis = 52**,
index vide. Ce rapport ajoute un 53e candidat. **Rien n'a été indexé.** Les tableaux
constituent une proposition examinée, pas une consigne d'ajouter tout fichier non suivi.
Chaque ligne exige l'accord sur le périmètre du futur commit.

### Fichiers suivis à inclure dans la publication complète proposée

| Fichier | Origine et raison |
| --- | --- |
| `.dockerignore` | S10 : autoriser COPY des tests dans la cible dédiée |
| `.env.example` | S10 : choix development explicite pour le poste local |
| `.env.production.example` | S10 : sandbox obligatoire ; IA/inscriptions restent désactivées |
| `.github/workflows/ci.yml` | S10 : preuves Linux et Docker avant publication |
| `Dockerfile` | S10 : libseccomp2, packaging extracteur, cibles tests/production |
| `README.md` | S7–10 : liens exploitation et documentation confinement |
| `backend/config.py` | S10 : mode d'extraction, sandbox par défaut |
| `backend/main.py` | S10 : contrôle natif au démarrage |
| `backend/services/worker.py` | S10 : dispatch vers le broker et réutilisation moteur |
| `compose.production.yaml` | S10 : mode et bornes imposés ; montages préservés |
| `compose.yaml` | S10 : sandbox sous Docker local |
| `pyproject.toml` | S10 : inclusion du nouveau package, pas de nouvelle dépendance Python |
| `tests/conftest.py` | S10 : adaptateur portable explicitement development |
| `tests/test_deployment.py` | S7 : refus d'une maintenance de sauvegarde en attente |
| `tools/deploy_production.py` | S7 : même garde sous verrou de déploiement |

### Nouveaux fichiers S7–9 à conserver et publier comme livraisons identifiées

Ces 21 fichiers constituent des sources/procédures cohérentes, pas des artefacts. Ils
sont déjà nécessaires aux liens README et aux tests d'exploitation disponibles localement.
Leur commit ne doit pas réinstaller ou écraser les scripts actuellement installés sur le VPS.

| Sprint | Fichiers proposés |
| --- | --- |
| S7 | `tools/backup_production.py` ; `tests/test_production_backups.py` ; `tests/test_restic_upload.py` |
| S7 | `ops/systemd/documind-backup.service` ; `ops/systemd/documind-backup.timer` ; `ops/systemd/documind-backup-alert.service` |
| S7 | `docs/sprint-7-backups.md` ; `docs/validation-sprint-7.md` |
| S8 | `tools/monitor_production.py` ; `tools/gmail_monitor_alert.py` ; `tests/test_monitoring.py` |
| S8 | `ops/systemd/documind-monitor.service` ; `ops/systemd/documind-monitor.timer` |
| S8 | `docs/sprint-8-monitoring.md` ; `docs/validation-sprint-8.md` |
| S9 | `tools/retention_production.py` ; `tests/test_retention.py` |
| S9 | `ops/systemd/documind-retention.service` ; `ops/systemd/documind-retention.timer` |
| S9 | `docs/sprint-9-retention.md` ; `docs/validation-sprint-9.md` |

### Nouveaux fichiers Sprint 10

| Lot | Fichiers proposés |
| --- | --- |
| Moteur/confinement | `documind_extractor/__init__.py` ; `documind_extractor/contract.py` ; `documind_extractor/engine.py` ; `documind_extractor/runner.py` ; `documind_extractor/sandbox.py` |
| Intégration | `backend/services/extraction.py` ; `compose.pdf-isolation-test.yaml` |
| Tests | `tests/test_extraction_linux.py` ; `tests/test_extraction_protocol.py` |
| Audit phase A | `docs/sprint-10-security-audit.md` ; `docs/sprint-10-remediation-plan.md` ; `docs/validation-sprint-10-audit.md` |
| Phase B lot 1 | `docs/sprint-10-pdf-isolation-design.md` ; `docs/sprint-10-pdf-isolation-validation.md` ; `docs/sprint-10-pdf-isolation-revalidation.md` |
| Historique/présente revue | `docs/sprint-10-landlock-compatibility.md` ; `docs/sprint-10-final-review.md` |

Cela représente 17 nouveaux fichiers S10 avec ce rapport, soit 53 candidats au total.
La note de compatibilité ABI 2 est historique et contient désormais un renvoi à la migration
confirmée ; elle ne prescrit plus une migration à effectuer sur le VPS actuel.

### À exclure explicitement

- `.env`, `.env.production`, Gmail/Restic privés, fichiers de mots de passe, identifiants
  Registry, clés SSH, certificats privés et tout autre secret : jamais à indexer.
- `var/` entier : venv Linux, sondes, références SHA-256, configuration Docker de test,
  recette diagnostique, outils téléchargés et caches ; ce sont des artefacts locaux.
- `.venv/`, `__pycache__/`, `*.pyc`, `.pytest_cache/`, `*.egg-info/`, couverture,
  `node_modules/`, `frontend/dist/`, `*.tsbuildinfo`, rapports Playwright : déjà ignorés.
- PDF/TXT personnels, données/bases et dumps, archives Restic, exports Docker/images,
  éventuel futur `build/` : ne pas les ajouter, même si une règle Git les laisse visibles.
  `build/` est absent à cette revue et ne possède pas de règle dédiée dans `.gitignore`.
- `/srv/documind-ai/ops/gmail_backup_alert.py` : hook déclaré existant uniquement sur
  le VPS, absent du dépôt ; aucune copie, recréation ou récupération automatique proposée.

### Dépendances et découpage conseillé

Si plusieurs commits sont préférés après autorisation, identifier d'abord S7 et son
verrou déployeur, puis S8 dépendant des helpers S7, puis S9 dépendant de S7/S8, puis
S10 phase A et phase B. Le README mêle ces livraisons : le publier avec tous ses
liens cibles ou faire approuver une séparation de ses hunks. Ne pas publier une
séquence intermédiaire incohérente sur `main`, car chaque push y peut publier des images.

Pour S10, broker, package, dispatch, config/startup, Docker/Compose, tests et CI doivent
être présents ensemble. Ne pas committer seulement les fichiers déjà suivis : l'image
perdrait ses nouveaux modules. Une branche avec PR permet une CI sans publication
avant fusion, sous réserve de l'autorisation explicite du push et de l'ouverture de PR.

## 4. Sprints 7–9 et contrôles locaux

Les 52 candidats ont une référence SHA-256 sous `var/sprint10-final-review/baseline.json`.
**Aucun des 52 n'a changé pendant cette revue** ; seuls ce rapport et les artefacts
ignorés de revue ont été créés. Les 21 fichiers S7–9 sont préservés, ainsi que les
deux changements suivis relatifs à la garde de maintenance.

- Sauvegarde et déploiement : même `deployment.lock`, verrou exclusif non bloquant.
  Le déployeur refuse `var/backup-maintenance.json` ; reprise de sauvegarde contrôlée.
- Conservation : verrou propre et verrou partagé du même fichier pendant l'inventaire,
  empêchant le travail simultané d'un écrivain exclusif ; refus si maintenance en attente.
- Surveillance : sonde brève du verrou, sans commande Docker d'administration ; alertes
  différées lors d'une opération normale, état d'envoi conservé, STARTTLS vérifié.
- Sauvegarde : arrêt uniquement API/web ; redémarrage en `finally` et `ExecStopPost`,
  contrôle des identités/montages, healthchecks et HTTPS ; aucune opération destructive DB.
- S9 : défaut simulation, unité `--simulate`, `--execute` renvoie 2 avant toute sonde ;
  aucun chemin de suppression activable par configuration. Politique 7/4/6 simulée,
  copies historiques et dernière sauvegarde protégées. Ne pas confondre proposition
  `would_remove` avec suppression effective.
- Timers conservés à 03 h, 08 h et 09 h Europe/Paris ; aucune unité installée ou activée.

| Contrôle de cette revue | Résultat |
| --- | --- |
| Docker, image de preuves locale identifiée | **72 réussis**, aucun ignoré, 10,36 s |
| Windows ciblé : protocole/déploiement/S7–9/Restic | **358 réussis**, 11,54 s |
| Recette autonome dans l'image finale, sans pytest | **Réussie**, ABI 7 locale : fichiers, troncature, FD, réseau, ressources, PDF/TXT |
| Analyse syntaxique AST des Python candidats | **22 fichiers**, réussie |
| Scan de signatures des secrets candidats | Aucune alerte ; portée limitée décrite plus haut |
| actionlint CI/deploy | Réussi ; shellcheck/pyflakes désactivés pour ce contrôle |
| `git diff --check` | Réussi |
| Index Git | Vide, aucune publication préparée par staging |

Les pytest signalent la dépréciation Starlette/httpx, sans échec. Les résultats précédents
**487 Windows / 416 Linux / 72 Docker**, les builds des deux cibles et le smoke de l'image
finale restent des éléments historiques de la [revalidation](sprint-10-pdf-isolation-revalidation.md),
pas de nouvelles exécutions complètes dans cette revue. Ne pas additionner les séries.
PostgreSQL/pgvector et les suites frontend n'ont pas été relancés ici ; aucune modification
du frontend ou de migration n'est proposée. Les tests des outils d'exploitation simulent
Docker, Restic et SMTP : ils ne déclenchent ni envoi B2/Gmail ni purge réelle.

## 5. CI/CD et conséquences exactes d'un push sur main

| Couverture actuelle | État |
| --- | --- |
| Windows | Absente des workflows ; résultat local seulement, RF10-01 |
| Linux | Ubuntu 24.04, Python 3.13, preuves natives obligatoires, aucune bascule de secours |
| Docker | Build cible de tests et 72 preuves amd64 avec réseau none, rootfs read-only, cap-drop ALL et limites |
| SQLite | Suite complète après les preuves |
| PostgreSQL/pgvector | Build PostgreSQL 17, base dédiée `documind_test`, mot de passe fictif ; suite complète ciblant cette base |
| Frontend | Node 22, npm ci, React, BFF et TypeScript/build ; job requis pour publish |
| arm64 | Build/push sous Buildx/QEMU ; pas de preuve native arm64 |

Un push sur `main` déclenche automatiquement `ci.yml` :

1. Jobs Python et frontend sur runners GitHub. Échec d'un job ⇒ `publish` ne démarre pas.
2. Si les deux réussissent, connexion à la Registry privée avec secrets GitHub, contrôle
   de non-réutilisation des tags SHA, builds et **push des trois images** backend,
   frontend/BFF et PostgreSQL pour `linux/amd64,linux/arm64`.
3. Création de l'artefact `documind-release-<SHA>` : manifeste à digests, Compose,
   déployeur, helper de sauvegarde et validateur de release ; rétention 90 jours.

Le job `publish` est aussi éligible à un `workflow_dispatch` de CI sur `main`.
Une PR déclenche les tests sans publication ; un simple push de branche différente
de `main` n'est pas couvert par le trigger push de ce fichier. Aucun workflow Windows
caché dans le dépôt ne complète cette couverture.

**Ce push ne contacte pas le VPS**, n'applique aucune migration et ne redémarre aucun
service ni timer. Les scripts d'exploitation committés ne sont pas installés par la CI.
Il reconstruit néanmoins l'image PostgreSQL même sans changement de son Dockerfile.
Le futur déploiement ordinaire pourra appliquer ce nouveau digest DB après sauvegarde :
ce n'est pas une opération backend uniquement à accepter implicitement.

`deploy.yml` reste un `workflow_dispatch` séparé sur `main`, avec environnement production,
approbation et contrôle de reviewers obligatoires, SHA/run exacts, SSH vérifié et contrôles
de compatibilité. Son existence n'autorise pas son lancement. Aucun secret de Registry
n'est stocké dans les fichiers candidats ; aucun accès réseau réel à celle-ci n'a été effectué.

## 6. Recette ABI 6 proposée, jamais exécutée sur le VPS

### Préconditions à approuver

Autoriser séparément cette recette distante. Relever le noyau, l'ABI et l'architecture
réellement utilisés et le profil Docker applicable, sans inspecter les variables d'un
conteneur de production. Confirmer marge mémoire/disque/CPU et absence de collision
de nom ; ne pas exécuter un essai de ressources pendant un pic ou une sauvegarde.

Stager l'image finale approuvée **par digest** via l'accès Registry en lecture existant,
ou par une archive d'image préparée depuis la CI et vérifiée. Le transfert/pull nécessite
son réseau administratif ; **le conteneur de recette lui-même n'aura aucun réseau**.
Ne pas construire sur le VPS, copier un `.env` ou réutiliser le Compose de production.

Ne pas lancer une pile API/BFF/DB entière : cette recette vérifie le runner et le broker
dans l'image finale, sans serveur ni connexion à PostgreSQL. Les migrations et tests
HTTP/intégration complets restent les étapes de CI/recette distinctes.

### Restrictions et commande proposées

À exécuter ultérieurement par l'administratrice après accord, avec les valeurs réelles
du manifeste choisi. `BACKEND_IMAGE` désigne une référence complète `@sha256:...`, jamais
un tag mutable. `CHECK_DIR` désigne un répertoire privé de recette hors `/srv/documind-ai`,
contenant seulement le script de l'annexe relu. Aucun de ces chemins n'est créé ici sur le VPS.

```bash
# Variables saisies après revue ; le test refuse les valeurs non figées.
case "$BACKEND_IMAGE" in
  registry.adelinemeistertzheim.fr/documind-ai/backend@sha256:*) ;;
  *) printf '%s\n' 'Référence de release par digest requise' >&2; exit 1 ;;
esac
printf '%s\n' "${BACKEND_IMAGE##*@sha256:}" | grep -Eq '^[a-f0-9]{64}$' || exit 1
docker image inspect "$BACKEND_IMAGE" --format '{{.Os}}/{{.Architecture}}'

docker run --rm -i --pull never --name documind-s10-recipe \
  --network none --read-only --init --security-opt no-new-privileges \
  --memory 1536m --cpus 2 --pids-limit 64 \
  --tmpfs /tmp:size=256m,mode=1777 \
  --log-driver json-file --log-opt max-size=10m --log-opt max-file=1 \
  --entrypoint python "$BACKEND_IMAGE" - \
  < "$CHECK_DIR/recipe_probe.py" > "$CHECK_DIR/result.json"
```

Le profil seccomp Docker reste actif. Si la production utilise un profil AppArmor/seccomp
personnalisé, relever son identité après autorisation et **ajouter sa référence réelle**
à cette commande ; ne pas supposer son nom ni passer `unconfined`. La commande reprend
les limites, l'utilisateur de l'image, le tmpfs et no-new-privileges du service API ;
`network none` et l'absence de volumes remplacent intentionnellement ses réseaux/montages.

Les 72 preuves locales utilisaient en plus `--cap-drop ALL` et tmpfs noexec/nosuid.
La recette autonome a été vérifiée localement avec le profil ci-dessus sans ces deux
ajouts pour correspondre au Compose ; `--init` et la rotation des logs sont des options
d'exploitation de la commande proposée, non des preuves locales supplémentaires revendiquées.
Une seconde passe plus stricte peut ajouter ces restrictions, jamais en retirer.

Pas d'env_file, bind mount, volume nommé, port publié, secret, socket Docker ou connexion
DB. Les fichiers fictifs vivent seulement dans le tmpfs privé. L'environnement de `docker
run` n'est pas transmis au conteneur sans option `--env`, et le broker réduit encore celui
de ses enfants. Les marqueurs `FAKE-*` du script sont publics et ne sont pas des secrets.

### Validation, refus et arrêt de la recette

- Valider uniquement si code 0, JSON `status=ok`, noyau attendu 6.12 et ABI mesurée **6**,
  UID non root, seccomp/no-new-privileges constatés et toutes les assertions réussies.
- Le script teste lecture/création interdites, troncature `open`/`openat`, `ftruncate`
  avec FD fictif préouvert, fermeture du FD hérité, environnement réduit, sockets
  IPv4/IPv6/Unix, fork, limites mémoire/CPU/délai/sortie, et extraction PDF/TXT synthétiques.
- Refuser en cas de profil différent non expliqué, assertion, timeout, OOM, signal,
  erreur native ou écart d'image/kernel/architecture ; conserver le diagnostic sans secret.
- Aucun test facultatif ignoré ne doit transformer un refus en succès. Ne pas changer
  Landlock/seccomp, ajouter des privilèges, monter les documents ou utiliser development.
- `--rm` supprime seulement ce conteneur de recette à sa sortie. En cas d'arrêt nécessaire,
  cibler son nom vérifié uniquement, jamais le projet de production ; aucun `prune` ou `down`.

Cette recette ne modifie ni `current`/`previous`, ni les volumes, ni PostgreSQL, ni Traefik,
ni les tâches planifiées. Son exécution consomme cependant des ressources de l'hôte :
aucune promesse d'impact nul n'est possible si celui-ci est déjà saturé. La marge préalable
et la fenêtre calme sont des critères d'admission, pas des raisons d'assouplir les limites.

### Retour arrière proposé après un futur déploiement autorisé

En cas d'échec de recette, **ne pas déployer** ; la production actuelle continue, aucun
rollback applicatif n'est nécessaire. En cas de futur échec de déploiement : conserver
bundle précédent et sauvegarde validée, utiliser le rollback manuel par SHA/run compatible
`0006`, sans initialize, migration/downgrade ou restauration automatique des volumes.
Le déployeur ne réactive une application précédente qu'après contrôle de schéma. Le retour
à l'ancien moteur doit accepter explicitement le risque de confinement antérieur ; ne pas
désactiver la nouvelle sandbox comme raccourci. Vérifier ensuite les contrôles HTTPS/CSRF,
connexion/isolation et le cycle de sauvegarde, sans appel IA payant.

## 7. Autorisations nécessaires et décision attendue

1. **Périmètre et corrections** : valider les 53 candidats, le découpage S7–10 et la décision
   RF10-01 (autoriser un correctif CI Windows ou accepter l'exception manuelle), ainsi que
   la portée arm64 et les risques supply chain ouverts.
2. **Commit** : autoriser explicitement la création du/des commits sur un inventaire relu.
   Ce rapport ne donne pas l'autorisation de `git add .` ou d'inclure d'autres fichiers.
3. **Push** : préciser branche/PR ou `main` ; pour `main`, approuver aussi la publication
   automatique des trois images dans la Registry et de l'artefact de release si les tests passent.
4. **Recette distante** : approuver séparément le staging de l'image exacte et le conteneur
   jetable décrit ici. Rien dans cette mission n'autorise son exécution sur le VPS.
5. **Déploiement** : après CI et recette acceptées, autorisation manuelle spécifique à la
   release, sauvegarde vérifiée, politique relative à l'image PostgreSQL et approbation de
   l'environnement production. Inscriptions publiques et activation IA restent hors périmètre.

**Arrêt après ce rapport : attente explicite de la validation de l'administratrice.
Aucun commit, push, workflow distant ou déploiement n'a été réalisé.**

## Annexe — script de recette autonome proposé

Ce script ne fait pas partie de l'application. Il est reproduit pour revue et transfert
manuel futur sous `CHECK_DIR/recipe_probe.py`, sans ajout automatique au dépôt ou au VPS.
Il a été exécuté uniquement dans l'image finale locale
`sha256:fa8ea4538c6365d40a526a78cfeb2bee2300271a6376179fb88dfa6308208e83`,
sur noyau WSL `6.18.54.1-microsoft-standard-WSL2`, ABI 7, Python 3.13.16, UID 1000.

```python
import ctypes
import hashlib
import json
import os
from pathlib import Path
import platform
import socket
import sys
import tempfile

import pymupdf
from backend.config import Settings
from backend.services import extraction


def probe(code, allow=None, before='', maximum=4096, timeout=5):
    prefix = (
        'import os,sys,ctypes,socket,resource; '
        f'sys.path.insert(0,{str(extraction.RUNNER.parent)!r}); '
        'from sandbox import confine;\n' + before + '\n' +
        f'confine(512,2,library_path={allow!r});\n'
    )
    return extraction.exchange([sys.executable, '-I', '-S', '-c', prefix + code], b'', timeout, maximum)


def must_deny(code, **kwargs):
    wrapper = "\ntry:\n" + ''.join('    ' + line + '\n' for line in code.splitlines())
    wrapper += "except PermissionError:\n    print('denied')\nelse:\n    raise AssertionError('unexpected permission')\n"
    assert probe(wrapper, **kwargs).strip() == b'denied'


settings = Settings(_env_file=None, database_url='sqlite://', ai_enabled=False, registration_mode='disabled')
extraction.check_available(settings)
assert os.getuid() != 0
status = Path('/proc/self/status').read_text()
assert 'NoNewPrivs:\t1' in status and 'Seccomp:\t2' in status
with tempfile.TemporaryDirectory(prefix='documind-recipe-') as directory:
    root = Path(directory)
    private = root / 'fake-secret'; private.write_bytes(b'FAKE-PRIVATE')
    original = hashlib.sha256(private.read_bytes()).hexdigest()
    public = root / 'runtime'; public.mkdir()
    runtime = public / 'fake-library'; runtime.write_bytes(b'FAKE-PUBLIC')
    must_deny(f'open({str(private)!r},"rb").read()')
    must_deny(f'open({str(root / "created")!r},"wb")')
    for function in ('open', 'openat'):
        args = f'{os.fsencode(runtime)!r},os.O_RDONLY|os.O_TRUNC'
        if function == 'openat': args = '-100,' + args
        code = ('libc=ctypes.CDLL(None,use_errno=True)\n' +
                f'assert libc.{function}({args})==-1 and ctypes.get_errno()==13\nprint("denied")')
        assert probe(code, allow=str(public)).strip() == b'denied'
    assert runtime.read_bytes() == b'FAKE-PUBLIC'
    # Deliberately preopen only a fake file inside this disposable child.
    code = 'libc=ctypes.CDLL(None,use_errno=True)\nassert libc.ftruncate(fd,ctypes.c_longlong(0))==-1 and ctypes.get_errno()==1\nprint("denied")'
    assert probe(code, before=f'fd=os.open({str(private)!r},os.O_RDWR)').strip() == b'denied'
    os.environ['FAKE_DOCUMIND_SECRET'] = 'FAKE-ENV'
    with private.open('rb') as source:
        os.dup2(source.fileno(), 200, inheritable=True)
        try:
            code = 'assert "FAKE_DOCUMIND_SECRET" not in os.environ\ntry:\n os.read(200,10)\nexcept OSError as error:\n assert error.errno==9\nelse:\n raise AssertionError("inherited descriptor")\nprint("closed")'
            assert probe(code).strip() == b'closed'
        finally: os.close(200)
    for family in ('AF_INET', 'AF_INET6', 'AF_UNIX'):
        must_deny(f'socket.socket(socket.{family},socket.SOCK_STREAM)')
    must_deny('os.fork()')
    code = 'libc=ctypes.CDLL(None,use_errno=True)\nassert libc.prlimit64(0,0,None,None)==-1 and ctypes.get_errno()==1\ntry:\n data=bytearray(600*1024*1024)\nexcept MemoryError:\n print("limited")\nelse:\n raise AssertionError("memory limit")'
    assert probe(code).strip() == b'limited'
    for code, expected, timeout in [('while True: pass', 'worker_failed', 5),
                                   ('import time; time.sleep(10)', 'timeout', .5),
                                   ('os.write(1,b"x"*8193)', 'invalid_output', 5)]:
        try: probe(code, maximum=8192, timeout=timeout)
        except extraction.ExtractionFailure as error: assert str(error) == expected
        else: raise AssertionError('resource failure not detected')
    assert hashlib.sha256(private.read_bytes()).hexdigest() == original
    text = root / 'fake.txt'; text.write_bytes(b'Fictitious recipe text.')
    assert extraction.extract_isolated(settings, text, '.txt', 200, 1000000) == ['Fictitious recipe text.']
    pdfpath = root / 'fake.pdf'
    with pymupdf.open() as pdf:
        pdf.new_page().insert_text((72, 72), 'Fictitious page one.')
        pdf.new_page().insert_text((72, 72), 'Fictitious page two.')
        pdfpath.write_bytes(pdf.tobytes())
    pages = extraction.extract_isolated(settings, pdfpath, '.pdf', 200, 1000000)
    assert len(pages) == 2 and 'page one' in pages[0] and 'page two' in pages[1]
print(json.dumps({'status':'ok', 'kernel':platform.release(), 'abi':ctypes.CDLL(None).syscall(444,0,0,1),
    'python':platform.python_version(), 'uid':os.getuid(), 'checks':'policy, files, truncation, FDs, network, resources, PDF/TXT'}))
```
