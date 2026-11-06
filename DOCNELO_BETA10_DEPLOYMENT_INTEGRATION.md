# Docnelo beta 10 - integration du deploiement atteste

Date : 2026-11-06.
Branche : `release/docnelo-public-beta-10-20261106`.
Base de cette intervention : `b22920a96d088d406055d7ea53c031e00f290f09`.
References : `DOCNELO_BETA10_PRODUCTION_PREPARATION.md` et
`DOCNELO_BETA10_ERASURE_IMPLEMENTATION.md`.

**GO local pour le contrat d'integration. NO-GO pour deployer ou ouvrir la
production sans les validations restantes.** Le blocage bundle/overlay du rapport
precedent est resolu par cette livraison, pas par une intervention sur le VPS.

## 1. Architecture retenue

Le bundle ferme contient maintenant `compose.erasure.yaml`, copie par la CI
**avant** la creation de `security-attestation.json`. Son SHA-256 est verifie
comme celui de tous les autres fichiers. Les images restent epinglees par
digest, avec controle du SHA Git et du profil de securite.

Le controleur utilise toujours un seul projet `documind-prod` :

```text
docker compose ... -p documind-prod -f BUNDLE/compose.production.yaml
```

Sans configuration d'effacement, la composition de production ne change pas.
Avec provisionnement complet et approuve, la meme commande comporte aussi :

```text
-f BUNDLE/compose.erasure.yaml
```

Ce n'est ni un second projet, ni un Compose concurrent, ni une modification du
bundle apres attestation. Les labels `project.config_files` doivent correspondre
a la liste ordonnee exacte des fichiers selectionnes. Les conteneurs API/BFF
sont recrees lors du deploiement pour rafraichir cette provenance, meme si les
images sont identiques. Cela ne recree ni les volumes ni les donnees PostgreSQL.

L'activation exige les quatre variables operateur suivantes, ensemble :

| Variable | Valeur a fournir explicitement |
|---|---|
| `ERASURE_AUTHORITY_HOST_DIR` | Repertoire absolu Linux, racine de l'autorite independante |
| `ERASURE_REQUESTS_HOST_DIR` | Repertoire absolu Linux prive des demandes |
| `ERASURE_INSTANCE_ID` | UUID canonique deja initialise et approuve |
| `ERASURE_APPLICATION_UID` | UID non-root reel de l'image API approuvee |

Ne pas ajouter des variables vides pour representer une absence de
provisionnement. Les chemins applicatifs sont fixes par l'overlay :
`/run/docnelo-erasure/authority` et `/run/docnelo-erasure/requests`.
Une declaration contradictoire de ces chemins est refusee.

Avant selection de l'overlay, le controleur exige le bundle courant complet,
le schema cible `0008`, les checksums valides et l'approbation independante dans
`/etc/documind-ai/release-security-trust.json`. Une attestation auto-produite
ou un manifeste seul ne donnent aucune autorisation.

Avant toute premiere activation applicative, une liaison durable est ecrite
dans `ROOT/var/erasure-deployment.json`, hors du bundle, en mode `0600`.
Elle lie les deux repertoires, l'UUID et l'UID. Ecriture exclusive, fsync du
fichier et des repertoires ; aucune substitution automatique. Toute suppression
de configuration ou modification de cette liaison est ensuite refusee.
Une ecriture interrompue/invalide laisse un refus, pas un retour silencieux
au fonctionnement sans protections. Ne jamais supprimer cette liaison pour
debloquer un deploiement.

Les inventaires attestes historiques restent reconnus pour le rollback
seulement. Ils ne deviennent pas des cibles de nouveaux deploiements.
Un rollback exige toujours schema compatible, controleur compatible, garde
de sauvegarde installee et approbation independante. Une liaison d'effacement
active interdit un retour a une composition sans ces protections.

## 2. Fichiers modifies

