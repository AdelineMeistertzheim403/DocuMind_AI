# DocuMind AI — Sprint 14.14 : consolidation et préparation de la release candidate

27 octobre 2026. Vérification locale sur la branche
`preparation/sprint-14-review`, sans commit, push, déploiement, accès VPS/B2,
ouverture d'inscription, activation IA ou suppression réelle.

## Verdicts distincts

| Décision | Verdict |
| --- | --- |
| Création d'une release candidate Git/CI | **GO conditionnel** : le lot local est cohérent, les tests locaux passent et aucune migration/dépendance/configuration de production ne change. Une revue humaine, un commit explicite, la CI GitHub Actions et l'attestation de release restent obligatoires. |
| Déploiement fermé | **No-Go tant que** les digests CI, l'attestation, les sauvegardes et les contrôles VPS ne sont pas vérifiés selon le runbook. |
| Ouverture publique | **NO-GO** : les textes restent des brouillons non approuvés et les validations juridiques/opérationnelles de production sont absentes. |

## 1. État Git et fichiers de la RC

La branche locale suit `origin/preparation/sprint-14-review`. Le worktree est
volontairement non committé ; aucun travail existant n'a été écrasé.
`git diff --check` est valide.

| Lot | Fichiers à inclure dans une RC revue |
| --- | --- |
| Sprints 14.10–14.13 | `docs/SPRINT_14_10_COMPLIANCE_READINESS_REPORT.md`, `docs/SPRINT_14_11_DATA_LIFECYCLE_REPORT.md`, `docs/SPRINT_14_12_DOCUMENT_EXPORT_REPORT.md`, `docs/SPRINT_14_13_PREOPENING_READINESS_REPORT.md` |
| Rétention/purge 14.11 | `tools/retention_production.py`, `backend/account_admin.py`, `tests/test_retention.py`, `tests/test_public_beta.py` |
| Récupération 14.12 | `backend/api.py`, `backend/services/documents.py`, `frontend/server/app.mjs`, `frontend/server/app.test.mjs`, `frontend/src/components/DocumentTable.tsx`, `frontend/src/pages/DocumentDetail.tsx`, `tests/test_documents.py` |
| Fiabilité de recette 14.14 | `tests/conftest.py`, `tests/test_config_and_schema.py`, ce rapport |

Les ajustements de fixtures isolent explicitement les tests du contenu de
l'environnement local : IA désactivée pour la fixture générale, profil public
testé avec IA désactivée, et test de démarrage sans clé exécuté sur une base
migrée jetable. Ils ne modifient aucune valeur de production.

## 2. Cohérence technique

| Sujet | Vérification | Résultat |
| --- | --- | --- |
| Migrations | La suite Python exécute `alembic check`; aucune migration n'est ajoutée ou modifiée. | Conforme localement. |
| Dépendances | Aucun manifeste Python ou frontend, lockfile ou image n'est modifié. | Conforme. |
| Rétention | Politique simulée configurable 7/4/3, plan horodaté/empreinté, verrous, alertes minimisées et refus sur incohérence. `--execute` refuse toujours l'exécution. | Non destructif et fail-closed. |
| Comptes non vérifiés | Seuil par défaut de sept jours, dry-run par défaut, `--execute` explicite, compteur cumulatif jamais décrémenté. | Conforme à la contrainte. |
| Téléchargement | API propriétaire + vérification du fichier opaque, taille/empreinte, flux par blocs ; BFF authentifié valide les métadonnées et ne relaie pas d'en-tête arbitraire. | Isolation préservée par tests propriétaire, session absente/expirée, fichier absent/corrompu et identité de stockage hostile. |
| ZIP global | Non livré afin d'éviter archive temporaire, pression mémoire/espace et nettoyage non démontrés. | Limitation assumée et documentée. |
| IA/inscriptions | Les garde-fous existants restent en place ; aucun code ne rouvre le verrou SQL ou n'active l'IA. | Conforme. |
| Pages légales | Routes publiques, versions locales et liens permanents existent ; les documents affichent encore leur statut de brouillon. | Ne pas les présenter comme approuvés. |

