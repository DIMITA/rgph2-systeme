# Transcription des messages vocaux

Ce conteneur transforme un message vocal en texte, dans la langue du citoyen. Le cœur s'en sert pour les messages vocaux WhatsApp : le texte obtenu passe ensuite par la base fermée, et le citoyen **confirme le sujet compris** avant de recevoir la réponse validée (voir architecture.md). Le service ne répond à rien lui-même : il transcrit.

```
WhatsApp ──vocal──► cœur ──audio──► transcription ──texte──► cœur : base fermée ──► « Vous voulez savoir : … ? Oui / Non »
```

## Démarrer

```bash
docker compose --profile transcription up -d transcription
docker compose exec transcription python -c "import urllib.request as u; print(u.urlopen('http://localhost:9000/sante').read())"
```

Puis régler le cœur (réglages chiffrés en base) : `transcription` à `service`, et `transcription_langues` avec les langues **déjà évaluées** (voir plus bas), par exemple `sw,ln` :

```bash
docker compose run --rm migrations python -m coeur.reglages definir transcription service
docker compose run --rm migrations python -m coeur.reglages definir transcription_langues sw,ln
docker compose restart api taches
```

Le modèle et les codes de langue du service se règlent dans `.env` (`TRANSCRIPTION_MODELE`, `TRANSCRIPTION_CODES`). Une langue absente de cette liste n'est pas transcrite : le citoyen se voit proposer un rappel par un conseiller.

Au premier démarrage, le modèle est téléchargé depuis Hugging Face (environ 4 Go), puis gardé dans le volume `modeles_transcription`. **Si le serveur de production n'a pas accès à Internet**, télécharger le modèle ailleurs (`huggingface-cli download facebook/mms-1b-all`) et copier le dossier du cache dans ce volume.

## Le modèle

Par défaut : **Meta MMS** (*Massively Multilingual Speech*, `facebook/mms-1b-all`), un modèle de reconnaissance vocale entraîné sur plus de 1 100 langues, avec un adaptateur par langue.

| Langue (cœur) | Code du modèle | À vérifier |
| --- | --- | --- |
| Français | `fra` | |
| Lingala | `lin` | |
| Kiswahili | `swh` | Le kiswahili du Congo diffère du kiswahili standard de l'entraînement |
| Kikongo | `kng` | **Quel kikongo ?** Pour le kikongo ya leta (kituba), mettre `kg:ktu` dans `TRANSCRIPTION_CODES`, si le modèle le connaît |
| Tshiluba | `lua` | |

Au démarrage, le service écarte et signale dans son journal toute langue que le modèle ne connaît pas. `GET /sante` donne la liste des langues effectivement disponibles.

