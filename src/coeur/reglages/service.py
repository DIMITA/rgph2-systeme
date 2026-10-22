from typing import Annotated

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from coeur.config import Parametres
from coeur.reglages.catalogue import ENV_SEULEMENT, SECRETS
from coeur.reglages.modeles import Reglage
from coeur.reglages.source import chiffreur


def valider(champ: str, valeur: str) -> None:
    """ValueError si le champ n'existe pas, doit rester dans .env, ou si la valeur est invalide."""
    if champ in ENV_SEULEMENT:
        raise ValueError(f"{champ} reste dans .env : d'autres services le lisent au démarrage")
    champ_modele = Parametres.model_fields.get(champ)
    if champ_modele is None:
        raise ValueError(f"Réglage inconnu : {champ}")
    type_ = champ_modele.annotation
    if champ_modele.metadata:  # contraintes de Field() : longueur minimale…
        type_ = Annotated[type_, *champ_modele.metadata]
    try:
        TypeAdapter(type_).validate_python(valeur)
    except ValidationError as erreur:
        raise ValueError(f"{champ} : {erreur.errors()[0]['msg']}") from erreur


def lire(session: Session, cle_maitre: str) -> dict[str, str]:
    fernet = chiffreur(cle_maitre)
    return {r.cle: fernet.decrypt(r.valeur.encode()).decode()
            for r in session.scalars(select(Reglage))}


def ecrire(session: Session, cle_maitre: str, valeurs: dict[str, str]) -> None:
    """Valide puis enregistre, chiffré. Tout ou rien."""
    for champ, valeur in valeurs.items():
        valider(champ, valeur)
    fernet = chiffreur(cle_maitre)
    for champ, valeur in valeurs.items():
        chiffre = fernet.encrypt(valeur.encode()).decode()
        session.execute(insert(Reglage).values(cle=champ, valeur=chiffre).on_conflict_do_update(
            index_elements=[Reglage.cle], set_={"valeur": chiffre}))
    session.commit()


def effacer(session: Session, champ: str) -> bool:
    supprime = session.execute(delete(Reglage).where(Reglage.cle == champ)).rowcount
    session.commit()
    return bool(supprime)


def changer_cle_maitre(session: Session, ancienne: str, nouvelle: str) -> int:
    """Rechiffre tout avec la nouvelle clé, en une transaction."""
    valeurs = lire(session, ancienne)
    fernet = chiffreur(nouvelle)
    for champ, valeur in valeurs.items():
        session.get(Reglage, champ).valeur = fernet.encrypt(valeur.encode()).decode()
    session.commit()
    return len(valeurs)


def masquer(champ: str, valeur: str) -> str:
    if champ not in SECRETS or not valeur:
        return valeur
    return f"{valeur[:3]}…{valeur[-2:]} ({len(valeur)} caractères)"


def eligibles() -> list[str]:
    """Champs de Parametres qui peuvent être gardés en base."""
    return [c for c in Parametres.model_fields if c not in ENV_SEULEMENT]
