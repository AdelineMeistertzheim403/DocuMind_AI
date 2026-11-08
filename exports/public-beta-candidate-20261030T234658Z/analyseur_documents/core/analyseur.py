from .analyseur_lisibilite import (
    calculer_lisibilite,
    calculer_repartition_longueurs,
    compter_alertes_complexite,
    compter_phrases_longues_par_page,
)
from .analyseur_phrases import (
    compter_phrases,
    detecter_phrases_longues,
    extraire_longueurs_phrases,
    preparer_texte_pour_phrases,
)
from .analyseur_resume import generer_resume_qualite
from .analyseur_structure import analyser_structure_document
from .analyseur_style import (
    calculer_indice_style_artificiel,
    compter_connecteurs,
    compter_formules_generiques,
)
from .analyseur_termes import TERMES_TECHNIQUES, detecter_termes_techniques
from .analyseur_utils import (
    compter_caracteres,
    compter_mots,
    extraire_mots,
    extraire_page_ligne,
    mots_les_plus_frequents,
)


def analyser_texte(
    texte,
    limite_phrase_longue=35,
    termes_techniques=None,
    mode_memoire=True,
    filtrer_blocs_non_narratifs_actif=True,
    ignorer_titres=True
):
    texte_analyse = preparer_texte_pour_phrases(
        texte,
        mode_memoire=mode_memoire,
        filtrer_blocs=filtrer_blocs_non_narratifs_actif
    )
    nombre_phrases = compter_phrases(
        texte_analyse,
        mode_memoire=False,
        filtrer_blocs=False,
        ignorer_titres=ignorer_titres
    )
    phrases_longues = detecter_phrases_longues(
        texte_analyse,
        limite_mots=limite_phrase_longue,
        mode_memoire=False,
        filtrer_blocs=False,
        ignorer_titres=ignorer_titres
    )
    longueurs_phrases = extraire_longueurs_phrases(
        texte_analyse,
        mode_memoire=False,
        filtrer_blocs=False,
        ignorer_titres=ignorer_titres
    )
    termes_trouves, termes_absents = detecter_termes_techniques(
        texte_analyse,
        termes_techniques=termes_techniques
    )
    connecteurs_frequents = compter_connecteurs(texte_analyse)
    formules_generiques = compter_formules_generiques(texte_analyse)
    indice_style = calculer_indice_style_artificiel(
        texte_analyse,
        longueurs_phrases,
        connecteurs_frequents,
        formules_generiques
    )

    resultat = {
        "nombre_caracteres": compter_caracteres(texte_analyse),
        "nombre_mots": compter_mots(texte_analyse),
        "nombre_phrases": nombre_phrases,
        "structure_document": analyser_structure_document(texte_analyse),
        "mots_frequents": mots_les_plus_frequents(texte_analyse),
        "phrases_longues": phrases_longues,
        "longueurs_phrases": longueurs_phrases,
        "repartition_longueurs": calculer_repartition_longueurs(longueurs_phrases),
        "phrases_longues_par_page": compter_phrases_longues_par_page(phrases_longues),
        "alertes_complexite": compter_alertes_complexite(phrases_longues),
        "connecteurs_frequents": connecteurs_frequents,
        "formules_generiques": formules_generiques,
        "indice_style_artificiel": indice_style,
        "lisibilite": calculer_lisibilite(longueurs_phrases, len(phrases_longues)),
        "termes_techniques": termes_trouves,
        "termes_techniques_absents": termes_absents
    }
    resultat["resume_qualite"] = generer_resume_qualite(resultat)

    return resultat


__all__ = [
    "TERMES_TECHNIQUES",
    "analyser_texte",
    "compter_caracteres",
    "compter_mots",
    "extraire_mots",
    "extraire_page_ligne",
    "mots_les_plus_frequents",
]
