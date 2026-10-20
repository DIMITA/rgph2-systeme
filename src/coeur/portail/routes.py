"""Pages du portail citoyen et point d'entrée JSON du chatbot.

Le portail fait partie du cœur : il appelle directement les services (aucune clé
d'API dans le navigateur) et se présente comme le canal « web ».
Tout fonctionne avec de simples formulaires ; portail.js améliore l'affichage
quand le navigateur le permet.
"""

from functools import lru_cache
from pathlib import Path as Chemin

from fastapi import APIRouter, Depends, Form, HTTPException, Path, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import Field, ValidationError
from sqlalchemy.orm import Session

from coeur import charte
from coeur.base import session_db
from coeur.commun import Canal, SchemaEntree
from coeur.config import Parametres, parametres
from coeur.connaissances import service as connaissances
from coeur.connaissances.depot import Corpus
from coeur.connaissances.routes import corpus_courant
from coeur.connaissances.schemas import ReponseSortie
from coeur.limiteur import LimiteurDebit
from coeur.portail.textes import textes
from coeur.signalements import service as signalements
from coeur.signalements.schemas import SignalementEntree
from coeur.territoires import service as territoires

routeur = APIRouter(include_in_schema=False)
gabarits = charte.gabarits(Chemin(__file__).parent / "gabarits")

NB_QUESTIONS_ACCUEIL = 5
# Pas de motif ici : une langue inconnue doit donner 404 (via _verifier_langue), pas 422.
LANGUE = Path()
TROP_DE_REQUETES = 429
ENTITE_INVALIDE = 422


class QuestionPortail(SchemaEntree):
    texte: str = Field(min_length=1, max_length=500)
    langue: str = Field(default="fr", pattern=r"^[a-z]{2,3}$")


@lru_cache
def limiteurs() -> tuple[LimiteurDebit, LimiteurDebit]:
    """(questions par minute, signalements par heure)."""
    reglages = parametres()
    return (
        LimiteurDebit(reglages.portail_questions_par_minute, 60),
        LimiteurDebit(reglages.portail_signalements_par_heure, 3600),
    )


def _adresse(request: Request) -> str:
    return request.client.host if request.client else "inconnue"


def _verifier_langue(session: Session, langue: str) -> list:
    langues = connaissances.langues_actives(session)
    if langue not in {l.code for l in langues}:
        raise HTTPException(404, textes("fr")["page_introuvable"])
    return langues


def message_escalade(t: dict[str, str], numero_vert: str) -> str:
    """Avec un numéro vert, on invite à appeler ; sans numéro, on n'en mentionne aucun."""
    if numero_vert:
        return t["escalade"].replace("{numero}", numero_vert)
    return t["escalade_sans_numero"]


def _page(request: Request, session: Session, langue: str, gabarit: str,
          statut: int = 200, **contexte):
    reglages = parametres()
    t = textes(langue)
    return gabarits.TemplateResponse(
        request,
        gabarit,
        {
            "langue": langue,
            "langues": _verifier_langue(session, langue),
            "t": t,
            "numero_vert": reglages.numero_vert,
            "message_escalade": message_escalade(t, reglages.numero_vert),
            # Charte : bandeau blanc sur la page d'accueil, bleu sur les autres.
            "accueil": gabarit == "accueil.html",
            "page": gabarit.removesuffix(".html"),
            **contexte,
        },
        status_code=statut,
    )


def _apercu_faq(corpus: Corpus, langue: str, reglages: Parametres, limite: int | None = None):
    contenus = (
        connaissances.texte_servi(corpus, cid, langue, reglages.langue_par_defaut)
        for cid in corpus.ids_contenus()
    )
    liste = [c for c in contenus if c is not None]
    return liste[:limite] if limite else liste


@routeur.get("/")
def racine(reglages: Parametres = Depends(parametres)):
    return RedirectResponse(f"/{reglages.langue_par_defaut}")


