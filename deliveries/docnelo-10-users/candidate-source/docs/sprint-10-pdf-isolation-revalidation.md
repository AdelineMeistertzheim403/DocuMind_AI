# Sprint 10 phase B, lot 1 — reprise de validation

## Conclusion

Le moteur local existant a été repris sans réécriture. **Les preuves Landlock + seccomp
passent maintenant aussi dans Docker Desktop**, ainsi que la sonde et les extractions
PDF/TXT dans la véritable cible finale de l'image. Le minimum ABI 3 est conservé,
sans profil ABI 2 ni assouplissement de sécurité.

Le contexte de production communiqué est désormais Debian 12,
`6.12.95+deb12-cloud-amd64`, Landlock **ABI 6** sur l'hôte et dans l'API,
avec une restriction Landlock effectivement appliquée dans Docker. Ces éléments
proviennent de l'administratrice : **aucun accès distant n'a été effectué**.
Le blocage ABI 2 précédemment étudié est levé selon ce diagnostic. Cela ne vaut pas
encore validation de l'image Sprint 10 sur le profil exact du VPS.

**Publication et déploiement restent en attente d'autorisation.** Il reste à faire
valider le diff complet, obtenir la CI de la version exacte et approuver les contrôles
de recette puis le déploiement manuel. Aucun commit, push ou workflow n'a été lancé.

## État Git et préservation

Au début de cette reprise, le dépôt comporte 15 fichiers suivis modifiés et des fichiers
non suivis des Sprints 7 à 10. Ils sont intentionnellement conservés. Le bilan `git diff`
seul ne couvre donc pas tout ce qui doit être relu et, ultérieurement, publié.

Une référence SHA-256 de **219 fichiers suivis ou non suivis, non ignorés**, a été
enregistrée localement sous `var/sprint10-revalidation/baseline.json`, avant les changements
de cette reprise. Ce relevé ne lit pas les `.env` privés ignorés et ne constitue pas un
inventaire de secrets. Les 21 fichiers d'exploitation identifiés pour les Sprints 7–9
(outils, tests, documentation et unités sous `ops/`) sont inchangés par rapport à cette référence.
Les changements antérieurs du verrou de maintenance dans le déployeur sont aussi conservés.

Le moteur, le broker, les configurations applicatives, le Dockerfile, les Compose,
la CI, le déployeur, les dépendances et les migrations ne sont pas modifiés par cette reprise.
Les seuls changements versionnables apportés ici sont :

- `tests/test_extraction_linux.py` : **sept preuves supplémentaires**, sans modification
  de la politique : `open`/`openat` avec `O_RDONLY|O_TRUNC`, `truncate`, `ftruncate`, refus
  des syscalls de changement de limites, refus du runner si ABI insuffisante ou échec
  de chargement seccomp ;
- le présent rapport et des renvois dans les rapports de validation et de compatibilité
  historiques pour distinguer leurs limites anciennes des résultats actuels.

Les fautes injectées touchent seulement des processus enfants jetables de test. Dans
ces deux scénarios, le runner termine avec le code d'indisponibilité attendu avant
traitement de l'entrée ; le broker le traduit en échec de confinement, sans repli.

## Audit du confinement et de l'intégration

| Élément | Vérification |
| --- | --- |
| Entrée du parseur | Nouvel interpréteur `-I -S`, script fixe, document transmis par octets ; aucune commande ou chemin fourni par le document |
| Environnement/FD | Seulement la locale, `close_fds=True`, pipes dédiés, stderr vers `/dev/null`, nouveau groupe de processus |
| Landlock | Installation avant lecture de l'entrée et import PyMuPDF ; ABI ≥ 3 ; masque incluant `TRUNCATE` ; runtime autorisé uniquement en lecture |
| Seccomp | Refus par défaut ; réseau, exec/clone/fork, ptrace, accès interprocessus, namespaces, montages, changements de limites, ioctl/fcntl exclus |
| Ressources du parseur | AS ≤ 512 Mio, CPU ≤ 30 s, core et taille de fichier 0, FD 32, NPROC 1 ; temps mural ≤ 30 s et sortie ≤ 8 Mio contrôlés par le parent |
| Protocole | En-tête ≤ 1024 octets, entrée ≤ 10 Mio, ≤ 200 pages et ≤ 1 million de caractères ; JSON strict, types/champs et identifiant de job vérifiés |
| Échecs | Indisponibilité native ⇒ startup refusé ; pas de bascule automatique development ; échecs documentaires contrôlés et processus récupérés |
| Fonctionnel | Extraction depuis les octets par PyMuPDF ; pages conservées ; algorithmes d'analyse classique préservés |
| Production | Trois services, deux volumes et réseaux existants ; sandbox imposée dans Compose ; un processus API et deux slots de traitement |

