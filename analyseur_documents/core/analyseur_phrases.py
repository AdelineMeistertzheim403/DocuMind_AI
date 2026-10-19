import re


CONNECTEURS = [
    "cependant",
    "toutefois",
    "néanmoins",
    "mais",
    "car",
    "donc",
    "ainsi",
    "en effet",
    "de plus",
    "par ailleurs",
    "tandis que",
    "alors que",
    "c'est pourquoi"
]


def _extraire_mots(texte):
    texte = texte.lower()
    return re.findall(r"\b[a-zàâäéèêëîïôöùûüçœ]+\b", texte)


def _extraire_page_ligne(ligne):
    match = re.match(r"^@@PAGE:(\d+)@@\s*(?:@@PDFPAGE:\d+@@\s*)?(.*)$", ligne)
    if not match:
        return None, ligne

    return int(match.group(1)), match.group(2)


def _extraire_pages_ligne(ligne):
    match = re.match(r"^@@PAGE:(\d+)@@\s*(?:@@PDFPAGE:(\d+)@@\s*)?(.*)$", ligne)
    if not match:
        return None, None, ligne

    page = int(match.group(1))
    page_pdf = int(match.group(2)) if match.group(2) else page
    return page, page_pdf, match.group(3)


def nettoyer_marqueurs_pages(texte):
    return re.sub(r"@@(?:PDF)?PAGE:\d+@@\s*", "", texte)


def normaliser_texte_pour_phrases(texte):
    texte = texte.replace("\r\n", "\n").replace("\r", "\n")
    # Recolle les mots coupes par un retour a la ligne dans les PDF.
    texte = re.sub(r"(\w)-\n(\w)", r"\1\2", texte)
    return texte


def _contenu_ligne(ligne):
    _, contenu = _extraire_page_ligne(ligne.strip())
    return re.sub(r"\s+", " ", contenu).strip()


def _normaliser_titre_section(ligne):
    ligne = _contenu_ligne(ligne)
    ligne = re.sub(r"^\d+(?:\.\d+)*\.?\s+", "", ligne)
    return ligne.strip(" \t:-")


def _est_entree_sommaire(ligne):
    ligne = _contenu_ligne(ligne)
    ligne_min = ligne.lower()

    if not ligne:
        return False

    if re.fullmatch(r"(sommaire|table des mati.res)", ligne_min):
        return True

    if re.search(r"\.{3,}", ligne):
        return True

    mots = _extraire_mots(ligne)
    if len(mots) <= 10 and re.search(r"\s\d+\s*$", ligne):
        return True

    return False


def _est_titre_section(ligne, motifs):
    titre = _normaliser_titre_section(ligne)

    if not titre:
        return False

    if _est_entree_sommaire(titre):
        return False

    if re.search(r"[.!?]$", titre):
        return False

    return any(re.fullmatch(motif, titre, flags=re.IGNORECASE) for motif in motifs)


def _compter_mots_apres(texte, position, taille=1200):
    extrait = texte[position:position + taille]
    lignes = [
        _contenu_ligne(ligne)
        for ligne in extrait.splitlines()
        if not _est_entree_sommaire(ligne)
    ]
    return len(_extraire_mots(" ".join(lignes)))


def _trouver_ligne_section(texte, motifs, depart=0, mots_min_apres=0):
    position = 0

    for ligne in texte.splitlines(keepends=True):
        debut_ligne = position
        fin_ligne = position + len(ligne)
        position = fin_ligne

        if debut_ligne < depart:
            continue

        if not _est_titre_section(ligne, motifs):
            continue

        if mots_min_apres and _compter_mots_apres(texte, fin_ligne) < mots_min_apres:
            continue

        return debut_ligne, fin_ligne

    return None


def _extraire_entree_sommaire(ligne):
    _, page_pdf, contenu = _extraire_pages_ligne(ligne.strip())
    match = re.match(r"^(.*?)\.{3,}\s*(\d+)\s*$", contenu.strip())

    if not match:
        return None

    titre = re.sub(r"\s+", " ", match.group(1)).strip()
    titre = re.sub(r"^\d+(?:\.\d+)*\.?\s*", "", titre).strip()

    if not titre:
        return None

    return {
        "page_pdf": page_pdf,
        "titre": titre,
        "titre_min": titre.lower(),
        "page_logique": int(match.group(2))
    }


def _extraire_entrees_sommaire(texte):
    entrees = []

    for ligne in texte.splitlines():
        entree = _extraire_entree_sommaire(ligne)
        if entree:
            entrees.append(entree)

    return entrees


