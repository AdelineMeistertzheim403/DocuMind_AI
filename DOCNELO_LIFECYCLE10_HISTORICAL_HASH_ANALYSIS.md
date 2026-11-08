# Lifecycle 10 — Analyse historique de l’empreinte API

Date : 31 octobre 2026. **Verdict : NO-GO maintenu.**

## Conclusion

Les sources locales permettent d’isoler trois familles : 280 lignes sans sept déclarations lifecycle explicites dans l’API, 300 lignes avec magasins plats, puis 362 lignes avec répertoires séparés. La différence API entre 300 et 362 lignes est limitée aux cinq chemins ; les autres différences de ces deux versions sont dans `lifecycle-init`.

La piste la plus précise issue des sources est la version **280 lignes** : elle ne déclare ni les cinq chemins de magasins, ni les deux chemins de clés. Un env_file fournissant ces sept valeurs peut produire un environnement effectif identique à la version courante, avec un autre hash. Ce cas est reproduit avec Compose 2.35.1. Il reste à vérifier si les fichiers d’environnement et la chaîne de création réels expliquent cette représentation historique.

Les tests avec Compose 2.35.1 démontrent que les changements de `lifecycle-init` seuls ne changent pas le hash API. Remplacer en mémoire les cinq chemins de l’ancienne déclaration par ceux de la nouvelle suffit à retrouver le hash API de la nouvelle source, dans un contexte synthétique constant. Cette construction est une expérience d’attribution, jamais une configuration à déployer ni une preuve de provenance.

Selon les observations opérateur, l’API active possède déjà les cinq valeurs nouvelles. La sauvegarde seule, sans entrée de création supplémentaire remplaçant ces valeurs, est donc incompatible avec cet environnement effectif. La sauvegarde assortie d’overrides historiques reste à examiner. Il n’est pas démontré que l’un des fichiers locaux soit le fichier utilisé sur le VPS.

## Preuves reçues du VPS

* Rejeu fidèle avec `defer_paths` sur Compose 2.35.1 ; résolution prématurée des chemins r1 confirmée.
* API : C différent de D, malgré référence textuelle d’image concordante ; Web R2 et DB conformes.
* Sauvegarde retrouvée : `/opt/documind-public-beta/public-beta-candidate-20261030T234818Z/compose.public-beta.vps.yaml.bak.20261031-005952`, 300 lignes.
* Fichier courant : 362 lignes. Cinq chemins API : sauvegarde 0/5 concordants, courant 5/5.
* Création API annoncée : **2026-10-31 01:11:06 UTC**.

Ces observations sont fournies par l’opératrice. Ni le fichier `.bak` réel, ni ses empreintes, ni le rapport r2 complet n’ont été lus depuis ce poste. Aucun accès VPS n’a eu lieu.

## Inventaire local vérifié

| Fichier | Lignes | SHA-256 |
|---|---:|---|
| `compose.public-beta.vps.yaml` | 362 | `f46571b71b7a3174c96b15b2848f2b31cdae60339621116eb14be03393dc4ff2` |
| Exports `20261030T234658Z` et `20261030T234818Z`, fichier Compose | 300 chacun | `15f42bf1f3332d2052c0f304994d0fab455fe86a84c627e4749195123d3c0fd0` |
| Exports `20261030T234213Z` et `20261030T234303Z`, fichier Compose | 280 chacun | `8fd28b87a0b03a1fa409e5b63161eaa6134cd705fbb6315dbb45bb3b2cbcb515` |

L’entrée Compose du `MANIFEST.sha256` de l’export `20261030T234818Z` correspond au SHA-256 300 lignes ci-dessus. Le manifeste lui-même a pour SHA-256 `47143ad4934c2bcc91225c8cfa0f92c1e036707e861514e9142a8ad212e0630b`. Cela identifie une copie locale conservée ; cela ne prouve pas son transfert ou son utilisation sur le VPS.

La taille en lignes n’identifie pas des octets. La première vérification opérateur est de comparer les SHA-256 des fichiers VPS aux familles ci-dessus. Une différence peut notamment venir des fins de ligne ; seule une comparaison de modèles qualifiée peut ensuite établir l’équivalence déclarative.

## Historique Git et chronologie

| Révision touchant le Compose | Lignes / blob Git | Date auteur et commit, convertie en UTC |
|---|---|---|
| `727b95a928d2378d48020ba893463c37a8dcf947` | 300 / `cb2ff689ecb483d58dba7388baabad610bcf4a4b` | 2026-10-30 23:50:10Z |
| `f6e08955b648012ad53355ba033f35d0d35ca71a` | 362 / `d712ea8b6a138a4077feedf7b59fd48fde7cd03b` | 2026-10-31 00:53:53Z |
| `3727f4c49f22a0129bb6e41270815b7e5a6d74ec` | 362 / même blob | 2026-10-31 08:20:40Z |
| `5927e86a3526f0f77935d7f6b8a47b1ba0183a40` | 362 / même blob | 2026-10-31 09:02:23Z |

