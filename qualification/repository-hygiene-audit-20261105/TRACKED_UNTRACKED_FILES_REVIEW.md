# Revue des familles suivies et non suivies

Diagnostic : conserver d'abord; ni non-suivi ni ignore ne signifie inutile.
Les comptes initiaux et leurs limites sont dans `GIT_STATUS_INVENTORY.md`.

| Famille | Decision proposee apres autorisation | Motif |
|---|---|---|
| Backend, BFF, frontend courants et tests associes | Versionner par lots examines | Modifications applicatives utiles, parfois de securite |
| `backend\lite_*.py`, `lifecycle_bootstrap.py`, outils Lite et tests nouveaux | Conserver puis examiner pour un lot coherent distinct | Branche fonctionnelle non equivalente a la candidate dix admissions |
| `tools\lifecycle_key_policy.py`, restauration, backup et tests hardening | Conserver ensemble | Politique de permissions et fermeture du quota apres restauration |
| Modeles `.env.*.example`, Compose, lockfiles, migrations | Versionner apres revue privee des modeles et de leur coherence | Configuration source, pas donnees runtime |
| Rapports expurges, manifestes, ancres, decisions NO-GO | Versionner apres revue | Traçabilite durable et lisible |
| `qualification\p4_*`, B1, comparateurs v1/v2, contenus P3 | Conserver sans rewriting; sources/rapports expurges a suivre | Versions et portees de preuve differentes |
| `candidates\recovery-control-directory-v1*` | Conserver les trois revisions, puis cataloguer | Revisions historiques, pas duplication jetable |
| `exports\public-beta-candidate-*` | Conserver bytes et liens aux commits; archivage controle possible ensuite | Instantanes distincts, pas une release courante autorisee |
| Livraisons backup v5 et v5.1, branding R1/R2, lifecycle dix | Conserver separement | Preuves attachees a chaque candidate |
| Images TAR, ZIP de livraison, wheels offline, dumps et donnees | Hors publication Git par defaut; depot de preuves prive et catalogue expurge a etudier | Volume, confidentialite et chaine de conservation |
| `var`, `.env`, TLS et archives privees deja ignores | Sauvegarde privee, avec tri reproductible/non reproductible | Git ne les preserve pas |
| Cache npm R1, caches d'outils | Sauvegarder puis proposer exclusion precise | Regenerabilite a confirmer hors ligne |
| Dist de reference et dist exports | Conserver avec leur manifeste | Generes mais probants |
| Cinq `.tmp_*.py` racine | Archiver comme travail, examiner avant retrait ulterieur | Scripts de transformation sauvegarde/restauration, sans appel courant trouve |

**Aucun retrait du suivi n'est propose sur la seule extension.** Aucun fichier
suivi actuellement demontre comme cache a retirer de l'index.
Les fichiers opaques et prives restent non audites en contenu.

## Travaux non suivis a ne pas perdre

Nouveaux modules : `backend\lifecycle_bootstrap.py`, `backend\lite_admissions.py`,
`lite_authority.py`, `lite_deletions.py`, `lite_reconciliation.py`,
`lite_release.py`, `lite_snapshot.py`; outils `lifecycle_key_policy.py`,
`lite_authority.py`, `lite_restore.py`, `public_beta_backup.py`,
`public_beta_restic_guard.py`, `restore_pgvector.py`.

Tests nouveaux : familles `test_lite_*`, `test_lifecycle_backup_lock.py`,
`test_lifecycle_key_permissions_v51.py`, `test_lifecycle_keys_restore.py`,
`test_public_beta_backup.py`, `test_public_beta_restic_guard.py`,
`test_recovery_quarantine_inprocess.py`, `test_recovery_quarantine_restored_latch.py`,
`test_restore_hardening.py`, `test_restore_hardening_postgres.py`,
`test_restore_pgvector.py`, et `frontend\src\pages\BetaLite.test.tsx`.
Conserver aussi le script d'export PowerShell, le test operateur owner-mismatch,
`Brand.tsx` et `docnelo-tokens.css`. Ce sont des sources, pas des logs regeneres.

## HEAD / worktree / candidate / beta

La candidate isolee est au commit `8b11d4daf47bd7c3c6766b9f5231ea8a84fdbf71`,
reference `a323afc5c9d63a8a9f59ac10c365710b58d1c868`.
Ses **15 fichiers du manifeste source ont a nouveau leurs SHA-256 conformes**.
Aucun de ces 15 contenus n'est identique a la version courante correspondante.

| Situation face au manifeste de la candidate | Chemins |
|---|---|
| Presents mais modifies par rapport a HEAD et differents de la candidate | `backend\account_admin.py`, `account_api.py`, `config.py`, `lifecycle_durability.py`, `main.py`, `public_registration.py` |
| Presents, identiques a HEAD mais differents de la candidate | `backend\lifecycle_admissions.py`, `lifecycle_snapshot.py`, `tools\public_beta_policy.py` |
| Absents du worktree principal et de HEAD | `backend\lifecycle_capacity.py`, `tests\capacity_roundtrip.py`, `lifecycle_group_key_probe.py`, `test_public_beta_capacity_backup.py`, `test_public_beta_capacity_failures.py`, `test_public_beta_capacity_ten.py` |

Ces six absences ne sont pas des suppressions Git : ces fichiers appartiennent a
la candidate isolee. Ils ne doivent pas etre recrees ici par fusion automatique.
Les 227 tests API/PostgreSQL/lifecycle, 50 BFF et 11 operateur ainsi que le
round-trip synthetique et le refus de la onzieme admission restent attaches a
leur candidate, pas aux 44 modifications de ce worktree.

Le worktree contient notamment un correctif de download BFF absent du runtime R2
(`frontend\server\app.mjs:297-323`, tests `app.test.mjs:213-257`) et une fermeture
du quota restaure dans `tools\validate_restore.py:344-360`. Les modifications
auth/session, quarantaine, durabilite, dependencies et documents doivent rester
preservees avec leurs tests; leur presence ne vaut pas qualification.

La release effectivement destinee a la beta n'est pas un assemblage autorise
demontre par cet audit. Les sources scellees, les rapports historiques, HEAD, le
worktree et une image reellement deployee sont cinq objets distincts.
Voir aussi les sept rapports `qualification\beta-10-readiness-audit-20261105`.

Ne modifier ni compteurs, temoins, pending, verrous, latch, schema ou seuils pour
faire converger les copies. Les identifiants DocuMind encore utilises dans les
packages, volumes et commandes ne sont pas des restes automatiquement supprimables.
