# Docnelo V5.1 - P4 B1 : revue de provenance du blob OCI auxiliaire

**Date :** 5 novembre 2026. **Nature :** analyse documentaire et statique locale.

**Conclusion de cause racine : `ROOT_CAUSE_NOT_ESTABLISHED`.**

**Decision generale : `REVIEW_ONLY_BLOCKED`.**
`formal_b1_contents_closed=false`. Tous les GO restent `false`.
Le refus strict historique `ERROR / 20` est conserve, sans exception nouvelle.

## 1. Conclusion et perimetre exact

Les elements retrouves confirment l'existence d'un objet hors du graphe
principal et la distinction entre contenus reguliers identiques et archive
complete toujours bloquee. Ils **n'identifient pas le producteur, l'etape
ni la raison d'inclusion** du blob auxiliaire.

Les scripts historiques effectifs de creation, d'assemblage du rootfs,
de sauvegarde et d'export P3 n'ont pas ete retrouves dans les sources
accessibles examinees. Ils n'ont donc pas pu etre audites comme s'ils
etaient disponibles. Des outils de revue, des recettes sans rattachement P3
et des generateurs de fixtures ont ete lus et distingues de ces producteurs.

Une metadata de compatibilite Docker, un objet intermediaire ou un objet
residuel inclus a l'export restent des hypotheses non departagees. Ni la
ressemblance JSON, ni l'auto-coherence SHA-256, ni les tailles voisines de
la configuration ne suffisent a en privilegier une.

Cette revue n'execute aucun programme de livraison, aucun binaire du rootfs,
aucune commande Docker et aucun acces reseau. Seul ce nouveau document est
cree. Les preuves, archives, comparateurs et livraisons restent inchanges.

## 2. Sources et niveau de preuve

### 2.1 Sources documentaires et code, avec lignes du depot

Les references S01-S12 servent aussi de citations aux hypotheses ci-dessous.
Les chemins designent les fichiers locaux observes, pas une recette supposee.

| Ref. | Fichier et lignes | Ce que cette source etablit / n'etablit pas |
|---|---|---|
| S01 | `DOCNELO_V51_P4_B1_CONSOLIDATED_REVIEW_2026-11-05.md:11`, `:44-61`, `:64-83`, `:115-127` | Synthese des observations Debian, emplacement de l'archive, graphe et decisions A/B/C. Le document declare sa nature documentaire, pas une attribution de provenance. |
| S02 | `qualification\b1-review-20261105\B1_INDEPENDENT_REVIEW.md:15-23`, `:29-38`, `:51-57`, `:76-85` | Ancre de l'archive de transmission, quatre jeux de preuves, absence de l'archive P3 et des inventaires dans ce paquet ; questions de provenance encore a instruire. |
| S03 | `qualification\p4_base_runtime_v3\P4_BASE_RUNTIME_REPORT.md:20-32`, `:101-107` | Les octets historiques P3 n'etaient pas fournis a cette preparation ; FROM scratch/COPY rootfs/USER sont des constats operateur rapportes, pas le Dockerfile original. |
| S04 | `qualification\p4_b1_consolidation_20261103\P4_B1_QUALIFICATION_REPORT.md:18-34`, `:36-43`, `:69-73` | Hash du Dockerfile historique rapporte, separation des identifiants, et avertissement contre une attribution de cause a COPY sans capture de la recette. |
| S05 | `deliveries\docnelo-v51-p4-b1-oci-comparator-v2\comparator.py:320-359`, `:369-439`, `:485-495` | Hachage des blobs, rattachement Docker/OCI puis refus des fichiers externes non reclames. C'est un lecteur/controleur, pas le producteur de l'archive. |
| S06 | `deliveries\docnelo-v51-p4-b1-p3-layer-contents-v1\layer_contents.py:69-102`, `:103-124`, `:143-152` | Graphe principal ancre, maintien du refus sur l'inventaire complet, mesure A sur une vue distincte et anomalie toujours non approuvee. Cela n'explique pas l'origine du blob. |
| S07 | `qualification\p4_build_materials_v2\image_catalog.py:1-5`, `:21-54` | Lecture d'une archive et de sa configuration ; provenance non approuvee. Ne cree ni ne sauvegarde une image P3. |
| S08 | `qualification\p4_base_runtime_v3\rootfs_check.py:1`, `:48-53`, `:121-131` ; `qualification\p4_base_runtime_v3\review.py:80-94` | Inventaire d'un arbre P4 synthetique ; dockerfile_issued=false et build_recipe_sha256=None dans la revue P4. Pas une recette d'assemblage P3 retrouvee. |
| S09 | `qualification\p4_base_runtime_v3\tests\test_runtime.py:130-143` ; `deliveries\docnelo-v51-p4-b1-oci-comparator-v2\test_comparator.py:122-142` ; `deliveries\docnelo-v51-p4-b1-p3-layer-contents-v1\test_layer_contents.py:20-60` | Construction de fixtures TAR/config et simulation de frontiere de verification. Le blob de test est explicitement invente a la ligne 47 du dernier fichier, pas copie du blob historique. |
| S10 | `qualification\p4_base_runtime_v3\transfer.py:1-13`, `:32-44` | Emballage ZIP de la livraison P4, non sauvegarde/export de l'image P3. Le nom de fonction pack ne prouve aucun lien avec l'archive Docker. |
| S11 | `ops\testing\combined_restore_lab.py:1-4`, `:23-35`, `:65-73` | Autre laboratoire : contexte Docker Desktop et image PostgreSQL, export nomme pg-rootfs.tar. Aucun rattachement atteste au producteur P3. Script lu, jamais execute dans cette revue. |
| S12 | `Dockerfile:1-15`, `:16-32` | Recette applicative Python 3.13 multi-etapes, non identifiee comme Dockerfile scratch/Python 3.11 P3. Sa presence ne remplace pas la recette historique manquante. |

