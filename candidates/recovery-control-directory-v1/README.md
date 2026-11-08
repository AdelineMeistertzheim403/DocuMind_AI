# Recovery Control Directory v1 - candidat local

Preparation seulement. Aucun deploiement, serveur, conteneur ou service
externe n'a ete lance pour preparer cet espace. Ne jamais utiliser ses
Compose complets avec `up`, `run`, `create` ou une commande de migration.
Les anciens fichiers du depot restent inchanges.

## Contrat versionne

| Parametre | Contrat v1 |
|---|---|
| `RECOVERY_CONTROL_VERSION` | chaine `1`, imposee dans les Compose |
| `RECOVERY_CONTROL_DIR` cote hote | chemin Linux absolu canonique d'un repertoire dedie, stable et preprovisionne |
| `RECOVERY_CONTROL_DIR` cote API | `/run/documind-control` |
| `RECOVERY_CONTROL_SOURCE_DIR` cote API | provenance non secrete de la variable hote, identique a la source absolue du bind |
| `Settings.recovery_state_path` | `/run/documind-control/recovery-state.json`, explicitement configure par `RECOVERY_STATE_PATH` |
| `RECOVERY_READER_GID` | entier decimal explicite, non nul, sans zero initial ; `group_add` identique |
| repertoire / enfant | root:groupe-lecteur, respectivement `0750` / `0440` |
| bind | repertoire entier RO, `create_host_path: false`, sans alias ni cible masquee |

Le format du JSON reste **format 1** ; ce n'est pas une nouvelle version
du middleware. Aucun code backend ou middleware n'est modifie.
Le frontend ne lit pas le latch : ne pas lui ajouter ce volume ou cette
variable. Ses routes locales ne deviennent pas toutes 503.

`RECOVERY_CONTROL_DIR` n'est pas une option ajoutee a `Settings` : c'est
le contrat operateur/Compose. Le backend continue a lire son chemin
absolu `RECOVERY_STATE_PATH`. Le champ de version est controle par les
gardes candidates, pas suppose reconnu par les anciens binaires.
La provenance `RECOVERY_CONTROL_SOURCE_DIR` est derivee par Compose,
pas une seconde source configurable : elle empeche la normalisation
Compose d'un chemin relatif de masquer une entree operateur invalide.
Le backend ignore cette variable de diagnostic ; la garde exige son
egalite exacte avec la source canonique inspectee.

Les quatre Compose dans `source/` sont des fichiers **complets** :
dev, production, VPS Beta et recette Beta. Le bind fichier est remplace,
pas complete par un override. Les anciennes fusions YAML de deux relais
de recette sont explicitees sans changer leurs valeurs. Le test de
projection compare tous les autres parametres aux configurations
originales, y compris les autres volumes, reseaux, limites et securites.
La variable recovery inutilisee de `lifecycle-init` est supprimee.

## Gardes et publication

`source/tools/recovery_control_directory.py` refuse les anciens binds,
les doubles cibles, masques tmpfs, chemins ambigus, sources parentes ou
enfants montees ailleurs (meme RO), `volumes_from`, montages configs/secrets
non revus et volumes nommes externes/driver-bind. Le controle d'inspection
verifie aussi la source, `RW=false`, l'environnement, USER explicite
non-root et le groupe supplementaire. Ce n'est pas une preuve de l'UID
effectif ni une inspection de tous les conteneurs du daemon.

Sur Linux, la garde hote verifie les ancetres sans symlink, proprietaires
root non modifiables par groupe/autres (exception repertoire root sticky),
le repertoire 0750, le fichier regulier 0440 single-link et <=1024 octets.
Le repertoire ne doit contenir que `recovery-state.json`. Son couple
device/inode est conserve entre validations. Sources deployment/data
Docker/volumes et repertoires parents les contenant sont refuses.
Le parseur existant reste responsable du contenu fail-closed.

Les gardes de deployment/backup sont adaptees dans les copies ; leurs
autres controles sont conserves. Le helper partage rejoint les listes
de controleur, de bundle atteste et de comparaison du garde installe.
Les anciens bundles restent lisibles pour diagnostic, mais plus
autorisables operationnellement, meme pour rollback dans ce candidat.
**Aucune nouvelle attestation CI/administrateur n'a ete produite.**

