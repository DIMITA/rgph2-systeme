"""Centre d'appels : serveur vocal (SVI), file d'attente, rappels et enregistrements.

La téléphonie elle-même tourne dans Asterisk (dossier asterisk/). Comme tout
canal, Asterisk parle au cœur par l'API, avec la clé du canal centre_ecoute :
il lit le menu du SVI et signale les étapes de chaque appel.
"""
