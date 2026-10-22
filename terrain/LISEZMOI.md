# Kiosques OKAPI et Ambassadeurs : mise en service des appareils

Les deux canaux de terrain utilisent **la même application**, servie par le cœur à l'adresse `https://<serveur>/terrain/`. C'est une application web installable (PWA) : rien à publier sur un magasin d'applications, et elle se met à jour toute seule à la synchronisation. Le code se trouve dans `src/coeur/terrain/`.

```
 tablette du kiosque / téléphone de l'Ambassadeur          cœur (HTTPS)
 ┌───────────────────────────────────────────┐
 │ application /terrain/ (service worker)    │  ── activation (une fois) ──► /v1/terrain/activation
 │  - paquet : FAQ, calendrier, territoires  │  ◄── paquet (si changé) ───── /v1/terrain/paquet
 │  - file d'envois (IndexedDB)              │  ── remontées (par lots) ───► /v1/terrain/remontees
 └───────────────────────────────────────────┘  ── badge (en ligne) ───────► /v1/terrain/badge
```

## Ce que fait l'appareil

| | Kiosque OKAPI | Ambassadeur |
| --- | --- | --- |
| Questions fréquentes validées, recherche, audio | oui, hors ligne | oui, hors ligne |
| Date de passage d'un territoire | oui, hors ligne | oui, hors ligne |
| Ménage non recensé, agent douteux | oui, envoyé au retour du réseau | oui, envoyé au retour du réseau |
| Question absente de la FAQ | « Ma question n'est pas dans la liste » | « Remonter une question ou un doute » |
| Rumeur | non | « Remonter une rumeur » |
| Vérifier un badge | **en ligne seulement** | **en ligne seulement** |
| Choix de la langue | à chaque visiteur ; retour à ce choix après 2 minutes sans action | retenu |

- **Hors ligne**, l'appareil n'affiche que des contenus **publiés et validés par le BCR**, téléchargés lors de la dernière synchronisation. La recherche filtre les questions de la FAQ : elle ne fabrique jamais de réponse.
- Ce qui est saisi hors ligne part dans une **file d'attente**, envoyée dès que le réseau revient (au retour du réseau, toutes les 5 minutes, à l'ouverture de l'application, ou avec le bouton « Synchroniser »). La barre du bas indique l'état du réseau, la date des informations et le nombre d'envois en attente.
- Chaque envoi porte un identifiant tiré au hasard : un envoi répété (réponse perdue en route) n'est **jamais compté deux fois**.
- La **vérification de badge** reste en ligne. Embarquer la liste des badges dans les tablettes reviendrait à la donner aux faussaires : les numéros sont trop courts pour qu'une empreinte les protège. Hors ligne, l'application renvoie vers l'USSD.
- Au tableau de bord, les remontées apparaissent comme les autres : questions dans « Questions sans réponse » (motif « Recueillie sur le terrain »), signalements et rumeurs dans « Signalements », consultations dans les statistiques, sous les canaux « Kiosques » et « Ambassadeurs ».

## Enrôler un appareil

1. Dans le tableau de bord, espace **Kiosques et Ambassadeurs** (rôles `ROLES_TERRAIN`, par défaut *Administrator*), remplir « Enrôler un appareil » :
   - **code** de l'appareil, par exemple `KIO-NKV-GOM-01` ou `AMB-KCE-MAT-07` ;
   - **territoire** du kiosque ou de l'Ambassadeur (proposé par défaut dans les formulaires) ;
   - **lieu** du kiosque (école, mairie…) ;
   - **langues** à embarquer : le français l'est toujours. Ne cocher que celles de la zone, pour limiter le volume d'audio à télécharger.
2. Le **code d'activation** (12 caractères) s'affiche **une seule fois**. Il est valable `TERRAIN_ACTIVATION_JOURS` (7 jours).
3. Sur l'appareil, **avec du réseau** : ouvrir `https://<serveur>/terrain/`, saisir le code. L'application télécharge aussitôt le paquet. Elle fonctionne ensuite sans réseau.
4. Installer l'application sur l'écran d'accueil : menu de Chrome, « Ajouter à l'écran d'accueil » (ou « Installer l'application »).

