def est_dans_zone_entete_pied(ligne, marge_haut_ratio, marge_bas_ratio):
    hauteur_page = ligne["hauteur_page"]
    y_haut = ligne["bbox"][1]
    y_bas = ligne["bbox"][3]
    limite_haut = hauteur_page * marge_haut_ratio
    limite_bas = hauteur_page * (1 - marge_bas_ratio)

    return y_bas < limite_haut or y_haut > limite_bas


def detecter_lignes_repetees(
    lignes,
    seuil_ratio=0.4,
    marge_haut_ratio=0.08,
    marge_bas_ratio=0.08
):
    if not lignes:
        return set()

    pages = {ligne["page"] for ligne in lignes}
    nombre_pages = len(pages)

    if nombre_pages < 2:
        return set()

    occurrences_par_page = {}

    for ligne in lignes:
        if not est_dans_zone_entete_pied(ligne, marge_haut_ratio, marge_bas_ratio):
            continue

        texte_normalise = ligne["texte_normalise"]
        if len(texte_normalise) <= 2:
            continue

        occurrences_par_page.setdefault(texte_normalise, set()).add(ligne["page"])

    seuil = max(2, int(nombre_pages * seuil_ratio))

    return {
        texte
        for texte, pages_ligne in occurrences_par_page.items()
        if len(pages_ligne) >= seuil
    }


def raison_ligne_ignoree(
    ligne,
    lignes_repetees,
    marge_haut_ratio,
    marge_bas_ratio
):
    hauteur_page = ligne["hauteur_page"]
    y_haut = ligne["bbox"][1]
    y_bas = ligne["bbox"][3]
    limite_haut = hauteur_page * marge_haut_ratio
    limite_bas = hauteur_page * (1 - marge_bas_ratio)

    if y_bas < limite_haut:
        return "en-tête"

    if y_haut > limite_bas:
        return "pied de page"

    if ligne["texte_normalise"] in lignes_repetees:
        return "ligne répétée"

    return None