Le registre local de CGU doit être revu avant publication : les rapports
antérieurs référencent une version `beta-2026-10-26-draft-1`, tandis que le
registre source contient aussi une version courante de travail. La RC ne doit
ni choisir ni rendre acceptée une version juridique : la future version
approuvée devra être archivée, empreintée et correspondre exactement à
`PUBLIC_TERMS_VERSION` et à son URL HTTPS.

## 3. Résultats de validation

| Commande | Résultat |
| --- | --- |
| `python -m pytest -q --basetemp .pytest-s14-14-final-retry` | **820 réussis, 70 ignorés**, 0 échec ; 2 avertissements Pytest de cache Windows non inscriptible. |
| `npm.cmd run test:bff` depuis `frontend` | Réussi. |
| `npm.cmd run test:ui` depuis `frontend` | **64 réussis**, 11 fichiers. |
| `npm.cmd run build` depuis `frontend` | TypeScript et Vite réussis. |
| `git diff --check` | Réussi. |

Les répertoires temporaires isolés utilisés par Pytest ont été supprimés. Les
tests ne prouvent pas le VPS, les timers, B2, SMTP Gmail, le reverse proxy ou
la disponibilité HTTPS publique.

## 4. Checklist de revue et publication GitHub Actions

1. Revoir le diff complet et la liste de fichiers ci-dessus ; exclure `.env`,
   `var/`, snapshots, secrets, données de test et artefacts de build.
2. Vérifier que le commit contient les rapports et tous les tests associés,
   sans modifier le verrou SQL, le compteur, l'IA, les dépendances ou les
   fichiers de production hors procédure approuvée.
3. Créer le commit/PR uniquement après autorisation explicite ; ne pas
   automatiquement pousser, fusionner ou taguer.
4. Attendre la CI GitHub Actions complète : Python, Windows, PostgreSQL,
   frontend/BFF et contrôles de release requis par la branche protégée.
5. Pour une future livraison fermée, vérifier depuis les outils de release
   actuels le SHA, workflow/run/tentative, les trois digests amd64, les
   checksums du bundle et l'ancre de confiance externe. Un hash local, un tag
   mutable ou un ancien contrôleur ne suffit pas.
6. Obtenir une autorisation distincte pour déployer le bundle attesté en mode
   fermé. Cette autorisation ne vaut pas ouverture des inscriptions.

## 5. Déploiement fermé et retour sûr

Avant toute livraison fermée autorisée, vérifier sans secrets exposés : snapshot
restaurable identifié, espace disque, marqueurs de maintenance, timers,
configuration résolue, schéma attendu, verrou fermé et compteur monotone. Le
déploiement doit rester avec inscriptions désactivées et IA désactivée, puis
contrôler santé API/BFF, HTTPS, digests et état SQL.

En incident, utiliser la fermeture d'urgence contrôlée ou rester fermé ; ne pas
réinitialiser le compteur, supprimer un compte pour recréer une place, exécuter
une rétention destructive, restaurer une ancienne base de production ou
contourner le contrôleur/registre de release. Tout retour exige un candidat
attesté compatible avec le schéma actuel et une approbation indépendante.

## 6. Blocages persistants

- [ ] Revue humaine et commit/PR autorisés du lot local.
- [ ] CI GitHub Actions, digests et attestation vérifiés.
- [ ] Vérifications VPS/B2/Restic, restauration isolée, SMTP Gmail, timers,
  logs, reverse proxy et HTTPS effectuées avec autorisation.
- [ ] Recette des téléchargements HTTPS, sessions expirées/interrompues et
  assistance de fermeture sur la stack cible.
- [ ] Inventaire de cookies/traceurs sur la stack livrée.
- [ ] Textes juridiques, prestataires, durées, rôles, réclamations/médiation,
  version/URLs des CGU et politique de fermeture validés par les personnes
  compétentes.
- [ ] Décisions distinctes de livraison fermée et d'ouverture publique.

Tant qu'une case reste ouverte, le statut public demeure **NO-GO**. La création
d'une RC Git reste seulement conditionnellement admissible après revue et CI ;
elle n'infère aucune approbation juridique ni autorisation d'ouverture.
