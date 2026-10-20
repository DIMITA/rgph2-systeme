# RGPH-2 : le cœur du système d'information citoyenne

Ce dépôt contient le **cœur commun** auquel se brancheront les six canaux du RGPH-2 : USSD/SMS, WhatsApp, portail web, kiosques OKAPI, Ambassadeurs et centre d'écoute. Il couvre la Phase 1 de [architecture.md](architecture.md) :

- étape 1 : le cœur ;
- étape 2 : le **portail web et son chatbot**, premier canal branché ;
- étape 3 : le **tableau de bord du Ministère** ;
- étape 4a : le **centre d'appels** (numéro vert sur IP : serveur vocal, file d'attente, rappels, enregistrements) ;
- étape 4b : la **console des agents** dans le navigateur et l'**écoute qualité** ;
- étape 5 : l'**USSD et les SMS** (menus, mots-clés, calendrier de passage, vérification des badges), avec la passerelle SMS Kannel ;
- toutes les interfaces aux couleurs de la **Charte graphique du Gouvernement** (Marque État Congolais) ;
- étape 6a : le **bot WhatsApp** (API officielle de Meta), relié à la base fermée et aux services de l'USSD ;
- étape 6b : les **rappels de passage** par WhatsApp (abonnement, envoi 3 jours avant et la veille, STOP) et la section WhatsApp du tableau de bord.

Le cœur fait trois choses :

1. **Répondre** aux questions des citoyens, uniquement avec des contenus **validés par le BCR**. Faute de contenu validé assez proche de la question, il renvoie `"escalade vers un humain"`.
2. **Recevoir les signalements** localisés : ménage non visité, rumeur, agent douteux.
3. **Produire des statistiques** d'usage par canal, langue et territoire, jamais à une maille plus fine que le territoire.

Les contenus sont rédigés et validés par le Ministère dans **Directus** (le CMS), sans passer par le prestataire.

---

## Sommaire

