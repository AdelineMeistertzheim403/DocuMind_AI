from collections import Counter


def calculer_lisibilite(longueurs_phrases, nombre_phrases_longues):
    if not longueurs_phrases:
        return {
            "score": 0,
            "niveau": "Non calculable",
            "moyenne_mots_phrase": 0,
            "pourcentage_phrases_longues": 0
        }

    nombre_phrases = len(longueurs_phrases)
    moyenne = sum(longueurs_phrases) / nombre_phrases
    pourcentage_longues = (nombre_phrases_longues / nombre_phrases) * 100

    score = 100
    score -= max(0, moyenne - 18) * 2
    score -= pourcentage_longues * 1.5
    score = max(0, min(100, round(score)))

    if score >= 80:
        niveau = "Bonne"
    elif score >= 60:
        niveau = "Correcte"
    elif score >= 40:
        niveau = "À améliorer"
    else:
        niveau = "Difficile"

    return {
        "score": score,
        "niveau": niveau,
        "moyenne_mots_phrase": moyenne,
        "pourcentage_phrases_longues": pourcentage_longues
    }


def calculer_repartition_longueurs(longueurs_phrases):
    categories = {
        "Courtes (0-15)": 0,
        "Moyennes (16-30)": 0,
        "Longues (31-45)": 0,
        "Très longues (46+)": 0
    }

    for longueur in longueurs_phrases:
        if longueur <= 15:
            categories["Courtes (0-15)"] += 1
        elif longueur <= 30:
            categories["Moyennes (16-30)"] += 1
        elif longueur <= 45:
            categories["Longues (31-45)"] += 1
        else:
            categories["Très longues (46+)"] += 1

    return categories


def compter_phrases_longues_par_page(phrases_longues):
    compteur = Counter()

    for item in phrases_longues:
        page = item.get("page")
        if page:
            compteur[page] += 1

    return dict(sorted(compteur.items()))


def compter_alertes_complexite(phrases_longues):
    compteur = Counter()

    for item in phrases_longues:
        for alerte in item.get("alertes", []):
            compteur[alerte] += 1

    return dict(compteur.most_common())
