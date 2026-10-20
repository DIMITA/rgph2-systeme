"""En-têtes de sécurité et de cache des pages du portail."""

from fastapi import Request

# La documentation de l'API (Swagger) charge ses scripts ailleurs : on ne la bride pas.
CHEMINS_EXCLUS = ("/docs", "/openapi.json")

POLITIQUE = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "media-src 'self' https:; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
)
# Application de terrain : télécharge l'audio des réponses (hébergé ailleurs) pour
# l'écoute hors ligne, depuis la page et depuis son service worker.
POLITIQUE_TERRAIN = POLITIQUE.replace("default-src 'self';", "default-src 'self'; connect-src 'self' https:;")


async def entetes_securite(request: Request, suivant):
    reponse = await suivant(request)
    chemin = request.url.path
    if not chemin.startswith(CHEMINS_EXCLUS):
        # Une page peut fixer sa propre politique (console des agents : WebSocket vers Asterisk).
        politique = POLITIQUE_TERRAIN if chemin.startswith("/terrain/") else POLITIQUE
        reponse.headers.setdefault("Content-Security-Policy", politique)
        reponse.headers["X-Content-Type-Options"] = "nosniff"
        reponse.headers["Referrer-Policy"] = "no-referrer"
        reponse.headers["X-Frame-Options"] = "DENY"
    if chemin.startswith("/statique/"):
        # Économise la bande passante en 2G : feuille de style et script gardés une journée.
        reponse.headers["Cache-Control"] = "public, max-age=86400"
    elif chemin.startswith("/terrain/"):
        # Revalidé à chaque fois : le service worker garde la copie hors ligne, et une
        # nouvelle version de l'application doit arriver dès la synchronisation suivante.
        reponse.headers["Cache-Control"] = "no-cache"
    elif chemin.startswith("/charte/"):
        # Police et armoiries ne changent presque jamais : un mois en cache.
        reponse.headers["Cache-Control"] = "public, max-age=2592000"
    return reponse