def _position_premiere_ligne_page(texte, page_cible):
    position = 0

    for ligne in texte.splitlines(keepends=True):
        _, page_pdf, _ = _extraire_pages_ligne(ligne.strip())
        if page_pdf and page_pdf >= page_cible:
            return position
        position += len(ligne)

    return None


def _trouver_zone_depuis_sommaire(texte):
    entrees = _extraire_entrees_sommaire(texte)

    if not entrees:
        return None

    entree_intro = next(
        (
            entree for entree in entrees
            if re.fullmatch(r"introduction(?: g.n.rale)?", entree["titre_min"], flags=re.IGNORECASE)
        ),
        None
    )

    if entree_intro is None:
        return None

    pages_sommaire = []
    page_attendue = entree_intro["page_pdf"]
    for page in sorted({entree["page_pdf"] for entree in entrees if entree["page_pdf"] is not None}):
        if page < entree_intro["page_pdf"]:
            continue
        if page != page_attendue:
            break
        pages_sommaire.append(page)
        page_attendue += 1

    entrees = [
        entree for entree in entrees
        if entree["page_pdf"] in pages_sommaire
    ]
    derniere_page_sommaire = max(
        entree["page_pdf"] for entree in entrees
        if entree["page_pdf"] is not None
    )
    page_debut = derniere_page_sommaire + 1
    debut = _position_premiere_ligne_page(texte, page_debut)

    if debut is None:
        return None

    entree_conclusion = next(
        (
            entree for entree in entrees
            if entree["page_logique"] > entree_intro["page_logique"]
            and re.fullmatch(r"conclusion(?: g.n.rale)?", entree["titre_min"], flags=re.IGNORECASE)
        ),
        None
    )
    fin = len(texte)

    if entree_conclusion:
        titres_fin = (
            r"bibliographie",
            r"webographie",
            r"r.f.rences",
            r"annexes?",
            r"table des illustrations",
            r"liste des abr.viations",
            r"glossaire",
            r"r.sum.",
            r"abstract",
            r"remerciements"
        )
        entree_apres_conclusion = next(
            (
                entree for entree in entrees
                if entree["page_logique"] > entree_conclusion["page_logique"]
                and any(
                    re.fullmatch(motif, entree["titre_min"], flags=re.IGNORECASE)
                    for motif in titres_fin
                )
            ),
            None
        )

        if entree_apres_conclusion:
            page_fin = (
                derniere_page_sommaire
                + (entree_apres_conclusion["page_logique"] - entree_intro["page_logique"])
                + 1
            )
            position_fin = _position_premiere_ligne_page(texte, page_fin)
            if position_fin is not None:
                fin = position_fin

    return debut, fin


def _extraire_zone_memoire_ancienne(texte):
    # Limite l'analyse narrative a la zone Introduction -> Conclusion.
    texte_normalise = normaliser_texte_pour_phrases(texte)

    debut = None
    for match in re.finditer(r"\bintroduction\b", texte_normalise, flags=re.IGNORECASE):
        extrait = texte_normalise[match.start():match.start() + 800]
        if re.search(r"\.{5,}", extrait):
            continue
        if len(_extraire_mots(extrait)) < 40:
            continue
        debut = match.start()
        break

    if debut is None:
        return texte_normalise

    fin_match = None
    for match in re.finditer(r"\bconclusion\b", texte_normalise, flags=re.IGNORECASE):
        if match.start() > debut:
            extrait = texte_normalise[match.start():match.start() + 800]
            if re.search(r"\.{5,}", extrait):
                continue
            fin_match = match
            break

    if not fin_match:
        return texte_normalise[debut:]

    fin = len(texte_normalise)
    sections_fin = re.search(
        r"\n\s*(?:@@PAGE:\d+@@\s*)?(liste des abréviations|table des illustrations|résumé|annexes)\b",
        texte_normalise[fin_match.end():],
        flags=re.IGNORECASE
    )

    if sections_fin:
        fin = fin_match.end() + sections_fin.start()

    return texte_normalise[debut:fin]