Les tests vérifient le refus d'accès aux autres documents et aux marqueurs de secrets,
la fermeture des FD hérités, l'absence d'environnement sensible, les refus de sockets
IPv4/IPv6/Unix, la troncature, les limites et la récupération après crash/blocage/sortie
trop grande. Les tests HTTP vérifient aussi l'isolation entre comptes et l'état de l'API
après une erreur d'extraction. Aucune exploitation PDF native réelle n'est nécessaire.

## Tests exécutés lors de cette reprise

Les nombres se recoupent : **ne pas les additionner**. Les bases sont temporaires
SQLite ; `TEST_DATABASE_URL` est retirée ou vide. Les outils Docker/Restic des tests
d'exploitation sont simulés. Les vrais clients OpenAI sont interdits par la fixture
automatique ; les processus de test imposent aussi IA désactivée et clé vide.

| Série | Résultat |
| --- | --- |
| Suite Windows complète | **487 réussis, 33 ignorés**, 294,51 s ; preuves Linux ignorées sur cet OS |
| Linux WSL élargi : extraction/protocole, documents, moteur, transactions, déploiement, sauvegardes, Restic, surveillance, conservation | **416 réussis**, 122,43 s |
| Sept nouveaux cas Linux seuls | **7 réussis**, 33 désélectionnés, 6,90 s |
| Image Docker, preuves existantes avant ajout | **65 réussis**, 9,56 s |
| Image Docker reconstruite, preuves finales | **72 réussis**, aucun ignoré, 10,38 s |
| Build cible `isolation-tests` puis cible finale `production` | Réussis |
| Image finale : sonde native + TXT + PDF synthétique de deux pages | Réussis |
| Image finale : UID non root, seccomp, no-new-privileges, capacités effectives nulles | Vérifiés par assertions |
| Image finale : absence de `/app/tests`, pytest et fichiers `.env` applicatifs | Vérifiée |
| Résolution Compose de tests et production | Réussie ; fichier env de test explicite et valeurs fictives uniquement |
| `compileall` des modules/tests concernés | Réussi |
| actionlint des workflows CI et déploiement | Réussi, contrôles shellcheck/pyflakes non exécutés |

Les séries pytest produisent un avertissement de dépréciation Starlette/httpx,
sans échec. Aucun changement de dépendance n'est réalisé pour cet avertissement.
La collecte de la suite Windows a précédé l'ajout des sept nouveaux cas Linux : son
nombre de tests ignorés reflète cet instant. Les nouveaux cas ont ensuite tous été
exécutés dans WSL et dans la série Docker finale de 72 tests, sans test ignoré.
Le contrôle final des empreintes ne détecte que les trois fichiers déjà existants
mentionnés ci-dessus (test et deux rapports) ; aucun fichier de référence n'a disparu.
`git diff --check` est également passé.

### Environnements réellement utilisés

- Windows : venv existant, suite portable ; les preuves natives sont ignorées sur Windows.
  L'adaptateur development des fixtures n'est pas une preuve de confinement.
- Ubuntu WSL : Python 3.12.3, noyau `6.18.54.1-microsoft-standard-WSL2`, ABI 7.
- Docker Desktop 4.94.0, Engine 29.8.2, Linux amd64, même noyau WSL et ABI 7.
  Image finale : Python **3.13.16**, UID **1000**, `NoNewPrivs=1`, `Seccomp=2`, `CapEff=0`.
- Base du build : `python:3.13-slim@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f`.

Les images sont uniquement locales :

```text
documind-sprint10-validation:local
  sha256:d8723a712cae825c43054f628781d57ced72ce29dfa4c23711d6b58f020d9c1f
documind-sprint10-production-check:local
  sha256:fa8ea4538c6365d40a526a78cfeb2bee2300271a6376179fb88dfa6308208e83
```

Ces identifiants locaux ne sont pas des références de release approuvée dans la Registry.
Le build télécharge ses dépendances ; **les conteneurs exécutant les preuves et extractions
n'ont aucun réseau, montage de volume, secret, port publié ou accès Docker**.
Ils utilisent rootfs read-only, capabilities retirées, no-new-privileges, 1536 Mio,
2 CPU, 64 PID et seulement un tmpfs privé `/tmp` de 256 Mio, noexec/nosuid.
Ils sont supprimés par `--rm` ; les images et caches de build locaux sont conservés.

Le client utilise explicitement le socket local `dockerDesktopLinuxEngine` et un
répertoire de configuration Docker vide sous `var/`. Il ne contacte aucun contexte
distant ni la Registry privée. Aucun moteur ou service de production n'est lancé.

### Commandes reproductibles sans production

Dans un environnement local dédié, sans variables de connexion de production :

