# Matrice de revue des 43 wheels P4

**43 contenus/RECORD/tags conformes statiquement ; 0 approbation P4.**

ABI/imports reels CPython3.11.18 : NON EXECUTES pour toutes les lignes.
Les tags supposent la cible glibc2.41 de v1, pas une base observee.
Les hashes exacts sont aussi dans materials/DEPENDENCIES_OBSERVED.json.

| Distribution | Version | Inclusion | Provenance observee | SHA256 wheel | Decision |
|---|---|---|---|---|---|
| alembic | 1.20.0 | harness, commandes migration interdites | archive historique hashee | `77eb101048d95f982c0353e9233404889dcd7a6fc244c107836c0e2fc9cf7d9d` | NON APPROUVE |
| annotated-doc | 0.0.5 | transitif de fastapi | archive historique hashee | `117bac03a25ede5df5440e855b32d556049ca169ead221505badf432fed4b101` | NON APPROUVE |
| annotated-types | 0.8.0 | transitif de pydantic | archive historique hashee | `f072f4d804ea359e4eaf198b1af7a8b0943881a87f31bb764f8bf219bb9419e0` | NON APPROUVE |
| anyio | 4.15.1 | transitif de httpx, openai, starlette | archive historique hashee | `6152fdbbf9a77fdec97731721bebf7c4c44f7c29b424b0065826173efc7ed101` | NON APPROUVE |
| argon2-cffi | 25.1.0 | backend.auth | archive historique hashee | `fdc8b074db390fccb6eb4a3604ae7231f219aa669a2652e0f20e16ba513d5741` | NON APPROUVE |
| argon2-cffi-bindings | 26.1.0 | transitif de argon2-cffi | archive historique hashee | `27f1821903e2ceadcb88ec2b45ef190897b7682449c772f4d9b53e42c520cf29` | NON APPROUVE |
| certifi | 2026.10.18 | transitif de httpcore, httpx | archive historique hashee | `73191c47aaa79da394e8fee2dbc2ec827432cab56311122c9e47abf79e390f62` | NON APPROUVE |
| cffi | 2.1.1 | transitif de argon2-cffi-bindings | archive historique hashee | `34e261f78cb6ceaaa36f42f2613f4380d94d9c759a9c73c769ee6e0247364632` | NON APPROUVE |
| distro | 1.9.0 | transitif de openai | archive historique hashee | `7bffd925d65168f85027d8da9af6bddab658135b840670a223589bc0c8ef02b2` | NON APPROUVE |
| fastapi | 0.146.0 | application ASGI et routeurs reels | archive historique hashee | `0eb9985a7d5bb11ce9a962d4b65e0cf1a2e13d6aca2e14da57bc526370e26748` | NON APPROUVE |
| greenlet | 3.5.6 | transitif de sqlalchemy | archive historique hashee | `1c20ea32a73d17b9b60e3371240e17b0068120c98a5ec01a224a7dd8c89733ba` | NON APPROUVE |
| h11 | 0.16.0 | transitif de httpcore | archive historique hashee | `63cf8bbe7522de3bf65932fda1d9c2772064ffb3dae62d55932da54b31cb6c86` | NON APPROUVE |
| httpcore | 1.0.9 | transitif de httpx | archive historique hashee | `2d400746a40668fc9dec9810239072b40b4484b640a8c38fd654a024c7a1bf55` | NON APPROUVE |
| httpx | 0.28.1 | requetes ASGITransport | archive historique hashee | `d909fcccc110f8c7faf814ca82a9a4d816bc5a6dbfea25d6591d6985b8ba59ad` | NON APPROUVE |
| idna | 3.20 | transitif de anyio, httpx | archive historique hashee | `ab7ae7122974553370f0bdb919e1a960b2cd1bc1ef0276416d896db81c14582c` | NON APPROUVE |
| iniconfig | 2.3.1 | transitif de pytest | archive historique hashee | `9121e2c1fdb355232495be3194c8dfe87ccc2d5dee45947b78e68f499790d7a7` | NON APPROUVE |
| jiter | 0.17.0 | transitif de openai | archive historique hashee | `5888fe5abc1ca2fa834a3e1b4c7ef0dcece286a7d7e95a609ef0934b777b9fc9` | NON APPROUVE |
| Mako | 1.4.3 | transitif de alembic | archive historique hashee | `723296007c870bfd6b3f0c3230dba7198096e5269297ebf5e4eff9e7ffa39d4f` | NON APPROUVE |
| MarkupSafe | 3.0.4 | transitif de mako | archive historique hashee | `6da83a088f8ef93b2d483a8232a4dbf4d69d3d8496b568a03c56becac43e1808` | NON APPROUVE |
| openai | 2.54.0 | garde du lanceur et imports SDK | archive historique hashee | `89089789197ccdb87f173a03145ed1598d00795220c93e96cf712b1cbf5e5f2b` | NON APPROUVE |
| opentelemetry-api | 1.45.1 | transitif de fastapi | archive historique hashee | `b31553efa588ae44bc306f863c785c5333a9ecc091248c6ee68b4b6c87fdedfb` | NON APPROUVE |
| packaging | 26.3 | transitif de pytest | archive historique hashee | `d7193f7c8e4e93f444fde0262bf90af30e16fa0ad0ad44cb553c87339b23cd1c` | NON APPROUVE |
| pgvector | 0.5.1 | modeles RAG SQLAlchemy | archive historique hashee | `ec5bcd5ffaefe6ecb2dcc9564ca921d284564b969183bc837a144604773af8ea` | NON APPROUVE |
| pip | 25.2 | bootstrap zip seulement, conserve dans la selection des 43 | PyPI HTTPS + archive historique | `6d67a2b4e7f14d8b31b8b52648866fa717f45a1eb70e83002f4331d07e953717` | NON APPROUVE |
| pluggy | 1.7.0 | transitif de pytest | archive historique hashee | `7dd7b0d8832ba3cb632c306926ded123429211b83641b35dc5c41ad2d34f9bec` | NON APPROUVE |
| psutil | 7.2.2 | backend.services.worker importe | archive historique hashee | `076a2d2f923fd4821644f5ba89f059523da90dc9014e85f8e45a5774ca5bc6f9` | NON APPROUVE |
| psycopg | 3.3.6 | garde du lanceur/harness, extra binary | archive historique hashee | `a1db9f7148b06a28606767efaca51fa6f9398c5c0a3810519be69d7000bdb631` | NON APPROUVE |
| psycopg-binary | 3.3.6 | transitif de psycopg | archive historique hashee | `a2e44a342d2aee40508e28a563d8961c39d9bbd8cae36d8578f0a3c6658aab0f` | NON APPROUVE |
| pycparser | 3.12 | transitif de cffi | archive historique hashee | `a076f3f489b39b43ed13563a1dafe42447445bec2e294154ec5c57fcdda4c85e` | NON APPROUVE |
| pydantic | 2.14.1 | transitif de fastapi, openai, pydantic-settings | archive historique hashee | `9195d967ec791692a04438115466764fb8b9a27b31f14a760437694f40d6b454` | NON APPROUVE |
| pydantic_core | 2.50.1 | transitif de pydantic | archive historique hashee | `8812592c85d0edf423f10eadcef42716d71e8219085ad9e85b775057b7306133` | NON APPROUVE |
| pydantic-settings | 2.16.0 | Settings | archive historique hashee | `7e73acf7f61936a15e5a3b6eedaea29f133357faf7272f2607ba479b049dd7f2` | NON APPROUVE |
| Pygments | 2.21.0 | transitif de pytest | archive historique hashee | `2363c69b61c4a97c838da3b130dcd6468f4848992b21a82f2a63ec34377137d9` | NON APPROUVE |
| pytest | 9.1.1 | lanceur r3 | archive historique hashee | `37a86b45efb9a47a61a36449063e8e18d0cab3161329fc099eb21783169c4f0c` | NON APPROUVE |
| python-dotenv | 1.2.4 | transitif de pydantic-settings | archive historique hashee | `42269a8a5b3fd54ffa6f3d84b18abed50064717576b4ecf03dc4a55d8aa04fdc` | NON APPROUVE |
| python-multipart | 0.0.32 | declarations des routes FastAPI | archive historique hashee | `ff6d3f776f16878c894e52e107296ffc890e913c611b1a4ec6c44e2821fe2e23` | NON APPROUVE |
| PyYAML | 6.0.3 | controle statique seulement, pas le profil monte | PyPI HTTPS + fichier local | `b8bb0864c5a28024fac8a632c443c87c5aa6f215c0b126c449ae1a150412f31d` | NON APPROUVE |
| sniffio | 1.3.1 | transitif de openai | archive historique hashee | `2f6da418d1f1e0fddd844478f41680e794e6051915791a034ff65e5f100525a2` | NON APPROUVE |
| SQLAlchemy | 2.0.55 | garde du lanceur, modeles et harness | archive historique hashee | `7251866982c2bb5a62d900bed7b4b88c1b09f9ff494b9dd152610cb5a99bb4d6` | NON APPROUVE |
| starlette | 1.9.0 | transitif de fastapi | archive historique hashee | `fd3f159936e882d06c1108f84688f7cda2cf85fc6a592a50edbd175e882c2ddc` | NON APPROUVE |
| tqdm | 4.70.1 | transitif de openai | archive historique hashee | `c293e525e6fef9c20e8728fd4612df02a0aa31bb5fe91ecd93e123b1b7bffa73` | NON APPROUVE |
| typing_extensions | 4.16.0 | transitif de alembic, anyio, fastapi, openai, opentelemetry-api, psycopg, pydantic, pydantic-core, pydantic-settings, sqlalchemy, starlette, typing-inspection | archive historique hashee | `481caa481374e813c1b176ada14e97f1f67a4539ce9cfeb3f350d78d6370c2e8` | NON APPROUVE |
| typing-inspection | 0.4.4 | transitif de fastapi, pydantic, pydantic-settings | archive historique hashee | `65b8397ba37ccbce054456aaccddfc91e6e3083c92824df348d96ca832f3f147` | NON APPROUVE |

Le profil applicatif standard n'active pas fastapi[standard]. Seul psycopg[binary] est active. Aucun extra reseau/CLI/IA ne l'est.