def extraire_zone_memoire(texte):
    # Limite l'analyse narrative a la vraie zone Introduction -> Conclusion.
    texte_normalise = normaliser_texte_pour_phrases(texte)

    intro = _trouver_ligne_section(
        texte_normalise,
        [r"introduction", r"introduction g.n.rale"],
        mots_min_apres=30
    )

    if intro is None:
        zone_sommaire = _trouver_zone_depuis_sommaire(texte_normalise)
        if zone_sommaire:
            debut, fin = zone_sommaire
            return texte_normalise[debut:fin]
        return texte_normalise

    debut, _ = intro
    conclusion = _trouver_ligne_section(
        texte_normalise,
        [r"conclusion", r"conclusion g.n.rale"],
        depart=debut + 1
    )

    if conclusion is None:
        return texte_normalise[debut:]

    _, fin_titre_conclusion = conclusion
    fin = len(texte_normalise)
    section_apres_conclusion = _trouver_ligne_section(
        texte_normalise,
        [
            r"bibliographie",
            r"webographie",
            r"r.f.rences",
            r"annexes?",
            r"table des illustrations",
            r"liste des abr.viations",
            r"glossaire",
            r"r.sum.",
            r"abstract",
            r"remerciements"
        ],
        depart=fin_titre_conclusion
    )

    if section_apres_conclusion:
        fin = section_apres_conclusion[0]

    return texte_normalise[debut:fin]


def filtrer_blocs_non_narratifs(texte):
    lignes_filtres = []

    motifs_lignes = [
        r"^(figure|annexe|table des illustrations|liste des abréviations|mots-clés)\b",
        r"^(route dynamique|clé dictionnaire|appel api métadonnées|lecture table dictionary|construction configuration|overrides dictionaryregistry\.ts|chargement des données|affichage tableau)$",
        r"^(oui|non)$",
        r"^(key|count|icon_name|fa_icon|icon_color|active|is_external|champ|description)$"
    ]

    for ligne in texte.split("\n"):
        page, contenu = _extraire_page_ligne(ligne.strip())
        prefixe = f"@@PAGE:{page}@@ " if page else ""
        ligne_propre = contenu.strip()

        if not ligne_propre:
            lignes_filtres.append("")
            continue

        if any(re.match(motif, ligne_propre, flags=re.IGNORECASE) for motif in motifs_lignes):
            continue

        if re.search(r"[{}\[\]]|/admin/|dictionarykey|icon_name|fa_icon", ligne_propre, flags=re.IGNORECASE):
            continue

        lignes_filtres.append(prefixe + contenu)

    return "\n".join(lignes_filtres)


def est_titre_probable(ligne):
    ligne = ligne.strip()

    if not ligne:
        return False

    if re.search(r"[.!?]$", ligne):
        return False

    mots = _extraire_mots(ligne)

    if len(mots) < 2:
        return False

    if re.match(r"^\d+(?:\.\d+)*\s+", ligne):
        return True

    if len(mots) <= 10 and not re.search(r"[,;]", ligne):
        return True

    if ligne.isupper() and len(mots) <= 12:
        return True

    return False


def preparer_texte_pour_phrases(texte, mode_memoire=True, filtrer_blocs=True):
    texte_prepare = normaliser_texte_pour_phrases(texte)

    if mode_memoire:
        texte_prepare = extraire_zone_memoire(texte_prepare)

    if filtrer_blocs:
        texte_prepare = filtrer_blocs_non_narratifs(texte_prepare)

    return texte_prepare


def est_ligne_parasite(ligne, ignorer_titres=True):
    ligne = ligne.strip()

    if not ligne:
        return True

    if re.fullmatch(r"\d+", ligne):
        return True

    if re.search(r"\.{5,}", ligne):
        return True

    if ligne.startswith("Adeline Meistertzheim"):
        return True

    if "Stage dans l'entreprise Patas Monkey" in ligne:
        return True

    if re.match(r"^(figure|annexe|table des illustrations)\b", ligne, flags=re.IGNORECASE):
        return True

    mots = _extraire_mots(ligne)

    if ignorer_titres and est_titre_probable(ligne):
        return True

    if ligne.endswith(":") and len(mots) <= 12:
        return True

    if ":" in ligne and len(mots) <= 10 and not re.search(r"[.!?]$", ligne):
        return True

    if len(mots) <= 4 and not re.search(r"[.!?]$", ligne):
        return True

    return False


def _ajouter_segments(phrases, ligne_courante, page_courante):
    segments = re.split(r"(?<=[.!?])\s+", ligne_courante)

    for segment in segments:
        segment = re.sub(r"\s+", " ", segment).strip()
        if segment:
            phrases.append({
                "phrase": segment,
                "page": page_courante
            })


