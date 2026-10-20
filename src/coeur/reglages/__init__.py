"""Réglages du cœur gardés en base, chiffrés.

Deux étages :
- `.env` ne garde que ce qu'il faut avant d'atteindre la base, ou ce que lisent
  d'autres conteneurs (PostgreSQL, Directus, Asterisk, Kannel), plus CLE_MAITRE ;
- la table `coeur.reglages` garde le reste (pepper, clés, WhatsApp, numéro vert…),
  chaque valeur chiffrée avec CLE_MAITRE (Fernet : AES-128-CBC + HMAC-SHA256).

Une sauvegarde de la base, seule, ne révèle donc aucun secret : il faut aussi
CLE_MAITRE, rangée à part dans un coffre-fort. Une variable d'environnement du même
nom l'emporte toujours sur la base (tests, dépannage).

    python -m coeur.reglages initialiser     # assistant, à la mise en service
    python -m coeur.reglages lister          # valeurs (secrets masqués)
    python -m coeur.reglages definir numero_vert "0800 000 000"
"""