**Aucun nom de personne** n'est enregistré : un Ambassadeur n'est connu que par le code de son appareil. La correspondance entre codes et Ambassadeurs reste à l'INS.

### Appareil perdu, volé ou remplacé

- **Révoquer** : l'appareil ne peut plus rien envoyer ni télécharger. À sa prochaine synchronisation, l'application revient à l'écran d'activation.
- **Nouveau code** : pour une tablette remplacée ou une application réinstallée (données du navigateur effacées). L'ancien jeton cesse aussitôt de fonctionner. Les envois en attente sur un appareil révoqué partent si on le réactive avec un nouveau code.
- La liste signale « à vérifier » un appareil actif qui ne s'est pas synchronisé depuis 7 jours : sa FAQ et son calendrier sont peut-être périmés.

## Préparer les tablettes des kiosques

- **Android 9 ou plus**, avec **Chrome à jour**. Les autres navigateurs ne sont pas testés.
- **Ne jamais effacer les données de Chrome** : elles contiennent le jeton, le paquet et la file d'envois. L'application demande au navigateur un stockage persistant, que Chrome accorde aux applications installées.
- **Mode kiosque** : activer l'**épinglage d'écran** d'Android (Paramètres > Sécurité > Épinglage de l'application), ouvrir l'application installée, puis l'épingler. Pour un parc entier, un lanceur de kiosque géré (MDM) fait la même chose à distance.
- Désactiver la mise en veille de l'écran pendant les heures d'ouverture. Prévoir l'alimentation solaire et le lieu sécurisé prévus dans architecture.md.
- Synchroniser au moins **une fois par semaine** (passage d'un Ambassadeur avec un partage de connexion, ou retour au réseau). Le paquet ne fait que quelques dizaines de Ko hors audio, et n'est retéléchargé que s'il a changé.

## Audio hors ligne

L'audio des réponses (`audio_url` dans Directus) est téléchargé à chaque synchronisation pour les langues de l'appareil, puis servi sans réseau. Pour que cela marche bien, le serveur qui héberge les fichiers audio doit répondre en HTTPS avec l'en-tête **`Access-Control-Allow-Origin: https://<serveur du cœur>`**. Sans cet en-tête, l'audio est gardé quand même, mais la lecture hors ligne peut échouer sur certains appareils. **À vérifier sur les tablettes retenues.** Les vidéos ne sont pas gardées : trop lourdes pour les zones sans réseau.

## Exploitation

| Réglage | Défaut | Rôle |
| --- | --- | --- |
| `ROLES_TERRAIN` | `Administrator` | Rôles Directus qui enrôlent et révoquent les appareils |
| `TERRAIN_ACTIVATION_JOURS` | 7 | Validité d'un code d'activation |
| `CONSERVATION_REMONTEES_JOURS` | 60 | Durée de vie des identifiants anti-doublon des remontées |

- Une remontée datée de plus de 60 jours, ou dans le futur (horloge de la tablette déréglée), prend l'heure de réception.
- Un lot compte 200 remontées au plus. L'application envoie plusieurs lots de suite si besoin.
- Les essais d'activation sont limités à 10 par quart d'heure et par adresse IP. Les vérifications de badge sont limitées par appareil (`BADGES_VERIFICATIONS_PAR_HEURE`).
- Le service worker exige **HTTPS** (sauf sur `localhost`, pour les essais).

## Tester

- `tests/integration/test_terrain.py` : API et espace du tableau de bord.
- `tests/integration/test_terrain_navigateur.py` : l'application dans Chromium. Le serveur est **réellement arrêté** au milieu du parcours (page et service worker sans réseau), puis relancé : rien n'est perdu ni doublé, et la révocation ramène à l'écran d'activation. Prérequis : `pip install -e ".[e2e]"` puis `python -m playwright install chromium` (ou `NAVIGATEUR_E2E=/chemin/vers/chrome`).
- À la main : enrôler un appareil dans le tableau de bord, ouvrir `http://localhost:8000/terrain/` dans Chrome, puis cocher « Offline » dans les outils de développement (onglet Application > Service workers).
