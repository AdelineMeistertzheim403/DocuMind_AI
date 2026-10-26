FROM python:3.13-slim@sha256:d879ed88565a7a3c614b980b369d4a5025a9d057b71f93d09fc6d0b2ca823a18 AS dependencies
ENV PIP_INDEX_URL=https://pypi.org/simple PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
COPY requirements.build.lock requirements.runtime.lock ./
RUN python -m pip install --no-cache-dir --only-binary=:all: --require-hashes -r requirements.build.lock
COPY pyproject.toml ./
COPY analyseur_documents ./analyseur_documents
COPY backend ./backend
COPY documind_extractor ./documind_extractor
# This is a dedicated builder with its complete external PEP 517 tool closure.
RUN python -m pip wheel --no-cache-dir --no-build-isolation --check-build-dependencies --no-deps --wheel-dir /wheels . \
    && python -m pip install --no-cache-dir --only-binary=:all: --ignore-installed --prefix /runtime/usr/local --require-hashes -r requirements.runtime.lock \
    && python -m pip install --no-cache-dir --no-index --no-deps --ignore-installed --prefix /runtime/usr/local /wheels/documind_ai-0.1.0-py3-none-any.whl

FROM python:3.13-slim@sha256:d879ed88565a7a3c614b980b369d4a5025a9d057b71f93d09fc6d0b2ca823a18 AS application
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
# Already present in this verified base; no mutable apt-get update is needed.
RUN test "$(dpkg-query -W -f='${Version}' libseccomp2)" = '2.6.0-2'
COPY --from=dependencies /runtime/usr/local/ /usr/local/
COPY pyproject.toml ./
COPY requirements.lock ./
COPY analyseur_documents ./analyseur_documents
COPY backend ./backend
COPY documind_extractor ./documind_extractor
RUN useradd --create-home app && mkdir -p /app/var && chown app:app /app/var
COPY alembic.ini ./
COPY migrations ./migrations
USER app
EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

# Disposable proofs against the same Linux runtime. No tests enter the final image.
FROM application AS isolation-tests
USER root
COPY requirements.test.lock ./
RUN python -m pip install --no-cache-dir --index-url https://pypi.org/simple --only-binary=:all: --require-hashes -r requirements.test.lock
COPY tests ./tests
COPY compose.production.yaml ./compose.production.yaml
USER app
CMD ["python", "-m", "pytest", "-p", "no:cacheprovider", "tests/test_extraction_linux.py", "tests/test_extraction_protocol.py", "-q"]

FROM application AS production
