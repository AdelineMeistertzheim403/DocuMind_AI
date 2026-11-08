# Perimetre de preservation - 2026-11-05

**PLAN_READY_CAPTURE_BLOCKED. Plan seulement, aucune sauvegarde realisee.**
Les dix livrables de phase 1 ont ete lus. Aucun de leurs fichiers n'est modifie.
Les chemins ci-dessous sont relatifs a la racine du depot, sauf indication.
Les inventaires futurs exhaustifs contenant des noms prives resteront chiffres,
hors Git; ce document ne contient pas de contenu de cle, de base ou de document.

## 1. Etat reobserve avant creation des sept documents

Releve Git : `2026-11-05T13:29:56.919047+00:00`.

| Mesure | Constat |
|---|---|
| Branche | `branding/docnelo` |
| HEAD | `1bc1a4a5bb49395acabdce5e7604d1a6b97dea61` |
| Suivis / modifies / changements indexes | 338 / 44 / 0 |
| Non suivis | 4 202 entrees, dont les dix livrables de phase 1 |
| Statut total | 4 246 entrees, dont deux racines de worktrees non suivies |
| References communes enumerees | 96 |
| Worktrees enregistres | 5, dont la racine |

Les 4 192 entrees citees dans la mission sont l'etat anterieur aux dix livrables
de phase 1. Les 4 056 entrees des quatre familles de preuves sont egalement un
compte historique avant ces livrables, pas le compte d'un futur point de capture.
Apres les sept documents de ce plan, l'attendu sans autre ecriture est 4 209
entrees non suivies, soit 4 253 au total. Refaire le releve au vrai point de capture.

## 2. Matrice de couverture obligatoire

| Objet | Perimetre a capturer, sans filtrage Git |
|---|---|
| Historique Git | Tout `.git`, objets loose/packs, refs, logs/reflogs, HEAD, index, config, info/exclude, hooks comme donnees inertes, worktrees administratifs et autres fichiers presents |
| Worktree principal | Tous les fichiers et repertoires accessibles, caches compris au premier gel; modifications suivies, non suivis, ignores et fichiers caches Windows |
| Quatre worktrees imbriques | Leurs repertoires physiques complets, y compris ignores, fichiers `.git` et tous leurs fichiers d'etat; ne pas les reduire aux seuls fichiers suivis |
| 44 modifies | Liste exhaustive dans `..\repository-hygiene-audit-20261105\GIT_STATUS_INVENTORY.md`; sauvegarder les bytes courants et leur index, pas seulement un diff |
| Non suivis | Code, tests Lite/hardening, scripts temporaires, modeles, documents d'audit et familles deliveries/exports/candidates/qualification |
| Ignores non reproductibles | `.env`, configurations privees, sauvegardes, dumps, donnees locales, archives, cles, candidates et preuves masquees par info/exclude |
| Preuves scellees | Sources, materiaux offline/wheels, archives, recus, manifestes, ancres, rapports B1-B7/P4 disponibles et decisions NO-GO; conservation additionnelle distincte |
| Prives opaques | Images TAR, ZIP, dumps, bases, documents utilisateurs eventuels et historique Git contenant potentiellement du prive; pas de publication de leur contenu |
| Contexte externe | Configuration effective issue de deux fichiers externes et de parametres de processus; inventorier les dependances pertinentes en prive avant autorisation d'inclusion |

Le parcours physique de preparation inclut `.git` et les worktrees internes une
seule fois, ne suit pas les liens et ne lit pas les donnees des bases.
Les fichiers ignores ne sont jamais exclus d'office. Les 596 fichiers npm-cache
restent dans le perimetre initial. Les 27 distributions identifiees en phase 1
restent des preuves possibles, meme si elles sont generees.

Les outils/JSON prives de session cites dans l'audit sont hors depot. Si leur
conservation est souhaitee, les designer et l'autoriser separement; ils ne sont
pas une sauvegarde et ne sont pas inclus silencieusement ici.

## 3. Taille physique accessible et stabilite observee

Parcours de metadonnees de 24,4 secondes, avant creation du plan :

| Mesure | Valeur |
|---|---:|
| Fichiers ordinaires accessibles enumeres | 146 885 |
| Repertoires accessibles enumeres | 18 186 |
| Somme logique des fichiers ordinaires | 11 607 939 985 octets |
| Dont `.git` | 629 980 556 octets |
| Dont `deliveries` | 3 286 032 605 octets |
| Dont `var` | 6 745 831 157 octets |
| Refus de parcours | 115 |
| Liens/reparse non suivis | 7 |
| Changements taille/mtime detectes au second passage des fichiers enumeres | 0 |
| Fichiers ordinaires avec indicateur Windows OFFLINE observes | 0 |

Ce n'est ni un snapshot coherent ni une preuve d'absence de writers. Le dernier
fichier observe n'a pas la meme fenetre d'observation que le premier; une ecriture
peut conserver taille/mtime ou survenir apres le controle.
Les noms de fichiers donnent 1 102 candidats base/dump, dont certains faux positifs
comme `Dockerfile.db` et des fixtures de bibliotheques. Aucune base n'a ete ouverte.

