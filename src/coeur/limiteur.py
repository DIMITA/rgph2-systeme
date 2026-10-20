"""Limitation du nombre de requêtes par adresse IP, contre les abus.

Les adresses ne sont gardées qu'en mémoire, le temps de la fenêtre, et jamais
enregistrées. Chaque processus a ses propres compteurs : avec plusieurs
processus, la limite effective est multipliée d'autant.
"""

import threading
import time
from collections import deque


class LimiteurDebit:
    def __init__(self, limite: int, fenetre_secondes: float):
        self.limite = limite
        self.fenetre = fenetre_secondes
        self._appels: dict[str, deque[float]] = {}
        self._verrou = threading.Lock()

    def autoriser(self, cle: str, maintenant: float | None = None) -> bool:
        maintenant = time.monotonic() if maintenant is None else maintenant
        with self._verrou:
            self._oublier_inactifs(maintenant)
            appels = self._appels.setdefault(cle, deque())
            if len(appels) >= self.limite:
                return False
            appels.append(maintenant)
            return True

    def _oublier_inactifs(self, maintenant: float) -> None:
        limite = maintenant - self.fenetre
        for cle in list(self._appels):
            appels = self._appels[cle]
            while appels and appels[0] <= limite:
                appels.popleft()
            if not appels:
                del self._appels[cle]

    def nb_adresses_suivies(self) -> int:
        return len(self._appels)

    def reinitialiser(self) -> None:
        with self._verrou:
            self._appels.clear()
