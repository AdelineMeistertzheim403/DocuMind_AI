# Sprint 14.7.8 — Audit GitHub Actions de la PR nº 6

26 octobre 2026. Lecture seule de GitHub et rédaction locale, sans intervention
sur le code, les workflows, les dépendances ou la production. Référence :
[rapport de publication 14.7.7](SPRINT_14_7_7_GITHUB_DRAFT_PR_REPORT.md).

**CI de PR validée sur ce run : python, Windows et frontend ont réussi ; publish
est skipped. Aucun échec de job observé.** La revue
humaine en Draft peut continuer ; fusion, RC utilisable, déploiement et ouverture
ne sont pas autorisés par cet audit.

## 1. Périmètre et date des preuves

- [PR nº 6](https://github.com/AdelineMeistertzheim403/DocuMind_AI/pull/6).
- [Run nº 15, ID 40326201923](https://github.com/AdelineMeistertzheim403/DocuMind_AI/actions/runs/40326201923).
- Dernier relevé des jobs et logs : **26 octobre 2026 à 13:20:54 UTC** ; checks,
  artefacts et déploiements revérifiés à **13:21:18 UTC**.
- Workflow `.github/workflows/ci.yml`, événement `pull_request`, tentative **1**,
  état global `completed`, conclusion **success**, fin du run à **13:17:54 UTC**.

Les requêtes sont exclusivement des GET : PR, commits, run, jobs, checks, artefacts,
déploiements associés au SHA et logs disponibles. Authentification existante en
mémoire ; liens signés de logs non enregistrés et aucun header d'authentification
GitHub transmis à leur hébergement de téléchargement. Copies de logs expurgées
sous `var/s14-7-8-*`, ignoré ; aucun log brut ou secret joint à un rapport public.

## 2. État réel de la PR et commits

| Contrôle | Résultat API |
| --- | --- |
| État / Draft | open / true |
| Source | preparation/sprint-14-review |
| SHA source | f3c92eb8ba2bb69b83a9798ebc3df8a70f48fbb2 |
| Cible | main |
| SHA base | 8243e0511c5505a9cc70f76ad02392f7a816590d |
| Fusion | merged=false ; merged_at=null |
| Auto-merge | null, non activé |
| Commits de la PR | Un seul, le SHA source attendu |
| Nouveau commit depuis 14.7.7 | Aucun |

La branche, le SHA source et la base correspondent au rapport précédent. La PR
n'a pas été convertie en Ready for review, modifiée, fusionnée ou relancée.

## 3. Jobs et conclusions disponibles

| Job | Statut | Conclusion | Étape en échec |
| --- | --- | --- | --- |
| [python](https://github.com/AdelineMeistertzheim403/DocuMind_AI/actions/runs/40326201923/job/121583422638) | completed | success | Aucune |
| [windows](https://github.com/AdelineMeistertzheim403/DocuMind_AI/actions/runs/40326201923/job/121583423054) | completed | success | Aucune |
| [frontend](https://github.com/AdelineMeistertzheim403/DocuMind_AI/actions/runs/40326201923/job/121583422920) | completed | success | Aucune |
| [publish](https://github.com/AdelineMeistertzheim403/DocuMind_AI/actions/runs/40326201923/job/121594346179) | completed | skipped | Aucune, job non exécuté |

Les trois checks réussis et le check publish ignoré sont tous émis par
`github-actions`. Aucune étape en échec n'est retournée par l'API des jobs.

### Python : compteurs réellement présents dans les logs

| Campagne du job python | Réussis | Ignorés | Échoués | Durée pytest |
| --- | --- | --- | --- | --- |
| Landlock/seccomp Linux hôte | 72 | 0 | 0 | 8,63 s |
| Runtime Docker isolé, sans réseau/volumes | 72 | 0 | 0 | 13,13 s |
| Suite complète SQLite/migrations | 832 | 28 | 0 | 389,38 s |
| Suite complète PostgreSQL/pgvector | 844 | 16 | 0 | 481,21 s |

Les deux suites complètes totalisent chacune 860 cas, avec des cas partagés.
**Ne pas additionner ces lignes comme des tests uniques.** Chaque résumé rapporte
également un avertissement Starlette/TestClient, sans échec.
Installation Python, inventaire contraint, prérequis, construction de l'image de
preuve, construction PostgreSQL, démarrage DB et upload des matériaux Linux ont
aussi la conclusion success dans les métadonnées d'étapes.

Les motifs précis ne sont pas récapitulés par pytest `-rs` dans ces logs. D'après
les marqueurs des sources revues, les skips SQLite se répartissent en douze cas
nécessitant PG, six snapshots Docker opt-in, huit E2E opt-in et deux preuves root.
Les seize skips PG correspondent aux six snapshots, huit E2E et deux preuves root.
Cette attribution provient des sources et de la cohérence des comptes ; elle ne
remplace pas une liste nominative de motifs produite par le runner.
Les succès root locaux de 14.7.6 restent historiques, pas des succès CI implicites.

### Frontend : compteurs et build

- Vitest : **10 fichiers réussis, 52 tests réussis sur 52** ; aucun échec ni ignoré
  indiqué dans ce résumé complet.
- Node/BFF : **50 tests, 50 réussis, 0 échoué, 0 ignoré, 0 annulé, 0 todo**.
- `TypeScript and production frontend build` : success ; Vite 6.4.4, build annoncé
  en **3,50 s**. Les étapes checkout, setup-node et npm ci ont aussi réussi.

Ces chiffres viennent des logs GitHub, pas d'une reprise des comptes locaux.

### Windows : résultat final

La suite portable SQLite rapporte **790 réussis, 30 ignorés, 0 échoué**, un
avertissement, en **1320,92 s (22 min)**. Elle utilise **Python 3.13.17**.
Le workflow exclut explicitement `tests/test_extraction_linux.py` sous Windows :
ces tests non collectés ne font pas partie des trente ignorés. Leur couverture
Linux et Docker est documentée séparément ci-dessus. Les logs ne détaillent pas
les trente motifs d'ignorance avec `-rs` ; ne pas les qualifier de succès.

Pendant les relevés intermédiaires, l'endpoint des logs renvoyait HTTP 404 alors
que le job était encore actif. Après terminaison, les logs sont disponibles et
ont été consultés : cette limite initiale est levée, sans rerun ni contournement.

## 4. SHA réellement testé

Les métadonnées du run et les checks GitHub Actions sont attachés au SHA source
`f3c92eb8ba2bb69b83a9798ebc3df8a70f48fbb2`.

Les logs checkout de **python, Windows et frontend** contiennent le fetch de
`refs/remotes/pull/6/merge` et la sortie de `git log -1 --format=%H` :

```text
502b1e07ceb4ddd98d53b46a17cfb4e48afbe205
```

C'est donc le checkout de test de PR effectivement observé pour ces trois jobs.
Il correspond au SHA de merge synthétique annoncé par la PR ; **ce n'est pas une
fusion effectuée sur main**. Le rattachement des checks au SHA source et le test
du merge synthétique sont cohérents ; ils désignent deux objets Git distincts.

Runtime Linux hôte observé : **CPython 3.13.16**. Frontend : **Node 22.23.3,
npm 10.9.9**. Ne pas remplacer ces valeurs par les versions locales de 14.7.5.
La version patch Python exacte du conteneur n'est pas déduite d'un chemin générique
python3.13. Les runtimes non figés restent un élément de RF10-03.

## 5. Erreurs et avertissements significatifs

Aucune étape en échec ni résumé de test en échec dans les logs accessibles.
**Aucune cause d'échec applicatif démontrée et aucun correctif de code proposé.**
La réussite Windows ne permet pas d'exclure une course intermittente, un verrou
SQLite ou une réapparition future de SQL-01 ; aucune panne de ce type n'est
démontrée par ce run.
Pas de relance automatique ni d'augmentation de timeout pour obtenir du vert.

| Signal réel | Qualification |
| --- | --- |
| StarletteDeprecationWarning sur httpx/TestClient | Présent dans les quatre campagnes Linux/Docker et la campagne Windows ; avertissement de compatibilité future, non bloquant sur ce run. Revoir séparément la migration de dépendance après qualification, sans changement ici. |
| pip exécuté en root pendant les étapes de build Docker | Deux warnings dans le build ; ce n'est pas la preuve d'un parseur exécuté root. Les tests de runtime confiné ont réussi. Ne pas supprimer le warning ou affaiblir le sandbox pour le masquer. |
| npm deprecated whatwg-encoding@3.1.1 | Dépréciation transitive observée ; aucune vulnérabilité/CVE déduite de ce seul message. Pas de mise à jour effectuée. |
| Événements WARNING de refus BFF | Les logs des tests négatifs contiennent 401/403, 408 et 503 de capacité/timeout. Les 50 tests BFF réussissent ; ces signaux ne sont pas un incident de production ni une preuve du 503 SQL historique. |
| Logs Windows HTTP 404 pendant le job | Limite initiale levée après terminaison ; pas une erreur métier. |

Il n'y a ni nouvel audit CVE, ni certification de toutes les versions, ni correction
de SQL-01 justifiée par ces passages réussis. Pour tout échec futur, relever les
logs et la classe d'erreur avant une correction ; ne pas rapprocher deux incidents
uniquement sur leur code HTTP ou leur plateforme.

## 6. Publication et déploiement dans le périmètre examiné

Un seul run est retourné pour le SHA source : cette CI `pull_request`, tentative 1.
Aucun run de deploy pour ce SHA, aucun workflow manuel déclenché et aucun déploiement
GitHub associé retourné par l'endpoint deployments filtré sur ce commit.

Le job publish porte la condition source :

```text
github.event_name != 'pull_request' && github.ref == 'refs/heads/main'
```

Elle est fausse pour ce run. La conclusion terminale **skipped** est confirmée
par les API jobs et checks. Aucune étape de login/push Registry n'a été exécutée
par ce job.

Les deux seuls artefacts retournés au contrôle final sont les inventaires runners :

- `documind-runner-materials-linux-502b1e07ceb4ddd98d53b46a17cfb4e48afbe205` ;
- `documind-runner-materials-windows-502b1e07ceb4ddd98d53b46a17cfb4e48afbe205`.

Leur contenu n'a pas été téléchargé ni attesté par cet audit.
Le suffixe suit le SHA du checkout de PR, conformément à github.sha ; ce n'est
pas une incohérence avec le SHA source des checks. Aucun artefact de release
`documind-release-…` n'est retourné lors de ce contrôle. L'inventaire n'est pas
un bundle de release ni une attestation d'origine des trois images.

Le job Python a construit son runtime d'isolation et l'image PG de test selon les
Dockerfiles ; il ne s'agit pas d'une publication des trois images de production,
d'un double rebuild reproductible ni d'une qualification complète des matériaux.

**Aucune publication de release ou opération de déploiement déclenchée dans les
preuves consultées.** Aucun accès agent à la Registry privée ou au VPS, aucune
inspection de ces services interdits. La conclusion n'exclut pas une action d'un
autre acteur hors de ce SHA/run : sa portée est explicitement limitée à l'audit.

## 7. Risques qui restent distincts

| Risque | État après ce relevé |
| --- | --- |
| R14-SQL-01 | Cause historique du GET 503 inconnue. Les suites Linux et Windows réussies ne l'identifient pas et ne prouvent pas son impossibilité. |
| R14-SQL-02 | Correctif documentaire local publié dans la branche et testé sous fautes définies ; aucune réparation automatique d'une perte ancienne. Les suites CI SQLite/PG réussissent, avec leurs skips documentés. |
| R14-SQL-03 | Inscription éventuellement commitée malgré erreur/notification absente ; compteur conservé et récupération à revoir avec décision opératrice. Aucun effacement/reset implicite. |
| RF10-03 | Transitifs contraints et inventaires améliorés, mais build tools PEP 517, bases, APT/APK, commit/archive pgvector et provenance non intégralement qualifiés. Les archives Linux 3.13 n'ont pas été récupérées/attestées par cet audit ; un install/build CI réussi ne remplace pas ces preuves. |
| RF10-04 | Publication future séquentielle pouvant être partielle : arrêt, preuves conservées, aucune relance/suppression/retagging automatique. Non déclenchée par cette PR. |

Une CI verte ne vaut pas acceptation de ces risques. Aucun test réel SMTP/B2/VPS,
aucune restauration de production, aucun changement d'inscription publique ou IA,
de quota cinq cumulatif ou de schéma 0007. Les preuves d'exploitation, la conformité
des textes et les décisions opératrice restent séparées.

## 8. Verdicts et recommandations

| Décision | Verdict et conditions |
| --- | --- |
| CI de PR validée | **Oui pour le run 40326201923, tentative 1** : python/windows/frontend success, publish skipped ; comptes et ignorés ci-dessus. Cela ne lève pas les risques résiduels. |
| PR apte à poursuivre sa revue | **Oui, en Draft** : source inchangée, aucun nouveau commit, preuves et réserves explicites. Ne pas convertir son statut ou activer l'auto-merge. |
| Fusion | **No-Go à ce stade** : revue humaine, décisions sur SQL-01/03 et qualification RF10-03 non closes ; protection effective/base à jour à revérifier avant toute fusion. Nouvelle autorisation requise, avec effet de publication automatique sur main explicité. |
| RC utilisable | **No-Go** : qualification des matériaux et des trois builds complets/provenance, décision des risques, run/digests et bundle neuf fichiers cohérents puis recette des images réelles manquants. |
| Déploiement fermé | **No-Go** : aucune autorisation VPS, approbation indépendante root, contrôle des guards/bootstrap, sauvegarde/restauration réelle qualifiée et secours corrigé ou correction en avant validés par cet audit. |
| Ouverture publique | **No-Go** : exigences précédentes, SMTP/textes/alertes/B2 et recette de fermeture/quota réels, décisions opératrice distinctes. IA toujours off. |

Prochaine étape recommandée : revue humaine de la PR en Draft, qualification
RF10-03 et décisions explicites sur les risques. Avant une future fusion, relire
le SHA, les checks et les protections ; ce constat ne couvre aucun nouveau commit.
Les warnings de dépendances relèvent d'un lot contrôlé,
pas d'une modification automatique pendant cette mission.

## 9. Préservation et clôture locale

Seul ce nouveau rapport rejoint les fichiers non suivis ; l'ancien rapport 14.7.7
reste conservé avec son constat daté. Logs expurgés et scripts de lecture sont sous
var, ignoré. Aucun code, workflow, dépendance, config de production ou secret modifié.
Index vide ; aucun commit, push, PR, merge, rerun, publication ou déploiement exécuté.

État Git constaté après rédaction :

```text
## preparation/sprint-14-review...origin/preparation/sprint-14-review
?? docs/SPRINT_14_7_7_GITHUB_DRAFT_PR_REPORT.md
?? docs/SPRINT_14_7_8_GITHUB_CI_REVIEW_REPORT.md
```

**Arrêt après cet audit daté. CI réussie ; PR maintenue en Draft,
aucune fusion, release utilisable, livraison ou ouverture autorisée.**
