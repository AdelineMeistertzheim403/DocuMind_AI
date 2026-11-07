# Docnelo Public Beta 10 - Qualification distante de la CI snapshots

Date : 2026-11-07, UTC.

**Decision : NO-GO pour qualifier ce candidat au titre des snapshots Docker.**
Les jobs `python` et `frontend` reussissent, mais `snapshots` echoue et les
preuves JUnit, manifestes de capture et rapports de quarantaine requis manquent.
Le build a froid et le nettoyage du laboratoire sont, eux, verifies.
Aucun correctif ni nouveau lancement du workflow n'a ete effectue.

## 1. Candidat publie et execution unique

Branche : `release/docnelo-public-beta-10-20261106`.
Worktree : `deliveries/docnelo-public-beta-release-20261106/source`.

Commit candidat : **`11e55670e792af9c6fb08ca7fc3a24be08028be9`**.
Parent precedemment qualifie : `733f224dd7881fbd088e04a23726dc4a07c922c1`.
Message : `ci: qualify beta ten Docker snapshot restores on Linux`.
Le trailer Co-authored-by Copilot est present.

Les douze fichiers audites ont ete commites : workflow CI, deux fichiers de
contrats CI, tests snapshots modernises, fixtures du laboratoire, Dockerfile,
Compose et lanceur, ainsi que les quatre rapports historiques de la chaine
de qualification. Aucun dump, archive, secret detecte, donnees de laboratoire
ou artefact temporaire n'a ete inclus.

Le worktree release etait propre apres commit et apres publication.
Le push normal, sans force, a avance la branche distante de `733f224` a
`11e5567`. Le SHA distant a ete compare au SHA local, avec egalite exacte.
Les travaux du worktree principal et ses 59 modifications suivies preexistantes
ont ete preserves.

Seul `ci.yml` a ete declenche manuellement :

```powershell
gh workflow run ci.yml --repo AdelineMeistertzheim403/DocuMind_AI --ref release/docnelo-public-beta-10-20261106
```

Execution : **42368987363**, tentative **1**, evenement `workflow_dispatch`.
Workflow ID : `389532488`, chemin `.github/workflows/ci.yml`.
Lien : https://github.com/AdelineMeistertzheim403/DocuMind_AI/actions/runs/42368987363

`headSha` et `head_sha` correspondent exactement au candidat publie ;
`head_branch` correspond a la branche release. L'inventaire des runs de ce SHA
contient uniquement cette execution. Aucune relance automatique ou manuelle.

Debut du run : `2026-11-07T11:37:51Z`.
Fin/conclusion : `2026-11-07T12:02:28Z`, **failure**, soit 24 min 37 s.

## 2. Jobs et durees

| Job | ID | Conclusion | Duree |
| --- | --- | --- | --- |
| `python` | 128392987219 | success | 24 min 31 s, de 11:37:56 a 12:02:27 UTC |
| `frontend` | 128392987451 | success | 39 s, de 11:37:56 a 11:38:35 UTC |
| `snapshots` | 128392987467 | failure | 2 min 26 s, de 11:37:55 a 11:40:21 UTC |
| `publish` | 128398057278 | skipped | Aucun step execute ; duree non applicable |
| `windows` | - | absent | Aucun job Windows |

La limite Python reste 35 minutes : marge observee de 10 min 29 s.
La limite snapshots est 20 minutes ; son echec n'est pas un timeout.
Les images officielles ne sont pas publiees : `publish` est ignore sur release,
avec zero step, aucun login registry ni build-push officiel, et aucun artefact
de release produit.

## 3. Comptes des suites Python et frontend

Comptes tires des resumes finaux des logs, et non du seul statut des jobs.
Les suites se recouvrent ; leurs nombres ne doivent pas etre additionnes
comme des tests uniques.

| Suite Python | Reussis | Echoues | Ignores | Duree de suite |
| --- | --- | --- | --- | --- |
| Landlock/seccomp Linux natifs | 73 | 0 | 0 | 7,48 s |
| Runtime Docker isole | 73 | 0 | 0 | 12,20 s |
| Suite complete SQLite/POSIX/migrations | 1226 | 0 | 132 | 471,20 s |
| PostgreSQL obligatoire | 57 | 0 | 0 | 47,84 s |
| Controleur root et API d'effacement irrevocablement non-root | 71 | 0 | 0 | 176,60 s |
| HTTPS/SMTP/navigateur public beta | 8 | 0 | 0 | 20,92 s |
| Autorite root native | 2 | 0 | 0 | 0,71 s |
| Autorite non-root native | 1 | 0 | 0 | 1,84 s |
| Suite complete PostgreSQL/pgvector | 1265 | 0 | 93 | 597,69 s |

