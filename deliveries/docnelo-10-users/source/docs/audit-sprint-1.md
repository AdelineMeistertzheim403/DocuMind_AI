# Audit du dépôt — Sprint 1

Inspection du 19 octobre 2026. Le dossier fourni n'est pas un dépôt Git initialisé.
Aucun AGENTS.md, manifeste de dépendances, backend, migration ou test n'était présent.

| Module | Rôle et dépendances | Décision |
| --- | --- | --- |
| `main.py`, `ui/interface.py` | Démarrage et orchestration Tkinter / CustomTkinter | Conservés, aucun import par le backend |
| `core/analyseur.py` et huit modules associés | Fonctions pures : statistiques, structure, phrases, lisibilité, style, termes, résumé qualité ; bibliothèque standard | Réutilisés directement sans modification |
| `pdf/lecteur_pdf.py`, `pdf_extraction.py`, `pdf_nettoyage.py`, `pdf_pages.py` | PyMuPDF, extraction visuelle, filtres, pages affichées ; pas de GUI, pas de limites | Conservés pour le bureau ; ingestion web bornée avec PyMuPDF, texte brut intégral par page physique |
| `ui/interface_documents.py` | Lecture TXT UTF-8 mêlée aux boîtes de dialogue Tkinter et exports | Le backend lit le TXT indépendamment pour éviter la dépendance GUI |
| `export/export_pdf.py` | TXT/CSV/HTML par bibliothèque standard ; PDF via PyMuPDF ; export de figures fourni par l'interface | Conservé pour le bureau ; JSON pour l'API du sprint |
| `ui/interface_assets.py`, `interface_helpers.py` | Pillow, CustomTkinter et matplotlib pour assets/graphiques | Dépendances optionnelles `desktop` |

Le résumé existant est un diagnostic de qualité déterministe, pas un résumé sémantique du contenu.
L'indice de style est une heuristique et ne constitue pas une détection fiable d'IA.
Le terme par défaut `base de donnÃ©es` présente déjà un problème d'encodage dans le moteur ;
il est conservé pour éviter un changement silencieux du comportement du bureau. Les termes
personnalisés permettent d'utiliser la bonne orthographe dans l'API.

## Architecture retenue

`backend/api.py` → schémas / services → moteur original et SQLAlchemy 2.
Les tables enfants héritent du propriétaire via le document : aucun endpoint enfant ne contourne ce contrôle.
`owner_id` est un UUID non nul et indexé. Un futur modèle utilisateurs pourra devenir sa cible de clé étrangère.
Les clés API sont un mécanisme MVP révocable par configuration, sans inscription ni session utilisateur.
Les analyses successives sont historisées avec paramètres et version du moteur.
Les chunks n'ont ni embeddings ni dépendance IA : page, index et offsets locaux à la page suffisent pour la préparation RAG.
Le découpage actuel est fixe par caractères, sans prétention sémantique.

## Écarts volontaires du web

L'extraction web conserve le texte des en-têtes, pieds et titres pour le futur RAG.
Elle ne fait pas appel au nettoyage visuel du lecteur de bureau qui accumule toutes les lignes et leurs métadonnées.
Le moteur conserve ses filtres d'analyse configurables. Les pages de l'API sont les pages physiques (base 1),
et non les numéros imprimés détectés par l'application de bureau.
Le TXT est une page logique unique. OCR et PDF chiffrés ne sont pas pris en charge.
L'ajout d'un fournisseur IA pourra se faire via un service dédié ; aucun SDK ou appel OpenAI n'est ajouté ici.