| Fichier | Modification |
|---|---|
| `compose.erasure.yaml` | Abandon de toutes les capabilities API ; montages existants conserves |
| `tools/release_security.py` | Inventaire atteste, selection stricte, liaison durable, controles des montages/permissions et conteneurs |
| `tools/deploy_production.py` | Selection dans le meme projet, probe non-root, quota ferme, provenance et reprise protegees |
| `tools/backup_production.py` | Meme selection et verifications pour la sauvegarde et la reprise courantes |
| `.github/workflows/ci.yml` | Overlay copie avant attestation ; qualification native d'integration obligatoire |
| `.github/workflows/deploy.yml` | Inventaires courant/historiques explicites, sans relachement des approbations |
| `Dockerfile` | Outils et contrats copies dans la cible de tests uniquement |
| `tests/test_deployment.py` | Recreation applicative sans recreation des dependances |
| `tests/test_release_security.py` | Bundle courant/historique, CI et configurations invalides |
| `tests/test_erasure_deployment.py` | Nouveaux tests natifs d'integration et de refus |
| Ce rapport | Resultats, limites et publication future |

`compose.production.yaml`, le moteur d'effacement, les migrations, les sources
frontend/BFF et les donnees existantes ne sont pas modifies.
La cible Docker finale conserve `USER app` ; les copies d'outils de test
n'entrent pas dans cette cible.

## 3. Verifications de securite

- Autorite montee en bind **lecture seule**, proprietaire root, non modifiable
  par groupe/autres ; demandes en bind **lecture/ecriture**, proprietaire UID
  applicatif, privees `0700`. `create_host_path=false` pour les deux montages.
- Refus des chemins relatifs/ambigus, liens symboliques, ascendances non fiables,
  repertoires imbriques, sources sous la racine de deploiement ou les donnees
  Docker. Aucun repertoire ni UUID/secret/autorite de production cree.
- API non-root, racine du conteneur en lecture seule,
  `no-new-privileges:true`, `cap_drop: [ALL]`, aucune capability ajoutee,
  aucun socket Docker, service root ou endpoint administratif ajoute.
- Probe en processus applicatif non-root : UID reel/effectif/sauve conforme,
  impossibilite de regagner root, verification des deux headers d'installation
  existants via `Authority.check()`. Cette probe ne cree pas de preuves.
  Elle precede la maintenance applicative et est rejouee avant le demarrage
  et un eventuel redemarrage de repli.
- Absence totale de configuration : production inchangee et effacement non
  disponible. Configuration partielle/incoherente, autorite absente, mauvais UID,
  montage impropre ou approbation absente : refus du deploiement/reprise.
- Volumes documents/base/lifecycle, verrou de sauvegarde et latch de quarantaine
  historiques conserves. La sauvegarde refuse les montages ou labels divergents ;
  sa reprise reste `--no-recreate --pull never`, sans application d'un nouveau
  montage par un simple redemarrage quotidien.
- Aucun SQL d'ouverture ajoute. Une activation avec effacement exige un quota
  SQL ferme et coherent, controle avant les changements et avant demarrage.
  `REGISTRATION_MODE=disabled` reste la configuration de preparation.

L'effacement lui-meme conserve son protocole existant : demande persistante,
revue d'identite, autorisation root explicite liee au plan, maintenance/quarantaine,
execution, puis verification independante. Le controleur de deploiement ne
realise aucune de ces autorisations a la place de root.

## 4. Tests locaux et resultats

| Qualification finale | Resultat |
|---|---|
| Linux/PostgreSQL : moteur, integration, permissions root et approbation reelle | **73 reussis, zero saut** |
| Windows : deploiement, attestation, sauvegardes, monitoring et retention | **430 reussis, 46 sauts attendus** |
| Docker Compose, configuration sans effacement | Valide ; trois montages API historiques |
| Docker Compose, configuration avec overlay | Valide ; deux binds supplementaires ; services DB/BFF et volumes inchanges |
| Compose avec variable de montage requise absente | Refuse ; aucun repertoire ou service cree |

Les 73 cas comprennent les 30 regressions d'effacement documentaire/de compte
(dont interruptions SIGKILL, reprise et refus de faux succes), 41 cas
d'integration et deux preuves d'approbation/permissions root.
Les 46 sauts Windows correspondent aux conditions PostgreSQL/POSIX et sont
distincts du groupe Linux obligatoire sans aucun saut.

