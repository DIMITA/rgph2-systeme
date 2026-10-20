from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from coeur.base import session_db
from coeur.commun import Canal
from coeur.config import Parametres, parametres
from coeur.confidentialite.service import empreinte_telephone
from coeur.connaissances import service
from coeur.connaissances.depot import Corpus, cache
from coeur.connaissances.schemas import ContenuSortie, QuestionEntree, ReponseSortie
from coeur.interactions import service as interactions
from coeur.securite import canal_appelant
from coeur.territoires.service import territoire_existe

# 422 : écrit en clair, le nom de la constante a changé selon les versions de Starlette.
ENTITE_INVALIDE = 422

routeur = APIRouter(prefix="/v1", tags=["base de connaissances"])

PARAM_LANGUE = Query(default="fr", pattern=r"^[a-z]{2,3}$")


def corpus_courant(
    session: Session = Depends(session_db), reglages: Parametres = Depends(parametres)
) -> Corpus:
    return cache.obtenir(session, reglages.cache_contenus_secondes)


@routeur.post("/questions", response_model=ReponseSortie)
def poser_question(
    entree: QuestionEntree,
    canal: Canal = Depends(canal_appelant),
    session: Session = Depends(session_db),
    corpus: Corpus = Depends(corpus_courant),
    reglages: Parametres = Depends(parametres),
):
    """Point d'entrée unique de tous les canaux.

    Renvoie un contenu validé par le BCR, ou `{"type": "escalade",
    "message": "escalade vers un humain"}` : le canal doit alors passer la main
    au centre d'écoute ou à un agent.
    """
    if entree.territoire_code and not territoire_existe(session, entree.territoire_code):
        raise HTTPException(ENTITE_INVALIDE, "Territoire inconnu")

    reponse = service.repondre(corpus, entree.texte, entree.langue, reglages)
    interactions.enregistrer(
        session,
        canal=canal,
        texte=entree.texte,
        langue_demandee=entree.langue,
        territoire_code=entree.territoire_code,
        usager_empreinte=(
            empreinte_telephone(entree.telephone, reglages.pepper_telephone)
            if entree.telephone
            else None
        ),
        reponse=reponse,
    )
    return reponse


@routeur.get("/faq", response_model=list[ContenuSortie])
def faq(
    langue: str = PARAM_LANGUE,
    _canal: Canal = Depends(canal_appelant),
    corpus: Corpus = Depends(corpus_courant),
    reglages: Parametres = Depends(parametres),
):
    """Toute la FAQ publiée dans une langue (repli en français). Utilisée par les kiosques."""
    contenus = (
        service.texte_servi(corpus, cid, langue, reglages.langue_par_defaut)
        for cid in corpus.ids_contenus()
    )
    return [c for c in contenus if c is not None]


@routeur.get("/contenus/{contenu_id}", response_model=ContenuSortie)
def lire_contenu(
    contenu_id: int,
    langue: str = PARAM_LANGUE,
    _canal: Canal = Depends(canal_appelant),
    corpus: Corpus = Depends(corpus_courant),
    reglages: Parametres = Depends(parametres),
):
    contenu = service.texte_servi(corpus, contenu_id, langue, reglages.langue_par_defaut)
    if contenu is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Contenu inexistant ou non publié")
    return contenu
