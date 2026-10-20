"""Journal d'accès sans données personnelles.

Les passerelles d'opérateur (Kannel pour les SMS) transmettent le numéro, le texte
du message et leur clé dans l'adresse (`?de=…&texte=…&cle=…`). Le journal d'accès
d'uvicorn écrirait tout cela en clair : on n'y garde que le chemin.
"""

import logging


class SansParametres(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Format d'uvicorn : (client, méthode, chemin complet, version HTTP, statut).
        if isinstance(record.args, tuple) and len(record.args) == 5:
            client, methode, chemin, version, statut = record.args
            record.args = (client, methode, str(chemin).split("?", 1)[0], version, statut)
        return True


def proteger_journal_acces() -> None:
    journal = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, SansParametres) for f in journal.filters):
        journal.addFilter(SansParametres())
