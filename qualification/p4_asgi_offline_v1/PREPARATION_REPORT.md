# Rapport de preparation P4

## Resultat

**Preparation uniquement ; P4 NON EXECUTE, INCOMPLETE, sans GO.**
Le paquet `qualification/p4_asgi_offline_v1` est un complement autonome.
Ni v1, ni r2, ni r3, ni leurs preuves ne sont modifies. Aucun conteneur,
daemon Docker, latch historique, namespace P2/P3, donnees restaurees reelles,
service applicatif ou production n'a ete utilise par cette preparation.

Les resultats P1 (119), P3-r3 et P3 Docker sont des constats fournis par
l'operateur, non reproduits ici. D11 reste un refus observe, avec code
numerique non conserve : il ne devient ni PASS numerique retroactif, ni
pretexte a relancer D11. Le lecteur P3 arrete doit rester conserve.

## Analyse du contrat fige

References r3 examinees :

- `DEBIAN_OFFLINE_PROTOCOL.md`, section P4 et D03-D09/D11/D12/D14 ;
- `run_local.py`, notamment `verify_inputs`, `audit_guard`, profil monte ;
- `lab/test_mounted_latch.py` et `tests/test_fastapi_directory_transitions.py` ;
- `source/tests/test_recovery_quarantine_inprocess.py` ;
- `source/backend/main.py`, `source/backend/recovery_quarantine.py` ;
- `source/tools/recovery_control_directory.py` et les quatre locks source.

`run_local.py` exige Linux Debian13/x86_64, CPython **3.11.18** dans un
venv, `-I -B`, plugins pytest externes desactives, aucun PYTHONPATH/PYTHONHOME
ou option pytest externe. Le mode monte exige UID non nul, `/.dockerenv`,
GID lecteur effectif et le repertoire `/run/documind-control`.
Il execute **un** test monte, pas les 209 tests host ni P2/P3.
Il inventorie tout r3 avant/apres et autorise les ecritures seulement dans
ses deux nouveaux sous-repertoires evidence/scratch.

Il ne faut pas utiliser `--preparation` pour qualifier Debian ni modifier
`platform.machine` a l'exterieur pour contourner les controles. Sa
neutralisation interne apres controle est celle du harness historique.

La vraie FastAPI, ses routeurs, le vrai lifespan et le vrai middleware
sont importes par le harness, sous Settings et dependances synthetiques.
L'import de `backend.main` inclut sa creation globale **sous ces spies** ;
ce n'est pas le lancement de l'entrypoint applicatif. Aucune execution
`uvicorn`, `backend.main:app`, Compose applicatif ou serveur HTTP n'est permise.
Les requetes HTTPX utilisent ASGITransport en memoire, sans socket.

Le harness interdit reseau, sous-processus, SQL, SMTP, IA et threads reels.
Les workers sont des compteurs positifs, pas des workers operationnels.
Une autorite Lite fail-on-access interdit d'utiliser une autorite signee
ou le writer Lite reel. Ni la chaine signee Lite, ni l'extraction PDF,
ni PostgreSQL ne sont qualifies par P4.

Le test emet `RCD_EVENT startup`, puis attend une commande JSON par ligne.
Chaque `closed` balaie les couples route/methode enregistres deux fois
(non authentifie/authentifie). Standard exige 503 partout. Lite distingue
les routes refusees **403 avant quarantaine**, les autres etant 503.
Aucun corps ne doit etre consomme ni la sentinelle aval atteinte.
`sentinel` exige un processus initialement ready : GET health authentifie,
500 intentionnel et une seule atteinte de la sentinelle devant le vrai
routeur. Ce 500 n'est ni une erreur toleree de production ni un succes metier.

L'etat ferme au startup reste ferme apres publication ready. Un processus
initialement ready peut etre referme puis rouvert dans ce laboratoire
synthetique seulement. EOF, stop sans observation, skip/xfail ou mauvais
HTTP font echouer le test. Un stop valide retourne par le lifespan,
produit resultat/JUnit/manifeste et laisse le conteneur arrete.

## Disponibilite des composants

Le transfert historique FastAPI contient 42 wheels dont les octets et le
lock CP311 concordent. Un wheel PyYAML CP311 existe aussi localement.
La fermeture des **metadonnees Python** de cette selection de 43 wheels
est complete pour CPython3.11.18/Linux/x86_64, extra `psycopg[binary]`
seulement. Ce constat est reproductible sans installation.

