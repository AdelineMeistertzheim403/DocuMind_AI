import re

from .analyseur_utils import extraire_page_ligne


SYMBOLES_PUCES = (
    "\u2022\u25cf\u25cb\u25e6\u25aa\u25ab\u25a0\u25a1"
    "\u2013\u2014\u2713\u2714\u2794\u27a2\u203a\u2043"
    "\u2219\u00b7\uf0b7\uf0a7\uf0d8"
)
MOTIF_LISTE_PUCE = re.compile(
    rf"^\s*(?:[{re.escape(SYMBOLES_PUCES)}]|[-*+?]|"
    r"(?:\d+(?:\.\d+)*|[a-zA-Z]|[ivxlcdmIVXLCDM]+)[.)])\s+\S"
)
MOTIF_PUCE_SEULE = re.compile(
    rf"^\s*(?:[{re.escape(SYMBOLES_PUCES)}]|[-*+?])\s*$"
)


def est_ligne_liste_puce(texte):
    return MOTIF_LISTE_PUCE.match(texte) is not None


def est_ligne_puce_seule(texte):
    return MOTIF_PUCE_SEULE.match(texte) is not None


def est_titre_section_structure(texte):
    titre = re.sub(r"^\d+(?:\.\d+)*\.?\s+", "", texte).strip(" \t:-").lower()
    titres_connus = {
        "introduction",
        "introduction generale",
        "conclusion",
        "conclusion generale",
        "bibliographie",
        "webographie",
        "references",
        "annexe",
        "annexes",
        "sommaire",
        "table des matieres",
        "table des illustrations",
        "resume",
        "abstract",
        "remerciements",
        "glossaire"
    }
    return titre in titres_connus


def analyser_structure_document(texte):
    lignes_textuelles = []
    listes_puces = []
    liste_courante = None
    puce_en_attente = None

    def terminer_liste():
        nonlocal liste_courante
        if liste_courante:
            listes_puces.append(liste_courante)
            liste_courante = None

    def ajouter_element_liste(page, texte_element):
        nonlocal liste_courante
        if liste_courante is None:
            liste_courante = {
                "page": page,
                "elements": []
            }

        liste_courante["elements"].append({
            "page": page,
            "texte": texte_element
        })

    for ligne in texte.splitlines():
        page, contenu = extraire_page_ligne(ligne.strip())
        contenu = contenu.strip()

        if not contenu:
            terminer_liste()
            continue

        lignes_textuelles.append({
            "page": page,
            "texte": contenu
        })

        if est_ligne_puce_seule(contenu):
            puce_en_attente = {"page": page, "symbole": contenu}
            continue

        if est_titre_section_structure(contenu):
            terminer_liste()
            puce_en_attente = None
            continue

        if puce_en_attente:
            ajouter_element_liste(
                puce_en_attente["page"] or page,
                f"{puce_en_attente['symbole']} {contenu}"
            )
            puce_en_attente = None
            continue

        if est_ligne_liste_puce(contenu):
            ajouter_element_liste(page, contenu)
            continue

        terminer_liste()

    terminer_liste()
    nombre_elements = sum(len(liste["elements"]) for liste in listes_puces)

    return {
        "nombre_lignes_textuelles": len(lignes_textuelles),
        "nombre_listes_puces": len(listes_puces),
        "nombre_elements_listes_puces": nombre_elements,
        "listes_puces": listes_puces
    }
