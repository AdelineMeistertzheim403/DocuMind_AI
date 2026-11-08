TERMES_TECHNIQUES_PAR_DEFAUT = [
    "API",
    "React Native",
    "Docker",
    "base de données",
    "SQL",
    "NoSQL",
    "Spring Boot",
    "Laravel",
    "Dolibarr",
    "interface utilisateur",
    "authentification",
    "endpoint",
    "JSON"
]


def extraire_termes_depuis_texte(contenu):
    return [ligne.strip() for ligne in contenu.splitlines() if ligne.strip()]


def formater_statistiques(resultat, nombre_termes_recherches):
    lignes = [
        "STATISTIQUES GÉNÉRALES",
        "",
        f"Nombre de caractères : {resultat['nombre_caracteres']}",
        f"Nombre de mots : {resultat['nombre_mots']}",
        f"Nombre de phrases : {resultat['nombre_phrases']}"
    ]

    if resultat["nombre_phrases"] > 0:
        moyenne = resultat["nombre_mots"] / resultat["nombre_phrases"]
        lignes.append(f"Nombre moyen de mots par phrase : {moyenne:.2f}")

    if "phrases_longues" in resultat:
        lignes.append(f"Nombre de phrases longues : {len(resultat['phrases_longues'])}")

    structure = resultat.get("structure_document")
    if structure:
        lignes.append(f"Nombre de listes à puces détectées : {structure['nombre_listes_puces']}")

    nettoyage_pdf = resultat.get("nettoyage_pdf")
    if nettoyage_pdf:
        lignes.append(f"Lignes PDF ignorées en en-tête/pied : {nettoyage_pdf['nombre_lignes_ignorees']}")

    lisibilite = resultat.get("lisibilite")
    if lisibilite:
        lignes.extend([
            "",
            "LISIBILITÉ",
            f"Niveau : {lisibilite['niveau']}",
            f"Score : {lisibilite['score']} / 100",
            f"Moyenne analysée : {lisibilite['moyenne_mots_phrase']:.2f} mots par phrase",
            f"Phrases longues : {lisibilite['pourcentage_phrases_longues']:.1f} %"
        ])

    indice_style = resultat.get("indice_style_artificiel")
    if indice_style:
        lignes.extend([
            "",
            "INDICE DE STYLE POTENTIELLEMENT ARTIFICIEL",
            f"Niveau : {indice_style['niveau']}",
            f"Score : {indice_style['score']} / 100",
            f"Diversité lexicale : {indice_style['diversite_lexicale']:.2f}",
            f"Régularité des phrases : {indice_style['regularite_phrases']:.2f}",
            indice_style["note"]
        ])

        if indice_style.get("signaux"):
            lignes.append("Signaux :")
            for signal in indice_style["signaux"]:
                lignes.append(f"- {signal}")

    lignes.append("")
    lignes.append(f"Nombre de termes techniques recherchés : {nombre_termes_recherches}")

    if "termes_techniques" in resultat:
        lignes.append(f"Nombre de termes techniques trouvés : {len(resultat['termes_techniques'])}")

    absents = resultat.get("termes_techniques_absents", [])
    lignes.append(f"Nombre de termes techniques non trouvés : {len(absents)}")

    return "\n".join(lignes) + "\n"


def formater_resume_qualite(resultat):
    resume = resultat.get("resume_qualite")

    if not resume:
        return "RÉSUMÉ QUALITÉ\n\nAucun résumé disponible.\n"

    lignes = [
        "RÉSUMÉ QUALITÉ",
        "",
        f"Niveau global : {resume['niveau']}",
        f"Score : {resume['score']} / 100",
        "",
        "POINTS FORTS"
    ]

    for point in resume["points_forts"]:
        lignes.append(f"- {point}")

    lignes.extend(["", "POINTS À AMÉLIORER"])
    for point in resume["points_a_ameliorer"]:
        lignes.append(f"- {point}")

    lignes.extend(["", "RECOMMANDATIONS"])
    for recommandation in resume["recommandations"]:
        lignes.append(f"- {recommandation}")

    return "\n".join(lignes) + "\n"


def formater_mots_frequents(resultat):
    lignes = ["MOTS LES PLUS FRÉQUENTS", ""]

    mots_frequents = resultat.get("mots_frequents", [])
    if not mots_frequents:
        lignes.append("Aucun mot fréquent détecté.")
        return "\n".join(lignes) + "\n"

    for index, (mot, frequence) in enumerate(mots_frequents, start=1):
        lignes.append(f"{index}. {mot} : {frequence}")

    connecteurs = resultat.get("connecteurs_frequents", {})
    if connecteurs:
        lignes.extend(["", "CONNECTEURS LOGIQUES FRÉQUENTS", ""])
        for connecteur, frequence in connecteurs.items():
            lignes.append(f"- {connecteur} : {frequence}")

    formules = resultat.get("formules_generiques", {})
    if formules:
        lignes.extend(["", "FORMULES GÉNÉRIQUES REPÉRÉES", ""])
        for formule, frequence in formules.items():
            lignes.append(f"- {formule} : {frequence}")

    return "\n".join(lignes) + "\n"


