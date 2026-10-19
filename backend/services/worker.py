"""Bounded extraction and legacy analysis in disposable child processes."""
import json
import multiprocessing
import os
import time

import psutil
from fastapi import HTTPException


def extract(path, extension, max_pages, max_chars):
    import pymupdf as fitz

    if extension == ".txt":
        with open(path, "rb") as stream:
            data = stream.read()
        if data.startswith((b"%PDF-", b"PK\x03\x04", b"MZ", b"\x89PNG", b"\xff\xd8\xff")):
            raise ValueError("Le contenu ne correspond pas à un fichier TXT")
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("TXT UTF-8 requis") from exc
        if any(ord(c) < 32 and c not in "\n\r\t\f" for c in text):
            raise ValueError("Contenu binaire interdit")
        pages = [text]
    else:
        with open(path, "rb") as stream:
            if not stream.read(8).startswith(b"%PDF-"):
                raise ValueError("Signature PDF invalide")
        try:
            with fitz.open(path, filetype="pdf") as document:
                if not document.is_pdf or document.needs_pass or document.is_repaired:
                    raise ValueError("PDF corrompu ou chiffré")
                if not 0 < document.page_count <= max_pages:
                    raise ValueError("Limite du nombre de pages dépassée")
                pages = []
                total = 0
                for page in document:
                    text = page.get_text("text", sort=True)
                    total += len(text)
                    if total > max_chars:
                        raise ValueError("Limite de texte extrait dépassée")
                    pages.append(text)
        except (fitz.FileDataError, fitz.EmptyFileError, RuntimeError) as exc:
            raise ValueError("PDF illisible") from exc
    if sum(map(len, pages)) > max_chars:
        raise ValueError("Limite de texte extrait dépassée")
    if not any(text.strip() for text in pages):
        raise ValueError("Document vide ou sans texte extractible (OCR non disponible)")
    return pages


def analyze(pages, options):
    from analyseur_documents.core.analyseur import analyser_texte

    # Neutralize uploaded marker syntax before inserting trusted physical page numbers.
    import re
    marked = "\n".join(
        f"@@PAGE:{number}@@ @@PDFPAGE:{number}@@ {line}"
        for number, text in enumerate(pages, 1)
        for line in re.sub(r"@@(?:PDF)?PAGE:\d+@@", "", text).splitlines()
    )
    return analyser_texte(marked, **options)


def child(connection, operation, args, memory_mb, timeout):
    try:
        if os.name == "posix":
            import resource
            memory = memory_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
            cpu = max(1, int(timeout) + 1)
            resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
        result = {"extract": extract, "analyze": analyze}[operation](*args)
        connection.send_bytes(json.dumps({"result": result}).encode())
    except (ValueError, MemoryError) as exc:
        connection.send_bytes(json.dumps({"error": str(exc) or "Limite mémoire dépassée"}).encode())
    finally:
        connection.close()


def run_worker(settings, operation, *args):
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=child, args=(sender, operation, args, settings.worker_memory_mb, settings.worker_timeout_seconds))
    process.start()
    sender.close()
    deadline = time.monotonic() + settings.worker_timeout_seconds
    try:
        monitored = psutil.Process(process.pid)
        while not receiver.poll(0.02):
            if time.monotonic() >= deadline:
                raise HTTPException(422, "Délai de traitement dépassé")
            try:
                if monitored.memory_info().rss > settings.worker_memory_mb * 1024 * 1024:
                    raise HTTPException(422, "Limite mémoire dépassée")
            except psutil.NoSuchProcess:
                pass
            if not process.is_alive() and not receiver.poll():
                raise HTTPException(422, "Le traitement du document a échoué")
        try:
            payload = json.loads(receiver.recv_bytes())
        except EOFError as exc:
            raise HTTPException(422, "Le traitement du document a échoué") from exc
        if "error" in payload:
            raise HTTPException(422, payload["error"])
        return payload["result"]
    finally:
        receiver.close()
        if process.is_alive():
            process.terminate()
        process.join(timeout=2)
        if process.is_alive():
            process.kill()
            process.join()
