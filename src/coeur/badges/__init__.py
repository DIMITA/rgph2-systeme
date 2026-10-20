"""Vérification des badges d'agents recenseurs.

La liste vient de l'INS (fichier CSV). Elle ne contient ni nom ni photo : seulement
le numéro du badge, le territoire d'affectation et l'état (actif ou retiré).
Les numéros ne sont pas stockés en clair mais sous forme d'empreinte : une copie
de la table ne permet pas de fabriquer de faux badges « valides ».
"""
