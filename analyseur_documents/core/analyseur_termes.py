import re

from .analyseur_phrases import nettoyer_marqueurs_pages


TERMES_TECHNIQUES = [
    "API",
    "React",
    "React Native",
    "Docker",
    "base de donnÃ©es",
    "SQL",
    "NoSQL",
    "Spring Boot",
    "Laravel",
    "Dolibarr",
    "interface utilisateur",
    "authentification",
    "serveur",
    "endpoint",
    "JSON"
]


def detecter_termes_techniques(texte, termes_techniques=None):
    if termes_techniques is None:
        termes_techniques = []

    texte = nettoyer_marqueurs_pages(texte)
    termes_trouves = []
    termes_absents = []

    for terme in termes_techniques:
        terme_nettoye = terme.strip()

        if not terme_nettoye:
            continue

        motif = rf"(?<!\w){re.escape(terme_nettoye)}(?!\w)"
        occurrences = len(re.findall(motif, texte, flags=re.IGNORECASE))

        if occurrences > 0:
            termes_trouves.append({
                "terme": terme_nettoye,
                "occurrences": occurrences
            })
        else:
            termes_absents.append(terme_nettoye)

    return termes_trouves, termes_absents