- [Vue d'ensemble](#vue-densemble)
- [Démarrer](#démarrer)
- [Travailler dans Directus](#travailler-dans-directus)
- [Utiliser l'API](#utiliser-lapi)
- [Portail web et chatbot](#portail-web-et-chatbot)
- [Tableau de bord du Ministère](#tableau-de-bord-du-ministère)
- [Centre d'appels (numéro vert)](#centre-dappels-numéro-vert)
- [USSD et SMS](#ussd-et-sms)
- [WhatsApp](#whatsapp)
- [Charte graphique du Gouvernement](#charte-graphique-du-gouvernement)
- [Protection des données](#protection-des-données)
- [Exploitation](#exploitation)
- [Tests](#tests)
- [Faire évoluer le code](#faire-évoluer-le-code)
- [Limites connues et points à trancher](#limites-connues-et-points-à-trancher)

---

## Vue d'ensemble

```
  WhatsApp  Kiosques  Ambassadeurs   USSD    SMS (SMPP)           Numéro vert
      └─────────┴──────────┘          │   ┌───▼────┐                  │
         (étapes suivantes)  agréga-  │   │ Kannel │           ┌──────▼──────┐
                              teur    │   └───┬────┘           │  Asterisk   │ SVI, file,
                              │◄──────┘◄──────┘                │ (conteneur) │ enregistrements
                              │◄───────────────────────────────┴─────────────┘
                              │  HTTPS + clé d'API par canal
                     ┌────────▼─────────┐
   citoyen (web) ───►│   API « cœur »   │  FastAPI (Python), un seul déploiement
   /fr, /ln…         │ + portail web    │  (monolithe modulaire)
                     └───┬──────────┬───┘
         lecture seule   │          │  écriture
     ┌───────────────────▼──┐   ┌───▼─────────────────────────────┐
     │ schéma public        │   │ schéma coeur                    │
     │ contenus, traduc-    │   │ territoires, interactions,      │
     │ tions, formulations, │   │ signalements                    │
     │ langues              │   │ (invisible pour Directus)       │
     └───────────▲──────────┘   └─────────────────────────────────┘
                 │ lecture/écriture        PostgreSQL 16
          ┌──────┴──────┐
          │  Directus   │  ← le Ministère rédige et le BCR valide ici
          └─────────────┘
```

### Les modules

Chaque module est un dossier de `src/coeur/` qui contient `modeles.py` (tables), `schemas.py` (formats d'entrée et de sortie), `service.py` (règles) et `routes.py` (API). Un module n'appelle un autre module **que par son `service.py`**.

| Module | Rôle |
| --- | --- |
| `connaissances/` | Lit les contenus publiés et choisit la bonne réponse (`moteur.py`), ou décide d'escalader |
| `interactions/` | Journal de chaque question (sans nom ni numéro en clair) |
| `signalements/` | Signalements localisés envoyés par les canaux, et leur suivi par le Ministère |
| `statistiques/` | Agrégats par pays, province ou territoire, avec secret statistique |
| `territoires/` | Référentiel des provinces, villes et territoires |
| `confidentialite/` | Empreinte des numéros, masquage des numéros et courriels dans les textes |
| `retention/` | Suppression des données à la fin de la période de conservation |
| `portail/` | Portail web citoyen et chatbot (canal « web ») : pages et textes de l'interface |
| `centre_appels/` | Menu du serveur vocal, suivi des appels (empreinte du numéro), rappels chiffrés, enregistrements et leur purge |
| `tableau_de_bord/` | Espaces connectés avec les comptes Directus : tableau de bord du Ministère, console des agents (`console.py`), écoute qualité |
| `calendrier/` | Dates de passage des agents par territoire (saisies et validées dans Directus) |
| `badges/` | Liste des badges d'agents (empreintes, import CSV de l'INS) et vérification |
| `mobile/` | Socle commun USSD et SMS : textes courts, alphabet GSM, langue préférée, services, journal des consultations et des SMS |
| `ussd/` | Menus USSD (`moteur.py`) rejoués à partir de la saisie cumulée |
| `sms/` | Mots-clés et questions par SMS (`analyse.py`), envoi par Kannel (`passerelle.py`) avec plafond journalier |
| `whatsapp/` | Bot WhatsApp : webhook signé (`routes.py`), conversation en listes et boutons (`conversation.py`), envoi par l'API Graph (`passerelle.py`) |
| `simulateur/` | Page de test imitant un téléphone basique (désactivée par défaut, jamais en production) |
| `charte/` | Charte graphique du Gouvernement : feuille de style, bloc-marque, police, armoiries, pages d'erreur, documentation de l'API |

Fichiers transverses : `main.py` (assemblage), `config.py` (réglages), `securite.py` (clés d'API), `base.py` (base de données), `commun.py` (types partagés), `limiteur.py` (limite de débit), `journalisation.py` (journal d'accès sans paramètres d'adresse).

### Comment une question est traitée

1. Le canal envoie `POST /v1/questions` avec sa clé d'API.
2. Si le citoyen demande explicitement un humain (« parler à un conseiller »…), l'API **escalade**.
3. Sinon, le moteur compare la question aux questions et **formulations** des contenus *publiés*, dans la langue demandée et en français. Il ne génère jamais de texte : il ne fait que choisir.
4. Il y a **escalade** si le meilleur score est sous le seuil (`SEUIL_CONFIANCE`, 0,5 par défaut) ou si deux contenus sont trop proches (`MARGE_AMBIGUITE`, 0,1).
5. Sinon, l'API renvoie le texte validé dans la langue demandée. S'il n'existe pas encore dans cette langue, elle renvoie la version française avec `"repli_langue": true`.
6. L'échange est enregistré dans le journal : numéro remplacé par une empreinte, texte masqué.

Un contenu n'est servi que si **le contenu ET sa traduction** sont au statut `publie`. Les statuts `brouillon`, `en_revue` et `archive` ne sont jamais servis.

---

## Démarrer

Prérequis : Docker (avec Docker Compose v2) et Git. Python 3.11 ou plus est nécessaire seulement pour lancer les tests hors Docker.

```bash
# 1. Créer le fichier de secrets
cp .env.exemple .env
#    → remplacer TOUTES les valeurs « changer-... »
#      python -c "import secrets; print(secrets.token_urlsafe(32))"

# 2. Démarrer PostgreSQL, les migrations, l'API, Directus et sa configuration
docker compose up -d

# 3. Importer le référentiel des territoires (voir donnees/LISEZMOI.md)
docker compose run --rm migrations python -m coeur.territoires importer donnees/territoires.csv

# 4. (Hors production) Charger la FAQ et le calendrier de démonstration, et des badges fictifs
docker compose run --rm migrations python -m coeur.connaissances charger-exemples
docker compose run --rm migrations python -m coeur.badges importer donnees/badges-exemple.csv

# 5. Vérifier toute la chaîne Directus → API
python outils/verifier_pile.py      # avec les variables du .env chargées dans le shell
```

| Service | Adresse |
| --- | --- |
| Portail citoyen | http://localhost:8000/fr (ou `/ln`, `/sw`, `/kg`, `/lua`) |
| API | http://localhost:8000/v1/…. Documentation interactive : http://localhost:8000/docs |
| Tableau de bord | http://localhost:8000/tableau-de-bord (comptes Directus autorisés) |
| Téléphonie | SIP sur UDP 5060, audio sur UDP 10000-10050, postes WebRTC sur le port 8088 (voir [asterisk/LISEZMOI.md](asterisk/LISEZMOI.md)) |
| Directus | http://localhost:8055 (compte administrateur : `DIRECTUS_ADMIN_EMAIL` / `DIRECTUS_ADMIN_MDP`) |
| Simulateur de téléphone | http://localhost:8000/simulateur (si `SIMULATEUR_MOBILE=true`) |

Au démarrage, `docker compose up` lance dans l'ordre :

- `postgres` crée les rôles à la première initialisation (`db/init/01-roles.sh`) ;
- `migrations` crée ou met à jour les tables (Alembic), puis s'arrête ;
- `api` et `directus` démarrent ;
- `directus-config` règle l'affichage des collections et crée les rôles, puis s'arrête. Ce service peut être relancé sans risque ;
- `asterisk` (téléphonie), `sms` (passerelle SMS Kannel) et `taches` démarrent. `taches` s'exécute toutes les heures (`python -m coeur.taches`) : purges du centre d'appels, rappels de passage WhatsApp, abonnements expirés.

---

## Travailler dans Directus

### Les rôles

| Rôle | Peut | Ne peut pas |
| --- | --- | --- |
| **Rédacteur** | Créer des contenus et des traductions, les modifier tant qu'ils sont `brouillon` ou `en_revue` | Publier ; modifier un contenu déjà publié ; toucher aux formulations ; supprimer |
| **Validateur BCR** | Tout ce que fait le Rédacteur, plus publier, archiver, gérer les formulations et les langues | Administrer Directus |
| **Lecteur** | Consulter | Modifier |
| **Tableau de bord** | Se connecter au tableau de bord du Ministère | Voir ou modifier les contenus |
| **Agent centre d'appels** | Utiliser la console des agents (téléphone, FAQ, signalements, rappels) | Voir les statistiques ou écouter les enregistrements |
| **Superviseur qualité** | Écouter les conversations enregistrées (écoutes journalisées) | Voir les statistiques ou utiliser la console |

Pour créer un compte : **Paramètres → Utilisateurs → Créer**, puis choisir le rôle. Ces règles sont définies dans `outils/configurer_directus.py`, et `outils/verifier_pile.py` vérifie qu'elles sont bien appliquées.

### Le circuit d'un contenu

```
brouillon ──► en_revue ──► publie ──► archive
  (Rédacteur)              (Validateur BCR uniquement)
```

- **Contenu** : un sujet de la FAQ. Sa `cle` est un identifiant court et stable (ex. `calendrier-passage`).
- **Traduction** : le texte du contenu dans une langue. Chaque langue est validée **séparément**.
  - `reponse` : texte complet (web, WhatsApp, kiosque).
  - `reponse_courte` : 160 caractères au plus, pour l'USSD et le SMS.
  - `audio_url` : enregistrement par un locuteur natif.
- **Formulations** : d'autres manières de poser la même question (« date de passage », « quand passent les agents »). **C'est le principal levier pour améliorer la qualité des réponses** : en cas d'escalade injustifiée, ajouter la formulation employée par le citoyen. Les questions escaladées se trouvent dans `coeur.interactions`, colonne `texte_masque`, filtrées sur `resultat = 'escalade'`.

Une modification publiée est prise en compte par l'API au plus tard après `CACHE_CONTENUS_SECONDES` (60 s par défaut).

> **Important** : la structure des tables de contenus est définie par les migrations (`migrations/versions/`), pas dans Directus. N'ajoutez ni ne supprimez de champ depuis l'interface « Modèle de données » : faites une migration (voir [Faire évoluer le code](#faire-évoluer-le-code)).

---

## Utiliser l'API

La documentation complète est générée automatiquement sur `/docs`. Chaque appel porte l'en-tête `X-Cle-API`. La clé identifie le canal, qui n'a donc pas à se déclarer lui-même.

| Méthode et chemin | Clé | Usage |
| --- | --- | --- |
| `POST /v1/questions` | canal | Poser une question : réponse validée ou escalade |
| `GET /v1/faq?langue=ln` | canal | Toute la FAQ publiée (synchronisation des kiosques) |
| `GET /v1/contenus/{id}?langue=ln` | canal | Un contenu publié |
| `POST /v1/signalements` | canal | Envoyer un signalement |
| `GET /v1/signalements` | Ministère | Lister les signalements (filtres : `territoire_code`, `statut`) |
| `PATCH /v1/signalements/{id}` | Ministère | Changer le statut : `nouveau`, `en_traitement`, `clos` |
| `GET /v1/statistiques?niveau=territoire` | Ministère | Statistiques. `niveau` vaut `national`, `province` ou `territoire` |
| `GET /v1/territoires` | aucune | Référentiel des provinces et territoires |
| `GET /v1/calendrier/{territoire}` | canal | Dates de passage publiées pour un territoire |
| `POST /v1/badges/verification` | canal | Vérifier un badge : `valide`, `retire` ou `inconnu` |
| `POST /v1/ussd` | ussd | Échange USSD (agrégateur) : réponse `CON …` ou `END …` |
| `GET /v1/sms/entrant` | sms | SMS reçu, transmis par Kannel |
| `GET`, `POST /v1/whatsapp/webhook` | signature de Meta | Abonnement du webhook, messages WhatsApp reçus |
| `GET /sante` | aucune | État du service (pour la supervision) |

### Exemple : poser une question

```bash
curl -X POST http://localhost:8000/v1/questions \
  -H "X-Cle-API: <clé du canal>" -H "Content-Type: application/json" \
  -d '{"texte": "Quand passent les agents ?", "langue": "ln",
       "territoire_code": "NKV-GOM", "telephone": "0812345678"}'
```

Réponse validée :

```json
{"type": "reponse", "score": 0.75, "message": null, "motif": null,
 "contenu": {"contenu_id": 2, "cle": "calendrier-passage", "langue": "fr", "repli_langue": true,
             "question": "...", "reponse": "...", "reponse_courte": "...", "audio_url": null}}
```

Escalade : **le canal doit alors passer la main** au centre d'écoute ou à un agent.

```json
{"type": "escalade", "message": "escalade vers un humain",
 "motif": "aucune_reponse_validee", "score": 0.23, "contenu": null}
```

| `motif` | Signification |
| --- | --- |
| `aucune_reponse_validee` | Aucun contenu publié ne correspond assez |
| `ambigu` | Plusieurs contenus correspondent autant l'un que l'autre |
| `demande_humain` | Le citoyen a demandé à parler à quelqu'un |
| `traduction_indisponible` | Le contenu trouvé n'a de version publiée ni dans la langue demandée, ni en français |

Champs acceptés : `texte` (500 caractères au plus), `langue` (code de 2 ou 3 lettres, `fr` par défaut), `territoire_code` et `telephone` (tous deux facultatifs). **Tout autre champ est refusé (HTTP 422).**

---

## Portail web et chatbot

Le portail est le canal « web ». Il fait partie du cœur et appelle directement ses services : aucune clé d'API n'est envoyée au navigateur. Toutes les interactions et tous les signalements du portail sont enregistrés avec le canal `web`.

| Page | Contenu |
| --- | --- |
| `/{langue}` | Accueil : poser une question, aperçu de la FAQ |
| `/{langue}/faq` | Toutes les questions publiées (pliables, sans JavaScript) |
| `/{langue}/signaler` | Signalement : type, territoire, quartier ou village, précisions. Aucun champ téléphone |

**Conçu pour la 2G et les téléphones modestes :**

- Tout fonctionne avec de simples formulaires HTML. `portail.js` est une amélioration facultative : la conversation s'affiche sans recharger la page.
- Aucune ressource externe (ni CDN, ni outil de mesure d'audience) : la police de la charte et les armoiries sont servies par le site. Les pages sont compressées ; la feuille de style et le script restent en cache une journée, la police et les armoiries un mois.
- La première visite pèse environ **47 Ko compressés**, dont 28 Ko pour la police (une seule fois, puis en cache). Les visites suivantes pèsent moins de **2 Ko**. Le texte s'affiche aussitôt en police du téléphone, puis passe en Cooper Hewitt une fois celle-ci chargée. Un test (`test_page_legere_pour_la_2g`) empêche la page de dépasser 30 Ko non compressés, et un autre (`test_police_legere`) limite chaque graisse à 20 Ko.

**Langues de l'interface.** Le portail est proposé dans toutes les langues actives de Directus, et les contenus s'affichent dans la langue choisie (repli en français, signalé à l'écran). Les textes de l'interface (boutons, consignes) viennent de `src/coeur/portail/textes/<code>.json`. Sont fournis `fr.json` et `ln.json`. **Le lingala est une proposition à faire relire par un locuteur natif** (voir `textes/LISEZMOI.md`). Pour une autre langue, faire traduire `fr.json` et le déposer sous le code de la langue (ex. `sw.json`). Toute clé manquante est reprise du français, et un test vérifie que chaque traduction est complète.

**Escalade.** Si `NUMERO_VERT` est renseigné, le portail invite à l'appeler. Tant qu'il est vide (numéro pas encore attribué), le portail n'affiche aucun numéro : il indique que la question est enregistrée pour compléter la FAQ, ce qui est le cas grâce au journal des interactions. Dans les deux cas, il ne collecte aucune donnée pour rappeler le citoyen.

**Protections :**

- Les textes affichés sont échappés, et le script n'utilise jamais `innerHTML`.
- Une politique CSP stricte n'autorise que les ressources du site lui-même.
- Le débit est limité par adresse IP : 20 questions par minute et 5 signalements par heure, réglables.
- Les adresses IP sont comptées en base sous forme d'empreinte (HMAC), jamais en clair, dans une table non journalisée effacée par les tâches périodiques.

> **Derrière un proxy HTTPS**, renseigner `FORWARDED_ALLOW_IPS` avec l'adresse du proxy. Sinon, toutes les requêtes semblent venir du proxy, et l'ensemble des citoyens partage la même limite de débit.

---

## Tableau de bord du Ministère

Adresse : **http://localhost:8000/tableau-de-bord**. Les pages sont rendues par le serveur, sans bibliothèque externe, et ne sont jamais mises en cache.

| Page | Contenu |
| --- | --- |
| Synthèse | Questions posées, part sans réponse validée, usagers distincts, signalements. Répartitions par canal, langue, province ou territoire, et signalements par type. Filtre par période, **export CSV** (séparateur `;`, ouvrable dans Excel) |
| Questions sans réponse | Les questions escaladées les plus fréquentes (30 derniers jours) et les plus récentes, filtrables par langue et par motif. **C'est la liste de travail pour enrichir la FAQ** dans Directus |
| Signalements | Liste filtrable (territoire, type, statut) avec quartier ou village et précisions, pour les équipes de terrain, et changement de statut |

**Connexion avec les comptes Directus.** Il n'y a pas de second annuaire : le Ministère crée et désactive les comptes dans Directus. Une même page de connexion mène à trois espaces, chacun réservé à des rôles : le **pilotage** (cette section, `ROLES_TABLEAU_DE_BORD`), la **console des agents** (`ROLES_AGENTS`) et l'**écoute qualité** (`ROLES_QUALITE`). Chacun arrive directement dans son espace. Rôles admis au pilotage :

- *Administrator* ;
- *Validateur BCR* ;
- *Tableau de bord* : n'a accès à aucun contenu, par exemple pour l'UNFPA.

Les Rédacteurs et les Lecteurs sont refusés. La session dure 8 heures, dans un cookie signé limité au chemin `/tableau-de-bord` : les citoyens du portail ne reçoivent jamais de cookie. Le compte n'est vérifié qu'à la connexion : un compte désactivé dans Directus garde l'accès jusqu'à la fin de sa session. Les tentatives de connexion sont limitées à 10 par quart d'heure et par adresse IP.

**Mêmes garde-fous que l'API :**

- pas de maille plus fine que le territoire ;
- effectifs inférieurs à `SEUIL_SECRET_STATISTIQUE`, et ceux qui permettraient de les retrouver par différence, affichés « masqué » (vides dans l'export) ;
- aucune localité dans les statistiques. Seule la liste des signalements montre le quartier ou le village, parce que les équipes de terrain en ont besoin.

**Heures.** La base enregistre en UTC. Le tableau de bord affiche les heures et découpe les journées selon `FUSEAU_HORAIRE` : `Africa/Kinshasa` (UTC+1) par défaut, ou `Africa/Lubumbashi` (UTC+2) pour l'est.

---

## Centre d'appels (numéro vert)

Le centre d'appels repose sur un standard téléphonique sur IP, **Asterisk**, dans le conteneur `asterisk`. Contrairement à une simple ligne, il prend **plusieurs appels en même temps**. Le détail technique, la fiche à transmettre à l'opérateur et les tests sont dans [asterisk/LISEZMOI.md](asterisk/LISEZMOI.md).

**Ce que vit l'appelant :**

1. Accueil, avec l'annonce que l'appel peut être enregistré.
2. Choix de la langue : 1 français, 2 lingala, 3 kiswahili, 4 kikongo, 5 tshiluba.
3. **Serveur vocal (SVI)** : il écoute les réponses enregistrées et validées par le BCR, sans attendre d'agent.
4. Avec la touche 0 : **file d'attente**, puis le premier agent libre. La conversation est enregistrée.
5. Si l'attente dépasse 3 minutes, ou si aucun agent n'est connecté : **proposition de rappel**.

**Alimenter le SVI depuis Directus**, sur un contenu publié :

- le champ `ordre_svi` (1 à 8) place la question dans le menu ;
- dans chaque traduction, `audio_question_url` donne la question lue et `audio_url` la réponse lue.

Le SVI se met à jour seul toutes les 5 minutes. Les messages fixes (accueil, menus, attente…) sont à faire enregistrer par des locuteurs natifs : le script complet est dans [asterisk/messages/LISEZMOI.md](asterisk/messages/LISEZMOI.md).

**Dimensionnement retenu** : 240 appels par jour au pic, soit environ 36 à l'heure de pointe. Il faut **6 agents** et **10 canaux simultanés** chez l'opérateur pour que 80 % des appels soient décrochés en moins de 30 secondes (calcul Erlang C).

**Rappels** : le numéro de l'appelant est conservé **chiffré** (Fernet, clé `CLE_CHIFFREMENT`). Il n'est révélé qu'à l'agent qui prend le rappel en charge, et il est **effacé dès que le rappel est clôturé**, ou au plus tard après `CONSERVATION_RAPPELS_JOURS` (7). Le service `taches` vérifie ces délais toutes les heures.

### Console des agents

Adresse : `/tableau-de-bord/agent`, réservée au rôle Directus *Agent centre d'appels*. L'agent travaille avec un casque et un navigateur récent (Edge, Chrome, Firefox), sans téléphone.

1. **Prendre un poste** (poste1…poste6). Le navigateur devient le téléphone de ce poste (WebRTC, bibliothèque JsSIP servie par le site). Un poste ne sert qu'à un agent à la fois.
2. **Recevoir les appels** de la file : décrocher, raccrocher, couper le micro, se mettre en pause ou reprendre. La langue choisie par l'appelant s'affiche, jamais son numéro.
3. **Chercher la réponse validée** à lire au citoyen. Ces recherches ne sont pas comptées dans les statistiques.
4. **Enregistrer un signalement** pris au téléphone (canal `centre_ecoute`).
5. **Qualifier l'appel** avant le suivant : citoyen renseigné, signalement, question transmise au BCR, hors sujet, appel coupé. C'est une liste fermée, sans texte libre.
6. **Traiter les rappels** : « Prendre » réserve la demande et affiche le numéro, « Appeler » le compose, puis « Rappelé » ou « Injoignable » clôt la demande et efface le numéro.

### Écoute qualité

Adresse : `/tableau-de-bord/qualite`, réservée au rôle *Superviseur qualité*. On y trouve la liste des conversations (date, poste, langue, durée, issue) et l'écoute dans le navigateur. **Chaque écoute est journalisée** (compte, date, fichier). Ce journal survit à la suppression de l'enregistrement et n'est effacé qu'à la purge de fin de conservation.

---

## USSD et SMS

Deux canaux pour **tout téléphone, même sans internet**. Ils offrent les mêmes services, et le SMS sert aussi de **repli si les opérateurs refusent l'USSD** (voir les risques dans architecture.md). Le détail technique et la fiche pour l'opérateur sont dans [sms/LISEZMOI.md](sms/LISEZMOI.md).

### Ce que vit le citoyen

**USSD** (code `*xxx#`, à obtenir auprès de l'ARPTC). Au premier appel, il choisit sa langue, qui est ensuite retenue. Il trouve ensuite ce menu :

| Touche | Service |
| --- | --- |
| 1 | **Questions fréquentes** : réponse courte validée, et réponse complète par SMS sur demande |
| 2 | **Date de passage des agents** : province, puis territoire |
| 3 | **Vérifier un agent** : numéro du badge, réponse « valide », « retiré » ou « inconnu ». Si le badge est inconnu, il peut signaler l'agent |
| 4 | **Ménage non recensé** : territoire, quartier ou village (facultatif), puis confirmation |
| 5 | **Parler à un conseiller** : numéro vert, ou demande de rappel. La demande arrive dans la console des agents |
| 6 | Changer de langue |

Un écran fait 182 caractères au plus. Une liste trop longue continue avec « 98 Suite », et « 0 » revient à l'écran précédent.

**SMS** : les mots-clés ci-dessous sont les mêmes dans toutes les langues. Majuscules, accents et tirets sont indifférents.

| Message | Réponse |
| --- | --- |
| `AIDE` | La liste des mots-clés |
| `AGENT AB1234` | Le badge est valide (avec son territoire), retiré ou inconnu |
| `PASSAGE GOMA` | Les dates de passage dans ce territoire (nom ou code) |
| `NONVISITE GOMA Himbi 2` | Le signalement d'un ménage non recensé, avec le quartier |
| `FAUXAGENT GOMA AB1234` | Le signalement d'un faux agent, avec le badge présenté |
| `RAPPEL` | La demande de rappel par un conseiller |
| `LANGUE ln` | Le changement de langue (code ou nom) |
| Toute autre phrase | Une question pour la base fermée : réponse validée ou escalade (numéro vert, RAPPEL) |

Une phrase qui commence par un mot-clé mais ressemble à une question (« agent recenseur faux, que faire ? ») est traitée comme une question.

### Ce que fait le Ministère

- **Calendrier de passage** : dans Directus, collection *Calendrier passages*. On y saisit une ou plusieurs périodes par territoire. Le circuit est celui des contenus : seul le Validateur BCR publie. Le menu des territoires vient du référentiel : il faut relancer `docker compose up directus-config` après chaque import de territoires.
- **Liste des badges** : l'INS fournit un fichier CSV (`numero,territoire_code,actif`, avec 1 pour un badge en service et 0 pour un badge retiré), sans nom ni photo. **Chaque import remplace toute la liste** ; un fichier qui contient une seule ligne invalide est refusé en entier.
  ```bash
  docker compose run --rm migrations python -m coeur.badges importer /chemin/badges.csv
  ```
  Les numéros sont conservés sous forme d'**empreinte** : une copie de la table ne permet pas de fabriquer un faux badge « valide ». Chaque numéro de téléphone est limité à `BADGES_VERIFICATIONS_PAR_HEURE` vérifications par heure, contre les essais au hasard.
- **Textes des menus et des messages** : `src/coeur/mobile/textes/` (français, et une proposition en lingala à faire relire). Voir le [LISEZMOI](src/coeur/mobile/textes/LISEZMOI.md) de ce dossier.

### Ce qui est compté

Le tableau de bord présente une section *USSD et SMS* : dates de passage consultées, badges valides, badges inconnus ou retirés, SMS reçus, **SMS envoyés en segments facturés** (le coût chez l'opérateur), et réponses non envoyées à cause du plafond. Les questions et les signalements USSD et SMS sont comptés avec ceux des autres canaux.

**Coût des SMS** : chaque numéro reçoit au plus `SMS_REPONSES_PAR_JOUR` réponses par jour (10 par défaut). Au-delà, les messages reçus sont traités mais ne reçoivent plus de réponse. Une réponse plus longue que `SMS_SEGMENTS_MAX` SMS (3 par défaut) est remplacée par sa version courte : une réponse validée n'est **jamais tronquée**.

### Tester sans opérateur

- **Simulateur** : avec `SIMULATEUR_MOBILE=true`, la page http://localhost:8000/simulateur imite un téléphone basique (USSD et SMS). Chaque échange y est traité comme un vrai.
- **De bout en bout** : avec `SMS_SIMULATION=true`, Kannel remplace l'opérateur par un simulateur. Ensuite, `python outils/verifier_mobile.py` passe une session USSD, envoie des SMS à travers Kannel et vérifie qu'aucun numéro n'apparaît en clair.
- **Badges fictifs** : `donnees/badges-exemple.csv` (EX0001 à EX0003 en service, EX0099 retiré).

---

## WhatsApp

Le bot WhatsApp offre les services de l'USSD et du SMS sous forme de **listes et de boutons**. Il répond aussi aux **questions écrites** : la base fermée donne la réponse complète validée, avec l'**audio et la vidéo en langue locale** s'il y en a. Sans réponse validée, il propose un rappel par un conseiller, qui arrive dans la console des agents.

Il passe par l'**API officielle de Meta**, la seule disponible : **les messages transitent donc hors de RDC**. C'est un point à faire arbitrer par le point focal protection des données. Le cœur ne garde que l'empreinte du numéro, jamais le texte des messages.

- Mise en service (compte, numéro, webhook), profil aux couleurs de la charte, médias et coûts : [whatsapp/LISEZMOI.md](whatsapp/LISEZMOI.md).
- **Vidéo** : nouveau champ `video_url` dans les traductions (Directus), validé comme le reste. Il faut une adresse HTTPS publique, MP4 de 16 Mo au plus.
- **Sécurité** : toute notification sans signature valide de Meta (`X-Hub-Signature-256`) est refusée.
- **Rappels de passage** : « Prévenez-moi » après une date de passage. Le citoyen reçoit un message 3 jours avant le passage, puis la veille, entre 8 h et 18 h. `STOP` efface tout. Le numéro des abonnés est conservé **chiffré** et effacé 7 jours après le passage. Les rappels utilisent un **modèle approuvé par Meta** et sont **facturés** ; le texte à soumettre est dans le LISEZMOI.
- **Tableau de bord** : la section WhatsApp donne les messages reçus, les usagers distincts, les réponses (gratuites), les rappels envoyés (facturés), les abonnés et les échecs d'envoi.
- **Tester sans compte Meta** : la section WhatsApp du simulateur (`/simulateur`), et `python outils/verifier_whatsapp.py`.

---

## Charte graphique du Gouvernement

Toutes les interfaces que voient les utilisateurs suivent la **Charte graphique du Gouvernement de la RDC** (« La Marque État Congolais », février 2022) : le portail citoyen, les espaces connectés (tableau de bord, console des agents, écoute qualité), le simulateur, la documentation de l'API, les pages d'erreur et Directus.

| Élément | Règle de la charte | Mise en œuvre |
| --- | --- | --- |
| Bloc-marque | Armoiries « Le Gouvernement » à gauche, **Ligne d'État** (bleu, jaune, rouge à parts égales, de haut en bas, hauteur des armoiries, 53 px au moins à l'écran), intitulé officiel | Macro `marque()` de `charte/gabarits/_charte.html`. Intitulé : *Institut national de la statistique, Bureau central du recensement* |
| Couleurs | Drapeau : `#0095c9`, `#fff24b`, `#db3832`. Complémentaires, dont le bleu institutionnel `#17418a` | Variables de `charte/statique/charte.css`. Le bleu du drapeau, trop clair pour du texte (contraste 3,3:1), est réservé à la Ligne d'État ; liens, boutons et bandeaux sont en `#17418a` (9,9:1) |
| Typographie | **Cooper Hewitt** : semi-gras pour l'intitulé et les titres, Medium pour le texte | Hébergée par le site (licence SIL OFL), réduite aux caractères utiles (français, lingala, tshiluba) : 14 Ko par graisse |
| Site web | Accueil : bandeau blanc, armoiries en couleur. Autres pages : bandeau bleu, marque en blanc. Pied de page : liseré tricolore, marque, liens utiles | Portail : `accueil` dans `portail/routes.py`. Espaces internes, simulateur, erreurs, `/docs` : bandeau bleu |
| Interdits | Armoiries en couleur sur fond sombre, ordre des couleurs changé, logo déformé, intitulé dans une autre police | Version blanche des armoiries sur les fonds bleus. Tests de `test_charte.py` (ordre, présence, variantes) |

**Directus** : le script de configuration lui applique la charte. Il règle la couleur du projet, les armoiries en blanc, le bloc-marque et le fond bleu à liseré tricolore sur la page de connexion, ainsi que la police Cooper Hewitt (servie par Directus lui-même). L'interface est en français et les collections portent des noms français.

**Régénérer les ressources** (armoiries, police, bloc-marque en image) après un changement de l'intitulé ou des tailles :

```bash
pip install fonttools brotli pillow
# Police : https://www.cooperhewitt.org/wp-content/uploads/fonts/CooperHewitt-OTF-public.zip
python outils/preparer_charte.py <dossier des .otf de Cooper Hewitt>
docker compose build && docker compose up -d && docker compose up directus-config
```

Sources : armoiries publiées par le Gouvernement dans la charte (domaine public, CC0), conservées dans `charte/sources/` avec la licence de la police.

---

## Protection des données

Ces règles sont **appliquées par le code** et **vérifiées par des tests**, pas seulement écrites :

| Règle (architecture.md) | Mise en œuvre | Test |
| --- | --- | --- |
| Pas de nom, de pièce d'identité ni de composition du ménage | Tout champ non prévu est refusé (`extra="forbid"`, `commun.py`) | `test_champ_non_prevu_refuse`, `test_donnee_personnelle_non_prevue_refusee` |
| Numéro de téléphone | Jamais stocké. Seule son **empreinte HMAC-SHA256** (`confidentialite/service.py`) est conservée : elle permet de compter les usagers uniques | `test_interaction_journalisee_sans_donnee_personnelle` |
| Textes libres | Les suites de 6 chiffres ou plus et les adresses électroniques sont remplacées par `[masqué]` | `test_confidentialite.py` |
| Statistiques jamais sous le territoire | Seuls les niveaux `national`, `province` et `territoire` existent. La localité des signalements n'est jamais lue par les statistiques | `test_aucune_maille_plus_fine_que_le_territoire`, `test_signalements_agreges_sans_localite` |
| Secret statistique | Effectif entre 1 et 4 masqué (`SEUIL_SECRET_STATISTIQUE`=5). Une ligne entière est masquée si elle compte moins de 5 interactions. Masquage complémentaire : une case masquée ne se déduit jamais d'un total publié (national, province, canal, langue) | `test_niveau_territoire_avec_secret_statistique`, `test_secret_statistique.py` |
| Conservation limitée | Commande `purger` (voir [Exploitation](#exploitation)) | `test_retention.py` |
| Cloisonnement | 3 rôles PostgreSQL. L'API ne peut pas modifier les contenus. Directus ne voit ni les interactions ni les signalements | `test_droits_base.py` |
| Numéro des demandes de rappel | **Chiffré** dans la base, effacé dès le rappel traité ou après 7 jours | `test_demande_de_rappel_chiffree`, `test_rappels_expires_apres_sept_jours` |
| Enregistrements des appels | Annonce en début d'appel, suppression automatique après 90 jours (fichiers compris) | `test_purge_des_enregistrements_anciens` |
| Numéro à rappeler révélé à un seul agent | Affiché seulement à l'agent qui prend le rappel (verrou en base), jamais dans les listes | `test_prendre_et_cloturer_un_rappel`, `test_liste_des_rappels_sans_numero` |
| Écoute des enregistrements | Réservée au rôle Superviseur qualité. Chaque écoute est journalisée, et le journal survit à la suppression du fichier | `test_ecoute_journalisee`, `test_journal_des_ecoutes_conserve_apres_suppression` |
| Téléphonie sans trace en clair | Pas de CDR, de CEL ni de journal de file. Journaux d'Asterisk sans numéros | `test_logs_et_cdr_sans_numero_en_clair`, `outils/verifier_telephonie.py` |
| Badges des agents | Stockés sous forme d'empreinte. Vérifications plafonnées par numéro | `test_badges_stockes_sous_forme_d_empreinte`, `test_verifications_de_badge_plafonnees` |
| USSD et SMS sans trace en clair | Le numéro ne sert qu'à répondre et n'est pas conservé (empreinte seulement). Le journal des SMS ne garde ni texte ni numéro. Le journal d'accès de l'API retire les paramètres d'adresse (numéro, texte, clé) et Kannel n'écrit que les avertissements | `test_aucun_numero_en_clair`, `test_journal_d_acces_sans_parametres`, `outils/verifier_mobile.py` |
| WhatsApp | Notifications signées seulement. Empreinte du numéro, aucun texte de message conservé, attente oubliée après 30 min. Numéro des abonnés aux rappels **chiffré**, effacé au STOP ou 7 jours après le passage | `test_notification_non_signee_ou_mal_signee_refusee`, `test_journal_sans_texte_ni_numero`, `test_stop_efface_abonnements_et_numero`, `test_expiration_apres_le_passage`, `outils/verifier_whatsapp.py` |
| Contenus validés seulement | L'API ne lit que les contenus `publie`. Seul le rôle Validateur BCR peut publier | `test_questions.py`, `outils/verifier_pile.py` |

**La clé `PEPPER_TELEPHONE` est un secret critique.** Il faut la conserver dans un coffre-fort et **ne jamais la changer en cours d'opération** : les usagers ne seraient plus reconnus. Sa fuite permettrait de retrouver un numéro à partir de son empreinte, par essais successifs.

---

## Exploitation

Les commandes qui modifient le référentiel ou purgent des données passent par le service `migrations`, qui dispose du rôle propriétaire :

```bash
# Mettre à jour le schéma après une nouvelle version
docker compose build && docker compose up -d

# Importer ou mettre à jour le référentiel des territoires
docker compose run --rm migrations python -m coeur.territoires importer donnees/territoires.csv

# Purge de fin de conservation (au plus tard 6 mois après la publication des résultats).
# Supprime tout ce qui a été enregistré AVANT la date donnée. Pour tout effacer : date du lendemain.
docker compose run --rm migrations python -m coeur.retention purger --avant 2028-06-30

# Reconfigurer Directus (après une mise à jour du script ou une erreur de manipulation)
docker compose up directus-config

# Vérifier la chaîne complète Directus → API
python outils/verifier_pile.py
```

### Réglages (`.env`)

| Variable | Défaut | Rôle |
| --- | --- | --- |
| `CLES_API` | (aucun) | Une clé par canal, format `canal:cle,canal:cle`. Canaux : `ussd sms whatsapp web kiosque ambassadeur centre_ecoute` |
| `CLE_MINISTERE` | (aucun) | Accès aux statistiques et aux signalements |
| `PEPPER_TELEPHONE` | (aucun) | Voir [Protection des données](#protection-des-données) |
| `SEUIL_CONFIANCE` | 0.5 | Plus haut : plus d'escalades, moins de risque d'erreur |
| `MARGE_AMBIGUITE` | 0.1 | Écart minimal entre les deux meilleurs contenus |
| `SEUIL_SECRET_STATISTIQUE` | 5 | Effectif minimal publié |
| `CONSERVATION_TEXTE_QUESTIONS` | `tout` | Texte (masqué) des questions gardé dans le journal : `tout`, `escalades` ou `aucun`. À arbitrer par le point focal protection des données |
| `CACHE_CONTENUS_SECONDES` | 60 | Délai maximal de prise en compte d'une publication |
| `ENVIRONNEMENT` | developpement | Avec `production`, le chargement des exemples est refusé |
| `NUMERO_VERT` | (vide) | Affiché par le portail en cas d'escalade. Vide : aucun numéro affiché |
| `PORTAIL_QUESTIONS_PAR_MINUTE` | 20 | Limite par adresse IP |
| `PORTAIL_SIGNALEMENTS_PAR_HEURE` | 5 | Limite par adresse IP |
| `FORWARDED_ALLOW_IPS` | 127.0.0.1 | Adresse du proxy HTTPS (voir [Portail web](#portail-web-et-chatbot)) |
| `SECRET_SESSION` | (aucun) | Signe le cookie du tableau de bord. Le changer déconnecte tout le monde |
| `SESSION_HTTPS_SEULEMENT` | false | À passer à `true` dès que le site est servi en HTTPS |
| `ROLES_TABLEAU_DE_BORD` | Administrator,Validateur BCR,Tableau de bord | Rôles Directus admis au pilotage |
| `ROLES_AGENTS` | Administrator,Agent centre d'appels | Rôles admis à la console des agents |
| `ROLES_QUALITE` | Administrator,Superviseur qualité | Rôles admis à l'écoute qualité |
| `FUSEAU_HORAIRE` | Africa/Kinshasa | Heure affichée et découpage des journées du tableau de bord |
| `CLE_API_CENTRE_ECOUTE` | (aucun) | Clé du canal `centre_ecoute`, partagée par l'API et Asterisk |
| `CLE_CHIFFREMENT` | (aucun) | Clé Fernet de chiffrement des numéros à rappeler. **Secret critique** : sa perte rend les rappels en attente illisibles |
| `SECRET_POSTES` | (aucun) | Secret dont sont dérivés les mots de passe SIP des postes |
| `NB_POSTES` | 6 | Nombre de postes d'agents dans la file |
| `SVI_TOUCHES_LANGUES` | fr:1,ln:2,sw:3,kg:4,lua:5 | Touches du choix de la langue (enregistrées dans les messages) |
| `SVI_SYNTHESE_PROVISOIRE` | false | Voix de synthèse française quand un contenu n'a pas d'audio. Pour les tests seulement |
| `RAPPEL_APRES_SECONDES` | 180 | Attente avant de proposer un rappel |
| `CONSERVATION_ENREGISTREMENTS_JOURS` | 90 | Durée de conservation des conversations enregistrées |
| `CONSERVATION_RAPPELS_JOURS` | 7 | Délai au-delà duquel un numéro à rappeler est effacé |
| `OPERATEUR_SIP_*`, `SIP_ADRESSE_EXTERNE` | (vide) | Liaison de l'opérateur et adresse publique du serveur, aussi annoncée aux navigateurs des agents (voir [asterisk/LISEZMOI.md](asterisk/LISEZMOI.md)) |
| `ASTERISK_WS_URL` | ws://localhost:8088/ws | Adresse WebSocket d'Asterisk vue du navigateur des agents (`wss://…` en production) |
| `SIP_DOMAINE` | rgph2.local | Domaine SIP des postes |
| `TELEPHONIE_SIMULATION`, `SIMULATEUR_MDP` | false, (vide) | Appels simulés et téléphone logiciel de test. **Jamais en production** |
| `USSD_CODE` | (vide) | Code court USSD, affiché par le simulateur |
| `KANNEL_MDP` | (aucun) | Mot de passe du compte d'envoi de Kannel (API et passerelle SMS) |
| `SMS_EXPEDITEUR` | RGPH2 | Nom ou numéro court affiché comme expéditeur, à convenir avec l'opérateur |
| `SMS_REPONSES_PAR_JOUR` | 10 | Plafond de réponses par SMS par numéro et par jour |
| `SMS_SEGMENTS_MAX` | 3 | Longueur maximale d'une réponse ; au-delà, la version courte est envoyée |
| `BADGES_VERIFICATIONS_PAR_HEURE` | 10 | Vérifications de badge par numéro et par heure |
| `OPERATEUR_SMPP_*` | (vide) | Liaison SMPP de l'opérateur (voir [sms/LISEZMOI.md](sms/LISEZMOI.md)) |
| `WHATSAPP_PASSERELLE` | simulation | `meta` une fois le compte ouvert |
| `WHATSAPP_MODELE_RAPPEL`, `WHATSAPP_MODELE_LANGUES` | rappel_passage, fr:fr,sw:sw | Modèle des rappels de passage et ses langues chez Meta (les autres langues reçoivent le français) |
| `WHATSAPP_RAPPELS_JOURS` | 3,1 | Jours avant le passage où le rappel part |
| `WHATSAPP_HEURE_DEBUT`, `WHATSAPP_HEURE_FIN` | 8, 18 | Plage horaire des envois (heure locale) |
| `WHATSAPP_ABONNEMENTS_MAX` | 3 | Territoires suivis par usager |
| `WHATSAPP_ABONNEMENT_JOURS_APRES` | 7 | Effacement de l'abonnement (et du numéro) après la fin du dernier passage |
| `WHATSAPP_NUMERO_ID`, `WHATSAPP_JETON`, `WHATSAPP_SECRET_APP`, `WHATSAPP_JETON_VERIFICATION` | (vide) | Compte WhatsApp Business de l'INS (voir [whatsapp/LISEZMOI.md](whatsapp/LISEZMOI.md)). Sans `WHATSAPP_SECRET_APP`, toute notification est refusée |
| `SMS_SIMULATION`, `SIMULATEUR_MOBILE` | false, false | Opérateur SMS simulé et page `/simulateur`. **Jamais en production** |

### Avant la mise en production

- [ ] Remplacer `donnees/territoires.csv` par le référentiel officiel de l'INS.
- [ ] Générer des secrets forts et uniques, et ranger `PEPPER_TELEPHONE` dans un coffre-fort.
- [ ] Placer l'API et Directus derrière un proxy HTTPS (Nginx, Caddy…), renseigner `FORWARDED_ALLOW_IPS` et passer `SESSION_HTTPS_SEULEMENT=true`. Ne pas exposer PostgreSQL.
- [ ] Renseigner `NUMERO_VERT` dès qu'il est attribué. Faire relire `ln.json` et traduire l'interface en kiswahili, kikongo et tshiluba.
- [ ] Mettre en place des sauvegardes PostgreSQL chiffrées (`pg_dump`) **et tester leur restauration**.
- [ ] Ne pas charger les exemples (`ENVIRONNEMENT=production`).
- [ ] Faire l'audit de sécurité prévu avant l'ouverture de chaque canal.
- [ ] Centre d'appels : obtenir la liaison SIP et le numéro vert (fiche dans `asterisk/LISEZMOI.md`), faire enregistrer les messages vocaux, ranger `CLE_CHIFFREMENT` dans le coffre-fort, `TELEPHONIE_SIMULATION=false` et `SVI_SYNTHESE_PROVISOIRE=false`.
- [ ] Faire valider par le point focal protection des données l'enregistrement des appels (annonce, durée de 90 jours, accès).
- [ ] Faire valider par l'INS l'intitulé du bloc-marque (*Institut national de la statistique, Bureau central du recensement*, dans `src/coeur/charte/__init__.py`) et, le cas échéant, par le Ministère de la Communication et Médias, garant de la charte.
- [ ] USSD et SMS : obtenir le code court (ARPTC), la liaison SMPP et un agrégateur USSD (fiche dans `sms/LISEZMOI.md`). Importer la vraie liste des badges, saisir et publier le calendrier, faire relire les textes en lingala. Mettre `SMS_SIMULATION=false` et `SIMULATEUR_MOBILE=false`.
- [ ] WhatsApp : faire vérifier l'entreprise (INS) chez Meta, obtenir le numéro et le jeton permanent, abonner le webhook en HTTPS, soumettre le profil (fiche dans `whatsapp/LISEZMOI.md`). **Faire arbitrer le transit des messages par Meta** par le point focal protection des données. Faire approuver le modèle `rappel_passage` et prévoir son budget.
- [ ] Console des agents : publier le WebSocket d'Asterisk (port 8088) **en `wss://` derrière le proxy HTTPS**, et renseigner `ASTERISK_WS_URL`. Les navigateurs n'autorisent le micro que sur un site en HTTPS. Renseigner `SIP_ADRESSE_EXTERNE` avec l'adresse IP publique.

---

## Tests

```bash
python -m venv .venv && .venv/Scripts/activate      # Linux/Mac : source .venv/bin/activate
pip install -e ".[dev]"
docker compose -f docker-compose.test.yml up -d     # base jetable, port 5433
pytest
```

- `tests/unitaires/` : moteur de recherche, confidentialité, limiteur de débit, alphabet GSM, mots-clés SMS, longueur des écrans USSD dans chaque langue. Ces tests ne demandent pas de base.
- `tests/integration/` : API de bout en bout contre PostgreSQL, migrations, droits des rôles. Chaque lancement repart d'une base vide et vérifie au passage que les migrations s'appliquent et s'annulent.
- `outils/verifier_console_agent.py` : la console des agents dans un vrai navigateur (Edge piloté par Playwright, micro factice). Connexion du poste, appel décroché et enregistré avec du son, qualification, pause, rappel, écoute qualité journalisée. Prérequis : `pip install -e ".[e2e]"`.
- `outils/verifier_mobile.py` : une session USSD, puis des SMS envoyés par l'opérateur simulé de Kannel (aller et retour), et le contrôle de l'absence de numéro en clair dans la base et les journaux. Il faut `SMS_SIMULATION=true`.
- `outils/verifier_whatsapp.py` : des notifications signées comme celles de Meta, envoyées au webhook (langue, menu, FAQ, question libre, badge, rappel), et le contrôle de l'absence de numéro en clair. Il faut `WHATSAPP_PASSERELLE=simulation` et `SIMULATEUR_MOBILE=true`.
- `outils/verifier_telephonie.py` : trois appels simulés (serveur vocal, rappel, agent) et contrôle de l'absence de numéro en clair. Il faut `TELEPHONIE_SIMULATION=true`.
- `outils/verifier_pile.py` : vérification sur la pile complète, Directus compris : circuit de validation et connexion au tableau de bord. Il ne journalise qu'une seule question, pour ne pas fausser les statistiques.

---

## Faire évoluer le code

**Modifier une table.** Changer le modèle dans `modeles.py`, puis générer la migration et la relire :

```bash
DATABASE_URL=postgresql+psycopg://rgph_admin:test_admin@localhost:5433/rgph_test \
  alembic revision --autogenerate -m "description du changement"
```

Penser aux droits des rôles (voir `_droits()` dans `migrations/versions/0001_schema_initial.py`). Pour vérifier qu'aucun écart ne subsiste entre le code et la base : `alembic check`.

**Ajouter un module.** Créer `src/coeur/<module>/` avec `modeles.py`, `schemas.py`, `service.py` et `routes.py`. Déclarer ses modèles dans `src/coeur/modeles.py` et son routeur dans `src/coeur/main.py`.

**Brancher un canal** (étapes suivantes). Un canal externe (bot WhatsApp, kiosque…) appelle l'API avec sa clé ; il ne lit jamais la base directement. En cas d'`escalade`, il passe la main à un humain. Le calendrier (`/v1/calendrier`) et la vérification des badges (`/v1/badges/verification`) sont à sa disposition.

**Changer d'agrégateur USSD.** `POST /v1/ussd` suit le format le plus répandu (`sessionId`, `phoneNumber`, `text` cumulé, réponse `CON`/`END`). Pour un autre format, ajouter une route qui traduit les champs puis appelle `ussd.service.traiter` ; le moteur ne change pas.

**Changer de moteur de recherche** (par exemple Rasa, après évaluation langue par langue). Écrire une classe qui respecte `MoteurRecherche` (`connaissances/moteur.py`) et l'instancier dans `connaissances/depot.py`. La règle de décision (`decider`) et l'escalade ne changent pas. Garder les tests de `test_moteur.py` comme référence de qualité.

---

## Limites connues et points à trancher

- **Moteur de recherche** : il est lexical (mots et variantes). Il fonctionne bien en français sur la FAQ d'exemple. Pour les langues nationales, la qualité dépendra surtout des **formulations** saisies. Il faut l'évaluer langue par langue avec de vraies questions.
- **Secret statistique** : petites cases masquées, puis masquage complémentaire dans chaque tableau publié (toutes les marges, et les territoires d'une même province). C'est une règle simple, pas une optimisation : elle masque parfois plus que le strict nécessaire, et elle ne couvre pas un croisement entre deux périodes choisies par l'utilisateur (du 1er au 10 moins du 1er au 9). Les chiffres des centres d'appels, de l'USSD et de WhatsApp sont des totaux nationaux, sans répartition à soustraire. À faire valider par le point focal protection des données avant toute publication externe.
- **Texte des questions** : il est conservé, masqué, pour améliorer la FAQ. Un citoyen peut néanmoins y écrire un nom. `CONSERVATION_TEXTE_QUESTIONS=escalades` ne garde que les questions restées sans réponse (celles qui servent à enrichir la FAQ), `aucun` n'en garde aucune. Le choix revient au point focal protection des données.
- **Territoires** : le fichier fourni est un échantillon aux codes provisoires.
- **Hébergement** : le lieu d'hébergement en RDC reste à décider (centre de données local ou cloud avec région locale). La pile Docker convient aux deux options.
- **Interface du portail** : disponible en français et en lingala (proposition à relire). Les autres langues affichent l'interface en français tant que leur fichier `textes/<langue>.json` n'est pas fourni.
- **Limites de débit et anti-doublons** : comptés dans PostgreSQL (tables `UNLOGGED` `coeur.compteurs_debit` et `coeur.memoire_courte`), donc partagés par tous les processus et serveurs. Chaque contrôle coûte un aller-retour à la base ; si la charge du pic le rend trop coûteux, `coeur/limiteur.py` est le seul fichier à changer (Redis par exemple). La fenêtre glissante est estimée à partir de deux fenêtres fixes, et une requête refusée compte aussi : insister prolonge le blocage.
- **Messages vocaux** : tant qu'ils ne sont pas enregistrés, une voix de synthèse française provisoire les remplace, y compris pour les autres langues.
- **Postes partagés** : un poste ne sert qu'à un agent à la fois. Un second agent qui prend le même poste déconnecte le premier.
- **Rappel resté « en cours »** : si l'agent qui l'a pris ne le clôture pas, le rappel reste bloqué jusqu'à l'expiration automatique (7 jours). L'administrateur peut le clôturer depuis son propre compte agent.
- **Codecs** : postes et opérateur en G.711 (A-law, µ-law), sans transcodage. Asterisk n'a pas de module Opus libre.
- **Sessions USSD rejouées** : le menu est recalculé à chaque échange à partir de la saisie cumulée. Il ne dépend donc d'aucune mémoire de session, et une demande répétée par la passerelle ne crée pas de doublon pendant 5 minutes. Ce format est celui de la plupart des agrégateurs ; un opérateur qui n'envoie que la dernière saisie demandera une petite route d'adaptation.
- **Textes USSD et SMS** : en français, avec une proposition en lingala à relire. Les autres langues affichent les menus en français, mais servent les réponses validées dans leur langue.
- **Charte dans Directus** : la page de connexion de Directus garde sa propre police, car Directus ne permet pas de la changer sur ses pages publiques. Le reste de l'application est en Cooper Hewitt.
- **WhatsApp, premier message** : il reçoit l'accueil et le choix de la langue. Une question posée dans ce premier message n'est pas traitée : le citoyen la repose une fois sa langue choisie.
- **Exemples de contenus** : ils sont en français seulement et marqués `[EXEMPLE non validé]`. Aucun texte en langue nationale n'est fourni : il doit venir de traducteurs et être validé par le BCR.