Les trois révisions de 362 lignes portent le même blob Compose. Elles ne constituent donc pas trois configurations distinctes expliquant une dérive API.

La version corrigée existe dans Git 17 min 13 s avant l’heure de création API annoncée. C’est cohérent avec une intervention entre les deux, sans en prouver la réalisation. Les horloges et dates Git ne sont pas une attestation de déploiement.

Le suffixe `.bak.20261031-005952` n’indique pas de fuseau et ne prouve pas l’instant de copie. Un `cp -a` peut aussi conserver le mtime source. Ne pas conclure « sauvegarde antérieure donc source utilisée » à partir du nom, du mtime ou d’un nombre de lignes. Il faut le journal de l’action et son contexte horaire.

## Modèles comparés localement

Le modèle ancien est celui de l’export 300 lignes identifié ci-dessus ; le modèle nouveau est la source locale 362 lignes. Le moteur officiel 2.35.1 les charge avec un seul contexte synthétique, un même projet physique de laboratoire, des env_file fictifs et aucune image réellement lancée. `defer_paths` est fidèle pour les deux.

Les différences API sont exactement :

| Variable | Ancienne source locale | Nouvelle source locale |
|---|---|---|
| `LIFECYCLE_REGISTRY_PATH` | `/app/lifecycle/registry.sqlite` | `/app/lifecycle/registry/registry.sqlite` |
| `LIFECYCLE_CONFIRMATION_PATH` | `/app/lifecycle/confirmation.sqlite` | `/app/lifecycle/confirmation/confirmation.sqlite` |
| `LIFECYCLE_AUTHENTICATED_CONFIRMATION_PATH` | `/app/lifecycle/authenticated-confirmation.sqlite` | `/app/lifecycle/authenticated/authenticated-confirmation.sqlite` |
| `LIFECYCLE_HOLDS_PATH` | `/app/lifecycle/holds.sqlite` | `/app/lifecycle/holds/holds.sqlite` |
| `LIFECYCLE_ADMISSION_ANCHOR_PATH` | `/app/lifecycle/admission-anchor.sqlite` | `/app/lifecycle/admissions/admission-anchor.sqlite` |

Dans `lifecycle-init`, les différences de modèles concernent `cap_add`, `command` et les mêmes cinq variables. Les modèles DB/Web sont identiques entre ces sources, dans le contexte testé.

### Famille antérieure de 280 lignes

La comparaison de son API avec celle de 362 lignes identifie **exactement sept ajouts déclaratifs** : les cinq variables de magasins ci-dessus, plus `LIFECYCLE_AUTHENTICATION_KEY_PATH` et `LIFECYCLE_ADMISSION_KEY_PATH`. Les autres champs du modèle API sont identiques dans le contexte constant testé.

Un test charge ces sept valeurs depuis un env_file fictif : les environnements effectifs API des versions 280 et 362 deviennent égaux, mais leurs hashes restent différents. Un second test omet uniquement ces sept déclarations dans une copie en mémoire du modèle courant : il retrouve le modèle API et le hash de la source 280, sans changer les hashes DB/Web.

Cette piste ne repose donc pas sur une recherche arbitraire de valeurs. Elle repose sur une source exportée conservée et une différence structurelle exacte. Elle ne prouve toutefois ni que le VPS possédait les sept valeurs dans son env_file à 01:11:06Z, ni que le modèle 280 a servi à créer l’API. Une simulation bornée côté opérateur peut vérifier sa compatibilité avec D et les valeurs effectives, sans écrire une nouvelle configuration.

Le rapport local `DOCUMIND_PUBLIC_BETA_LIFECYCLE_INIT_OWNER_MISMATCH_FIX_REPORT.md` explique cette évolution : stores séparés, provisionnement en deux phases et traitement des propriétaires. Il fournit une intention technique et des résultats de laboratoire ; ses anciennes commandes d’intervention ne sont **pas** à réexécuter pour le diagnostic actuel.

## Ce qui participe au hash

