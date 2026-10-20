# Sprint 10 — Complément de validation RF10-01 et RF10-02

## Verdict et périmètre

**Verdict : prêt pour la préparation des commits sur le périmètre RF10-01/RF10-02.**
Les corrections locales sont implémentées et les contrôles finaux réussissent.
L'inventaire global reste à approuver. **Aucune autorisation de commit, push ou déploiement n'est déduite
de l'accord de préparation.** Aucun accès au VPS ou à la Registry privée effectué.

Ce complément actualise RF10-01/02 de la [revue finale](sprint-10-final-review.md).
Ses autres constats, les risques supply chain et la recette ABI 6 avant déploiement
restent à traiter ou à accepter selon cette revue.

## RF10-01 — Windows obligatoire avant publication

Dans `.github/workflows/ci.yml` :

- nouveau job `windows`, runner `windows-2022`, Python **3.13 x64**, PowerShell `pwsh`,
  délai maximal de 25 minutes ; actions épinglées, credentials checkout non conservés ;
- installation `python -m pip install -c requirements.lock '.[test]' tzdata` ; `tzdata`
  est déjà épinglé dans le fichier de contraintes et garantit les zones IANA sur Windows ;
- vérification de la plateforme, de Python 3.13 et de `Europe/Paris` avant la suite ;
- `AI_ENABLED=false`, clé OpenAI vide, inscriptions désactivées, configuration DB
  initiale SQLite et credentials applicatifs vides ; aucun secret GitHub, service Docker,
  base PostgreSQL ou environnement production référencé par ce job ;
- suppression de `TEST_DATABASE_URL` avant les tests, pour que les fixtures créent
  leurs propres bases SQLite temporaires ;
- exécution de **toute la suite portable**, via
  `python -m pytest -q -p no:cacheprovider --ignore=tests/test_extraction_linux.py` ;
- seuls les tests noyau Linux sont exclus du job Windows. Ils restent obligatoires
  dans le job Linux et dans Docker ; aucune politique ou fixture de confinement modifiée ;
- `publish.needs` devient **`[python, windows, frontend]`**, sans `always()` ni
  `continue-on-error` permettant de publier après échec Windows.

Le job possède les seules permissions de lecture du dépôt héritées du workflow.
Le jeton technique de checkout n'est pas un secret applicatif ou de production.
Les tests métiers IA utilisent exclusivement leurs fournisseurs simulés ; les fixtures
existantes interdisent les vrais clients OpenAI. Cela n'active aucune fonctionnalité
de l'application de production et ne déclenche aucun appel facturé.

### Problème détecté pendant la validation et corrigé

La première configuration ajoutait aussi `OWNER_DEMO_ENABLED=false`. Elle faisait
échouer des tests dont la fixture active explicitement le comportement IA **simulé**,
avec HTTP 403 au lieu de la réponse du mock. L'essai global de cette configuration
non retenue s'est terminé avec **43 échecs et 446 succès** ; une reproduction ciblée
a confirmé **1 échec / 1 succès** avant arrêt sur le premier échec.

Cette surcharge a été retirée du nouveau job, sans changer les tests fonctionnels,
les réglages de production ni les protections. `AI_ENABLED=false`, clé vide et
interdiction des clients réels restent présents. L'essai final est réalisé dans
une copie des seules sources Git candidates, dépourvue de `.env` privé.

## RF10-02 — Publication provisoirement amd64 seulement

Les trois étapes Buildx publient désormais **`platforms: linux/amd64`** :

| Image | Nouvelle publication |
| --- | --- |
| `documind-ai/backend` | linux/amd64 |
| `documind-ai/frontend` | linux/amd64 |
| `documind-ai/postgres` | linux/amd64 |

L'étape d'installation QEMU est retirée : les builds s'exécutent nativement sur le
runner Ubuntu amd64. Aucun tag ou digest existant n'est modifié et aucune ancienne
image arm64 n'est supprimée. Cette restriction concerne les **nouvelles versions**.

### Compatibilité examinée avant modification

| Élément | Conclusion |
| --- | --- |
| VPS amd64 confirmé | Les images natives correspondent à son architecture ; aucun besoin d'émulation |
| Format `release.json` | Inchangé : trois références Registry par digest et révision supportée ; aucune exigence d'index multiarchitecture dans le validateur |
| Digests Buildx | Un digest peut identifier le manifeste ou un index OCI avec attestations ; un build monoarchitecture ne garantit pas l'absence d'index. Le format reste accepté |
| `images.env` et Compose | Références figées transmises telles quelles ; pas de sélection d'un sous-manifeste arm64 dans le code |
| Vérification des images | Labels de révision Git et identité de l'image résolue restent vérifiés ; aucun contrôle affaibli |
| Déploiement/reprise | Même bundle à cinq fichiers, mêmes contrôles de projet, services, volumes et schéma ; aucune adaptation nécessaire |
| Rollback | Ancien digest multiarchitecture toujours résolvable sur amd64 s'il reste disponible ; compatibilité SQL `0006` inchangée |
| PostgreSQL | Aucun changement d'architecture effective sur ce VPS, de major 17, de schéma ou de chemin de volume ; l'image reste reconstruite lors de la future publication |
| Sprints 7–9 | Aucune dépendance à la présence d'arm64 dans un index ; scripts, unités, verrous et simulation préservés |

