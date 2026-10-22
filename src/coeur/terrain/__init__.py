"""Canaux de terrain : kiosques OKAPI et Ambassadeurs.

Une même application hors-ligne (`statique/`, servie sous /terrain/) tourne sur la
tablette d'un kiosque ou sur le téléphone d'un Ambassadeur. Chaque appareil est
enrôlé avec son propre jeton, révocable depuis le tableau de bord. Il télécharge un
« paquet » (FAQ publiée, calendrier, territoires) quand il a du réseau, et envoie
plus tard ce qu'il a recueilli hors ligne (« remontées ») : consultations, questions
restées sans réponse, signalements, rumeurs.
"""
