import csv
import html
import textwrap
from pathlib import Path


def _page_phrase(item):
    return f"Page {item['page']} - " if item.get("page") else ""


def _lignes_liste(titre, elements):
    lignes = ["", f"{titre} :"]

    if not elements:
        lignes.append("- Aucun élément.")
        return lignes

    for element in elements:
        lignes.append(f"- {element}")

    return lignes


def _lignes_dictionnaire(titre, donnees):
    lignes = ["", f"{titre} :"]

    if not donnees:
        lignes.append("- Aucune donnée.")
        return lignes

    for cle, valeur in donnees.items():
        lignes.append(f"- {cle} : {valeur}")

    return lignes


def _generer_lignes_rapport(resultat):
    lignes = [
        "=== Rapport d'analyse ===",
        "",
        f"Nombre de caractères : {resultat['nombre_caracteres']}",
        f"Nombre de mots : {resultat['nombre_mots']}",
        f"Nombre de phrases : {resultat['nombre_phrases']}",
    ]

    lisibilite = resultat.get("lisibilite")
    if lisibilite:
        lignes.extend([
            "",
            "Lisibilité :",
            f"- Niveau : {lisibilite['niveau']}",
            f"- Score : {lisibilite['score']} / 100",
            f"- Moyenne : {lisibilite['moyenne_mots_phrase']:.2f} mots par phrase",
            f"- Phrases longues : {lisibilite['pourcentage_phrases_longues']:.1f} %",
        ])

    indice_style = resultat.get("indice_style_artificiel")
    if indice_style:
        lignes.extend([
            "",
            "Indice de style potentiellement artificiel :",
            f"- Niveau : {indice_style['niveau']}",
            f"- Score : {indice_style['score']} / 100",
            f"- Diversité lexicale : {indice_style['diversite_lexicale']:.2f}",
            f"- Régularité des phrases : {indice_style['regularite_phrases']:.2f}",
            f"- Note : {indice_style['note']}",
        ])
        lignes.extend(_lignes_liste("Signaux", indice_style.get("signaux", [])))
        lignes.extend(_lignes_dictionnaire("Détail des signaux", indice_style.get("details", {})))

    resume = resultat.get("resume_qualite")
    if resume:
        lignes.extend([
            "",
            "Résumé qualité :",
            f"- Niveau global : {resume['niveau']}",
            f"- Score : {resume['score']} / 100",
        ])
        lignes.extend(_lignes_liste("Points forts", resume["points_forts"]))
        lignes.extend(_lignes_liste("Points à améliorer", resume["points_a_ameliorer"]))
        lignes.extend(_lignes_liste("Recommandations", resume["recommandations"]))

    lignes.extend(["", "Mots les plus fréquents :"])
    for mot, frequence in resultat["mots_frequents"]:
        lignes.append(f"- {mot} : {frequence}")

    lignes.extend(_lignes_dictionnaire("Connecteurs logiques fréquents", resultat.get("connecteurs_frequents", {})))
    lignes.extend(_lignes_dictionnaire("Formules génériques repérées", resultat.get("formules_generiques", {})))
    lignes.extend(_lignes_dictionnaire("Répartition des longueurs", resultat.get("repartition_longueurs", {})))
    lignes.extend(_lignes_dictionnaire("Phrases longues par page", resultat.get("phrases_longues_par_page", {})))
    lignes.extend(_lignes_dictionnaire("Alertes de complexité", resultat.get("alertes_complexite", {})))

    structure = resultat.get("structure_document")
    if structure:
        lignes.extend([
            "",
            "Structure du document :",
            f"- Lignes textuelles détectées : {structure['nombre_lignes_textuelles']}",
            f"- Listes à puces détectées : {structure['nombre_listes_puces']}",
            "",
            "Listes à puces :"
        ])

        lignes.insert(
            len(lignes) - 2,
            f"- Éléments de listes à puces : {structure.get('nombre_elements_listes_puces', 0)}"
        )

        if not structure.get("listes_puces"):
            lignes.append("- Aucune liste à puces détectée.")
        else:
            for index, liste in enumerate(structure["listes_puces"], start=1):
                page = f"Page {liste['page']} - " if liste.get("page") else ""
                elements = liste.get("elements", [])
                lignes.append(f"- Liste {index} - {page}{len(elements)} élément(s)")

                for element in elements:
                    page_element = f"Page {element['page']} - " if element.get("page") else ""
                    lignes.append(f"  - {page_element}{element['texte']}")

    nettoyage_pdf = resultat.get("nettoyage_pdf")
    if nettoyage_pdf:
        lignes.extend([
            "",
            "Nettoyage PDF :",
            f"- Lignes ignorées : {nettoyage_pdf['nombre_lignes_ignorees']}",
            f"- Marge haut : {nettoyage_pdf['marge_haut_ratio'] * 100:.0f} %",
            f"- Marge bas : {nettoyage_pdf['marge_bas_ratio'] * 100:.0f} %",
            f"- Seuil de répétition : {nettoyage_pdf['seuil_repetition'] * 100:.0f} %",
            "",
            "Lignes ignorées :"
        ])

        lignes_ignorees = nettoyage_pdf.get("lignes_ignorees", [])
        if not lignes_ignorees:
            lignes.append("- Aucune ligne ignorée.")
        else:
            for item in lignes_ignorees[:120]:
                lignes.append(f"- Page {item['page']} - {item['raison']} : {item['texte']}")

            if len(lignes_ignorees) > 120:
                lignes.append(f"- ... {len(lignes_ignorees) - 120} ligne(s) ignorée(s) non affichée(s).")

    lignes.extend(["", "Phrases trop longues :"])
    if not resultat["phrases_longues"]:
        lignes.append("- Aucune phrase trop longue.")
    else:
        for item in resultat["phrases_longues"]:
            lignes.append(f"- {_page_phrase(item)}{item['nombre_mots']} mots : {item['phrase']}")

            if item.get("alertes"):
                lignes.append(f"  Alertes : {', '.join(item['alertes'])}")

            if item.get("connecteurs"):
                lignes.append(f"  Connecteurs : {', '.join(item['connecteurs'])}")

            if item.get("suggestion"):
                lignes.append(f"  Suggestion : {item['suggestion']}")

    lignes.extend(["", "Termes techniques détectés :"])
    if not resultat["termes_techniques"]:
        lignes.append("- Aucun terme technique détecté.")
    else:
        for item in resultat["termes_techniques"]:
            lignes.append(f"- {item['terme']} : {item['occurrences']} occurrence(s)")

    lignes.extend(["", "Termes techniques non trouvés :"])
    absents = resultat.get("termes_techniques_absents", [])
    if not absents:
        lignes.append("- Tous les termes recherchés ont été trouvés.")
    else:
        for terme in absents:
            lignes.append(f"- {terme}")

    return lignes


