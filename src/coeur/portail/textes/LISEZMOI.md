# Textes de l'interface du portail

Un fichier par langue, nommé d'après le code de la langue dans Directus (`fr.json`, `ln.json`…). Chaque fichier contient les mêmes clés que `fr.json`. Une clé absente est reprise du français, et un test vérifie que chaque fichier n'a ni clé en trop ni clé manquante.

Ces fichiers ne contiennent que les **textes de l'interface** (boutons, consignes, messages). Les réponses aux questions des citoyens se trouvent dans Directus et sont validées par le BCR.

| Fichier | État | À faire avant la mise en ligne |
| --- | --- | --- |
| `fr.json` | Texte de référence | Relecture par le Ministère |
| `ln.json` | **Proposition de traduction**, faite le 20/10/2026 (lingala de Kinshasa, sans marques de ton) | **Relecture par un locuteur natif**, de préférence un traducteur du BCR |

Points à vérifier en priorité dans `ln.json` :

- les termes institutionnels : « botangi bato » pour *recensement*, « Biro monene ya botangi bato » pour *Bureau central du recensement*, « eyano ya leta » pour *réponse officielle* ;
- les emprunts au français (« teritware », « kartie », « ekipi ») : faut-il les garder ou employer des termes lingala ?

Pour ajouter une langue : copier `fr.json` sous le nouveau code (ex. `sw.json`), traduire les valeurs sans toucher aux clés, garder `{numero}` tel quel, puis lancer `pytest`.
