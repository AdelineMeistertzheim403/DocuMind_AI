# P4 Base Runtime v3

**BLOCKED - proposition review-only, sans GO Docker ni production.**

Commencer par P4_BASE_RUNTIME_REPORT.md, P4_BASE_PROVENANCE.md,
P4_ROOTFS_BUILD_PROTOCOL.md et TRANSFER.md.

La revue nouvelle verifie1223 references de symboles versionnes dans
les31 liens prives des wheels. Les89 liens systeme restent bloques :
le rootfs P3 corrige et les fournisseurs Debian/CPython qualifies
ne sont pas remis localement. Aucune recette executable ne peut
etre delivree honnetement sans ces entrees.

P4_RUNTIME_COMPONENTS.json distingue noms/versions requis et fournisseurs
non fournis. P4_NATIVE_CLOSURE_REVIEW.json detaille ELF/dynsym/versions.
P4_PREPARATION_DECISION.json garde build/create/start/production false.

Scripts : review.py/elf_audit.py pour les bytes des wheels,
rootfs_check.py pour un futur arbre synthetique Linux fige,
image_check.py pour une future archive scratch monocouche.
Ces deux derniers ne qualifient ni un chargeur global ni l'ABI a eux seuls.
common.py, record.py, wheels.py, preserve.py sont des copies exactes
v2, autonomes dans ce paquet. transfer.py ne manipule que cette livraison.

Les tests des nouveaux outils se lancent sans installation ni Docker :

```text
.\.venv\Scripts\python.exe -I -B -m unittest discover -s qualification\p4_base_runtime_v3\tests -v
```

Conservation verifiee sur les1072 fichiers historiques scopes avant/apres,
y compris r3/v1/v2 et leurs preuves locales. Cela ne pretend pas inspecter
des namespaces distants ni remplacer les preuves Debian.
