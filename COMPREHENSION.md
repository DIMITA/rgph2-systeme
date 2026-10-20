# Comprendre les langues nationales : ce qui est mesuré, ce qui reste à faire

Le système ne rédige jamais de réponse : il reconnaît le **sujet** d'une question parmi ceux de la FAQ validée (voir `architecture.md`). Deux étapes peuvent échouer, et se mesurent séparément :

1. **La voix → le texte** (transcription) : messages vocaux WhatsApp et question dite au serveur vocal (touche 9). Service `transcription/`.
2. **Le texte → le sujet** (compréhension) : toute question écrite (USSD, SMS, WhatsApp, web) ou transcrite. Moteur du cœur, `src/coeur/connaissances/moteur.py`.

Aucune langue n'est ouverte sur la foi de ce document : il dit quels modèles valent la peine d'être évalués sur **de vraies questions du recensement** (`python -m coeur.connaissances.evaluation`), seule mesure qui décide.

## 1. La voix

### Ce qui est mesuré

Le détail est dans `transcription/LISEZMOI.md`. En résumé (Google FLEURS, phrases lues, format WhatsApp) :

| Langue | Meta MMS (`mms-1b-all`) | Meta Omnilingual ASR |
| --- | --- | --- |
| Français | 16 % d'erreur de mots | mesure en cours |
| Lingala | 18 % | mesure en cours |
| Kiswahili | 16 % | mesure en cours |
| Tshiluba | **absent** | mesure en cours |
| Kikongo | **absent** | mesure en cours |

La mesure d'Omnilingual ASR (modèles CTC 1B et LLM 1B, workflow `transcription.yml`) est en cours ; ce tableau sera complété avec ses résultats. Omnilingual connaît le tshiluba (`lua_Latn`), pas le kikongo.

### Le kikongo : la démarche proposée

Aucun modèle ouvert n'a de code pour le kikongo (ni `kng`, ni `ktu`, ni `kon`), ni en kikongo ya leta (kituba) ni en kikongo. Il n'existe pas non plus d'enregistrements publics transcrits pour le mesurer. La démarche, du moins cher au plus cher, chaque étape ne se faisant que si la précédente ne suffit pas :

