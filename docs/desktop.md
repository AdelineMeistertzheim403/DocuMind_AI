# Analyseur de Documents

Application Python avec interface graphique pour analyser des fichiers `.txt` et `.pdf`.

Le projet calcule des statistiques textuelles, détecte les mots fréquents, repère les phrases trop longues, analyse leur complexité, identifie les termes techniques présents ou absents, génère un résumé qualité, puis permet d'exporter les résultats et les graphiques.

## Sommaire

1. Présentation
2. Fonctionnalités
3. Architecture du projet
4. Installation complète
5. Utilisation
6. Détails de l'analyse
7. Structure des résultats
8. Personnalisation
9. Limitations connues
10. Pistes d'amélioration

## 1. Présentation

Ce projet est conçu pour analyser rapidement des documents académiques ou techniques.

Il inclut :

- une interface graphique avec `customtkinter`,
- un moteur d'analyse textuelle,
- une extraction PDF basée sur PyMuPDF,
- un résumé qualité lisible,
- un export de rapport en plusieurs formats,
- un export séparé des graphiques.

## 2. Fonctionnalités

- Lecture de fichiers `.txt` et `.pdf`.
- Statistiques globales :
  - nombre de caractères,
  - nombre de mots,
  - nombre de phrases,
  - moyenne de mots par phrase.
- Score de lisibilité sur 100.
- Résumé qualité avec points forts, points à améliorer et recommandations.
- Top des mots fréquents.
- Détection des phrases longues avec seuil configurable.
- Affichage de la page PDF associée aux phrases longues.
- Détection des phrases longues à risque :
  - beaucoup de virgules,
  - parenthèses,
  - connecteurs logiques,
  - manque de ponctuation interne.
- Suggestions simples pour couper certaines phrases longues.
- Détection des termes techniques avec nombre d'occurrences.
- Affichage des termes techniques non trouvés.
- Détection des listes à puces et listes numérotées.
- Options d'analyse dans l'interface :
  - ignorer les titres,
  - ignorer les en-têtes et pieds de page,
  - ignorer figures, tableaux et annexes,
  - analyser seulement la zone Introduction → Conclusion.
- Graphiques :
  - distribution des longueurs de phrases,
  - répartition des phrases par niveau de longueur,
  - phrases longues par page,
  - score de lisibilité,
  - termes techniques trouvés et absents,
  - alertes de complexité,
  - connecteurs fréquents,
  - signaux de style potentiellement artificiel,
  - top des mots les plus fréquents.
- Indice de style potentiellement artificiel :
  - régularité des longueurs de phrases,
  - fréquence des connecteurs logiques,
  - formules génériques,
  - diversité lexicale.
- Export du rapport aux formats `.pdf`, `.html`, `.txt` et `.csv`.
- Export des graphiques aux formats `.png`, `.pdf` et `.svg`.
- Bascule thème clair/sombre.

## 3. Architecture du projet

```text
Analyseur_documents/
├── analyseur_documents/
│   ├── core/
│   │   ├── analyseur.py
│   │   ├── analyseur_lisibilite.py
│   │   ├── analyseur_phrases.py
│   │   ├── analyseur_resume.py
│   │   ├── analyseur_structure.py
│   │   ├── analyseur_style.py
│   │   ├── analyseur_termes.py
│   │   └── analyseur_utils.py
│   ├── pdf/
│   │   ├── lecteur_pdf.py
│   │   ├── pdf_extraction.py
│   │   ├── pdf_nettoyage.py
│   │   └── pdf_pages.py
│   ├── ui/
│   │   ├── interface.py
│   │   ├── interface_assets.py
│   │   ├── interface_documents.py
│   │   └── interface_helpers.py
│   └── export/
│       └── export_pdf.py
├── main.py
└── README.md
```

Rôle des fichiers :

