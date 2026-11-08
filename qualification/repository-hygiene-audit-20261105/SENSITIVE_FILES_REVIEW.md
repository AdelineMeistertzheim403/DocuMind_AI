# Revue des risques de fichiers sensibles

Metadonnees uniquement pour les familles privees. Aucun secret, document personnel,
dump, cle ou contenu d'archive n'a ete copie dans les rapports.
Les niveaux ci-dessous qualifient un **risque de conservation/publication**, pas
une vulnerabilite applicative exploitable demontree. La confiance porte sur
l'observation de metadonnees, pas sur l'existence d'un secret dans le fichier.

| # | Severity | File | Lines | Vulnerability | Confidence |
|---|----------|------|-------|---------------|------------|
| 1 | 🟡 MEDIUM | Historique Git, identifiant expurge HIST-PDF-01 | N/A, metadonnees | Ancien PDF au nom personnel encore atteignable dans des refs locales | 10/10 |
| 2 | 🟡 MEDIUM | deliveries\docnelo-signup-e2e-lab\tls\lab.key et lab.crt | N/A, metadonnees | Materiel TLS candidat non suivi, non ignore, donc exposable par ajout large | 9/10 |
| 3 | 🟡 MEDIUM | var\backups et deliveries\docnelo-lifecycle-10-api\roundtrip\before.dump | N/A, metadonnees | Sauvegardes/dumps locaux ignores, confidentialite non etablie | 10/10 |
| 4 | 🟡 MEDIUM | exports\public-beta-candidate-20261030T234303Z.tar.gz et qualification\b1-review-20261105\b1-evidence.tar | N/A, metadonnees | Archives opaques visibles, export aussi present dans l'historique | 10/10 |
| 5 | ⚪ LOW | .env, .env.example, .env.production.example | N/A, metadonnees | Fichier prive ignore et modeles suivis dont le contenu sensible n'est pas verifie | 10/10 |

## Conclusions autorisees

**Aucun secret actuellement suivi a tort n'est demontre. Ce n'est pas une
attestation d'absence de secrets.** Les modeles suivis n'ont pas fait l'objet
d'une lecture privee de leur contenu. Un scan de noms n'autorise pas a les
declarer surs ni a les publier.

HIST-PDF-01 a ete ajoute dans `ab4d3b3` puis supprime dans `396c76e`; il n'est
pas dans HEAD mais reste atteignable notamment depuis `main` et la ref distante
locale mise en cache correspondante. Le nom est volontairement masque pour
ne pas reproduire de donnees personnelles. Les contenus n'ont pas ete ouverts.
Une ref `origin` locale n'etablit pas l'etat ni l'accessibilite publique du serveur.
La suppression d'un fichier dans un commit ne retire pas ses anciennes versions.

`lab.key` fait 1 704 octets, `lab.crt` 1 159. Leur nom et taille suggerent du
materiel TLS; ni utilisabilite ni absence de reutilisation ne sont demontrees.
Un certificat n'est pas lui-meme une cle privee. Garder la paire dans une
conservation privee jusqu'a revue; aucune rotation ni revocation effectuee.

Dans `var\backups`, un `database.dump` de 118 484 octets et un
`documents.tar.gz` de 3 018 174 octets ont ete reperes; `roundtrip\before.dump`
fait 57 914 octets. Donnees reelles ou synthetiques : non etabli en contenu.
La presence de « lab », « test » ou « roundtrip » n'est pas une preuve d'innocuite.

L'export TAR.GZ visible apparait aussi dans l'historique, notamment `5927e86`.
Quatre exports horodates figurent dans les metadonnees historiques examinees.
Ne pas confondre risque d'inclusion opaque et secret effectivement trouve.
L'archive B1 doit conserver ses octets et ses ancres; l'exclusion ou l'archivage
eventuel n'autorise aucune reecriture de preuve.

## Couverture et limites

HEAD/index : 338 chemins chacun; 1 794 chemins historiques distincts examines
dans les refs/reflogs accessibles, sans inspection des blobs prives.
Les candidats de noms `Dockerfile.db`, `docs\migration-postgresql.sql` et le PDF
fixture du frontend ne sont pas des donnees privees du seul fait de leur nom.
Une migration SQL source ne doit pas etre ignoree comme un dump.

La revue de metadonnees a rencontre 115 refus de permission. Sept entrees
symlink/reparse ont ete laissees sans traversal; ce chiffre vient de la revue
de metadonnees dediee, pas d'un inventaire physique exhaustif.
Git a en outre emis deux avertissements de fonctionnalite non implementee.
Pas de contournement des permissions, pas de recuperation des objets
inatteignables, pas de controle distant, pas d'inspection interne des archives.

## Suites proposees, non appliquees

Revue privee autorisee des modeles et des inclusions d'archives; evaluation
locale de HIST-PDF-01 et de sa diffusion; archivage chiffre des donnees et cles;
exclusions precises contre les ajouts accidentels. Si un secret est confirme,
rotation/revocation puis strategie historique soumise a approbation separee.
Pas de reecriture d'historique, suppression, retrait d'index ou commit ici.