Les `main` et orchestrateurs `execute` deployment/backup sont bloques par
`CANDIDATE_ONLY`, sans option de contournement. Cela est intentionnel :
ce paquet sert aux gardes et au laboratoire, pas au VPS. Le helper
`backup_local.create_backup` valide aussi le nouveau contrat avant toute
verification externe ; il n'est pas execute ici.

Le seul publisher general ajoute, `publish_quarantine`, publie
**uniquement quarantined** : verrou operateur externe preexistant,
temporaire O_EXCL/O_NOFOLLOW, fchown root:groupe, fchmod 0440 avant ecriture
et publication, flush/fsync fichier, replace relatif au fd du repertoire,
fsync repertoire, revalidation d'identite et relecture bornee.
Il n'expose aucune fonction de passage automatique a ready.

Le verrou Beta demeure exactement
`/opt/documind-public-beta/.public-beta-backup.lock`.
`DEPLOYMENT_BASE`, `OPERATOR_LOCK` et `CONTROL_DIR` sont independants ;
la condition du repertoire de release n'est plus derivee de
`CONTROL.parent`. Ne jamais remplacer, deplacer ou supprimer ce verrou.
Le publisher exige le bon proprietaire du verrou, fourni explicitement ;
il ne cree/chown pas un ancien verrou absent ou mal possede.

## Identites et limites

Ne pas supposer UID/GID 1000 : le Dockerfile original utilise USER app
sans identite numerique contractuelle. Choisir un groupe dedie non
privilegie, verifier les UID/GID effectifs dans **chaque image par digest**,
les groupes supplementaires, rootless/userns-remap, traverse, lecture
0440 et refus d'ecriture. Les autres groupes lifecycle restent inchanges.
L'operateur backup doit lui aussi avoir les droits de lecture appropries.
Ne pas regler un refus de lecture avec USER root ou un bind RW.

Les modes/UID POSIX de la campagne Windows sont **modelises**, pas prouves
sur NTFS ni sur un Engine Linux. Les ACL, sous-montages, autres conteneurs
du daemon, AppArmor/SELinux et le mapping userns restent a examiner au labo.
Le repertoire ne doit jamais etre remplace, restaure, nettoye par retention
ou inclus dans un volume de donnees. Seul l'enfant est publie atomiquement.

Les writers Lite existants restent inchanges : certains publient 0644 et
lient leurs chemins a des autorites signees. **Ils ne sont pas declares
compatibles** avec le contrat 0440. Leur integration exige une revision
distincte et de nouvelles preuves ; ne pas recopier une autorite signee
ou reutiliser `public=True` comme moyen de contourner ce contrat.

Les outils restore copies produisent toujours des **artefacts** quarantine
0600. Ce ne sont pas des publishers du controle vivant : conserver
l'archive et le fichier restaure immuables, puis provisionner un nouveau
controle runtime ferme. Voir D19, sans lancer de restauration reelle.

## Executer uniquement la campagne locale

Depuis le depot Windows, avec deux chemins neufs :

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
.\.venv\Scripts\python.exe -I -B .\candidates\recovery-control-directory-v1\run_local.py --preparation --evidence C:\chemin-neuf\evidence --scratch C:\chemin-neuf\scratch
```

Le parent de chaque sortie doit deja exister. Aucune sortie dans le
candidat, les releases, les livraisons, les fixtures ou les artifacts.
Le lanceur verifie INPUTS.json, refuse les fichiers ajoutes/non inventories
et le code incompatible Python 3.11, bloque reseau/DNS/sous-processus/
threads/SQL/SMTP/IA, refuse dotenv reel et toute ecriture hors sorties.
La vraie app globale est isolee **avant** l'import `backend.main`.
Les tests conservent le routeur et tous les middlewares ; seules des
sentinelles aval demontrent fermeture ou controle positif.

Les seules transitions ready preparees sont dans les namespaces
synthetiques des tests ou de `lab/control.py`, ce dernier exigeant un
marqueur root et une autorisation explicite. Aucun de ces outils ne
prend le chemin du latch restaure comme entree de qualification.

Voir `DEBIAN_OFFLINE_PROTOCOL.md` pour les prerequis et D01-D20.
Les fichiers `lab/` ne constituent **pas** des preuves Docker executees.
`INPUTS.json`, `ORIGIN.json`, `CHANGES.json`, `candidate.patch` et
`SHA256SUMS` rendent le correctif verifiable, pas signe ou deployable.
