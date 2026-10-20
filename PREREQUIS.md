# Prérequis : tout ce qu'il faut obtenir hors du code, et comment

Le code tourne seul en simulation. Pour ouvrir un canal aux citoyens, il faut en plus des serveurs, des accès chez les opérateurs et chez Meta, des données de l'INS, du matériel et des validations. Ce document dit, pour chaque élément : à quoi il sert, qui l'obtient, comment, et où le mettre une fois obtenu.

Les délais ne sont pas indiqués. Ils dépendent des interlocuteurs, et aucun n'est connu à ce jour. Les démarches auprès de l'ARPTC, des opérateurs et de Meta sont les plus longues et les moins maîtrisables : **elles sont à lancer en premier**.

## Où va chaque valeur

Deux endroits, et un outil pour chacun :

| Où | Quoi | Comment |
| --- | --- | --- |
| `.env` sur le serveur | Ce qu'il faut avant d'atteindre la base, et ce que lisent Directus, Asterisk ou Kannel : mots de passe PostgreSQL, `CLE_MAITRE`, liaisons SIP et SMPP des opérateurs, adresse IP publique, adresses publiques | `python outils/preparer_env.py`. Les secrets sont tirés au hasard ; seules les valeurs à fournir sont demandées. On peut le relancer quand une valeur arrive : vider la ligne dans `.env`, puis relancer |
| En base, chiffré avec `CLE_MAITRE` | Ce que seul le cœur lit : numéro vert, code USSD, WhatsApp, transcription, pepper et clés internes (tirés au hasard) | `docker compose run --rm migrations python -m coeur.reglages initialiser`, puis `… definir <réglage> [valeur]` pour une valeur obtenue plus tard. Ensuite `docker compose restart api taches` |

`CLE_MAITRE` se range dans un coffre-fort, **à part des sauvegardes de la base**. Sans elle, les réglages en base sont perdus. Avec une sauvegarde, elle révèle tous les secrets.

## Vue d'ensemble

