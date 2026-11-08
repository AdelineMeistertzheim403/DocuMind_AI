# Docnelo V5.1 Hardening — Debian Lab

Paquet minimal de développement, distinct de V5/V5.1 scellées.
**Aucune qualification Linux revendiquée. NO-GO production et Lifecycle 10.**

## Contenu et limites

Les neuf fichiers du rapport sont embarqués octet pour octet. Le builder
refuse un fichier absent, un symlink, un rapport divergent ou une empreinte
différente avant de créer un ZIP. Les dépendances locales des cinq suites
actives sont incluses, ainsi que le module de snapshot et ses dépendances.
Aucune donnée, DB, archive de capture, clé, env-file, image ou credential
réel n'est inclus. Les constantes des tests sont exclusivement synthétiques.

`tests/test_public_beta_snapshot.py` est conservé **comme référence seulement**,
avec son empreinte exacte. Ses fixtures applicatives historiques ne sont pas
livrées ; il n'est pas une suite exécutable de ce paquet minimal.
Les anciennes 167 réussites/13 exclusions du rapport ne sont pas attribuées
à ce ZIP et ne constituent pas une qualification Debian.

Le profil pytest autonome ne charge aucun conftest applicatif : ni backend.main,
ni fixture Alembic, ni configuration applicative, ni client API/OpenAI.
Son plugin garde le marquage POSIX et le refus des exclusions demandé par
`--require-no-skips`. Aucun seeding ou substitut de quiescence n'est ajouté.
Il ne remplace pas les gardes des modules livrés.

`SHA256SUMS` à la racine décrit tous les fichiers payload, pas lui-même.
Le SHA-256 externe du ZIP couvre aussi les octets de ce manifeste.
Le ZIP préserve les paths du dépôt, sans préfixe de release.

## Installation future autorisée — non exécutée

Transférer uniquement sous
`~/docnelo-lab/development/v5.1-hardening/`, jamais dans `release/v5.1`.
Vérifier le SHA externe avant extraction. Extraire dans un dossier nouveau ;
ne pas superposer ce paquet à un dépôt complet ou à une release.
Depuis la racine extraite : `sha256sum -c SHA256SUMS`.

Identifier Python 3.11 Linux et les binaires PG 17.11/pgvector 0.8.0.
Les trois versions Python de requirements.txt correspondent aux métadonnées
du poste de développement ; aucun wheel Linux ni lock transitif n'est livré.
Installation éventuelle dans un venv dédié autorisé avec des paquets déjà
approuvés : jamais une installation opportuniste sur la production.

Avant tests : confirmer absence de réseau externe, tunnel, service/daemon,
volume, DB et secrets de production. Aucune API ne doit être attachée aux
DB synthétiques de recette. Garder preuves et cibles partielles.

## Commandes de qualification future — non exécutées

Toujours se placer à la racine extraite. Utiliser explicitement le profil
de ce paquet ; ne pas utiliser les commandes du rapport sans ce `-c`.
Ne pas collecter le test historique de référence.

Suite de composants locaux sur Linux :

```text
python -m pytest -c qualification/docnelo_v51_hardening/pytest.ini -q --require-no-skips tests/test_lifecycle_backup_lock.py tests/test_restore_pgvector.py tests/test_restore_hardening.py tests/test_lifecycle_keys_restore.py
```

Intégrations PostgreSQL, uniquement après autorisation et prérequis :

```text
python -m pytest -c qualification/docnelo_v51_hardening/pytest.ini -q --require-no-skips tests/test_restore_hardening_postgres.py
```

Le second parcours exige les variables **synthétiques et de recette seulement**
documentées dans le rapport : DOCUMIND_HARDENING_POSTGRES_LAB,
DOCUMIND_RESTORE_LAB, DOCUMIND_HARDENING_EVIDENCE_ROOT,
DOCUMIND_RESTORE_DATABASE_URL, DOCUMIND_RESTORE_PREPARE_DATABASE_URL.
Aucune valeur de ces variables n'est exportée ou livrée par ce paquet.
Sans cible autorisée, ces trois tests restent non exécutés et ne sont pas PASS.

Les tests PostgreSQL créent des DB nouvelles et les conservent ; aucune
suppression ni réutilisation automatique. La préparation pgvector est
explicite et distincte du rôle de restauration, sans SUPERUSER pour celui-ci.
Une réussite de composant ne qualifie pas le round-trip backup/restore,
les stores/HMAC/paths/Compose/Restic, la provenance H0 ou Lifecycle 10.

## Reproduction du paquet — sans qualification

Depuis un checkout contenant ces seuls fichiers, le builder peut être appelé
avec une nouvelle destination ZIP :

```text
python qualification/docnelo_v51_hardening/build_package.py --output NEW_OUTPUT.zip
```

Il n'importe ni les modules applicatifs ni les tests et n'exécute aucun outil
de migration, capture ou restore. Il refuse toute sortie préexistante.
