# Codes retour et decisions separees

**Le CLI layer_contents.py retourne toujours 20 pour une tentative traitee**,
y compris quand la mesure A est complete et identique. Le rapport general
reste REVIEW_ONLY_BLOCKED et B.status=ERROR/B.returncode=20.
Il ne transforme jamais le refus historique v2 en PASS.

| A.scope_returncode | A.decision | Mesure |
|---|---|---|
| 0 | REGULAR_LAYER_CONTENTS_IDENTICAL_ONLY | Tous les chemins reguliers et SHA-256 correspondent ; portee A seulement. |
| 10 | REGULAR_LAYER_CONTENTS_DIFFERENT | Mesure exhaustive achevee ; chemins/contenus/types reguliers differents. |
| 20 | NOT_ESTABLISHED | Integrite, graphe, taille, chemin, entree speciale, scellement ou IO invalides. |
| 30 | NOT_ESTABLISHED | Controle incomplet : format ou attribut non pris en charge, limite depassee. |

`A.measurement_complete=true` uniquement pour les deux premieres lignes.
`controlled_metadata_scope_returncode` est independant (0/10) et ne change
jamais B. Absence de `.` = difference metadata/repertoire persistante,
meme si A.scope_returncode=0.

Le recepisse `complete=true` atteste seulement la fin du processus de capture,
pas la reussite de A. Verifier les empreintes, le code shell 20, le recepisse,
le rapport et A.measurement_complete avant toute interpretation.

Erreur argparse : 2 avant capture. Interruption, timeout, crash ou erreur
d'ecriture peuvent produire un autre code et aucun recepisse final complet :
ARRET, mesure incomplete, conserver le dossier. Refus de destination existante
ou non independante : code 20 sans la modifier. Ne pas reutiliser --out.

record_tests.py retourne le code unittest (0/1) ou 30 si capture incomplete.
Aucun test ignore n'est permis pour la qualification Python 3.11.
comparator.py est la copie du CLI strict v2 ; ses codes propres et son refus
de l'archive complete sont inchanges. Le point d'entree de cette nouvelle
mesure est layer_contents.py.

Tous les GO restent false et formal_b1_contents_closed=false dans tous les
rapports. C5 est une decision distincte independante et explicitement autorisee.
