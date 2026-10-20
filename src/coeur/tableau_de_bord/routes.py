"""Pages du tableau de bord (réservées aux comptes autorisés)."""

import csv
import io
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from coeur import charte
from coeur.base import session_db
from coeur.config import Parametres, parametres
from coeur.centre_appels.service import statistiques_appels
from coeur.mobile.statistiques import statistiques_mobile
from coeur.whatsapp.statistiques import statistiques_whatsapp
from coeur.connaissances.service import langues_actives
from coeur.interactions import service as interactions
from coeur.limiteur import LimiteurDebit
from coeur.signalements import service as signalements
from coeur.signalements.schemas import StatutSignalement, TypeSignalement
from coeur.statistiques.schemas import Axe, Effectifs
from coeur.statistiques.service import repartir_interactions, repartir_signalements
from coeur.tableau_de_bord.auth import (
    CHEMIN,
    Authentificateur,
    Utilisateur,
    accueil,
    authentificateur,
    espaces,
    exiger,
)
from coeur.territoires.service import lister as lister_territoires

routeur = APIRouter(prefix=CHEMIN, include_in_schema=False)
gabarits = charte.gabarits(Path(__file__).parent / "gabarits")


def heure_locale(moment: datetime) -> str:
    return moment.astimezone(ZoneInfo(parametres().fuseau_horaire)).strftime("%d/%m/%Y %H:%M")


gabarits.env.filters["heure_locale"] = heure_locale

PAR_PAGE = 50
JOURS_ESCALADES_FREQUENTES = 30
NiveauGeo = Literal["province", "territoire"]

MOTIFS = {
    "aucune_reponse_validee": "Aucune réponse validée",
    "ambigu": "Plusieurs réponses possibles",
    "demande_humain": "Demande à parler à quelqu'un",
    "traduction_indisponible": "Traduction indisponible",
}
TYPES = {
    "menage_non_visite": "Ménage non visité",
    "rumeur": "Rumeur",
    "agent_douteux": "Agent douteux",
    "autre": "Autre",
}
STATUTS = {"nouveau": "Nouveau", "en_traitement": "En traitement", "clos": "Clos"}
CANAUX = {
    "ussd": "USSD", "sms": "SMS", "whatsapp": "WhatsApp", "web": "Portail web",
    "kiosque": "Kiosques", "ambassadeur": "Ambassadeurs", "centre_ecoute": "Centre d'écoute",
}


PILOTAGE = exiger("pilotage")


@lru_cache
def limiteur_connexion() -> LimiteurDebit:
    """10 tentatives de connexion par quart d'heure et par adresse IP."""
    return LimiteurDebit(10, 15 * 60)


def _date(texte: str | None) -> date | None:
    try:
        return date.fromisoformat(texte) if texte else None
    except ValueError:
        return None


def _page(request: Request, gabarit: str, utilisateur: Utilisateur | None = None,
          statut: int = 200, **contexte) -> Response:
    reponse = gabarits.TemplateResponse(
        request,
        gabarit,
        {"utilisateur": utilisateur, "espaces": espaces(utilisateur.role) if utilisateur else [],
         "seuil": parametres().seuil_secret_statistique,
         "rubrique": gabarit.removesuffix(".html"), **contexte},
        status_code=statut,
    )
    # Données de pilotage : jamais gardées dans un cache (navigateur ou proxy).
    reponse.headers["Cache-Control"] = "no-store"
    return reponse


def _libelles(session: Session) -> dict[str, str]:
    """Codes → noms lisibles : provinces, territoires, langues, canaux, types."""
    noms = {**CANAUX, **TYPES, "non_renseigne": "Non renseigné", "RDC": "RDC"}
    for province in lister_territoires(session):
        noms[province.code] = province.nom
        noms.update({t.code: t.nom for t in province.territoires})
    noms.update({l.code: l.nom for l in langues_actives(session)})
    return noms


def _maximum(lignes: list[Effectifs], champ: str) -> int:
    return max((getattr(l, champ) or 0 for l in lignes), default=0) or 1


# --- Connexion -----------------------------------------------------------------------

@routeur.get("/connexion")
def connexion(request: Request):
    return _page(request, "connexion.html")


