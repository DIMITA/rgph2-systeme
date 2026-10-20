import csv
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from coeur.territoires.modeles import Province, Territoire
from coeur.territoires.schemas import ProvinceSortie, TerritoireSortie

COLONNES_CSV = ("province_code", "province_nom", "territoire_code", "territoire_nom", "type")


def territoire_existe(session: Session, code: str) -> bool:
    return session.get(Territoire, code) is not None


def lister(session: Session) -> list[ProvinceSortie]:
    provinces = session.scalars(select(Province).order_by(Province.nom)).all()
    territoires = session.scalars(select(Territoire).order_by(Territoire.nom)).all()
    par_province: dict[str, list[TerritoireSortie]] = {}
    for t in territoires:
        par_province.setdefault(t.province_code, []).append(TerritoireSortie.model_validate(t))
    return [
        ProvinceSortie(code=p.code, nom=p.nom, territoires=par_province.get(p.code, []))
        for p in provinces
    ]


def importer_csv(session: Session, chemin: Path) -> tuple[int, int]:
    """Crée ou met à jour provinces et territoires depuis un CSV (séparateur « , », UTF-8).

    Une ligne sans territoire_code déclare seulement la province.
    Renvoie (nombre de provinces, nombre de territoires) lus.
    """
    provinces: dict[str, str] = {}
    territoires: list[dict[str, str]] = []
    with chemin.open(encoding="utf-8-sig", newline="") as fichier:
        lecteur = csv.DictReader(fichier)
        manquantes = set(COLONNES_CSV) - set(lecteur.fieldnames or [])
        if manquantes:
            raise ValueError(f"Colonnes manquantes dans {chemin} : {sorted(manquantes)}")
        for ligne in lecteur:
            provinces[ligne["province_code"].strip()] = ligne["province_nom"].strip()
            if ligne["territoire_code"].strip():
                territoires.append({k: (ligne[k] or "").strip() for k in COLONNES_CSV})

    for code, nom in provinces.items():
        session.merge(Province(code=code, nom=nom))
    session.flush()
    for t in territoires:
        session.merge(
            Territoire(
                code=t["territoire_code"],
                nom=t["territoire_nom"],
                type=t["type"] or "territoire",
                province_code=t["province_code"],
            )
        )
    session.commit()
    return len(provinces), len(territoires)
