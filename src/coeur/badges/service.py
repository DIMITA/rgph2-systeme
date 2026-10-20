import csv
import hashlib
import hmac
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from coeur.badges.modeles import Badge
from coeur.territoires.modeles import Territoire

COLONNES_CSV = ("numero", "territoire_code", "actif")
_FORMAT = re.compile(r"^[A-Z0-9]{3,20}$")

StatutBadge = Literal["valide", "retire", "inconnu"]


def normaliser_badge(texte: str) -> str:
    """« rgph-0012 34 » → « RGPH001234 ». ValueError si le format est impossible."""
    numero = re.sub(r"[\s\-./]", "", texte).upper()
    if not _FORMAT.match(numero):
        raise ValueError("Numéro de badge invalide")
    return numero


def empreinte_badge(numero: str, pepper: str) -> str:
    return hmac.new(pepper.encode(), b"badge:" + normaliser_badge(numero).encode(),
                    hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class Verification:
    statut: StatutBadge
    numero: str
    territoire_code: str | None = None
    territoire_nom: str | None = None


def verifier(session: Session, numero: str, pepper: str) -> Verification:
    """Badge valide (avec son territoire), retiré, ou inconnu. ValueError si format invalide."""
    numero = normaliser_badge(numero)
    ligne = session.execute(
        select(Badge, Territoire.nom)
        .join(Territoire, Territoire.code == Badge.territoire_code)
        .where(Badge.empreinte == empreinte_badge(numero, pepper))
    ).first()
    if ligne is None:
        return Verification("inconnu", numero)
    badge, nom = ligne
    return Verification("valide" if badge.actif else "retire", numero, badge.territoire_code, nom)


def _vrai(texte: str) -> bool:
    return texte.strip().lower() in ("1", "oui", "o", "true", "vrai", "actif")


def importer_csv(session: Session, chemin: Path, pepper: str) -> tuple[int, int]:
    """Remplace toute la liste par le fichier de l'INS (séparateur « , », UTF-8).

    Un badge absent du nouveau fichier devient « inconnu ». Le fichier est refusé en
    entier s'il contient une ligne invalide (le remplacement est tout ou rien).
    Renvoie (badges actifs, badges retirés).
    """
    connus = set(session.scalars(select(Territoire.code)))
    badges: dict[str, Badge] = {}
    erreurs = []
    with chemin.open(encoding="utf-8-sig", newline="") as fichier:
        lecteur = csv.DictReader(fichier)
        manquantes = set(COLONNES_CSV) - set(lecteur.fieldnames or [])
        if manquantes:
            raise ValueError(f"Colonnes manquantes dans {chemin} : {sorted(manquantes)}")
        for n, ligne in enumerate(lecteur, start=2):
            territoire = (ligne["territoire_code"] or "").strip()
            try:
                empreinte = empreinte_badge(ligne["numero"] or "", pepper)
            except ValueError:
                erreurs.append(f"ligne {n} : numéro de badge invalide")
                continue
            if territoire not in connus:
                erreurs.append(f"ligne {n} : territoire inconnu {territoire!r}")
                continue
            badges[empreinte] = Badge(empreinte=empreinte, territoire_code=territoire,
                                      actif=_vrai(ligne["actif"] or ""))
    if erreurs:
        raise ValueError("Import refusé, aucun badge modifié :\n" + "\n".join(erreurs[:20]))
    session.execute(delete(Badge))
    session.add_all(badges.values())
    session.commit()
    actifs = sum(b.actif for b in badges.values())
    return actifs, len(badges) - actifs
