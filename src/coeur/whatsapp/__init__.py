"""Canal WhatsApp : API officielle de Meta (« Cloud API »), reliée à la base fermée.

Meta appelle le webhook /v1/whatsapp/webhook à chaque message ; le bot répond par
l'API Graph, avec des listes et des boutons. Les messages transitent par Meta (hors
de RDC) : seule l'empreinte du numéro est conservée ici. Voir whatsapp/LISEZMOI.md.
"""