- `main.py` : point d'entrée de l'application.
- `analyseur_documents/core/` : logique d'analyse textuelle.
- `analyseur_documents/core/analyseur.py` : point d'entrée de l'analyse globale. Il prépare le texte, appelle les modules spécialisés, puis rassemble les résultats.
- `analyseur_documents/core/analyseur_utils.py` : fonctions communes de comptage, extraction de mots, nettoyage des marqueurs de page et statistiques de base.
- `analyseur_documents/core/analyseur_phrases.py` : découpage des phrases, détection des phrases longues et complexité.
- `analyseur_documents/core/analyseur_lisibilite.py` : calcul du score de lisibilité, répartition des longueurs et alertes de complexité.
- `analyseur_documents/core/analyseur_structure.py` : analyse de la structure du document, détection et regroupement des listes à puces.
- `analyseur_documents/core/analyseur_style.py` : comptage des connecteurs, formules génériques et calcul de l'indice de style potentiellement artificiel.
- `analyseur_documents/core/analyseur_termes.py` : recherche des termes techniques présents ou absents.
- `analyseur_documents/core/analyseur_resume.py` : génération du résumé qualité, des points forts, points à améliorer et recommandations.
- `analyseur_documents/pdf/` : extraction et nettoyage des PDF.
- `analyseur_documents/pdf/lecteur_pdf.py` : point d'entrée de la lecture PDF. Il coordonne l'extraction, le nettoyage et la gestion des pages.
- `analyseur_documents/pdf/pdf_extraction.py` : extraction brute des lignes PDF, tailles de police, gras et détection des titres visuels.
- `analyseur_documents/pdf/pdf_nettoyage.py` : détection des en-têtes, pieds de page et lignes répétées à ignorer.
- `analyseur_documents/pdf/pdf_pages.py` : détection des numéros de page affichés dans le document et génération des marqueurs de page internes.
- `analyseur_documents/ui/` : interface graphique et interactions utilisateur.
- `analyseur_documents/ui/interface.py` : assemblage principal de l'interface, options d'analyse, onglets et actions utilisateur.
- `analyseur_documents/ui/interface_assets.py` : chargement du logo et configuration de l'icône de l'application.
- `analyseur_documents/ui/interface_documents.py` : sélection des fichiers, lecture des documents et dialogues d'export.
- `analyseur_documents/ui/interface_helpers.py` : formatage des résultats et génération des graphiques.
- `analyseur_documents/export/export_pdf.py` : export des rapports et des graphiques.

## 4. Installation complète

Cette section part du principe que Python n'est pas encore installé sur la machine.

### 4.1 Installer Python

Le projet nécessite Python `3.10` ou plus récent.

#### Windows

1. Aller sur le site officiel : <https://www.python.org/downloads/>
2. Télécharger la dernière version stable de Python pour Windows.
3. Lancer l'installateur.
4. Cocher impérativement :

```text
Add python.exe to PATH
```

5. Cliquer sur `Install Now`.
6. Ouvrir PowerShell ou l'invite de commandes, puis vérifier :

```bash
python --version
pip --version
```

Si la commande `python` ne fonctionne pas, essayer :

```bash
py --version
```

#### macOS

Méthode recommandée avec Homebrew :

1. Installer Homebrew si nécessaire : <https://brew.sh/>
2. Installer Python :

```bash
brew install python
```

3. Vérifier l'installation :

```bash
python3 --version
pip3 --version
```

Autre méthode possible : télécharger Python depuis <https://www.python.org/downloads/macos/>.

#### Linux

Sur Ubuntu ou Debian :

```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv python3-tk
```

Sur certaines versions d'Ubuntu, `pip` et la création d'environnements virtuels ne sont pas installés par défaut. Les paquets importants sont donc :

- `python3` : le langage Python,
- `python3-pip` : l'outil d'installation des dépendances,
- `python3-venv` : la création de l'environnement virtuel `.venv`,
- `python3-tk` : nécessaire pour l'interface graphique Tkinter.

Sur Fedora :

```bash
sudo dnf install python3 python3-pip
```

Sur Arch Linux :

```bash
sudo pacman -S python python-pip
```

Vérifier ensuite :

```bash
python3 --version
python3 -m pip --version
```

Si `python3 -m pip --version` affiche `No module named pip`, installer ou réinstaller `pip` :

```bash
sudo apt update
sudo apt install python3-pip
```

### 4.2 Récupérer le projet

Si le projet est déjà sur la machine, ouvrir un terminal dans le dossier `Analyseur_documents`.

Sinon, avec Git :

