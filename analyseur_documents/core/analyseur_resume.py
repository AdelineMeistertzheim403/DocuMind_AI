def generer_resume_qualite(resultat):
    lisibilite = resultat["lisibilite"]
    phrases_longues = resultat["phrases_longues"]
    termes_absents = resultat["termes_techniques_absents"]
    phrases_complexes = [
        item for item in phrases_longues
        if item.get("alertes")
    ]
    indice_style = resultat.get("indice_style_artificiel", {})

    points_forts = []
    points_a_ameliorer = []

    if lisibilite["score"] >= 80:
        points_forts.append("La lisibilité globale est bonne.")
    elif lisibilite["score"] >= 60:
        points_forts.append("La lisibilité globale reste correcte.")
    else:
        points_a_ameliorer.append("La lisibilité globale peut être améliorée.")

    if len(phrases_longues) == 0:
        points_forts.append("Aucune phrase trop longue n'a été détectée.")
    else:
        points_a_ameliorer.append(f"{len(phrases_longues)} phrase(s) dépassent la limite choisie.")

    if lisibilite["moyenne_mots_phrase"] and lisibilite["moyenne_mots_phrase"] <= 20:
        points_forts.append("La longueur moyenne des phrases est maîtrisée.")
    elif lisibilite["moyenne_mots_phrase"] > 20:
        points_a_ameliorer.append("La longueur moyenne des phrases est élevée.")

    if phrases_complexes:
        points_a_ameliorer.append(
            f"{len(phrases_complexes)} phrase(s) longues présentent aussi des signes de complexité."
        )

    if termes_absents:
        points_a_ameliorer.append(f"{len(termes_absents)} terme(s) recherché(s) sont absents.")
    elif resultat["termes_techniques"]:
        points_forts.append("Tous les termes techniques recherchés ont été trouvés.")

    if indice_style.get("niveau") in {"Moyen", "Élevé"}:
        points_a_ameliorer.append(
            f"Indice de style potentiellement artificiel : {indice_style['niveau'].lower()}."
        )

    if not points_forts:
        points_forts.append("Le document contient assez d'informations pour produire une analyse.")

    recommandations = []
    if phrases_longues:
        recommandations.append("Commencer par retravailler les phrases longues listées dans l'onglet dédié.")
    if phrases_complexes:
        recommandations.append("Prioriser les phrases avec beaucoup de virgules, parenthèses ou connecteurs.")
    if termes_absents:
        recommandations.append("Vérifier si les termes techniques absents sont réellement attendus dans ce document.")
    if indice_style.get("niveau") in {"Moyen", "Élevé"}:
        recommandations.append("Relire les passages très génériques ou trop réguliers pour les rendre plus personnels et précis.")
    if not recommandations:
        recommandations.append("Aucune action prioritaire évidente : l'analyse ne signale pas de problème majeur.")

    return {
        "niveau": lisibilite["niveau"],
        "score": lisibilite["score"],
        "points_forts": points_forts,
        "points_a_ameliorer": points_a_ameliorer,
        "recommandations": recommandations
    }