### 2.2 Preuves brutes locales effectivement ouvertes

L'archive `qualification\b1-review-20261105\b1-evidence.tar` a ete ouverte
en lecture seule, sans extraction sur disque. Son SHA-256 a ete recalcule :

`49418c8f928de66e82b49c5b9834ae1ce0254245a4092898ca0e5b3d28f971cd`

Il correspond a l'ancre documentaire S02. Ses 33 entrees ont ete listees ;
les membres lus sont des fichiers reguliers bornes. Les quatre manifestes
internes et les hashes des fichiers qu'ils designent ont ete verifies.
Les hashes enregistres dans les quatre recepisses ont egalement ete verifies.
Cela verifie les copies contre les ancres disponibles, pas leur auteur ni
l'independance du canal de remise de ces ancres.

Les noms ci-dessous sont des **membres logiques TAR**, pas des fichiers
extraits. Prefixes :

- V2 : `p4-b1-oci-v2-6e3e9a30bf4e452780fc79f0cd6a53c7`.
- A : `p4-b1-p3-layer-v1-1f1304c0ce3246b9b64ebd851dbeb442`.

| Membre sous le prefixe | SHA-256 de son SHA256SUMS | Resultat du recepisse lu |
|---|---|---|
| V2, `unit-tests/SHA256SUMS` | `80f0435b6d5eddfd724660359c1cfd7ec0ef76aa13ea01484855c370188067ea` | returncode=0, complete=true |
| V2, `comparison/SHA256SUMS` | `da22ccae43b1eb4df9906993015fc666bb454e7bdb0cdcc41ea1ba65d780cd0c` | returncode=20, complete=true |
| A, `unit-tests/SHA256SUMS` | `d44877191c7f0d0043887f9b11a5387685a62aa305ada83dc7bf1adce54bee91` | returncode=0, complete=true |
| A, `comparison/SHA256SUMS` | `832d2272b76f38583fcf060cfb34e43e309cf677ddeadb64d1f143d1a5615ef8` | returncode=20, complete=true |

Les deux membres `comparison/report.json` ont ete lus en memoire.
Les champs `outer_entries`, `observed_sha256.archive`, `error` pour V2,
et `A_regular_layer_contents`/`B_strict_whole_archive` pour A sont les
references brutes des constats ci-apres. Un TAR binaire n'a pas de lignes
de source pertinentes : membre et champs JSON sont donnes plutot que des
numeros de lignes inventes. Les S01/S02 fournissent les references textuelles.

Le paquet contient des resultats de controles et leurs recepisses, **pas**
les octets des quatre blobs P3, les scripts producteurs, le Dockerfile
historique ou les captures de creation/export. Le JSON brut du blob de
829 octets n'a donc pas ete reparse dans cette revue. Sa qualification
comme metadata Docker est un constat operatrice, non une nouvelle
observation de ses champs.

