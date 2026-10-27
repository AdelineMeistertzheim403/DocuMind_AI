from uuid import UUID, uuid4

import fitz
import pytest
from sqlalchemy import func, select

from backend.models import Analysis, Document, DocumentChunk, DocumentPage
from tests.conftest import OTHER_KEY


def pdf_bytes(texts):
    with fitz.open() as pdf:
        for text in texts:
            page = pdf.new_page()
            page.insert_textbox(fitz.Rect(72, 72, 520, 760), text)
        return pdf.tobytes()


def upload(client, data, filename="document.txt", mime="application/octet-stream"):
    return client.post("/api/v1/documents", files={"file": (filename, data, mime)})


def test_txt_full_lifecycle(client, app):
    response = upload(client, "Docker utilise une API. Cette API retourne des documents.".encode())
    assert response.status_code == 201, response.text
    document = response.json()
    identifier = document["id"]
    assert "storage_name" not in document
    assert client.get("/api/v1/documents").json()["total"] == 1
    detail = client.get(f"/api/v1/documents/{identifier}").json()
    assert detail["pages"][0]["page_number"] == 1
    assert "Docker" in detail["pages"][0]["text"]
    assert client.get(f"/api/v1/documents/{identifier}/analysis").status_code == 404
    result = client.post(f"/api/v1/documents/{identifier}/analyze", json={"mode_memoire": False})
    assert result.status_code == 201, result.text
    stats = result.json()["result"]
    assert stats["nombre_mots"] == 9
    assert stats["nombre_phrases"] == 2
    assert {t["terme"]: t["occurrences"] for t in stats["termes_techniques"]}["API"] == 2
    assert client.get(f"/api/v1/documents/{identifier}/analysis").json()["id"] == result.json()["id"]
    again = client.post(f"/api/v1/documents/{identifier}/analyze")
    assert again.status_code == 201, again.text
    with app.state.sessions() as db:
        chunks = db.scalars(select(DocumentChunk)).all()
        assert len(chunks) == 1
        assert chunks[0].text == detail["pages"][0]["text"]
        assert chunks[0].start_char == 0
        assert chunks[0].end_char == len(chunks[0].text)
        assert db.scalar(select(func.count()).select_from(Analysis)) == 2
    assert client.delete(f"/api/v1/documents/{identifier}").status_code == 204
    assert client.get(f"/api/v1/documents/{identifier}").status_code == 404
    with app.state.sessions() as db:
        for model in (Document, DocumentPage, DocumentChunk, Analysis):
            assert db.scalar(select(func.count()).select_from(model)) == 0
    assert list(app.state.settings.storage_dir.iterdir()) == []


def test_pdf_pages_and_long_sentence_locations(client):
    texts = ["Docker provides an API.", " ".join(["document"] * 45) + "."]
    response = upload(client, pdf_bytes(texts), "document.PDF", "text/plain")
    assert response.status_code == 201, response.text
    identifier = response.json()["id"]
    pages = client.get(f"/api/v1/documents/{identifier}").json()["pages"]
    assert [page["page_number"] for page in pages] == [1, 2]
    assert "Docker" in pages[0]["text"]
    result = client.post(f"/api/v1/documents/{identifier}/analyze", json={"mode_memoire": False, "ignorer_titres": False}).json()["result"]
    assert result["phrases_longues"][0]["page"] == 2


@pytest.mark.parametrize("filename,data,status", [
    ("empty.txt", b"", 422), ("blank.txt", b" \n\t", 422),
    ("bad.pdf", b"%PDF-1.7\ninvalid", 422), ("fake.pdf", b"hello", 422),
    ("binary.txt", b"abc\x00xyz", 422), ("latin.txt", b"\xff\xfe", 422),
    ("fake.txt", b"%PDF-1.7\n", 422), ("program.exe", b"MZ", 415),
    ("image.txt", b"\x89PNG\r\n", 422),
])
def test_rejected_files_leave_no_data(client, app, filename, data, status):
    response = upload(client, data, filename)
    assert response.status_code == status, response.text
    assert client.get("/api/v1/documents").json()["total"] == 0
    assert list(app.state.settings.storage_dir.iterdir()) == []


def test_empty_and_encrypted_pdf(client):
    assert upload(client, pdf_bytes([""]), "blank.pdf").status_code == 422
    with fitz.open() as pdf:
        pdf.new_page().insert_text((72, 72), "Secret document.")
        encrypted = pdf.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="reader")
    assert upload(client, encrypted, "encrypted.pdf").status_code == 422


def test_size_limit(client, app):
    app.state.settings.max_upload_bytes = 20
    assert upload(client, b"x" * 21).status_code == 413
    # Global request bound also works without trusting Content-Length.
    assert client.post("/api/v1/documents", content=iter([b"a" * 70000] * 200)).status_code == 413
    assert not list(app.state.settings.storage_dir.iterdir())