@routeur.post("/connexion")
def connexion_envoi(
    request: Request,
    email: str = Form(default=""),
    mdp: str = Form(default=""),
    auth: Authentificateur = Depends(authentificateur),
    reglages: Parametres = Depends(parametres),
):
    adresse = request.client.host if request.client else "inconnue"
    if not limiteur_connexion().autoriser(adresse):
        return _page(request, "connexion.html", statut=429,
                     erreur="Trop de tentatives. Réessayez dans un quart d'heure.")
    utilisateur = auth.verifier(email.strip(), mdp) if email and mdp else None
    if utilisateur is None:
        return _page(request, "connexion.html", statut=401, email=email,
                     erreur="Adresse électronique ou mot de passe incorrect.")
    if utilisateur.role not in reglages.roles_autorises():
        return _page(request, "connexion.html", statut=403, email=email,
                     erreur="Votre compte n'a pas accès au tableau de bord.")
    request.session.clear()
    request.session.update({"email": utilisateur.email, "role": utilisateur.role})
    return RedirectResponse(accueil(utilisateur.role), status_code=303)


@routeur.post("/deconnexion")
def deconnexion(request: Request):
    request.session.clear()
    return RedirectResponse(f"{CHEMIN}/connexion", status_code=303)


# --- Synthèse ------------------------------------------------------------------------

def _repartitions(session: Session, niveau: NiveauGeo, depuis: date | None,
                  jusqu_a: date | None, seuil: int) -> dict[str, list[Effectifs]]:
    """Les dates choisies sont des journées à l'heure locale (FUSEAU_HORAIRE)."""
    axe_geo = Axe(niveau)
    fuseau = ZoneInfo(parametres().fuseau_horaire)
    return {
        "total": repartir_interactions(session, None, depuis, jusqu_a, seuil, fuseau),
        "canal": repartir_interactions(session, Axe.CANAL, depuis, jusqu_a, seuil, fuseau),
        "langue": repartir_interactions(session, Axe.LANGUE, depuis, jusqu_a, seuil, fuseau),
        "geo": repartir_interactions(session, axe_geo, depuis, jusqu_a, seuil, fuseau),
        "signalements_total": repartir_signalements(session, None, depuis, jusqu_a, seuil, fuseau),
        "signalements_type": repartir_signalements(session, Axe.TYPE, depuis, jusqu_a, seuil, fuseau),
        "signalements_geo": repartir_signalements(session, axe_geo, depuis, jusqu_a, seuil, fuseau),
    }


@routeur.get("")
def synthese(
    request: Request,
    niveau: NiveauGeo = "province",
    depuis: str | None = None,
    jusqu_a: str | None = None,
    utilisateur: Utilisateur = Depends(PILOTAGE),
    session: Session = Depends(session_db),
    reglages: Parametres = Depends(parametres),
):
    debut, fin = _date(depuis), _date(jusqu_a)
    donnees = _repartitions(session, niveau, debut, fin, reglages.seuil_secret_statistique)
    total = donnees["total"][0] if donnees["total"] else None
    return _page(
        request, "synthese.html", utilisateur,
        niveau=niveau, depuis=debut, jusqu_a=fin, total=total,
        signalements_total=donnees["signalements_total"][0] if donnees["signalements_total"] else None,
        repartitions=donnees, noms=_libelles(session), maximum=_maximum,
        appels=statistiques_appels(session, debut, fin, ZoneInfo(reglages.fuseau_horaire),
                                   reglages.seuil_secret_statistique),
        mobile=statistiques_mobile(session, debut, fin, ZoneInfo(reglages.fuseau_horaire),
                                   reglages.seuil_secret_statistique),
        whatsapp=statistiques_whatsapp(session, debut, fin, ZoneInfo(reglages.fuseau_horaire),
                                       reglages.seuil_secret_statistique),
    )