Aucune incompatibilité non résolue n'a été relevée pour le VPS amd64 déclaré. Les
scripts ne deviennent pas pour autant un garde-fou général interdisant tout hôte arm64 :
ils n'ajoutent pas de nouvelle vérification matérielle. Avant déploiement, l'opératrice
doit confirmer que l'image résolue est `linux/amd64`, conformément à la recette existante.
Une future utilisation sur arm64 demandera une nouvelle certification et une décision
explicite de rétablir sa publication. Aucun changement de format des anciennes releases
ou des outils de rollback n'est nécessaire pour cette limitation.

## Tests et portée des preuves

| Contrôle | Résultat |
| --- | --- |
| Windows : installation dans un venv neuf Python 3.13.7, dépendances de test + tzdata sous contraintes | Réussie |
| Windows : `pip check`, précontrôle Python et zone Europe/Paris | Réussis |
| Windows : suite portable finale dans une copie sans fichiers privés | **489 réussis**, aucun ignoré, 300,62 s |
| Tests de déploiement Windows ciblés, configuration finale | **87 réussis**, 1,79 s |
| Linux : déploiement, sauvegardes, confirmation Restic, surveillance, conservation, configuration finale | **328 réussis**, 9,35 s ; premier passage : 328 réussis, 9,84 s |
| Build local explicite `--platform linux/amd64 --target production` et inspection de l'image | Réussis : `linux/amd64`, utilisateur `app` |
| Manifeste/digests, `images.env`, schéma `0006`, refus de rollback vers `0007` | Vérifications locales réussies, références fictives uniquement |
| actionlint CI et déploiement | Réussi ; shellcheck/pyflakes non exécutés |
| `git diff --check` | Réussi |

Deux tests de configuration ont été ajoutés à `tests/test_deployment.py`, et le test
existant du graphe de publication a été adapté :

- job Windows sans secrets/services de production, suite portable non filtrée hors
  module natif Linux, dépendances nécessaires et refus de poursuivre sur erreur ;
- les trois composants Docker limités à amd64 et absence de QEMU.

Les 489 succès Windows comprennent les deux nouveaux tests ; les 40 preuves noyau
Linux du module exclu ne sont pas collectées dans cette série et ne sont pas comptées
comme réussies. Leurs étapes Linux/Docker restent présentes et obligatoires dans la CI.

La suite finale utilise les commandes de précontrôle et de test **lues dans le YAML**,
avec l'environnement déclaré par le job. Une valeur volontairement invalide de
`TEST_DATABASE_URL` est injectée avant exécution pour vérifier son retrait sans contacter
une base. Le checkout local de test contient seulement les sources non ignorées, pas
les `.env`, certificats, volumes, caches ou documents de production.

La machine locale utilise Windows PowerShell **5.1**, pas le `pwsh` du runner GitHub.
Les commandes ont été exécutées localement, mais le provisionnement `windows-2022`,
les actions GitHub et PowerShell 7 restent à confirmer par la première CI autorisée.
Aucun workflow distant n'a été lancé. Le build backend explicite amd64 réutilise les
couches applicatives inchangées et produit le même identifiant local qu'avant la correction :
`sha256:fa8ea4538c6365d40a526a78cfeb2bee2300271a6376179fb88dfa6308208e83`.
Ces tests ne prétendent pas prouver une nouvelle construction/poussée des trois images
dans la Registry ou un pull de futurs digests encore inexistants.

L'avertissement Starlette/httpx reste une dépréciation sans échec. Le lock incomplet
des transitifs et les autres risques supply chain de la revue finale ne sont pas
résolus par ces deux corrections ciblées.

## Préservation, fichiers et conséquences d'un futur push

Fichiers versionnables modifiés pendant ce complément :

1. `.github/workflows/ci.yml` : job Windows, nouveau verrou de publication, amd64 seulement.
2. `tests/test_deployment.py` : couverture des deux décisions de CI.
3. `docs/sprint-10-final-review.md` : renvoi au présent complément, historique conservé.
4. `docs/sprint-10-rf01-rf02-validation.md` : présent rapport.

Les références SHA-256 prises au début du travail permettent de confirmer les autres
fichiers inchangés, notamment moteur, Landlock/seccomp, broker, Dockerfiles/Compose,
fixtures, dépendances/contraintes, déployeur/rollback et tous les fichiers des Sprints 7–9.
Les artefacts de test sous `var/sprint10-rf01-rf02/` restent ignorés. Le packaging a créé
un répertoire `build/` : ses 69 copies de sources ont été vérifiées puis retirées ; aucune
modification préexistante n'a été supprimée. Ce répertoire ne doit pas être publié.

Un push ultérieur sur `main` exécuterait désormais **trois jobs requis** (Linux, Windows,
frontend), puis publierait les trois images amd64 et le bundle seulement après réussite.
Il ne déclencherait toujours aucun déploiement VPS. Le workflow manuel de déploiement
et les procédures de sauvegarde et retour arrière restent inchangés.

L'inventaire précédent de 53 candidats gagne ce rapport, soit **54 candidats proposés**,
sans ajout à l'index. Toute décision de séparation des Sprints 7–10 doit préserver leurs
dépendances et les liens documentaires. Aucune commande de commit ou push préparée/exécutée.

**Arrêt après ce complément : attente de l'autorisation explicite de l'administratrice
avant commit, push, recette distante ou déploiement.**
