# Serveur téléphonique (Asterisk 20)

Le centre d'appels du numéro vert repose sur Asterisk 20, une version maintenue à long terme, construite sur Alpine Linux.

## Parcours d'un appel

```
Numéro vert ─► accueil (annonce de l'enregistrement) ─► choix de la langue
            ─► menu : « Tapez 1 pour : <question> … Pour un conseiller, tapez 0 »
                 ├─ réponse écoutée (contenu validé BCR) ─► retour au menu
                 ├─ 9 ─► question dite ─► « Vous voulez savoir : <question> ? 1 oui, 2 non »
                 │        ├─ 1 ─► réponse écoutée ─► retour au menu
                 │        └─ 2 ou incomprise ─► un nouvel essai, puis conseiller
                 └─ 0 ─► file d'attente (musique, annonce toutes les 45 s)
                           ├─ un agent décroche ─► conversation enregistrée
                           └─ attente > RAPPEL_APRES_SECONDES, ou aucun agent connecté
                                 ─► « Tapez 1 pour être rappelé » ─► demande de rappel
```

Asterisk ne garde rien : il signale chaque étape au cœur (`POST /v1/appels/evenements`, clé du canal `centre_ecoute`). C'est le cœur qui compte les appels, ne garde que l'empreinte des numéros et chiffre les numéros à rappeler.

| Fichier | Rôle |
| --- | --- |
| `config/` | Modèles de configuration. Les `{{MARQUEURS}}` sont remplacés au démarrage par les variables d'environnement |
| `config/extensions.conf` | Le parcours de l'appel ci-dessus, commenté |
| `synchro/configurer.py` | Rend la configuration, installe les messages vocaux, prépare les dossiers |
| `synchro/synchroniser_svi.py` | Toutes les 5 min : lit le menu dans l'API, prépare les audios, régénère le menu |
| `synchro/question_vocale.py` | AGI de la touche 9 : envoie la question dite au cœur, puis l'efface |
| `messages/` | Messages vocaux enregistrés (voir `messages/LISEZMOI.md`) |

## Fiche technique pour l'opérateur (numéro vert)

À transmettre à Vodacom, Airtel ou Orange lors de la négociation :

| Élément | Besoin |
| --- | --- |
| Type de liaison | **SIP trunk** (RFC 3261) sur UDP 5060, avec authentification par adresse IP ou par compte (enregistrement SIP) |
| Canaux simultanés | **10 au minimum** pour le pic de mai-juin 2027 (6 agents, plus les appelants dans le serveur vocal ou en attente) |
| Codecs | G.711 A-law (de préférence) ou µ-law |
| Touches (DTMF) | RFC 4733 (RFC 2833) |
| Numéro présenté | Numéro de l'appelant transmis (sans lui, le rappel est impossible) |
| Appels sortants | Autorisés vers les mobiles RDC, pour les rappels |
| Hébergement | Serveur en RDC, adresse IP publique fixe. Ports à ouvrir : UDP 5060 (SIP) et UDP 10000-10050 (audio) **depuis l'opérateur uniquement** |

Une fois la liaison obtenue, renseigner dans `.env` les variables `OPERATEUR_SIP_HOTE`, `OPERATEUR_SIP_PORT`, `OPERATEUR_SIP_UTILISATEUR`, `OPERATEUR_SIP_MDP`, `OPERATEUR_SIP_ENREGISTREMENT` et `SIP_ADRESSE_EXTERNE`, puis lancer `docker compose up -d asterisk`.

## Tester sans opérateur

- **Automatiquement** : avec `TELEPHONIE_SIMULATION=true`, `python outils/verifier_telephonie.py` passe trois appels simulés (réponse du SVI, rappel, agent) et contrôle le résultat, y compris l'absence de numéro en clair. Durée : environ 2 min 30. `python outils/verifier_question_vocale.py` vérifie la touche 9 avec un faux service de transcription (environ 2 min 30, réglages de transcription rétablis à la fin).
- **À l'oreille** : renseigner `SIMULATEUR_MDP`, puis configurer un téléphone logiciel (MicroSIP, Linphone) avec l'utilisateur `simulateur`, ce mot de passe et le serveur `localhost:5060`. Appeler n'importe quel numéro : on suit le parcours d'un vrai appel.

