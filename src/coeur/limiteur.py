"""Compteurs et mémoires de courte durée, partagés par tous les processus via PostgreSQL.

- `LimiteurDebit` : limite de requêtes par clé (adresse IP, empreinte d'usager).
- `MemoireCourte` : ce qui a déjà été vu ou répondu récemment (message WhatsApp
  renvoyé par Meta, requête USSD rejouée par la passerelle).

Les clés ne sont jamais enregistrées en clair : seule leur empreinte HMAC (avec
PEPPER_TELEPHONE) l'est. Les tables sont « UNLOGGED » : ni journal de transactions,
ni réplication, ni sauvegarde. Elles sont vidées si PostgreSQL redémarre après un
arrêt brutal, ce qui est sans conséquence ici. Les lignes expirées sont effacées
par les tâches périodiques (`purger`).
"""

import hashlib
import hmac
import time
from datetime import datetime, timezone

from sqlalchemy import JSON, BigInteger, DateTime, Integer, String, delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Mapped, Session, mapped_column

from coeur.base import SCHEMA_COEUR, Base, moteur_sql
from coeur.config import parametres

TABLES_COURTES = {"schema": SCHEMA_COEUR, "prefixes": ["UNLOGGED"]}


class CompteurDebit(Base):
    __tablename__ = "compteurs_debit"
    __table_args__ = TABLES_COURTES

    cle: Mapped[str] = mapped_column(String(64), primary_key=True)
    # Numéro de la fenêtre : secondes depuis l'origine // durée de la fenêtre.
    fenetre: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    nb: Mapped[int] = mapped_column(Integer)
    expire_a: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class Marque(Base):
    __tablename__ = "memoire_courte"
    __table_args__ = TABLES_COURTES

    cle: Mapped[str] = mapped_column(String(64), primary_key=True)
    valeur: Mapped[dict | None] = mapped_column(JSON)
    expire_a: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


def _empreinte(espace: str, cle: str) -> str:
    return hmac.new(parametres().pepper_telephone.encode(), f"{espace}:{cle}".encode(),
                    hashlib.sha256).hexdigest()


def _date(secondes: float) -> datetime:
    return datetime.fromtimestamp(secondes, timezone.utc)


class LimiteurDebit:
    """Au plus `limite` requêtes par clé sur une fenêtre glissante de `fenetre_secondes`.

    La fenêtre glissante est estimée à partir de deux fenêtres fixes : la courante,
    plus la précédente au prorata du temps qui en reste dans la fenêtre glissante.
    Les requêtes refusées sont comptées aussi (dans la limite de `limite` + 1) :
    une rafale parallèle ne peut pas passer entre la lecture et l'écriture, et
    insister prolonge le blocage.
    """

    def __init__(self, espace: str, limite: int, fenetre_secondes: float):
        self.espace = espace
        self.limite = limite
        self.fenetre = fenetre_secondes

    def autoriser(self, cle: str, maintenant: float | None = None) -> bool:
        maintenant = time.time() if maintenant is None else maintenant
        numero = int(maintenant // self.fenetre)
        empreinte = _empreinte(self.espace, cle)
        ajout = insert(CompteurDebit).values(
            cle=empreinte, fenetre=numero, nb=1,
            expire_a=_date((numero + 2) * self.fenetre),
        )
        ajout = ajout.on_conflict_do_update(
            index_elements=[CompteurDebit.cle, CompteurDebit.fenetre],
            set_={"nb": func.least(CompteurDebit.nb + 1, self.limite + 1)},
        ).returning(CompteurDebit.nb)
        with moteur_sql().begin() as connexion:
            courante = connexion.execute(ajout).scalar_one()
            precedente = connexion.execute(
                select(CompteurDebit.nb).where(CompteurDebit.cle == empreinte,
                                               CompteurDebit.fenetre == numero - 1)
            ).scalar() or 0
        ecoule = maintenant / self.fenetre - numero
        return precedente * (1 - ecoule) + courante <= self.limite

    def reinitialiser(self) -> None:
        """Pour les tests : oublie tous les compteurs (de tous les espaces)."""
        with moteur_sql().begin() as connexion:
            connexion.execute(delete(CompteurDebit))


class MemoireCourte:
    """Clé → valeur (JSON), oubliée après `duree_secondes`."""

    def __init__(self, espace: str, duree_secondes: float):
        self.espace = espace
        self.duree = duree_secondes

    def nouveau(self, cle: str) -> bool:
        """Vrai la première fois qu'une clé est vue pendant la durée de la mémoire."""
        maintenant = time.time()
        empreinte = _empreinte(self.espace, cle)
        with moteur_sql().begin() as connexion:
            connexion.execute(delete(Marque).where(Marque.cle == empreinte,
                                                   Marque.expire_a <= _date(maintenant)))
            ajout = insert(Marque).values(
                cle=empreinte, valeur=None, expire_a=_date(maintenant + self.duree)
            ).on_conflict_do_nothing().returning(Marque.cle)
            return connexion.execute(ajout).scalar() is not None

    def lire(self, cle: str) -> dict | None:
        with moteur_sql().connect() as connexion:
            return connexion.execute(
                select(Marque.valeur).where(Marque.cle == _empreinte(self.espace, cle),
                                            Marque.expire_a > _date(time.time()))
            ).scalar()

    def garder(self, cle: str, valeur: dict) -> None:
        expire = _date(time.time() + self.duree)
        ajout = insert(Marque).values(cle=_empreinte(self.espace, cle), valeur=valeur,
                                      expire_a=expire)
        ajout = ajout.on_conflict_do_update(index_elements=[Marque.cle],
                                            set_={"valeur": valeur, "expire_a": expire})
        with moteur_sql().begin() as connexion:
            connexion.execute(ajout)

    def vider(self) -> None:
        """Pour les tests : oublie toutes les marques (de tous les espaces)."""
        with moteur_sql().begin() as connexion:
            connexion.execute(delete(Marque))


def purger(session: Session, maintenant: datetime | None = None) -> int:
    """Efface les compteurs et marques expirés. Renvoie le nombre de lignes effacées."""
    maintenant = maintenant or datetime.now(timezone.utc)
    nb = session.execute(delete(CompteurDebit).where(CompteurDebit.expire_a < maintenant)).rowcount
    nb += session.execute(delete(Marque).where(Marque.expire_a < maintenant)).rowcount
    return nb