Les deux suites completes signalent chacune 24 subtests passes.
Les groupes PostgreSQL, effacement, navigateur/mail et ownership obligatoires
conservent `--require-no-skips` et n'ont aucun ignore.
Les preuves critiques de securite, migrations, effacement et restauration
incluses dans le job Python ne presentent aucun echec.

Les suites completes n'activent pas le laboratoire Docker et ignorent donc les
12 scenarios physiques snapshots ; cela ne vaut jamais leur qualification.
Par rapport au candidat precedent, les comptes sont coherents avec trois
nouveaux contrats passes et six ignores supplementaires : les six anciennes
variantes optionnelles deviennent douze cas physiques optionnels dans ces
suites generales. Le job snapshots devait les qualifier separement.
Les motifs de tous les autres ignores ne sont pas exposes individuellement
par les commandes generales `pytest -q` ; leur statut ne doit pas etre masque.

Frontend : **67 tests React passes**, 11 fichiers, zero echec ou ignore
dans le resume, duree 10,05 s. BFF : **54 passes, 0 echec, 0 ignore**,
1,174 s. `tsc -b && vite build` reussit ; Vite annonce 4,54 s.

L'avertissement Starlette/httpx preexistant reste visible dans les suites Python.

## 4. Resultats snapshots et preuves physiques manquantes

Build epingle : success, `11:37:58Z` a `11:38:45Z`, soit **47 s**.
Qualification physique : failure, `11:38:45Z` a `11:40:19Z`, soit **94 s**.
Upload des preuves de diagnostic : success, `11:40:19Z` a `11:40:20Z`.

La progression pytest distante est exactement :

```text
.......FF.......... [100%]
```

Cela donne **19 resultats observes : 17 succes, 2 echecs, 0 erreur de test
affichee par E, 0 ignore affiche par s**. Il existe en plus une erreur de fin
de session, hors de ces 19 resultats, lors de l'ecriture JUnit.
Ces comptes sont deduits de la progression : ils ne sont pas certifies par
un JUnit ni par un resume final, car la generation du rapport a leve une exception.

Erreur certaine conservee :

```text
PermissionError: [Errno 13] Permission denied: '/results/snapshot-proofs.xml'
```

La trace situe l'erreur dans `_pytest/junitxml.py`, `pytest_sessionfinish`,
sur `open(self.logfile, "w", encoding="utf-8")`.
Le bilan du lanceur contient `pytest_exit=1`.

Les fichiers obligatoires suivants sont absents de l'artefact :

- `lab/snapshot-proofs.xml`.
- `lab/capture-closed-false.json`.
- `lab/capture-closed-true.json`.

Ces deux derniers fichiers devaient conserver les manifestes reels et les
rapports de quarantaine des restaurations `closed=false` et `closed=true`.
Les tests correspondants sont, dans l'ordre standard du fichier, les deux
premiers tests physiques apres les sept cas unitaires ; leur export JSON
ecrit egalement dans `/results`.

Le refus d'ecriture explique certainement l'absence de JUnit et constitue
une cause tres probable des deux echecs d'export physique. Cependant, la trace
JUnit interrompt l'affichage des traces individuelles des deux tests :
il n'est pas possible d'affirmer sur ces logs seuls que toutes leurs assertions
anterieures de restauration ont reussi.

**Les deux restaurations PostgreSQL ne sont donc pas attestees ni qualifiees
distamment.** Il en va de meme pour leur conservation documentaire, les cinq
magasins restaures, leurs SHA-256 et leurs rapports de quarantaine interdisant
reprise/ouverture. Le statut positif des autres positions de progression ne
remplace pas les preuves physiques et rapports requis.
Les anciennes preuves locales restent historiques, pas un substitut a ce run.

## 5. Diagnostic UID/GID et permissions, sans correctif

Le lanceur cree le repertoire de resultats sur l'hote avec `Path.mkdir`,
puis le monte dans le conteneur a `/results`.
Le runner Docker est explicitement UID/GID **0:0**, avec **`--cap-drop ALL`**.
Sous Linux natif, UID 0 sans `CAP_DAC_OVERRIDE` ne peut pas ecrire dans un
repertoire appartenant a un autre UID si les bits DAC ne lui donnent pas ce droit.

