"""Assemblage de l'application : chaque module apporte son routeur."""

from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from coeur.base import session_db
from coeur.connaissances.routes import routeur as connaissances
from coeur.portail.routes import routeur as portail
from coeur.portail.securite import entetes_securite
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
app.add_middleware(GZipMiddleware, minimum_size=500)
app.middleware("http")(entetes_securite)
app.mount(
    "/statique",
    StaticFiles(directory=Path(__file__).parent / "portail" / "statique"),
    name="statique",
)


@app.get("/sante", tags=["exploitation"])
def sante(session: Session = Depends(session_db)) -> dict[str, str]:
    try:
        session.execute(text("SELECT 1"))
    except Exception as erreur:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Base indisponible") from erreur
    return {"statut": "ok"}


# Le portail en dernier : ses adresses (/fr, /ln…) ne doivent masquer aucune route de l'API.
for routeur in (connaissances, signalements, statistiques, territoires, portail):
    app.include_router(routeur)
