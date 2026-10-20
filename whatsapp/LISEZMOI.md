# WhatsApp : mise en service et fiche pour Meta

Le canal WhatsApp repose sur l'**API officielle de Meta** (« Cloud API »), seule offre encore disponible : l'API qu'on pouvait héberger soi-même (« On-Premises ») a été arrêtée en octobre 2025. Le code se trouve dans `src/coeur/whatsapp/`.

```
citoyen ──► WhatsApp (Meta) ──POST signé──► /v1/whatsapp/webhook (cœur) ──► base fermée, services
   ▲                                                                           │
   └──────────────── API Graph : POST /{numero_id}/messages ◄──────────────────┘
```

## Ce que vit le citoyen

1. Au premier message, il reçoit un accueil et une **liste des langues**. S'il a posé une question dans ce message, elle reçoit sa réponse dès la langue choisie. Sa langue est ensuite retenue, et c'est la même que celle choisie par USSD ou par SMS : l'usager est reconnu par l'empreinte de son numéro.
2. Le **menu** propose : questions fréquentes, date de passage, vérifier un agent, ménage non recensé, parler à un conseiller, changer de langue.
3. Il peut aussi **écrire sa question**. La base fermée donne la **réponse complète validée**, suivie de l'**audio** et de la **vidéo** en langue locale s'ils existent dans Directus (champs `audio_url` et `video_url`). Sans réponse validée, il peut demander à être rappelé, et la demande arrive dans la console des agents avec l'origine « WhatsApp ».
4. Les mots-clés du SMS fonctionnent aussi : `AGENT AB1234`, `PASSAGE GOMA`…
5. Il peut **envoyer un message vocal** dans sa langue. Le bot le transcrit (service `transcription`, voir [transcription/LISEZMOI.md](../transcription/LISEZMOI.md)), cherche le sujet dans la base fermée, puis demande « J'ai compris votre question ainsi : … Est-ce bien cela ? » avec Oui / Non (et l'audio de la question s'il existe). « Oui » : la réponse validée. « Non » : il propose de reformuler ou d'être rappelé. Dans une langue pas encore ouverte (`TRANSCRIPTION_LANGUES`), il propose directement un rappel par un conseiller. La voix n'est jamais enregistrée.
6. Les images et les vidéos ne sont pas lues : le bot invite à écrire ou à parler.

## Démarches au nom de l'INS (hors code)

1. **Meta Business Suite** : créer le portefeuille d'entreprise de l'INS et faire **vérifier l'entreprise** (documents officiels).
2. **Compte WhatsApp Business** et **numéro dédié**. Ce numéro ne doit pas déjà être utilisé dans l'application WhatsApp.
3. **Application Meta** (developers.facebook.com) avec le produit WhatsApp. Il faut relever :
   - l'identifiant du numéro (*Phone number ID*), à mettre dans `WHATSAPP_NUMERO_ID` ;
   - le **secret de l'application**, à mettre dans `WHATSAPP_SECRET_APP`.
4. **Jeton permanent** : créer un *utilisateur système* avec la permission `whatsapp_business_messaging`. Son jeton va dans `WHATSAPP_JETON`. Le jeton temporaire de la console expire en 24 h.
5. **Webhook** : l'adresse est `https://<serveur>/v1/whatsapp/webhook`, en HTTPS obligatoire, avec un certificat valide. Le jeton de vérification est celui de `WHATSAPP_JETON_VERIFICATION`. S'abonner au champ **`messages`**.
6. Passer `WHATSAPP_PASSERELLE=meta`, puis lancer `docker compose up -d api`.

### Profil du compte (charte graphique du Gouvernement)

| Élément | Valeur proposée |
| --- | --- |
| Nom affiché | **RGPH-2 · INS** (soumis à l'approbation de Meta, qui exige un lien visible avec l'entreprise vérifiée) |
| Photo de profil | `src/coeur/charte/statique/profil-whatsapp.png` : armoiries « Le Gouvernement » en couleur sur fond blanc, 640 × 640 |
| Catégorie | Administration publique |
| Description | « Service officiel d'information du 2e Recensement général de la population et de l'habitat. Institut national de la statistique, Bureau central du recensement. » |
| Site web | https://rgph.cd |

## Médias (audio et vidéo)

