"""Contenus de démonstration, en français uniquement.

Ils servent aux tests et aux démonstrations. Ce sont des **exemples** : ils n'ont
pas été validés par le BCR et ne doivent jamais être chargés en production
(la commande de chargement le refuse si ENVIRONNEMENT=production).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from coeur.connaissances.modeles import Contenu, Formulation, Traduction

AVERTISSEMENT = "[EXEMPLE non validé] "

EXEMPLES: list[dict] = [
    {
        "cle": "exemple-calendrier-passage",
        "categorie": "calendrier",
        "question": "Quand les agents recenseurs passeront-ils chez moi ?",
        "reponse": "Les agents recenseurs passent dans tous les ménages pendant la période "
        "du dénombrement. La date exacte pour votre territoire est annoncée par les autorités locales.",
        "reponse_courte": "Les agents passent pendant le dénombrement. Date de votre territoire : "
        "annoncée par les autorités locales.",
        "formulations": [
            "date de passage des agents",
            "quel jour le recensement arrive dans mon quartier",
            "calendrier du recensement",
        ],
    },
    {
        "cle": "exemple-verifier-agent",
        "categorie": "agents",
        "question": "Comment reconnaître un vrai agent recenseur ?",
        "reponse": "Un agent recenseur porte un badge officiel avec sa photo et un numéro. "
        "Vous pouvez vérifier ce numéro par SMS ou auprès du centre d'écoute.",
        "reponse_courte": "Un vrai agent porte un badge officiel avec photo et numéro, "
        "vérifiable par SMS.",
        "formulations": ["vérifier un agent", "badge de l'agent", "faux agent recenseur"],
    },
    {
        "cle": "exemple-confidentialite",
        "categorie": "confidentialite",
        "question": "Mes réponses au recensement sont-elles confidentielles ?",
        "reponse": "Oui. Vos réponses sont protégées par la loi et servent uniquement "
        "à produire des statistiques. Elles ne sont transmises à aucune autre administration.",
        "reponse_courte": "Oui, vos réponses sont confidentielles et servent seulement aux statistiques.",
        "formulations": ["qui peut voir mes réponses", "mes données sont-elles protégées"],
    },
    {
        "cle": "exemple-menage-non-visite",
        "categorie": "signalement",
        "question": "Mon ménage n'a pas été recensé, que faire ?",
        "reponse": "Signalez-le par SMS, sur WhatsApp ou au centre d'écoute en indiquant "
        "votre territoire et votre quartier ou village. Une équipe viendra vous recenser.",
        "reponse_courte": "Signalez-le par SMS ou au centre d'écoute avec votre territoire "
        "et votre quartier.",
        "formulations": ["personne n'est venu chez moi", "on m'a oublié", "pas été recensé"],
    },
    {
        "cle": "exemple-pourquoi-recensement",
        "categorie": "general",
        "question": "À quoi sert le recensement général de la population ?",
        "reponse": "Le recensement permet de connaître le nombre d'habitants et leurs "
        "conditions de vie, pour mieux planifier les écoles, les hôpitaux et les routes.",
        "reponse_courte": "Il sert à compter la population pour planifier écoles, hôpitaux et routes.",
        "formulations": ["pourquoi faire un recensement", "utilité du recensement"],
    },
]


def charger_exemples(session: Session, statut: str = "publie") -> list[int]:
    """Insère les exemples (s'ils n'existent pas déjà) et renvoie leurs identifiants."""
    ids = []
    for ex in EXEMPLES:
        existant = session.scalar(select(Contenu).where(Contenu.cle == ex["cle"]))
        if existant:
            ids.append(existant.id)
            continue
        contenu = Contenu(cle=ex["cle"], categorie=ex["categorie"], statut=statut)
        session.add(contenu)
        session.flush()
        session.add(
            Traduction(
                contenu_id=contenu.id,
                langue_code="fr",
                question=ex["question"],
                reponse=AVERTISSEMENT + ex["reponse"],
                reponse_courte=ex["reponse_courte"],
                statut=statut,
            )
        )
        for texte in ex["formulations"]:
            session.add(Formulation(contenu_id=contenu.id, langue_code="fr", texte=texte))
        ids.append(contenu.id)
    session.commit()
    return ids
