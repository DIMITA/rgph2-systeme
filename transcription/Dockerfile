# Service de transcription du RGPH-2 (messages vocaux → texte), sur processeur.
# Pour un serveur avec GPU NVIDIA : remplacer l'index « cpu » de PyTorch par « cu124 »
# et réserver le GPU dans docker-compose.yml (voir LISEZMOI.md).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HF_HOME=/modeles
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu "torch>=2.4,<3" \
    && pip install --no-cache-dir -r /app/requirements.txt
COPY serveur.py /app/serveur.py
WORKDIR /app
RUN useradd --system --no-create-home rgph && mkdir -p /modeles && chown rgph /modeles
USER rgph

EXPOSE 9000
CMD ["uvicorn", "serveur:app_depuis_environnement", "--factory", "--host", "0.0.0.0", "--port", "9000"]