```bash
git clone <url-du-repot>
cd Analyseur_documents
```

Si le projet a été téléchargé en `.zip`, le décompresser puis ouvrir un terminal dans le dossier extrait.

### 4.3 Créer un environnement virtuel

L'environnement virtuel permet d'installer les dépendances du projet sans modifier le Python global de la machine.

#### Windows

```bash
python -m venv .venv
```

Si `python` ne fonctionne pas :

```bash
py -m venv .venv
```

#### macOS / Linux

```bash
python3 -m venv .venv
```

Vérifier ensuite que le fichier d'activation existe :

```bash
ls .venv/bin/activate
```

Si cette commande affiche `Aucun fichier ou dossier de ce nom`, l'environnement virtuel n'a pas été créé. Sur Ubuntu / Debian, installer d'abord le paquet manquant :

```bash
sudo apt update
sudo apt install python3-venv
python3 -m venv .venv
```

### 4.4 Activer l'environnement virtuel

#### Windows PowerShell

```bash
.venv\Scripts\Activate.ps1
```

Si PowerShell bloque l'activation avec une erreur de politique d'exécution :

```bash
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Puis relancer :

```bash
.venv\Scripts\Activate.ps1
```

#### Windows cmd

```bash
.venv\Scripts\activate.bat
```

#### macOS / Linux

```bash
source .venv/bin/activate
```

Une fois activé, le terminal affiche généralement `(.venv)` au début de la ligne.

Attention : il faut bien activer le fichier `activate`, pas le dossier `bin`.

Commande correcte :

```bash
source .venv/bin/activate
```

Commande incorrecte :

```bash
source .venv/bin
```

### 4.5 Installer les dépendances

Avec l'environnement virtuel activé :

#### Windows

```bash
python -m pip install --upgrade pip
python -m pip install customtkinter pymupdf matplotlib
```

#### macOS / Linux

```bash
python -m pip install --upgrade pip
python -m pip install customtkinter pymupdf matplotlib
```

Après activation de `.venv`, la commande `python` doit normalement pointer vers le Python de l'environnement virtuel. Pour vérifier :

```bash
which python
python -m pip --version
```

Le chemin doit contenir `.venv`.

### 4.6 Lancer l'application

#### Windows

```bash
python main.py
```

Ou, si nécessaire :

```bash
py main.py
```

#### macOS / Linux

```bash
python3 main.py
```

### 4.7 Résolution des problèmes fréquents

#### `python` n'est pas reconnu sur Windows

- Vérifier que Python est installé.
- Réinstaller Python en cochant `Add python.exe to PATH`.
- Essayer la commande `py` à la place de `python`.

#### `pip` n'est pas reconnu

Utiliser plutôt :

```bash
python -m pip --version
```

Ou sur macOS / Linux :

```bash
python3 -m pip --version
```

Sur Ubuntu / Debian, si le message est :

```text
/usr/bin/python3: No module named pip
```

installer `pip` :

```bash
sudo apt update
sudo apt install python3-pip
```

Puis revenir dans le dossier du projet et recréer l'environnement virtuel si nécessaire :

```bash
cd Analyseur_documents
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install customtkinter pymupdf matplotlib
```

#### `.venv/bin/activate` est introuvable sur Linux ou macOS

Ce message signifie généralement que l'environnement virtuel n'a pas encore été créé, ou que le terminal n'est pas placé dans le dossier du projet.

Vérifier le dossier courant :

```bash
pwd
ls
```

Le dossier doit contenir `main.py`, `README.md` et les autres fichiers du projet.

Créer ensuite l'environnement virtuel :

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Sur Ubuntu / Debian, si la création échoue, installer `python3-venv` :

```bash
sudo apt update
sudo apt install python3-venv
python3 -m venv .venv
source .venv/bin/activate
```

#### `python3 -m install ...` affiche `No module named install`

La commande est incomplète : il manque `pip`.

Commande incorrecte :

```bash
python3 -m install customtkinter pymupdf matplotlib
```

Commande correcte, une fois `.venv` activé :

```bash
python -m pip install customtkinter pymupdf matplotlib
```

#### Erreur avec `customtkinter`, `fitz` ou `matplotlib`

Réinstaller les dépendances dans l'environnement virtuel :

```bash
python -m pip install customtkinter pymupdf matplotlib
```

Sur macOS / Linux :

```bash
python3 -m pip install customtkinter pymupdf matplotlib
```

#### L'interface graphique ne s'ouvre pas sous Linux

Installer les composants Tkinter du système.

Ubuntu / Debian :

```bash
sudo apt update
sudo apt install python3-tk
```

Si l'erreur indique exactement :

```text
ModuleNotFoundError: No module named 'tkinter'
```

cela signifie que Python fonctionne, que les dépendances du projet peuvent être installées, mais que le module graphique système `tkinter` manque.

Sur Ubuntu, faire :

```bash
sudo apt update
sudo apt install python3-tk
```

Puis vérifier :

```bash
python3 -c "import tkinter; print('Tkinter OK')"
```

Si la machine utilise Python 3.12 et que l'erreur continue, installer le paquet spécifique :

```bash
sudo apt install python3.12-tk
```

Puis relancer depuis le dossier du projet :

```bash
source .venv/bin/activate
python main.py
```

Après activation de `.venv`, utiliser plutôt `python main.py` que `python3 main.py`, pour être sûr d'utiliser l'environnement virtuel actif.

Fedora :

```bash
sudo dnf install python3-tkinter
```

## 5. Utilisation

Lancer l'application :

```bash
python main.py
```

Sur macOS / Linux, utiliser plutôt :

```bash
python3 main.py
```

Étapes dans l'interface :

1. Ouvrir l'onglet principal `Configuration`.
2. Cliquer sur `Choisir un fichier`.
3. Sélectionner un document `.txt` ou `.pdf`.
4. Définir la limite `Phrase trop longue à partir de`.
5. Ajuster les options d'analyse si besoin.
6. Cliquer sur `Analyser`.
7. Consulter l'onglet principal `Rapport d'analyse`, qui contient :
   - `Statistiques`
   - `Résumé qualité`
   - `Mots fréquents`
   - `Phrases longues`
   - `Termes techniques`
   - `Structure`
   - `Graphiques`
