# Sprint 14.8 — Mise à jour contrôlée de la PR nº 6

26 octobre 2026. Publication Git uniquement, autorisée par l'exploitante.

## Commit et push

- Branche : `preparation/sprint-14-review`, dépôt `AdelineMeistertzheim403/DocuMind_AI`.
- Parent : `f3c92eb8ba2bb69b83a9798ebc3df8a70f48fbb2`.
- Commit unique : **`f4c52274d7608f78571b5a4c92d271dffc384475`**.
- Message : `build: stabiliser les matériaux de la release privée`.
- Push normal réussi : `git push origin preparation/sprint-14-review`.
- [PR nº 6](https://github.com/AdelineMeistertzheim403/DocuMind_AI/pull/6) : ouverte,
  **Draft**, cible `main`, nouveau SHA confirmé, non fusionnée, auto-merge absent.

La branche distante a été relue immédiatement avant le push : elle pointait
toujours sur le parent attendu. Aucun historique divergent, rebase ou force-push.
Le présent rapport est créé après le commit et reste **non suivi, non publié**.

## Inventaire indexé et commité

Exactement les 21 chemins de la section 7 du rapport 14.8 :

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
docs/SPRINT_14_7_7_GITHUB_DRAFT_PR_REPORT.md
docs/SPRINT_14_7_8_GITHUB_CI_REVIEW_REPORT.md
docs/SPRINT_14_7_9_PREMERGE_RISK_REVIEW.md
docs/SPRINT_14_7_10_BUILD_MATERIALS_QUALIFICATION_REPORT.md
docs/SPRINT_14_7_11_PRODUCTION_IMAGE_QUALIFICATION_REPORT.md
```

21 fichiers, 2825 insertions, 18 suppressions. Indexation par liste explicite,
sans `git add .` ni `git add -A`. Aucun autre fichier ajouté.

## Contrôles avant publication Git

- Rapports 14.8, 14.7.11 et runbook lus ; diff des Dockerfiles, CI, outils,
  manifests, locks et tests revu. Les 21 SHA-256 correspondent exactement à
  l'inventaire final de la précédente revue locale.
- Liste des fichiers modifiés/non suivis égale à la whitelist ; index initial
  vide ; fichiers texte réguliers, aucun lien symbolique ou chemin `var/`.
- Aucun secret détecté par revue et recherche de motifs de clés privées/tokens.
  Ce contrôle ne constitue pas une garantie exhaustive de détection de secrets.
  Archives, wheelhouses, caches, dumps, certificats et preuves privées exclus.
- Versions fonctionnelles conservées ; locks hachés, bases amd64 par digest,
  source pgvector exacte et compilation portable `OPTFLAGS=""`.
- Downloader HTTPS borné, origines précises, refus des redirections et divergences,
  signatures APK obligatoires, absence de fallback ou chemin privé nécessaire.
  Disponibilité des matériaux étayée par les builds publics réussis du même lot
  documentés en 14.8 ; aucune nouvelle acquisition exhaustive pendant ce push.
- Confinement, code métier, quota, IA, migrations, Compose et `deploy.yml`
  inchangés dans ce commit. Aucun accès à la production.
- GitHub confirme les checks requis `python`, `windows`, `frontend`, tous liés
  à GitHub Actions `app_id=15368`, branche à jour obligatoire et administrateurs
  inclus. `publish` n'est pas un check obligatoire.
- `publish` conserve `needs: [python, windows, frontend]` et la condition
  `github.event_name != 'pull_request' && github.ref == 'refs/heads/main'`.
- `git diff --check`, inventaire indexé et `git diff --cached --check` réussis.

Validation locale réexécutée avant commit :

```text
.venv\Scripts\python.exe -m pytest tests/test_pinned_builds.py tests/test_deployment.py -q -p no:cacheprovider --basetemp var/s14-8/publish-preflight-pytest --tb=short
```

**109 réussis, 0 échoué, 0 ignoré**, 1,69 s. Un avertissement existant
Starlette/httpx TestClient ; aucune modification de dépendance pour le masquer.
Les campagnes Docker et suites antérieures restent celles du rapport 14.8,
pas des campagnes intégralement relancées pendant cette publication Git.

## Première observation de la CI automatique

[Run 40355695162](https://github.com/AdelineMeistertzheim403/DocuMind_AI/actions/runs/40355695162),
attempt 1, événement **pull_request**, créé à 16:05:20 UTC (17:05:20 Europe/Paris).
Source : `f4c52274d7608f78571b5a4c92d271dffc384475`.
La PR expose le merge synthétique `b690546baf381b85a630a1a8206518129db6990a` ;
ce n'est pas une fusion dans main. Le checkout réellement utilisé devra être
confirmé par les logs/inventaires du run, pas déduit du seul SHA source.

| Job | État observé initialement | Conclusion |
| --- | --- | --- |
| [python](https://github.com/AdelineMeistertzheim403/DocuMind_AI/actions/runs/40355695162/job/121687426649) | in_progress, initialisation | Non disponible |
| [windows](https://github.com/AdelineMeistertzheim403/DocuMind_AI/actions/runs/40355695162/job/121687426721) | in_progress | Non disponible |
| [frontend](https://github.com/AdelineMeistertzheim403/DocuMind_AI/actions/runs/40355695162/job/121687426701) | in_progress, initialisation | Non disponible |
| publish | Pas encore présent dans la réponse jobs | Exclu par condition ; skipped pas encore observé |

Aucun nombre de tests CI disponible à cette première observation, aucun échec
observé et aucune conclusion de succès inventée. Aucun workflow manuel, rerun,
publication Registry ou déploiement déclenché par cette mission.

Dernière lecture : **16:06:20 UTC / 17:06:20 Europe/Paris**. `frontend` est
**completed / success** : étapes React, BFF et TypeScript/build réussies.
`python` reste en cours : installation et inventaire réussis, preuves natives
Landlock/seccomp réussies, construction du runtime isolé en cours. `windows`
reste en cours : bootstrap haché, installation et inventaire réussis, suite
portable en cours. Aucun échec observé. Les nombres de tests ne sont pas fournis
par cette réponse API jobs ; aucun compte historique n'est substitué.
`publish` reste absent de la liste jobs : son exclusion est confirmée dans le
workflow, mais sa conclusion finale skipped n'est pas encore observable.
**CI globale non encore validée.**

Contrôle Git final : branche synchronisée avec son upstream, index vide,
`git diff --check` réussi. Seul fichier non suivi :
`docs/SPRINT_14_8_PR_UPDATE_REPORT.md`. Aucun autre changement local.

## Risques et conditions avant fusion

- **R14-SQL-01** : origine du HTTP 503 historique inconnue.
- **R14-SQL-03** : admission commitée avec notification potentiellement absente ;
  compteur cumulatif conservé, pas de remboursement automatique.
- **RF10-03** : confiance/provenance partiellement qualifiée malgré les matériaux
  épinglés ; signatures npm historiques, provenance éditeurs et builder restent
  des décisions humaines, sans acceptation implicite.
- **RF10-04** : publication partielle possible lors d'une future fusion ; arrêt,
  conservation des preuves, aucune relance/suppression/retagging automatique.

Avant toute fusion : conclusions réelles des trois jobs sur cette révision,
confirmation de publish skipped, revue humaine et décisions bornées sur les risques,
protections/base/SHA revérifiés, puis autorisation explicite couvrant la fusion et
son éventuelle publication automatique privée. Une CI verte ne clôt pas ces risques.
Les images publiées, provenance et bundle neuf fichiers devront ensuite être
qualifiés ; déploiement fermé et ouverture restent des autorisations distinctes.

**Mission limitée à la mise à jour de la PR Draft et à l'observation de sa CI.**
Aucune fusion, acceptation de risque, intervention VPS/B2/SMTP, ouverture publique
ou activation IA. Arrêt avant toute autre opération de livraison.
