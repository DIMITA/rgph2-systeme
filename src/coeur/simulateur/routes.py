"""Simulateur de téléphone basique (USSD et SMS), pour les tests et les démonstrations.

N'existe que si SIMULATEUR_MOBILE=true, et jamais en production. Il appelle
directement les services du cœur, comme le ferait la passerelle de l'opérateur :
les échanges sont donc comptés et journalisés comme de vrais échanges.
"""

import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy.orm import Session

from coeur import charte
from coeur.base import session_db
from coeur.config import Parametres, parametres
from coeur.connaissances.depot import Corpus
from coeur.connaissances.routes import corpus_courant
from coeur.sms import service as sms
from coeur.ussd import service as ussd

routeur = APIRouter(prefix="/simulateur", include_in_schema=False)
gabarits = charte.gabarits(Path(__file__).parent / "gabarits")
NUMERO_EXEMPLE = "0810000000"


def actif(reglages: Parametres = Depends(parametres)) -> Parametres:
    if not reglages.simulateur_mobile or reglages.environnement == "production":
        raise HTTPException(404)
    return reglages


def _page(request: Request, reglages: Parametres, **contexte):
    return gabarits.TemplateResponse(request, "simulateur.html", {
        "numero": NUMERO_EXEMPLE, "code": reglages.ussd_code or "*xxx#", **contexte})


@routeur.get("")
def simulateur(request: Request, reglages: Parametres = Depends(actif)):
    return _page(request, reglages)


@routeur.post("/ussd")
def simuler_ussd(
    request: Request,
    numero: str = Form(max_length=20),
    session_ussd: str = Form(default=""),
    historique: str = Form(default="", max_length=500),
    saisie: str = Form(default="", max_length=100),
    session: Session = Depends(session_db),
    corpus: Corpus = Depends(corpus_courant),
    reglages: Parametres = Depends(actif),
):
    """Sans session : compose le code. Sinon : envoie la saisie à la suite de l'historique."""
    if not session_ussd:
        session_ussd, historique = "simulateur-" + secrets.token_hex(6), ""
    else:
        historique = f"{historique}*{saisie}" if historique else saisie
    ecran = ussd.traiter(session, corpus, reglages, session_id=session_ussd,
                         telephone=numero, texte=historique)
    return _page(request, reglages, numero=numero, ecran=ecran, session_ussd=session_ussd,
                 historique=historique)


@routeur.post("/sms")
def simuler_sms(
    request: Request,
    numero: str = Form(max_length=20),
    message: str = Form(max_length=480),
    session: Session = Depends(session_db),
    corpus: Corpus = Depends(corpus_courant),
    reglages: Parametres = Depends(actif),
):
    reponse, envoi = sms.recevoir(session, corpus, reglages, numero, message)
    return _page(request, reglages, numero=numero, sms_envoye=message, sms_reponse=reponse,
                 sms_statut=envoi)
