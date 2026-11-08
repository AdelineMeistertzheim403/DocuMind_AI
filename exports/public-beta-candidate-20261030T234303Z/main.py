import customtkinter as ctk
from analyseur_documents.ui.interface import AnalyseurApp


def main():
    root = ctk.CTk()
    app = AnalyseurApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