def formater_phrases_longues(resultat, limite):
    lignes = [f"PHRASES DE PLUS DE {limite} MOTS", ""]

    if "phrases_longues" not in resultat:
        lignes.append("La détection des phrases longues n'est pas encore disponible.")
        return "\n".join(lignes) + "\n"

    phrases_longues = resultat["phrases_longues"]
    if len(phrases_longues) == 0:
        lignes.append("Aucune phrase trop longue détectée.")
        return "\n".join(lignes) + "\n"

    for index, item in enumerate(phrases_longues, start=1):
        page = f"Page {item['page']} - " if item.get("page") else ""
        lignes.append(f"{index}. {page}{item['nombre_mots']} mots")

        alertes = item.get("alertes", [])
        if alertes:
            lignes.append(f"Alertes : {', '.join(alertes)}")

        connecteurs = item.get("connecteurs", [])
        if connecteurs:
            lignes.append(f"Connecteurs repérés : {', '.join(connecteurs)}")

        suggestion = item.get("suggestion")
        if suggestion:
            lignes.append(f"Suggestion : {suggestion}")

        lignes.append(item["phrase"])
        lignes.append("")

    return "\n".join(lignes) + "\n"


def formater_termes_techniques(resultat):
    lignes = ["TERMES TECHNIQUES DÉTECTÉS", ""]

    if "termes_techniques" not in resultat:
        lignes.append("La détection des termes techniques n'est pas encore disponible.")
        return "\n".join(lignes) + "\n"

    termes = resultat["termes_techniques"]
    if len(termes) == 0:
        lignes.append("Aucun terme technique détecté.")
    else:
        for item in termes:
            lignes.append(f"- {item['terme']} : {item['occurrences']} occurrence(s)")

    absents = resultat.get("termes_techniques_absents", [])
    lignes.extend(["", "TERMES NON TROUVÉS", ""])

    if not absents:
        lignes.append("Tous les termes recherchés ont été trouvés.")
    else:
        for terme in absents:
            lignes.append(f"- {terme}")

    return "\n".join(lignes) + "\n"


def formater_structure_document(resultat):
    structure = resultat.get("structure_document")

    if not structure:
        return "STRUCTURE DU DOCUMENT\n\nAucune donnée de structure disponible.\n"

    lignes = [
        "STRUCTURE DU DOCUMENT",
        "",
        f"Nombre de lignes textuelles détectées : {structure['nombre_lignes_textuelles']}",
        f"Nombre de listes à puces détectées : {structure['nombre_listes_puces']}",
        "",
        "LISTES À PUCES DÉTECTÉES",
        ""
    ]

    lignes.insert(
        4,
        f"Nombre d'éléments de listes à puces : {structure.get('nombre_elements_listes_puces', 0)}"
    )

    listes = structure.get("listes_puces", [])
    if not listes:
        lignes.append("Aucune liste à puces détectée.")
    else:
        for index, liste in enumerate(listes, start=1):
            page = f"Page {liste['page']} - " if liste.get("page") else ""
            elements = liste.get("elements", [])
            lignes.append(f"{index}. {page}{len(elements)} élément(s)")

            for element in elements:
                page_element = f"Page {element['page']} - " if element.get("page") else ""
                lignes.append(f"   - {page_element}{element['texte']}")

    nettoyage_pdf = resultat.get("nettoyage_pdf")
    if nettoyage_pdf:
        lignes.extend([
            "",
            "NETTOYAGE PDF",
            "",
            f"Lignes ignorées : {nettoyage_pdf['nombre_lignes_ignorees']}",
            f"Marge haut : {nettoyage_pdf['marge_haut_ratio'] * 100:.0f} %",
            f"Marge bas : {nettoyage_pdf['marge_bas_ratio'] * 100:.0f} %",
            f"Seuil de répétition : {nettoyage_pdf['seuil_repetition'] * 100:.0f} %",
            "",
            "LIGNES IGNORÉES",
            ""
        ])

        lignes_ignorees = nettoyage_pdf.get("lignes_ignorees", [])
        if not lignes_ignorees:
            lignes.append("Aucune ligne ignorée.")
        else:
            for index, item in enumerate(lignes_ignorees[:80], start=1):
                lignes.append(
                    f"{index}. Page {item['page']} - {item['raison']} : {item['texte']}"
                )

            if len(lignes_ignorees) > 80:
                lignes.append(f"... {len(lignes_ignorees) - 80} ligne(s) ignorée(s) non affichée(s).")

    return "\n".join(lignes) + "\n"