Les 10,94 Go de phase 1 et les 11,61 Go ci-dessus ne sont pas directement
comparables : Git arretait le parcours aux worktrees et son traitement des liens
differe; ici `.git` et les worktrees sont parcourus sans suivre les reparse.
Cette difference n'est pas une preuve de perte ou de suppression.
ACL, flux NTFS alternatifs, proprietaires, audit, hardlinks, sparse, compression,
EFS et donnees de reparse ne sont pas integralement inventories a ce stade.
La taille totale exacte et l'allocation de sauvegarde restent inconnues.

## 4. Inaccessibles : liste des 115 points d'arret

Chaque chemin ci-dessous a retourne `PermissionError`, errno 13. Ne pas changer
ses permissions ni le declarer vide, reproductible ou sauvegarde. Aucun
contournement effectue. L'absence d'acces bloque une attestation complete.
Ancre du catalogue : SHA-256 des chemins relatifs tries, encodes UTF-8 et termines
chacun par NUL : `848696489b06da5b7607e6558431a8f99cba43e2276abc096fcacdaa4f807044`.

```text
.pytest_cache
var\s14-8\publish-preflight-pytest
var\s14-7-4-cli
var\s14-6-recipe-a84c
var\s14-6-recipe-8a519489
var\s14-6-recipe-4a05
var\s14-6-recipe-4a03
var\s13-ci-8dd8f6fa\windows-full-fixed
var\s13-ci-8dd8f6fa\windows-full
var\s13-ci-8dd8f6fa\windows-final
var\s13-ci-8dd8f6fa\single-core-diagnostic
var\s13-ci-8dd8f6fa\reproduction
var\s13-ci-8dd8f6fa\polling-before
var\s13-ci-8dd8f6fa\payload-before-corrected-spy
var\s13-ci-8dd8f6fa\payload-before
var\s13-ci-8dd8f6fa\payload-after
var\s13-ci-8dd8f6fa\notification-file
var\s13-ci-8dd8f6fa\isolated-truncated
var\s13-ci-8dd8f6fa\individual-2
var\s13-ci-8dd8f6fa\individual-1
var\s13-ci-8dd8f6fa\handoff-probe
var\s13-ci-8dd8f6fa\fixed-individual-6
var\s13-ci-8dd8f6fa\fixed-individual-5
var\s13-ci-8dd8f6fa\fixed-individual-4
var\s13-ci-8dd8f6fa\fixed-individual-3
var\s13-ci-8dd8f6fa\fixed-individual-2
var\s13-ci-8dd8f6fa\fixed-individual-1
var\s13-ci-8dd8f6fa\final-repetition-3
var\s13-ci-8dd8f6fa\final-repetition-2
var\s13-ci-8dd8f6fa\final-repetition-1
var\s13-ci-8dd8f6fa\final-individual-6
var\s13-ci-8dd8f6fa\final-individual-5
var\s13-ci-8dd8f6fa\final-individual-4
var\s13-ci-8dd8f6fa\final-individual-3
var\s13-ci-8dd8f6fa\final-individual-2
var\s13-ci-8dd8f6fa\final-individual-1
var\s13-ci-8dd8f6fa\final-file
var\s13-a7b75801\windows-tmp
var\pytest-sec1004-target-d60d32dd765f4ae5aae0f78a619fbfa0
var\pytest-sec1004-preflight-final-72a91a75f28844ef8d52c8e10e0c8cd7
var\pytest-sec1004-full-05efb8178911420eb2b23d1d75e93ecd
var\pytest-sec1004-final-guard-c33c1329cccf4b7a8c0845b418607e6e
var\pytest-sec1004-complete-final-4c22fb7aa63649b4babf04a63da9817a
var\pytest-sec1004-audit-final-b50d78303a36433db1d9345d5f211f16
var\pytest-sec1003-ip-final-76346d02d1ef4d2292a4ad4046aa1330
var\pytest-sec10-03-upload-final-e985f58a5b0c4c5ea915880b8b422175
var\pytest-sec10-03-targeted-a7d89c403a364b948210694a2cbfbf66
var\pytest-sec10-03-regressions-4a8f0f09b71f4bf6a8b6ef387869dcb1
var\pytest-sec10-03-gateway-final-09c81d3275344296a1daea6a6ed2bcb4
var\pytest-sec10-03-full-1c331b9e58614f298723d267d76dbe63
var\pytest-s14-8-workflow-final
var\pytest-s14-8-final-policy
var\pytest-s14-8-final-build-policy
var\pytest-s14-8-builds-final
var\pytest-s14-8-builds
var\pytest-s13-target-0b995248fa3b4d73b7002caffde48e10
var\pytest-s13-public-final-e0752ba62f744272a3f93e99ffd469d2
var\pytest-s13-public-extra-738db9509d9347c48b0764df6eef6f4b
var\pytest-14-7-6-essential
var\pytest-14-7-5-materials
var\pytest-14-7-5-fresh-windows
var\pytest-14-7-5-delivery
var\pytest-14-7-4-windows-full
var\pytest-14-7-4-red
var\pytest-14-7-4-first
var\pytest-14-7-4-finaltarget
var\pytest-14-7-4-expanded2
var\pytest-14-7-4-expanded
var\pytest-14-7-3-risk-final
var\pytest-14-7-3-qualified-faults
var\pytest-14-7-3-pool-observation
var\pytest-14-7-3-faults
var\pytest-14-7-3-dbapi-faults
var\pytest-14-7-1-windows
var\pytest-14-7-1-ops
var\pytest-14-7-1-bootstrap
var\pytest-14-6-smtp-compat
var\pytest-14-6-1-windows-full
var\pytest-14-6-1-windows-final
var\pytest-14-6-1-target4
var\pytest-14-6-1-target3
var\pytest-14-6-1-target2
var\pytest-14-6-1-target-final
var\pytest-14-6-1-freeze
var\pytest-14-6-1-first
var\pytest-14-5-windows-full
var\pytest-14-5-email-second
var\pytest-14-5-email-first
var\pytest-14-4-windows-full
var\pytest-14-4-state
var\pytest-14-4-repeat-2
var\pytest-14-4-repeat-1
var\pytest-14-4-red
var\pytest-14-4-pg-regressions
var\pytest-14-4-pg-races-final
var\pytest-14-4-pg-races
var\pytest-14-4-block-backup
var\pytest-14-3-windows-full
var\pytest-14-3-targeted
var\pytest-14-3-regressions
var\pytest-14-3-red
var\pytest-14-3-pg
var\pytest-14-3-green
var\pytest-14-2-windows-target-final
var\pytest-14-2-windows-full
var\pytest-14-2-windows-final
var\pytest-14-2-targeted
var\pytest-14-2-red
var\pytest-14-2-pg-operator-confirm
var\pytest-14-2-pg-final
var\pytest-14-2-pg
var\pytest-14-2-last-policy
var\pytest-14-2-final-policy
var\pytest-14-2-core
var\pytest-14-2-admin-final
```

