FROM python:3.13-slim AS application
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libseccomp2 && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml ./
COPY requirements.lock ./
COPY analyseur_documents ./analyseur_documents
COPY backend ./backend
COPY documind_extractor ./documind_extractor
RUN pip install --no-cache-dir -c requirements.lock . && useradd --create-home app && mkdir -p /app/var && chown app:app /app/var
COPY alembic.ini ./
COPY migrations ./migrations
USER app
EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

# Disposable proofs against the same Linux runtime. No tests enter the final image.
FROM application AS isolation-tests
USER root
RUN pip install --no-cache-dir -c requirements.lock pytest httpx
COPY tests ./tests
COPY compose.production.yaml ./compose.production.yaml
USER app
CMD ["python", "-m", "pytest", "-p", "no:cacheprovider", "tests/test_extraction_linux.py", "tests/test_extraction_protocol.py", "-q"]

FROM application AS production
