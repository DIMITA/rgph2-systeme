# Tests de charge

`locustfile.py` simule les citoyens de chaque canal, au mélange attendu au pic : sessions USSD (35 %), SMS (25 %), WhatsApp (15 %), web (10 %), vérification de badge (10 %), appels au serveur vocal vus du cœur (5 %). Chaque usager simulé a son propre numéro et suit le vrai parcours de son canal, avec les vraies clés de la pile.

```bash
python -m venv .venv-charge && .venv-charge/bin/pip install -r charge/requirements.txt
set -a && . ./.env && set +a
export WHATSAPP_SECRET_APP=$(docker compose exec -T api python -c \
  "from coeur.config import parametres; print(parametres().whatsapp_secret_app)")
.venv-charge/bin/locust -f charge/locustfile.py --host http://localhost:8000 \
  --headless -u 300 -r 25 -t 150s --csv rapport
```

**Contre une pile d'essai seulement** : les échanges sont journalisés comme de vraies interactions (statistiques faussées), et les SMS partent vers Kannel.

Le chiffre à surveiller est le **p95 de « USSD écran »** : l'opérateur coupe une session USSD dont l'écran tarde (souvent 2 à 3 s). Au-delà, le citoyen voit une erreur, quel que soit le reste.

## Mesures du 20 octobre 2026

Pile Docker complète sur **une seule machine de 4 cœurs**, qui fait aussi tourner Locust (un cœur) et PostgreSQL. 150 s par palier, montée de 25 usagers par seconde.

| Configuration | Usagers | Requêtes/s | p50 | p95 | p99 | Erreurs |
| --- | --- | --- | --- | --- | --- | --- |
| Avant correction, 1 processus | 300 | 10 | 190 ms | 89 s | 91 s | 5,6 % |
| 1 processus | 300 | 97 | 460 ms | 780 ms | 940 ms | 0,08 % (keep-alive, corrigé ensuite) |
| 1 processus | 1 000 | 87 | 7,1 s | 8,7 s | 10 s | saturé |
| 3 processus, keep-alive 75 s | 1 000 | **209** | 1,3 s | 2,3 s | 2,8 s | **0** sur 31 343 |

Deux défauts trouvés et corrigés :

1. **Interblocage du pool de connexions** (la première ligne). Chaque requête tient sa connexion à PostgreSQL, puis le limiteur de débit ou la mémoire courte (USSD rejoué, message WhatsApp en double) en demandait une seconde *dans le même pool*. Sous charge, toutes les connexions étaient tenues par des requêtes qui attendaient chacune la seconde : plus rien ne passait avant le délai de 30 s, processeur au repos. Les compteurs ont maintenant leur propre petit pool (`coeur.base.moteur_court`), et un test le vérifie (`test_compteurs_disponibles_quand_le_pool_des_requetes_est_plein`).
2. **Requêtes perdues sur des connexions réutilisées** : uvicorn fermait les connexions inactives au bout de 5 s, pendant que le client en réutilisait une. Le délai est passé à 75 s (`Dockerfile`), plus long que celui d'un proxy HTTPS ou d'une passerelle.

Ce que ces chiffres disent :

- **Un processus de l'API tient environ 95 requêtes/s** sur un cœur, avec un p95 sous la seconde. Au-delà, l'attente monte vite : il faut des processus en plus (`API_PROCESSUS`, un par cœur réservé à l'API), pas des threads.
- Avec 3 processus, le débit double, mais la machine d'essai est pleine (API 2 cœurs, PostgreSQL 1,2 cœur, Locust 1) : **209 requêtes/s est un plancher**, pas la limite du logiciel. Une session USSD faisant 4 écrans, cela fait déjà environ 180 000 sessions USSD par heure.
- **PostgreSQL prend environ 0,6 cœur par 100 requêtes/s** (journal des interactions, compteurs, sessions). C'est la ressource à dimensionner en second. Au-delà de quelques processus d'API, il faut un pooler (PgBouncer) ou relever `max_connections` : chaque processus ouvre jusqu'à `BASE_CONNEXIONS_MAX` (20) + 10 connexions.

Ce que ces chiffres ne disent pas :

- Le **volume réel du pic** de mai-juin 2027 : il dépend de la campagne de communication. Le pilote donnera les proportions par canal et le nombre de requêtes par citoyen (tableau de bord) ; refaire alors la mesure **sur le serveur de production**, Locust tournant sur une autre machine.
- La **transcription** des messages vocaux n'est pas dans ce test : elle se dimensionne à part (`transcription/LISEZMOI.md`), et c'est elle qui demande un GPU.
- Les limites des **opérateurs** (débit SMPP de Kannel, nombre d'appels simultanés du trunk SIP, débit de l'API WhatsApp de Meta) : à obtenir dans les contrats (`PREREQUIS.md`).
