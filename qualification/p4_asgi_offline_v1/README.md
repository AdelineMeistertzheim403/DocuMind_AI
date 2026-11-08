# Docnelo V5.1 - complement P4 ASGI Docker offline

**PROPOSITION POUR EXAMEN UNIQUEMENT. Aucun GO build, create, start, P4,
Docker applicatif ou production. Aucune execution Docker dans cette preparation.**

Ce paquet est independant de v1/r2/r3. Il ne contient ni backend modifie,
ni copie corrigee du middleware, ni nouvelle preuve Debian.
Le candidat complet r3 reste une entree externe, verifiee par son ancre.

| Document | Usage |
|---|---|
| `PREPARATION_REPORT.md` | Analyse, statut reel, limites et blocages |
| `DEPENDENCIES.md` | Selection Python, composants natifs, methode de fermeture |
| `DEPENDENCIES_OBSERVED.json` | Versions, wheels, SHA, tags, Requires-Dist et 32 fichiers ELF |
| `IMAGE_COMPONENTS.pending.json` | Composants d'image et fermetures natives non fournis/approuves |
| `DEBIAN_P4_PROTOCOL.md` | Points d'arret et sequence operateur differee |
| `TEST_MATRIX.md` | 18 cas par profil, oracles et verdicts |
| `TRANSFER.md` | Ancres, transport et conservation |

Les scripts ne contactent pas Docker, sauf `collect.py` **si l'operateur lui
fournit explicitement une commande Docker**. `offline.py` et `check_create.py`
sont purement offline. `p4_control.py` refuse le prefixe historique
`docnelo-rcd-*` et exige root/Linux et une autorisation synthetique explicite.
Les fichiers `*.pending.json` sont volontairement inutilisables tels quels.
Le build-gate refuse toujours dans cette revision, meme si le formulaire
d'approbation est rempli : une revision de construction revue est necessaire.

Verification locale des nouveaux outils seulement, sans P1/P2/P3/D11 :
interpreter et `packaging26.3` deja verifies, par exemple le venv existant
Windows (pas d'installation) :

```text
.\.venv\Scripts\python.exe -I -B -m unittest discover -s qualification\p4_asgi_offline_v1\tests -v
```

Le paquet transfere est accompagne d'un SHA256SUMS exact. Les SHA sont des
controles d'integrite, **pas des signatures ni une approbation de provenance**.
