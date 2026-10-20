# USSD et SMS : passerelles et fiche pour l'opérateur

## Parcours d'un message

```
SMS du citoyen ──► opérateur ──SMPP──► Kannel (conteneur sms) ──GET /v1/sms/entrant──► cœur
                                            ▲                                          │
réponse SMS ◄── opérateur ◄──SMPP──────────┘◄──────── sendsms (port 13013) ────────────┘

*xxx# du citoyen ──► opérateur ──► agrégateur USSD ──POST /v1/ussd──► cœur ──► « CON … » / « END … »
```

- **SMS** : **Kannel 1.4.5**, la passerelle SMS open source de référence, hébergée avec le cœur. Elle se branche directement chez l'opérateur, en SMPP : aucun service étranger ne voit passer les messages, conformément à l'exigence de localisation des données.
- **USSD** : l'opérateur ou son agrégateur appelle l'API en HTTP. Le cœur reçoit à chaque échange **toute la saisie depuis le début** (`1*2*3`) et rejoue le menu : aucune session n'est gardée côté serveur.

| Fichier | Rôle |
| --- | --- |
| `kannel.conf.modele` | Configuration de Kannel. Les `{{MARQUEURS}}` sont remplacés au démarrage |
| `smsc-operateur.conf` | Liaison SMPP de l'opérateur (`OPERATEUR_SMPP_*`) |
| `smsc-simulation.conf` | Opérateur simulé, pour les tests (`SMS_SIMULATION=true`) |
| `entrypoint.sh` | Rend la configuration et lance les deux processus de Kannel (bearerbox et smsbox) |

## Fiche technique pour l'opérateur

À transmettre à Vodacom, Airtel ou Orange, avec la demande de code court auprès de l'ARPTC.

### SMS

| Élément | Besoin |
| --- | --- |
| Liaison | **SMPP 3.4**, en mode *transceiver* (envoi et réception sur la même connexion) |
| Numéro court | Le même pour recevoir les SMS des citoyens et pour leur répondre |
| Tarification | **Gratuit pour le citoyen** (zero-rating). Les réponses sont à la charge du projet : prévoir au pic 2 à 3 SMS de réponse par message reçu (réponses longues en plusieurs parties) |
| Encodage | GSM 7 bits. Les réponses sont converties dans cet alphabet : 160 caractères par SMS, 153 par partie d'un SMS long |
| SMS longs | Concaténation (UDH) acceptée, jusqu'à 4 parties |
| Volume | À estimer avec le Ministère. Chaque numéro est plafonné à 10 réponses par jour (`SMS_REPONSES_PAR_JOUR`) |
| Hébergement | Serveur en RDC. Connexion sortante de Kannel vers l'opérateur : le port SMPP de l'opérateur, souvent 2775, à ouvrir **vers l'opérateur uniquement** |

Une fois la liaison obtenue, renseigner `OPERATEUR_SMPP_HOTE`, `OPERATEUR_SMPP_PORT`, `OPERATEUR_SMPP_UTILISATEUR`, `OPERATEUR_SMPP_MDP` et éventuellement `OPERATEUR_SMPP_SYSTEM_TYPE` dans `.env`. Passer ensuite `SMS_SIMULATION=false` et lancer `docker compose up -d sms`.

### USSD

| Élément | Besoin |
| --- | --- |
| Code | Code court `*xxx#` attribué par l'ARPTC, **gratuit pour le citoyen** |
| Raccordement | Appel HTTP de l'agrégateur vers `https://<serveur>/v1/ussd?cle=<clé du canal ussd>` (ou en-tête `X-Cle-API`) |
| Requête | `POST`, formulaire : `sessionId`, `phoneNumber`, `serviceCode`, `text` (toute la saisie depuis le début, séparée par `*`) |
| Réponse | Texte brut : `CON <écran>` pour attendre une saisie, `END <écran>` pour clore. 182 caractères au plus |
| Délai | Réponse en moins d'une seconde en temps normal ; prévoir un délai d'expiration d'au moins 5 secondes |

C'est le format le plus répandu chez les agrégateurs. Si l'opérateur impose un autre format, par exemple l'envoi de la dernière saisie seulement, une petite route d'adaptation est à écrire (voir le README, « Faire évoluer le code »).

## Tester sans opérateur

```bash
# Envoyer un SMS au nom du 243810000000 ; la réponse s'affiche (« Got message »)
docker compose exec sms fakesmsc -H 127.0.0.1 -r 13010 -i 1 -m 1 "243810000000 1234 text AIDE"

# Vérification complète (USSD, SMS aller-retour, absence de numéro en clair)
python outils/verifier_mobile.py
```

Avec `SIMULATEUR_MOBILE=true`, la page http://localhost:8000/simulateur permet aussi de tester l'USSD et les SMS à la main.

## Données personnelles

- **Journaux de Kannel** : niveau « avertissement » seulement, sans journal d'accès. Aux niveaux inférieurs, Kannel écrirait les numéros et le texte des SMS.
- **Journal d'accès de l'API** : il ne garde que le chemin, sans les paramètres de l'adresse (numéro, texte, clé). Voir `src/coeur/journalisation.py`.
- **File d'attente** (volume `file_sms`) : SMS pas encore remis à l'opérateur. Elle se vide d'elle-même à la remise.
- **Dans la base** : l'empreinte du numéro seulement. Le journal des SMS (`coeur.sms`) ne garde ni texte ni numéro : il sert au plafond journalier et au suivi des coûts.

## Exploitation

```bash
docker compose logs sms                    # avertissements de Kannel (liaison perdue, refus…)
```

L'interface d'administration de Kannel (port 13000) n'écoute que dans le conteneur, avec un mot de passe tiré au hasard à chaque démarrage.
