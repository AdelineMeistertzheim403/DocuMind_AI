"""Read-only document inventory. No repair, cleanup or output of private identities."""
import json

from backend.config import Settings
from backend.db import make_engine
from backend.services.document_integrity import check_document_integrity


def main():
    engine = None
    try:
        settings = Settings()
        engine = make_engine(settings.database_url)
        report = check_document_integrity(engine, settings.storage_dir)
    except Exception:
        # Config/DB errors can include secrets. Only a fixed aggregate is public.
        report = {'consistent': False, 'configuration_or_connection_error': True}
    finally:
        if engine is not None:
            engine.dispose()
    print(json.dumps(report, sort_keys=True))
    return 0 if report['consistent'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
