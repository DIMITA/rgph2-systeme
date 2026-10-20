"""Assemblage de l'application : chaque module apporte son routeur."""

from pathlib import Path

from fastapi import Depends, FastAPI, status
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from coeur import charte
from coeur.badges.routes import routeur as badges
from coeur.base import session_db
from coeur.calendrier.routes import routeur as calendrier
from coeur.charte import documentation, erreurs
from coeur.centre_appels.routes import routeur as centre_appels
from coeur.tableau_de_bord.console import routeur as console_agents
from coeur.config import parametres
from coeur.connaissances.routes import routeur as connaissances
from coeur.journalisation import proteger_journal_acces
from coeur.portail.routes import routeur as portail
from coeur.portail.securite import entetes_securite
from coeur.signalements.routes import routeur as signalements
from coeur.simulateur.routes import routeur as simulateur
from coeur.sms.routes import routeur as sms
from coeur.statistiques.routes import routeur as statistiques
from coeur.terrain.routes import routeur as terrain
from coeur.tableau_de_bord.auth import CHEMIN as CHEMIN_TDB
from coeur.tableau_de_bord.auth import DUREE_SESSION
from coeur.tableau_de_bord.routes import routeur as tableau_de_bord
from coeur.tableau_de_bord.terrain import routeur as terrain_tableau_de_bord
from coeur.territoires.routes import routeur as territoires
from coeur.ussd.routes import routeur as ussd
from coeur.whatsapp.routes import routeur as whatsapp

app = FastAPI(
    title="API du RGPH-2 — INS · Bureau central du recensement",
    # Documentation servie par charte.documentation (aux couleurs de la charte).
    docs_url=None,
    redoc_url=None,
    description=(
        "API commune à tous les canaux (USSD/SMS, WhatsApp, web, kiosques, "
        "Ambassadeurs, centre d'écoute). Ne sert que des contenus validés par le BCR ; "
        "sinon, renvoie une escalade vers un humain."
    ),
    version="0.1.0",
)
# Ni numéro, ni texte de SMS, ni clé dans le journal d'accès.
proteger_journal_acces()
app.add_middleware(GZipMiddleware, minimum_size=500)
# Pages d'erreur aux couleurs de la charte (navigateurs) ; JSON inchangé pour l'API.
app.add_exception_handler(HTTPException, erreurs.erreur_http)
app.add_exception_handler(Exception, erreurs.erreur_inattendue)
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
# Charte graphique du Gouvernement : feuille de style, police, armoiries (toutes les interfaces).
app.mount(charte.CHEMIN, StaticFiles(directory=charte.STATIQUE), name="charte")
app.mount(
    "/statique",
    StaticFiles(directory=Path(__file__).parent / "portail" / "statique"),
    name="statique",
)
# Application hors ligne des kiosques et des Ambassadeurs (index.html servi sous /terrain/).
app.mount(
    "/terrain",
    StaticFiles(directory=Path(__file__).parent / "terrain" / "statique", html=True),
    name="terrain",
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


app.include_router(documentation.routeur)

# Le portail en dernier : ses adresses (/fr, /ln…) ne doivent masquer aucune route de l'API.
for routeur in (
    connaissances, signalements, statistiques, territoires, calendrier, badges, ussd, sms, whatsapp,
    terrain,
    centre_appels, tableau_de_bord, console_agents, terrain_tableau_de_bord, simulateur, portail,
):
    app.include_router(routeur)
