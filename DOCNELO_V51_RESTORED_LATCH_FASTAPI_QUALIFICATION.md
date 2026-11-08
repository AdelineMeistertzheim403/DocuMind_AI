# Docnelo V5.1 - Qualification FastAPI avec latch restaure

## Decision au 2 novembre 2026

**Preparation Windows reussie ; qualification du latch reel Debian NON
EXECUTEE dans cette session. Aucun GO sur ce latch n'est encore prononce.**

Le paquet est pret pour une campagne Debian 13 / x86_64 / CPython 3.11.18
strictement in-process. Un succes cible pourra autoriser **uniquement**
`LIMITED_GO_RESTORED_LATCH_FASTAPI_INPROCESS_ONLY`.

**Aucun GO Docker, chaine Backup/Restore globale, S2, Lifecycle 10,
Public Beta ou production**, meme apres un succes de cette campagne.

## Livrables

| Fichier ou dossier | Role |
|---|---|
| `tests/test_recovery_quarantine_restored_latch.py` | Neuf cas, vrai FastAPI et vrai routage conserve |
| `qualification/restored_latch/run_campaign.py` | Lanceur autonome cible et preparation synthetique distincte |
| `qualification/restored_latch/pytest.ini` | Profil sans conftest, sans cache |
| `qualification/restored_latch/build_transfer.py` | Assembleur hors ligne, liste de sources explicite |
| `qualification/restored_latch/test_launcher.py` | Quinze controles des refus E/S et JUnit |
| `DOCNELO_V51_RESTORED_LATCH_DEBIAN_GUIDE.md` | Transfert, installation hors ligne, execution et decision |
| `deliveries/docnelo-v51-restored-latch-fastapi-20261102` | Nouveau transfert verifiable, 42 wheels Linux |
| `qualification/restored_latch/evidence-windows-20261102` | Preuves Windows persistantes, JUnit et inventaires |

Empreinte SHA-256 du **SHA256SUMS externe du nouveau transfert** :

```text
8cccb3511981326e5eb97490c0623c4efaccf56ef080791f588d366ec0a4f25b
```

Cette empreinte doit etre comparee par un canal de confiance avant extraction.
Les sommes ne sont pas une signature. Le paquet sources contient 63 fichiers
copies sur liste explicite, plus le lock et `PACKAGE.json`, soit 65 entrees
inventoriees et son `SHA256SUMS`. Le ZIP wheels contient 42 wheels et son
inventaire. Le transfert externe contient cinq fichiers inventories et
son inventaire.

Le precedent transfert `docnelo-v51-quarantine-debian-20261102` reste intact
et verifie contre son inventaire ; SHA-256 de son `SHA256SUMS` :

```text
e005cdb5a7e8f02d6394c6e529240309e91937145d64a62708cba75080d664c1
```

Il lui manquait le nouveau test, le nouveau profil, le nouveau lanceur
et le nouveau guide. Ses sources applicatives suffisent aux imports
effectivement executes par le nouveau scenario. Ses wheels sont reutilises
octet pour octet, sans telechargement, installation supplementaire ni
modification de l'ancien paquet. Les 55 fichiers `backend` et
`analyseur_documents` communs aux deux ZIP ont ete compares octet pour octet :
aucun changement. Les imports metier differes non executes
restent volontairement exclus : ce n'est pas un paquet de deploiement.

## Ce qui est effectivement construit et observe

Le nouveau test importe le harness de
`tests/test_recovery_quarantine_inprocess.py` sans le modifier.
Avant import de `backend.main`, il isole les sources de Settings,
vide l'environnement, remplace les fabriques SQL et le worker, interdit
connexions, mails, IA, migrations, sous-processus et vrais threads.
L'application globale est donc creee sous isolation, avec un latch
temporaire du harness et sans lancement de son lifespan.

L'instance **cible** est ensuite construite par le vrai
`backend.main.create_app`, avec une vraie instance validee de Settings :
`recovery_state_path` est explicitement le chemin absolu fourni au lanceur.
Le backend et le middleware ne sont pas modifies.

