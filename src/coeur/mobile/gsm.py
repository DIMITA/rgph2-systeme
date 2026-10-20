"""Alphabet des SMS et de l'USSD (GSM 03.38).

Un caractère hors de cet alphabet (ê, î, ô, guillemets typographiques…) fait passer
tout le message en Unicode : un SMS ne contient alors plus que 70 caractères au lieu
de 160, et certains téléphones affichent mal l'USSD. On remplace donc ces caractères
par leur équivalent le plus proche avant tout envoi.
"""

import math
import unicodedata

# Alphabet de base (les caractères accentués qu'il contient sont conservés tels quels).
_GSM = set(
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
)
# Caractères de l'extension (comptent double).
_EXTENSION = set("^{}\\[~]|€")
_REMPLACEMENTS = {
    "«": '"', "»": '"', "“": '"', "”": '"', "’": "'", "‘": "'", "…": "...",
    "–": "-", "—": "-", " ": " ", " ": " ", "œ": "oe", "Œ": "OE",
}


def en_gsm(texte: str) -> str:
    resultat = []
    for c in texte:
        if c in _GSM or c in _EXTENSION:
            resultat.append(c)
        elif c in _REMPLACEMENTS:
            resultat.append(_REMPLACEMENTS[c])
        else:
            # ê → e, î → i, ô → o… ; tout autre caractère inconnu devient « ? ».
            base = unicodedata.normalize("NFD", c)[0]
            resultat.append(base if base in _GSM else "?")
    return "".join(resultat)


def longueur_gsm(texte: str) -> int:
    return sum(2 if c in _EXTENSION else 1 for c in texte)


def nb_segments(texte: str) -> int:
    """Nombre de SMS facturés : 160 caractères pour un seul, 153 par partie au-delà."""
    n = longueur_gsm(texte)
    return 1 if n <= 160 else math.ceil(n / 153)


def couper(texte: str, longueur: int) -> str:
    """Raccourcit un libellé à `longueur` caractères, avec « ... » s'il est coupé."""
    return texte if len(texte) <= longueur else texte[: longueur - 3].rstrip() + "..."
