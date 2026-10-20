"""Pages d'erreur aux couleurs de la charte, pour tout ce qu'un humain voit dans un navigateur.

L'API (/v1, /api) garde ses réponses JSON : ses clients sont des programmes.
"""

from fastapi import Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import Response
from starlette.exceptions import HTTPException

from coeur.charte import GABARITS, gabarits

PREFIXES_API = ("/v1/", "/api/", "/openapi.json")
TITRES = {
    401: "Accès refusé",
    403: "Accès refusé",
    404: "Page introuvable",
    429: "Trop de demandes",
    500: "Erreur du service",
    503: "Service momentanément indisponible",
}
EXPLICATIONS = {
    401: "Cette page demande une connexion.",
    403: "Votre compte n'a pas accès à cette page.",
    404: "L'adresse demandée n'existe pas ou n'existe plus.",
    429: "Vous avez envoyé trop de demandes en peu de temps. Patientez une minute puis réessayez.",
    500: "Une erreur inattendue s'est produite. Réessayez dans quelques instants.",
    503: "Le service est momentanément indisponible. Réessayez dans quelques instants.",
}

_gabarits = gabarits(GABARITS)


def pour_un_navigateur(request: Request) -> bool:
    return (not request.url.path.startswith(PREFIXES_API)
            and "text/html" in request.headers.get("accept", ""))


def page_erreur(request: Request, statut: int) -> Response:
    statut_affiche = statut if statut in TITRES else (500 if statut >= 500 else 404)
    return _gabarits.TemplateResponse(request, "erreur.html", {
        "statut": statut, "titre": TITRES[statut_affiche],
        "explication": EXPLICATIONS[statut_affiche],
    }, status_code=statut)


async def erreur_http(request: Request, exc: HTTPException) -> Response:
    if exc.status_code < 400 or not pour_un_navigateur(request):
        return await http_exception_handler(request, exc)
    return page_erreur(request, exc.status_code)


async def erreur_inattendue(request: Request, exc: Exception) -> Response:
    if not pour_un_navigateur(request):
        return Response("Erreur interne", status_code=500, media_type="text/plain")
    return page_erreur(request, 500)
