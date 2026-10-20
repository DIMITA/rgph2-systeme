"""Webhook de Meta : vérification de l'abonnement (GET) et notifications (POST).

Meta n'utilise pas nos clés d'API : l'authenticité de chaque notification est
prouvée par sa signature (X-Hub-Signature-256), calculée avec le secret de l'app.
"""

import hmac
import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from coeur.base import session_db
from coeur.config import Parametres, parametres
from coeur.connaissances.depot import Corpus
from coeur.connaissances.routes import corpus_courant
from coeur.whatsapp import service

routeur = APIRouter(prefix="/v1/whatsapp", tags=["WhatsApp"])


@routeur.get("/webhook", response_class=PlainTextResponse)
def verifier_abonnement(
    mode: str = Query(alias="hub.mode"),
    jeton: str = Query(alias="hub.verify_token"),
    defi: str = Query(alias="hub.challenge", max_length=100),
    reglages: Parametres = Depends(parametres),
):
    """Appelé une fois par Meta à l'abonnement du webhook : renvoyer le défi."""
    attendu = reglages.whatsapp_jeton_verification
    if mode != "subscribe" or not attendu or not hmac.compare_digest(jeton, attendu):
        raise HTTPException(403, "Jeton de vérification invalide")
    return defi


@routeur.post("/webhook")
async def notification(
    request: Request,
    taches: BackgroundTasks,
    session: Session = Depends(session_db),
    corpus: Corpus = Depends(corpus_courant),
    reglages: Parametres = Depends(parametres),
) -> dict:
    """Messages reçus par le numéro WhatsApp. Toute notification non signée est refusée."""
    corps = await request.body()
    if not service.signature_valide(corps, request.headers.get("X-Hub-Signature-256"),
                                    reglages.whatsapp_secret_app):
        raise HTTPException(401, "Signature invalide")
    try:
        contenu = json.loads(corps)
    except ValueError as erreur:
        raise HTTPException(400, "Corps illisible") from erreur
    # Le traitement (base, envoi à Meta) bloque : hors de la boucle asynchrone.
    traites = await run_in_threadpool(service.recevoir, session, corpus, reglages, contenu,
                                      taches.add_task)
    return {"traites": traites}
