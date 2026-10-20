"""Prépare les ressources de la charte graphique du Gouvernement (Marque État Congolais).

Produit, dans src/coeur/charte/statique/ :
  - les armoiries « Le Gouvernement » en couleur (fond clair) et en blanc (fond bleu),
    aux tailles affichées et en double résolution, plus l'icône d'onglet ;
  - les icônes de l'application de terrain (192 et 512 px) ;
  - la police Cooper Hewitt (Medium et Semibold) réduite aux caractères utiles,
    au format woff2 : environ 20 Ko par graisse au lieu de 60.

Sources (à télécharger, non versionnées sauf les armoiries) :
  - armoiries : charte/sources/armoiries-gouvernement.png (CC0, Gouvernement de la RDC,
    https://commons.wikimedia.org/wiki/File:Armoiri_de_la_RDC_-_Le_Gouvernement.png) ;
  - police : https://www.cooperhewitt.org/wp-content/uploads/fonts/CooperHewitt-OTF-public.zip
    (licence SIL OFL 1.1).

Usage : pip install fonttools brotli pillow
        python outils/preparer_charte.py <dossier des .otf de Cooper Hewitt>
"""

import sys
from pathlib import Path

from fontTools import subset
from PIL import Image

RACINE = Path(__file__).resolve().parents[1]
CHARTE = RACINE / "src" / "coeur" / "charte"
SORTIE = CHARTE / "statique"
SOURCE_ARMOIRIES = CHARTE / "sources" / "armoiries-gouvernement.png"

# Latin de base et Latin-1 (français, accents), Latin étendu A, lettres ouvertes ɛ ɔ Ɛ Ɔ
# de l'orthographe du lingala et du tshiluba, ponctuation typographique, euro.
CARACTERES = ("U+0020-007E,U+00A0-00FF,U+0100-017F,U+0186,U+0190,U+0254,U+025B,"
              "U+2010-2014,U+2018-201E,U+2026,U+2039,U+203A,U+20AC,U+202F")
GRAISSES = {"Medium": "cooper-hewitt-medium", "Semibold": "cooper-hewitt-semibold"}
# Hauteur affichée des armoiries (px CSS) : accueil, autres pages. La charte impose
# 53 px au moins pour la Ligne d'État à l'écran, et elle a la hauteur des armoiries.
TAILLES = (64, 54)


def polices(dossier: Path) -> None:
    for graisse, nom in GRAISSES.items():
        options = subset.Options()
        options.flavor = "woff2"
        options.layout_features = ["kern", "liga", "case"]
        options.name_IDs = ["*"]  # garder le copyright et la licence dans le fichier
        police = subset.load_font(str(dossier / f"CooperHewitt-{graisse}.otf"), options)
        sous_ensemble = subset.Subsetter(options)
        sous_ensemble.populate(unicodes=subset.parse_unicodes(CARACTERES))
        sous_ensemble.subset(police)
        cible = SORTIE / f"{nom}.woff2"
        subset.save_font(police, str(cible), options)
        print(f"{cible.name} : {cible.stat().st_size // 1024} Ko")


def en_blanc(image: Image.Image) -> Image.Image:
    """Version monochrome blanche (la charte interdit les armoiries en couleur sur fond sombre)."""
    blanc = Image.new("RGBA", image.size, (255, 255, 255, 0))
    blanc.putalpha(image.getchannel("A"))
    return blanc


