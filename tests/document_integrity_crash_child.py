"""Subprocess-only crash fixture; never imported by the application."""
import io
import json
import os
from pathlib import Path
import sys
import threading
from uuid import UUID

# Direct script execution also works without installing the editable project.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import UploadFile
from sqlalchemy import event, select

from backend.config import Settings
from backend.db import make_engine, make_sessions
from backend.models import Document
from backend.services import documents


def main():
    settings = Settings(_env_file=None, **json.loads(Path(sys.argv[1]).read_text(encoding='utf-8')))
    stage = sys.argv[2]
    engine = make_engine(settings.database_url)
    original = engine.dialect.do_commit

    def die(*args, **kwargs):
        os._exit(73)

    def commit(connection):
        if stage in ('renamed', 'delete-uncommitted'):
            die()
        original(connection)
        die()

    engine.dialect.do_commit = commit
    if stage == 'part':
        documents.run_worker = die
    else:
        # Real parsing is tested separately in the sandbox suite. This child tests
        # abrupt lifecycle failures without spawning another worker interpreter.
        documents.run_worker = lambda *args: ['Fictitious source.']
    with make_sessions(engine)() as session:
        if stage.startswith('delete-'):
            documents.delete_document(session, settings, session.scalar(select(Document)))
        else:
            documents.import_document(session, settings,
                UploadFile(filename='synthetic.txt', file=io.BytesIO(b'Fictitious source.')),
                UUID(int=1), threading.Semaphore(1))
    raise AssertionError('Crash boundary not reached')


if __name__ == '__main__':
    main()
