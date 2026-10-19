import math
import re
from collections import Counter

from .analyseur_phrases import CONNECTEURS, nettoyer_marqueurs_pages
from .analyseur_utils import extraire_mots


FORMULES_GENERIQUES = [
    "il est important de",
    "il convient de",
    "il est essentiel de",
    "dans un monde où",
    "cela permet de",
    "cet aspect souligne",
    "il est nécessaire de",
    "de manière générale",
    "en conclusion",
    "d'une part",
    "d'autre part",
    "non seulement",
    "mais aussi"
]


def compter_connecteurs(texte):
    texte_minuscule = nettoyer_marqueurs_pages(texte).lower()
    compteur = Counter()

    for connecteur in CONNECTEURS:
        occurrences = len(re.findall(rf"\b{re.escape(connecteur)}\b", texte_minuscule))
        if occurrences:
            compteur[connecteur] = occurrences

    return dict(compteur.most_common(10))


def compter_formules_generiques(texte):
    texte_minuscule = nettoyer_marqueurs_pages(texte).lower()
    compteur = Counter()

    for formule in FORMULES_GENERIQUES:
        occurrences = len(re.findall(rf"\b{re.escape(formule)}\b", texte_minuscule))
        if occurrences:
            compteur[formule] = occurrences

    return dict(compteur.most_common())


def calculer_indice_style_artificiel(texte, longueurs_phrases, connecteurs, formules_generiques):
    mots = extraire_mots(texte)
    total_mots = len(mots)
    mots_uniques = len(set(mots))
    diversite_lexicale = (mots_uniques / total_mots) if total_mots else 0
    total_connecteurs = sum(connecteurs.values())
    total_formules = sum(formules_generiques.values())
    nombre_phrases = len(longueurs_phrases)

    moyenne = sum(longueurs_phrases) / nombre_phrases if nombre_phrases else 0
    variance = (
        sum((longueur - moyenne) ** 2 for longueur in longueurs_phrases) / nombre_phrases
        if nombre_phrases else 0
    )
    ecart_type = math.sqrt(variance)
    regularite = 0
    if moyenne:
        regularite = max(0, 1 - (ecart_type / moyenne))

    score = 0
    signaux = []
    details = {
        "Régularité des phrases": 0,
        "Connecteurs fréquents": 0,
        "Formules génériques": 0,
        "Faible diversité lexicale": 0
    }

    if nombre_phrases >= 5 and regularite >= 0.72:
        valeur = min(30, round(regularite * 30))
        score += valeur
        details["Régularité des phrases"] = valeur
        signaux.append("Longueur des phrases très régulière.")

    if total_connecteurs:
        ratio_connecteurs = total_connecteurs / max(1, nombre_phrases)
        valeur = min(25, round(ratio_connecteurs * 18))
        score += valeur
        details["Connecteurs fréquents"] = valeur
        if valeur >= 8:
            signaux.append("Connecteurs logiques fréquents.")

    if total_formules:
        valeur = min(25, total_formules * 8)
        score += valeur
        details["Formules génériques"] = valeur
        signaux.append("Formules génériques repérées.")

    if total_mots >= 120 and diversite_lexicale < 0.38:
        valeur = min(20, round((0.38 - diversite_lexicale) * 100))
        score += valeur
        details["Faible diversité lexicale"] = valeur
        signaux.append("Diversité lexicale faible.")

    score = max(0, min(100, score))
    if score >= 65:
        niveau = "Élevé"
    elif score >= 35:
        niveau = "Moyen"
    else:
        niveau = "Faible"

    if not signaux:
        signaux.append("Aucun signal stylistique fort détecté.")

    return {
        "score": score,
        "niveau": niveau,
        "signaux": signaux,
        "details": details,
        "diversite_lexicale": diversite_lexicale,
        "regularite_phrases": regularite,
        "note": "Cet indice ne prouve pas qu'un texte a été généré par IA. Il signale seulement des caractéristiques stylistiques à relire."
    }
