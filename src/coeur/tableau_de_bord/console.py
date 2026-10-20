"""Console des agents (espace « agents ») et écoute qualité (espace « qualite »).

La console téléphone dans le navigateur (JsSIP, WebRTC) en se connectant à
Asterisk avec le compte SIP d'un poste. Le mot de passe du poste est dérivé de
SECRET_POSTES et n'est remis qu'aux agents connectés.
"""

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from coeur.base import session_db
from coeur.centre_appels import service as centre
from coeur.centre_appels.modeles import QUALIFICATIONS, Enregistrement
from coeur.centre_appels.postes import mot_de_passe_poste, postes
from coeur.commun import Canal
from coeur.config import Parametres, parametres
from coeur.connaissances import service as connaissances
from coeur.connaissances.depot import Corpus
from coeur.connaissances.routes import corpus_courant
from coeur.signalements import service as signalements
from coeur.signalements.schemas import SignalementEntree
from coeur.tableau_de_bord.auth import CHEMIN, Utilisateur, exiger
from coeur.tableau_de_bord.routes import TYPES, _libelles, _page, heure_locale
from coeur.territoires.service import lister as lister_territoires
from coeur.territoires.service import territoire_existe

routeur = APIRouter(prefix=CHEMIN, include_in_schema=False)
AGENTS = exiger("agents")
QUALITE = exiger("qualite")
PAR_PAGE = 50
NB_RESULTATS_RECHERCHE = 5
# Canal par lequel le citoyen a demandé à être rappelé.
ORIGINES = {"appel": "Numéro vert", "ussd": "USSD", "sms": "SMS"}

LIBELLES_QUALIFICATION = {
    "renseigne": "Citoyen renseigné",
    "signalement": "Signalement enregistré",
    "transmis_bcr": "Question transmise au BCR",
    "hors_sujet": "Hors sujet",
    "coupe": "Appel coupé",
}


def _politique_console(reglages: Parametres) -> str:
    """CSP de la console : comme le reste du site, plus la connexion WebSocket à Asterisk."""
    return (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        f"media-src 'self' blob:; connect-src 'self' {reglages.asterisk_ws_url}; "
        "form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
    )


# --- Console des agents -----------------------------------------------------------------

@routeur.get("/agent")
def console(
    request: Request,
    utilisateur: Utilisateur = Depends(AGENTS),
    session: Session = Depends(session_db),
    reglages: Parametres = Depends(parametres),
):
    poste = request.session.get("poste")
    contexte = {"postes": postes(reglages.nb_postes), "poste": poste}
    if poste:
        contexte |= {
            "ws_url": reglages.asterisk_ws_url,
            "sip_uri": f"sip:{poste}@{reglages.sip_domaine}",
            "mot_de_passe": mot_de_passe_poste(reglages.secret_postes, poste),
            "provinces": lister_territoires(session),
            "types": TYPES,
            "qualifications": LIBELLES_QUALIFICATION,
            "langues": connaissances.langues_actives(session),
        }
    reponse = _page(request, "agent.html", utilisateur, **contexte)
    reponse.headers["Content-Security-Policy"] = _politique_console(reglages)
    return reponse


@routeur.post("/agent/poste")
def choisir_poste(
    request: Request,
    poste: str = Form(),
    _utilisateur: Utilisateur = Depends(AGENTS),
    reglages: Parametres = Depends(parametres),
):
    if poste not in postes(reglages.nb_postes):
        raise HTTPException(422, "Poste inconnu")
    request.session["poste"] = poste
    return RedirectResponse(f"{CHEMIN}/agent", status_code=303)


@routeur.post("/agent/liberer")
def liberer_poste(request: Request, _utilisateur: Utilisateur = Depends(AGENTS)):
    request.session.pop("poste", None)
    return RedirectResponse(f"{CHEMIN}/agent", status_code=303)


@routeur.get("/agent/appel-courant")
def appel_courant(
    request: Request,
    _utilisateur: Utilisateur = Depends(AGENTS),
    session: Session = Depends(session_db),
):
    """Appel décroché sur le poste de l'agent : langue choisie par l'appelant (jamais son numéro)."""
    appel = centre.appel_en_cours(session, request.session.get("poste") or "")
    if appel is None:
        return {"appel": None}
    noms = {l.code: l.nom for l in connaissances.langues_actives(session)}
    return {"appel": {
        "reference": appel.reference,
        "langue": appel.langue,
        "langue_nom": noms.get(appel.langue or "", "Non choisie"),
        "decroche_a": heure_locale(appel.decroche_a),
    }}


@routeur.get("/agent/recherche")
def recherche(
    q: str = "",
    langue: str = "fr",
    _utilisateur: Utilisateur = Depends(AGENTS),
    corpus: Corpus = Depends(corpus_courant),
    reglages: Parametres = Depends(parametres),
):
    """Contenus validés les plus proches. Rien n'est journalisé : c'est l'agent qui cherche."""
    q = q.strip()[:300]
    if not q:
        return []
    candidats = corpus.moteur.rechercher(q, [langue, reglages.langue_par_defaut])
    resultats = []
    for candidat in candidats[:NB_RESULTATS_RECHERCHE]:
        texte = connaissances.texte_servi(corpus, candidat.contenu_id, langue,
                                          reglages.langue_par_defaut)
        if texte:
            resultats.append({**texte.model_dump(), "score": candidat.score})
    return resultats


