"""Assemblage de l'application : chaque module apporte son routeur."""

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from coeur.base import session_db
from coeur.connaissances.routes import routeur as connaissances
from coeur.signalements.routes import routeur as signalements
from coeur.statistiques.routes import routeur as statistiques
from coeur.territoires.routes import routeur as territoires

app = FastAPI(
    title="RGPH-2 — Cœur",
    description=(
        "API commune à tous les canaux (USSD/SMS, WhatsApp, web, kiosques, "
        "Ambassadeurs, centre d'écoute). Ne sert que des contenus validés par le BCR ; "
        "sinon, renvoie une escalade vers un humain."
    ),
    version="0.1.0",
)
for routeur in (connaissances, signalements, statistiques, territoires):
    app.include_router(routeur)


@app.get("/sante", tags=["exploitation"])
def sante(session: Session = Depends(session_db)) -> dict[str, str]:
    try:
        session.execute(text("SELECT 1"))
    except Exception as erreur:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Base indisponible") from erreur
    return {"statut": "ok"}