Sur un runner GitHub-heberge, le repertoire cree appartient au compte hote
`runner`, pas au root du conteneur. Un mode usuel 0755 ne donne pas l'ecriture
a cet UID 0 sans capacites. Les UID/modes exacts du dossier distant n'ont pas
ete inventories par ce candidat ; ils ne sont pas presentes comme mesures
directes de l'artefact. L'explication est corroboree par la trace et le contrat
du lanceur.

Une micro-reproduction locale exclusivement synthetique a utilise un **nouveau**
volume Linux, appartenant a UID/GID 1001 avec mode 0755, puis un conteneur
UID 0 sans aucune capacite :

```text
euid 0 owner 1001 mode 0o755
CapEff: 0000000000000000
PermissionError: [Errno 13] Permission denied: '/results/snapshot-proofs.xml'
```

Le volume de diagnostic a ete supprime et son absence verifiee. Aucun volume
existant ni donnee de production n'a ete utilise. Ce probe reproduit le refus
DAC ; il ne relance pas la campagne ni ne corrige les permissions du candidat.

La validation precedente pilotee depuis Windows/Docker Desktop ne prouvait pas
ce contrat de permissions d'un bind mount Linux natif. L'echec distant met en
evidence une lacune du laboratoire de collecte des preuves, sans preuve d'un
defaut du code metier de sauvegarde/restauration.

Correction future a examiner seulement avec autorisation : definir explicitement
le contrat UID/GID et les droits du **seul repertoire de resultats neuf**, avec
ecriture pour le runner de preuves et lecture pour l'upload hote ; ajouter une
validation Linux native de ce contrat. Ne pas supprimer `cap-drop ALL`, ne pas
ajouter un contournement global DAC et ne pas rendre des repertoires partages
globalement inscriptibles pour obtenir un resultat vert.
Les traces individuelles des deux echecs devront etre recuperees lors d'une
nouvelle campagne autorisee apres correction de la collecte.

## 6. Builds a froid et reproductibilite

Les deux builds terminent avec succes, sans timeout, probleme de hash ni
erreur de resolution des paquets. Aucun tag local du poste n'a ete necessaire.
Le build du runner ne comporte aucune ligne CACHED ; le build PostgreSQL
partage une entree de cache avec les materiaux du meme job, sans cache externe
configure. La duree cumulee de l'etape de build est 47 s.

Versions du daemon et CLI hote : Docker **28.0.4**, linux/amd64, API 1.48.
Compose hote : **v2.38.2**, inventorie dans `compose-version.txt`.
Le build du runner confirme Compose **2.26.1-4** et pg_restore **17.11**.
Les sources Debian datees et verrous Python existants sont conserves ;
aucun contournement de signature, checksum ou TLS n'a ete applique.

Images distantes effectivement construites :

- Runner : `sha256:73f2096e4705a6fcea1c226c493f1132bc8ca3d417004bbcb9740a49d93b7fce`.
- PostgreSQL : `sha256:e3b48e2a9b507b8348ae508bae02a312c86354fce49576903c1d4edea4dce246`.

Les IDs de `images.json` correspondent a ceux du bilan de laboratoire.
Leurs differences avec les IDs locaux ne constituent pas un ecart de
reproductibilite des sources : les builds ne promettent pas une identite
bit-a-bit des couches et horodatages.

Les six empreintes de `source-materials.sha256` correspondent aux fichiers
du candidat : trois verrous, Dockerfile de laboratoire, Dockerfile.db et
manifeste pgvector. L'artefact du job Python confirme aussi les empreintes
sources, contraintes, projet et npm ; couverture des contraintes complete,
liste d'issues vide, Python hote **3.13.18**, x86_64/Linux.
Cet inventaire ne certifie pas independamment les octets npm telecharges ni
l'environnement PEP 517 ; ses indicateurs correspondants restent false.

Le probleme observe concerne donc la portabilite des permissions de collecte,
pas la disponibilite des images ou un echec du build a froid.

## 7. Artefacts, integrite et nettoyage

Deux artefacts, non expires, sont presents :

