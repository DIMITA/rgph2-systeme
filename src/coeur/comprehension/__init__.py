"""Compréhension des langues nationales : de la voix au texte.

La reconnaissance du *sujet* d'une question reste dans `connaissances` (moteur de
recherche interchangeable, base fermée). Ce module ne fait que transcrire la voix
en texte, avec un transcripteur interchangeable :

- `aucune` : pas de transcription ; les messages vocaux reçoivent une proposition
  de rappel par un conseiller ;
- `service` : un service HTTP du projet (conteneur `transcription`, modèle open
  source hébergé en RDC), ou tout autre service qui respecte le même contrat ;
- `simulation` : le « son » est le texte lui-même (tests, simulateur).

Une langue n'est transcrite que si elle figure dans TRANSCRIPTION_LANGUES : on
l'ouvre après l'avoir évaluée sur de vrais messages (voir connaissances.evaluation).
"""