def decouper_phrases_details(
    texte,
    mode_memoire=True,
    filtrer_blocs=True,
    ignorer_titres=True
):
    texte_normalise = preparer_texte_pour_phrases(
        texte,
        mode_memoire=mode_memoire,
        filtrer_blocs=filtrer_blocs
    )
    blocs = re.split(r"\n{2,}", texte_normalise)
    phrases = []

    for bloc in blocs:
        bloc = bloc.strip()
        if not bloc:
            continue

        lignes = [ligne.strip() for ligne in bloc.split("\n")]
        ligne_courante = ""
        page_courante = None

        for ligne in lignes:
            page, ligne = _extraire_page_ligne(ligne)

            if est_ligne_parasite(ligne, ignorer_titres=ignorer_titres):
                continue

            ligne = re.sub(r"\s+", " ", ligne).strip()
            if not ligne:
                continue

            if ligne_courante:
                ligne_courante = f"{ligne_courante} {ligne}"
            else:
                ligne_courante = ligne
                page_courante = page

            if re.search(r"[.!?][\"')\]]?$", ligne_courante):
                _ajouter_segments(phrases, ligne_courante, page_courante)
                ligne_courante = ""
                page_courante = None

        if ligne_courante:
            phrases.append({
                "phrase": re.sub(r"\s+", " ", ligne_courante).strip(),
                "page": page_courante
            })

    return phrases


def decouper_phrases(
    texte,
    mode_memoire=True,
    filtrer_blocs=True,
    ignorer_titres=True
):
    return [
        item["phrase"]
        for item in decouper_phrases_details(
            texte,
            mode_memoire=mode_memoire,
            filtrer_blocs=filtrer_blocs,
            ignorer_titres=ignorer_titres
        )
    ]


def compter_phrases(
    texte,
    mode_memoire=True,
    filtrer_blocs=True,
    ignorer_titres=True
):
    phrases = [
        item for item in decouper_phrases_details(
            texte,
            mode_memoire=mode_memoire,
            filtrer_blocs=filtrer_blocs,
            ignorer_titres=ignorer_titres
        )
        if item["phrase"].endswith((".", "!", "?"))
    ]
    return len(phrases)


def analyser_complexite_phrase(phrase):
    phrase_minuscule = phrase.lower()
    connecteurs_trouves = [
        connecteur
        for connecteur in CONNECTEURS
        if re.search(rf"\b{re.escape(connecteur)}\b", phrase_minuscule)
    ]
    nombre_virgules = phrase.count(",")
    nombre_parentheses = phrase.count("(") + phrase.count(")")
    alertes = []

    if nombre_virgules >= 4:
        alertes.append(f"{nombre_virgules} virgules")

    if nombre_parentheses >= 2:
        alertes.append("présence de parenthèses")

    if len(connecteurs_trouves) >= 2:
        alertes.append(f"{len(connecteurs_trouves)} connecteurs logiques")

    if nombre_virgules == 0 and len(_extraire_mots(phrase)) >= 35:
        alertes.append("peu de ponctuation interne")

    suggestion = "Essaie de couper cette phrase en deux."
    if connecteurs_trouves:
        suggestion = f"Essaie de couper cette phrase autour de « {connecteurs_trouves[0]} »."
    elif nombre_virgules >= 2:
        suggestion = "Essaie de transformer une partie après une virgule en nouvelle phrase."

    return {
        "nombre_virgules": nombre_virgules,
        "nombre_parentheses": nombre_parentheses,
        "connecteurs": connecteurs_trouves,
        "alertes": alertes,
        "suggestion": suggestion
    }


def detecter_phrases_longues(
    texte,
    limite_mots=35,
    mode_memoire=True,
    filtrer_blocs=True,
    ignorer_titres=True
):
    phrases = decouper_phrases_details(
        texte,
        mode_memoire=mode_memoire,
        filtrer_blocs=filtrer_blocs,
        ignorer_titres=ignorer_titres
    )

    phrases_longues = []

    for item in phrases:
        phrase = item["phrase"]

        if not phrase.endswith((".", "!", "?")):
            continue

        mots = _extraire_mots(phrase)

        if len(mots) > limite_mots:
            analyse_complexite = analyser_complexite_phrase(phrase)
            phrases_longues.append({
                "phrase": phrase.strip(),
                "nombre_mots": len(mots),
                "page": item["page"],
                **analyse_complexite
            })

    return phrases_longues


def extraire_longueurs_phrases(
    texte,
    mode_memoire=True,
    filtrer_blocs=True,
    ignorer_titres=True
):
    phrases = decouper_phrases_details(
        texte,
        mode_memoire=mode_memoire,
        filtrer_blocs=filtrer_blocs,
        ignorer_titres=ignorer_titres
    )

    longueurs = []

    for item in phrases:
        phrase = item["phrase"]
        if not phrase.endswith((".", "!", "?")):
            continue

        mots = _extraire_mots(phrase)
        if mots:
            longueurs.append(len(mots))

    return longueurs
