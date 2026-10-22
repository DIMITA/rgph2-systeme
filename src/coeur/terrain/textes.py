"""Textes de l'application de terrain, un fichier JSON par langue dans `textes/`.

Comme pour le portail, une clé absente d'une langue est reprise du français. Les
textes partent dans le paquet : l'appareil les a hors ligne.
"""

import json
from functools import lru_cache
from pathlib import Path

DOSSIER = Path(__file__).parent / "textes"
LANGUE_DE_BASE = "fr"


@lru_cache
def _fichier(langue: str) -> dict[str, str]:
    chemin = DOSSIER / f"{langue}.json"
    if not chemin.is_file():
        return {}
    return json.loads(chemin.read_text(encoding="utf-8"))


def textes(langue: str) -> dict[str, str]:
    return {**_fichier(LANGUE_DE_BASE), **_fichier(langue)}
