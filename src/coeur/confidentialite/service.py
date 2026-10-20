"""Règles de protection des données appliquées avant tout enregistrement.

- Le numéro de téléphone n'est jamais stocké : seule son empreinte HMAC-SHA256
  (calculée avec une clé secrète, le « pepper ») est conservée. Elle permet de
  compter les usagers uniques sans pouvoir retrouver le numéro sans la clé.
- Dans les textes libres, les suites de chiffres longues (téléphone, pièce
  d'identité) et les adresses électroniques sont remplacées par « [masqué] ».
"""

import hashlib
import hmac
import re

INDICATIF_RDC = "243"
MASQUE = "[masqué]"

_COURRIEL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# Six chiffres ou plus, éventuellement séparés par des espaces, points ou tirets.
_SUITE_CHIFFRES = re.compile(r"\+?\d(?:[\s.\-]?\d){5,}")


def normaliser_telephone(numero: str) -> str:
    """Ramène un numéro au format international sans « + » (ex. 243812345678)."""
    brut = numero.strip()
    chiffres = re.sub(r"\D", "", brut)
    if brut.startswith("00"):
        chiffres = chiffres[2:]
    elif chiffres.startswith("0") and len(chiffres) == 10:
        chiffres = INDICATIF_RDC + chiffres[1:]
    elif len(chiffres) == 9:
        chiffres = INDICATIF_RDC + chiffres
    if not 11 <= len(chiffres) <= 15:
        raise ValueError("Numéro de téléphone invalide")
    return chiffres


def empreinte_telephone(numero: str, pepper: str) -> str:
    """Empreinte irréversible (sans la clé) d'un numéro, sur 64 caractères hexadécimaux."""
    return hmac.new(
        pepper.encode(), normaliser_telephone(numero).encode(), hashlib.sha256
    ).hexdigest()


def masquer_donnees_sensibles(texte: str) -> str:
    texte = _COURRIEL.sub(MASQUE, texte)
    return _SUITE_CHIFFRES.sub(MASQUE, texte)