## Postes des agents (WebRTC)

Les agents téléphonent depuis la console du tableau de bord (`/tableau-de-bord/agent`). Le navigateur se connecte à Asterisk en WebSocket (port 8088) avec le compte du poste. Le mot de passe est dérivé de `SECRET_POSTES` et remis par le cœur à l'agent connecté.

Trois réglages sont indispensables, et chacun a été vérifié par `outils/verifier_console_agent.py` :

- **G.711 seulement** (`allow=alaw,ulaw`) : Asterisk n'a pas de transcodeur Opus libre, et un appel négocié en Opus serait coupé au décroché.
- **`rewrite_contact=yes`** : le navigateur annonce une adresse de contact fictive. Sans cette option, Asterisk ne le joint pas et le poste reste « indisponible ».
- **Nom d'hôte fixe et valide** (`hostname: telephonie` dans `docker-compose.yml`) et **`from_domain`** : JsSIP rejette les messages qui portent le nom aléatoire d'un conteneur.

L'audio passe en UDP (ports 10000-10050). `SIP_ADRESSE_EXTERNE` est annoncée aux navigateurs à la place de l'adresse interne du conteneur : `127.0.0.1` sur un poste de développement, l'adresse IP publique en production.

**En production**, le port 8088 doit être publié **en `wss://` derrière le proxy HTTPS**, car les navigateurs refusent le micro hors HTTPS. L'adresse correspondante va dans `ASTERISK_WS_URL`.

## Question dite (touche 9)

La touche 9 n'est proposée que dans les langues dont la voix est transcrite (réglage `transcription_langues`, voir `transcription/LISEZMOI.md`) : c'est le même service de transcription que pour les messages vocaux WhatsApp, avec la même règle. Le sujet compris est **toujours confirmé** par le citoyen (touche 1) avant la réponse ; une mauvaise compréhension coûte un « 2 », jamais une fausse information. Après deux refus ou une question incomprise, l'appel passe à un conseiller.

- La question est enregistrée (20 s au plus, 3 s de silence ou dièse pour finir) dans `/dev/shm/rgph-questions`, **en mémoire** ; l'AGI l'envoie au cœur (`POST /v1/appels/question-vocale`) puis la supprime. Si le citoyen raccroche pendant l'enregistrement, Asterisk l'efface.
- Le cœur ne garde que la transcription **masquée**, le temps de la confirmation, puis la journalise comme une question écrite (`entree = voix`). Il l'efface à la fin de l'appel.
- Toute réponse publiée peut être proposée, pas seulement les huit du menu : le serveur vocal prépare l'audio de tout le catalogue dans ces langues. Un sujet dont l'audio manque passe au conseiller.
- **Qualité au téléphone** : le son est en 8 kHz, moins bon que celui des messages WhatsApp. Le taux d'erreur mesuré sur FLEURS ne vaut pas pour le téléphone : il faut évaluer chaque langue sur de vrais appels avant de l'ouvrir.

## Données personnelles

- **Pas de CDR ni de CEL** : ils garderaient les numéros en clair. Le journal de la file (`queue_log`) et les messages détaillés (`verbose`) sont aussi désactivés pour la même raison.
- **Enregistrements** : ils sont écrits dans le volume `enregistrements`, partagé avec l'API, qui les supprime après `CONSERVATION_ENREGISTREMENTS_JOURS` (90 par défaut). Chaque appel commence par l'annonce de l'enregistrement.

## Exploitation

```bash
docker compose exec asterisk asterisk -rx "queue show rgph"          # agents et appels en attente
docker compose exec asterisk asterisk -rx "pjsip show endpoints"     # postes connectés
docker compose exec asterisk asterisk -rx "dialplan show svi-fr"     # menu français actuel
docker compose exec asterisk python3 /opt/rgph/synchro/synchroniser_svi.py   # mise à jour immédiate du SVI
```

Au démarrage, le message `There are no local system nameservers configured` est sans conséquence : PJSIP utilise alors la résolution DNS du système.