Ordre des middlewares utilisateur verifie :
`LiteBoundary`, `RecoveryQuarantine`, `SecurityAudit`, `IPAdmission`,
`UploadAdmission`, `RequestSizeLimit`.

Le vrai routeur et toutes ses routes sont conserves. Une sentinelle est
ajoutee immediatement devant lui dans la pile ASGI deja construite,
**sans remplacer le routeur ni les middlewares**. Elle ne doit jamais etre
atteinte dans les huit scenarios de refus.

Une observation d'`os.open`, transmettant a la vraie fonction sans simuler
le contenu lu, prouve une ouverture en lecture seule du chemin configure
pendant le lifespan. Chaque requete 503 ajoute une ouverture du meme chemin.
Chaque 403 Lite n'en ajoute aucune : ce refus precede la quarantaine.
Le corps des requetes n'est pas consomme.

## Matrice et resultats Windows

Execution depuis le **paquet extrait et verifie**, sous Windows / CPython
3.13.7 / FastAPI 0.146.0, via `python -I -B ...run_campaign.py --preparation`.
Le mode preparation refuse tout argument de latch externe et fabrique
un latch exclusivement dans son scratch. Il ne valide ni le chemin
Debian, ni les permissions POSIX, ni les wheels Linux en execution.

| Verification | Resultat Windows final |
|---|---|
| Campagne principale | **9 passed**, 0 skip, 0 xfail |
| Controles du lanceur | **15 passed**, 0 skip |
| Inventaire de l'application | **59 couples route/methode HTTP** |
| Sondes supplementaires par scenario | GET inexistant et OPTIONS documents |
| Scenarios de refus | 8 x 61 = **488 requetes refusees** |
| Repartition | **372 HTTP 503**, **116 HTTP 403 Lite** |
| Appels du vrai routeur dans ces huit scenarios | **0** |
| Activite workers/jobs/mail/cleanup dans ces scenarios | **0** |
| Tentatives d'E/S interdites dans la campagne finale | **0** |
| Empreinte et metadonnees du latch synthetique | Identiques avant/apres |
| Verdict conserve | `PREPARATION_ONLY_9_PASS_NO_SKIP` |

Les huit scenarios croisent : standard/Lite, avec/sans en-tetes
d'authentification synthetiques, latch en quarantaine/chemin absent.
Les en-tetes ne demontrent pas une authentification reussie : son execution
doit justement etre interdite en aval. Le chemin absent est toujours
un fichier non cree sous le temporaire du test, jamais dans le dossier
du latch restaure.

Par scenario standard : 61 refus 503. Par scenario Lite : 32 refus 503
et 29 refus 403. Les deux sondes supplementaires sont comprises dans ces
comptes. Tous les couples enregistres sont testes, dont health, login,
inscription, documents, compte, IA, RAG, documentation et OpenAPI.

**Administration HTTP : aucune route enregistree** dont le chemin contient
`admin` ou dont le module endpoint est `backend.account_admin`.
L'inventaire vide est conserve, plutot que de presenter une URL `/admin`
factice comme preuve d'un traitement administratif. La vraie route interne
`/api/v1/internal/upload-admission` est couverte. Aucune affirmation n'est
faite sur l'execution de l'outil d'administration CLI.

Le profil standard active l'IA et configure `extraction_mode="sandbox"` ;
les branches de recuperation jobs/resumes, demarrage worker, mail,
creation du stockage et nettoyage planifie doivent rester inactives.
Le profil Lite utilise sa vraie validation et impose l'IA desactivee.
Une autorite Lite fail-on-access evite toute lecture de registre reel.

Le neuvieme cas est un **controle positif uniquement synthetique** :
le latch du harness, distinct du fichier restaure, passe a `ready`.
Les spies de demarrage et d'arret sont effectivement actives ; la sentinelle
devant le vrai routeur est atteinte. SecurityAudit transforme son exception
en HTTP 500, ce qui est explicitement attendu. Aucun endpoint metier
n'est execute dans ce controle non plus.

