# Textes de l'USSD et des SMS

Un fichier par langue, nommé d'après le code de la langue dans Directus (`fr.json`, `ln.json`…), avec les mêmes clés que `fr.json`. Une clé absente est reprise du français. Un test vérifie qu'aucun fichier n'a de clé en trop ou de marqueur (`{numero}`, `{territoire}`…) oublié.

Ces fichiers ne contiennent que les **textes des menus et des messages**. Les réponses aux questions des citoyens se trouvent dans Directus et sont validées par le BCR.

## Contraintes propres au téléphone basique

- **Un écran USSD fait 182 caractères au plus**, menu compris. Les textes doivent rester très courts ; un test vérifie que chaque écran tient dans cette limite, dans chaque langue.
- **Alphabet des SMS (GSM 03.38)** : é, è, à, ù sont acceptés. Les autres accents (ê, î, ô, ç minuscule…) et les guillemets typographiques sont remplacés automatiquement (ê devient e), car un seul de ces caractères ferait passer un SMS de 160 à 70 caractères.
- **Mots-clés SMS** (AGENT, PASSAGE, NONVISITE, FAUXAGENT, RAPPEL, LANGUE, AIDE) : ils sont les mêmes dans toutes les langues et ne doivent pas être traduits dans les messages.

| Fichier | État | À faire avant la mise en ligne |
| --- | --- | --- |
| `fr.json` | Texte de référence | Relecture par le Ministère |
| `ln.json` | **Proposition de traduction**, faite le 20/10/2026 (lingala de Kinshasa, sans marques de ton) | **Relecture par un locuteur natif**, de préférence un traducteur du BCR |

Points à vérifier en priorité dans `ln.json` : « kalati » pour *badge*, « etuka » pour *province*, « EBOYAMI » pour un badge *retiré*, et les emprunts (« teritware », « kartie », « ekipi »).

Pour ajouter une langue : copier `fr.json` sous le nouveau code (ex. `sw.json`), traduire les valeurs sans toucher aux clés ni aux marqueurs entre accolades, puis lancer `pytest`.
