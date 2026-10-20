"""En-têtes de sécurité et de cache des pages du portail."""

from fastapi import Request

# La documentation de l'API (Swagger) charge ses scripts ailleurs : on ne la bride pas.
CHEMINS_EXCLUS = ("/docs", "/redoc", "/openapi.json")

POLITIQUE = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "media-src 'self' https:; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
)


async def entetes_securite(request: Request, suivant):
    reponse = await suivant(request)
    chemin = request.url.path
    if not chemin.startswith(CHEMINS_EXCLUS):
        reponse.headers["Content-Security-Policy"] = POLITIQUE
        reponse.headers["X-Content-Type-Options"] = "nosniff"
        reponse.headers["Referrer-Policy"] = "no-referrer"
        reponse.headers["X-Frame-Options"] = "DENY"
    if chemin.startswith("/statique/"):
        # Économise la bande passante en 2G : feuille de style et script gardés une journée.
        reponse.headers["Cache-Control"] = "public, max-age=86400"
    return reponse