@routeur.get("/export.csv")
def export_csv(
    niveau: NiveauGeo = "province",
    depuis: str | None = None,
    jusqu_a: str | None = None,
    _utilisateur: Utilisateur = Depends(PILOTAGE),
    session: Session = Depends(session_db),
    reglages: Parametres = Depends(parametres),
):
    """Mêmes chiffres que la synthèse, masqués de la même façon (case vide = masquée)."""
    debut, fin = _date(depuis), _date(jusqu_a)
    donnees = _repartitions(session, niveau, debut, fin, reglages.seuil_secret_statistique)
    noms = _libelles(session)
    sortie = io.StringIO()
    ecrivain = csv.writer(sortie, delimiter=";", lineterminator="\n")
    ecrivain.writerow(["indicateur", "axe", "valeur", "libelle", "effectif",
                       "escalades", "usagers_uniques", "masque"])

    def vide(v):
        return "" if v is None else v

    for cle, axe in (("total", "national"), ("canal", "canal"), ("langue", "langue"),
                     ("geo", niveau)):
        for e in donnees[cle]:
            ecrivain.writerow(["interactions", axe, e.valeur, noms.get(e.valeur, e.valeur),
                               vide(e.nb_interactions), vide(e.nb_escalades),
                               vide(e.nb_usagers_uniques), int(e.masque)])
    for cle, axe in (("signalements_total", "national"), ("signalements_type", "type"),
                     ("signalements_geo", niveau)):
        for e in donnees[cle]:
            ecrivain.writerow(["signalements", axe, e.valeur, noms.get(e.valeur, e.valeur),
                               vide(e.nb_signalements), "", "", int(e.masque)])
    nom = f"rgph2-statistiques-{niveau}-{date.today().isoformat()}.csv"
    return Response(
        # BOM UTF-8 : ouverture correcte des accents dans Excel.
        content="﻿" + sortie.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nom}"',
                 "Cache-Control": "no-store"},
    )


# --- Questions escaladées ------------------------------------------------------------

@routeur.get("/escalades")
def escalades(
    request: Request,
    langue: str | None = None,
    motif: str | None = None,
    page: int = Query(default=1, ge=1),
    utilisateur: Utilisateur = Depends(PILOTAGE),
    session: Session = Depends(session_db),
):
    depuis = datetime.now(timezone.utc) - timedelta(days=JOURS_ESCALADES_FREQUENTES)
    recentes = interactions.escalades_recentes(
        session, langue=langue or None, motif=motif or None,
        limite=PAR_PAGE + 1, decalage=(page - 1) * PAR_PAGE,
    )
    return _page(
        request, "escalades.html", utilisateur,
        frequentes=interactions.escalades_frequentes(session, depuis=depuis),
        recentes=recentes[:PAR_PAGE], page_suivante=len(recentes) > PAR_PAGE, page=page,
        langue=langue or "", motif=motif or "", motifs=MOTIFS, noms=_libelles(session),
        langues=langues_actives(session), jours=JOURS_ESCALADES_FREQUENTES,
    )


# --- Signalements --------------------------------------------------------------------

@routeur.get("/signalements")
def liste_signalements(
    request: Request,
    territoire_code: str | None = None,
    statut: StatutSignalement | Literal[""] | None = None,
    type: TypeSignalement | Literal[""] | None = None,
    page: int = Query(default=1, ge=1),
    utilisateur: Utilisateur = Depends(PILOTAGE),
    session: Session = Depends(session_db),
):
    lignes = signalements.lister(
        session, territoire_code=territoire_code or None, statut=statut or None,
        type_=type or None, limite=PAR_PAGE + 1, decalage=(page - 1) * PAR_PAGE,
    )
    return _page(
        request, "signalements.html", utilisateur,
        signalements=lignes[:PAR_PAGE], page_suivante=len(lignes) > PAR_PAGE, page=page,
        filtres={"territoire_code": territoire_code or "", "statut": statut or "",
                 "type": type or ""},
        provinces=lister_territoires(session), noms=_libelles(session),
        types=TYPES, statuts=STATUTS,
    )


@routeur.post("/signalements/{signalement_id}")
def changer_statut(
    signalement_id: int,
    statut: StatutSignalement = Form(),
    _utilisateur: Utilisateur = Depends(PILOTAGE),
    session: Session = Depends(session_db),
):
    if signalements.changer_statut(session, signalement_id, statut) is None:
        raise HTTPException(404, "Signalement introuvable")
    return RedirectResponse(f"{CHEMIN}/signalements", status_code=303)
