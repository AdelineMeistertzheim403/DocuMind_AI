# Sprint 14.8 — Validation finale de la CI

26 octobre 2026. Audit distant en lecture seule ; aucun test relancé.
Rapport précédent : [mise à jour de PR](SPRINT_14_8_PR_UPDATE_REPORT.md).

## Identités et périmètre

- [PR nº 6](https://github.com/AdelineMeistertzheim403/DocuMind_AI/pull/6) :
  `preparation/sprint-14-review` vers `main`. Initialement ouverte en Draft ;
  **dernière relecture : closed, merged=true, draft=false**, auto-merge absent.
  Ce changement distant n'a pas été effectué par cet audit.
- Source : `f4c52274d7608f78571b5a4c92d271dffc384475`.
- Checkout de PR : `b690546baf381b85a630a1a8206518129db6990a`, merge
  synthétique de test, pas un commit ajouté à main.
- Base testée : `8243e0511c5505a9cc70f76ad02392f7a816590d`.
  **Main actuelle : `348b17d82f7ecbdd58149053adb30b8130728e3e`**, donc modifiée
  depuis la première observation. Ne pas présenter la CI de PR comme celle de ce SHA.
- [Run 40355695162](https://github.com/AdelineMeistertzheim403/DocuMind_AI/actions/runs/40355695162),
  attempt 1, événement `pull_request`.
- Protection observée : `python`, `windows`, `frontend`, GitHub Actions
  `app_id=15368`, branche à jour exigée ; `publish` non requis.

## Conclusions et tests

**Run terminé avec succès, attempt 1.** Les logs de checkout des trois jobs
confirment le merge synthétique indiqué ci-dessus, source et base exactes incluses.

| Job / campagne | Réussis | Ignorés | Échoués | Conclusion |
| --- | ---: | ---: | ---: | --- |
| [python](https://github.com/AdelineMeistertzheim403/DocuMind_AI/actions/runs/40355695162/job/121687426649), confinement Linux natif | 72 | 0 | 0 | success |
| python, confinement Docker | 72 | 0 | 0 | success |
| python, SQLite | 854 | 28 | 0 | success, 379,22 s |
| python, PostgreSQL/pgvector | 866 | 16 | 0 | success, 462,02 s |
| [windows](https://github.com/AdelineMeistertzheim403/DocuMind_AI/actions/runs/40355695162/job/121687426721) | 812 | 30 | 0 | success, suite 1252,86 s |
| [frontend](https://github.com/AdelineMeistertzheim403/DocuMind_AI/actions/runs/40355695162/job/121687426701), React | 52 | 0 | 0 | success, 10 fichiers |
| frontend, BFF | 50 | 0 | 0 | success, 0 annulé |
| frontend, TypeScript/Vite | — | — | — | success |
| [publish](https://github.com/AdelineMeistertzheim403/DocuMind_AI/actions/runs/40355695162/job/121699904131) | — | — | — | completed / skipped |

Les ignorés sont conservés tels que rapportés par pytest, sans les compter comme
succès. Aucun test ni job relancé. Les avertissements visibles sont la dépréciation
Starlette/httpx TestClient et npm `whatwg-encoding@3.1.1` deprecated ; aucun échec
n'impose une correction. Les événements de refus des tests de sécurité BFF sont
attendus, pas des incidents de production. Aucun diagnostic de vulnérabilité
ne se déduit du seul avertissement npm.

La première lecture ne recensait aucun run deploy depuis cette CI. La dernière
en recense **quatre** : leur présence temporelle ne démontre ni leur relation
avec ce run ni un déploiement réussi. Aucun déploiement GitHub attaché au SHA
source n'est recensé ; le checkout synthétique n'en avait aucun lors du contrôle.
Publish est effectivement skipped : aucune publication de release n'est exécutée
par **ce run de PR**. L'absence globale de déploiement ultérieur n'est donc pas
confirmée. Aucun accès VPS ni inspection de son état réel.

Les résultats de campagnes qui se recouvrent ne doivent pas être additionnés
pour annoncer un nombre de tests uniques. Les inventaires des runners ne sont
pas les inventaires des futures images de production.

## Décisions humaines minimales proposées

Aucune acceptation n'est prise au nom de l'exploitante. La décision proposée
porte uniquement sur une publication privée automatique après une future fusion,
pas sur un déploiement ou une ouverture publique.

| Risque | Décision à prendre et limite | Condition d'arrêt |
| --- | --- | --- |
| R14-SQL-01 | Reconnaître que la cause du HTTP 503 historique reste inconnue ; décider si ce risque peut être conservé pour la publication privée, sans prétendre qu'une CI verte l'explique ou le corrige. | Réapparition, incohérence durable ou anomalie d'autorisation : arrêter la progression et diagnostiquer, sans retry SQL ni timeout arbitraire. |
| R14-SQL-03 | Décider séparément du risque d'admission commitée sans notification ; pour la seule publication privée, aucune admission réelle n'est autorisée. Compteur cumulatif et possibilité de renvoi conservés. | Avant ouverture, notification/réconciliation non validées ou compteur incohérent : rester fermé ; aucun remboursement automatique de place. |
| RF10-03 | Accepter ou refuser explicitement les limites résiduelles de provenance npm/PyPI/bases/builder pour une publication privée bornée. Les 122 cas npm liés seulement à une clé historique expirée ne deviennent pas rétroactivement certifiés. Les hashes, bases épinglées et signatures APK restent exigés. La bit-identité OCI n'est pas une condition supplémentaire. | Hash/version/architecture inattendus, indice de compromission, signature réellement invalide ou preuve obligatoire absente : aucune promotion des images. |
| RF10-04 | Confirmer la procédure de publication partielle : une seule exécution initiale, conserver les preuves, ne pas relancer, supprimer ou retaguer automatiquement. | Échec ou sortie partielle : arrêter la livraison et obtenir une nouvelle décision avant toute intervention. |

Une acceptation éventuelle doit identifier la révision revue, le futur SHA de
fusion, l'événement/run/attempt initial, une fenêtre de validité explicite et
une seule publication. Aucun rerun, déploiement ni usage public inclus.

## Étape suivante et limites

**CI de PR validée : les trois checks requis sont verts et publish skipped.**
Sur la seule base de cette CI, le dossier permettait de passer à une décision
humaine de fusion/publication privée, sans nouvelle série d'audits locaux.
**La PR ayant désormais été fusionnée par une autre opération, ce rapport
n'autorise ni ne valide rétroactivement cette fusion ou ses suites.** La liste
suivante décrit les décisions minimales initialement requises ; rapprocher les
autorisations et preuves de la fusion réellement effectuée avant de poursuivre :

1. Statuer sur la matrice ci-dessus pour la seule publication privée.
2. Autoriser explicitement le passage de la PR à prête pour revue puis sa fusion
   par merge commit, avec son effet de publication automatique sur main.
3. Juste avant cette opération, revérifier le même SHA, les checks, la base et
   les protections. Tout changement de code/base significatif invalide ce raccourci.
4. Observer la CI automatique du commit de fusion et sa publication ; relever
   les trois digests amd64, provenance et bundle attesté de neuf fichiers.
   Appliquer RF10-04 en cas d'échec, sans intervention automatique.

Ce contrôle des sorties futures est une étape de livraison, pas une demande de
refaire les campagnes déjà réussies. La recette des images réellement publiées,
les approbations indépendantes et le bootstrap sûr conditionnent ensuite une
autorisation distincte de déploiement fermé. SMTP/B2, conditions opérationnelles
et décision d'ouverture restent séparés. IA et inscriptions restent fermées.

Aucun commit, push, merge, rerun, changement de statut PR, publication,
accès VPS/B2/SMTP, déploiement ou acceptation de risque pendant cet audit.
Preuves brutes conservées localement sous `var/s14-8/final-ci/`, non ajoutées à Git.