| Élément | Pour quel canal | Qui l'obtient | Bloquant pour |
| --- | --- | --- | --- |
| [Serveurs hébergés en RDC](#1-hébergement-et-infrastructure) | Tous | Ministère / prestataire d'hébergement | Toute mise en ligne |
| [Nom de domaine et certificat HTTPS](#nom-de-domaine-et-https) | Tous | Ministère (domaine), exploitant (certificat) | Portail, WhatsApp, kiosques, console des agents |
| [Adresse IP publique fixe](#adresse-ip-publique-fixe-et-pare-feu) | Centre d'appels | Hébergeur | Numéro vert |
| [Code court USSD (et SMS)](#code-court-ussd-et-sms-arptc) | USSD, SMS | INS auprès de l'ARPTC | USSD, SMS |
| [Liaison SIP et numéro vert](#numéro-vert-et-liaison-sip) | Centre d'appels | INS auprès d'un opérateur | Centre d'appels |
| [Liaison SMPP](#liaison-smpp-sms) | SMS | INS auprès d'un opérateur | SMS |
| [Agrégateur USSD](#agrégateur-ussd) | USSD | INS auprès d'un opérateur ou agrégateur | USSD |
| [Gratuité pour le citoyen](#gratuité-pour-le-citoyen-zero-rating) | USSD, SMS, numéro vert | INS auprès des opérateurs | Accès des plus pauvres |
| [Compte WhatsApp Business vérifié](#3-whatsapp-meta) | WhatsApp | INS auprès de Meta | WhatsApp |
| [Référentiel des territoires](#référentiel-des-territoires) | Tous | INS | Mise en production |
| [Liste des badges des agents](#liste-des-badges-des-agents) | USSD, SMS, WhatsApp, kiosques | INS | Vérification des agents |
| [Contenus validés et traduits](#contenus-de-la-faq-et-calendrier) | Tous | Ministère (rédaction), BCR (validation), traducteurs | Toute réponse aux citoyens |
| [Enregistrements audio](#enregistrements-audio) | Centre d'appels, WhatsApp, kiosques | Ministère, locuteurs natifs | Serveur vocal, audio en langue locale |
| [Hébergement de l'audio](#hébergement-de-laudio) | WhatsApp, kiosques | Exploitant | Audio et vidéo des réponses |
| [Comptes des utilisateurs](#5-comptes-des-utilisateurs) | Tableau de bord, Directus | Administrateur Directus | Travail du Ministère, centre d'appels |
| [Tablettes et téléphones](#6-matériel-de-terrain-et-postes) | Kiosques, Ambassadeurs | Projet (achats) | Kiosques, Ambassadeurs |
| [Serveur de calcul et modèle de transcription](#7-transcription-des-messages-vocaux) | WhatsApp (vocal) | Ministère / hébergeur | Messages vocaux |
| [Validations juridiques et protection des données](#8-validations-et-protection-des-données) | Tous | Point focal protection des données, juristes | Ouverture de chaque canal |

---

## 1. Hébergement et infrastructure

### Serveurs en RDC

L'Ordonnance-loi n° 23/010 impose la localisation des données en RDC (voir architecture.md). Le choix entre centre de données local et cloud avec une région locale n'est pas encore fait. La pile Docker convient aux deux.

| Rôle | Point de départ | Remarques |
| --- | --- | --- |
| Cœur, base, Directus, Asterisk, Kannel | 4 cœurs, 16 Go de mémoire, 200 Go de disque SSD, Linux avec Docker et Docker Compose v2 | Les enregistrements des appels (G.711, environ 1 Mo par minute, gardés 90 jours) prennent l'essentiel du disque |
| Transcription des messages vocaux | Voir [§ 7](#7-transcription-des-messages-vocaux) | Peut tourner sur un serveur à part |

Ce sont des points de départ, sans mesure de charge : **à ajuster après le pilote**, avec les volumes réels (tableau de bord). Le niveau de disponibilité exigé au pic de mai-juin 2027 reste à décider (architecture.md). Il dira s'il faut un second serveur.

**À demander à l'hébergeur** : des serveurs en RDC, un accès administrateur (SSH), une adresse IP publique fixe, la possibilité d'ouvrir les ports ci-dessous, et un espace de sauvegarde hors du serveur.

### Nom de domaine et HTTPS

HTTPS est **obligatoire** : Meta refuse un webhook sans certificat valide, les navigateurs refusent le micro des agents hors HTTPS, et l'application des kiosques ne s'installe pas hors HTTPS.

- **Domaine** : un nom sous le domaine de l'INS ou du recensement (par exemple `info.rgph.cd`), demandé par le Ministère à son gestionnaire de domaine. Il faut de quoi publier : le portail et l'API, Directus, et le WebSocket d'Asterisk pour la console des agents (`wss://`).
- **Certificat** : gratuit avec Let's Encrypt. Un proxy comme **Caddy** l'obtient et le renouvelle tout seul.
- **Proxy HTTPS** (Caddy ou Nginx) devant l'API (port 8000), Directus (8055) et le WebSocket d'Asterisk (8088). PostgreSQL ne doit jamais être exposé.
- **Où** : dans `.env`, `FORWARDED_ALLOW_IPS` (adresse du proxy), `DIRECTUS_URL_PUBLIQUE`, `ASTERISK_WS_URL` (`wss://…`). En base : `definir session_https_seulement true`.

### Adresse IP publique fixe et pare-feu

| Port | Sens | Pour | Ouvert à |
| --- | --- | --- | --- |
| TCP 443 | Entrant | Portail, API, webhook WhatsApp, kiosques, Directus, console des agents | Tous |
| UDP 5060 | Entrant | Signalisation SIP du numéro vert | **L'opérateur seulement** |
| UDP 10000-10050 | Entrant | Audio des appels | L'opérateur et les postes des agents |
| Port SMPP de l'opérateur (souvent 2775) | Sortant | SMS | Vers l'opérateur seulement |
| TCP 443 | Sortant | API de Meta (WhatsApp), téléchargement des images Docker et du modèle de transcription | — |

- **Où** : l'adresse IP publique dans `.env`, `SIP_ADRESSE_EXTERNE`.

### Sauvegardes et coffre-fort

- **Sauvegardes de PostgreSQL** chiffrées (`pg_dump`), stockées hors du serveur. **Tester une restauration** avant l'ouverture.
- **Coffre-fort** pour `CLE_MAITRE` et le fichier `.env` : un outil open source (KeePassXC, Vaultwarden, HashiCorp Vault), avec au moins deux personnes habilitées à l'INS. `CLE_MAITRE` ne doit jamais se trouver avec les sauvegardes de la base.

---

## 2. Opérateurs télécoms et régulateur

Interlocuteurs : **ARPTC** (Autorité de régulation de la poste et des télécommunications du Congo) pour les codes courts ; **Vodacom, Airtel, Orange** pour les liaisons. Les fiches techniques à leur remettre existent déjà : [asterisk/LISEZMOI.md](asterisk/LISEZMOI.md) pour le numéro vert, [sms/LISEZMOI.md](sms/LISEZMOI.md) pour les SMS et l'USSD.

### Code court USSD (et SMS) : ARPTC

- **Quoi** : un code `*xxx#` pour l'USSD, et un numéro court pour les SMS, gratuits pour le citoyen.
- **Comment** : demande de l'INS à l'ARPTC, en général portée avec un opérateur.
- **Où** : en base, `definir ussd_code "*123#"`. Le numéro court SMS se convient avec l'opérateur ; le nom d'expéditeur va dans `sms_expediteur`.

### Numéro vert et liaison SIP

- **Quoi** : un numéro vert gratuit pour l'appelant et une liaison **SIP trunk** vers le serveur : 10 canaux simultanés au minimum, G.711, numéro de l'appelant transmis, appels sortants autorisés pour les rappels.
- **Comment** : remettre la fiche technique d'[asterisk/LISEZMOI.md](asterisk/LISEZMOI.md) à l'opérateur.
- **Ce qu'il fournit** : l'hôte SIP, le port, l'identifiant et le mot de passe (ou une authentification par adresse IP), et le numéro vert.
- **Où** : dans `.env`, `OPERATEUR_SIP_HOTE`, `OPERATEUR_SIP_PORT`, `OPERATEUR_SIP_UTILISATEUR`, `OPERATEUR_SIP_MDP`, `OPERATEUR_SIP_ENREGISTREMENT`. Puis `docker compose up -d asterisk`. Le numéro vert, en base : `definir numero_vert "0800 000 000"`.

### Liaison SMPP (SMS)

- **Quoi** : une liaison **SMPP 3.4** en mode *transceiver*, avec le numéro court, les SMS longs (jusqu'à 4 parties) et un volume estimé.
- **Comment** : remettre la fiche de [sms/LISEZMOI.md](sms/LISEZMOI.md).
- **Ce qu'il fournit** : l'hôte, le port, l'identifiant (*system_id*), le mot de passe, éventuellement le *system_type*.
- **Où** : dans `.env`, `OPERATEUR_SMPP_HOTE`, `OPERATEUR_SMPP_PORT`, `OPERATEUR_SMPP_UTILISATEUR`, `OPERATEUR_SMPP_MDP`, `OPERATEUR_SMPP_SYSTEM_TYPE`, puis `SMS_SIMULATION=false` et `docker compose up -d sms`.

### Agrégateur USSD

- **Quoi** : l'opérateur, ou son agrégateur, appelle notre API à chaque écran USSD.
- **Ce qu'on lui donne** : l'adresse `https://<domaine>/v1/ussd?cle=<clé>`. La clé est celle du canal `ussd` dans `CLES_API` (`.env`, générée par `preparer_env.py`). Le format attendu est dans [sms/LISEZMOI.md](sms/LISEZMOI.md). Si l'agrégateur en impose un autre, une petite route d'adaptation est à écrire.
- **Ce qu'il fournit** : rien à mettre chez nous, sauf, s'il l'exige, ses adresses IP à autoriser au pare-feu.

### Gratuité pour le citoyen (zero-rating)

À négocier avec chaque opérateur pour l'USSD, les SMS reçus et le numéro vert. Les réponses par SMS restent à la charge du projet : prévoir un budget, et au pic 2 à 3 SMS de réponse par message reçu. Si un opérateur refuse, le repli prévu est dans architecture.md (risques).

---

## 3. WhatsApp (Meta)

Démarches détaillées et profil du compte : [whatsapp/LISEZMOI.md](whatsapp/LISEZMOI.md). En résumé :

| Étape | Qui | Ce qu'on obtient | Où le mettre |
| --- | --- | --- | --- |
| Portefeuille d'entreprise Meta de l'INS, **vérification de l'entreprise** (documents officiels) | INS | Entreprise vérifiée | — |
| Compte WhatsApp Business et **numéro dédié** (jamais utilisé dans l'application WhatsApp) | INS | Le numéro | — |
| Application Meta (developers.facebook.com), produit WhatsApp | Exploitant | Identifiant du numéro (*Phone number ID*), secret de l'application | En base : `whatsapp_numero_id`, `whatsapp_secret_app` |
| Utilisateur système, permission `whatsapp_business_messaging` | Exploitant | Jeton permanent | En base : `whatsapp_jeton` (saisie masquée) |
| Abonnement du webhook `https://<domaine>/v1/whatsapp/webhook`, champ `messages` | Exploitant | — | Jeton de vérification : `afficher whatsapp_jeton_verification`, à recopier chez Meta |
| Modèle de message `rappel_passage` (rappels de passage), soumis à l'approbation de Meta | Exploitant, Ministère | Modèle approuvé | — |
| Budget des messages-modèles (facturés par Meta) | Ministère | — | — |

Ensuite : `definir whatsapp_passerelle meta`, puis `docker compose restart api taches`. Les messages transitent par Meta, hors de RDC : c'est à faire arbitrer (§ 8).

---

## 4. Données et contenus

### Référentiel des territoires

- **Quoi** : la liste officielle des provinces, villes et territoires, avec leurs codes. Le fichier fourni, `donnees/territoires.csv`, n'est qu'un **échantillon aux codes provisoires**.
- **Qui** : l'INS. Format et import : [donnees/LISEZMOI.md](donnees/LISEZMOI.md).
- **Où** : `docker compose run --rm migrations python -m coeur.territoires importer <fichier>`.

### Liste des badges des agents

- **Quoi** : le numéro de badge de chaque agent recenseur, son territoire, et s'il est en service ou retiré. Sert à démasquer les faux agents.
- **Qui** : l'INS, à mettre à jour à chaque recrutement ou retrait. Colonnes `numero,territoire_code,actif`.
- **Où** : `docker compose run --rm migrations python -m coeur.badges importer <fichier>`. Le fichier remplace toute la liste. Seules les empreintes des numéros sont gardées. Le fichier source se garde dans le coffre-fort, puis s'efface du serveur.

### Contenus de la FAQ et calendrier

- **Quoi** : les questions et réponses officielles, leurs formulations (les façons de poser la même question), leurs traductions en lingala, kiswahili, kikongo et tshiluba, et les dates de passage par territoire.
- **Qui** : le Ministère rédige, les traducteurs traduisent, le **BCR valide** dans Directus (circuit dans le README, « Travailler dans Directus »). Les contenus d'exemple, marqués `[EXEMPLE non validé]`, ne vont jamais en production.
- **Aussi** : les textes des interfaces en langues nationales, à faire traduire puis relire. Les propositions en lingala sont à relire ; les autres langues sont à faire. Fichiers : `src/coeur/portail/textes/`, `src/coeur/mobile/textes/`, `src/coeur/terrain/textes/`.

### Enregistrements audio

- **Serveur vocal** : les messages fixes (accueil, menus, attente), enregistrés par des locuteurs natifs dans chaque langue. Liste et format : [asterisk/messages/LISEZMOI.md](asterisk/messages/LISEZMOI.md).
- **Réponses** : l'audio de chaque réponse validée (champ `audio_url` dans Directus), et si possible de chaque question (`audio_question_url`, joué avant la confirmation d'un message vocal). Jamais de voix de synthèse en production.
- **Qui** : le Ministère organise les séances d'enregistrement ; le BCR valide comme le texte.

### Hébergement de l'audio

- **Quoi** : une adresse **HTTPS publique** pour chaque fichier audio et vidéo des réponses. Meta les télécharge pour WhatsApp, et les kiosques les gardent hors ligne.
- **Comment** : le serveur de fichiers de Directus, ou tout espace web du projet. Il doit envoyer l'en-tête `Access-Control-Allow-Origin: https://<domaine du cœur>`, sinon la lecture hors ligne peut échouer sur les tablettes ([terrain/LISEZMOI.md](terrain/LISEZMOI.md)). Vidéos : MP4, 16 Mo au plus.

---

## 5. Comptes des utilisateurs

Tout se gère dans **Directus** : il n'y a pas d'autre annuaire. Le compte administrateur est créé au premier démarrage (`DIRECTUS_ADMIN_EMAIL`, mot de passe tiré au hasard dans `.env`). Il crée ensuite les comptes nominatifs :

| Rôle Directus | Pour | Accès |
| --- | --- | --- |
| Rédacteur | Équipe de rédaction du Ministère | Rédiger dans Directus |
| Validateur BCR | BCR | Valider les contenus ; tableau de bord |
| Tableau de bord | UNFPA, partenaires | Statistiques agrégées seulement |
| Agent centre d'appels | Agents du numéro vert | Console des agents |
| Superviseur qualité | Superviseurs | Écoute des enregistrements (journalisée) |
| Administrator | Administrateurs du projet | Tout, dont l'enrôlement des kiosques et des Ambassadeurs |

Il faut aussi remettre la **clé d'API du Ministère** (`afficher cle_ministere`) à l'équipe qui interroge les statistiques par programme, s'il y en a une.

---

## 6. Matériel de terrain et postes

| Matériel | Besoin | Préparation |
| --- | --- | --- |
| Tablettes des kiosques (50 territoires prioritaires) | Android 9 ou plus, Chrome à jour, écran tactile, alimentation solaire et batterie, lieu sécurisé (école, mairie), assurance | [terrain/LISEZMOI.md](terrain/LISEZMOI.md) : enrôlement, épinglage d'écran, synchronisation hebdomadaire |
| Téléphones des Ambassadeurs | Android avec Chrome ; un appareil par Ambassadeur | Enrôlement depuis le tableau de bord, un code par appareil |
| Postes des agents du centre d'appels | Ordinateur avec Chrome ou Edge à jour, **casque avec micro**, réseau stable | Compte « Agent centre d'appels » ; accès en HTTPS seulement |

---

## 7. Transcription des messages vocaux

Détails : [transcription/LISEZMOI.md](transcription/LISEZMOI.md).

| Élément | Pourquoi | Comment l'obtenir |
| --- | --- | --- |
| **Serveur de calcul** | Sur processeur seul (4 cœurs), un message de 20 s se transcrit en 7 à 14 s, un message à la fois : assez pour un pilote, pas pour le pic | Un GPU NVIDIA hébergé en RDC, ou plusieurs instances. À dimensionner avec le volume de messages vocaux du pilote |
| **Le modèle** (`facebook/mms-1b-all`, environ 4 Go) | Transcrire | Téléchargé depuis Hugging Face au premier démarrage. Si le serveur n'a pas Internet : le télécharger ailleurs et le copier dans le volume `modeles_transcription` |
| **Un modèle pour le kikongo et le tshiluba** | Aucune version de MMS ne les couvre (`mms-1b-all`, `mms-1b-l1107`, `mms-1b-fl102`, mesure du 20 octobre 2026) | Évaluer un autre modèle ouvert (Omnilingual ASR de Meta) ; sinon, ou en attendant, ces langues restent en rappel par un conseiller. Aucun code à changer : le service accepte tout modèle qui respecte son contrat |
| **Messages d'évaluation** | Ouvrir une langue sur des chiffres, pas sur une impression | Une centaine de vrais messages vocaux par langue, sur le recensement, avec la question attendue. Sources : Ambassadeurs, centre d'écoute, séances d'enregistrement |
| **Variante du kikongo** | Le modèle et les traductions en dépendent | Décision du Ministère : kikongo ya leta (kituba) ou kikongo |

Une fois prêt : `definir transcription service`, puis `definir transcription_langues sw,ln` (langues évaluées seulement).

---

## 8. Validations et protection des données

À obtenir **avant l'ouverture de chaque canal**. Interlocuteur principal : le **point focal protection des données** de l'INS-BCR.

| Sujet | Décision attendue | Où ça se règle |
| --- | --- | --- |
| Transit des messages WhatsApp par Meta (hors RDC) | Accepter ou non le canal WhatsApp | — |
| Enregistrement des appels | Annonce, durée de 90 jours, accès des superviseurs | `conservation_enregistrements_jours` (en base) |
| Texte des questions gardé dans le journal | Tout, seulement les questions sans réponse, ou rien | `conservation_texte_questions` (en base) |
| Secret statistique avant toute publication externe | Valider la règle de masquage et la perturbation de ± 2 des effectifs publiés | `seuil_secret_statistique`, `perturbation_statistique` (en base) |
| Audit de sécurité | Un audit avant l'ouverture de chaque canal numérique | — |
| Licence du modèle de transcription (MMS : CC-BY-NC 4.0, pas d'usage commercial) | Compatibilité avec un service public exploité par un prestataire | Juriste de l'INS ou de l'UNFPA |
| Intitulé du bloc-marque (*Institut national de la statistique, Bureau central du recensement*) | Validation par l'INS et, le cas échéant, par le Ministère de la Communication et Médias, garant de la charte | `src/coeur/charte/__init__.py` |
| Fin de conservation | Date de purge : au plus tard six mois après la publication des résultats | README, « Exploitation » |
