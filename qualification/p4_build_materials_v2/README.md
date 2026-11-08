# P4 Build Materials v2

**BLOCKED - review-only. Aucun GO build/create/start/production.**

Commencer par `P4_BUILD_MATERIALS_REPORT.md`, puis
`P4_DOCKER_BUILD_PROTOCOL.md` et `TRANSFER.md`.

| Livrable | Portee |
|---|---|
| P4_IMAGE_COMPONENTS.json | Base non identifiee, composants manquants, identites/hashes observes |
| P4_NATIVE_CLOSURE.json | 32 ELF, versions et120 liens, dont89 non resolus sans base |
| P4_WHEEL_APPROVAL_MATRIX.md |43 distributions justifiees, integrite statique, aucune approbation inventee |
| P4_UPSTREAM_COMPARISONS.json | Concordance exacte PyPI pour PyYAML/pip, pas une signature |
| P4_PIP_BOOTSTRAP.json | pip25.2 vendored et probe zip Windows, cible CP311 non qualifiee |
| P4_PREPARATION_DECISION.json | NO-GO explicite avec blocages |
| materials/ |43 wheels, inventaire v1 byte-identique, lock propose |

Les scripts sont offline : image_catalog.py (metadata archives seulement),
wheels.py, native.py, bootstrap_probe.py, report_materials.py, gate.py,
common.py, preserve.py et transfer.py. record.py n'execute une commande
que si l'operateur la fournit explicitement. Les captures historiques
contiennent des commandes de lecture/acquisition, pas des instructions
a relancer sur Debian.
verify_materials.py reproduit les controles statiques, y compris les
comparaisons PyPI archivees, sans acces aux anciens transferts ni reseau.

Aucun Dockerfile executable n'est fourni : la base CPython3.11.18,
la fermeture systeme et le builder offline ne sont pas qualifies.
Ne pas substituer CP313, un venv hote ou l'image P3 non approuvee.

Controles des nouveaux outils sur la machine de preparation, pas P4 :

```text
.\.venv\Scripts\python.exe -I -B -m unittest discover -s qualification\p4_build_materials_v2\tests -v
```
