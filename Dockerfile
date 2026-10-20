FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

COPY alembic.ini ./
COPY migrations ./migrations
COPY outils ./outils
COPY donnees ./donnees

# Groupe partagé avec Asterisk (gid 1500) : l'API peut purger les enregistrements.
RUN groupadd --gid 1500 rgph-media \
    && useradd --system --no-create-home --groups rgph-media rgph \
    && mkdir -p /donnees/enregistrements
USER rgph

EXPOSE 8000
CMD ["uvicorn", "coeur.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
