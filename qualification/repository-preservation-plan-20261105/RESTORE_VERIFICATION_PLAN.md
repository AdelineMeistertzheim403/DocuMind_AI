# Verification integrale de restauration - procedure future

**RESTORE_TEST_EXECUTED=false. Aucune restauration realisee dans cette phase.**
Un controle d'archive ou quelques hashes echantillonnes ne suffisent pas.

## 1. Preparer R sans risque pour l'original

Choisir un nouvel emplacement protege, assez grand et vide, sur un environnement
isole. L'original doit etre absent ou inaccessible en ecriture a l'environnement
de test; des chemins `.git` absolus copies peuvent sinon atteindre l'original.
Pas de reseau, synchronisation cloud, execution d'application, de hooks, de tests
runtime, de SQL, de binaire de rootfs ou de Docker.

Verifier l'authenticite/integrite de l'enveloppe chiffree et son ancre externe,
puis dechiffrer uniquement sur stockage protege. Verifier que la cle de recuperation
independante suffit; la simple presence d'une cle dans la session courante
deverrouillee ne constitue pas un essai de reprise apres perte.
Ne pas extraire de chemins absolus, `..`, doublons, liens externes non autorises
ou archives inconnues en executant leur contenu.
Les archives historiques sont restaurees comme fichiers opaques, sans extraction.

## 2. Deux essais, deux autorites verifiees

Restaurer depuis A dans R-A, puis depuis B dans R-B, deux emplacements neufs.
Ils peuvent etre testes successivement pour economiser l'espace, seulement avec
autorisation propre de gestion des repertoires d'essai : aucune suppression
automatique n'est accordee par ce plan.
Verifier E independamment et essayer aussi sa restitution documentaire.
Ne pas utiliser une restauration de A pour simuler un test de B.

Avant toute reparation des liens Git, comparer les bytes bruts restaures a M0 :

| Domaine | Controle exhaustif attendu |
|---|---|
| Chemins | Egalite des ensembles, y compris caches utiles, ignores, vides et sources imbriquees; zero omission/extra inattendu |
| Fichiers et ADS | SHA-256 de chaque fichier et flux, tailles et types; pas seulement nombre total |
| Liens/reparse | Identite du type/tag, bytes bruts, cible et topologie; zero traversal inattendu |
| Hardlinks et metadonnees | Relations, timestamps declares, attributs, sparse/compression/EFS pertinents et ACL/owner/audit recuperables |
| Prives | Restes chiffres hors espace de restitution protege; ACL de destination restent restrictives |
| Git brut | Objets, refs, index de chaque worktree, config/exclude, HEAD/reflogs et fichiers administratifs conformes a M0 |
| Preuves | Ancres historiques, manifestes et bytes des sources scellees conserves |

Les ACL historiques peuvent etre restituees pour essai seulement dans une zone
isolee ou les identites/privileges sont maitrises. Une copie avec des ACL plus
restrictives ne prouve pas que les ACL originales sont recuperables; verifier
egalement le catalogue de securite. Si l'OS ne peut representer une metadonnee
necessaire, statut incomplet et ARRET, pas de normalisation silencieuse.

Les deux jonctions node_modules ont une cible absolue dans l'ancien arbre :
leur restitution brute conserve d'abord cette information, sans les suivre.
Apres validation brute, une relocalisation explicitement autorisee dans la seule
copie derivee doit les faire pointer vers `frontend\node_modules` de R.
Journaliser les changements de donnees de reparse et comparer ensuite les cibles
logiques, pas leurs anciens chemins absolus. Ne rien modifier dans A/B/E.
Les cinq reparse Linux demandent toujours une methode validee pour leur capture
brute puis leur interpretation/restitution; ne pas inventer leurs cibles.

## 3. Recuperation Git derivee, sans toucher les maitres

Apres validation brute, travailler sur la restitution derivee, pas sur A/B/E.
Appliquer `GIT_WORKTREES_RECOVERY.md`. Desactiver fsmonitor, hooks et operations
automatiques dans cet environnement; ne pas recopier aveuglement des commandes
de configuration privees ou des inclusions pointant sur l'original.

Verifier localement les objets avec `git fsck --full` sans reparer ni recuperer
automatiquement les objets. Les objets dangling peuvent etre legitimes et utiles :
les garder et les examiner en prive; tout objet manquant/corrompu est bloquant.
Comparer les 96 refs initiales, ou l'ensemble exactement gele M0 s'il a change
avant capture autorisee, sans publier leurs noms prives.
Examiner chaque HEAD symbolique ou detache, chaque index et les 44 bytes courants.
Un `git status` ne doit pas servir a reconstruire les modifications via checkout.

Comparer les etats XY et ensembles de chemins de M0 par worktree, en tenant
compte seulement des modifications administratives de liaison declarees.
Les ignores internes de chaque worktree sont controles physiquement, pas par
l'absence de sortie de `git status`.

## 4. Ancres B1 et separation des candidates

| Objet | SHA-256 exige |
|---|---|
| `qualification\b1-review-20261105\b1-evidence.tar` | `49418c8f928de66e82b49c5b9834ae1ce0254245a4092898ca0e5b3d28f971cd` |
| `qualification\b1-review-20261105\B1_INDEPENDENT_REVIEW.md` | `edc2309dbef2d302f45767806d5b870489584a9c02591868a23b73344e3d88e0` |

Verifier egalement tous les autres manifestes historiques du perimetre E contre
leurs ancres etablies. Les deux ancres ci-dessus ne couvrent pas seules tout E.
Ne pas recalculer puis remplacer une valeur historique pour faire passer un ecart.
Comparer les 15 fichiers de la candidate dix au manifeste source existant et
preserver son commit `8b11d4daf47bd7c3c6766b9f5231ea8a84fdbf71`.
Les six fichiers propres a cette candidate absents du worktree principal ne
doivent pas y apparaitre comme une « reparation ».

Pas de restauration applicative de SQLite/PostgreSQL dans ce lot : la fidelite
des bytes captures est un objet distinct de la restaurabilite fonctionnelle
d'une base. Cette derniere exige un protocole coherent autorise, sans lequel
la garantie correspondante reste non etablie.

## 5. Recepisse futur obligatoire

Produire en zone privee un recepisse pour A, B et E : capture_id, supports,
outil/version, commandes, codes retour, stdout/stderr, manifeste source et
manifestes restitues, SHA-256, toutes differences/limites, decryptage et reprise
des cles, chaque worktree, ancres B1 et separation de la candidate dix.
Ancrer la synthese expurgee hors des copies; ne publier aucun nom personnel,
secret, SDDL ou detail de donnees.

Resultats distincts : `PASS`, `FAIL`, `INCOMPLETE`. PASS seulement si couverture
complete du perimetre autorise et zero ecart non autorise. Toute erreur d'acces,
instabilite ou metadonnee indispensable non recuperable implique FAIL/INCOMPLETE.
Une procedure ecrite, un checksum de conteneur ou un listing lisible ne vaut
pas recepisse de restauration. Meme PASS n'autorise pas l'ouverture beta.