8. Revenir dans `Configuration` pour cliquer sur `Exporter rapport` ou `Exporter graphiques`.

## 6. Détails de l'analyse

### 6.1 Extraction PDF

Le module `analyseur_documents/pdf/lecteur_pdf.py` coordonne la lecture des PDF. L'extraction brute est réalisée dans `analyseur_documents/pdf/pdf_extraction.py` avec :

```python
page.get_text("dict")
```

Cela permet de récupérer le texte, la taille de police, la police utilisée, le gras et le numéro de page PDF réel. Le module `analyseur_documents/pdf/pdf_pages.py` détecte ensuite le numéro de page affiché dans le document quand il existe.

### 6.2 Découpage des phrases

Le module `analyseur_documents/core/analyseur_phrases.py` prépare le texte avant segmentation :

- normalisation des retours à la ligne,
- recollement des mots coupés par césure,
- filtrage des titres probables,
- filtrage des blocs non narratifs,
- segmentation avec la ponctuation finale : `.`, `!`, `?`.

### 6.3 Phrases longues

Une phrase est signalée si son nombre de mots est strictement supérieur au seuil choisi.

Chaque phrase longue peut contenir :

- le nombre de mots,
- la page PDF si disponible,
- les alertes de complexité,
- les connecteurs repérés,
- une suggestion de découpage.

### 6.4 Termes techniques

Les termes saisis dans l'interface sont recherchés dans le document.

Le résultat distingue :

- les termes trouvés avec leur nombre d'occurrences,
- les termes non trouvés.

### 6.5 Résumé qualité

Le résumé qualité combine :

- score de lisibilité,
- nombre de phrases longues,
- proportion de phrases longues,
- complexité des phrases longues,
- termes techniques absents.

### 6.6 Exports

Le rapport peut être exporté en :

- `.pdf`,
- `.html`,
- `.txt`,
- `.csv`.

Les graphiques peuvent être exportés en :

- `.png`,
- `.pdf`,
- `.svg`.

### 6.7 Structure du document

L'onglet `Structure` affiche des informations sur l'organisation du texte :