def exporter_rapport_txt(resultat, chemin_sortie):
    with open(chemin_sortie, "w", encoding="utf-8") as fichier:
        fichier.write("\n".join(_generer_lignes_rapport(resultat)) + "\n")


def exporter_rapport_html(resultat, chemin_sortie):
    lignes = _generer_lignes_rapport(resultat)
    contenu = "\n".join(html.escape(ligne) for ligne in lignes)

    page = f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <title>Rapport d'analyse</title>
  <style>
    body {{
      font-family: Arial, sans-serif;
      line-height: 1.55;
      max-width: 980px;
      margin: 32px auto;
      color: #202124;
      background: #ffffff;
    }}
    h1 {{
      margin-bottom: 8px;
    }}
    pre {{
      white-space: pre-wrap;
      background: #f6f8fa;
      border: 1px solid #d0d7de;
      padding: 18px;
      border-radius: 8px;
    }}
  </style>
</head>
<body>
  <h1>Rapport d'analyse</h1>
  <pre>{contenu}</pre>
</body>
</html>
"""

    with open(chemin_sortie, "w", encoding="utf-8") as fichier:
        fichier.write(page)


def exporter_rapport_csv(resultat, chemin_sortie):
    with open(chemin_sortie, "w", encoding="utf-8", newline="") as fichier:
        writer = csv.writer(fichier, delimiter=";")
        writer.writerow([
            "page",
            "nombre_mots",
            "phrase",
            "alertes",
            "connecteurs",
            "suggestion",
        ])

        for item in resultat["phrases_longues"]:
            writer.writerow([
                item.get("page") or "",
                item["nombre_mots"],
                item["phrase"],
                ", ".join(item.get("alertes", [])),
                ", ".join(item.get("connecteurs", [])),
                item.get("suggestion", ""),
            ])


def exporter_rapport_pdf(resultat, chemin_sortie):
    from matplotlib.backends.backend_pdf import PdfPages
    from matplotlib.figure import Figure

    lignes = _generer_lignes_rapport(resultat)
    lignes_wrappees = []

    for ligne in lignes:
        if not ligne:
            lignes_wrappees.append("")
            continue
        lignes_wrappees.extend(textwrap.wrap(ligne, width=95) or [""])

    lignes_par_page = 44

    with PdfPages(chemin_sortie) as pdf:
        for index in range(0, len(lignes_wrappees), lignes_par_page):
            figure = Figure(figsize=(8.27, 11.69))
            axe = figure.add_subplot(111)
            axe.axis("off")
            extrait = "\n".join(lignes_wrappees[index:index + lignes_par_page])
            axe.text(
                0.05,
                0.96,
                extrait,
                va="top",
                ha="left",
                family="monospace",
                fontsize=9,
                transform=axe.transAxes,
            )
            pdf.savefig(figure, bbox_inches="tight")


def exporter_resultat(resultat, chemin_sortie):
    extension = Path(chemin_sortie).suffix.lower()

    if extension == ".html":
        exporter_rapport_html(resultat, chemin_sortie)
        return

    if extension == ".csv":
        exporter_rapport_csv(resultat, chemin_sortie)
        return

    if extension == ".pdf":
        exporter_rapport_pdf(resultat, chemin_sortie)
        return

    exporter_rapport_txt(resultat, chemin_sortie)


def exporter_graphiques(figure, chemin_sortie):
    extension = Path(chemin_sortie).suffix.lower()

    if extension not in {".png", ".pdf", ".svg"}:
        chemin_sortie = f"{chemin_sortie}.png"

    figure.savefig(chemin_sortie, bbox_inches="tight", dpi=160)