def _afficher_message(axe, titre, message="Aucune donnée"):
    axe.set_title(titre)
    axe.text(0.5, 0.5, message, ha="center", va="center", wrap=True)
    axe.set_xticks([])
    axe.set_yticks([])


def _barres_horizontales(axe, donnees, titre, couleur):
    if not donnees:
        _afficher_message(axe, titre)
        return

    labels = list(donnees.keys())
    valeurs = list(donnees.values())
    axe.barh(labels, valeurs, color=couleur)
    axe.invert_yaxis()
    axe.set_title(titre)
    axe.set_xlabel("Nombre")


def _creer_figure_simple():
    from matplotlib.figure import Figure

    return Figure(figsize=(9.5, 5.2), dpi=100)


def _figure_histogramme_longueurs(resultat):
    longueurs = resultat.get("longueurs_phrases", [])
    figure = _creer_figure_simple()
    axe = figure.add_subplot(111)

    if longueurs:
        nb_classes = min(20, max(5, int(len(longueurs) ** 0.5)))
        axe.hist(longueurs, bins=nb_classes, color="#4E79A7", edgecolor="white")
        axe.set_xlabel("Mots par phrase")
        axe.set_ylabel("Nombre de phrases")
    else:
        _afficher_message(axe, "Distribution des longueurs")

    axe.set_title("Distribution des longueurs de phrases")
    figure.tight_layout()
    return "Distribution des longueurs", figure


def _figure_repartition_longueurs(resultat):
    figure = _creer_figure_simple()
    axe = figure.add_subplot(111)
    donnees = {
        cle: valeur
        for cle, valeur in resultat.get("repartition_longueurs", {}).items()
        if valeur > 0
    }

    _barres_horizontales(axe, donnees, "Phrases par niveau de longueur", "#59A14F")
    figure.tight_layout()
    return "Phrases par niveau", figure


def _figure_phrases_longues_par_page(resultat):
    figure = _creer_figure_simple()
    axe = figure.add_subplot(111)
    donnees = resultat.get("phrases_longues_par_page", {})

    if donnees:
        pages = list(donnees.keys())
        valeurs = list(donnees.values())
        axe.bar([str(page) for page in pages], valeurs, color="#E15759")
        axe.set_xlabel("Page")
        axe.set_ylabel("Nombre de phrases longues")
        axe.set_title("Phrases longues par page")
    else:
        _afficher_message(axe, "Phrases longues par page", "Disponible pour les PDF")

    figure.tight_layout()
    return "Phrases longues par page", figure


def _figure_score_lisibilite(resultat):
    figure = _creer_figure_simple()
    axe = figure.add_subplot(111)
    lisibilite = resultat.get("lisibilite", {})
    score = lisibilite.get("score", 0)
    niveau = lisibilite.get("niveau", "Non calculable")

    axe.barh(["Lisibilité"], [score], color="#76B7B2")
    axe.set_xlim(0, 100)
    axe.set_xlabel("Score / 100")
    axe.set_title(f"Score de lisibilité - {niveau}")
    axe.text(min(score + 2, 96), 0, str(score), va="center")
    figure.tight_layout()
    return "Score de lisibilité", figure


def _figure_termes_techniques(resultat):
    figure = _creer_figure_simple()
    axe = figure.add_subplot(111)
    donnees = {
        item["terme"]: item["occurrences"]
        for item in resultat.get("termes_techniques", [])[:10]
    }

    _barres_horizontales(axe, donnees, "Termes techniques les plus présents", "#F28E2B")
    figure.tight_layout()
    return "Termes techniques", figure


def _figure_termes_trouves_absents(resultat):
    figure = _creer_figure_simple()
    axe = figure.add_subplot(111)
    termes = resultat.get("termes_techniques", [])
    termes_absents = resultat.get("termes_techniques_absents", [])

    axe.bar(
        ["Trouvés", "Non trouvés"],
        [len(termes), len(termes_absents)],
        color=["#59A14F", "#E15759"]
    )
    axe.set_ylabel("Nombre")
    axe.set_title("Termes techniques trouvés / non trouvés")
    figure.tight_layout()
    return "Termes trouvés / absents", figure


def _figure_alertes_complexite(resultat):
    figure = _creer_figure_simple()
    axe = figure.add_subplot(111)
    _barres_horizontales(
        axe,
        resultat.get("alertes_complexite", {}),
        "Alertes de complexité",
        "#B07AA1"
    )
    figure.tight_layout()
    return "Alertes de complexité", figure


def _figure_connecteurs_frequents(resultat):
    figure = _creer_figure_simple()
    axe = figure.add_subplot(111)
    _barres_horizontales(
        axe,
        resultat.get("connecteurs_frequents", {}),
        "Connecteurs logiques fréquents",
        "#EDC948"
    )
    figure.tight_layout()
    return "Connecteurs fréquents", figure


