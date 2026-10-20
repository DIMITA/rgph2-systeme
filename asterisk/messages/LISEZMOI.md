# Messages vocaux du centre d'appels : script d'enregistrement

Chaque message doit être **enregistré par un locuteur natif dans chaque langue**, puis déposé ici :

```
asterisk/messages/<code langue>/<nom du fichier>.wav     (ou .mp3, .ogg, .m4a)
asterisk/messages/fr/accueil.wav
asterisk/messages/ln/accueil.wav
…
```

Le format est converti automatiquement au démarrage (8 kHz, mono). Enregistrez simplement dans un endroit calme, sans musique ni écho. Après dépôt, reconstruisez et redémarrez : `docker compose up -d --build asterisk`.

**En attendant les enregistrements**, une voix de synthèse française **provisoire** est utilisée. Une langue sans enregistrement reprend le message français.

## Messages communs

Ces textes sont la référence française, à traduire et faire valider avant l'enregistrement. Ils sont aussi définis dans `synchro/messages.py`.

| Fichier | Texte (français, à traduire) |
| --- | --- |
| `accueil` | Bienvenue au centre d'écoute du recensement général de la population. Cet appel peut être enregistré pour améliorer la qualité du service. |
| `svi_intro` | Pour écouter une réponse, tapez son numéro. Pour parler à un conseiller, tapez zéro. |
| `touche_1` … `touche_8` | Tapez 1 pour : … Tapez 8 pour : (8 fichiers ; la question suit immédiatement) |
| `aucune_reponse_langue` | Un conseiller va vous répondre. Merci de rester en ligne. |
| `choix_invalide` | Choix non valide. |
| `attente` | Tous nos conseillers sont occupés. Merci de patienter. (répété toutes les 45 s en file d'attente) |
| `hors_service` | Aucun conseiller n'est disponible pour le moment. |
| `rappel_propose` | Pour être rappelé gratuitement par un conseiller, tapez 1. Pour patienter encore, tapez 2. |
| `rappel_confirme` | Votre demande est enregistrée. Un conseiller vous rappellera dès que possible. Au revoir. |
| `rappel_impossible` | Votre numéro n'est pas visible : nous ne pouvons pas vous rappeler. |
| `au_revoir` | Merci de votre appel. Au revoir. |

> `accueil` contient l'**annonce obligatoire de l'enregistrement**. Elle ne doit pas être supprimée.

## Choix de la langue

Le fichier `choix_langue` est enregistré **dans la langue elle-même**, avec **sa touche**. Les touches sont fixées par `SVI_TOUCHES_LANGUES` (par défaut : `fr:1,ln:2,sw:3,kg:4,lua:5`). Si on les change, il faut réenregistrer ces messages.

| Fichier | Contenu attendu |
| --- | --- |
| `fr/choix_langue` | « Pour le français, tapez 1. » |
| `ln/choix_langue` | La même phrase en lingala, avec la touche 2 |
| `sw/choix_langue` | La même phrase en kiswahili, avec la touche 3 |
| `kg/choix_langue` | La même phrase en kikongo, avec la touche 4 |
| `lua/choix_langue` | La même phrase en tshiluba, avec la touche 5 |

## Réponses de la FAQ au téléphone

Elles ne sont **pas** déposées ici. Elles viennent de Directus :

- le champ **`ordre_svi`** du contenu (1 à 8) place la question dans le menu téléphonique ;
- dans chaque traduction, **`audio_question_url`** (la question lue) et **`audio_url`** (la réponse lue) donnent les deux enregistrements.

Le serveur vocal se met à jour tout seul toutes les 5 minutes. Seuls les contenus **publiés** (validés par le BCR) et dotés d'un audio y figurent. La voix de synthèse provisoire peut remplacer l'audio en test (`SVI_SYNTHESE_PROVISOIRE=true`), jamais en production.
