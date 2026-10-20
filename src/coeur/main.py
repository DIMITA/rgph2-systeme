"""Assemblage de l'application : chaque module apporte son routeur."""

from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from coeur.base import session_db
from coeur.centre_appels.routes import routeur as centre_appels
from coeur.config import parametres
from coeur.connaissances.routes import routeur as connaissances
from coeur.portail.routes import routeur as portail
from coeur.portail.securite import entetes_securite
from coeur.signalements.routes import routeur as signalements
from coeur.statistiques.routes import routeur as statistiques
from coeur.tableau_de_bord.auth import CHEMIN as CHEMIN_TDB
from coeur.tableau_de_bord.auth import DUREE_SESSION
from coeur.tableau_de_bord.routes import routeur as tableau_de_bord
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
# Session du tableau de bord : cookie signé, limité à son chemin (le portail n'en pose aucun).
app.add_middleware(
    SessionMiddleware,
    secret_key=parametres().secret_session,
    session_cookie="rgph_tableau_de_bord",
    max_age=DUREE_SESSION,
    path=CHEMIN_TDB,
    same_site="strict",
    https_only=parametres().session_https_seulement,
)
app.middleware("http")(entetes_securite)
app.mount(
    "/statique",
    StaticFiles(directory=Path(__file__).parent / "portail" / "statique"),
    name="statique",
)
app.mount(
    f"{CHEMIN_TDB}/statique",
    StaticFiles(directory=Path(__file__).parent / "tableau_de_bord" / "statique"),
    name="statique_tableau_de_bord",
)


@app.get("/sante", tags=["exploitation"])
def sante(session: Session = Depends(session_db)) -> dict[str, str]:
    try:
        session.execute(text("SELECT 1"))
    except Exception as erreur:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Base indisponible") from erreur
    return {"statut": "ok"}


# Le portail en dernier : ses adresses (/fr, /ln…) ne doivent masquer aucune route de l'API.
for routeur in (
    connaissances, signalements, statistiques, territoires, centre_appels, tableau_de_bord, portail,
):
    app.include_router(routeur)
