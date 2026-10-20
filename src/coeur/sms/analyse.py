"""Lecture des SMS reçus : mot-clé éventuel, territoire désigné par son nom ou son code."""

import re
import unicodedata
from dataclasses import dataclass

# Mot-clé (sans accents, tirets ni espaces) → commande.
MOTS_CLES = {
    "AIDE": "aide", "MENU": "aide", "INFO": "aide",
    "AGENT": "agent", "BADGE": "agent",
    "PASSAGE": "passage", "CALENDRIER": "passage",
    "NONVISITE": "non_visite", "NONRECENSE": "non_visite",
    "FAUXAGENT": "faux_agent",
    "RAPPEL": "rappel", "CONSEILLER": "rappel",
    "LANGUE": "langue",
}


def normaliser(texte: str) -> str:
    """Majuscules sans accents, tirets et apostrophes changés en espaces."""
    sans_accents = "".join(c for c in unicodedata.normalize("NFD", texte)
                           if unicodedata.category(c) != "Mn")
    return " ".join(re.sub(r"[-'’_.,;:]", " ", sans_accents).upper().split())


@dataclass(frozen=True)
class Commande:
    # None : pas de mot-clé, le message est une question pour la base de connaissances.
    nom: str | None
    mots: list[str]


def analyser(texte: str) -> Commande:
    mots = texte.split()
    if not mots:
        return Commande("aide", [])
    # Un ou deux premiers mots (« NON VISITE », « FAUX-AGENT »).
    for n in (2, 1):
        cle = normaliser("".join(mots[:n])).replace(" ", "")
        if cle in MOTS_CLES and len(mots) >= n:
            return Commande(MOTS_CLES[cle], mots[n:])
    return Commande(None, mots)


def _variantes(nom: str, code: str) -> set[str]:
    nom_n = normaliser(nom)
    variantes = {nom_n, normaliser(code)}
    if nom_n.startswith("VILLE DE "):
        variantes.add(nom_n.removeprefix("VILLE DE "))
    return variantes


def trouver_territoire(territoires: list[tuple[str, str]], mots: list[str],
                       max_mots: int = 4) -> tuple[list[str], list[str]]:
    """Territoire désigné par les premiers mots (le plus long nom reconnu).

    `territoires` : liste de (code, nom). Renvoie (codes reconnus, mots restants) ;
    plusieurs codes si le nom est ambigu (ex. une ville et un territoire homonymes).
    """
    index: dict[str, list[str]] = {}
    for code, nom in territoires:
        for variante in _variantes(nom, code):
            index.setdefault(variante, []).append(code)
    for n in range(min(max_mots, len(mots)), 0, -1):
        codes = index.get(normaliser(" ".join(mots[:n])))
        if codes:
            return sorted(set(codes)), mots[n:]
    return [], mots
