import re
from collections import Counter

from .analyseur_phrases import nettoyer_marqueurs_pages


MOTS_A_IGNORER = {
    "le", "la", "les", "un", "une", "des",
    "de", "du", "dans", "en", "et", "à",
    "au", "aux", "pour", "par", "avec",
    "ce", "cette", "ces", "sur", "que",
    "qui", "est", "sont", "être", "plus"
}


def extraire_page_ligne(ligne):
    match = re.match(r"^@@PAGE:(\d+)@@\s*(?:@@PDFPAGE:\d+@@\s*)?(.*)$", ligne)
    if not match:
        return None, ligne

    return int(match.group(1)), match.group(2)


def compter_caracteres(texte):
    return len(nettoyer_marqueurs_pages(texte))


def extraire_mots(texte):
    texte = nettoyer_marqueurs_pages(texte).lower()
    return re.findall(r"\b[a-zàâäéèêëîïôöùûüçœ]+\b", texte)


def compter_mots(texte):
    return len(extraire_mots(texte))


def mots_les_plus_frequents(texte, nombre=10):
    mots = extraire_mots(texte)
    mots_filtres = [
        mot for mot in mots
        if mot not in MOTS_A_IGNORER and len(mot) > 2
    ]

    compteur = Counter(mots_filtres)
    return compteur.most_common(nombre)
