import sys
import tempfile
import tkinter as tk
from pathlib import Path

import customtkinter as ctk

try:
    from PIL import Image
except ImportError:
    Image = None


def configurer_icone_application(root, dossier_application):
    chemin_icone = Path(dossier_application) / "icone.png"

    if not chemin_icone.exists():
        return None, None

    chemin_icone_temporaire = None

    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "AnalyseurDocuments.App"
            )
        except Exception:
            pass

    try:
        if Image is not None:
            image_icone = Image.open(chemin_icone)
            chemin_ico = Path(tempfile.gettempdir()) / "analyseur_documents_icone.ico"
            image_icone.save(
                chemin_ico,
                format="ICO",
                sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
            )
            chemin_icone_temporaire = chemin_ico
            root.iconbitmap(default=str(chemin_ico))
    except Exception:
        chemin_icone_temporaire = None

    icone_application = None
    try:
        icone_application = tk.PhotoImage(file=str(chemin_icone))
        root.iconphoto(True, icone_application)
    except tk.TclError:
        if chemin_icone_temporaire is None:
            icone_application = None

    return icone_application, chemin_icone_temporaire


def charger_logo_interface(dossier_application, taille=(58, 58)):
    if Image is None:
        return None

    chemin_logo = Path(dossier_application) / "logo.png"

    if not chemin_logo.exists():
        return None

    try:
        image_logo = Image.open(chemin_logo)
        return ctk.CTkImage(
            light_image=image_logo,
            dark_image=image_logo,
            size=taille
        )
    except Exception:
        return None
