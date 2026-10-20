"""Postes d'agents : comptes SIP fixes (poste1, poste2…), comme des bureaux physiques.

Le mot de passe de chaque poste est dérivé de SECRET_POSTES, connu du cœur et
d'Asterisk (asterisk/synchro/configurer.py applique la même formule) : aucun
mot de passe n'est stocké, et changer le secret les renouvelle tous.
"""

import hashlib
import hmac


def postes(nombre: int) -> list[str]:
    return [f"poste{n}" for n in range(1, nombre + 1)]


def mot_de_passe_poste(secret: str, poste: str) -> str:
    return hmac.new(secret.encode(), poste.encode(), hashlib.sha256).hexdigest()[:32]