| Artefact | ID | Taille ZIP | SHA-256 ZIP annonce et verifie |
| --- | --- | --- | --- |
| `documind-snapshot-proofs-11e55670e792af9c6fb08ca7fc3a24be08028be9` | 13572559595 | 17240 octets | `f82f39768c468f17aa4d170fffa4f05a873d891ca75c7faf53e7ccce046cb753` |
| `documind-runner-materials-linux-11e55670e792af9c6fb08ca7fc3a24be08028be9` | 13573780793 | 1941 octets | `bb964147e663daf28581fa7a3d163c4cb6c61d35d7714eadbfef2ad077fa5060` |

Les ZIP ont ete telecharges et leurs digests compares exactement aux digests
GitHub, avant extraction hors depot. L'artefact snapshots contient neuf fichiers :
versions moteur/Compose, `engine.txt`, `images.json`, les deux logs de build,
`source-materials.sha256`, `qualification.log`, `lab/lab-resources.json`.
Il conserve le diagnostic mais pas les preuves de restauration requises.

Laboratoire : `documind-snapshot-2a2102eb91bc`.
`lab-resources.json` confirme :

```text
before: containers=[], volumes=[], networks=[]
pytest_exit: 1
after: containers=[], volumes=[], networks=[]
```

Les logs confirment l'arret/suppression de db, la suppression des trois volumes
et du reseau prive. Le lanceur verifie egalement l'absence du runner de preuves.
Le nettoyage controle a donc reussi malgre l'echec pytest. Aucune ressource du
projet n'est signalee residuelle, aucun nettoyage global Docker n'est utilise.
Cela ne remplace pas les preuves manquantes des bases restaurees individuellement.

Empreintes de fichiers de diagnostic :

- `qualification.log` :
  `cca7b244e3812ad247d9c62eef6ecf2d7e24017b813820a13597bcecf7ac94f2`.
- `lab/lab-resources.json` :
  `83edb5699a5d6590500bde50a9f81159808e5efbc4450093295ad17fa44bff49`.
- Log CI complet collecte :
  `017587d6a190b663e8d4cf98a9ab57011dea34c034ed49cfac65af829db33441`.

Les fichiers sont conserves dans le dossier de session hors depot :
`C:\Users\Adeline\.copilot\session-state\12ffa574-cb17-4a50-a650-3af684ea07ab\files`,
notamment `snapshot-remote-proofs`, `snapshot-remote-runner-materials`,
`snapshot-remote-full-ci.log` et `snapshot-remote-dac-diagnostic.json`.
Les archives et logs ne sont pas ajoutes au commit.

## 8. Required checks de main et restrictions

Lecture de la protection actuelle de `main` :
`strict=true`, required checks **`python` et `frontend`**, app GitHub Actions
**15368**. Les regles de rulesets applicables retournees sont vides.
**`snapshots` n'est pas actuellement un required check de merge.**

Les check runs du candidat sont effectivement : python success, frontend
success, snapshots failure, publish skipped, tous app 15368.
La dependance `publish.needs=[python,frontend,snapshots]` et la conclusion
globale failure bloquent la qualification/publication. Les seuls checks requis
de main ne suffisent pas a rendre un merge dependant de snapshots ; aucune
modification de protection n'est effectuee.

Aucun merge main, lancement deploy.yml, acces VPS, deploiement, publication
d'image officielle ou ouverture des inscriptions. Les gardes de sauvegarde
et restauration restent intactes. Aucun correctif n'est applique apres l'echec.
Le HEAD local/distant reste le candidat publie ; ce nouveau rapport est conserve
localement non commite, sans second push.

## 9. Decision et conditions de reprise

**NO-GO** pour declarer les snapshots qualifies sur
`11e55670e792af9c6fb08ca7fc3a24be08028be9` et pour poursuivre sur la base
d'une CI supposee entierement verte.

Les acquis sont : Python/frontend reussis, build epingle a froid reussi,
artefact de diagnostic conserve, integrite des fichiers/materiaux verifiee,
nettoyage du projet confirme, absence de publication officielle.
Les blocages sont : deux echecs observes, erreur de fin de session JUnit,
preuves des deux restaurations/quarantaines absentes.

Une nouvelle autorisation sera necessaire pour corriger exclusivement
l'infrastructure de collecte, verifier ses permissions sous Linux natif,
creer/publier un nouveau candidat et lancer une nouvelle CI. Aucune relance
du run existant n'a lieu. L'ajout manuel du required check snapshots a main
reste une operation distincte, non effectuee ici.
