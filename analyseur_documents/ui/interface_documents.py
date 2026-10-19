from pathlib import Path
from tkinter import filedialog

from ..export.export_pdf import exporter_graphiques as exporter_figure
from ..export.export_pdf import exporter_resultat
from ..pdf.lecteur_pdf import lire_pdf


TYPES_DOCUMENTS = [
    ("Documents texte et PDF", "*.txt *.pdf"),
    ("Fichiers texte", "*.txt"),
    ("Fichiers PDF", "*.pdf")
]

TYPES_RAPPORTS = [
    ("Rapport PDF", "*.pdf"),
    ("Page HTML", "*.html"),
    ("Fichier texte", "*.txt"),
    ("CSV phrases longues", "*.csv")
]

TYPES_GRAPHIQUES = [
    ("Image PNG", "*.png"),
    ("Document PDF", "*.pdf"),
    ("Image SVG", "*.svg")
]


def choisir_document():
    return filedialog.askopenfilename(
        title="Choisir un document",
        filetypes=TYPES_DOCUMENTS
    )


def lire_document(
    chemin_fichier,
    ignorer_titres=True,
    ignorer_entetes_pieds=True
):
    extension = Path(chemin_fichier).suffix.lower()

    if extension == ".txt":
        with open(chemin_fichier, "r", encoding="utf-8") as fichier:
            return {
                "texte": fichier.read(),
                "nettoyage_pdf": None
            }

    if extension == ".pdf":
        return lire_pdf(
            chemin_fichier,
            ignorer_titres=ignorer_titres,
            ignorer_entetes_pieds=ignorer_entetes_pieds,
            retourner_details=True
        )

    return None


def demander_chemin_rapport():
    return filedialog.asksaveasfilename(
        title="Exporter le rapport",
        defaultextension=".pdf",
        filetypes=TYPES_RAPPORTS
    )


def demander_chemin_graphiques():
    return filedialog.asksaveasfilename(
        title="Exporter les graphiques",
        defaultextension=".png",
        filetypes=TYPES_GRAPHIQUES
    )


def exporter_rapport_analyse(resultat, chemin_sortie):
    exporter_resultat(resultat, chemin_sortie)


def exporter_graphiques_analyse(figure, chemin_sortie):
    exporter_figure(figure, chemin_sortie)