Les essais de mise au point precedents ont ete refuses par les gardes
(notamment hostname JUnit et symlinks temporaires pytest) ; ils n'ont pas
ete annonces comme des succes. Le lanceur final utilise un hostname
synthetique, un journal explicite et des temporaires sans symlink.
Le middleware applicatif n'a pas ete adapte pour faire passer les tests.

## Preuves et protections

`evidence-windows-20261102/campaign` contient JUnit, scenarios detailles,
environnement, empreintes des sources et inventaire des preuves.
Le dossier parent ajoute JUnit des quinze controles, `PACKAGE.json`,
le lock et les inventaires du transfert et des wheels, puis un inventaire
exhaustif incluant celui du sous-dossier.

SHA-256 du `SHA256SUMS` racine des preuves Windows :

```text
ed242a73713479b67a5a275ae12a60a36552381d5220a8dd4fd52d5a09fbf8df
```

SHA-256 du `SHA256SUMS` original des sources extraites, egalement conserve
dans `campaign/environment.json` :

```text
1efccdb76e37dbfda9a59d74a4a780e053a32d7b2b7c9dcd0d6a47e2b9629771
```

`scenarios.json` et les proprietes JUnit consignent les methodes, chemins
et modules effectivement enregistres, chaque reponse, chaque lecture,
le chemin configure, l'etat de demarrage et les compteurs downstream.
`environment.json` conserve les snapshots avant/apres : SHA-256, mode,
taille, mtime_ns, inode et device. L'atime n'est pas compare, car une
lecture normale peut le faire evoluer.

SHA-256 du latch **synthetique Windows**, et non du latch restaure :

```text
f781c141a7ccdc5fbe2133cddd864f08686b9f354dd259404ac55267bbe44725
```

Le lanceur installe un audit Python permanent avant pytest et les imports
applicatifs : toute tentative interdite est comptabilisee et fait echouer
la campagne, meme si une exception est interceptee. Les ecritures sont
limitees aux nouveaux dossiers preuves/scratch ; dotenv, sockets/DNS,
SQLite, sous-processus, fork, SMTP et HTTP externe sont refuses.
Le harness ajoute les sentinelles SQL, IA, threads, mails et documents.
C'est une qualification ciblee par isolation et audit, pas un sandbox OS
general destine a executer des dependances hostiles.

La collecte doit contenir exactement neuf cas du fichier autorise ;
skip/skipif/xfail et tout resultat skip/xfail/xpass sont interdits.
JUnit est revalide apres pytest. Les sources sont inventoriees et
reverifiees avant/apres. Le mode cible exige un venv dedie, Debian 13,
x86_64, CPython 3.11.18 et une fermeture installee exactement egale au lock.
Les versions installees Windows sont conservees distinctement ; elles
ne sont pas assimilees a la fermeture Linux.

## Qualification Debian encore requise

Chemin exige explicitement au lancement :

```text
/home/adeline/docnelo-lab/artifacts/qualification/capture-v51/roundtrip-restore/files/recovery-state.json
```

SHA-256 exige :

```text
0a01b17bf9de4fe0d4eccdbae2da89f3345c261622bb8f11a2777c2f53229565
```

Les preuves doivent etre produites dans un **nouveau** sous-repertoire de :

```text
/home/adeline/docnelo-lab/development/v5.1-hardening/quarantine-debian-evidence/
```

Suivre le guide hors ligne. Aucun acces Debian, VPS ou production n'a ete
effectue ici ; le latch reel n'a ete ni lu ni modifie depuis Windows.
Les releases, archives historiques, fixtures et anciennes preuves n'ont
pas ete modifies par ce travail.

Le GO limite reste conditionne a neuf succes sans skip, aux inventaires
conformes, aux vraies lectures du chemin ci-dessus, a zero execution metier
et E/S interdite, au maintien de `quarantined` et du mode 0600, et aux
snapshots avant/apres strictement identiques au SHA-256 attendu.