@routeur.get("/{langue}")
def accueil(request: Request, langue: str = LANGUE, session: Session = Depends(session_db),
            corpus: Corpus = Depends(corpus_courant), reglages: Parametres = Depends(parametres)):
    return _page(request, session, langue, "accueil.html",
                 faq=_apercu_faq(corpus, langue, reglages, NB_QUESTIONS_ACCUEIL))


@routeur.post("/{langue}/question")
def question_formulaire(
    request: Request,
    langue: str = LANGUE,
    texte: str = Form(default=""),
    session: Session = Depends(session_db),
    corpus: Corpus = Depends(corpus_courant),
    reglages: Parametres = Depends(parametres),
):
    faq = _apercu_faq(corpus, langue, reglages, NB_QUESTIONS_ACCUEIL)
    _verifier_langue(session, langue)
    t = textes(langue)
    if not limiteurs()[0].autoriser(_adresse(request)):
        return _page(request, session, langue, "accueil.html", TROP_DE_REQUETES,
                     faq=faq, erreur=t["trop_de_requetes"])
    texte = texte.strip()
    if not texte or len(texte) > 500:
        return _page(request, session, langue, "accueil.html", ENTITE_INVALIDE,
                     faq=faq, erreur=t["question_vide"], saisie=texte[:500])
    reponse = connaissances.traiter_question(
        session, corpus, reglages, canal=Canal.WEB, texte=texte, langue=langue
    )
    return _page(request, session, langue, "accueil.html", faq=faq,
                 echange={"question": texte, "reponse": reponse})


@routeur.post("/api/portail/question", response_model=ReponseSortie)
def question_json(
    entree: QuestionPortail,
    request: Request,
    session: Session = Depends(session_db),
    corpus: Corpus = Depends(corpus_courant),
    reglages: Parametres = Depends(parametres),
):
    """Utilisé par portail.js. Même contrat que POST /v1/questions, sans clé d'API."""
    _verifier_langue(session, entree.langue)
    if not limiteurs()[0].autoriser(_adresse(request)):
        return JSONResponse({"detail": textes(entree.langue)["trop_de_requetes"]},
                            status_code=TROP_DE_REQUETES)
    return connaissances.traiter_question(
        session, corpus, reglages, canal=Canal.WEB, texte=entree.texte, langue=entree.langue
    )


@routeur.get("/{langue}/faq")
def faq(request: Request, langue: str = LANGUE, session: Session = Depends(session_db),
        corpus: Corpus = Depends(corpus_courant), reglages: Parametres = Depends(parametres)):
    return _page(request, session, langue, "faq.html", faq=_apercu_faq(corpus, langue, reglages))


@routeur.get("/{langue}/signaler")
def signaler(request: Request, langue: str = LANGUE, session: Session = Depends(session_db)):
    return _page(request, session, langue, "signaler.html",
                 provinces=territoires.lister(session), saisie={})


@routeur.post("/{langue}/signaler")
def signaler_envoi(
    request: Request,
    langue: str = LANGUE,
    type: str = Form(default=""),
    territoire_code: str = Form(default=""),
    localite: str = Form(default=""),
    description: str = Form(default=""),
    session: Session = Depends(session_db),
    reglages: Parametres = Depends(parametres),
):
    t = textes(langue)
    saisie = {"type": type, "territoire_code": territoire_code,
              "localite": localite, "description": description}

    def reafficher(statut: int, erreur: str):
        return _page(request, session, langue, "signaler.html", statut,
                     provinces=territoires.lister(session), saisie=saisie, erreur=erreur)

    _verifier_langue(session, langue)
    if not limiteurs()[1].autoriser(_adresse(request)):
        return reafficher(TROP_DE_REQUETES, t["trop_de_requetes"])
    try:
        entree = SignalementEntree(
            type=type, territoire_code=territoire_code,
            localite=localite.strip() or None, description=description.strip() or None,
        )
    except ValidationError:
        return reafficher(ENTITE_INVALIDE, t["signalement_invalide"])
    if not territoires.territoire_existe(session, entree.territoire_code):
        return reafficher(ENTITE_INVALIDE, t["signalement_invalide"])
    signalements.creer(session, entree, Canal.WEB, reglages.pepper_telephone)
    return _page(request, session, langue, "merci.html")