Les refus verifies couvrent notamment : overlay manquant ou modifie apres
attestation, digest d'image divergent, bundle non atteste/non approuve,
configuration partielle, UID root/incoherent, autorite absente ou appartenant
a l'application, demandes trop ouvertes ou appartenant a root, lien symbolique,
montage inscriptible de l'autorite, demandes en lecture seule, auto-creation
de sources, privileges supplementaires, environnement vivant divergent,
suppression/reassociation de la liaison et reprise quotidienne avec mauvais
montage.

Environnement Linux utilise uniquement pour cette qualification :

```text
Image locale de preuves : docnelo-erasure-integration-proofs:20261106
ID : sha256:cef8ebde03010ddf7515913d4f2c5b89c7a616a85dbef422e19c2a966840c1d9
PostgreSQL : conteneur jetable sans port publie, stockage tmpfs
Tests : conteneur root separe, racine readonly, stockage de test tmpfs
API de test : UID reel/effectif/sauve abandonne definitivement, non-root
```

Commande finale executee dans ce conteneur isole :

```bash
python -m pytest -q -p no:cacheprovider --require-no-skips \
  --basetemp=/tmp/final-qualification \
  tests/test_standard_erasure.py tests/test_erasure_deployment.py \
  tests/test_release_security.py::test_real_root_registry_permissions_and_symlinks \
  tests/test_release_security.py::test_real_approval_and_installed_backup_guard_end_to_end
```

La CI inclut desormais aussi `tests/test_erasure_deployment.py` dans le groupe
root/Linux/PostgreSQL obligatoire. Le parcours beta/e-mail/navigateur,
frontend, BFF et controles de securite existants restent requis.
Ils n'ont pas tous ete rejoues localement pendant cette intervention :
la CI distante sur le nouveau HEAD reste a executer.

L'avertissement de deprecation httpx/Starlette est non bloquant.
Le repertoire temporaire Windows par defaut etant inaccessible, les executions
concluantes ont utilise des repertoires de test dedies. Une fixture de test
initiale trop ouverte a ete corrigee, sans affaiblir le controle de permissions.

## 5. Preparation operationnelle encore requise

Ces etapes sont **mutantes et non executees**, avec autorisation distincte :

1. Publier et qualifier la release ; obtenir ensuite l'autorisation de promotion
   et les artefacts officiels de la CI main. Verifier leurs digests et leur
   provenance, puis obtenir la revue root independante. Ne pas attester un
   bundle modifie localement apres sa publication.
2. Deployer d'abord le nouveau contrat **sans variables d'effacement** si
   l'installation actuelle utilise un bundle anterieur a cette integration.
   Cela conserve le fonctionnement sans autorite. Les deux gardes installees
   dans `ROOT/ops` doivent correspondre exactement au candidat approuve :
   `backup_production.py` et `release_security.py`, sous administration root.
3. En preproduction Linux, puis sur VPS seulement apres accord, fermer et
   verifier les inscriptions, passer en maintenance/quarantaine et suspendre
   les producteurs/reprises automatiques. Relever les montages/UID effectifs ;
   ne pas deduire leurs valeurs des chemins du laboratoire.
4. Provisionner et initialiser explicitement l'autorite independante et les
   demandes avec le protocole du rapport d'effacement. Aucune valeur inconnue
   ni politique de conservation ne doit etre inventee.
5. Ajouter ensemble les quatre valeurs approuvees dans la configuration
   operateur, sans modifier le bundle. Effectuer un nouveau deploiement approuve
   de ce contrat ; la probe et les controles doivent reussir avant activation.
   Un changement de configuration n'est pas activable par une reprise de
   sauvegarde : celle-ci refusera les anciens conteneurs incompatibles.
6. Verifier les montages reels, le quota cumulatif ferme, la persistance de la
   liaison, la sauvegarde/reprise, puis qualifier un effacement et sa verification
   independante en preproduction. Preserver les utilisateurs existants.