- nombre de lignes textuelles détectées,
- nombre de listes à puces détectées,
- nombre d'éléments présents dans les listes à puces,
- détail des listes trouvées avec leurs éléments,
- numéro de page affiché dans le document quand il est disponible,
- lignes PDF ignorées pendant le nettoyage des en-têtes et pieds de page.

Les listes sont détectées grâce au début des lignes. Exemples reconnus :

```text
• Développement de l'interface
- Création des routes API
* Tests fonctionnels
1. Analyse du besoin
2) Développement
a. Configuration
a) Configuration
```

Pour les PDF, la détection repose sur le texte extrait ligne par ligne avec PyMuPDF. Certains PDF peuvent perdre les symboles visuels de liste pendant l'extraction ; dans ce cas, la liste peut ne pas être détectée même si elle est visible dans le document.

Quand plusieurs éléments de liste se suivent, l'application les regroupe dans une seule liste. Par exemple, six lignes commençant par `•` seront affichées comme `1` liste contenant `6` éléments, et non comme six listes séparées.

Pour les numéros de page, l'application essaie d'utiliser le numéro imprimé en pied de page. Elle conserve aussi en interne le numéro réel de la page PDF afin que les filtres, comme `Analyser Introduction → Conclusion`, continuent de fonctionner correctement.

### 6.8 Nettoyage des en-têtes et pieds de page

L'option `Ignorer en-têtes et pieds de page` permet de retirer du texte qui revient souvent dans les marges du PDF.

Le nettoyage combine deux méthodes :

- suppression des lignes situées dans la zone haute ou basse de la page ;
- suppression des lignes répétées sur plusieurs pages quand elles se trouvent dans ces zones.

Exemples de lignes souvent supprimées :

```text
Mémoire de stage - Nom Prénom
Université / année scolaire
Page 12
12
```

Par défaut, l'application considère :

- les 8 % supérieurs de la page comme zone d'en-tête ;
- les 8 % inférieurs de la page comme zone de pied de page ;
- une ligne comme répétée si elle apparaît sur au moins 40 % des pages.

Les lignes ignorées sont visibles dans l'onglet `Structure`, section `Nettoyage PDF`, afin de vérifier que le programme n'a pas retiré du contenu utile.

### 6.9 Indice de style potentiellement artificiel

L'application calcule un indice de style potentiellement artificiel.

Cet indice ne prouve pas qu'un texte a été généré par IA. Il sert uniquement à signaler des caractéristiques stylistiques qui peuvent mériter une relecture humaine.

Le score est compris entre `0` et `100`.

Important :

- un score bas signifie que le texte présente peu de signaux de style artificiel ;
- un score élevé signifie que le texte présente davantage de signaux de style artificiel ;
- ce n'est pas un score de qualité ;
- ce n'est pas une preuve qu'une IA a rédigé le document.

Interprétation utilisée par l'application :

```text
0 à 34   : Faible
35 à 64  : Moyen
65 à 100 : Élevé
```

Exemples d'interprétation :

- `Faible` : le texte ne présente pas beaucoup de régularités ou de formules génériques repérées.
- `Moyen` : certains passages peuvent sembler très standardisés ou répétitifs.
- `Élevé` : plusieurs signaux sont présents en même temps ; une relecture attentive est recommandée.

Les signaux utilisés sont :

- phrases de longueur très régulière : les phrases ont souvent une taille similaire ;
- connecteurs logiques fréquents : par exemple `cependant`, `de plus`, `en effet`, `ainsi` ;
- formules génériques répétées : par exemple `il est important de`, `cela permet de`, `il convient de` ;
- diversité lexicale faible : le texte utilise proportionnellement peu de mots différents.

Le score augmente quand plusieurs de ces signaux apparaissent ensemble.

Par exemple, un texte peut obtenir un score élevé s'il contient :

- beaucoup de phrases de longueur proche,
- beaucoup de connecteurs logiques,
- plusieurs formules très génériques,
- un vocabulaire assez répétitif.

À l'inverse, un score bas indique seulement que ces signaux précis n'ont pas été fortement détectés. Cela ne garantit pas que le texte n'a pas été généré par IA.

Le résultat est affiché avec :

