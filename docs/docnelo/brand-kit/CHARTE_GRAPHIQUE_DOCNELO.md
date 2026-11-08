# Charte graphique Docnelo — v1.0 (proposition)

## Positionnement
**Docnelo** : analyse et organisation intelligentes des documents.
**Docnelo Business** : déclinaison professionnelle de la même marque.

## Symbole et signature
- Documents superposés : organisation documentaire.
- Trois points connectés : analyse, liens entre informations et fonctionnalités d’intelligence artificielle.
- Logotype horizontal : usage prioritaire sur le web et dans les documents.
- Icône seule : favicon, PWA, avatar et espaces compacts.
- Version Business : même emblème, suffixe BUSINESS (ne pas créer une identité concurrente).

## Palette proposée
| Rôle | Couleur | HEX |
|---|---|---|
| Marine, texte | Marine profond | `#0B1D3B` |
| Primaire | Bleu électrique | `#126BEE` |
| Secondaire | Azur | `#5BAAF5` |
| Accent | Menthe | `#3AD8B4` |
| Fond clair | Blanc bleuté | `#F7FAFD` |
| Fond sombre | Nuit | `#091426` |
| Texte secondaire | Gris bleuté | `#53677E` |

Ces couleurs sont une **palette de travail inspirée de l'image** ; elles ne sont pas des valeurs CSS mesurées sur le site existant.

## Typographies
- Interface : `Inter` ou `system-ui`, poids 400 / 500 / 600 / 700.
- Documents et présentations : `Lato` ou `Arial` si Inter n’est pas installé.
- Le lettrage de l’image reste la référence visuelle : ne pas substituer automatiquement la police de l’UI à la signature.

## Espacement et lisibilité
- Zone de protection : au moins la moitié de la hauteur de l’emblème de chaque côté du logotype.
- Logo horizontal : largeur conseillée de 160 px minimum sur le web ; icône seule sous cette largeur.
- Ne pas déformer, tourner, recolorer arbitrairement ou placer le logo sur un fond photographique chargé.
- Fond sombre : utiliser le fichier dédié avec lettrage clair.
- Utiliser les bleus et le vert comme accents ; garder les surfaces et les textes lisibles.
- Tester l’accessibilité des contrastes pour chaque combinaison texte/fond.

## Déclinaisons livrées
- `docnelo-horizontal-transparent.png` : original détouré.
- `docnelo-horizontal-dark-transparent.png` : adaptation pour fond sombre.
- `docnelo-icon-transparent.png` et tailles 32, 64, 192, 512.
- `favicon.ico`.
- `docnelo-business-transparent.png` / `docnelo-business-dark-transparent.png` : proposition de signature Business.
- `apercu-declinaisons.png` : planche de présentation.
- `docnelo-tokens.css` : variables CSS de départ.

## Important — fichiers de production
Le logo choisi est une image raster. Les fichiers transparents sont dérivés automatiquement de cette image, et non une vectorisation certifiée. Sur fond très contrasté, inspecter les contours et ajuster si nécessaire. Pour produire un SVG de qualité master, reconstruire manuellement le dessin dans Figma ou Inkscape à partir de ce visuel et vérifier le rendu aux petites tailles. Une recherche d’antériorités sur le **dessin du logo** peut aussi être utile, distincte de celle sur le nom.
