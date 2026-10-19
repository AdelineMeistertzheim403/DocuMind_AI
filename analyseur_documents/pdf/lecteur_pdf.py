import fitz

from .pdf_extraction import (
    est_titre_visuel,
    extraire_lignes_pdf,
    taille_police_normale,
)
from .pdf_nettoyage import detecter_lignes_repetees, raison_ligne_ignoree
from .pdf_pages import (
    detecter_numeros_pages_affiches,
    formater_ligne_avec_pages,
    page_affichee,
)


def _details_ligne_ignoree(ligne, raison, numeros_pages_affiches):
    return {
        "page": page_affichee(ligne, numeros_pages_affiches),
        "page_pdf": ligne["page"],
        "texte": ligne["texte"],
        "raison": raison
    }


def _details_nettoyage(
    lignes_ignorees,
    marge_haut_ratio,
    marge_bas_ratio,
    seuil_repetition
):
    return {
        "lignes_ignorees": lignes_ignorees,
        "nombre_lignes_ignorees": len(lignes_ignorees),
        "marge_haut_ratio": marge_haut_ratio,
        "marge_bas_ratio": marge_bas_ratio,
        "seuil_repetition": seuil_repetition
    }


def lire_pdf(
    chemin_fichier,
    ignorer_titres=True,
    ignorer_entetes_pieds=True,
    marge_haut_ratio=0.08,
    marge_bas_ratio=0.08,
    seuil_repetition=0.4,
    retourner_details=False
):
    document = fitz.open(chemin_fichier)

    try:
        lignes = extraire_lignes_pdf(document)
        taille_normale = taille_police_normale(lignes)
        numeros_pages_affiches = detecter_numeros_pages_affiches(
            lignes,
            marge_bas_ratio
        )
        lignes_repetees = (
            detecter_lignes_repetees(
                lignes,
                seuil_ratio=seuil_repetition,
                marge_haut_ratio=marge_haut_ratio,
                marge_bas_ratio=marge_bas_ratio
            )
            if ignorer_entetes_pieds
            else set()
        )
        lignes_texte = []
        lignes_ignorees = []

        for ligne in lignes:
            raison = None

            if ignorer_entetes_pieds:
                raison = raison_ligne_ignoree(
                    ligne,
                    lignes_repetees,
                    marge_haut_ratio,
                    marge_bas_ratio
                )

            if raison:
                lignes_ignorees.append(
                    _details_ligne_ignoree(ligne, raison, numeros_pages_affiches)
                )
                continue

            if ignorer_titres and est_titre_visuel(ligne, taille_normale):
                continue

            lignes_texte.append(
                formater_ligne_avec_pages(ligne, numeros_pages_affiches)
            )

        texte = "\n".join(lignes_texte)

        if retourner_details:
            return {
                "texte": texte,
                "nettoyage_pdf": _details_nettoyage(
                    lignes_ignorees,
                    marge_haut_ratio,
                    marge_bas_ratio,
                    seuil_repetition
                )
            }

        return texte
    finally:
        document.close()