## 3. Faits etablis et bornes de ces faits

| Objet dans les rapports verifies | SHA-256 | Taille |
|---|---|---:|
| Archive historique designee par les deux controles | `ffec209c1b5eb3a8861e60585266c18069896adf05c8fe8f98c558d682351c2d` | Non re-mesuree ici |
| Configuration principale | `bbe90dab376fcd41b3495cad1264c017323ed68ed0915c601ea5fd229cbf6abd` | 835 |
| Manifeste OCI principal | `c4c9b897d2e3dea6bbcc3da95b078ce5ffa556f5e4c52020a40da8be784ccc44` | 402 |
| Couche reguliere unique | `7b1b9ae269d164c3b88d386714f2def703acb15812a6d6f813c10064f57c766e` | 322534912 |
| Blob auxiliaire | `eec772146db049680bf51af9758854bd4c210bff907cac5d73a10deec0775653` | 829 |

Les deux inventaires externes des rapports concordent : deux repertoires
`blobs` et `blobs/sha256`, quatre blobs reguliers, `index.json`,
`manifest.json` et `oci-layout`, soit neuf entrees. Les deux rapports
identifient la meme archive et le meme blob auxiliaire.

Le rapport strict donne exactement :
`Invalid: Unclaimed outer regular entries: ['blobs/sha256/eec772146db049680bf51af9758854bd4c210bff907cac5d73a10deec0775653']`.
Le controle de binding S05 revendique les objets references, puis refuse
l'entree restante. Le code 20 n'est pas une simple absence de compte rendu.

Le rapport limite donne A.measurement_complete=true,
A.scope_returncode=0, expected_regular_paths=9771 et
REGULAR_LAYER_CONTENTS_IDENTICAL_ONLY. B reste ERROR/20,
conformity_granted=false, approved=false et used_to_identify_layer=false.
Ces conclusions ne sont pas recalculees en executant les comparateurs ici.

Le graphe ancre est index.json -> manifeste c4c9... -> configuration bbe90...
et couche 7b1b... ; manifest.json confirme configuration/couche.
Le blob eec772... n'est pas une cible de ce graphe principal controle.
Les tailles 829 et 835 excluent une identite **des octets** entre les deux
objets, mais ne permettent ni de comparer leurs champs ni d'exclure une
equivalence partielle de leurs JSON. Les six octets d'ecart n'expliquent rien.

L'auto-coherence contenu/nom prouve une identite relative a l'empreinte,
pas l'auteur, la date de generation, l'etape d'insertion ou le role de
l'objet. Une archive ancree fige aussi une anomalie deja presente.
Enfin, ERROR/20 est le resultat de la politique stricte de S05 :
ce n'est pas, a lui seul, une preuve de malveillance ni une demonstration
d'invalidite universelle au regard de toutes les variantes de format OCI.

## 4. Recherche des producteurs et exclusions motivees

Les recherches ont porte sur les noms et identifiants P3, le hash eec772...,
les operations de sauvegarde/export, FROM scratch/COPY rootfs et les
constructions TAR dans les textes et scripts locaux. Les Dockerfile et
les familles candidates/qualification/ops/tools/deliveries/exports ont ete
examines par recherche puis lecture ciblee. Une recherche elargie a inclus
les textes ignores/caches, hors .git, environnements .venv, node_modules
et __pycache__.

Deux recherches Git locales de variations de contenu (-S) sur toutes les
references locales, limitees aux scripts Python/shell/PowerShell et
Dockerfile, n'ont trouve aucun commit pour les chaines exactes
`p3-image-export.tar` et `docnelo-p3-python311`. Aucune recuperation distante
n'a eu lieu. Cela ne couvre pas un script sans ces chaines, un fichier
non versionne, des references Git absentes ou une commande saisie sur la VM.

La recherche elargie a retourne des acces refuses, notamment .pytest_cache
et plusieurs sous-repertoires var de tests. Aucune permission n'a ete
modifiee ; ces arbres n'ont pas ete contournes. L'ancien dossier historique
inaccessible mentionne par l'operatrice n'a pas ete explore sur la VM.
**La recherche n'est pas exhaustive.**

