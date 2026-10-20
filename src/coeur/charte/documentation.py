"""Documentation interactive de l'API (/docs), aux couleurs de la charte.

Swagger UI est chargé comme le fait FastAPI ; on y ajoute le bandeau de la charte
(armoiries, Ligne d'État, intitulé), l'icône d'onglet et la police Cooper Hewitt.
"""

from functools import lru_cache

from fastapi import APIRouter, Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse

from coeur.charte import GABARITS, gabarits

routeur = APIRouter(include_in_schema=False)

BANDEAU = """{% import "_charte.html" as charte %}
<link rel="stylesheet" href="/charte/charte.css">
<link rel="stylesheet" href="/charte/documentation.css">
<header class="bandeau bandeau-bleu"><div class="bandeau-int">
  {{ charte.marque("/docs", blanc=true) }}
  <p class="espace">RGPH-2<span>Documentation de l'API</span></p>
</div></header>
"""


@lru_cache
def bandeau() -> str:
    return gabarits(GABARITS).env.from_string(BANDEAU).render()


@routeur.get("/docs")
def documentation(request: Request) -> HTMLResponse:
    page = get_swagger_ui_html(
        openapi_url=request.app.openapi_url,
        title=request.app.title,
        swagger_favicon_url="/charte/favicon.png",
        swagger_ui_parameters={"defaultModelsExpandDepth": -1},
    )
    return HTMLResponse(page.body.decode().replace("<body>", "<body>" + bandeau(), 1))