Compose 2.35.1 calcule `ServiceHash` sur le modèle **du service concerné**, après exclusions de build, pull_policy, scale, deploy.replicas, depends_on et profiles. Changer un autre service ne suffit pas à changer le hash API. Un changement de YAML partagé ou d’interpolation pourrait toutefois modifier indirectement le modèle API ; c’est pour cela que les modèles effectivement résolus sont comparés. [Source officielle ServiceHash](https://github.com/docker/compose/blob/v2.35.1/pkg/compose/hash.go).

Le calcul CLI du hash charge sans résolution des environnements de service. Les déclarations explicites et les déclarations env_file restent distinctes. Le rendu aplati peut perdre leur origine ou résoudre trop tôt les chemins ; `defer_paths` et la vérification de son rejeu restent obligatoires. [Source officielle config/runHash](https://github.com/docker/compose/blob/v2.35.1/cmd/compose/config.go).

Les deux anciennes valeurs publiques de contact/opérateur, chargées uniquement par env_file dans le cas observé, ne constituent donc pas à elles seules une explication de C ≠ D. Ajouter ces valeurs dans `environment` fabriquerait une autre déclaration. Aucun gel de ce type n’est utilisé comme preuve historique ici.

## Hypothèses classées par preuves

| Hypothèse | Niveau / priorité | Conclusion ou preuve manquante |
|---|---|---|
| Rejeu r1 infidèle | Confirmé puis corrigé pour le diagnostic | Ne reste plus une explication de l’écart natif C/D |
| Grand diff de `lifecycle-init` suffisant à expliquer D API | Écarté pour les deux sources locales testées | Changer seulement init conserve le hash API ; revoir uniquement si un modèle API indirectement différent est démontré |
| Sauvegarde 300 lignes seule, sans override pertinent | Fortement incompatible avec les 0/5 effectifs annoncés | Les cinq valeurs explicites auraient imposé les anciens chemins lors d’une création Compose ordinaire |
| Sauvegarde plus correction historique des seuls cinq chemins | Piste bornée, insuffisante si mêmes modèles que localement | Retrouve C dans le test ; n’explique pas un troisième hash D. Un autre champ/contexte est alors nécessaire |
| Famille 280 lignes : sept déclarations API omises, valeurs venant d’env_file | **Piste prioritaire, étayée par les sources et les tests, non confirmée sur VPS** | Peut conserver le même environnement avec un hash différent ; vérifier les sept valeurs effectives via env_file et la compatibilité de hash, puis retrouver la chaîne de création authentifiée |
| Autre override, ordre ou contenu à la création | À vérifier en priorité | Labels config_files, copie authentifiée des octets, journal de création et ordre complet |
| Déclaration historique différente avec même runtime | Plausible, non prouvée | User/commande/workdir hérités ou explicites, présence de valeurs égales aux défauts, env_file chemin/format/ordre, healthcheck, délai d’arrêt, labels/options. Un inspect conforme ne retrouve pas ces choix sans ambiguïté |
| Contexte d’interpolation ou plateforme/compatibilité différent | Plausible, borné par les enregistrements | Retrouver les entrées réellement utilisées ; pas d’essais arbitraires de valeurs |
| Référence image textuelle différente | Dépriorisée par la concordance fournie | Ne pas la réintroduire comme cause sans nouveau fait contradictoire |
| Taille/nom/date de la sauvegarde prouvant son utilisation | Insuffisant | Identité de fichier et preuve de création manquent |

Cette classification ne suppose pas une troisième variable d’environnement secrète. La différence restante peut être purement déclarative, avec des valeurs effectives identiques. Web et DB conformes resserrent le périmètre sans établir la provenance de l’API.

## Preuve de provenance requise

Il faut relier une même chaîne de preuve à : l’ID exact du conteneur créé le 31 octobre à 01:11:06Z, son ID d’image et sa référence textuelle, la commande de création, le projet et répertoire de travail, les fichiers Compose/overrides ordonnés et leurs octets à cette date, les chemins/format/ordre env_file, les fichiers/variables d’interpolation et options de lancement.

Un relevé d’intervention ou une archive scellée à cette date peut fournir ce lien. Le contenu actuel des chemins cités par les labels ne le fournit pas. Une histoire shell non horodatée est seulement un indice, potentiellement sensible ; ne pas la publier. La chaîne doit aussi expliquer les cinq chemins effectifs nouveaux.

Un hash égal à D est nécessaire pour la reproductibilité, mais ne prouve pas que la chaîne testée a réellement été utilisée. Les comparaisons avec le contexte actuel doivent être étiquetées comme telles, même lorsque les options d’un outil s’appellent « historiques ».

## Livrables et verdict

Procédure détaillée : `DOCNELO_LIFECYCLE10_HISTORICAL_HASH_OPERATOR_PROCEDURE.md`. Qualification : `DOCNELO_LIFECYCLE10_HISTORICAL_HASH_TEST_REPORT.md` et dossier `deliveries/docnelo-lifecycle10-historical-analysis-r1/` avec manifeste SHA-256.

Aucun nouveau contrôleur VPS n’est nécessaire : la procédure réutilise r2 scellé en lecture seule. Les expériences bornées restent en mémoire et ne sont pas proposées comme configuration de déploiement. Une simulation opérateur facultative permet de vérifier l’hypothèse des sept omissions sans fichier supplémentaire. Aucun fichier Compose, `.env`, label, conteneur, clé ou témoin existant n’a été modifié.

**NO-GO :** l’identité exacte de la sauvegarde VPS par rapport aux exports locaux, la chaîne déclarative de création et sa reproduction de D ne sont pas démontrées. Aucun contournement du garde, déploiement, redémarrage, migration ou ouverture autorisé.