- **Licence : MMS est publié sous CC-BY-NC 4.0 (pas d'usage commercial).** Un service public d'information sans contrepartie financière semble compatible, mais **c'est à faire confirmer** (juriste de l'INS ou de l'UNFPA) avant la mise en service, en particulier si un prestataire exploite le service.
- **Qualité : inconnue tant qu'elle n'est pas mesurée.** On peut s'attendre à des erreurs nombreuses sur les langues peu dotées : c'est pour cela que le citoyen confirme toujours le sujet compris.
- **Mélange de langues** (lingala et français dans la même phrase, très courant) : le modèle transcrit dans une seule langue à la fois, celle du citoyen. Les mots français mal transcrits pénalisent moins qu'on ne croit, car la base fermée cherche un sujet, pas une phrase exacte. À mesurer aussi.

### Changer de modèle

Tout service qui respecte le même contrat peut remplacer celui-ci, sans toucher au cœur : un autre modèle open source (Whisper, Omnilingual ASR de Meta…), ou un service externe si la localisation des données le permet. Dans `serveur.py`, il suffit d'écrire une classe qui respecte `Moteur` (`langues()` et `transcrire()`).

```
POST /transcrire?langue=ln      corps : fichier audio (ogg/opus, mp3, wav, m4a…)
→ 200 {"texte": "…", "langue": "ln"}
→ 422 langue non prise en charge ou audio illisible ; 413 audio trop long (DUREE_MAX)
```

## Mesures

Workflow `.github/workflows/transcription.yml` (script `evaluer_fleurs.py`) : le vrai modèle, sur des phrases lues par des locuteurs natifs (Google FLEURS, jeu de test), converties au format des messages vocaux WhatsApp (Ogg/Opus 16 kb/s), envoyées au service HTTP réel. Processeur seul, 4 cœurs.

Mesure du 20 octobre 2026, `facebook/mms-1b-all`, 40 enregistrements par langue :

| Langue | Taux d'erreur de mots (moyen / médian) | Durée moyenne | Calcul moyen | Calcul par seconde d'audio |
| --- | --- | --- | --- | --- |
| Français | 16 % / 15 % | 10 s | 3,6 s | 0,36 s |
| Lingala (RDC) | 18 % / 17 % | 20 s | 7,2 s | 0,36 s |
| Kiswahili (Kenya) | 16 % / 14 % | 14,5 s | 5,1 s | 0,35 s |
| Kikongo | **pas d'adaptateur dans le modèle** (`kng`, `ktu`, `kon`, `kwy`) | | | |
| Tshiluba | **pas d'adaptateur dans le modèle** (`lua`) | | | |

Ce que ça dit, et ce que ça ne dit pas :

- Le lingala et le kiswahili sont transcrits à peu près aussi bien que le français : environ une erreur pour six mots. Les erreurs portent surtout sur l'orthographe, les nombres et les noms propres (« parchemin » → « parchemen », « 24½ » → « 241 »). C'est peu gênant pour retrouver un sujet de la FAQ.
- Ce sont des **phrases générales lues à voix haute, au calme**. De vraies questions spontanées, dans la rue, souvent en mélangeant lingala et français, donneront de moins bons résultats. Seule l'évaluation sur de vrais messages du recensement (plus bas) permet d'ouvrir une langue.
- Le kiswahili de FLEURS est celui du Kenya, pas celui de l'est de la RDC.
- **Kikongo et tshiluba ne sont pas couverts par ce modèle.** Sans autre modèle, ces deux langues restent en « proposition de rappel par un conseiller ». Le rapport de la mesure vérifie aussi les autres versions de MMS.
- Sur processeur seul, le calcul prend environ un tiers de la durée de l'audio, un message à la fois : moins de 3 secondes d'audio transcrites par seconde. C'est assez pour un pilote, pas pour le pic.

## Matériel

Sur processeur, la transcription d'un message de 30 secondes prend plusieurs secondes, et le service traite **un message à la fois** (l'adaptateur de langue est partagé). C'est suffisant pour un pilote et pour les évaluations, **pas pour le pic de mai-juin 2027**. Pour le pic, il faut un **GPU** (voir le commentaire dans `docker-compose.yml` et le `Dockerfile`), ou plusieurs instances. Le dimensionnement dépend du volume de messages vocaux attendu : à mesurer pendant le pilote (tableau de bord, section WhatsApp).

## Ouvrir une langue

1. Recueillir de **vrais messages vocaux** dans la langue, avec pour chacun la question de la FAQ attendue, ou rien si elle est hors champ. Sources possibles : Ambassadeurs, centre d'écoute, séances d'enregistrement. Au moins une centaine par langue, de personnes et de lieux variés.
2. Les décrire dans un CSV (`langue,audio,transcription,attendu`, voir `src/coeur/connaissances/evaluation.py`), puis, avec `TRANSCRIPTION=service` :
   ```bash
   python -m coeur.connaissances.evaluation vocaux_ln.csv --seuils 0.4,0.5,0.6 --details
   ```
3. Décider avec le BCR sur les chiffres : part de bons sujets, part de sujets faux (le citoyen dira « Non »), taux d'erreur de mots. Les sujets faux ne donnent jamais de fausse information, puisqu'il y a confirmation, mais trop de « Non » découragent le citoyen.
4. Ajouter la langue au réglage `transcription_langues` (`docker compose run --rm migrations python -m coeur.reglages definir transcription_langues sw,ln,lua`). Après l'ouverture, suivre au tableau de bord (section WhatsApp) les messages vocaux confirmés et refusés.

## Protection des données

- La voix n'est **jamais écrite sur disque** : décodée en mémoire par ffmpeg, transcrite, puis oubliée. Le service ne journalise aucun texte transcrit.
- Le cœur ne garde que la transcription masquée (numéros et courriels retirés), selon `CONSERVATION_TEXTE_QUESTIONS`, comme une question écrite.
- Le service n'est joignable que depuis le réseau interne de Docker : ne pas publier son port.

## Tester

- `tests/unitaires/test_service_transcription.py` : le contrat HTTP et le décodage d'un vrai message Ogg/Opus par ffmpeg, avec un moteur factice. **Le modèle MMS lui-même n'est pas exécuté par les tests**, trop lourd.
- Dans le cœur, `TRANSCRIPTION=simulation` remplace le service : le « son » est le texte lui-même (tests, simulateur).
