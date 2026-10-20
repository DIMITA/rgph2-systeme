# Service de transcription du RGPH-2 (messages vocaux → texte), sur processeur.
# Pour un serveur avec GPU NVIDIA : remplacer l'index « cpu » de PyTorch par « cu124 »
# et réserver le GPU dans docker-compose.yml (voir LISEZMOI.md).
# MOTEUR=omnilingual ajoute Meta Omnilingual ASR (fairseq2) ; à régler aussi à l'exécution.
FROM python:3.12-slim
ARG MOTEUR=mms

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HF_HOME=/modeles \
    FAIRSEQ2_CACHE_DIR=/modeles/fairseq2 MOTEUR=$MOTEUR
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libsndfile1 \
    && rm -rf /var/lib/apt/lists/*
COPY requirements*.txt /app/
RUN if [ "$MOTEUR" = omnilingual ]; then \
        apt-get update && apt-get install -y --no-install-recommends build-essential cmake zlib1g-dev \
        && pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu \
           -r /app/requirements.txt -r /app/requirements-omnilingual.txt \
        && apt-get purge -y build-essential cmake zlib1g-dev && apt-get autoremove -y \
        && rm -rf /var/lib/apt/lists/*; \
    else \
        pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu "torch>=2.4,<3" \
        && pip install --no-cache-dir -r /app/requirements.txt; \
    fi
COPY serveur.py /app/serveur.py
WORKDIR /app
RUN useradd --system --no-create-home rgph && mkdir -p /modeles && chown rgph /modeles
USER rgph

EXPOSE 9000
CMD ["uvicorn", "serveur:app_depuis_environnement", "--factory", "--host", "0.0.0.0", "--port", "9000"]