Le seul hash documentaire de recette P3 retrouve est celui du Dockerfile
historique, `605418eb09c102b5757dab88ad3ecbd1a70eb750bfea22615784ede4d9259e47`
(S04). Il ne donne pas les octets du fichier ni une capture de son execution.
Le contexte scratch/Python 3.11 reste rapporte par S03. On ne peut attribuer
au Dockerfile une insertion de blob situe hors de la couche.

Les S07-S10 sont des lecteurs, inventaires, fixtures ou emballages de
livraison. En particulier, le blob JSON de test de S09 est synthetique :
ce n'est ni une copie ni une preuve de fabrication du blob eec772....
Le script d'export S11 vise un autre laboratoire et PostgreSQL, et S12
une recette applicative Python 3.13. Aucun lien chronologique ou
cryptographique avec P3 n'a ete retrouve pour ces deux sources.

## 5. Hypotheses restantes, sans classement de vraisemblance

| Hypothese | Appui disponible | Ce qui manque pour l'etayer ou la refuter | Etat |
|---|---|---|---|
| H1 - Metadata Docker heritee/de compatibilite produite a la sauvegarde | Nature JSON Docker rapportee ; coexistence de manifest.json et d'un graphe OCI dans l'inventaire verifie (S01, S05). | JSON brut auxiliaire et config ; code/documentation de l'exporteur exact et traces historiques montrant cette transformation. La double representation n'attribue pas l'objet a un producteur. | Non etablie. |
| H2 - Ancienne configuration ou objet intermediaire de creation/assemblage | Objet distinct de la config principale, taille voisine. Aucun autre appui causal. | Scripts et contexte historiques, chaine de transformations, captures ancrees reliant les deux objets. Sans eux, ni parentage, ni ordre temporel ne sont connus (S03, S04, S08). | Non etablie. |
| H3 - Objet residuel du stockage de contenu copie dans l'export sans reference principale | L'absence de rattachement est prouvee dans le scope du controle ; l'objet figure dans l'archive ancree (S05/S06 et rapports verifies). | Implementation/version/backend du producteur, politique de selection des blobs et capture de la sauvegarde. Aucun parcours historique copiant tout un magasin de blobs n'a ete retrouve. | Non etablie ; seule la non-atteignabilite principale est constatee. |
| H4 - Assemblage/re-emballage manuel, melange de materiaux ou ajout avant acquisition de l'ancre | Une telle operation pourrait conserver des noms conformes aux hashes. Aucune trace positive retrouvee. | Journal de creation de l'archive, empreintes successives, acteurs et chaine de conservation. Aucune alteration malveillante n'est demontree. | Non etablie. |

Les hypotheses ne sont ni mutuellement exclusives ni des accusations.
La preuve actuelle explique **pourquoi le controle refuse**, pas
**pourquoi le producteur a inclus cet objet**. Aucun code local identifie
ne permet de departager H1-H4 ; il n'existe pas ici de justification
technique documentee suffisante de l'origine.

## 6. Risques d'une acceptation sans reference explicite

| Risque | Consequence possible / limite de l'evaluation |
|---|---|
| Confusion integrite/provenance | Un contenu peut etre parfaitement hache mais n'avoir ni role approuve ni auteur/etape identifies. Accepter le nom SHA seul ne ferme pas cette lacune. |
| Confusion A/B/C | L'identite des 9771 fichiers ne justifie ni tout le TAR externe ni les composants de base. La convertir en PASS global effacerait une reserve existante. |
| Interpretation differente par un autre lecteur | Un importeur ou consommateur futur pourrait traiter des metadata que le graphe principal n'utilise pas. Aucun comportement de ce type n'est teste ou prouve ici. |
| Donnees non attendues ou contenu non revu | Le JSON auxiliaire peut contenir des champs hors scope. Aucun secret, code executable ou contenu malveillant n'est constate ; l'absence de ces elements n'est pas non plus attestee par la seule taille/hash. |
| Tolerance generalisee ou precedente implicite | Une exception pour tous les blobs auto-coherents permettrait d'accepter d'autres objets hors graphe sans examiner leur provenance. Aucune telle exception n'est proposee. |
| Rupture de piste d'audit | Supprimer le blob, ajouter une reference ou re-sceller l'archive changerait les octets historiques et rendrait les anciens rapports inapplicables a cette nouvelle archive. |