def _figure_signaux_style(resultat):
    figure = _creer_figure_simple()
    axe = figure.add_subplot(111)
    indice_style = resultat.get("indice_style_artificiel", {})
    _barres_horizontales(
        axe,
        indice_style.get("details", {}),
        "Signaux de style potentiellement artificiel",
        "#9C755F"
    )
    if indice_style:
        axe.set_xlabel(f"Score total : {indice_style.get('score', 0)} / 100")
    figure.tight_layout()
    return "Signaux de style", figure


def creer_figures_analyse(resultat):
    try:
        figures = [
            _figure_histogramme_longueurs(resultat),
            _figure_repartition_longueurs(resultat),
            _figure_phrases_longues_par_page(resultat),
            _figure_score_lisibilite(resultat),
            _figure_termes_techniques(resultat),
            _figure_termes_trouves_absents(resultat),
            _figure_alertes_complexite(resultat),
            _figure_connecteurs_frequents(resultat),
            _figure_signaux_style(resultat),
        ]
    except ImportError:
        return [], "Matplotlib n'est pas installé.\nInstalle-le avec : pip install matplotlib"

    return figures, None


def creer_figure_analyse(resultat):
    try:
        from matplotlib.figure import Figure
    except ImportError:
        return None, "Matplotlib n'est pas installé.\nInstalle-le avec : pip install matplotlib"

    longueurs = resultat.get("longueurs_phrases", [])
    mots_frequents = resultat.get("mots_frequents", [])
    repartition = resultat.get("repartition_longueurs", {})
    longues_par_page = resultat.get("phrases_longues_par_page", {})
    termes = resultat.get("termes_techniques", [])
    termes_absents = resultat.get("termes_techniques_absents", [])
    alertes = resultat.get("alertes_complexite", {})
    connecteurs = resultat.get("connecteurs_frequents", {})
    indice_style = resultat.get("indice_style_artificiel", {})
    lisibilite = resultat.get("lisibilite", {})

    if not any([longueurs, mots_frequents, repartition, termes, alertes, connecteurs, indice_style]):
        return None, "Pas de données pour afficher les graphiques."

    figure = Figure(figsize=(13.5, 9), dpi=100)
    axes = [figure.add_subplot(3, 3, index) for index in range(1, 10)]

    axe_hist = axes[0]
    if longueurs:
        nb_classes = min(20, max(5, int(len(longueurs) ** 0.5)))
        axe_hist.hist(longueurs, bins=nb_classes, color="#4E79A7", edgecolor="white")
        axe_hist.set_title("Distribution des longueurs")
        axe_hist.set_xlabel("Mots par phrase")
        axe_hist.set_ylabel("Phrases")
    else:
        _afficher_message(axe_hist, "Distribution des longueurs")

    _barres_horizontales(
        axes[1],
        {cle: valeur for cle, valeur in repartition.items() if valeur > 0},
        "Phrases par niveau",
        "#59A14F"
    )

    if longues_par_page:
        pages = list(longues_par_page.keys())
        valeurs = list(longues_par_page.values())
        axes[2].bar([str(page) for page in pages], valeurs, color="#E15759")
        axes[2].set_title("Phrases longues par page")
        axes[2].set_xlabel("Page")
        axes[2].set_ylabel("Phrases")
    else:
        _afficher_message(axes[2], "Phrases longues par page", "Disponible pour les PDF")

    score_lisibilite = lisibilite.get("score", 0)
    axes[3].barh(["Lisibilité"], [score_lisibilite], color="#76B7B2")
    axes[3].set_xlim(0, 100)
    axes[3].set_title("Score de lisibilité")
    axes[3].set_xlabel("/ 100")
    axes[3].text(score_lisibilite + 2, 0, str(score_lisibilite), va="center")

    termes_graphique = {
        item["terme"]: item["occurrences"]
        for item in termes[:8]
    }
    _barres_horizontales(axes[4], termes_graphique, "Termes techniques", "#F28E2B")

    axes[5].bar(
        ["Trouvés", "Non trouvés"],
        [len(termes), len(termes_absents)],
        color=["#59A14F", "#E15759"]
    )
    axes[5].set_title("Termes trouvés / absents")
    axes[5].set_ylabel("Nombre")

    _barres_horizontales(axes[6], alertes, "Alertes de complexité", "#B07AA1")

    _barres_horizontales(axes[7], connecteurs, "Connecteurs fréquents", "#EDC948")

    signaux_style = indice_style.get("details", {})
    _barres_horizontales(axes[8], signaux_style, "Signaux de style artificiel", "#9C755F")
    if indice_style:
        axes[8].set_xlabel(f"Score total : {indice_style.get('score', 0)} / 100")

    figure.tight_layout()
    return figure, None
