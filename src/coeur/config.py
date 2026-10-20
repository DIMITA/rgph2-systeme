"""Paramètres de l'application, lus dans les variables d'environnement (ou le fichier .env)."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from coeur.commun import Canal


class Parametres(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environnement: str = "developpement"

    # Connexion de l'API (rôle rgph_api : lecture seule sur les contenus du CMS).
    database_url: str

    # Clé secrète servant à calculer l'empreinte des numéros de téléphone.
    # La perdre empêche de relier les nouvelles interactions aux anciennes ;
    # la divulguer permet de retrouver un numéro par essais successifs.
    pepper_telephone: str = Field(min_length=32)

    # Une clé par canal, au format "canal:cle,canal:cle".
    cles_api: str = ""
    # Clé du canal centre_ecoute, partagée avec le serveur téléphonique (Asterisk).
    cle_api_centre_ecoute: str = ""
    # Clé réservée au Ministère (statistiques, liste des signalements).
    cle_ministere: str = Field(min_length=16)

    # Base de connaissances fermée : en dessous de ce score, on escalade vers un humain.
    seuil_confiance: float = 0.5
    # Si deux contenus différents ont des scores plus proches que cette marge, on escalade.
    marge_ambiguite: float = 0.1
    # Toute case statistique strictement inférieure à ce seuil (et non nulle) est masquée.
    seuil_secret_statistique: int = 5
    # Durée pendant laquelle les contenus publiés restent en mémoire avant relecture.
    cache_contenus_secondes: int = 60
    langue_par_defaut: str = "fr"

    # Portail web
    # Vide tant que le numéro n'est pas attribué : le portail n'en affiche alors aucun.
    numero_vert: str = ""
    # Limites par adresse IP (gardées en mémoire, jamais enregistrées).
    portail_questions_par_minute: int = 20
    portail_signalements_par_heure: int = 5

    # Tableau de bord : connexion avec les comptes Directus.
    directus_url: str = "http://directus:8055"
    # Rôles Directus admis dans chaque espace (listes séparées par des virgules).
    roles_tableau_de_bord: str = "Administrator,Validateur BCR,Tableau de bord"
    roles_agents: str = "Administrator,Agent centre d'appels"
    roles_qualite: str = "Administrator,Superviseur qualité"
    # Signe le cookie de session du tableau de bord (32 caractères au moins).
    secret_session: str = Field(min_length=32)
    # À activer en production (HTTPS) : le cookie n'est alors jamais envoyé en clair.
    session_https_seulement: bool = False
    # Heure affichée dans le tableau de bord (la base enregistre en UTC).
    # La RDC a deux fuseaux : Africa/Kinshasa (UTC+1) et Africa/Lubumbashi (UTC+2).
    fuseau_horaire: str = "Africa/Kinshasa"

    # Centre d'appels
    # Chiffre les numéros des demandes de rappel (clé Fernet : 44 caractères).
    cle_chiffrement: str = Field(min_length=44)
    # Sert à calculer le mot de passe SIP de chaque poste d'agent (partagé avec Asterisk).
    secret_postes: str = Field(min_length=32)
    nb_postes: int = 6
    # Touches du choix de la langue au téléphone (enregistrées dans les messages vocaux).
    svi_touches_langues: str = "fr:1,ln:2,sw:3,kg:4,lua:5"
    dossier_enregistrements: str = "/donnees/enregistrements"
    conservation_enregistrements_jours: int = 90
    conservation_rappels_jours: int = 7
    # Adresse WebSocket d'Asterisk vue du navigateur des agents (wss:// en production).
    asterisk_ws_url: str = "ws://localhost:8088/ws"
    # Domaine SIP des postes (indifférent pour Asterisk, qui identifie par l'utilisateur).
    sip_domaine: str = "rgph2.local"

    def roles_par_espace(self) -> dict[str, set[str]]:
        """Espace (pilotage, agents, qualite) → rôles Directus admis."""
        def liste(texte: str) -> set[str]:
            return {r.strip() for r in texte.split(",") if r.strip()}

        return {"pilotage": liste(self.roles_tableau_de_bord),
                "agents": liste(self.roles_agents),
                "qualite": liste(self.roles_qualite)}

    def roles_autorises(self) -> set[str]:
        return set().union(*self.roles_par_espace().values())

    def cles_par_canal(self) -> dict[str, Canal]:
        """Associe chaque clé d'API au canal qu'elle identifie."""
        resultat: dict[str, Canal] = {}
        for paire in filter(None, (p.strip() for p in self.cles_api.split(","))):
            canal, _, cle = paire.partition(":")
            if not cle:
                raise ValueError(f"Entrée CLES_API invalide : {paire!r} (attendu canal:cle)")
            resultat[cle.strip()] = Canal(canal.strip())
        if self.cle_api_centre_ecoute:
            resultat[self.cle_api_centre_ecoute] = Canal.CENTRE_ECOUTE
        return resultat

    def touches_langues(self) -> dict[str, int]:
        """Code de langue → touche du téléphone (ex. {"fr": 1, "ln": 2})."""
        resultat = {}
        for paire in filter(None, (p.strip() for p in self.svi_touches_langues.split(","))):
            code, _, touche = paire.partition(":")
            resultat[code.strip()] = int(touche)
        return resultat


@lru_cache
def parametres() -> Parametres:
    return Parametres()