La composition a ete compilee localement ; **aucun deploiement complet de
la stack officielle ni exercice VPS n'est revendique ici**.
L'inventaire de l'installation existante, la migration autorisee vers `0008`,
SMTP/DNS/HTTPS, les documents juridiques et les durees de conservation restent
les portes du rapport de preparation precedent.

La liaison de deploiement n'est pas le journal root d'effacement et ne le
remplace pas. Preserver les deux hors des restaurations SQL/documents.
Le journal root et sa copie operateur independante restent necessaires pour
eviter la reintroduction de donnees effacees apres restauration. La verification
active ne vaut pas destruction de WAL, backups, logs, SSD ou copies externes.
Les delais, obligations de conservation et controles de destruction de ces
copies restent a approuver ; aucun ordonnanceur ni purge de sauvegarde ajoute.

## 6. Publication et CI sur le HEAD exact - non executees

Les commandes suivantes sont pour PowerShell, depuis le depot historique.
La premiere partie est une **lecture locale sans effet** :

```powershell
$release = 'deliveries\docnelo-public-beta-release-20261106\source'
$branch = 'release/docnelo-public-beta-10-20261106'
$repo = 'AdelineMeistertzheim403/DocuMind_AI'
if ((git -C $release branch --show-current) -ne $branch) { throw 'Wrong branch' }
if (git -C $release status --porcelain=v1) { throw 'Dirty delivery worktree' }
$sha = (git -C $release rev-parse HEAD).Trim()
git -C $release --no-pager log -1 --format='%H %s'
```

**Mutation GitHub, seulement apres nouvelle autorisation** :

```powershell
git -C $release push --set-upstream origin "HEAD:refs/heads/$branch"
if ($LASTEXITCODE -ne 0) { throw 'Push failed' }
$remote = git -C $release ls-remote --heads origin "refs/heads/$branch"
if ($LASTEXITCODE -ne 0 -or -not $remote) { throw 'Remote branch unavailable' }
if (($remote -split '\s+')[0] -ne $sha) { throw 'Published SHA mismatch' }
gh workflow run ci.yml --repo $repo --ref $branch
if ($LASTEXITCODE -ne 0) { throw 'CI dispatch failed' }
```

**Lectures GitHub de suivi**, sans deployment :

```powershell
gh run list --repo $repo --workflow ci.yml --branch $branch --commit $sha `
  --event workflow_dispatch --limit 5 `
  --json databaseId,headSha,status,conclusion,url
# Apres identification manuelle du run correspondant :
# gh run view RUN_ID --repo $repo --json headSha,status,conclusion,jobs,url
```

Ne valider qu'un run dont `headSha` est exactement `$sha`, avec tous les jobs
requis reussis. Si la branche avance entre publication et dispatch, rejeter
un run portant un autre SHA. Un push de branche seul ne lance pas cette CI.
Le job `publish` reste exclu sur cette branche ; aucune image officielle
ni bundle publiable n'est produit par cette simple qualification.

**Ne pas merger ni dispatcher la CI sur main sans accord incluant la publication
automatique d'images.** Le workflow de deploiement reste manuel, limite a main,
avec environnement production protege, CI main reussie du SHA exact et confiance
root independante sur l'hote. Aucune de ces autorisations n'est accordee par
la redaction des commandes.

## 7. Checklist finale

- [x] Overlay inclus avant attestation, inventaire ferme et digests verifies.
- [x] Meme projet Compose ; fonctionnement sans autorite conserve.
- [x] Permissions, identite non-root, refus et liaison persistante qualifies.
- [x] Compatibilite des gardes de sauvegarde/reprise couverte.
- [x] Tests locaux concluants ; aucun changement de production.
- [ ] Publication autorisee et CI distante verte sur le HEAD exact.
- [ ] Integration qualifiee sur la topologie de preproduction cible.
- [ ] Inventaire VPS, gardes root et autorite effectivement provisionnes/approuves.
- [ ] Migration/SMTP/HTTPS/juridique/conservation valides.
- [ ] Deploiement puis ouverture des inscriptions autorises separement.

**Aucun push, merge, publication d'image officielle, acces VPS, migration,
deploiement ou ouverture SQL n'a ete effectue. Aucun chantier VSS A/B repris.**
