# RGPH-2 : le cœur du système d'information citoyenne

Ce dépôt contient le **cœur commun** auquel se brancheront les six canaux du RGPH-2 : USSD/SMS, WhatsApp, portail web, kiosques OKAPI, Ambassadeurs et centre d'écoute. Il correspond à la Phase 1, étape 1, de [architecture.md](architecture.md).

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
- [Protection des données](#protection-des-données)
- [Exploitation](#exploitation)
- [Tests](#tests)
- [Faire évoluer le code](#faire-évoluer-le-code)
- [Limites connues et points à trancher](#limites-connues-et-points-à-trancher)

---

## Vue d'ensemble

```
  USSD/SMS  WhatsApp  Web  Kiosques  Ambassadeurs  Centre d'écoute     (étapes suivantes)
      └─────────┴───────┴──────┴───────────┴──────────────┘
                              │  HTTPS + clé d'API par canal
                     ┌────────▼─────────┐
                     │   API « cœur »   │  FastAPI (Python), un seul déploiement
                     │ (monolithe       │
                     │  modulaire)      │
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

Fichiers transverses : `main.py` (assemblage), `config.py` (réglages), `securite.py` (clés d'API), `base.py` (base de données), `commun.py` (types partagés).

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

# 4. (Hors production) Charger la FAQ de démonstration
docker compose run --rm migrations python -m coeur.connaissances charger-exemples

# 5. Vérifier toute la chaîne Directus → API
python outils/verifier_pile.py      # avec les variables du .env chargées dans le shell
```

| Service | Adresse |
| --- | --- |
| API | http://localhost:8000. Documentation interactive : http://localhost:8000/docs |
| Directus | http://localhost:8055 (compte administrateur : `DIRECTUS_ADMIN_EMAIL` / `DIRECTUS_ADMIN_MDP`) |

Au démarrage, `docker compose up` lance dans l'ordre :

- `postgres` crée les rôles à la première initialisation (`db/init/01-roles.sh`) ;
- `migrations` crée ou met à jour les tables (Alembic), puis s'arrête ;
- `api` et `directus` démarrent ;
- `directus-config` règle l'affichage des collections et crée les rôles, puis s'arrête. Ce service peut être relancé sans risque.

---

## Travailler dans Directus

### Les rôles

| Rôle | Peut | Ne peut pas |
| --- | --- | --- |
| **Rédacteur** | Créer des contenus et des traductions, les modifier tant qu'ils sont `brouillon` ou `en_revue` | Publier ; modifier un contenu déjà publié ; toucher aux formulations ; supprimer |
| **Validateur BCR** | Tout ce que fait le Rédacteur, plus publier, archiver, gérer les formulations et les langues | Administrer Directus |
| **Lecteur** | Consulter | Modifier |

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

## Protection des données

Ces règles sont **appliquées par le code** et **vérifiées par des tests**, pas seulement écrites :

| Règle (architecture.md) | Mise en œuvre | Test |
| --- | --- | --- |
| Pas de nom, de pièce d'identité ni de composition du ménage | Tout champ non prévu est refusé (`extra="forbid"`, `commun.py`) | `test_champ_non_prevu_refuse`, `test_donnee_personnelle_non_prevue_refusee` |
| Numéro de téléphone | Jamais stocké. Seule son **empreinte HMAC-SHA256** (`confidentialite/service.py`) est conservée : elle permet de compter les usagers uniques | `test_interaction_journalisee_sans_donnee_personnelle` |
| Textes libres | Les suites de 6 chiffres ou plus et les adresses électroniques sont remplacées par `[masqué]` | `test_confidentialite.py` |
| Statistiques jamais sous le territoire | Seuls les niveaux `national`, `province` et `territoire` existent. La localité des signalements n'est jamais lue par les statistiques | `test_aucune_maille_plus_fine_que_le_territoire`, `test_signalements_agreges_sans_localite` |
| Secret statistique | Effectif entre 1 et 4 masqué (`SEUIL_SECRET_STATISTIQUE`=5). Une ligne entière est masquée si elle compte moins de 5 interactions | `test_niveau_territoire_avec_secret_statistique` |
| Conservation limitée | Commande `purger` (voir [Exploitation](#exploitation)) | `test_retention.py` |
| Cloisonnement | 3 rôles PostgreSQL. L'API ne peut pas modifier les contenus. Directus ne voit ni les interactions ni les signalements | `test_droits_base.py` |
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
| `CACHE_CONTENUS_SECONDES` | 60 | Délai maximal de prise en compte d'une publication |
| `ENVIRONNEMENT` | developpement | Avec `production`, le chargement des exemples est refusé |

### Avant la mise en production

- [ ] Remplacer `donnees/territoires.csv` par le référentiel officiel de l'INS.
- [ ] Générer des secrets forts et uniques, et ranger `PEPPER_TELEPHONE` dans un coffre-fort.
- [ ] Placer l'API et Directus derrière un proxy HTTPS (Nginx, Caddy…). Ne pas exposer PostgreSQL.
- [ ] Mettre en place des sauvegardes PostgreSQL chiffrées (`pg_dump`) **et tester leur restauration**.
- [ ] Ne pas charger les exemples (`ENVIRONNEMENT=production`).
- [ ] Faire l'audit de sécurité prévu avant l'ouverture de chaque canal.

---

## Tests

```bash
python -m venv .venv && .venv/Scripts/activate      # Linux/Mac : source .venv/bin/activate
pip install -e ".[dev]"
docker compose -f docker-compose.test.yml up -d     # base jetable, port 5433
pytest
```

- `tests/unitaires/` : moteur de recherche, confidentialité. Ces tests ne demandent pas de base.
- `tests/integration/` : API de bout en bout contre PostgreSQL, migrations, droits des rôles. Chaque lancement repart d'une base vide et vérifie au passage que les migrations s'appliquent et s'annulent.
- `outils/verifier_pile.py` : vérification sur la pile complète, Directus compris.

---

## Faire évoluer le code

**Modifier une table.** Changer le modèle dans `modeles.py`, puis générer la migration et la relire :

```bash
DATABASE_URL=postgresql+psycopg://rgph_admin:test_admin@localhost:5433/rgph_test \
  alembic revision --autogenerate -m "description du changement"
```

Penser aux droits des rôles (voir `_droits()` dans `migrations/versions/0001_schema_initial.py`). Pour vérifier qu'aucun écart ne subsiste entre le code et la base : `alembic check`.

**Ajouter un module.** Créer `src/coeur/<module>/` avec `modeles.py`, `schemas.py`, `service.py` et `routes.py`. Déclarer ses modèles dans `src/coeur/modeles.py` et son routeur dans `src/coeur/main.py`.

**Brancher un canal** (étapes suivantes). Le canal appelle l'API ; il ne lit jamais la base directement. En cas d'`escalade`, il passe la main à un humain. Pour l'USSD et le SMS, utiliser `reponse_courte`.

**Changer de moteur de recherche** (par exemple Rasa, après évaluation langue par langue). Écrire une classe qui respecte `MoteurRecherche` (`connaissances/moteur.py`) et l'instancier dans `connaissances/depot.py`. La règle de décision (`decider`) et l'escalade ne changent pas. Garder les tests de `test_moteur.py` comme référence de qualité.

---

## Limites connues et points à trancher

- **Moteur de recherche** : il est lexical (mots et variantes). Il fonctionne bien en français sur la FAQ d'exemple. Pour les langues nationales, la qualité dépendra surtout des **formulations** saisies. Il faut l'évaluer langue par langue avec de vraies questions.
- **Secret statistique** : seul le masquage des petites cases est appliqué. En croisant plusieurs niveaux (national moins somme des territoires), on pourrait parfois déduire une valeur masquée. Ce point est à revoir avec le point focal protection des données avant toute publication externe.
- **Texte des questions** : il est conservé, masqué, pour améliorer la FAQ. Un citoyen peut néanmoins y écrire un nom. Si ce risque est jugé trop élevé, on peut ne conserver que le texte des escalades, ou aucun texte.
- **Territoires** : le fichier fourni est un échantillon aux codes provisoires.
- **Hébergement** : le lieu d'hébergement en RDC reste à décider (centre de données local ou cloud avec région locale). La pile Docker convient aux deux options.
- **Exemples de contenus** : ils sont en français seulement et marqués `[EXEMPLE non validé]`. Aucun texte en langue nationale n'est fourni : il doit venir de traducteurs et être validé par le BCR.
