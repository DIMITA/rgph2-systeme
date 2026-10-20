"""Configuration commune : valeurs de test, fixées avant tout import de l'application."""

import os

URL_API = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://rgph_api:test_api@localhost:5433/rgph_test"
)
URL_ADMIN = os.environ.get(
    "TEST_DATABASE_URL_ADMIN", "postgresql+psycopg://rgph_admin:test_admin@localhost:5433/rgph_test"
)
URL_DIRECTUS = os.environ.get(
    "TEST_DATABASE_URL_DIRECTUS",
    "postgresql+psycopg://rgph_directus:test_directus@localhost:5433/rgph_test",
)

CLE_WEB = "cle-web-test"
CLE_USSD = "cle-ussd-test"
CLE_MINISTERE = "cle-ministere-test-0000"
CLE_CENTRE = "cle-centre-ecoute-test"
PEPPER = "pepper-de-test-" + "x" * 32

os.environ.update(
    {
        "ENVIRONNEMENT": "test",
        "DATABASE_URL": URL_API,
        "PEPPER_TELEPHONE": PEPPER,
        "CLES_API": f"web:{CLE_WEB},ussd:{CLE_USSD}",
        "CLE_MINISTERE": CLE_MINISTERE,
        "CACHE_CONTENUS_SECONDES": "0",
        "SEUIL_CONFIANCE": "0.5",
        "MARGE_AMBIGUITE": "0.1",
        "SEUIL_SECRET_STATISTIQUE": "5",
        "NUMERO_VERT": "0800 000 000",
        "PORTAIL_QUESTIONS_PAR_MINUTE": "20",
        "PORTAIL_SIGNALEMENTS_PAR_HEURE": "5",
        "SECRET_SESSION": "secret-de-session-de-test-" + "y" * 32,
        "DIRECTUS_URL": "http://directus-factice",
        "CLE_API_CENTRE_ECOUTE": CLE_CENTRE,
        "CLE_CHIFFREMENT": "pkbHRqzm-cAjAYvBEXdIrFOhAl5an6FKkNrvaL6cmOQ=",
        "SECRET_POSTES": "secret-des-postes-de-test-" + "z" * 32,
        # Indépendants du .env local du développeur.
        "SMS_PASSERELLE": "simulation",
        "SIMULATEUR_MOBILE": "false",
        "SMS_REPONSES_PAR_JOUR": "10",
        "SMS_SEGMENTS_MAX": "3",
        "BADGES_VERIFICATIONS_PAR_HEURE": "10",
        "WHATSAPP_PASSERELLE": "simulation",
        "WHATSAPP_SECRET_APP": "secret-app-whatsapp-test",
        "WHATSAPP_JETON_VERIFICATION": "jeton-verification-test",
    }
)
