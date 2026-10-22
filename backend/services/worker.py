"""Bounded extraction and legacy analysis in disposable child processes."""
import json
import multiprocessing
import os
import time

import psutil
from fastapi import HTTPException


def extract(path, extension, max_pages, max_chars):
    # Portable development adapter only; production never sends a path to a parser.
    from documind_extractor.engine import extract as extract_bytes
    with open(path, 'rb') as source:
        data = source.read()
    try:
        return extract_bytes(data, extension, max_pages, max_chars)
    except Exception:
        raise ValueError('Document illisible ou non conforme') from None


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
    except (ValueError, MemoryError):
        connection.send_bytes(json.dumps({"error": "Document illisible ou limite de traitement atteinte"}).encode())
    except Exception:
        connection.send_bytes(json.dumps({"error": "Le traitement du document a échoué", "worker_failed": True}).encode())
    finally:
        connection.close()


def run_worker(settings, operation, *args):
    if operation == 'extract' and settings.extraction_mode == 'sandbox':
        from .extraction import extract_isolated
        return extract_isolated(settings, *args)
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
            if payload.get('worker_failed'):
                from ..security_audit import mark
                mark('system.worker.failed', 'worker_failed')
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