@routeur.post("/agent/signalement", status_code=201)
def signalement_telephone(
    type: str = Form(default=""),
    territoire_code: str = Form(default=""),
    localite: str = Form(default=""),
    description: str = Form(default=""),
    _utilisateur: Utilisateur = Depends(AGENTS),
    session: Session = Depends(session_db),
    reglages: Parametres = Depends(parametres),
):
    try:
        entree = SignalementEntree(type=type, territoire_code=territoire_code,
                                   localite=localite.strip() or None,
                                   description=description.strip() or None)
    except ValidationError:
        raise HTTPException(422, "Type ou territoire invalide") from None
    if not territoire_existe(session, entree.territoire_code):
        raise HTTPException(422, "Territoire inconnu")
    cree = signalements.creer(session, entree, Canal.CENTRE_ECOUTE, reglages.pepper_telephone)
    return {"id": cree.id}


@routeur.post("/agent/qualification")
def qualification(
    appel: str = Form(),
    qualification: Literal[QUALIFICATIONS] = Form(),  # type: ignore[valid-type]
    _utilisateur: Utilisateur = Depends(AGENTS),
    session: Session = Depends(session_db),
):
    if centre.qualifier(session, appel, qualification) is None:
        raise HTTPException(404, "Appel introuvable")
    return {"ok": True}


@routeur.get("/agent/rappels")
def rappels(
    utilisateur: Utilisateur = Depends(AGENTS),
    session: Session = Depends(session_db),
):
    """Demandes de rappel ouvertes, sans les numéros (révélés seulement à la prise en charge)."""
    noms = {l.code: l.nom for l in connaissances.langues_actives(session)}
    return [
        {"id": r.id, "cree_a": heure_locale(r.cree_a), "langue_nom": noms.get(r.langue or "", "—"),
         "origine": ORIGINES.get(r.origine, r.origine),
         "statut": r.statut, "pris_par_moi": r.traite_par == utilisateur.email}
        for r in centre.rappels_ouverts(session)
    ]


@routeur.post("/agent/rappels/{rappel_id}/prendre")
def prendre_rappel(
    rappel_id: int,
    utilisateur: Utilisateur = Depends(AGENTS),
    session: Session = Depends(session_db),
):
    try:
        numero = centre.prendre_rappel(session, rappel_id, utilisateur.email)
    except centre.RappelDejaPris:
        return JSONResponse({"detail": "Rappel déjà pris par un autre agent"}, status_code=409)
    if numero is None:
        raise HTTPException(404, "Rappel introuvable ou déjà traité")
    return {"numero": numero}


@routeur.post("/agent/rappels/{rappel_id}/cloturer")
def cloturer_rappel(
    rappel_id: int,
    statut: Literal["rappele", "injoignable"] = Form(),
    utilisateur: Utilisateur = Depends(AGENTS),
    session: Session = Depends(session_db),
):
    if centre.traiter_rappel(session, rappel_id, statut, utilisateur.email) is None:
        raise HTTPException(404, "Rappel introuvable")
    return {"ok": True}


# --- Écoute qualité ---------------------------------------------------------------------

def _duree(chemin: Path) -> str:
    """Durée d'un WAV 8 kHz 16 bits mono (en-tête de 44 octets)."""
    if not chemin.is_file():
        return "fichier absent"
    secondes = max(chemin.stat().st_size - 44, 0) // 16_000
    return f"{secondes // 60} min {secondes % 60:02d} s"


@routeur.get("/qualite")
def qualite(
    request: Request,
    page: int = 1,
    utilisateur: Utilisateur = Depends(QUALITE),
    session: Session = Depends(session_db),
    reglages: Parametres = Depends(parametres),
):
    page = max(page, 1)
    lignes = centre.lister_enregistrements(session, PAR_PAGE + 1, (page - 1) * PAR_PAGE)
    return _page(
        request, "qualite.html", utilisateur,
        enregistrements=[(e, a, _duree(centre.chemin_enregistrement(e)))
                         for e, a in lignes[:PAR_PAGE]],
        page=page, page_suivante=len(lignes) > PAR_PAGE, noms=_libelles(session),
        qualifications=LIBELLES_QUALIFICATION, ecoutes=centre.dernieres_ecoutes(session),
        conservation=reglages.conservation_enregistrements_jours,
    )


@routeur.get("/qualite/ecouter/{enregistrement_id}")
def ecouter(
    enregistrement_id: int,
    request: Request,
    utilisateur: Utilisateur = Depends(QUALITE),
    session: Session = Depends(session_db),
):
    enregistrement = session.get(Enregistrement, enregistrement_id)
    if enregistrement is None:
        raise HTTPException(404, "Enregistrement introuvable")
    chemin = centre.chemin_enregistrement(enregistrement)
    if not chemin.is_file():
        raise HTTPException(404, "Fichier supprimé ou absent")
    # Le lecteur audio demande le fichier par morceaux : seule la première demande compte.
    plage = request.headers.get("range", "")
    if not plage or plage.startswith("bytes=0-"):
        centre.journaliser_ecoute(session, enregistrement, utilisateur.email)
    return FileResponse(chemin, media_type="audio/wav", headers={"Cache-Control": "no-store"})