1. **Décider de la variante** (Ministère) : kituba (kikongo ya leta, langue véhiculaire de l'Ouest) ou kikongo. Les traductions de la FAQ, les messages vocaux et le modèle en dépendent ; c'est déjà dans « À décider en Phase 1 ».
2. **Recueillir 100 à 200 questions dites** dans cette variante, avec leur transcription et le sujet attendu, par les Ambassadeurs ou en séance d'enregistrement (une demi-journée par locuteur, une dizaine de locuteurs de lieux différents). Ce jeu sert à mesurer, quelle que soit la suite : il faut le faire de toute façon.
3. **Mesurer sans entraînement** :
   - Omnilingual ASR **sans code de langue** (`kg:-` dans `CODES_LANGUES`, déjà prévu) : le modèle CTC transcrit toute langue écrite en alphabet latin. Le kikongo s'écrit de façon assez régulière, et la base fermée cherche un sujet, pas une phrase exacte : une transcription imparfaite peut suffire.
   - `omniASR_LLM_7B_ZS` (« zero-shot ») : on lui donne une dizaine d'exemples (audio + texte) de la langue, et il transcrit les suivants. C'est fait pour les langues absentes de l'entraînement, mais il faut un GPU (7 milliards de paramètres).
4. **Entraîner, si la mesure ne suffit pas** : affiner MMS (un adaptateur de langue) ou Omnilingual CTC sur **5 à 10 heures** de parole transcrite. Sources : séances d'enregistrement (lecture des questions de la FAQ et de textes courts), enregistrements bibliques existants (droits à négocier), collecte Mozilla Common Voice. Quelques jours de GPU, et un ingénieur pour un mois environ.
5. **En attendant, et si rien ne suffit** : le kikongo reste en **rappel par un conseiller** (comportement actuel), et à l'écrit, sur les formulations saisies dans le CMS.

Le tshiluba suit les étapes 2 et 3 (le modèle le connaît, il reste à le mesurer sur de vraies questions), puis 4 si nécessaire.

## 2. Le texte

### Aujourd'hui

Le moteur du cœur est **lexical** : il compare les mots de la question à ceux des questions et formulations enregistrées dans le CMS, langue par langue, en tolérant pluriels, conjugaisons et fautes de frappe. Il ne comprend une question en lingala que si une formulation proche, **en lingala**, a été saisie. Sa qualité dépend donc entièrement du travail de traduction et de collecte de formulations.

### Ce qui est mesuré : un modèle multilingue fait-il mieux ?

Script `outils/evaluer_comprehension_texte.py`, workflow `comprehension.yml`. FLORES-200 (Meta, CC-BY-SA 4.0) contient 1 012 phrases traduites par des professionnels en lingala, kiswahili, kikongo (`kon_Latn`) et tshiluba. Pour chaque phrase en langue nationale, le modèle doit retrouver **sa traduction française** : dans un lot de 100 (la taille d'une FAQ), et parmi les 1 012. C'est la situation d'une FAQ rédigée en français et interrogée dans une autre langue, **sans aucune formulation traduite**.

Mesure du 20 octobre 2026, processeur seul :

| Modèle (licence) | Lingala | Kiswahili | Kikongo | Tshiluba | Calcul (5 × 1 012 phrases) |
| --- | --- | --- | --- | --- | --- |
| Moteur lexical du cœur (référence, 300 phrases, lot seulement) | 76 % | 68 % | 79 % | 84 % | 142 s |
| LaBSE (Apache 2.0) | 81 % / 70 % | 100 % / 100 % | 82 % / 69 % | 79 % / 70 % | 394 s |
| multilingual-e5-base (MIT) | 100 % / 97 % | 100 % / 100 % | 97 % / 92 % | 92 % / 83 % | 461 s |
| BGE-M3 (MIT) | 99 % / 95 % | 100 % / 100 % | 97 % / 91 % | 93 % / 85 % | 1 526 s |
| **SONAR** (Meta, **non commerciale**) | **100 % / 100 %** | **100 % / 100 %** | **100 % / 100 %** | **99 % / 99 %** | 2 309 s |

(« lot / tout » : bonne traduction première dans un lot de 100 / parmi les 1 012.)

Ce que ça dit :

- **Le test est trop facile, et il faut le savoir.** Le moteur lexical, qui ne comprend aucune de ces langues, retrouve déjà 68 à 84 % des phrases dans un lot de 100 : les phrases de FLORES sont longues et pleines de noms propres, de nombres et de mots empruntés (« diabete », « Martelly »). Une vraie question de citoyen (« bato ya recensement bakoya mokolo nini ? ») n'a rien de tout cela. Seule la colonne « parmi les 1 012 » départage vraiment les modèles.
- **Sur ce critère, deux familles se détachent** : SONAR, à peu près parfait dans les quatre langues, et multilingual-e5 ou BGE-M3, bons en lingala et en kikongo, plus faibles en tshiluba (83 à 85 %). LaBSE ne connaît vraiment que le kiswahili.
- **SONAR a été entraîné sur les 200 langues de NLLB**, dont celles-ci, avec des données proches de FLORES : son score parfait est en partie un effet de proximité. Et son encodeur de texte est publié sous **licence non commerciale** (fichier `LICENSE.md` du paquet `sonar-space`, vérifié le 20 octobre 2026), comme MMS : même question juridique à trancher. multilingual-e5-base (MIT) est l'alternative sans réserve de licence.
- Le **kikongo de FLORES** (`kon_Latn`) n'est pas forcément la variante retenue par le Ministère (voir plus haut).
- Coût : quelques dixièmes de seconde par question courte sur processeur pour e5, davantage pour SONAR. C'est acceptable, à condition de calculer à l'avance les vecteurs des questions de la FAQ.

### La démarche proposée

Un modèle multilingue ne remplace pas le moteur lexical : il **s'y ajoute**, pour les questions qu'aucune formulation saisie ne couvre.

1. **Construire le jeu d'évaluation écrit** : 100 à 200 vraies questions par langue, avec le sujet attendu (y compris des questions hors champ, qui doivent escalader). C'est le même recueil que pour la voix, en version écrite ; les SMS et les messages WhatsApp du pilote en fourniront aussi.
2. **Brancher un moteur sémantique** derrière l'interface `MoteurRecherche` (rien d'autre ne change) : un petit service à part, comme la transcription, qui calcule les vecteurs des questions publiées à chaque rafraîchissement du corpus et cherche la plus proche. Le cœur combine les deux moteurs : la meilleure réponse lexicale, sinon la meilleure sémantique. Candidats : multilingual-e5-base (MIT, plus léger, sans réserve) en premier ; SONAR (meilleur, mais licence non commerciale) si le juriste valide l'usage, en même temps que pour MMS.
3. **Calibrer un seuil propre** à ce moteur : ses scores ne sont pas sur la même échelle que ceux du moteur lexical. Le réglage se fait langue par langue, sur le jeu d'évaluation, en visant **zéro réponse fausse** à l'écrit (une réponse fausse donne une information officielle hors sujet) quitte à escalader plus souvent.
4. **Ouvrir langue par langue**, comme pour la voix, et suivre au tableau de bord la part de questions escaladées.

Le travail des traducteurs garde toute sa valeur : les formulations saisies dans le CMS restent la voie la plus sûre, et le jeu d'évaluation dira de combien le modèle les complète.
