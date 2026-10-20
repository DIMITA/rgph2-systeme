"""Messages vocaux du centre d'appels.

Chaque message doit être enregistré par un locuteur natif dans chaque langue et
déposé dans asterisk/messages/<langue>/<nom>.wav (ou .mp3, .ogg, .m4a).
En attendant, une voix de synthèse française provisoire est générée (espeak-ng).
La liste ci-dessous est aussi le script d'enregistrement : voir messages/LISEZMOI.md.
"""

PHRASES = {
    "accueil": "Bienvenue au centre d'écoute du recensement général de la population. "
               "Cet appel peut être enregistré pour améliorer la qualité du service.",
    "svi_intro": "Pour écouter une réponse, tapez son numéro. "
                 "Pour parler à un conseiller, tapez zéro.",
    **{f"touche_{n}": f"Tapez {n} pour :" for n in range(1, 9)},
    "aucune_reponse_langue": "Un conseiller va vous répondre. Merci de rester en ligne.",
    "choix_invalide": "Choix non valide.",
    "attente": "Tous nos conseillers sont occupés. Merci de patienter.",
    "hors_service": "Aucun conseiller n'est disponible pour le moment.",
    "rappel_propose": "Pour être rappelé gratuitement par un conseiller, tapez 1. "
                      "Pour patienter encore, tapez 2.",
    "rappel_confirme": "Votre demande est enregistrée. Un conseiller vous rappellera "
                       "dès que possible. Au revoir.",
    "rappel_impossible": "Votre numéro n'est pas visible : nous ne pouvons pas vous rappeler.",
    "au_revoir": "Merci de votre appel. Au revoir.",
}

# Annonce de chaque langue dans le menu de choix : enregistrée dans la langue elle-même,
# avec sa touche (voir SVI_TOUCHES_LANGUES).
NOMS_LANGUES = {
    "fr": "le français", "ln": "le lingala", "sw": "le kiswahili",
    "kg": "le kikongo", "lua": "le tshiluba",
}


def phrase_choix_langue(code: str, touche: int) -> str:
    return f"Pour {NOMS_LANGUES.get(code, code)}, tapez {touche}."


def touches_langues(texte: str) -> dict[str, int]:
    """« fr:1,ln:2 » → {"fr": 1, "ln": 2} (même format que dans le cœur)."""
    resultat = {}
    for paire in filter(None, (p.strip() for p in texte.split(","))):
        code, _, touche = paire.partition(":")
        resultat[code.strip()] = int(touche)
    return resultat
