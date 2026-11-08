# Docnelo V5.1 - Recovery Control Directory r3 : examen uniquement

## Decision et contexte

**Proposition pour examen uniquement. Aucun remplacement de v1/r2,
aucun GO P3 operationnel, Docker, S2, Lifecycle 10, Public Beta ou production.**
Nouveau candidat : `candidates/recovery-control-directory-v1-r3`.
Aucun Docker, serveur, nouveau namespace synthetique, changement de
permissions existantes ou operation sur le latch P2 n'a ete execute.

L'operateur rapporte un preflight Debian13/Compose2.26.1-4 r2 refuse
avec `REFUSED_NO_DOCKER_ACTION` et l'erreur de divergence du profil.
Le champ natif est la chaine `"134217728"` pour la declaration source
`128m`. Cette observation est fournie, non reproduite par Docker ici.

## Verification du chemin et correctif exclusif

Chemin conserve : `preflight_p3.py` verifie INPUTS.json, puis
`validate_documents()` verifie SHA source et parametres, appelle
`_validate_source()`, puis `_validate_rendered()`, et termine par P2,
garde hote, identite device/inode et SHA du probe.

Dans r2, `_validate_rendered()` reconstituait les binds valides dans
une copie et appliquait les gardes historiques, puis normalisait
uniquement `api.get('mem_limit') == 134217728`.
La chaine native ne remplissait pas cette condition et restait
differente de `'128m'` dans la comparaison finale du profil.
De plus, une egalite numerique simple ne suffit pas a exclure un float
exact ; r3 impose donc un couple type/valeur, sans conversion generique.

| Valeur rendue | Type JSON/Python exact | Decision r3 |
|---|---|---|
| `"128m"` | string / str | accepte |
| `134217728` | nombre entier / int | accepte |
| `"134217728"` | string / str | accepte |
| `134217728.0`, notation exponentielle numerique | float | refuse |
| toute autre valeur/type ou champ absent | autre | refuse |

Seules ces trois representations sont normalisees vers `'128m'`
**dans la copie interne du rendu**. Pas de int(), float(), trim,
changement de casse, unite alternative ou arrondi. Le YAML source
approuve reste `mem_limit: 128m` ; il n'est pas normalise ni modifie.
Le JSON brut conserve exactement son type, ses octets et son empreinte.
Le seul autre changement du module est le tag de preuve `v1-r3`.
Aucune autre normalisation ou regle de securite n'est modifiee.

## Controles conserves

Le source doit conserver chaque `create_host_path: false` booleen
explicitement present, les binds RO et le profil lecteur complet.
Le rendu doit concorder avec les sept parametres approuves, UID/GID
non-root, groupe lecteur, chemins, image ID, securites et limites.
`bind: {}` seul ne donne jamais une autorisation ; la garde historique
`validate_compose()` reste byte-identique et le refuse seule.

P2, source existante sans creation, ancetres, modes root:groupe 0750/0440,
identite du repertoire, exclusion DockerRootDir, probe et SHA restent
obligatoires. Alias, RW, heritage et contradictions restent refuses.
Le preflight ne cree aucune source ni verrou, ne publie aucun etat,
ne change aucun mode et ne lance aucune commande Docker.
Son resultat reste `REVIEW_ONLY_SOURCE_RENDER_HOST_PREFLIGHT`,
avec `p3_go=false`, `container_created=false`, `container_started=false`.

## Fichiers precisement concernes, par rapport a la copie r2

| Chemin dans r3 | Nature |
|---|---|
| `source/tools/preflight_recovery_compose.py` | normalisation mem_limit stricte et tag de revision |
| `run_local.py` | ajout du quatrieme fichier de tests ; obligation des 51 cas r2 en plus des 119 P1 |
| `README.md` | portee r3, representations admises, provenance des inventaires et commande locale |
| `DEBIAN_OFFLINE_PROTOCOL.md` | reprise P3-r3, nouveau constat fourni, types admis/refuses, rendu brut conserve |
| `tests/test_compose_memory_normalization.py` | nouveau, 39 cas |
| `BASELINE_R3.json` | nouveau, ancrage v1/r2 et artefacts historiques |
| `build_r3_inventory.py` | nouveau generateur r3 a perimetre de modification borne |
| `REPORT_R3.md` | nouveau, present rapport |
| `REVISION_CHANGES.json` | regenere, delta r2 -> r3 et SHA avant/apres |
| `revision.patch` | regenere, patch r2 -> r3, non applique aux candidats figes |
| `PRESERVATION_VERIFIED.json` | regenere, attestations de conservation |
| `INPUTS.json`, `SHA256SUMS` | regeneres, integrite du candidat r3 |

Hors candidat : nouveau `DOCNELO_V51_RECOVERY_DIRECTORY_R3_REPORT.md`,
nouvelles preuves sous `qualification/recovery_directory_r3/` et
nouveau transfert `deliveries/docnelo-v51-recovery-directory-candidate-v1-r3/`.
Aucun de ces chemins ne remplace un livrable anterieur.

