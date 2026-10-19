FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml ./
COPY requirements.lock ./
COPY analyseur_documents ./analyseur_documents
COPY backend ./backend
RUN pip install --no-cache-dir -c requirements.lock . && useradd --create-home app && mkdir -p /app/var && chown app:app /app/var
COPY alembic.ini ./
COPY migrations ./migrations
USER app
EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