Ce n'est pas une fermeture d'image : base Debian13, executable CPython,
stdlib, chargeur, bibliotheques systeme, provenance et approbations sont
absents. Le wheel PyYAML a seulement une empreinte observee localement.
Les locks runtime/build de r3 sont principalement CP313 ; ils ne sont
pas substituables. Details et ecarts dans `DEPENDENCIES.md`.

**Aucun Dockerfile executable ni commande de build n'est livre.** La
methode de fermeture est definie, mais l'assemblage attend des composants
verifies et une revision approuvee. Aucun telechargement, apt, pip reseau,
resolution de tags ou installation n'a ete effectue.

## Outillage et preuves preparees

`offline.py` verifie les inventaires exacts, r3 et ses ancres, le transfert
historique, les wheels sans extraction, les tags CP311, Requires-Python,
Requires-Dist et les DT_NEEDED ELF sans executer ldd. Les sorties nouvelles
sont exclusives. Le build-gate reste ferme.

`p4_control.py` peut, apres autorisation, creer uniquement un nouveau
`/var/tmp/docnelo-p4-<uuid>`. Marqueur root0600 lie a l'inode/device,
verrou stable root0600, controle root:lecteur0750, enfant0440, evidence
UID:GID0700. Il reutilise le publisher quarantine exact de r3 ;
les publications ready/invalides utilisent fichier exclusif, metadata,
fsync fichier, replace, fsync repertoire. Pas de publication FIFO/device.

`check_create.py` prepare un argv non execute, puis controle le JSON
Engine du conteneur **created, jamais demarre**, l'image et les seuls
montages des autres conteneurs. Il refuse les alias, y compris les
parents/alias RO, montages implicites, sockets, volumes anonymes, ports,
environnement inconnu et toute protection manquante. Ce controle
ponctuel ne resout pas les races TOCTOU : gel et revalidation operateur.

`runtime_probe.py` est destine a l'image future, jamais execute ici dans
une image : identites/maps, CPython/OS/venv, RECORD et chaque fichier
installe, imports sans backend, psycopg binary, binaires effectivement
mappes, mountinfo et limites a revoir. Il ne donne qu'une observation.

`collect.py` conserve argv, stdout/stderr, horloges, identites et retour
numerique, meme lors d'un refus. Une interruption laisse un started.json
sans succes. `evaluate.py` recoupe logs Engine horodates, actions/inodes,
plan, inspect avant/apres, capture start/wait, identites, resultat, JUnit
et observations du lanceur. La revue humaine des aspects non automatisables
est obligatoire. Au mieux il produit `PASS_CASE_ONLY`, jamais un GO.
`preservation.py` compare l'inventaire exact des historiques locaux,
sans ecriture dans ces arbres. Cela ne pretend pas avoir inspecte leurs
equivalents Debian ni leurs metadonnees POSIX.

## Blocages restants

1. Base Debian13/x86_64 et CPython3.11.18 binaires verifies et approuves,
   archives, SHA, provenance et image ID local inexistants dans ce paquet.
2. Fermeture ELF systeme/stdlib, proprietaires des paquets, versions,
   hashes et compatibilite ABI non prouves ; 32 ELF wheels inventories
   ne couvrent pas les bibliotheques de la base ni les chargements tardifs.
3. Provenance independante de PyYAML, revue de la selection minimale et du
   bootstrap pip25.2 a obtenir. Aucun hash CP313 ne doit les remplacer.
4. Recette d'assemblage deterministe non approuvee ; build-gate ferme.
5. Image future a observer sous les memes restrictions, pip check offline,
   imports reels et inventaires avant/apres a fournir.
6. UID/GID locaux, rootful sans remap, droits effectifs, absence d'alias,
   sous-montages, propagation et acces candidat a qualifier sur Debian.
7. Autorisations distinctes avant build, create et start non donnees.
8. Les 36 executions de la matrice coeur, leurs preuves Debian et la revue
   finale restent a faire. D14 multi-consommateur est un lot distinct
   decrit mais non automatise par l'inspecteur strict mono-conteneur.

La preuve locale des nouveaux outils est dans `LOCAL_CHECKS.json`.
Elle n'est pas une qualification Linux/Docker/ABI/DAC. Le manifeste
`PRESERVATION_BEFORE.json` et sa verification finale documentent la
conservation des sources et historiques explicitement inventories.
La premiere capture locale echouee reste conservee : Python enfant
ambigu sans packaging et fixture texte CRLF sous Windows. L'interpreteur
du venv existant est ensuite explicite, les copies de fixture binaires,
et les 17 tests finaux passent. Aucun paquet n'a ete installe.