def armoiries() -> None:
    source = Image.open(SOURCE_ARMOIRIES).convert("RGBA")
    for hauteur in TAILLES:
        for echelle in (1, 2):
            taille = hauteur * echelle
            image = source.resize((taille, taille), Image.LANCZOS)
            suffixe = "" if echelle == 1 else "@2x"
            image.save(SORTIE / f"armoiries-{hauteur}{suffixe}.png", optimize=True)
            en_blanc(image).save(SORTIE / f"armoiries-blanc-{hauteur}{suffixe}.png", optimize=True)
    source.resize((32, 32), Image.LANCZOS).save(SORTIE / "favicon.png", optimize=True)
    # Photo de profil WhatsApp (640 x 640, affichée en cercle) : armoiries en couleur sur blanc.
    profil = Image.new("RGBA", (640, 640), (255, 255, 255, 255))
    profil.alpha_composite(source.resize((500, 500), Image.LANCZOS), (70, 70))
    profil.convert("RGB").save(SORTIE / "profil-whatsapp.png", optimize=True)
    # Fond de la page de connexion de Directus : bleu institutionnel, liseré tricolore en bas.
    fond = Image.new("RGB", (1920, 1080), "#17418a")
    for i, couleur in enumerate(("#0095c9", "#fff24b", "#db3832")):
        fond.paste(Image.new("RGB", (640, 14), couleur), (i * 640, 1066))
    fond.save(SORTIE / "fond-connexion.png", optimize=True)
    source.resize((180, 180), Image.LANCZOS).save(SORTIE / "apple-touch-icon.png", optimize=True)
    # Icônes de l'application de terrain (Android) : armoiries dans la zone sûre centrale
    # (80 %) d'un carré blanc, pour qu'elles restent entières une fois découpées en rond.
    for taille in (192, 512):
        icone = Image.new("RGBA", (taille, taille), (255, 255, 255, 255))
        cote = round(taille * 0.7)
        icone.alpha_composite(source.resize((cote, cote), Image.LANCZOS),
                              ((taille - cote) // 2, (taille - cote) // 2))
        icone.convert("RGB").save(SORTIE / f"icone-{taille}.png", optimize=True)
    total = sum(p.stat().st_size for p in SORTIE.glob("*.png"))
    print(f"armoiries : {len(list(SORTIE.glob('*.png')))} fichiers, {total // 1024} Ko au total")


def bloc_marque(dossier: Path) -> None:
    """Bloc-marque complet en image (armoiries, Ligne d'État, intitulé), pour les outils
    qui n'acceptent qu'une image : page de connexion de Directus, documents.

    Proportions de la charte (p. 10-11) : la Ligne d'État a la hauteur des armoiries,
    sa largeur X vaut environ 1/21 de cette hauteur, et 4X la sépare de chaque côté.
    """
    from PIL import ImageDraw, ImageFont

    sys.path.insert(0, str(RACINE / "src"))
    from coeur.charte import INTITULE

    hauteur = 160
    x = round(hauteur / 21)
    police = ImageFont.truetype(str(dossier / "CooperHewitt-Semibold.otf"), round(hauteur * 0.19))
    lignes = [ligne.upper() for ligne in INTITULE]
    largeur_texte = max(police.getbbox(l)[2] for l in lignes)
    for blanc in (False, True):
        image = Image.new("RGBA", (hauteur + 8 * x + x + largeur_texte + 4, hauteur), (0, 0, 0, 0))
        source = Image.open(SOURCE_ARMOIRIES).convert("RGBA").resize((hauteur, hauteur), Image.LANCZOS)
        image.alpha_composite(en_blanc(source) if blanc else source, (0, 0))
        dessin = ImageDraw.Draw(image)
        gauche = hauteur + 4 * x
        for i, couleur in enumerate(("#0095c9", "#fff24b", "#db3832")):
            dessin.rectangle((gauche, round(i * hauteur / 3), gauche + x - 1,
                              round((i + 1) * hauteur / 3) - 1), fill=couleur)
        interligne = round(hauteur * 0.24)
        haut = (hauteur - interligne * len(lignes)) // 2
        for i, ligne in enumerate(lignes):
            dessin.text((gauche + 5 * x, haut + i * interligne), ligne, font=police,
                        fill="#ffffff" if blanc else "#323230")
        nom = "bloc-marque-blanc.png" if blanc else "bloc-marque.png"
        image.save(SORTIE / nom, optimize=True)
        print(f"{nom} : {image.size[0]} x {image.size[1]}")


if __name__ == "__main__":
    SORTIE.mkdir(parents=True, exist_ok=True)
    armoiries()
    if len(sys.argv) > 1:
        polices(Path(sys.argv[1]))
        bloc_marque(Path(sys.argv[1]))