Les **248 fichiers v1**, **257 fichiers r2** et **70 artefacts
historiques** sont controles par SHA, avec verification des jeux de
fichiers des candidats et des repertoires de preuves/transfert anterieurs.
Dans la copie r3, **248 fichiers r2 non concernes restent byte-identiques** :
trois fichiers de tests historiques (119 + 51), tous les Compose
applicatifs et labo, publishers, middleware, backend, outils P2, lecteur,
wrapper et dependances/locks copies. Les fichiers de provenance v1/r2
restent inchanges et ne sont pas presentes comme de nouvelles preuves.
Ne pas lancer les generateurs herites dans r3.

## Resultats Windows effectivement obtenus

Campagne `qualification/recovery_directory_r3/windows-preparation-001` :
**209 passes, 0 echec, 0 skip, 0 xfail ; aucune E/S interdite enregistree**.
Windows / CPython **3.13.7**, pas Debian / CPython 3.11.18.
JUnit, cas detailles, stdout pytest, resultat, versions/RECORD des
dependances, inventaire d'entree et SHA sont conserves.

| Groupe | Cas passes |
|---|---:|
| P1 configuration/contrat, fichier inchange | 77 |
| P1 vraie application FastAPI ASGI, fichier inchange | 42 |
| Source/rendu/P2/hote r2, fichier inchange | 51 |
| Trois couples type/valeur approuves, preflight complet | 3 |
| Valeurs voisines, variantes textuelles et types incorrects | 24 |
| Champ mem_limit absent | 1 |
| Nombres JSON exponentiels exactement equivalents mais floats | 2 |
| Source modifiee en octets entiers/chaine/flottant toujours refusee | 3 |
| Chaine native ne contournant pas source false, RO, P2 ou hote absent | 4 |
| CLI, rendu brut chaine preserve et aucune autorisation Docker | 1 |
| Conservation SHA de tous les fichiers r2 non concernes | 1 |
| **Total** | **209** |

Les 24 refus couvrent entre autres 134217727/134217729 en int/chaine,
zero, float exact, true/false/null, liste/dictionnaire, zeros initiaux,
signe plus, espaces, decimal/exposant textuels, casse/unites alternatives,
separateur souligne, retour ligne et chiffres Unicode.
Les 119 cas P1 et 51 cas r2 sont imposes a la collecte, sans skip/xfail.
Le lanceur audite et bloque reseau/DNS/sous-processus/threads/SQL/SMTP/IA,
dotenv reel et ecritures hors nouveaux scratch/evidence.

Les nouveaux cas reutilisent le fixture r2 sans le modifier.
L'hote/P2 positifs sont modelises ; le CLI lit ses entrees reelles dans
un scratch neuf mais utilise le probe/controle hote synthetiques.
Cela ne qualifie pas les permissions Linux, l'image ou le daemon.
Le lanceur analyse la syntaxe Python avec grammaire 3.11 ; ce n'est
pas une execution du runtime CPython 3.11.18.

## Debian, transfert et limites a qualifier

Lire `DEBIAN_OFFLINE_PROTOCOL.md`, section P3-r3, apres examen et
autorisation distincte. Extraire r3 dans un nouvel emplacement de
development ; verifier les manifestes et leurs ancres par un canal
independant. Aucune image, fermeture wheelhouse CP311 supplementaire
ou dependance nouvelle n'est fournie. Les versions et RECORD captures
ne constituent pas une verification de tous les binaires installes.

Reprendre le LAB existant en lecture seule : ne pas reprovisionner,
publier, chmod, remettre ready ou modifier le marqueur P2.
Ecrire uniquement dans une evidence Debian neuve sous
`/home/adeline/docnelo-lab/development/v5.1-hardening/quarantine-debian-evidence/`.
Employer le YAML approuve intact, le rendu Compose natif intact, les
sept parametres explicites, le marqueur P2 et les SHA approuves.
Ne pas transformer le JSON rendu en fichier Compose.

Restent **NON EXECUTES ici** : preflight r3 natif Debian13/Compose2.26.1-4,
CPython3.11.18, fermetures offline, droits effectifs UID/GID/userns,
inspections Engine/RO/DAC, absence d'alias dans les conteneurs locaux,
creation avec source absente D11 et propagation D01-D20.
Toute normalisation native supplementaire non approuvee doit refuser.
DockerRootDir doit encore etre confirme par une preuve locale revue.
Le risque TOCTOU entre preflight/create impose gel operateur,
reverification des hashes/identites et inspection avant tout start,
uniquement dans une campagne future autorisee.

Les manifestes SHA ne sont pas des signatures. La comparaison de
documents et les tests Windows ne prouvent ni le comportement Engine
ni l'autorisation de creer/demarrer un conteneur. **Examen uniquement.**