## 5. Liens et bases : objets a ne pas copier naivement

| Chemin | Type / constat |
|---|---|
| `var\s14-7-10-materials\validation-output\verify\lib64` | Reparse Linux, tag `0xA000001D` |
| Meme repertoire, `bin\python`, `bin\python3`, `bin\python3.13` | Trois reparse Linux, meme tag |
| `var\pdf-isolation-linux-env\lib64` | Reparse Linux, meme tag |
| `var\lite-step2-74152cc207\source\frontend\node_modules` | Junction `0xA0000003`, cible interne `frontend\node_modules` |
| `var\lite-step3a-dfb9c9eb30\source\frontend\node_modules` | Junction, meme cible interne |

Les sept n'ont pas ete suivis. `os.readlink` ne prend pas en charge les cinq
objets Linux ici (`ValueError`); leurs cibles et bytes de reparse ne sont pas
encore attestes. Une copie NTFS classique non testee ne suffit pas a les preserver.
Ne pas transformer ces liens en fichiers ordinaires, ni dupliquer leurs cibles.

Cinq couples WAL/SHM ont ete reperes sous
`var\whitespace-validation-456a1eafb3\tmp-windows-retry\test_real_capture_includes_exa0\synthetic-lab\` :
`admission_anchor\anchor.sqlite`, `authenticated\authenticated.sqlite`,
`holds\holds.sqlite`, `registry\registry.sqlite`, `witness\witness.sqlite`,
avec suffixes `-wal` et `-shm`. Leur presence ne prouve ni activite ni inactivite.
Le nom synthetic-lab n'autorise pas une copie incoherente. Aucun writer ni base
active n'a ete arrete, ouvert ou sauvegarde.

## 6. Dependances Git hors simple repertoire de sources

Le stockage objets resolu est sous `.git`. Pas d'alternates/http-alternates,
shallow, modules ou LFS repertories observes; pas de partialClone/promisor dans
les cles controlees. Ce sont des controles de dependances, pas un `fsck` complet.
Deux fichiers de configuration effectifs sont externes au depot; leurs valeurs
ne sont pas publiees. `GIT_CONFIG_COUNT` est present dans l'environnement.
Conserver en prive les reglages pertinents et leur provenance lors de la capture,
sans copier automatiquement tout le profil utilisateur.
Un reglage fsmonitor est present; les consultations suivantes l'ont desactive
pour leur processus, sans modifier la configuration persistante.

Les ACL/privileges utiles, supports de destination, cles de chiffrement, methode
compatible reparse Linux et protocole de quiescence restent a choisir/valider.
La preparation du plan est possible; une sauvegarde complete coherente n'est
pas encore autorisable sur les seules informations disponibles.
