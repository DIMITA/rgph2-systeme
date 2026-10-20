"""Ce que demande l'assistant d'initialisation, et ce qui doit rester dans .env."""

import secrets
from collections.abc import Callable
from dataclasses import dataclass

from cryptography.fernet import Fernet

# Lus avant d'atteindre la base, ou aussi par d'autres conteneurs (Asterisk, Kannel,
# Directus) qui ne lisent pas cette table : ils restent dans .env (voir
# outils/preparer_env.py), et `definir` les refuse.
ENV_SEULEMENT = frozenset({
    "environnement", "database_url", "directus_url", "fuseau_horaire",
    "cles_api", "cle_api_centre_ecoute",
    "secret_postes", "nb_postes", "svi_touches_langues", "sip_domaine", "asterisk_ws_url",
    "dossier_enregistrements", "sms_passerelle", "kannel_url", "kannel_utilisateur",
    "kannel_mdp", "simulateur_mobile", "transcription_url",
})


def _jeton(octets: int) -> Callable[[], str]:
    return lambda: secrets.token_urlsafe(octets)


@dataclass(frozen=True)
class Question:
    champ: str
    libelle: str
    aide: str = ""
    secret: bool = False
    # Valeur tirée au hasard à la première initialisation ; jamais demandée.
    generer: Callable[[], str] | None = None
    choix: tuple[str, ...] = ()
    # Ne poser la question que si cette condition sur les réponses précédentes est vraie.
    si: Callable[[dict[str, str]], bool] | None = None


def _whatsapp_meta(valeurs: dict[str, str]) -> bool:
    return valeurs.get("whatsapp_passerelle") == "meta"


QUESTIONS = (
    # --- Secrets tirés au hasard : personne n'a à les connaître -----------------------------
    Question("pepper_telephone", "Clé des empreintes de numéros",
             "NE JAMAIS LA CHANGER en cours d'opération : les usagers ne seraient plus reconnus.",
             secret=True, generer=_jeton(48)),
    Question("cle_chiffrement", "Clé de chiffrement des numéros à rappeler (Fernet)",
             secret=True, generer=lambda: Fernet.generate_key().decode()),
    Question("secret_session", "Secret du cookie du tableau de bord", secret=True,
             generer=_jeton(48)),
    Question("cle_ministere", "Clé d'API du Ministère (statistiques, signalements)",
             "À remettre à l'équipe du Ministère qui interroge l'API.", secret=True,
             generer=_jeton(24)),
    Question("whatsapp_jeton_verification", "Jeton de vérification du webhook WhatsApp",
             "Choisi par nous, à recopier chez Meta à l'abonnement du webhook.", secret=True,
             generer=_jeton(24)),
    # --- À fournir par une personne ---------------------------------------------------------
    Question("numero_vert", "Numéro vert",
             "Tel qu'il s'affiche (ex. « 0800 000 000 »). Vide tant qu'il n'est pas attribué."),
    Question("ussd_code", "Code court USSD",
             "Ex. « *123# ». Vide tant que l'ARPTC ne l'a pas attribué."),
    Question("whatsapp_passerelle", "Passerelle WhatsApp",
             "« simulation » tant que le compte Meta n'est pas ouvert, puis « meta ».",
             choix=("simulation", "meta")),
    Question("whatsapp_numero_id", "Identifiant du numéro WhatsApp (Phone number ID)",
             "Console Meta, produit WhatsApp, « Configuration de l'API ».", si=_whatsapp_meta),
    Question("whatsapp_jeton", "Jeton d'accès permanent WhatsApp",
             "Jeton d'un utilisateur système (permission whatsapp_business_messaging).",
             secret=True, si=_whatsapp_meta),
    Question("whatsapp_secret_app", "Secret de l'application Meta",
             "Paramètres de l'application, « Clé secrète » : vérifie chaque message reçu.",
             secret=True, si=_whatsapp_meta),
    Question("transcription", "Transcription des messages vocaux",
             "« aucune » tant que le service n'est pas démarré, puis « service ».",
             choix=("aucune", "service")),
    Question("transcription_langues", "Langues dont les messages vocaux sont transcrits",
             "Ouvertes une à une après évaluation (ex. « sw,ln »). Vide : aucune.",
             si=lambda v: v.get("transcription") == "service"),
    Question("conservation_texte_questions", "Texte des questions gardé dans le journal",
             "À arbitrer par le point focal protection des données.",
             choix=("tout", "escalades", "aucun")),
)

SECRETS = frozenset(q.champ for q in QUESTIONS if q.secret)
