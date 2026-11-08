import tkinter as tk
from tkinter import messagebox
from pathlib import Path

import customtkinter as ctk

from ..core.analyseur import analyser_texte
from .interface_assets import (
    charger_logo_interface,
    configurer_icone_application,
)
from .interface_documents import (
    choisir_document,
    demander_chemin_graphiques,
    demander_chemin_rapport,
    exporter_graphiques_analyse,
    exporter_rapport_analyse,
    lire_document,
)
from .interface_helpers import (
    TERMES_TECHNIQUES_PAR_DEFAUT,
    creer_figures_analyse,
    extraire_termes_depuis_texte,
    formater_mots_frequents,
    formater_phrases_longues,
    formater_resume_qualite,
    formater_statistiques,
    formater_structure_document,
    formater_termes_techniques,
)


class AnalyseurApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Analyseur de documents")
        self.root.geometry("1080x720")
        self.root.minsize(980, 640)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self.dossier_application = Path(__file__).resolve().parents[2]
        self.logo_interface = None
        self.icone_application = None
        self.chemin_icone_temporaire = None

        self.chemin_fichier = None
        self.resultat = None
        self.details_nettoyage_pdf = None
        self.canvas_graphes = None
        self.figure_graphes = None
        self.figures_graphes = []
        self.index_graphe = 0
        self.label_graphe = None
        self.zone_canvas_graphes = None

        self.var_ignorer_titres = tk.BooleanVar(value=True)
        self.var_ignorer_entetes_pieds = tk.BooleanVar(value=True)
        self.var_filtrer_blocs = tk.BooleanVar(value=True)
        self.var_intro_conclusion = tk.BooleanVar(value=True)

        self.configurer_icone_application()
        self.creer_interface()

    def configurer_icone_application(self):
        self.icone_application, self.chemin_icone_temporaire = configurer_icone_application(
            self.root,
            self.dossier_application
        )

    def charger_logo_interface(self):
        return charger_logo_interface(self.dossier_application)

    def creer_interface(self):
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(1, weight=1)

        self.frame_header = ctk.CTkFrame(self.root, corner_radius=15)
        self.frame_header.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="ew")
        self.logo_interface = self.charger_logo_interface()

        colonne_texte = 1 if self.logo_interface else 0
        self.frame_header.grid_columnconfigure(colonne_texte, weight=1)

        if self.logo_interface:
            label_logo = ctk.CTkLabel(
                self.frame_header,
                image=self.logo_interface,
                text=""
            )
            label_logo.grid(row=0, column=0, rowspan=2, padx=(20, 0), pady=15, sticky="w")

        titre = ctk.CTkLabel(
            self.frame_header,
            text="Analyseur de documents",
            font=ctk.CTkFont(size=28, weight="bold")
        )
        titre.grid(row=0, column=colonne_texte, padx=20, pady=(15, 5), sticky="w")

        sous_titre = ctk.CTkLabel(
            self.frame_header,
            text="Analyse rapidement tes fichiers PDF ou TXT : statistiques, mots fréquents, phrases longues et termes techniques.",
            font=ctk.CTkFont(size=14),
            text_color="gray"
        )
        sous_titre.grid(row=1, column=colonne_texte, padx=20, pady=(0, 15), sticky="w")

        self.onglets_principaux = ctk.CTkTabview(self.root, corner_radius=15)
        self.onglets_principaux.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="nsew")
        self.onglets_principaux.add("Configuration")
        self.onglets_principaux.add("Rapport d'analyse")

        self.creer_configuration(self.onglets_principaux.tab("Configuration"))
        self.creer_onglets_rapport(self.onglets_principaux.tab("Rapport d'analyse"))

    def creer_configuration(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(3, weight=1)

        frame_actions = ctk.CTkFrame(parent, corner_radius=12)
        frame_actions.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        frame_actions.grid_columnconfigure(4, weight=1)

        bouton_choisir = ctk.CTkButton(
            frame_actions,
            text="Choisir un fichier",
            command=self.choisir_fichier,
            width=160
        )
        bouton_choisir.grid(row=0, column=0, padx=(15, 8), pady=15)

        bouton_analyser = ctk.CTkButton(
            frame_actions,
            text="Analyser",
            command=self.analyser_document,
            width=120
        )
        bouton_analyser.grid(row=0, column=1, padx=8, pady=15)

        bouton_exporter = ctk.CTkButton(
            frame_actions,
            text="Exporter rapport",
            command=self.exporter_rapport,
            width=145
        )
        bouton_exporter.grid(row=0, column=2, padx=8, pady=15)

        bouton_exporter_graphes = ctk.CTkButton(
            frame_actions,
            text="Exporter graphiques",
            command=self.exporter_graphiques,
            width=160
        )
        bouton_exporter_graphes.grid(row=0, column=3, padx=8, pady=15)

        self.label_fichier = ctk.CTkLabel(
            frame_actions,
            text="Aucun fichier sélectionné",
            text_color="gray"
        )
        self.label_fichier.grid(row=0, column=4, padx=15, pady=15, sticky="w")

        frame_options = ctk.CTkFrame(parent, corner_radius=12)
        frame_options.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="ew")
        frame_options.grid_columnconfigure(4, weight=1)

        label_limite = ctk.CTkLabel(
            frame_options,
            text="Phrase trop longue à partir de :"
        )
        label_limite.grid(row=0, column=0, padx=(15, 8), pady=15, sticky="w")

        self.input_limite_phrase = ctk.CTkEntry(
            frame_options,
            width=70,
            justify="center"
        )
        self.input_limite_phrase.insert(0, "35")
        self.input_limite_phrase.grid(row=0, column=1, pady=15, sticky="w")

        label_mots = ctk.CTkLabel(frame_options, text="mots")
        label_mots.grid(row=0, column=2, padx=8, pady=15, sticky="w")

        bouton_mode = ctk.CTkButton(
            frame_options,
            text="Changer thème",
            command=self.changer_theme,
            width=130
        )
        bouton_mode.grid(row=0, column=5, padx=15, pady=15, sticky="e")

        frame_filtres = ctk.CTkFrame(parent, corner_radius=12)
        frame_filtres.grid(row=2, column=0, padx=10, pady=(0, 10), sticky="ew")
        frame_filtres.grid_columnconfigure(0, weight=1)
        frame_filtres.grid_columnconfigure(1, weight=1)
        frame_filtres.grid_columnconfigure(2, weight=1)
        frame_filtres.grid_columnconfigure(3, weight=1)

        checkbox_titres = ctk.CTkCheckBox(
            frame_filtres,
            text="Ignorer les titres",
            variable=self.var_ignorer_titres
        )
        checkbox_titres.grid(row=0, column=0, padx=15, pady=12, sticky="w")

        checkbox_blocs = ctk.CTkCheckBox(
            frame_filtres,
            text="Ignorer figures, tableaux et annexes",
            variable=self.var_filtrer_blocs
        )
        checkbox_blocs.grid(row=0, column=1, padx=15, pady=12, sticky="w")

        checkbox_zone = ctk.CTkCheckBox(
            frame_filtres,
            text="Analyser Introduction → Conclusion",
            variable=self.var_intro_conclusion
        )
        checkbox_zone.grid(row=0, column=2, padx=15, pady=12, sticky="w")

        checkbox_entetes = ctk.CTkCheckBox(
            frame_filtres,
            text="Ignorer en-têtes et pieds de page",
            variable=self.var_ignorer_entetes_pieds
        )
        checkbox_entetes.grid(row=0, column=3, padx=15, pady=12, sticky="w")

        frame_termes = ctk.CTkFrame(parent, corner_radius=12)
        frame_termes.grid(row=3, column=0, padx=10, pady=(0, 10), sticky="nsew")
        frame_termes.grid_columnconfigure(0, weight=1)
        frame_termes.grid_rowconfigure(2, weight=1)

        label_termes = ctk.CTkLabel(
            frame_termes,
            text="Termes techniques à rechercher",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        label_termes.grid(row=0, column=0, padx=15, pady=(12, 0), sticky="w")

        aide_termes = ctk.CTkLabel(
            frame_termes,
            text="Saisis un terme par ligne. Exemple : API, Docker, base de données, React Native...",
            text_color="gray"
        )
        aide_termes.grid(row=1, column=0, padx=15, pady=(0, 8), sticky="w")

        self.zone_saisie_termes = ctk.CTkTextbox(
            frame_termes,
            height=170,
            font=ctk.CTkFont(size=13)
        )
        self.zone_saisie_termes.grid(row=2, column=0, padx=15, pady=(0, 15), sticky="nsew")
        self.zone_saisie_termes.insert("1.0", "\n".join(TERMES_TECHNIQUES_PAR_DEFAUT))

    def creer_onglets_rapport(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(0, weight=1)

        self.tabview = ctk.CTkTabview(parent, corner_radius=15)
        self.tabview.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")

        self.tabview.add("Statistiques")
        self.tabview.add("Résumé qualité")
        self.tabview.add("Mots fréquents")
        self.tabview.add("Phrases longues")
        self.tabview.add("Termes techniques")
        self.tabview.add("Structure")
        self.tabview.add("Graphiques")

        self.zone_stats = self.creer_zone_texte(self.tabview.tab("Statistiques"))
        self.zone_resume = self.creer_zone_texte(self.tabview.tab("Résumé qualité"))
        self.zone_mots = self.creer_zone_texte(self.tabview.tab("Mots fréquents"))
        self.zone_phrases = self.creer_zone_texte(self.tabview.tab("Phrases longues"))
        self.zone_termes = self.creer_zone_texte(self.tabview.tab("Termes techniques"))
        self.zone_structure = self.creer_zone_texte(self.tabview.tab("Structure"))
        self.frame_graphes = self.creer_zone_graphiques(self.tabview.tab("Graphiques"))

    def creer_zone_texte(self, parent):
        zone_texte = ctk.CTkTextbox(
            parent,
            wrap="word",
            font=ctk.CTkFont(size=14)
        )
        zone_texte.pack(expand=True, fill="both", padx=10, pady=10)
        return zone_texte

    def creer_zone_graphiques(self, parent):
        frame = ctk.CTkFrame(parent)
        frame.pack(expand=True, fill="both", padx=10, pady=10)
        frame.grid_columnconfigure(1, weight=1)
        frame.grid_rowconfigure(1, weight=1)

        bouton_precedent = ctk.CTkButton(
            frame,
            text="Précédent",
            command=self.afficher_graphe_precedent,
            width=120
        )
        bouton_precedent.grid(row=0, column=0, padx=10, pady=10, sticky="w")

        self.label_graphe = ctk.CTkLabel(
            frame,
            text="Aucun graphique",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self.label_graphe.grid(row=0, column=1, padx=10, pady=10)

        bouton_suivant = ctk.CTkButton(
            frame,
            text="Suivant",
            command=self.afficher_graphe_suivant,
            width=120
        )
        bouton_suivant.grid(row=0, column=2, padx=10, pady=10, sticky="e")

        self.zone_canvas_graphes = ctk.CTkFrame(frame, fg_color="transparent")
        self.zone_canvas_graphes.grid(row=1, column=0, columnspan=3, sticky="nsew")
        return frame

    def changer_theme(self):
        mode_actuel = ctk.get_appearance_mode()

        if mode_actuel == "Dark":
            ctk.set_appearance_mode("light")
        else:
            ctk.set_appearance_mode("dark")

    def choisir_fichier(self):
        chemin = choisir_document()

        if chemin:
            self.chemin_fichier = chemin
            nom_fichier = Path(chemin).name
            self.label_fichier.configure(
                text=f"Fichier : {nom_fichier}",
                text_color="white"
            )
            self.vider_resultats()

    def lire_document(self):
        if not self.chemin_fichier:
            messagebox.showwarning(
                "Aucun fichier",
                "Veuillez sélectionner un fichier avant de lancer l'analyse."
            )
            return None

        resultat_document = lire_document(
            self.chemin_fichier,
            ignorer_titres=self.var_ignorer_titres.get(),
            ignorer_entetes_pieds=self.var_ignorer_entetes_pieds.get()
        )

        if resultat_document:
            self.details_nettoyage_pdf = resultat_document.get("nettoyage_pdf")
            return resultat_document["texte"]

        messagebox.showerror(
            "Format non supporté",
            "Seuls les fichiers .txt et .pdf sont acceptés."
        )
        return None

    def analyser_document(self):
        texte = self.lire_document()

        if not texte:
            return

        try:
            limite_phrase_longue = int(self.input_limite_phrase.get())
        except ValueError:
            messagebox.showerror(
                "Valeur invalide",
                "La limite des phrases longues doit être un nombre entier."
            )
            return

        if limite_phrase_longue <= 0:
            messagebox.showerror(
                "Valeur invalide",
                "La limite doit être supérieure à 0."
            )
            return

        termes_techniques = self.recuperer_termes_techniques()

        self.resultat = analyser_texte(
            texte,
            limite_phrase_longue=limite_phrase_longue,
            termes_techniques=termes_techniques,
            mode_memoire=self.var_intro_conclusion.get(),
            filtrer_blocs_non_narratifs_actif=self.var_filtrer_blocs.get(),
            ignorer_titres=self.var_ignorer_titres.get()
        )

        if self.details_nettoyage_pdf:
            self.resultat["nettoyage_pdf"] = self.details_nettoyage_pdf

        self.afficher_resultat()
        self.onglets_principaux.set("Rapport d'analyse")

        messagebox.showinfo(
            "Analyse terminée",
            "Le document a bien été analysé."
        )

    def afficher_resultat(self):
        self.vider_resultats()

        self.afficher_statistiques()
        self.afficher_resume_qualite()
        self.afficher_mots_frequents()
        self.afficher_phrases_longues()
        self.afficher_termes_techniques()
        self.afficher_structure_document()
        self.afficher_graphiques()

    def afficher_statistiques(self):
        termes_recherches = self.recuperer_termes_techniques()
        contenu = formater_statistiques(
            self.resultat,
            nombre_termes_recherches=len(termes_recherches)
        )
        self.zone_stats.insert("end", contenu)

    def afficher_resume_qualite(self):
        self.zone_resume.insert("end", formater_resume_qualite(self.resultat))

    def recuperer_termes_techniques(self):
        contenu = self.zone_saisie_termes.get("1.0", "end")
        return extraire_termes_depuis_texte(contenu)

    def afficher_mots_frequents(self):
        self.zone_mots.insert("end", formater_mots_frequents(self.resultat))

    def afficher_phrases_longues(self):
        limite = self.input_limite_phrase.get()
        self.zone_phrases.insert("end", formater_phrases_longues(self.resultat, limite))

    def afficher_termes_techniques(self):
        self.zone_termes.insert("end", formater_termes_techniques(self.resultat))

    def afficher_structure_document(self):
        self.zone_structure.insert("end", formater_structure_document(self.resultat))

    def afficher_graphiques(self):
        for widget in self.zone_canvas_graphes.winfo_children():
            widget.destroy()

        self.figures_graphes, message = creer_figures_analyse(self.resultat)
        self.index_graphe = 0

        if message:
            self.figure_graphes = None
            self.label_graphe.configure(text="Aucun graphique")
            label = ctk.CTkLabel(self.zone_canvas_graphes, text=message)
            label.pack(expand=True)
            return

        if not self.figures_graphes:
            self.figure_graphes = None
            self.label_graphe.configure(text="Aucun graphique")
            label = ctk.CTkLabel(
                self.zone_canvas_graphes,
                text="Pas de données pour afficher les graphiques."
            )
            label.pack(expand=True)
            return

        self.afficher_graphe_courant()

    def afficher_graphe_courant(self):
        for widget in self.zone_canvas_graphes.winfo_children():
            widget.destroy()

        titre, figure = self.figures_graphes[self.index_graphe]
        self.figure_graphes = figure
        self.label_graphe.configure(
            text=f"{self.index_graphe + 1}/{len(self.figures_graphes)} - {titre}"
        )

        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

        self.canvas_graphes = FigureCanvasTkAgg(figure, master=self.zone_canvas_graphes)
        self.canvas_graphes.draw()
        self.canvas_graphes.get_tk_widget().pack(expand=True, fill="both")

    def afficher_graphe_precedent(self):
        if not self.figures_graphes:
            return

        self.index_graphe = (self.index_graphe - 1) % len(self.figures_graphes)
        self.afficher_graphe_courant()

    def afficher_graphe_suivant(self):
        if not self.figures_graphes:
            return

        self.index_graphe = (self.index_graphe + 1) % len(self.figures_graphes)
        self.afficher_graphe_courant()

    def vider_resultats(self):
        zones = [
            self.zone_stats,
            self.zone_resume,
            self.zone_mots,
            self.zone_phrases,
            self.zone_termes,
            self.zone_structure
        ]

        for zone in zones:
            zone.delete("1.0", "end")

        if self.zone_canvas_graphes:
            for widget in self.zone_canvas_graphes.winfo_children():
                widget.destroy()

        if self.label_graphe:
            self.label_graphe.configure(text="Aucun graphique")

        self.figure_graphes = None
        self.figures_graphes = []
        self.index_graphe = 0

    def exporter_rapport(self):
        if not self.resultat:
            messagebox.showwarning(
                "Aucune analyse",
                "Veuillez analyser un document avant d'exporter le rapport."
            )
            return

        chemin_sortie = demander_chemin_rapport()

        if chemin_sortie:
            exporter_rapport_analyse(self.resultat, chemin_sortie)
            messagebox.showinfo(
                "Export terminé",
                "Le rapport a bien été exporté."
            )

    def exporter_graphiques(self):
        if not self.resultat or not self.figure_graphes:
            messagebox.showwarning(
                "Aucun graphique",
                "Veuillez analyser un document avec des données graphiques avant d'exporter."
            )
            return

        chemin_sortie = demander_chemin_graphiques()

        if chemin_sortie:
            exporter_graphiques_analyse(self.figure_graphes, chemin_sortie)
            messagebox.showinfo(
                "Export terminé",
                "Les graphiques ont bien été exportés."
            )