```bash
python -m pytest -p no:cacheprovider \
  tests/test_extraction_linux.py tests/test_extraction_protocol.py -q
python -m pytest -p no:cacheprovider \
  tests/test_extraction_linux.py tests/test_extraction_protocol.py \
  tests/test_documents.py tests/test_engine.py tests/test_transactions.py \
  tests/test_deployment.py tests/test_production_backups.py tests/test_restic_upload.py \
  tests/test_monitoring.py tests/test_retention.py -q
docker build --target isolation-tests -t documind-sprint10-validation:local .
docker run --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges --memory 1536m --cpus 2 --pids-limit 64 \
  --tmpfs /tmp:rw,noexec,nosuid,size=256m,mode=1777 documind-sprint10-validation:local
docker build --target production -t documind-sprint10-production-check:local .
docker run --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges --memory 1536m --cpus 2 --pids-limit 64 \
  --tmpfs /tmp:rw,noexec,nosuid,size=256m,mode=1777 --entrypoint python \
  documind-sprint10-production-check:local -I -S \
  /app/documind_extractor/runner.py 512 5 /usr/local/lib/python3.13/site-packages --check
```

La sortie attendue de la dernière sonde est `{"status":"ready"}`, code 0. Ne pas
utiliser le Compose principal ni charger les `.env` privés pour ces preuves.
Le Compose dédié peut aussi servir avec un fichier env vide explicitement désigné.

## CI, déploiement et retour arrière

La CI existante impose les preuves natives et celles dans Docker avant publication,
puis la suite SQLite et PostgreSQL 17/pgvector. Les tests frontend/BFF/TypeScript
sont un second job requis. Les images sont publiées sous SHA, puis référencées par
digest dans le bundle. Les actions sont épinglées ; actionlint et les tests de
configuration/déploiement passent localement. La CI distante n'a pas été déclenchée.

**Attention : un push sur `main` peut publier des images si la CI passe.** Il n'est
pas une opération de simple validation sans effet. Toute publication attend l'accord
explicite de l'administratrice. Le workflow de déploiement est exclusivement manuel,
avec approbation de l'environnement production, SHA/run précis et contrôle SSH/TLS.

Le nouveau lot ne change aucune migration : révision `0006`, volumes documentaire
sur `/app/var` et PostgreSQL sur `/var/lib/postgresql/data`. Le déployeur conserve
le verrou commun aux sauvegardes, le refus en présence d'une maintenance inachevée,
la sauvegarde préalable, la vérification de schéma et les contrôles HTTPS/CSRF/health.
Ces chemins sont exercés par simulations, pas par une sauvegarde ou connexion réelle.

Pour cette installation désormais active, la future procédure est une **mise à jour
ordinaire**, `initialize=false`, sans autorisation de migration pour ce lot ; ne pas
utiliser les procédures d'adoption d'une première installation partielle. Avant arrêt
de l'ancienne application, faire approuver et tester la nouvelle image par digest dans
une recette isolée adaptée au noyau/profil cible, sans secret ni volume de production.

Conserver le bundle précédent et la sauvegarde vérifiée. Si le nouveau démarrage échoue,
le déployeur tente de relancer l'ancienne application seulement si son schéma est compatible.
Le retour arrière manuel utilise le SHA/run antérieur approuvé, sans downgrade PostgreSQL
ou modification de volumes. Le retour à un moteur ancien réintroduit le risque traité
par ce lot : il doit être accepté explicitement sous accès privé. Ne jamais sélectionner
development comme solution de secours de la nouvelle release.

## Risques résiduels et validations encore nécessaires

1. **Image exacte sur le profil cible :** Docker local ABI 7 ne remplace pas une recette
   ABI 6 avec le profil de sécurité cible. La restriction testée dans l'ancienne API de
   production confirme une capacité, pas l'ensemble du nouveau runner et de PyMuPDF.
2. **CI de la version exacte :** PostgreSQL/pgvector réel et frontend/BFF/TypeScript ne
   sont pas réexécutés dans cette reprise ciblée ; exiger tous les jobs avant publication.
   Les tests locaux d'exploitation ne prouvent ni transfert B2 ni restauration réelle.
3. **Architecture :** preuves Docker amd64 seulement. La CI publie aussi arm64 ; sa
   construction sous QEMU n'est pas une preuve d'isolation sur un noyau arm64. Certifier
   séparément cette architecture avant d'y utiliser l'image.
4. **Modèle :** noyau et UID partagés, métadonnées partiellement visibles, bibliothèques
   autorisées devant rester sans secrets et immuables. Aucune résistance absolue aux
   failles noyau ou à la saturation globale n'est revendiquée.
5. **Périmètre d'audit :** ce lot ne résout pas les autres constats Sprint 10, notamment
   l'admission HTTP avant réception. Il n'autorise pas d'ouverture publique.
6. **Exploitation approuvée :** future sauvegarde, healthchecks/HTTPS et import/analyse
   classiques sur données fictives, puis vérification du cycle de sauvegarde/reprise.
   Préserver les secrets, les tâches Sprints 7–9, les inscriptions privées et l'IA désactivée.

Arrêt après ce rapport : aucune publication, modification distante, sauvegarde réelle,
restauration, activation IA/inscription, suppression de volumes, commit ou push.
