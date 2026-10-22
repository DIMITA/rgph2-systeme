"""Espace « terrain » : enrôlement et révocation des kiosques et des téléphones d'Ambassadeurs.

Le code d'activation n'est affiché qu'une fois, dans la réponse qui le crée : il
n'est gardé qu'en empreinte et ne peut pas être réaffiché. Perdu, on en génère un
nouveau.
"""

from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from coeur.base import session_db
from coeur.config import Parametres, parametres
from coeur.connaissances.service import langues_actives
from coeur.tableau_de_bord.auth import CHEMIN, Utilisateur, exiger
from coeur.tableau_de_bord.routes import _libelles, _page
from coeur.terrain import service
from coeur.terrain.modeles import Appareil, RemonteeRecue
from coeur.territoires.service import lister as lister_territoires

routeur = APIRouter(prefix=CHEMIN, include_in_schema=False)
TERRAIN = exiger("terrain")
TYPES_APPAREIL = {"kiosque": "Kiosque OKAPI", "ambassadeur": "Ambassadeur"}
JOURS_REMONTEES = 30
# Au-delà, l'appareil est signalé : sa FAQ et son calendrier sont peut-être périmés.
JOURS_SANS_SYNCHRO = 7


def etat(appareil: Appareil) -> str:
    if appareil.revoque_a is not None:
        return "Révoqué"
    if appareil.jeton_empreinte is not None:
        return "Actif"
    if appareil.activation_expire_a and appareil.activation_expire_a > datetime.now(timezone.utc):
        return "En attente d'activation"
    return "Code expiré"


def _afficher(request: Request, session: Session, utilisateur: Utilisateur, statut: int = 200,
              **contexte):
    maintenant = datetime.now(timezone.utc)
    remontees = dict(session.execute(
        select(RemonteeRecue.appareil_id, func.count())
        .where(RemonteeRecue.recu_a >= maintenant - timedelta(days=JOURS_REMONTEES))
        .group_by(RemonteeRecue.appareil_id)
    ).all())
    return _page(
        request, "terrain.html", utilisateur, statut,
        appareils=service.lister(session), etat=etat, remontees=remontees,
        types=TYPES_APPAREIL, provinces=lister_territoires(session), noms=_libelles(session),
        langues=[l for l in langues_actives(session) if l.code != "fr"],
        perime=maintenant - timedelta(days=JOURS_SANS_SYNCHRO),
        jours_remontees=JOURS_REMONTEES, **contexte,
    )


@routeur.get("/terrain")
def page_terrain(request: Request, utilisateur: Utilisateur = Depends(TERRAIN),
                 session: Session = Depends(session_db)):
    return _afficher(request, session, utilisateur, saisie={})


@routeur.post("/terrain")
def creer_appareil(
    request: Request,
    type: Literal["kiosque", "ambassadeur"] = Form(),
    code: str = Form(default=""),
    territoire_code: str = Form(default=""),
    lieu: str = Form(default=""),
    langues: list[str] = Form(default=[]),
    utilisateur: Utilisateur = Depends(TERRAIN),
    session: Session = Depends(session_db),
    reglages: Parametres = Depends(parametres),
):
    actives = {l.code for l in langues_actives(session)}
    try:
        appareil, activation = service.creer(
            session, type_=type, code=code, territoire_code=territoire_code,
            langues=[l for l in langues if l in actives],
            lieu=lieu if type == "kiosque" else None,
            jours_activation=reglages.terrain_activation_jours)
    except ValueError as erreur:
        return _afficher(request, session, utilisateur, 422, erreur=str(erreur),
                         saisie={"type": type, "code": code, "territoire_code": territoire_code,
                                 "lieu": lieu, "langues": langues})
    return _afficher(request, session, utilisateur, saisie={},
                     activation={"code": appareil.code, "valeur": activation,
                                 "jours": reglages.terrain_activation_jours})


def _appareil(session: Session, appareil_id: int) -> Appareil:
    appareil = session.get(Appareil, appareil_id)
    if appareil is None:
        raise HTTPException(404, "Appareil introuvable")
    return appareil


@routeur.post("/terrain/{appareil_id}/code")
def nouveau_code(
    request: Request,
    appareil_id: int,
    utilisateur: Utilisateur = Depends(TERRAIN),
    session: Session = Depends(session_db),
    reglages: Parametres = Depends(parametres),
):
    """Tablette remplacée ou application réinstallée : l'ancien jeton cesse de fonctionner."""
    appareil = _appareil(session, appareil_id)
    activation = service.reactiver(session, appareil, reglages.terrain_activation_jours)
    return _afficher(request, session, utilisateur, saisie={},
                     activation={"code": appareil.code, "valeur": activation,
                                 "jours": reglages.terrain_activation_jours})


@routeur.post("/terrain/{appareil_id}/revoquer")
def revoquer(
    request: Request,
    appareil_id: int,
    utilisateur: Utilisateur = Depends(TERRAIN),
    session: Session = Depends(session_db),
):
    appareil = _appareil(session, appareil_id)
    service.revoquer(session, appareil)
    return _afficher(request, session, utilisateur, saisie={},
                     message=f"{appareil.code} est révoqué : il ne peut plus se synchroniser.")