def test_extraction_limits(client, app):
    app.state.settings.max_pdf_pages = 1
    assert upload(client, pdf_bytes(["First.", "Second."]), "many.pdf").status_code == 422
    app.state.settings.max_text_chars = 3
    assert upload(client, b"Too much text.").status_code == 422
    assert upload(client, pdf_bytes(["Too much text."]), "large.pdf").status_code == 422


def test_authentication_and_owner_isolation(client):
    response = upload(client, b"Private document.")
    identifier = response.json()["id"]
    client.headers.pop("X-API-Key")
    assert client.get("/api/v1/documents").status_code == 401
    assert upload(client, b"Private.").status_code == 401
    client.headers["X-API-Key"] = "invalid"
    assert client.get(f"/api/v1/documents/{identifier}").status_code == 401
    client.headers["X-API-Key"] = OTHER_KEY
    assert client.get("/api/v1/documents").json()["total"] == 0
    for method, suffix in [("get", ""), ("get", "/download"), ("delete", ""), ("post", "/analyze"), ("get", "/analysis")]:
        assert getattr(client, method)(f"/api/v1/documents/{identifier}{suffix}").status_code == 404


def test_original_download_is_owned_verified_and_does_not_expose_storage(client, app):
    source = b"Original document bytes.\n"
    key = client.headers["X-API-Key"]
    response = upload(client, source, "rapport final.txt")
    identifier = response.json()["id"]
    download = client.get(f"/api/v1/documents/{identifier}/download")
    assert download.status_code == 200
    assert download.content == source
    assert download.headers["content-type"].startswith("text/plain")
    assert download.headers["content-disposition"].endswith("filename*=UTF-8''rapport%20final.txt")
    assert "storage_name" not in download.text
    client.headers.pop("X-API-Key")
    assert client.get(f"/api/v1/documents/{identifier}/download").status_code == 401
    client.headers["X-API-Key"] = "invalid"
    assert client.get(f"/api/v1/documents/{identifier}/download").status_code == 401
    client.headers["X-API-Key"] = key
    path = next(app.state.settings.storage_dir.iterdir())
    path.unlink()
    unavailable = client.get(f"/api/v1/documents/{identifier}/download")
    assert unavailable.status_code == 409
    assert str(path) not in unavailable.text


def test_original_download_rejects_corrupted_source(client, app):
    response = upload(client, b"Original document bytes.", "source.txt")
    identifier = response.json()["id"]
    path = next(app.state.settings.storage_dir.iterdir())
    path.write_bytes(b"Modified source.")
    assert client.get(f"/api/v1/documents/{identifier}/download").status_code == 409


def test_original_download_rejects_unsafe_storage_identity(client, app):
    response = upload(client, b"Original document bytes.", "source.txt")
    identifier = response.json()["id"]
    with app.state.sessions() as db:
        db.get(Document, UUID(identifier)).storage_name = "../../outside.txt"
        db.commit()
    assert client.get(f"/api/v1/documents/{identifier}/download").status_code == 409


def test_http_validation_and_health(client):
    assert client.get("/api/v1/health").json() == {"status": "ok", "database": "ok"}
    assert client.get("/api/v1/documents/invalid").status_code == 422
    assert client.get(f"/api/v1/documents/{uuid4()}").status_code == 404
    assert client.get("/api/v1/documents?limit=101").status_code == 422
    assert client.post("/api/v1/documents").status_code == 422
    identifier = upload(client, b"An API document.").json()["id"]
    for options in ({"limite_phrase_longue": 0}, {"termes_techniques": ["a" * 101]}, {"unknown": True}):
        assert client.post(f"/api/v1/documents/{identifier}/analyze", json=options).status_code == 422
    assert client.get("/openapi.json").status_code == 200


def test_server_generated_filename(client, app):
    response = upload(client, b"A safe document.", "../../secret.txt")
    assert response.status_code == 201
    assert response.json()["filename"] == "secret.txt"
    files = list(app.state.settings.storage_dir.iterdir())
    assert len(files) == 1 and len(files[0].stem) == 32


def test_worker_busy(client, app):
    while app.state.slots.acquire(blocking=False):
        pass
    assert upload(client, b"A document.").status_code == 503
    assert not list(app.state.settings.storage_dir.iterdir())


def test_database_errors_are_sanitized(client, app, monkeypatch):
    from sqlalchemy.exc import OperationalError
    from backend.api import db

    class FailedSession:
        def execute(self, *args):
            raise OperationalError("internal query", {}, Exception("private connection details"))

    app.dependency_overrides[db] = lambda: FailedSession()
    response = client.get("/api/v1/health")
    assert response.status_code == 503
    assert response.json() == {"detail": "Base indisponible"}
    assert "private" not in response.text
    app.dependency_overrides.clear()
