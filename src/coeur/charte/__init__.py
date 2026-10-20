"""Identité visuelle : Charte graphique du Gouvernement de la RDC (Marque État Congolais, 2022).

Toutes les interfaces montrées aux utilisateurs (portail, espaces connectés, simulateur,
documentation de l'API, pages d'erreur, Directus) s'appuient sur ce module :

- `statique/charte.css` : couleurs, police Cooper Hewitt, bloc-marque, bandeaux, boutons ;
- `gabarits/_charte.html` : macros Jinja du bloc-marque, de l'en-tête de page et du pied ;
- `statique/` : armoiries (couleur et blanc), police, icône d'onglet, produites par
  outils/preparer_charte.py.

Le bloc-marque se compose, de gauche à droite (charte, p. 8 à 11) : les armoiries
« Le Gouvernement », la Ligne d'État (bleu, jaune, rouge à parts égales, de haut en bas)
et l'intitulé officiel de la structure émettrice.
"""

from pathlib import Path

from fastapi.templating import Jinja2Templates

DOSSIER = Path(__file__).parent
GABARITS = DOSSIER / "gabarits"
STATIQUE = DOSSIER / "statique"
CHEMIN = "/charte"

# Intitulé officiel, en Cooper Hewitt semi-gras. La première ligne est réservée à la
# nature de l'émetteur (charte, p. 15). À faire valider par l'INS.
INTITULE = ("Institut national", "de la statistique", "Bureau central du recensement")

# Couleurs de la charte (valeurs « Web » des p. 26 et 27).
COULEURS = {
    "etat_bleu": "#0095c9", "etat_jaune": "#fff24b", "etat_rouge": "#db3832",
    "bleu_institutionnel": "#17418a", "anthracite": "#323230", "argent": "#afb8be",
}
# Site officiel du recensement, cité dans les pieds de page.
SITE_OFFICIEL = "https://rgph.cd"


def gabarits(dossier: Path) -> Jinja2Templates:
    """Gabarits d'un module, avec accès aux composants de la charte (`_charte.html`)."""
    moteur = Jinja2Templates(directory=[dossier, GABARITS])
    moteur.env.globals.update(INTITULE=INTITULE, SITE_OFFICIEL=SITE_OFFICIEL)
    return moteur