Ce sont des risques de confiance, d'interoperabilite et de decision,
pas des vulnerabilites exploitables nouvellement demontrees. Le simple
stockage du blob dans un TAR ne prouve aucune execution.

## 7. Pieces manquantes et criteres pour le relecteur independant

Les demandes ci-dessous sont documentaires, pour une collecte distincte
autorisee en lecture seule. Elles n'autorisent ni nouvelle commande Docker,
ni build, ni nouvel export, ni correction des preuves.

1. **Octets et comparaison ciblee.** Acceder par une voie autorisee a
   l'archive historique ancree, au JSON auxiliaire exact de 829 octets et
   a la configuration principale de 835 octets. Relever leurs schemas,
   champs, valeurs et differences sans reecrire les originaux. Une
   normalisation JSON en memoire peut aider a comparer, jamais remplacer
   les octets/hash. Des champs eventuels comme history, rootfs, created,
   docker_version ou container_config seraient des indices auto-declares,
   pas des champs ici observes ni des attestations d'origine.
2. **Recettes et captures historiques.** Fournir les scripts exacts de
   preparation/assemblage, Dockerfile correspondant a S04, commandes et
   parametres effectivement utilises, hashes de leur code, codes retour,
   stdout/stderr et chronologie deja conservee. Un chemin ou une recette
   reconstruite a posteriori ne suffit pas a prouver ce qui fut execute.
3. **Producteur precis.** Identifier depuis les captures contemporaines
   les versions CLI/daemon/builder et le backend d'export/stockage reellement
   utilises. Examiner hors ligne une source ou documentation de cette
   version, ancree et fournie par une voie autorisee : fonction qui genere
   le JSON, regle d'inclusion et absence de reference eventuelle. Une version
   installee aujourd'hui, ou proposee par un protocole P4 futur, ne suffit pas.
4. **Lien causal et contradictions.** Relier la regle technique aux octets
   eec772..., a la configuration bbe90... et a l'archive ffec209c... avec
   des captures ancrees. Expliquer les champs et tailles, et rechercher les
   contradictions. Une compatibilite de schema ne constitue pas a elle
   seule la preuve de cette execution. Sans lien causal, laisser la cause
   non etablie, sans classer une hypothese comme explication dominante.
5. **Decisions distinctes et attribuees.** Documenter auteur habilite,
   pieces ouvertes, methode, objections et perimetre exact de chaque avis.
   Une origine eventuellement expliquee ne requalifie pas retroactivement
   le code strict 20. Une decision future sur le format ou la provenance
   serait un acte distinct, pas une modification de v2 ou une exception
   automatique. B1/C5/P4 restent non accordes par ce document.

En attendant ces pieces, maintenir le blob avec l'archive originale,
les inventaires, livraisons et preuves, sans suppression ni ajout de
reference. Conserver A comme resultat de contenus seulement, B comme
refus strict, et C comme qualification/provenance non accordees.

## 8. Limites et decision finale

Les hashes de l'archive de transmission et de ses preuves internes ont ete
verifies localement. Les octets de l'archive image P3 et du blob auxiliaire
n'ont pas ete remis localement dans les pieces examinees : aucun nouveau
hachage de ces objets n'est revendique. Aucune documentation externe ni
source Docker/Moby/containerd propre au producteur n'a ete consultee.
L'absence de scripts retrouves, les exclusions de recherche et les acces
refuses interdisent toute conclusion d'absence exhaustive.

Les comparateurs et leurs tests sont des preuves de methode, pas des
temoins de fabrication. Leurs fixtures ne peuvent pas servir a attribuer
une origine au blob qu'elles modelisent.

```json
{
  "root_cause": "ROOT_CAUSE_NOT_ESTABLISHED",
  "decision": "REVIEW_ONLY_BLOCKED",
  "A_regular_layer_contents": "REGULAR_LAYER_CONTENTS_IDENTICAL_ONLY",
  "B_strict_whole_archive": "ERROR",
  "B_returncode": 20,
  "C_p4_and_provenance": "NOT_GRANTED",
  "formal_b1_contents_closed": false,
  "go": {
    "build": false,
    "create": false,
    "start": false,
    "run": false,
    "pull": false,
    "import": false,
    "p4": false,
    "runtime": false,
    "production": false,
    "c5": false
  }
}
```

**Aucune cause racine suffisamment prouvee ; aucune levee du refus 20,
aucune cloture B1/C5 et aucun GO.**
