import re


def detecter_numeros_pages_affiches(lignes, marge_bas_ratio):
    numeros = {}

    for ligne in lignes:
        texte = ligne["texte"].strip()
        hauteur_page = ligne["hauteur_page"]
        y_haut = ligne["bbox"][1]
        limite_bas = hauteur_page * (1 - marge_bas_ratio)

        if y_haut <= limite_bas:
            continue

        if re.fullmatch(r"\d{1,4}", texte):
            numeros[ligne["page"]] = int(texte)

    return numeros


def page_affichee(ligne, numeros_pages_affiches):
    return numeros_pages_affiches.get(ligne["page"], ligne["page"])


def formater_ligne_avec_pages(ligne, numeros_pages_affiches):
    page = page_affichee(ligne, numeros_pages_affiches)
    return f"@@PAGE:{page}@@ @@PDFPAGE:{ligne['page']}@@ {ligne['texte']}"
