"""Reconcile local files against committed database records with the API stopped."""
import argparse
import re

from sqlalchemy import select

from .config import Settings
from .db import make_engine
from .models import Document

GENERATED = re.compile(r"^[0-9a-f]{32}\.(?:part|pdf|txt|pdf\.deleted|txt\.deleted)$")


def reconcile(settings, apply=False):
    engine = make_engine(settings.database_url)
    try:
        with engine.connect() as connection:
            referenced = set(connection.scalars(select(Document.storage_name)))
    finally:
        engine.dispose()
    root = settings.storage_dir.resolve()
    actions = []
    if not root.exists():
        return actions
    for path in sorted(root.iterdir()):
        if not path.is_file() or not GENERATED.fullmatch(path.name):
            continue
        original = path.name.removesuffix(".deleted")
        if path.name.endswith(".deleted") and original in referenced:
            destination = root / original
            if not destination.exists():
                actions.append(("restore", path.name))
                if apply:
                    path.replace(destination)
                continue
        if path.name not in referenced:
            actions.append(("delete", path.name))
            if apply:
                path.unlink()
    for name in sorted(referenced):
        if not (root / name).exists() and not (root / (name + ".deleted")).exists():
            actions.append(("missing", name))
    return actions


def main():
    parser = argparse.ArgumentParser(description="Maintenance API arrêtée uniquement ; simulation par défaut")
    parser.add_argument("--apply", action="store_true", help="Appliquer suppressions et restaurations")
    args = parser.parse_args()
    for action, name in reconcile(Settings(), args.apply):
        print(f"{action}: {name}")


if __name__ == "__main__":
    main()