Meta télécharge lui-même les fichiers : `audio_url` et `video_url` doivent être des **adresses HTTPS publiques**.

| Type | Formats | Taille maximale |
| --- | --- | --- |
| Audio | MP3, AAC, OGG (Opus) | 16 Mo |
| Vidéo | MP4 (H.264 et AAC) | 16 Mo |

## Coûts

Les réponses envoyées dans les **24 heures** qui suivent un message du citoyen sont **gratuites**. Les messages envoyés hors de cette fenêtre, c'est-à-dire les rappels de passage, passent par des **modèles approuvés par Meta** et sont facturés selon la grille tarifaire de Meta pour la RDC. Le journal `coeur.whatsapp_messages` compte les uns et les autres, sans texte ni numéro.

## Rappels de passage

Après avoir consulté la date de passage d'un territoire, le citoyen peut toucher **« Prévenez-moi »**. C'est un consentement explicite. Il reçoit alors un message **3 jours avant** le passage, puis **la veille**. Il peut suivre trois territoires au plus.

- **Si les dates ne sont pas encore publiées**, l'abonnement est quand même accepté. Les rappels partiront dès que le BCR aura publié les dates dans Directus.
- **Les envois** se font entre 8 h et 18 h (heure de Kinshasa), par le service `taches`, toutes les heures. Un même rappel n'est jamais envoyé deux fois.
- **`STOP`**, écrit ou touché sous un rappel, efface tous les abonnements de l'usager et son numéro.
- **Le numéro est conservé chiffré** (Fernet), comme pour les demandes de rappel téléphonique, car il faut pouvoir écrire plus tard. Il est effacé au `STOP`, ou 7 jours après la fin du dernier passage publié dans le territoire.

### Modèle à soumettre à Meta

Hors de la fenêtre de 24 h, WhatsApp n'autorise que des **modèles approuvés**. Il faut soumettre celui-ci dans le gestionnaire WhatsApp :

| Champ | Valeur |
| --- | --- |
| Nom | `rappel_passage` (réglage `WHATSAPP_MODELE_RAPPEL`) |
| Catégorie | **Utilité** (*Utility*) |
| Langues | Français (`fr`). Kiswahili (`sw`) une fois traduit. Meta ne propose pas le lingala, le kikongo ni le tshiluba : ces usagers reçoivent la version française (réglage `WHATSAPP_MODELE_LANGUES`) |
| Corps (fr) | `Recensement RGPH-2 : les agents recenseurs passeront à {{1}} du {{2}} au {{3}}. Ils portent un badge officiel avec photo : vous pouvez le vérifier ici en écrivant AGENT suivi de son numéro.` |
| Exemple des variables | `Goma`, `17/05/2027`, `30/05/2027` |
| Bouton | Réponse rapide : `Arrêter les rappels` |

Chaque rappel est **facturé** au tarif « Utilité » de Meta pour la RDC. Le tableau de bord compte les rappels envoyés.

## Données personnelles

- **Les messages transitent par Meta**, donc hors de RDC. C'est un écart avec l'exigence de localisation de l'architecture, à faire **arbitrer par le point focal protection des données**. Le cœur limite ce qu'il garde lui-même :
  - **l'empreinte du numéro**, jamais le numéro ;
  - **ni le texte des messages**, ni dans le journal ni ailleurs. Seules les questions posées au moteur sont journalisées, masquées, comme sur les autres canaux ;
  - **une attente de 30 minutes au plus** (`coeur.conversations_whatsapp`) : on y note seulement « numéro de badge attendu » ou le territoire déjà choisi ;
  - **le numéro chiffré des abonnés aux rappels** (`coeur.abonnements_whatsapp`), effacé au `STOP` ou après le passage.
- **Signature** : toute notification sans signature valide de Meta est refusée (HTTP 401).

## Tester sans compte Meta

- **Simulateur** : avec `SIMULATEUR_MOBILE=true`, la page http://localhost:8000/simulateur a une section WhatsApp, avec les listes et les boutons cliquables.
- **Rappels de passage** : le bouton « Envoyer maintenant les rappels de passage dus » du simulateur évite d'attendre la tâche horaire.
- **De bout en bout** : `python outils/verifier_whatsapp.py`, rappels de passage compris. Il envoie au webhook des notifications **signées comme celles de Meta** et vérifie les réponses au format exact de l'API Graph.