- un niveau : `Faible`, `Moyen` ou `Élevé`,
- un score sur 100,
- une liste de signaux détectés,
- une note de prudence.

La bonne utilisation de cet indice est donc :

```text
Score faible  -> peu de signaux suspects selon les règles du programme.
Score moyen   -> quelques signaux à vérifier.
Score élevé   -> plusieurs signaux à relire attentivement.
```

### 6.10 Graphiques disponibles

L'onglet `Graphiques` regroupe plusieurs visualisations :

- histogramme des longueurs de phrases,
- répartition des phrases courtes, moyennes, longues et très longues,
- phrases longues par page pour les PDF,
- barre de score de lisibilité,
- occurrences des termes techniques,
- comparaison termes trouvés / non trouvés,
- alertes de complexité,
- connecteurs logiques fréquents,
- signaux de style potentiellement artificiel.

Les graphiques sont affichés un par un dans l'interface. Utiliser les boutons `Précédent` et `Suivant` pour naviguer entre les visualisations.

## 7. Structure des résultats

La fonction `analyser_texte(...)` retourne un dictionnaire de ce type :

```python
{
    "nombre_caracteres": int,
    "nombre_mots": int,
    "nombre_phrases": int,
    "structure_document": dict,
    "mots_frequents": list[tuple[str, int]],
    "phrases_longues": list[dict],
    "longueurs_phrases": list[int],
    "repartition_longueurs": dict,
    "phrases_longues_par_page": dict,
    "alertes_complexite": dict,
    "connecteurs_frequents": dict,
    "formules_generiques": dict,
    "indice_style_artificiel": dict,
    "lisibilite": dict,
    "termes_techniques": list[dict],
    "termes_techniques_absents": list[str],
    "resume_qualite": dict
}
```

Exemple d'élément dans `phrases_longues` :

```python
{
    "phrase": "...",
    "nombre_mots": 42,
    "page": 7,
    "nombre_virgules": 4,
    "nombre_parentheses": 0,
    "connecteurs": ["cependant", "de plus"],
    "alertes": ["4 virgules", "2 connecteurs logiques"],
    "suggestion": "Essaie de couper cette phrase autour de « cependant »."
}
```

Exemple d'élément dans `termes_techniques` :

```python
{
    "terme": "Docker",
    "occurrences": 3
}
```

## 8. Personnalisation

### 8.1 Ajouter des mots à ignorer

Modifier l'ensemble `MOTS_A_IGNORER` dans `analyseur.py`.

### 8.2 Définir les termes techniques

Saisir les termes dans la zone dédiée de l'interface, un terme par ligne.

### 8.3 Modifier les connecteurs de phrase complexe

Modifier la liste `CONNECTEURS` dans `analyseur_documents/core/analyseur_phrases.py`.

### 8.4 Ajuster les heuristiques PDF

Adapter les fonctions suivantes selon le type de documents analysés :

- `est_titre_visuel(...)` dans `analyseur_documents/pdf/pdf_extraction.py`,
- `raison_ligne_ignoree(...)` dans `analyseur_documents/pdf/pdf_nettoyage.py`,
- `detecter_numeros_pages_affiches(...)` dans `analyseur_documents/pdf/pdf_pages.py`,
- `est_titre_probable(...)` dans `analyseur_documents/core/analyseur_phrases.py`,
- `filtrer_blocs_non_narratifs(...)` dans `analyseur_documents/core/analyseur_phrases.py`.

## 9. Limitations connues

- Certains PDF très bruités peuvent encore perturber l'extraction.
- Les tableaux complexes, les colonnes multiples ou les PDF OCRisés peuvent produire des résultats imparfaits.
- Les suggestions de reformulation sont heuristiques.
- La détection des termes techniques se base sur une recherche textuelle, pas sur une analyse sémantique.
- Le projet ne contient pas encore de tests automatisés.

## 10. Pistes d'amélioration

- Ajouter des tests unitaires avec `pytest`.
- Exporter aussi en `.json`.
- Ajouter un mode CLI pour analyser plusieurs fichiers en lot.
- Sauvegarder les préférences utilisateur dans un fichier JSON.
- Comparer deux versions d'un même document.
- Ajouter une détection des répétitions de mots ou d'expressions.
